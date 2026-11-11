// FailoverLab: SimulationEngine Runtime
// Wraps pure reducer with clock timer, re-entrancy protection, and subscriber notification

import {
  simulationReducer,
  INITIAL_SIMULATION_STATE,
} from './transitions';
import type {
  SimulationState,
  SimulationAction,
  SimulationConfig,
} from './types';
import { controllerClient, type ControllerStateDto, type PolicyDto } from '../api/controllerClient';

export class SimulationEngine {
  private state: SimulationState;
  private listeners: Set<(state: SimulationState) => void> = new Set();
  private intervalId: ReturnType<typeof setInterval> | null = null;
  private isRunning: boolean = true;
  private tickSpeed: number = 1; // 1x, 2x, 5x
  private activeTimeouts: Set<ReturnType<typeof setTimeout>> = new Set();
  private isBackendConnected: boolean = false;

  constructor() {
    this.state = { ...INITIAL_SIMULATION_STATE };
    this.setupTimer();
  }

  public getIsBackendConnected(): boolean {
    return this.isBackendConnected;
  }

  public setBackendConnected(connected: boolean) {
    this.isBackendConnected = connected;
    this.notify();
  }

  public applyBackendState(dto: ControllerStateDto) {
    if (!dto) return;

    const regA = dto.region_a ? {
      id: 'region-a' as const,
      name: dto.region_a.name || 'Mumbai',
      cloudZone: dto.region_a.cloud_zone || 'ap-south-1',
      role: dto.region_a.role as 'ACTIVE' | 'STANDBY',
      health: dto.region_a.health as 'HEALTHY' | 'DEGRADED' | 'DOWN',
      status: (dto.region_a.health === 'HEALTHY' ? (dto.region_a.is_fenced ? 'fenced' : 'healthy') : 'failed') as any,
      acceptsWrites: Boolean(dto.region_a.accepts_writes),
      ingressTrafficPercent: dto.region_a.ingress_traffic_percent ?? (dto.region_a.role === 'ACTIVE' ? 100 : 0),
      ingressRps: dto.region_a.ingress_rps ?? (dto.region_a.role === 'ACTIVE' ? 2450 : 0),
      appServersHealthy: dto.region_a.app_servers_healthy ?? 8,
      appServersTotal: dto.region_a.app_servers_total ?? 8,
      activeConnections: dto.region_a.active_connections ?? 1420,
      iops: dto.region_a.iops ?? (dto.region_a.accepts_writes ? 4500 : 0),
      fencingEpoch: dto.region_a.fencing_epoch ?? 101,
      isFenced: Boolean(dto.region_a.is_fenced),
    } : this.state.regionA;

    const regB = dto.region_b ? {
      id: 'region-b' as const,
      name: dto.region_b.name || 'Singapore',
      cloudZone: dto.region_b.cloud_zone || 'ap-southeast-1',
      role: dto.region_b.role as 'ACTIVE' | 'STANDBY',
      health: dto.region_b.health as 'HEALTHY' | 'DEGRADED' | 'DOWN',
      status: (dto.region_b.health === 'HEALTHY' ? (dto.region_b.is_fenced ? 'fenced' : 'healthy') : 'failed') as any,
      acceptsWrites: Boolean(dto.region_b.accepts_writes),
      ingressTrafficPercent: dto.region_b.ingress_traffic_percent ?? (dto.region_b.role === 'ACTIVE' ? 100 : 0),
      ingressRps: dto.region_b.ingress_rps ?? (dto.region_b.role === 'ACTIVE' ? 2450 : 0),
      appServersHealthy: dto.region_b.app_servers_healthy ?? 8,
      appServersTotal: dto.region_b.app_servers_total ?? 8,
      activeConnections: dto.region_b.active_connections ?? 120,
      iops: dto.region_b.iops ?? (dto.region_b.accepts_writes ? 4800 : 120),
      fencingEpoch: dto.region_b.fencing_epoch ?? 101,
      isFenced: Boolean(dto.region_b.is_fenced),
    } : this.state.regionB;

    const rep = dto.replication ? {
      status: dto.replication.status,
      lagSeconds: dto.replication.lag_seconds ?? 0.8,
      lagMs: dto.replication.lag_ms ?? Math.round((dto.replication.lag_seconds ?? 0.8) * 1000),
      bandwidthMbps: dto.replication.bandwidth_mbps ?? 450,
      packetLossPercent: dto.replication.packet_loss_percent ?? 0,
      pendingBytes: dto.replication.pending_bytes ?? 12400,
      bytesTransferred: dto.replication.bytes_transferred ?? 45000000,
      mode: 'ASYNCHRONOUS_WAL' as const,
    } : this.state.replication;

    const rt = dto.route ? {
      activeTarget: dto.route.active_target as 'region-a' | 'region-b',
      dnsTtlSeconds: dto.route.dns_ttl_seconds ?? 2,
      propagationPercent: dto.route.propagation_percent ?? 100,
      verificationStatus: dto.route.verification_status,
    } : this.state.route;

    const voters = dto.voters ? dto.voters.map((v) => ({
      id: v.id,
      name: v.name,
      location: v.location,
      vote: v.vote,
      latencyMs: v.latency_ms,
    })) : this.state.voters;

    const cfg = dto.policy ? {
      healthCheckIntervalSec: dto.policy.health_check_interval_sec ?? this.state.config.healthCheckIntervalSec,
      failureThresholdConsecutive: dto.policy.failure_threshold_consecutive ?? this.state.config.failureThresholdConsecutive,
      quorumSize: dto.policy.quorum_size ?? this.state.config.quorumSize,
      majorityRequired: dto.policy.majority_required ?? this.state.config.majorityRequired,
      acceptableReplicationLagSec: dto.policy.acceptable_replication_lag_sec ?? this.state.config.acceptableReplicationLagSec,
      fencingDurationSec: dto.policy.fencing_duration_sec ?? this.state.config.fencingDurationSec,
      routePropagationSec: dto.policy.route_propagation_sec ?? this.state.config.routePropagationSec,
      routeVerificationSec: dto.policy.route_verification_sec ?? this.state.config.routeVerificationSec,
      autoFailoverEnabled: dto.policy.auto_failover_enabled ?? this.state.config.autoFailoverEnabled,
    } : this.state.config;

    this.state = {
      ...this.state,
      controllerState: dto.controller_state as any ?? this.state.controllerState,
      simulatedTimeSeconds: dto.simulated_time_seconds ?? this.state.simulatedTimeSeconds,
      consecutiveFailures: dto.consecutive_failures ?? this.state.consecutiveFailures,
      blockedReason: dto.blocked_reason ?? null,
      blockedAtState: dto.blocked_at_state as any ?? null,
      isSequenceInProgress: Boolean(dto.is_sequence_in_progress),
      routeRetryCount: dto.route_retry_count ?? 0,
      persistedIntent: dto.persisted_intent ?? null,
      isPausedInterrupted: Boolean(dto.is_paused_interrupted),
      regionA: regA,
      regionB: regB,
      replication: rep,
      route: rt,
      voters,
      config: cfg,
    };
    this.notify();
  }

