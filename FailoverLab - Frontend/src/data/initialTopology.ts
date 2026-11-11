import type {
  RegionState,
  DatabaseNode,
  DnsState,
  LeaseFenceState,
  ReplicationChannelState,
  QuorumEngineState,
  GlobalTelemetry,
  FailoverConfig,
  FailoverState,
} from '../types/simulation';

export const INITIAL_REGION_A: RegionState = {
  id: 'region-a',
  name: 'Region A (Mumbai)',
  code: 'ap-south-1',
  status: 'healthy',
  role: 'ACTIVE',
  appServersHealthy: 12,
  appServersTotal: 12,
  ingressRps: 2450,
  avgLatencyMs: 18,
  errorRatePercent: 0.02,
};

export const INITIAL_REGION_B: RegionState = {
  id: 'region-b',
  name: 'Region B (Singapore)',
  code: 'ap-southeast-1',
  status: 'healthy',
  role: 'STANDBY',
  appServersHealthy: 12,
  appServersTotal: 12,
  ingressRps: 0,
  avgLatencyMs: 34,
  errorRatePercent: 0.0,
};

export const INITIAL_PRIMARY_DB: DatabaseNode = {
  id: 'db-region-a',
  region: 'region-a',
  name: 'Primary Database (Aurora / Postgres)',
  role: 'PRIMARY',
  accessMode: 'READ_WRITE',
  status: 'healthy',
  generationId: 101, // Generation Epoch
  replicationLagMs: 0,
  uncommittedTxCount: 0,
  iops: 4800,
  storageGb: 850,
  lastHeartbeat: Date.now(),
};

export const INITIAL_STANDBY_DB: DatabaseNode = {
  id: 'db-region-b',
  region: 'region-b',
  name: 'Standby Replica (Cross-Region)',
  role: 'STANDBY',
  accessMode: 'READ_ONLY',
  status: 'healthy',
  generationId: 101,
  replicationLagMs: 24, // 24ms nominal cross-ocean WAL streaming lag
  uncommittedTxCount: 0,
  iops: 120,
  storageGb: 850,
  lastHeartbeat: Date.now(),
};

export const INITIAL_DNS: DnsState = {
  primaryTarget: 'region-a',
  ttlSeconds: 5, // Low TTL for fast failover routing
  activeDnsTarget: 'region-a',
  propagationProgress: 100,
  routingRule: 'FAILOVER_HEALTH_CHECK',
  resolutionStatus: 'NOMINAL',
};

export const INITIAL_LEASE_FENCE: LeaseFenceState = {
  currentHolder: 'region-a',
  generationId: 101,
  leaseTtlMs: 5000,
  leaseRemainingMs: 5000,
  fenceStatus: 'ACTIVE_LOCK',
  lastRenewedAt: Date.now(),
};

export const INITIAL_REPLICATION: ReplicationChannelState = {
  status: 'STREAMING',
  lagMs: 24,
  bandwidthMbps: 450,
  packetLossPercent: 0.0,
  pendingBytes: 12400,
  mode: 'ASYNCHRONOUS_WAL',
};

export const INITIAL_QUORUM: QuorumEngineState = {
  nodes: [
    {
      id: 'q-node-1',
      name: 'Observer 1',
      location: 'ap-south-1 (Mumbai Local)',
      alive: true,
      vote: 'region-a',
      latencyMs: 4,
    },
    {
      id: 'q-node-2',
      name: 'Observer 2',
      location: 'ap-southeast-1 (Singapore Local)',
      alive: true,
      vote: 'region-a',
      latencyMs: 28,
    },
    {
      id: 'q-node-3',
      name: 'Observer 3 (Tie-Breaker)',
      location: 'eu-central-1 (Neutral / Zurich)',
      alive: true,
      vote: 'region-a',
      latencyMs: 72,
    },
  ],
  requiredVotes: 2,
  currentLeaderVote: 'region-a',
  consensusReached: true,
  lastElectionTime: Date.now(),
};

export const INITIAL_TELEMETRY: GlobalTelemetry = {
  simTick: 0,
  uptimeSeconds: 0,
  totalClientRps: 2450,
  overallSuccessRate: 99.98,
  clientErrorRate: 0.02,
  p95LatencyMs: 22,
  totalFailoversCount: 0,
  lastFailoverDurationMs: null,
  estimatedRpoLossTx: 0,
};

export const INITIAL_CONFIG: FailoverConfig = {
  heartbeatIntervalMs: 1000,
  failureThresholdConsecutive: 3,
  leaseTtlSeconds: 5,
  dnsPropagationDelaySeconds: 3,
  autoFailoverEnabled: true,
  hysteresisWindowSeconds: 4,
};

export const INITIAL_CONTROLLER_STATE: FailoverState = 'NOMINAL';
