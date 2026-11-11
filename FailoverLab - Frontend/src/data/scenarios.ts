import type { ScenarioDefinition } from '../types/simulation';

export const SCENARIOS: ScenarioDefinition[] = [
  {
    id: 'scenario-a-normal',
    letter: 'A',
    title: 'SCENARIO A — NORMAL OPERATION',
    subtitle: 'Baseline Health & Single-Writer Invariant Stability',
    difficulty: 'Beginner',
    category: 'Safety',
    summary:
      'Both regions are fully healthy. Region A (Mumbai) serves 100% of ingress traffic. Region B (Singapore) remains in passive standby receiving asynchronous Write-Ahead Log (WAL) replication. Replication lag is minimal (0.8s), well within the 5.0s policy limit.',
    setup:
      'Region A is ACTIVE [Epoch 101], Region B is STANDBY [Epoch 101]. Health checks ping every 2s with 0 consecutive failures.',
    expectedBehaviour:
      'No unnecessary failovers occur. Only Region A accepts writes. The single-writer safety invariant is preserved continuously.',
    objectives: [
      'Observe steady-state active-passive topology with 2,450 RPS ingress to Mumbai',
      'Verify that Region B remains read-only and never claims active write authority',
      'Confirm asynchronous WAL replication lag remains steady at ~0.8s (< 5.0s policy)',
      'Inspect periodic 2s synthetic health probe heartbeats arriving with nominal latency',
    ],
    expectedRto: '0s (Nominal operation)',
    expectedRpo: '0 tx (Replication streaming nominal)',
    initialDescription:
      'Cluster running normally. Region A serves 2,450 RPS. Region B is warm standby.',
    steps: [
      {
        phase: '1. Steady-State Ingress',
        description: 'Global DNS directs 100% traffic to Region A (Mumbai). Region B remains idle standby.',
      },
      {
        phase: '2. WAL Streaming',
        description: 'Mumbai streams WAL logs across WAN to Singapore replica with ~0.8s latency.',
      },
      {
        phase: '3. Periodic Probing',
        description: 'Health agents in Mumbai and Singapore report nominal heartbeats every 2 seconds.',
      },
    ],
    setupChaos: (engine) => {
      engine.reset();
    },
    resetScenario: (engine) => {
      engine.reset();
    },
  },
  {
    id: 'scenario-b-primary-crash',
    letter: 'B',
    title: 'SCENARIO B — PRIMARY APPLICATION CRASH',
    subtitle: 'Complete Automated Multi-Step Failover Pipeline',
    difficulty: 'Intermediate',
    category: 'Crash',
    summary:
      'Region A primary storage suffers a sudden unrecoverable crash. Health monitors detect consecutive failed heartbeats. All safety gates pass: Quorum succeeds (3/3 votes), Region A is fenced (Epoch 102), Region B is promoted to ACTIVE writer, and Anycast DNS is repointed.',
    setup:
      'Mumbai primary database process killed. Synthetic health checks fail consecutively until reaching threshold 3/3.',
    expectedBehaviour:
      'The application visibly proceeds through failure detection (SUSPECTED), quorum voting, fencing, standby promotion, routing update, and verification.',
    objectives: [
      'Witness the 3-probe consecutive failure debouncer advancing to QUORUM_CHECK',
      'Observe 3 independent quorum observers voting to confirm Mumbai is down',
      'Verify generation epoch increment to #102 preventing split-brain writes',
      'Track DNS propagation cutover from 25% to 100% and synthetic test route verification',
    ],
    expectedRto: '~4.8s (Debounce 6s + Fence 1s + DNS 3s)',
    expectedRpo: '< 24ms (Un-replicated WAL delta)',
    initialDescription:
      'Sudden hard crash of Mumbai primary database. Controller executes full automated failover.',
    steps: [
      {
        phase: '1. Failure Detection',
        description: 'Mumbai DB process crashes; local health probes fail (1/3, 2/3, 3/3).',
      },
      {
        phase: '2. Quorum Consensus',
        description: '3 independent observers vote PRIMARY_OUTAGE, reaching 2/3 majority requirement.',
      },
      {
        phase: '3. Storage Fencing',
        description: 'Mumbai write authority revoked; fencing token epoch incremented to #102.',
      },
      {
        phase: '4. Standby Promotion & DNS Shift',
        description: 'Region B promoted to PRIMARY; DNS repoints traffic to Singapore; route verified.',
      },
    ],
    setupChaos: (engine) => {
      engine.reset();
      engine.injectPrimaryOutage();
    },
    resetScenario: (engine) => {
      engine.reset();
    },
  },
  {
    id: 'scenario-c-transient-failure',
    letter: 'C',
    title: 'SCENARIO C — TRANSIENT FAILURE / FALSE POSITIVE',
    subtitle: 'Hysteresis Debouncing & False-Positive Suppression',
    difficulty: 'Intermediate',
    category: 'Flapping',
    summary:
      'A transient WAN hiccup causes synthetic health probes to drop 1 or 2 heartbeats. Before the configured failure threshold (3 consecutive probes) is met, the primary recovers. The debouncer cancels the suspicion, suppressing costly premature failover.',
    setup:
      'Drop 2 consecutive probes in Region A, then restore heartbeats before the 3rd probe fails.',
    expectedBehaviour:
      'The primary returns to HEALTHY. Automatic failover is NOT triggered. The system logs the cancelled suspicion and explains why.',
    objectives: [
      'Understand why naive failover systems flip-flop catastrophically during transient jitter',
      'Observe state transitioning from HEALTHY to PRIMARY_SUSPECTED on probe 1 and 2',
      'Watch false-positive recovery trigger on probe 3, resetting failure counter to 0',
      'Verify that zero role changes, epoch increments, or DNS cuts were made',
    ],
    expectedRto: '0s (Failover suppressed; no cutover disruption)',
    expectedRpo: '0 tx (Replication uninterrupted)',
    initialDescription:
      'Transient 2-second packet drop. Controller marks primary SUSPECTED, then restores HEALTHY without failover.',
    steps: [
      {
        phase: '1. Transient Jitter Injected',
        description: 'Health probe fails (1/3); controller moves to PRIMARY_SUSPECTED.',
      },
      {
        phase: '2. Debounce Counter Increment',
        description: 'Second probe fails (2/3); controller holds in debounce window.',
      },
      {
        phase: '3. False-Positive Recovery',
        description: 'Probe 3 succeeds; controller logs false-positive suppression and resets counter to 0.',
      },
    ],
    setupChaos: (engine) => {
      engine.reset();
      engine.triggerFlapping();
    },
    resetScenario: (engine) => {
      engine.reset();
    },
  },
  {
    id: 'scenario-d-network-partition-quorum-lost',
    letter: 'D',
    title: 'SCENARIO D — NETWORK PARTITION / QUORUM LOST',
    subtitle: 'Split-Brain Prevention Under Insufficient Quorum Votes',
    difficulty: 'Advanced',
    category: 'Partition',
    summary:
      'A cross-region network partition isolates monitoring observers. Independent observers cannot agree on the primary failure (e.g. only 1 of 3 votes for outage). The controller halts and blocks failover to prevent split-brain dual-primary corruption.',
    setup:
      'Sever cross-region fiber link. Configure observer votes such that majority (2/3) cannot be attained.',
    expectedBehaviour:
      'Do not promote the standby. Show a blocked state (FAILOVER_BLOCKED) and explain that the controller cannot safely confirm the primary failure.',
    objectives: [
      'Learn why 2-node clusters cannot safely partition without a 3rd tie-breaker',
      'Observe Gate 1 failing when outage votes (1/3) < required majority (2/3)',
      'Inspect the prominent FAILOVER_BLOCKED banner with clear explanation',
      'Verify that Region B remains safely in standby with zero unauthorized writes',
    ],
    expectedRto: 'Blocked (Data safety prioritized over availability)',
    expectedRpo: '0 tx (Split-brain prevented)',
    initialDescription:
      'Network partition with lost quorum consensus. Controller halts at Safety Gate 1.',
    steps: [
      {
        phase: '1. Partition Injected',
        description: 'Cross-region transit severed. Observer votes split (1 Outage, 2 Healthy/Abstain).',
      },
      {
        phase: '2. Quorum Check Invoked',
        description: 'Controller gathers votes but fails to achieve required 2/3 majority.',
      },
      {
        phase: '3. Transition Blocked',
        description: 'Controller enters FAILOVER_BLOCKED to prevent catastrophic split-brain writes.',
      },
    ],
    setupChaos: (engine) => {
      engine.reset();
      engine.injectNetworkPartition();
      engine.injectPrimaryOutage();
      engine.setVoterVote('voter-1', 'PRIMARY_HEALTHY');
      engine.setVoterVote('voter-2', 'PRIMARY_OUTAGE');
      engine.setVoterVote('voter-3', 'PRIMARY_HEALTHY');
    },
    resetScenario: (engine) => {
      engine.reset();
    },
  },
  {
    id: 'scenario-e-standby-unhealthy',
    letter: 'E',
    title: 'SCENARIO E — STANDBY UNHEALTHY',
    subtitle: 'Standby Readiness Verification Safety Gate',
    difficulty: 'Intermediate',
    category: 'Safety',
    summary:
      'Region B (Singapore) suffers local storage corruption before Mumbai fails. When Mumbai crashes, the controller reaches Quorum Check but halts because Gate 2 (Standby Readiness) fails. Promoting a dead standby would convert a single-region outage into total system death.',
    setup:
      'Mark Region B health as DOWN. Trigger Mumbai primary failure.',
    expectedBehaviour:
      'Do not complete automatic failover. Halt in FAILOVER_BLOCKED and explain that no verified healthy destination is available.',
    objectives: [
      'Understand the danger of blindly promoting an unverified replica',
      'Verify Gate 2 intercepting the failover pipeline before fencing Region A',
      'Confirm Region A is not needlessly fenced when the failover destination is down',
      'Review actionable operator guidance in the blocked state banner',
    ],
    expectedRto: 'Blocked (Standby unavailable)',
    expectedRpo: 'N/A (Cutover rejected)',
    initialDescription:
      'Singapore replica is unhealthy. When Mumbai crashes, controller blocks promotion.',
    steps: [
      {
        phase: '1. Standby Corrupted',
        description: 'Singapore replica marked DOWN with failed storage health check.',
      },
      {
        phase: '2. Primary Failure Detected',
        description: 'Mumbai crashes; quorum majority confirmed by observers.',
      },
      {
        phase: '3. Readiness Gate Halts Failover',
        description: 'Gate 2 fails. Promotion aborted. Controller transitions to FAILOVER_BLOCKED.',
      },
    ],
    setupChaos: (engine) => {
      engine.reset();
      engine.injectStandbyUnready();
      engine.injectPrimaryOutage();
    },
    resetScenario: (engine) => {
      engine.reset();
    },
  },
  {
    id: 'scenario-f-high-replication-lag',
    letter: 'F',
    title: 'SCENARIO F — HIGH REPLICATION LAG',
    subtitle: 'RPO Data-Loss Protection Safety Gate',
    difficulty: 'Intermediate',
    category: 'Degradation',
    summary:
      'WAN bandwidth throttling causes asynchronous WAL replication lag to balloon to 8.4 seconds (exceeding the 5.0s policy limit). When Mumbai fails, promoting Singapore immediately would cause ~20,500 uncommitted transactions to vanish.',
    setup:
      'Throttle cross-region bandwidth. Lag spikes to 8.4s. Mumbai crashes.',
    expectedBehaviour:
      'Block automatic promotion under the current policy and show the potential data-loss risk. Any exceptional override must be explicit and recorded.',
    objectives: [
      'Grasp the fundamental trade-off between RTO (recovery time) and RPO (data loss)',
      'Calculate potential transactional loss (8.4s * 2,450 RPS = ~20,500 transactions at risk)',
      'Verify Gate 3 blocking failover with an explicit RPO breach warning',
      'Test policy adjustment slider and observe how increasing threshold to 10s unblocks promotion',
    ],
    expectedRto: 'Blocked (Pending manual authorization or lag catch-up)',
    expectedRpo: '8,400ms (Unacceptable under 5s policy)',
    initialDescription:
      'Replication lag at 8.4s (> 5s limit). Controller halts at Gate 3 to protect data integrity.',
    steps: [
      {
        phase: '1. Replication Lag Throttled',
        description: 'Replication lag spikes to 8.4s; RPO status flips to DEGRADED.',
      },
      {
        phase: '2. Primary Crashes',
        description: 'Mumbai fails; quorum verifies outage.',
      },
      {
        phase: '3. Gate 3 Blocks Promotion',
        description: 'Lag > 5.0s policy limit. Promotion halted in FAILOVER_BLOCKED.',
      },
    ],
    setupChaos: (engine) => {
      engine.reset();
      engine.injectHighReplicationLag();
      engine.injectPrimaryOutage();
    },
    resetScenario: (engine) => {
      engine.reset();
    },
  },
  {
    id: 'scenario-g-route-failure',
    letter: 'G',
    title: 'SCENARIO G — DNS / ROUTING UPDATE FAILURE',
    subtitle: 'Bounded Retries & Degraded-Service Route Verification',
    difficulty: 'Advanced',
    category: 'Crash',
    summary:
      'Region B is safely promoted to Primary, but global Anycast BGP routing table updates fail. The controller attempts bounded retries, records every attempt, and refuses to report successful recovery until route verification passes.',
    setup:
      'Inject route failure. Crash Mumbai primary. Observe promotion succeed but route verification fail.',
    expectedBehaviour:
      'Retry a bounded number of times, record every attempt, and do not report successful traffic recovery until route verification succeeds. Display the degraded-service condition clearly.',
    objectives: [
      'Learn why database promotion alone does not equal application availability',
      'Observe Gate 6 failing when synthetic test requests to Singapore time out',
      'Use the dedicated "Retry Routing Update" control to re-test BGP convergence',
      'Verify traffic shifts to Singapore only after route verification succeeds',
    ],
    expectedRto: 'Extended by retry backoff',
    expectedRpo: '< 24ms (Database promoted safely)',
    initialDescription:
      'Standby promoted, but DNS routing update fails. Controller halts at Gate 6 with retry controls.',
    steps: [
      {
        phase: '1. Primary Fails & Promotes',
        description: 'Mumbai crashes; Singapore promoted to Primary with Epoch 102.',
      },
      {
        phase: '2. Route Cutover Fails',
        description: 'DNS Anycast BGP update fails to converge; verification probe times out.',
      },
      {
        phase: '3. Bounded Retry & Recovery',
        description: 'Controller records retry attempts. Operator clicks "Retry Routing Update" to verify.',
      },
    ],
    setupChaos: (engine) => {
      engine.reset();
      engine.injectRouteFailure();
      engine.injectPrimaryOutage();
    },
    resetScenario: (engine) => {
      engine.reset();
    },
  },
  {
    id: 'scenario-h-old-primary-recovers',
    letter: 'H',
    title: 'SCENARIO H — OLD PRIMARY RECOVERS',
    subtitle: 'Asymmetric Re-Join & Deliberate Manual Failback',
    difficulty: 'Intermediate',
    category: 'Recovery',
    summary:
      'After failover to Singapore completes, the old Mumbai primary recovers. Instead of an automated thundering-herd switchback, Mumbai re-joins in STANDBY mode. Failback requires reverse replication synchronization, health verification, and an explicit operator command.',
    setup:
      'Run failover to Region B (SECONDARY_ACTIVE). Then restore Mumbai back online.',
    expectedBehaviour:
      'Region A returns as standby. The current active writer and route stay on Region B. Failback requires health, synchronization, fencing, and an explicit user command.',
    objectives: [
      'Learn why automated failback is an anti-pattern in distributed systems (ping-pong hazard)',
      'Watch Mumbai re-join as STANDBY with 0% ingress and revoked write lock',
      'Reconcile reverse replication (Singapore -> Mumbai WAL sync)',
      'Click "Approve Failback" to execute controlled, safe role reversal back to Mumbai',
    ],
    expectedRto: 'Controlled maintenance window (< 2s)',
    expectedRpo: '0 tx (Full reverse WAL reconciliation)',
    initialDescription:
      'Region B is active writer. Mumbai recovers online. Controller enforces manual failback protocol.',
    steps: [
      {
        phase: '1. Singapore Active',
        description: 'Region B serves 100% traffic as primary with Epoch 102.',
      },
      {
        phase: '2. Mumbai Re-joins in Standby',
        description: 'Mumbai hardware boots up. Fencing status verified; role set to STANDBY.',
      },
      {
        phase: '3. Reverse WAL Reconciliation',
        description: 'WAL stream reversed from Singapore to Mumbai. Lag reaches 0.5s.',
      },
      {
        phase: '4. Controlled Manual Failback',
        description: 'Operator approves failback. Singapore fenced; Mumbai promoted to Epoch 103.',
      },
    ],
    setupChaos: (engine) => {
      engine.reset();
      // Step to SECONDARY_ACTIVE
      engine.injectPrimaryOutage();
      engine.scheduleTimeout(() => {
        engine.recoverPrimary();
      }, 5000);
    },
    resetScenario: (engine) => {
      engine.reset();
    },
  },
  {
    id: 'scenario-i-controller-interruption',
    letter: 'I',
    title: 'SCENARIO I — CONTROLLER INTERRUPTION',
    subtitle: 'Mid-Transition Halt & Idempotent State Reconciliation',
    difficulty: 'Advanced',
    category: 'Interruption',
    summary:
      'Simulate the failover controller crashing or pausing mid-flight during the cutover sequence. When restarted, the controller reads persisted transition intent from the metadata store, verifies fencing tokens, and reconciles state without exposing dual-active writers.',
    setup:
      'Initiate failover, then immediately interrupt the controller mid-transition.',
    expectedBehaviour:
      'Pause the sequence. On restart, reconcile persisted transition intent and known simulated state before continuing. Do not blindly repeat promotion or expose dual-active write status.',
    objectives: [
      'Understand the danger of non-idempotent failover logic (double promotion / split-brain)',
      'Observe persisted transition intent saved in the linearizable metadata store',
      'Resume the orchestrator and inspect the idempotent reconciliation audit event',
      'Verify system safely converges to SECONDARY_ACTIVE with valid epoch progression',
    ],
    expectedRto: 'Resumed safely post-reconciliation',
    expectedRpo: '0 tx corruption',
    initialDescription:
      'Controller halted mid-transition. Resuming reconciles persistent intent without dual-primary.',
    steps: [
      {
        phase: '1. Cutover Initiated',
        description: 'Mumbai fails; controller begins fencing sequence.',
      },
      {
        phase: '2. Orchestrator Interrupted',
        description: 'Controller process halted mid-transition. State saved to metadata store.',
      },
      {
        phase: '3. Idempotent Reconciliation',
        description: 'Controller restarts; verifies persisted intent; completes promotion safely.',
      },
    ],
    setupChaos: (engine) => {
      engine.reset();
      engine.injectPrimaryOutage();
      engine.scheduleTimeout(() => {
        engine.controllerInterrupt();
      }, 1500);
    },
    resetScenario: (engine) => {
      engine.reset();
    },
  },
];
