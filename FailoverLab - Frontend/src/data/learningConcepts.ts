export interface LearningConcept {
  id: string;
  number: number;
  title: string;
  shortDesc: string;
  whatItMeans: string;
  whyNeeded: string;
  whatToObserve: string;
  modelLimitation: string;
}

export const LEARNING_CONCEPTS: LearningConcept[] = [
  {
    id: 'active-passive',
    number: 1,
    title: 'Active-Passive Architecture',
    shortDesc: 'Single-writer topology with hot/warm standby disaster recovery replica',
    whatItMeans:
      'A multi-region deployment pattern where only one primary region accepts read-write application traffic, while one or more secondary regions maintain replicas of the data ready to assume the primary role if disaster strikes.',
    whyNeeded:
      'Avoids the extreme complexity of multi-master conflict resolution (e.g. concurrent updates to the same row in different geographic regions) while delivering disaster recovery across global regions.',
    whatToObserve:
      'Notice that Region A holds the READ_WRITE lock with active IOPS while Region B remains strictly READ_ONLY. Region B never accepts writes until explicitly promoted.',
    modelLimitation:
      'In a physical cloud environment, the passive standby may serve read-only queries across read replicas; FailoverLab focuses purely on write authority and cutover coordination.',
  },
  {
    id: 'health-checks',
    number: 2,
    title: 'Health Checks & False Positives',
    shortDesc: 'Synthetic probe debouncing to prevent premature failover on transient jitter',
    whatItMeans:
      'Automated probes sent across networks to determine node availability. A false positive occurs when temporary network latency or packet loss causes healthy nodes to appear dead.',
    whyNeeded:
      'WAN internet connections frequently drop packets for 1-2 seconds. Triggering a database promotion on a single lost probe would cause catastrophic, unnecessary service interruption and failover flapping.',
    whatToObserve:
      'Watch Scenario C where 1 or 2 probes fail, moving state to PRIMARY_SUSPECTED. When probe 3 succeeds, the failure count resets to 0 and the false positive is suppressed without failover.',
    modelLimitation:
      'Probes in this lab use simulated discrete second ticks rather than true HTTP/TCP socket keep-alive probe streams with jitter and TCP timeouts.',
  },
  {
    id: 'quorum-detection',
    number: 3,
    title: 'Quorum & Failure Detection',
    shortDesc: 'Odd-numbered distributed observer voting (N/2 + 1 majority rule)',
    whatItMeans:
      'A consensus mechanism requiring a strict majority (> 50%) of independent observer nodes to agree on a state change before action is taken.',
    whyNeeded:
      'In a two-region system (Mumbai and Singapore), if the network cable between them is severed, neither region can determine whether the other crashed or the network broke. A 3rd neutral observer (e.g. Zurich) breaks the tie authoritatively.',
    whatToObserve:
      'In Scenario D, notice how the controller gathers votes from Mumbai, Singapore, and Zurich. When only 1 observer reports an outage, failover is blocked because 1/3 is below the required 2/3 majority.',
    modelLimitation:
      'FailoverLab simulates Raft/Paxos voting via deterministic state variables rather than asynchronous network consensus RPCs over socket connections.',
  },
  {
    id: 'split-brain',
    number: 4,
    title: 'Split-Brain Vulnerability',
    shortDesc: 'The catastrophic state where two independent regions simultaneously accept writes',
    whatItMeans:
      'A failure condition where two separate nodes in a cluster both believe they are the authoritative primary writer, accepting concurrent diverging writes from clients.',
    whyNeeded:
      'Split-brain causes irreversible silent data corruption. Once two databases diverge, automated reconciliation is virtually impossible without manual data surgery or transaction loss.',
    whatToObserve:
      'Safety Gate 5 explicitly verifies that `!(RegionA.acceptsWrites && RegionB.acceptsWrites)`. The simulator halts immediately with FAILOVER_BLOCKED if dual writers could ever exist.',
    modelLimitation:
      'FailoverLab programmatically guarantees single-writer safety in its transition logic, whereas production systems rely on hardware fencing, STONITH, or cloud IAM API calls that can occasionally fail.',
  },
  {
    id: 'leases-fencing',
    number: 5,
    title: 'Write Leases & Fencing Tokens',
    shortDesc: 'Martin Kleppmann generation epoch tokens and storage-level write revocation',
    whatItMeans:
      'Time-bounded authorization leases paired with monotonically increasing epoch numbers (e.g. Epoch 101 -> 102). Storage layers reject any write carrying an older generation token.',
    whyNeeded:
      'Even if an old primary pauses (due to a garbage collection pause or network freeze) and wakes up later, its write token is outdated. The storage layer rejects its trailing packets, guaranteeing consistency.',
    whatToObserve:
      'Observe the Generation Epoch increment from #101 to #102 during FENCING_PRIMARY. Region A is hard-fenced before Region B is granted write permission.',
    modelLimitation:
      'Storage fencing is modelled via state variables rather than physical disk SCSI-3 persistent reservations or cloud storage condition checks.',
  },
  {
    id: 'replication',
    number: 6,
    title: 'Primary-to-Standby Replication',
    shortDesc: 'Asynchronous Write-Ahead Log (WAL) delta streaming across trans-oceanic WAN',
    whatItMeans:
      'The process where transaction log entries committed on the primary database are continuously shipped over the WAN and replayed on the standby replica.',
    whyNeeded:
      'Keeps the standby data as fresh as possible so it is ready for promotion with minimal transaction loss when a regional disaster occurs.',
    whatToObserve:
      'Look at the cross-region replication link in the architecture diagram. It displays WAL streaming status and lag in seconds and milliseconds.',
    modelLimitation:
      'Replication is modelled with a simulated lag parameter rather than physical database engine WAL streaming sockets and disk replay queues.',
  },
  {
    id: 'lag-rto-rpo',
    number: 7,
    title: 'Replication Lag, RTO, and RPO',
    shortDesc: 'The fundamental trade-off between Recovery Time and Recovery Point Objectives',
    whatItMeans:
      'RTO (Recovery Time Objective) is the maximum acceptable downtime before service is restored. RPO (Recovery Point Objective) is the maximum acceptable transactional data loss measured in time or transaction volume.',
    whyNeeded:
      'Fast automated failover (low RTO) can conflict with zero data loss (low RPO). If replication is lagging by 8 seconds, failing over immediately incurs 8 seconds of lost data (~20,000 transactions at 2,450 RPS).',
    whatToObserve:
      'Test Scenario F where replication lag spikes to 8.4s. The controller halts at Gate 3 to prevent RPO breach under the 5.0s policy limit.',
    modelLimitation:
      'RPO loss in the simulation is an estimation derived from `lagSeconds * ingressRps` rather than a forensic diff of un-replicated database commit blocks.',
  },
  {
    id: 'dns-caching',
    number: 8,
    title: 'DNS Failover & Client-Side Caching',
    shortDesc: 'Low-TTL CNAME propagation delays and recursive resolver caching reality',
    whatItMeans:
      'Using Domain Name System records with low Time-To-Live (e.g. 5s) to repoint client domains (e.g. api.failoverlab.internal) from Mumbai to Singapore IP endpoints.',
    whyNeeded:
      'Allows global client traffic to be dynamically re-routed to the standby region without requiring code deployment or manual client reconfiguration.',
    whatToObserve:
      'During ROUTE_UPDATING, watch the propagation bar advance from 25% to 100%. Clients with cached records continue sending requests to the old region until their local TTL expires.',
    modelLimitation:
      'The simulation models DNS propagation as a discrete progress percentage rather than thousands of distributed ISP resolver cache expiries.',
  },
  {
    id: 'controlled-failback',
    number: 9,
    title: 'Controlled Manual Failback',
    shortDesc: 'Asymmetric re-join and why automated switchback is an anti-pattern',
    whatItMeans:
      'The deliberate procedure of returning primary authority back to the original region once it has fully recovered and synchronized its reverse replication stream.',
    whyNeeded:
      'Automated failback is dangerous. If Region A reboots with intermittent stability, automatically switching back could cause secondary crashes or thundering-herd ping-pong failovers.',
    whatToObserve:
      'In Scenario H, when Mumbai recovers, it re-joins as STANDBY. The controller enters PRIMARY_RECOVERING, reverses the WAL stream, and waits for explicit operator approval before switching.',
    modelLimitation:
      'Reverse sync in the simulation is accelerated for lab demonstration; physical databases must re-synchronize gigabytes of delta WAL logs before role reversal.',
  },
  {
    id: 'control-plane-recovery',
    number: 10,
    title: 'Control-Plane Interruption & Recovery',
    shortDesc: 'Idempotent state reconciliation when the orchestrator itself fails mid-transition',
    whatItMeans:
      'Ensuring the failover controller can crash or pause mid-transition, reboot, read persisted intent from its metadata store, and safely continue without repeating actions or corrupting state.',
    whyNeeded:
      'In distributed systems, controllers fail too. If an orchestrator crashes after fencing Region A but before promoting Region B, it must resume idempotently without granting dual write leases.',
    whatToObserve:
      'Scenario I pauses the orchestrator at FENCING_PRIMARY. On resume, the controller validates persisted intent, confirms Region A is fenced, and safely promotes Region B with monotonic Epoch 102.',
    modelLimitation:
      'Persisted intent is stored in the simulated state engine rather than a replicated Raft/etcd distributed key-value cluster across physical nodes.',
  },
];
