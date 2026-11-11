// FailoverLab: Multi-Region Active-Passive Failover Controller
// Academic Context: System Design & SSD Case Study 23

export type RegionId = 'region-a' | 'region-b';

/**
 * Mandatory State Machine States for Case Study 23:
 * HEALTHY -> PRIMARY_SUSPECTED -> QUORUM_CHECK -> FENCING_PRIMARY ->
 * PROMOTING_STANDBY -> ROUTE_UPDATING -> VERIFYING_ROUTE -> SECONDARY_ACTIVE
 *
 * Fault/Blocked: FAILOVER_BLOCKED
 * Recovery: PRIMARY_RECOVERING -> FAILBACK_PENDING -> FAILBACK_IN_PROGRESS -> HEALTHY
 */
export type ControllerState =
  | 'HEALTHY'
  | 'PRIMARY_SUSPECTED'
  | 'QUORUM_CHECK'
  | 'FENCING_PRIMARY'
  | 'PROMOTING_STANDBY'
  | 'ROUTE_UPDATING'
  | 'VERIFYING_ROUTE'
  | 'SECONDARY_ACTIVE'
  | 'FAILOVER_BLOCKED'
  | 'PRIMARY_RECOVERING'
  | 'FAILBACK_PENDING'
  | 'FAILBACK_IN_PROGRESS';

export type HealthStatus = 'HEALTHY' | 'DEGRADED' | 'DOWN';

export type RegionRole = 'ACTIVE' | 'STANDBY';

export type EventSeverity = 'info' | 'warn' | 'critical' | 'success' | 'action';

export type EventSubsystem =
  | 'DNS'
  | 'DATABASE'
  | 'QUORUM'
  | 'FENCING'
  | 'CONTROLLER'
  | 'NETWORK'
  | 'CHAOS'
  | 'SAFETY_GATE';

export interface AuditRecord {
  id: string;
  simulatedTimeSeconds: number;
  wallClockTimestamp: string;
  severity: EventSeverity;
  subsystem: EventSubsystem;
  transition?: string;
  reason: string;
  details?: string;
  metadata?: Record<string, string | number | boolean>;
}

export interface QuorumVoter {
  id: string;
  name: string;
  location: string;
  vote: 'PRIMARY_OUTAGE' | 'PRIMARY_HEALTHY' | 'ABSTAIN';
  latencyMs: number;
}

export type SelectedComponentType =
  | 'CLIENTS'
  | 'DNS'
  | 'REGION_A'
  | 'REGION_A_APP'
  | 'REGION_A_DB'
  | 'PRIMARY_DB'
  | 'REGION_A_HEALTH'
  | 'REGION_B'
  | 'REGION_B_APP'
  | 'REGION_B_DB'
  | 'STANDBY_DB'
  | 'REGION_B_HEALTH'
  | 'REPLICATION_LINK'
  | 'FENCING'
  | 'REPLICATION'
  | 'CONTROLLER'
  | 'CONTROLLER_HEALTH_MONITOR'
  | 'CONTROLLER_QUORUM'
  | 'QUORUM'
  | 'CONTROLLER_LEASE'
  | 'LEASE_FENCE'
  | 'CONTROLLER_EXECUTOR'
  | 'CONTROLLER_METADATA'
  | 'CONTROLLER_AUDIT';

export interface RegionModel {
  id: RegionId;
  name: string; // Region A: "Mumbai", Region B: "Singapore"
  cloudZone: string; // ap-south-1 vs ap-southeast-1
  role: RegionRole;
  health: HealthStatus;
  status: 'healthy' | 'degraded' | 'failed' | 'fenced';
  acceptsWrites: boolean; // SAFETY INVARIANT: Never true for both simultaneously
  ingressTrafficPercent: number; // 0 to 100%
  ingressRps: number;
  appServersHealthy: number;
  appServersTotal: number;
  activeConnections: number;
  iops: number;
  fencingEpoch: number; // Monotonically increasing generation epoch
  isFenced: boolean;
}

export interface ReplicationState {
  status: 'STREAMING' | 'DEGRADED' | 'SEVERED' | 'REVERSED' | 'SYNCED';
  lagSeconds: number; // In simulated seconds
  lagMs: number;
  bandwidthMbps: number;
  packetLossPercent: number;
  pendingBytes: number;
  bytesTransferred: number;
  mode: 'ASYNCHRONOUS_WAL';
}

