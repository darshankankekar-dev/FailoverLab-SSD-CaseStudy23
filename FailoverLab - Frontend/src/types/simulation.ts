// System Design & SSD Case Study 23: Multi-Region Active-Passive Failover Controller

export type RegionId = 'region-a' | 'region-b';

export type NodeStatus = 'healthy' | 'degraded' | 'failed' | 'fenced' | 'recovering' | 'standby';

export type FailoverState =
  | 'NOMINAL'
  | 'HEALTH_WARNING'
  | 'QUORUM_VOTING'
  | 'REVOKING_LEASE'
  | 'FENCING_PRIMARY'
  | 'CATCHING_UP_REPLICATION'
  | 'PROMOTING_STANDBY'
  | 'UPDATING_DNS'
  | 'TRAFFIC_SHIFT'
  | 'FAILOVER_COMPLETE'
  | 'SPLIT_BRAIN_BLOCKED';

export type EventSeverity = 'info' | 'warn' | 'critical' | 'success' | 'action';

export type EventSubsystem =
  | 'DNS'
  | 'DATABASE'
  | 'QUORUM'
  | 'FENCING'
  | 'CONTROLLER'
  | 'NETWORK'
  | 'CHAOS'
  | 'METRICS';

export interface AuditEvent {
  id: string;
  timestamp: string;
  simTime: number; // in seconds
  severity: EventSeverity;
  subsystem: EventSubsystem;
  title: string;
  description: string;
  metadata?: Record<string, string | number | boolean>;
}

export interface QuorumNode {
  id: string;
  name: string;
  location: string;
  alive: boolean;
  vote: RegionId | 'NONE';
  latencyMs: number;
}

export interface DatabaseNode {
  id: string;
  region: RegionId;
  name: string;
  role: 'PRIMARY' | 'STANDBY';
  accessMode: 'READ_WRITE' | 'READ_ONLY' | 'FENCED';
  status: NodeStatus;
  generationId: number;
  replicationLagMs: number;
  uncommittedTxCount: number;
  iops: number;
  storageGb: number;
  lastHeartbeat: number;
}

export interface RegionState {
  id: RegionId;
  name: string;
  code: string; // ap-south-1 (Mumbai) / ap-southeast-1 (Singapore)
  status: NodeStatus;
  role: 'ACTIVE' | 'STANDBY';
  appServersHealthy: number;
  appServersTotal: number;
  ingressRps: number;
  avgLatencyMs: number;
  errorRatePercent: number;
}

export interface DnsState {
  primaryTarget: RegionId;
  ttlSeconds: number;
  activeDnsTarget: RegionId;
  propagationProgress: number; // 0 to 100%
  routingRule: 'GEO_PROXIMITY' | 'FAILOVER_HEALTH_CHECK';
  resolutionStatus: 'NOMINAL' | 'PROPAGATING' | 'FAILED';
}

export interface LeaseFenceState {
  currentHolder: RegionId | null;
  generationId: number; // Monotonically increasing epoch fencing token
  leaseTtlMs: number;
  leaseRemainingMs: number;
  fenceStatus: 'ACTIVE_LOCK' | 'GRACE_PERIOD' | 'EXPIRED' | 'REVOKED' | 'HARD_FENCED';
  lastRenewedAt: number;
}

export interface ReplicationChannelState {
  status: 'STREAMING' | 'DEGRADED' | 'SEVERED' | 'CATCHING_UP';
  lagMs: number;
  bandwidthMbps: number;
  packetLossPercent: number;
  pendingBytes: number;
  mode: 'ASYNCHRONOUS_WAL';
}

export interface QuorumEngineState {
  nodes: QuorumNode[];
  requiredVotes: number; // 2 out of 3
  currentLeaderVote: RegionId | 'SPLIT' | 'NONE';
  consensusReached: boolean;
  lastElectionTime: number;
}

export interface GlobalTelemetry {
  simTick: number; // monotonically increasing ticks
  uptimeSeconds: number;
  totalClientRps: number;
  overallSuccessRate: number;
  clientErrorRate: number;
  p95LatencyMs: number;
  totalFailoversCount: number;
  lastFailoverDurationMs: number | null;
  estimatedRpoLossTx: number;
}

export interface FailoverConfig {
  heartbeatIntervalMs: number; // e.g. 1000
  failureThresholdConsecutive: number; // e.g. 3
  leaseTtlSeconds: number; // e.g. 5
  dnsPropagationDelaySeconds: number; // e.g. 3
  autoFailoverEnabled: boolean;
  hysteresisWindowSeconds: number; // prevent flapping
}

export interface ScenarioDefinition {
  id: string;
  letter: string; // 'A' | 'B' | 'C' | 'D' | 'E' | 'F' | 'G' | 'H' | 'I'
  title: string;
  subtitle: string;
  difficulty: 'Beginner' | 'Intermediate' | 'Advanced';
  category: 'Partition' | 'Crash' | 'Degradation' | 'Maintenance' | 'Flapping' | 'Safety' | 'Recovery' | 'Interruption';
  summary: string;
  setup: string;
  expectedBehaviour: string;
  objectives: string[];
  expectedRto: string;
  expectedRpo: string;
  initialDescription: string;
  steps: {
    phase: string;
    description: string;
    triggerTick?: number;
  }[];
  setupChaos: (engine: any) => void;
  resetScenario?: (engine: any) => void;
}

export type SelectedComponentType =
  | 'CLIENTS'
  | 'DNS'
  | 'REGION_A'
  | 'REGION_B'
  | 'PRIMARY_DB'
  | 'STANDBY_DB'
  | 'QUORUM'
  | 'LEASE_FENCE'
  | 'REPLICATION_LINK'
  | 'CONTROLLER';