  public getState(): SimulationState {
    return this.state;
  }

  public getIsRunning(): boolean {
    return this.isRunning;
  }

  public getTickSpeed(): number {
    return this.tickSpeed;
  }

  public subscribe(listener: (state: SimulationState) => void): () => void {
    this.listeners.add(listener);
    listener(this.state);
    return () => {
      this.listeners.delete(listener);
    };
  }

  private notify() {
    const currentState = { ...this.state };
    this.listeners.forEach((listener) => listener(currentState));
  }

  public dispatch(action: SimulationAction) {
    const currentEpoch = this.state.resetEpoch;
    const nextState = simulationReducer(this.state, action);

    // Stale async discard check: If reset occurred, don't apply older mutations
    if (action.type !== 'RESET_SIMULATION' && nextState.resetEpoch !== currentEpoch) {
      return;
    }

    this.state = nextState;
    this.notify();
  }

  // --- Clock & Timer Management ---

  public start() {
    if (this.isRunning && this.intervalId !== null) return;
    this.isRunning = true;
    this.setupTimer();
    this.notify();
  }

  public pause() {
    this.isRunning = false;
    if (this.intervalId !== null) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }
    this.notify();
  }

  public togglePlay() {
    if (this.isRunning) {
      this.pause();
    } else {
      this.start();
    }
  }

  public setTickSpeed(speed: number) {
    this.tickSpeed = speed;
    if (this.isRunning) {
      this.setupTimer();
    }
    this.notify();
  }

  private setupTimer() {
    if (this.intervalId !== null) {
      clearInterval(this.intervalId);
    }
    const intervalMs = Math.max(150, 1000 / this.tickSpeed);
    this.intervalId = setInterval(() => {
      if (this.isRunning) {
        this.dispatch({ type: 'TICK' });
      }
    }, intervalMs);
  }

  public scheduleTimeout(fn: () => void, delayMs: number): ReturnType<typeof setTimeout> {
    const id = setTimeout(() => {
      this.activeTimeouts.delete(id);
      fn();
    }, delayMs);
    this.activeTimeouts.add(id);
    return id;
  }

  public clearAllTimeouts() {
    this.activeTimeouts.forEach((id) => clearTimeout(id));
    this.activeTimeouts.clear();
  }

  public destroy() {
    this.pause();
    this.clearAllTimeouts();
    this.listeners.clear();
  }

  // --- Primary Controls & Explicit Actions ---

  public tick(deltaSec?: number) {
    this.dispatch({ type: 'TICK', deltaSec });
  }

  public reset() {
    this.clearAllTimeouts();
    if (this.isBackendConnected) {
      controllerClient.resetSystem().catch((e) => console.warn('Backend reset failed', e));
    }
    this.dispatch({ type: 'RESET_SIMULATION' });
  }

  public injectPrimaryOutage() {
    if (this.isBackendConnected) {
      controllerClient.injectPrimaryOutage().then((st) => {
        if (st) this.applyBackendState(st);
      }).catch((e) => console.warn('Backend outage failed', e));
    }
    this.dispatch({ type: 'INJECT_PRIMARY_OUTAGE' });
  }

  public recoverPrimary() {
    if (this.isBackendConnected) {
      controllerClient.recoverPrimary().then((st) => {
        if (st) this.applyBackendState(st);
      }).catch((e) => console.warn('Backend recover failed', e));
    }
    this.dispatch({ type: 'RECOVER_PRIMARY' });
  }

  public triggerManualFailover() {
    if (this.isBackendConnected) {
      controllerClient.triggerFailover({ target_region: 'region-b', reason: 'Manual failover triggered from UI' })
        .then(() => controllerClient.fetchState())
        .then((st) => {
          if (st) this.applyBackendState(st);
        })
        .catch((e) => console.warn('Backend failover failed', e));
    }
    this.dispatch({ type: 'TRIGGER_MANUAL_FAILOVER' });
  }

  public stepFailover() {
    this.dispatch({ type: 'STEP_FAILOVER' });
  }

  public retryRoutingUpdate() {
    this.dispatch({ type: 'RETRY_ROUTING_UPDATE' });
  }

  public controllerInterrupt() {
    this.pause();
    this.dispatch({ type: 'CONTROLLER_INTERRUPT' });
  }

  public resumeControllerReconcile() {
    this.dispatch({ type: 'RESUME_CONTROLLER_RECONCILE' });
    this.start();
  }

  public triggerManualFailback() {
    if (this.isBackendConnected) {
      controllerClient.triggerFailback({ target_region: 'region-a', reason: 'Guarded failback approved from UI' })
        .then(() => controllerClient.fetchState())
        .then((st) => {
          if (st) this.applyBackendState(st);
        })
        .catch((e) => console.warn('Backend failback failed', e));
    }
    this.dispatch({ type: 'TRIGGER_MANUAL_FAILBACK' });
  }

  public reconcileReplication() {
    this.dispatch({ type: 'RECONCILE_REPLICATION' });
  }

  public dismissBlockedState() {
    this.dispatch({ type: 'DISMISS_BLOCKED_STATE' });
  }

  public updateConfig(config: Partial<SimulationConfig>) {
    if (this.isBackendConnected) {
      const policyPayload: Partial<PolicyDto> = {};
      if (config.healthCheckIntervalSec !== undefined) policyPayload.health_check_interval_sec = config.healthCheckIntervalSec;
      if (config.failureThresholdConsecutive !== undefined) policyPayload.failure_threshold_consecutive = config.failureThresholdConsecutive;
      if (config.quorumSize !== undefined) policyPayload.quorum_size = config.quorumSize;
      if (config.majorityRequired !== undefined) policyPayload.majority_required = config.majorityRequired;
      if (config.acceptableReplicationLagSec !== undefined) policyPayload.acceptable_replication_lag_sec = config.acceptableReplicationLagSec;
      if (config.fencingDurationSec !== undefined) policyPayload.fencing_duration_sec = config.fencingDurationSec;
      if (config.routePropagationSec !== undefined) policyPayload.route_propagation_sec = config.routePropagationSec;
      if (config.routeVerificationSec !== undefined) policyPayload.route_verification_sec = config.routeVerificationSec;
      if (config.autoFailoverEnabled !== undefined) policyPayload.auto_failover_enabled = config.autoFailoverEnabled;

      controllerClient.updatePolicy(policyPayload).catch((e) => console.warn('Backend policy update failed', e));
    }
    this.dispatch({ type: 'UPDATE_CONFIG', config });
  }

  public restoreConfigDefaults() {
    this.dispatch({ type: 'RESTORE_CONFIG_DEFAULTS' });
  }

  public selectComponent(component: SimulationState['selectedComponent']) {
    this.dispatch({ type: 'SELECT_COMPONENT', component });
  }

  public setVoterVote(voterId: string, vote: 'PRIMARY_OUTAGE' | 'PRIMARY_HEALTHY' | 'ABSTAIN') {
    this.dispatch({ type: 'SET_VOTER_VOTE', voterId, vote });
  }

  // --- Scenario Injections & Compatibility Aliases ---

  public injectNetworkPartition() {
    if (this.isBackendConnected) {
      controllerClient.injectPartition()
        .then((st) => { if (st) this.applyBackendState(st); })
        .catch((e) => console.warn('Backend partition failed', e));
    }
    this.dispatch({ type: 'INJECT_NETWORK_PARTITION' });
  }

  public restoreNetworkPartition() {
    this.dispatch({ type: 'RESTORE_NETWORK_PARTITION' });
  }

  public injectHighReplicationLag(lagSeconds: number = 8.5) {
    if (this.isBackendConnected) {
      controllerClient.injectReplicationLag(lagSeconds)
        .then((st) => { if (st) this.applyBackendState(st); })
        .catch((e) => console.warn('Backend lag injection failed', e));
    }
    this.dispatch({ type: 'INJECT_HIGH_REPLICATION_LAG' });
  }

  public restoreReplicationLag() {
    this.dispatch({ type: 'RESTORE_REPLICATION_LAG' });
  }

  public injectStandbyUnready() {
    this.dispatch({ type: 'INJECT_STANDBY_UNREADY' });
  }

  public restoreStandbyReadiness() {
    this.dispatch({ type: 'RESTORE_STANDBY_READINESS' });
  }

  public injectRouteFailure() {
    this.dispatch({ type: 'INJECT_ROUTE_FAILURE' });
  }

  public restoreRouteHealth() {
    this.dispatch({ type: 'RESTORE_ROUTE_HEALTH' });
  }

  public triggerPrimaryDbCrash() {
    this.injectPrimaryOutage();
  }

  public triggerFlapping() {
    this.injectPrimaryOutage();
    this.scheduleTimeout(() => {
      this.recoverPrimary();
    }, 1500);
  }

  public triggerGracefulSwitchover() {
    this.triggerManualFailover();
  }

  public restoreBaseline() {
    this.reset();
  }
}

export const simulationEngine = new SimulationEngine();
