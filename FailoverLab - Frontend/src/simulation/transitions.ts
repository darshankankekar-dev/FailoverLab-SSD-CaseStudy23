// FailoverLab: Pure Simulation Reducer & State Transitions
// System Design & SSD Case Study 23

import type {
  SimulationState,
  SimulationAction,
  SimulationConfig,
  AuditRecord,
  EventSeverity,
  EventSubsystem,
} from './types';
import {
  evaluateQuorumMajority,
  checkStandbyReadiness,
  checkReplicationLagPolicy,
  verifyFencingConfirmed,
  verifyNoDualPrimary,
  verifyRouteOperational,
  checkFailbackReadiness,
} from './safetyGates';

/**
 * SIMULATION CONFIGURATION
 * Prototype defaults for virtual lab; not production recommendations.
 */
export const INITIAL_SIMULATION_CONFIG: SimulationConfig = {
  healthCheckIntervalSec: 2, // 2 simulated seconds per probe
  failureThresholdConsecutive: 3, // 3 consecutive failures to trigger quorum
  quorumSize: 3, // 3 simulated independent voters
  majorityRequired: 2, // 2 of 3 votes
  acceptableReplicationLagSec: 5, // 5 simulated seconds acceptable lag
  fencingDurationSec: 2, // Simulated fencing delay
  routePropagationSec: 2, // Simulated DNS propagation duration
  routeVerificationSec: 2, // Simulated route verification delay
  autoFailoverEnabled: true,
};

export const INITIAL_SIMULATION_STATE: SimulationState = {
  controllerState: 'HEALTHY',
  simulatedTimeSeconds: 0,
  tickStepSec: 1,
  wallClockStartTime: Date.now(),

  regionA: {
    id: 'region-a',
    name: 'Mumbai',
    cloudZone: 'ap-south-1',
    role: 'ACTIVE',
    health: 'HEALTHY',
    status: 'healthy',
    acceptsWrites: true,
    ingressTrafficPercent: 100,
    ingressRps: 2450,
    appServersHealthy: 12,
    appServersTotal: 12,
    activeConnections: 2450,
    iops: 4800,
    fencingEpoch: 101,
    isFenced: false,
  },

  regionB: {
    id: 'region-b',
    name: 'Singapore',
    cloudZone: 'ap-southeast-1',
    role: 'STANDBY',
    health: 'HEALTHY',
    status: 'healthy',
    acceptsWrites: false, // Does not independently accept writes in standby
    ingressTrafficPercent: 0,
    ingressRps: 0,
    appServersHealthy: 12,
    appServersTotal: 12,
    activeConnections: 0,
    iops: 120,
    fencingEpoch: 101,
    isFenced: false,
  },

  config: { ...INITIAL_SIMULATION_CONFIG },

  replication: {
    status: 'STREAMING',
    lagSeconds: 0.8, // 800ms nominal cross-ocean WAL replication
    lagMs: 800,
    bandwidthMbps: 450,
    packetLossPercent: 0,
    pendingBytes: 12400,
    bytesTransferred: 45000000,
    mode: 'ASYNCHRONOUS_WAL',
  },

  route: {
    activeTarget: 'region-a',
    dnsTtlSeconds: 2,
    propagationPercent: 100,
    verificationStatus: 'VERIFIED',
  },

  voters: [
    {
      id: 'voter-1',
      name: 'Observer 1',
      location: 'ap-south-1 (Mumbai Local)',
      vote: 'PRIMARY_HEALTHY',
      latencyMs: 5,
    },
    {
      id: 'voter-2',
      name: 'Observer 2',
      location: 'ap-southeast-1 (Singapore Local)',
      vote: 'PRIMARY_HEALTHY',
      latencyMs: 32,
    },
    {
      id: 'voter-3',
      name: 'Observer 3 (Neutral Tie-Breaker)',
      location: 'eu-central-1 (Zurich Independent)',
      vote: 'PRIMARY_HEALTHY',
      latencyMs: 78,
    },
  ],

  consecutiveFailures: 0,
  lastHealthCheckSimTime: 0,

  outageInjected: false,
  partitionInjected: false,
  replicationThrottled: false,
  standbyReadinessBroken: false,
  routeFailureInjected: false,

  blockedReason: null,
  blockedAtState: null,

  resetEpoch: 1,
  isSequenceInProgress: false,
  routeRetryCount: 0,
  persistedIntent: null,
  isPausedInterrupted: false,

  eventHistory: [
    {
      id: 'init-1',
      simulatedTimeSeconds: 0,
      wallClockTimestamp: new Date().toISOString(),
      severity: 'info',
      subsystem: 'CONTROLLER',
      transition: 'INITIALIZED -> HEALTHY',
      reason:
        'FailoverLab controller initialized in nominal state. Region A (Mumbai) ACTIVE [Epoch 101], Region B (Singapore) STANDBY replica. Heartbeat probes normal.',
    },
  ],
  selectedComponent: 'CONTROLLER',
};