export interface RouteState {
  activeTarget: RegionId;
  dnsTtlSeconds: number;
  propagationPercent: number; // 0 to 100%
  verificationStatus: 'UNVERIFIED' | 'VERIFYING' | 'VERIFIED' | 'FAILED';
}

/**
 * SIMULATION CONFIGURATION
 * Note: These are educational virtual lab prototype defaults, NOT production recommendations.
 */
export interface SimulationConfig {
  healthCheckIntervalSec: number; // Default: 2 simulated seconds
  failureThresholdConsecutive: number; // Default: 3 failed probes
  quorumSize: number; // Default: 3 simulated independent voters
  majorityRequired: number; // Default: 2 votes (2 of 3)
  acceptableReplicationLagSec: number; // Default: 5 simulated seconds
  fencingDurationSec: number; // Simulated duration to fence old primary
  routePropagationSec: number; // Simulated DNS propagation delay
  routeVerificationSec: number; // Simulated test probe delay
  autoFailoverEnabled: boolean;
}

export const DEFAULT_CONFIG: SimulationConfig = {
  healthCheckIntervalSec: 2,
  failureThresholdConsecutive: 3,
  quorumSize: 3,
  majorityRequired: 2,
  acceptableReplicationLagSec: 5,
  fencingDurationSec: 5,
  routePropagationSec: 4,
  routeVerificationSec: 2,
  autoFailoverEnabled: true,
};

export interface SimulationState {
  controllerState: ControllerState;
  simulatedTimeSeconds: number; // Explicit simulated time clock
  tickStepSec: number;
  wallClockStartTime: number;

  regionA: RegionModel; // Mumbai
  regionB: RegionModel; // Singapore

  config: SimulationConfig;
  replication: ReplicationState;
  route: RouteState;

  voters: QuorumVoter[];
  consecutiveFailures: number;
  lastHealthCheckSimTime: number;

  // Active Chaos Injections
  outageInjected: boolean;
  partitionInjected: boolean;
  replicationThrottled: boolean;
  standbyReadinessBroken: boolean;
  routeFailureInjected: boolean;

  // Safety Gates & Blocked Tracking
  blockedReason: string | null;
  blockedAtState: ControllerState | null;

  // Re-entrancy, Retries & Interruption Tracking
  resetEpoch: number;
  isSequenceInProgress: boolean;
  routeRetryCount: number;
  persistedIntent: string | null;
  isPausedInterrupted: boolean;

  // History & Inspector
  eventHistory: AuditRecord[];
  selectedComponent: SelectedComponentType;
}

export type SimulationAction =
  | { type: 'TICK'; deltaSec?: number }
  | { type: 'INJECT_PRIMARY_OUTAGE' }
  | { type: 'RECOVER_PRIMARY' }
  | { type: 'INJECT_NETWORK_PARTITION' }
  | { type: 'RESTORE_NETWORK_PARTITION' }
  | { type: 'INJECT_HIGH_REPLICATION_LAG' }
  | { type: 'RESTORE_REPLICATION_LAG' }
  | { type: 'INJECT_STANDBY_UNREADY' }
  | { type: 'RESTORE_STANDBY_READINESS' }
  | { type: 'INJECT_ROUTE_FAILURE' }
  | { type: 'RESTORE_ROUTE_HEALTH' }
  | { type: 'TRIGGER_MANUAL_FAILOVER' }
  | { type: 'STEP_FAILOVER' }
  | { type: 'RETRY_ROUTING_UPDATE' }
  | { type: 'CONTROLLER_INTERRUPT' }
  | { type: 'RESUME_CONTROLLER_RECONCILE' }
  | { type: 'TRIGGER_MANUAL_FAILBACK' }
  | { type: 'RECONCILE_REPLICATION' }
  | { type: 'DISMISS_BLOCKED_STATE' }
  | { type: 'UPDATE_CONFIG'; config: Partial<SimulationConfig> }
  | { type: 'RESTORE_CONFIG_DEFAULTS' }
  | { type: 'SELECT_COMPONENT'; component: SimulationState['selectedComponent'] }
  | { type: 'SET_VOTER_VOTE'; voterId: string; vote: 'PRIMARY_OUTAGE' | 'PRIMARY_HEALTHY' | 'ABSTAIN' }
  | { type: 'RESET_SIMULATION' };