function appendEvent(
  state: SimulationState,
  severity: EventSeverity,
  subsystem: EventSubsystem,
  reason: string,
  transition?: string,
  details?: string
): AuditRecord[] {
  const record: AuditRecord = {
    id: `ev-${Date.now()}-${Math.floor(Math.random() * 10000)}`,
    simulatedTimeSeconds: state.simulatedTimeSeconds,
    wallClockTimestamp: new Date().toLocaleTimeString(),
    severity,
    subsystem,
    transition,
    reason,
    details,
  };
  return [record, ...state.eventHistory].slice(0, 100);
}

/**
 * Pure state reducer implementing all safety gates and deterministic transitions.
 */
export function simulationReducer(
  state: SimulationState,
  action: SimulationAction
): SimulationState {
  switch (action.type) {
    case 'TICK': {
      const deltaSec = action.deltaSec ?? state.tickStepSec;
      const nextSimTime = state.simulatedTimeSeconds + deltaSec;

      let newState: SimulationState = {
        ...state,
        simulatedTimeSeconds: nextSimTime,
      };

      const prevState = newState.controllerState;

      // Periodic Health Check evaluation (every healthCheckIntervalSec)
      const timeSinceLastProbe = nextSimTime - newState.lastHealthCheckSimTime;
      const shouldRunHealthCheck =
        timeSinceLastProbe >= newState.config.healthCheckIntervalSec;

      if (shouldRunHealthCheck) {
        newState.lastHealthCheckSimTime = nextSimTime;
        newState = evaluateHealthProbes(newState);
      }

      // If health probe evaluation caused a state change (e.g. entering QUORUM_CHECK),
      // let the state settle for this tick so voters and probes can be observed.
      if (newState.controllerState === prevState) {
        newState = stepStateMachine(newState);
      }

      return newState;
    }

    case 'INJECT_PRIMARY_OUTAGE': {
      let events = appendEvent(
        state,
        'critical',
        'CHAOS',
        'Primary Outage Injected: PostgreSQL/Aurora storage daemon collapsed in Mumbai (ap-south-1).'
      );
      return {
        ...state,
        outageInjected: true,
        regionA: {
          ...state.regionA,
          health: 'DOWN',
          iops: 0,
        },
        eventHistory: events,
      };
    }

    case 'RECOVER_PRIMARY': {
      let events = appendEvent(
        state,
        'info',
        'CHAOS',
        'Primary Storage Restored: Mumbai instance rebooted and passed hardware self-test.'
      );
      const isSecondaryActive = state.controllerState === 'SECONDARY_ACTIVE';
      return {
        ...state,
        outageInjected: false,
        regionA: {
          ...state.regionA,
          health: 'HEALTHY',
          // If secondary is already active, keep Region A in standby!
          role: isSecondaryActive ? 'STANDBY' : state.regionA.role,
          acceptsWrites: isSecondaryActive ? false : state.regionA.acceptsWrites,
          ingressTrafficPercent: isSecondaryActive ? 0 : state.regionA.ingressTrafficPercent,
          iops: isSecondaryActive ? 0 : 4800,
        },
        eventHistory: events,
      };
    }

    case 'INJECT_NETWORK_PARTITION': {
      let events = appendEvent(
        state,
        'critical',
        'NETWORK',
        'Cross-Region WAN Partition Injected: Inter-region fiber connection severed. Replication pipeline interrupted.'
      );
      return {
        ...state,
        partitionInjected: true,
        replication: {
          ...state.replication,
          status: 'SEVERED',
        },
        voters: state.voters.map((v) =>
          v.id === 'voter-1'
            ? { ...v, vote: 'PRIMARY_HEALTHY' }
            : { ...v, vote: 'PRIMARY_OUTAGE' }
        ),
        eventHistory: events,
      };
    }

    case 'RESTORE_NETWORK_PARTITION': {
      let events = appendEvent(
        state,
        'success',
        'NETWORK',
        'Cross-Region WAN Partition Restored: Inter-region fiber connection reconnected.'
      );
      return {
        ...state,
        partitionInjected: false,
        replication: {
          ...state.replication,
          status: 'STREAMING',
          lagSeconds: 0.8,
        },
        eventHistory: events,
      };
    }

    case 'INJECT_HIGH_REPLICATION_LAG': {
      let events = appendEvent(
        state,
        'warn',
        'DATABASE',
        `Replication Throttling Injected: Replication lag spiked to 8.4s (exceeds policy limit of ${state.config.acceptableReplicationLagSec}s).`
      );
      return {
        ...state,
        replicationThrottled: true,
        replication: {
          ...state.replication,
          status: 'DEGRADED',
          lagSeconds: 8.4,
        },
        eventHistory: events,
      };
    }

    case 'RESTORE_REPLICATION_LAG': {
      let events = appendEvent(
        state,
        'success',
        'DATABASE',
        'Replication Throttling Cleared: Replication lag returned to nominal 0.8s.'
      );
      return {
        ...state,
        replicationThrottled: false,
        replication: {
          ...state.replication,
          status: 'STREAMING',
          lagSeconds: 0.8,
        },
        eventHistory: events,
      };
    }

    case 'INJECT_STANDBY_UNREADY': {
      let events = appendEvent(
        state,
        'critical',
        'CHAOS',
        'Standby Readiness Broken: Region B (Singapore) simulated storage volume corrupted.'
      );
      return {
        ...state,
        standbyReadinessBroken: true,
        regionB: {
          ...state.regionB,
          health: 'DOWN',
        },
        eventHistory: events,
      };
    }

    case 'RESTORE_STANDBY_READINESS': {
      let events = appendEvent(
        state,
        'success',
        'CHAOS',
        'Standby Readiness Restored: Region B (Singapore) storage replica restored to HEALTHY.'
      );
      return {
        ...state,
        standbyReadinessBroken: false,
        regionB: {
          ...state.regionB,
          health: 'HEALTHY',
        },
        eventHistory: events,
      };
    }

    case 'INJECT_ROUTE_FAILURE': {
      let events = appendEvent(
        state,
        'critical',
        'DNS',
        'Route Verification Failure Injected: Anycast BGP routing table drop induced.'
      );
      return {
        ...state,
        routeFailureInjected: true,
        route: {
          ...state.route,
          verificationStatus: 'FAILED',
        },
        eventHistory: events,
      };
    }

    case 'RESTORE_ROUTE_HEALTH': {
      let events = appendEvent(
        state,
        'success',
        'DNS',
        'Route Health Restored: DNS / BGP routing tables converged.'
      );
      return {
        ...state,
        routeFailureInjected: false,
        route: {
          ...state.route,
          verificationStatus: 'VERIFIED',
        },
        eventHistory: events,
      };
    }

    case 'RECONCILE_REPLICATION': {
      if (state.controllerState !== 'PRIMARY_RECOVERING') {
        return state;
      }
      let events = appendEvent(
        state,
        'success',
        'DATABASE',
        'Reverse Replication Reconciled: Singapore -> Mumbai WAL sync caught up to 0.5s lag. Pre-failback check passed.',
        'PRIMARY_RECOVERING -> FAILBACK_PENDING'
      );
      return {
        ...state,
        controllerState: 'FAILBACK_PENDING',
        replication: {
          ...state.replication,
          status: 'SYNCED',
          lagSeconds: 0.5,
        },
        eventHistory: events,
      };
    }

    case 'TRIGGER_MANUAL_FAILBACK': {
      // Re-entrancy check: Prevent duplicate triggers
      if (
        state.isSequenceInProgress ||
        state.controllerState !== 'FAILBACK_PENDING'
      ) {
        return state;
      }

      const failbackCheck = checkFailbackReadiness(state);
      if (!failbackCheck.passed) {
        let events = appendEvent(
          state,
          'warn',
          'SAFETY_GATE',
          failbackCheck.reason,
          `${state.controllerState} -> FAILOVER_BLOCKED`
        );
        return {
          ...state,
          controllerState: 'FAILOVER_BLOCKED',
          blockedReason: failbackCheck.reason,
          blockedAtState: 'FAILBACK_PENDING',
          eventHistory: events,
        };
      }

      let events = appendEvent(
        state,
        'action',
        'CONTROLLER',
        'Deliberate Manual Failback Authorized: Initiating controlled role reversal back to Region A (Mumbai).',
        'FAILBACK_PENDING -> FAILBACK_IN_PROGRESS'
      );

      return {
        ...state,
        controllerState: 'FAILBACK_IN_PROGRESS',
        isSequenceInProgress: true,
        eventHistory: events,
      };
    }

    case 'DISMISS_BLOCKED_STATE': {
      if (state.controllerState !== 'FAILOVER_BLOCKED') {
        return state;
      }
      let events = appendEvent(
        state,
        'info',
        'CONTROLLER',
        'Operator dismissed blocked state. Restoring controller evaluation.'
      );
      return {
        ...state,
        controllerState: 'HEALTHY',
        blockedReason: null,
        blockedAtState: null,
        isSequenceInProgress: false,
        consecutiveFailures: 0,
        eventHistory: events,
      };
    }

    case 'UPDATE_CONFIG': {
      let events = appendEvent(
        state,
        'info',
        'CONTROLLER',
        `Simulation configuration updated: ${Object.keys(action.config).join(', ')} (Prototype defaults)`
      );
      return {
        ...state,
        config: { ...state.config, ...action.config },
        eventHistory: events,
      };
    }

    case 'TRIGGER_MANUAL_FAILOVER': {
      if (state.regionB.role === 'ACTIVE' || state.isSequenceInProgress) {
        return state;
      }
      const events = appendEvent(
        state,
        'action',
        'CONTROLLER',
        'Manual Failover Triggered: Operator invoked emergency failover drill. Bypassing debounce threshold and advancing directly to Quorum Consensus.',
        `${state.controllerState} -> QUORUM_CHECK`
      );
      const voters = state.voters.map((v) => ({ ...v, vote: 'PRIMARY_OUTAGE' as const }));
      return {
        ...state,
        controllerState: 'QUORUM_CHECK',
        consecutiveFailures: state.config.failureThresholdConsecutive,
        voters,
        isSequenceInProgress: true,
        outageInjected: true,
        regionA: {
          ...state.regionA,
          health: 'DOWN',
        },
        eventHistory: events,
      };
    }

    case 'STEP_FAILOVER': {
      if (state.controllerState === 'HEALTHY') {
        const events = appendEvent(
          state,
          'warn',
          'CONTROLLER',
          'Stepped: Synthetic health check failed (1/3). Transitioning to PRIMARY_SUSPECTED.',
          'HEALTHY -> PRIMARY_SUSPECTED'
        );
        return {
          ...state,
          controllerState: 'PRIMARY_SUSPECTED',
          consecutiveFailures: 1,
          eventHistory: events,
        };
      }
      if (state.controllerState === 'PRIMARY_SUSPECTED') {
        const events = appendEvent(
          state,
          'critical',
          'QUORUM',
          'Stepped: Failure threshold reached (3/3). Proceeding to Quorum Consensus.',
          'PRIMARY_SUSPECTED -> QUORUM_CHECK'
        );
        const voters = state.voters.map((v) => ({ ...v, vote: 'PRIMARY_OUTAGE' as const }));
        return {
          ...state,
          controllerState: 'QUORUM_CHECK',
          consecutiveFailures: state.config.failureThresholdConsecutive,
          voters,
          isSequenceInProgress: true,
          eventHistory: events,
        };
      }
      return stepStateMachine(state);
    }

    case 'RETRY_ROUTING_UPDATE': {
      const nextRetry = state.routeRetryCount + 1;
      if (state.routeFailureInjected && nextRetry <= 3) {
        const events = appendEvent(
          state,
          'warn',
          'DNS',
          `[Routing Retry ${nextRetry}/3] DNS / BGP route propagation re-attempted. Anycast probe timed out. Degraded routing condition persists.`,
          'ROUTE_RETRY'
        );
        return {
          ...state,
          routeRetryCount: nextRetry,
          route: {
            ...state.route,
            verificationStatus: 'FAILED',
          },
          eventHistory: events,
        };
      }

      const events = appendEvent(
        state,
        'success',
        'DNS',
        `Routing Update Retry Succeeded: Route verification probe passed on attempt #${nextRetry}. Full traffic cutover verified.`,
        'RETRY_ROUTING_UPDATE -> SECONDARY_ACTIVE'
      );
      return {
        ...state,
        controllerState: 'SECONDARY_ACTIVE',
        routeRetryCount: 0,
        blockedReason: null,
        blockedAtState: null,
        isSequenceInProgress: false,
        routeFailureInjected: false,
        route: {
          ...state.route,
          verificationStatus: 'VERIFIED',
          propagationPercent: 100,
        },
        eventHistory: events,
      };
    }

    case 'CONTROLLER_INTERRUPT': {
      const events = appendEvent(
        state,
        'critical',
        'CONTROLLER',
        `Controller Interrupted: Orchestrator process halted mid-transition at state ${state.controllerState}. Intent saved to metadata store. Ingress paused.`,
        'CONTROLLER_INTERRUPTED'
      );
      return {
        ...state,
        persistedIntent: state.controllerState,
        isPausedInterrupted: true,
        isSequenceInProgress: false,
        eventHistory: events,
      };
    }

    case 'RESUME_CONTROLLER_RECONCILE': {
      const intent = state.persistedIntent || state.controllerState;
      const events = appendEvent(
        state,
        'success',
        'CONTROLLER',
        `Controller Reconciled: Resumed from persisted state [${intent}]. Validating fencing tokens and storage leases. Zero dual-master status confirmed.`,
        'RECONCILED -> RESUMED'
      );
      const reconciledState: SimulationState = {
        ...state,
        persistedIntent: null,
        isPausedInterrupted: false,
        isSequenceInProgress: true,
        eventHistory: events,
      };
      return stepStateMachine(reconciledState);
    }

    case 'RESTORE_CONFIG_DEFAULTS': {
      const events = appendEvent(
        state,
        'info',
        'CONTROLLER',
        'Configuration Policy Defaults Restored: Interval: 2s, Threshold: 3 probes, Quorum: 2/3 votes, Max Lag: 5s.'
      );
      return {
        ...state,
        config: { ...INITIAL_SIMULATION_CONFIG },
        eventHistory: events,
      };
    }

    case 'SET_VOTER_VOTE': {
      const voters = state.voters.map((v) =>
        v.id === action.voterId ? { ...v, vote: action.vote } : v
      );
      return {
        ...state,
        voters,
      };
    }

    case 'SELECT_COMPONENT': {
      return {
        ...state,
        selectedComponent: action.component,
      };
    }

    case 'RESET_SIMULATION': {
      const resetEpoch = state.resetEpoch + 1;
      let events = appendEvent(
        INITIAL_SIMULATION_STATE,
        'info',
        'CONTROLLER',
        'Virtual Lab Reset: Baseline configuration, regions, routing, counters, and epochs restored. All pending sequences cancelled.'
      );
      return {
        ...INITIAL_SIMULATION_STATE,
        resetEpoch,
        simulatedTimeSeconds: 0,
        wallClockStartTime: Date.now(),
        eventHistory: events,
      };
    }

    default:
      return state;
  }
}

/**
 * Health Probing logic evaluated on simulated time intervals.
 * Implements: False-positive recovery, consecutive failure threshold, and Quorum trigger.
 */
function evaluateHealthProbes(state: SimulationState): SimulationState {
  const isPrimaryFailing =
    state.outageInjected || state.regionA.health !== 'HEALTHY';

  // Case 1: Primary is healthy
  if (!isPrimaryFailing) {
    // FALSE POSITIVE RECOVERY:
    // If primary recovered before reaching threshold, restore HEALTHY and reset failures.
    if (state.controllerState === 'PRIMARY_SUSPECTED') {
      const events = appendEvent(
        state,
        'success',
        'SAFETY_GATE',
        `False Positive Suppressed: Primary (Mumbai) probe succeeded before failure threshold (${state.consecutiveFailures}/${state.config.failureThresholdConsecutive}). Controller restored to HEALTHY without initiating failover.`,
        'PRIMARY_SUSPECTED -> HEALTHY'
      );
      return {
        ...state,
        controllerState: 'HEALTHY',
        consecutiveFailures: 0,
        voters: state.voters.map((v) => ({ ...v, vote: 'PRIMARY_HEALTHY' })),
        eventHistory: events,
      };
    }

    // Normal healthy ticking
    return {
      ...state,
      consecutiveFailures: 0,
      voters: state.voters.map((v) => ({ ...v, vote: 'PRIMARY_HEALTHY' })),
    };
  }

  // Case 2: Primary is failing (Outage detected)
  // Only evaluate if in nominal HEALTHY or PRIMARY_SUSPECTED
  if (
    state.controllerState === 'HEALTHY' ||
    state.controllerState === 'PRIMARY_SUSPECTED'
  ) {
    const nextFailures = state.consecutiveFailures + 1;

    // Below threshold: Mark PRIMARY_SUSPECTED
    if (nextFailures < state.config.failureThresholdConsecutive) {
      const events = appendEvent(
        state,
        'warn',
        'CONTROLLER',
        `Synthetic health probe failed (${nextFailures}/${state.config.failureThresholdConsecutive}). Region A suspected. Holding in debounce window to filter transient jitter.`,
        state.controllerState === 'HEALTHY' ? 'HEALTHY -> PRIMARY_SUSPECTED' : undefined
      );
      return {
        ...state,
        controllerState: 'PRIMARY_SUSPECTED',
        consecutiveFailures: nextFailures,
        eventHistory: events,
      };
    }

    // Threshold reached: Advance to QUORUM_CHECK
    // Set voter votes based on partition state
    const nextVoters = state.voters.map((v) => {
      if (state.partitionInjected && v.id === 'voter-1') {
        return { ...v, vote: 'PRIMARY_HEALTHY' as const }; // Isolated in Mumbai
      }
      return { ...v, vote: 'PRIMARY_OUTAGE' as const };
    });

    const events = appendEvent(
      state,
      'critical',
      'QUORUM',
      `Consecutive failure threshold reached (${nextFailures}/${state.config.failureThresholdConsecutive}). Gathering independent health monitor votes from 3 observers.`,
      'PRIMARY_SUSPECTED -> QUORUM_CHECK'
    );

    return {
      ...state,
      controllerState: 'QUORUM_CHECK',
      consecutiveFailures: nextFailures,
      voters: nextVoters,
      isSequenceInProgress: true,
      eventHistory: events,
    };
  }

  return state;
}

/**
 * State machine stepper enforcing all mandatory safety gates.
 */
function stepStateMachine(state: SimulationState): SimulationState {
  switch (state.controllerState) {
    // ----------------------------------------------------
    // STEP 1: QUORUM_CHECK -> FENCING_PRIMARY
    // ----------------------------------------------------
    case 'QUORUM_CHECK': {
      // Safety Gate 1: Quorum Majority
      const quorumResult = evaluateQuorumMajority(
        state.voters,
        state.config.majorityRequired
      );

      if (!quorumResult.passed) {
        const events = appendEvent(
          state,
          'critical',
          'SAFETY_GATE',
          quorumResult.reason,
          'QUORUM_CHECK -> FAILOVER_BLOCKED'
        );
        return {
          ...state,
          controllerState: 'FAILOVER_BLOCKED',
          blockedReason: quorumResult.reason,
          blockedAtState: 'QUORUM_CHECK',
          isSequenceInProgress: false,
          eventHistory: events,
        };
      }

      // Safety Gate 2: Standby Readiness
      const standbyResult = checkStandbyReadiness(state.regionB);
      if (!standbyResult.passed) {
        const events = appendEvent(
          state,
          'critical',
          'SAFETY_GATE',
          standbyResult.reason,
          'QUORUM_CHECK -> FAILOVER_BLOCKED'
        );
        return {
          ...state,
          controllerState: 'FAILOVER_BLOCKED',
          blockedReason: standbyResult.reason,
          blockedAtState: 'QUORUM_CHECK',
          isSequenceInProgress: false,
          eventHistory: events,
        };
      }

      // Safety Gate 3: Replication Lag Gate
      const lagResult = checkReplicationLagPolicy(
        state.replication,
        state.config.acceptableReplicationLagSec
      );
      if (!lagResult.passed) {
        const events = appendEvent(
          state,
          'critical',
          'SAFETY_GATE',
          lagResult.reason,
          'QUORUM_CHECK -> FAILOVER_BLOCKED'
        );
        return {
          ...state,
          controllerState: 'FAILOVER_BLOCKED',
          blockedReason: lagResult.reason,
          blockedAtState: 'QUORUM_CHECK',
          isSequenceInProgress: false,
          eventHistory: events,
        };
      }

      // All safety gates passed! Advance to FENCING_PRIMARY
      const events = appendEvent(
        state,
        'action',
        'FENCING',
        `All quorum and readiness safety gates passed (${quorumResult.outageVotesCount}/3 votes). Revoking Region A write authority and advancing fencing epoch.`,
        'QUORUM_CHECK -> FENCING_PRIMARY'
      );

      return {
        ...state,
        controllerState: 'FENCING_PRIMARY',
        eventHistory: events,
      };
    }

    // ----------------------------------------------------
    // STEP 2: FENCING_PRIMARY -> PROMOTING_STANDBY
    // ----------------------------------------------------
    case 'FENCING_PRIMARY': {
      const nextEpoch = state.regionA.fencingEpoch + 1;

      // Revoke write authorization on Region A & apply hard fence
      const fencedRegionA = {
        ...state.regionA,
        acceptsWrites: false,
        isFenced: true,
      };

      // Safety Gate 4: Verify Fencing Confirmed
      const fencingResult = verifyFencingConfirmed(fencedRegionA);
      if (!fencingResult.passed) {
        const events = appendEvent(
          state,
          'critical',
          'SAFETY_GATE',
          fencingResult.reason,
          'FENCING_PRIMARY -> FAILOVER_BLOCKED'
        );
        return {
          ...state,
          controllerState: 'FAILOVER_BLOCKED',
          blockedReason: fencingResult.reason,
          blockedAtState: 'FENCING_PRIMARY',
          isSequenceInProgress: false,
          eventHistory: events,
        };
      }

      const events = appendEvent(
        state,
        'success',
        'FENCING',
        `Region A (Mumbai) hard-fenced. Write lease revoked. Storage fencing epoch advanced to #${nextEpoch}. Promoting Region B.`,
        'FENCING_PRIMARY -> PROMOTING_STANDBY'
      );

      return {
        ...state,
        controllerState: 'PROMOTING_STANDBY',
        regionA: fencedRegionA,
        regionB: {
          ...state.regionB,
          fencingEpoch: nextEpoch,
        },
        eventHistory: events,
      };
    }

    // ----------------------------------------------------
    // STEP 3: PROMOTING_STANDBY -> ROUTE_UPDATING
    // ----------------------------------------------------
    case 'PROMOTING_STANDBY': {
      // Promote Region B to ACTIVE and authorize writes
      const promotedRegionB = {
        ...state.regionB,
        role: 'ACTIVE' as const,
        acceptsWrites: true,
        iops: 4800,
      };

      // Safety Gate 5: Verify Dual-Primary Invariant
      const dualPrimaryCheck = verifyNoDualPrimary(
        state.regionA,
        promotedRegionB
      );
      if (!dualPrimaryCheck.passed) {
        const events = appendEvent(
          state,
          'critical',
          'SAFETY_GATE',
          dualPrimaryCheck.reason,
          'PROMOTING_STANDBY -> FAILOVER_BLOCKED'
        );
        return {
          ...state,
          controllerState: 'FAILOVER_BLOCKED',
          blockedReason: dualPrimaryCheck.reason,
          blockedAtState: 'PROMOTING_STANDBY',
          isSequenceInProgress: false,
          eventHistory: events,
        };
      }

      const events = appendEvent(
        state,
        'success',
        'DATABASE',
        `Region B (Singapore) promoted to PRIMARY. Writable master assigned Epoch #${promotedRegionB.fencingEpoch}. Initiating DNS / Anycast route cutover.`,
        'PROMOTING_STANDBY -> ROUTE_UPDATING'
      );

      return {
        ...state,
        controllerState: 'ROUTE_UPDATING',
        regionA: {
          ...state.regionA,
          role: 'STANDBY',
          ingressTrafficPercent: 0,
        },
        regionB: promotedRegionB,
        route: {
          ...state.route,
          activeTarget: 'region-b',
          propagationPercent: 25,
          verificationStatus: 'UNVERIFIED',
        },
        eventHistory: events,
      };
    }

    // ----------------------------------------------------
    // STEP 4: ROUTE_UPDATING -> VERIFYING_ROUTE
    // ----------------------------------------------------
    case 'ROUTE_UPDATING': {
      const nextPropagation = Math.min(
        100,
        state.route.propagationPercent + 50
      );
      const nextTraffic = nextPropagation;

      if (nextPropagation < 100) {
        return {
          ...state,
          route: {
            ...state.route,
            propagationPercent: nextPropagation,
          },
          regionB: {
            ...state.regionB,
            ingressTrafficPercent: nextTraffic,
            activeConnections: Math.round(2450 * (nextTraffic / 100)),
          },
        };
      }

      // DNS reached 100% propagation
      const events = appendEvent(
        state,
        'action',
        'DNS',
        'DNS propagation converged to 100%. Dispatching synthetic test request to verify route connectivity.',
        'ROUTE_UPDATING -> VERIFYING_ROUTE'
      );

      return {
        ...state,
        controllerState: 'VERIFYING_ROUTE',
        route: {
          ...state.route,
          propagationPercent: 100,
          verificationStatus: 'VERIFYING',
        },
        regionB: {
          ...state.regionB,
          ingressTrafficPercent: 100,
          activeConnections: 2450,
        },
        eventHistory: events,
      };
    }

    // ----------------------------------------------------
    // STEP 5: VERIFYING_ROUTE -> SECONDARY_ACTIVE
    // ----------------------------------------------------
    case 'VERIFYING_ROUTE': {
      // Safety Gate 6: Verify Route Operational
      const routeCheck = verifyRouteOperational(
        state.route,
        'region-b',
        state.routeFailureInjected
      );

      if (!routeCheck.passed) {
        const events = appendEvent(
          state,
          'critical',
          'SAFETY_GATE',
          routeCheck.reason,
          'VERIFYING_ROUTE -> FAILOVER_BLOCKED'
        );
        return {
          ...state,
          controllerState: 'FAILOVER_BLOCKED',
          blockedReason: routeCheck.reason,
          blockedAtState: 'VERIFYING_ROUTE',
          isSequenceInProgress: false,
          route: {
            ...state.route,
            verificationStatus: 'FAILED',
          },
          eventHistory: events,
        };
      }

      const events = appendEvent(
        state,
        'success',
        'CONTROLLER',
        'Synthetic test probe verified. Failover successfully completed. Region B (Singapore) is ACTIVE and serving all production traffic.',
        'VERIFYING_ROUTE -> SECONDARY_ACTIVE'
      );

      return {
        ...state,
        controllerState: 'SECONDARY_ACTIVE',
        isSequenceInProgress: false,
        route: {
          ...state.route,
          verificationStatus: 'VERIFIED',
        },
        eventHistory: events,
      };
    }

    // ----------------------------------------------------
    // RECOVERY STEP: SECONDARY_ACTIVE & Primary Restored -> PRIMARY_RECOVERING
    // ----------------------------------------------------
    case 'SECONDARY_ACTIVE': {
      // If primary recovers, transition to PRIMARY_RECOVERING (never auto-switchback!)
      if (!state.outageInjected && state.regionA.health === 'HEALTHY' && state.regionA.isFenced) {
        const events = appendEvent(
          state,
          'info',
          'CONTROLLER',
          'Region A (Mumbai) back online in STANDBY mode. Entering PRIMARY_RECOVERING. Reverse replication reconciliation required.',
          'SECONDARY_ACTIVE -> PRIMARY_RECOVERING'
        );
        return {
          ...state,
          controllerState: 'PRIMARY_RECOVERING',
          replication: {
            ...state.replication,
            status: 'REVERSED',
            lagSeconds: 3.2,
          },
          eventHistory: events,
        };
      }
      return state;
    }

    // ----------------------------------------------------
    // STEP 6: FAILBACK_IN_PROGRESS -> HEALTHY
    // ----------------------------------------------------
    case 'FAILBACK_IN_PROGRESS': {
      const nextEpoch = state.regionB.fencingEpoch + 1;

      // Graceful role reversal back to Region A
      const fencedRegionB = {
        ...state.regionB,
        role: 'STANDBY' as const,
        acceptsWrites: false,
        isFenced: true,
        ingressTrafficPercent: 0,
        activeConnections: 0,
        iops: 120,
      };

      const restoredRegionA = {
        ...state.regionA,
        role: 'ACTIVE' as const,
        health: 'HEALTHY' as const,
        acceptsWrites: true,
        isFenced: false,
        ingressTrafficPercent: 100,
        activeConnections: 2450,
        iops: 4800,
        fencingEpoch: nextEpoch,
      };

      const events = appendEvent(
        state,
        'success',
        'CONTROLLER',
        `Failback complete: Region A (Mumbai) restored to ACTIVE [Epoch #${nextEpoch}]. Region B returned to STANDBY. Normal operation resumed.`,
        'FAILBACK_IN_PROGRESS -> HEALTHY'
      );

      return {
        ...state,
        controllerState: 'HEALTHY',
        isSequenceInProgress: false,
        regionA: restoredRegionA,
        regionB: fencedRegionB,
        route: {
          activeTarget: 'region-a',
          dnsTtlSeconds: 2,
          propagationPercent: 100,
          verificationStatus: 'VERIFIED',
        },
        replication: {
          status: 'STREAMING',
          lagSeconds: 0.8,
          lagMs: 800,
          bandwidthMbps: 450,
          packetLossPercent: 0,
          pendingBytes: 12400,
          bytesTransferred: state.replication.bytesTransferred + 1000000,
          mode: 'ASYNCHRONOUS_WAL',
        },
        eventHistory: events,
      };
    }

    default:
      return state;
  }
}
