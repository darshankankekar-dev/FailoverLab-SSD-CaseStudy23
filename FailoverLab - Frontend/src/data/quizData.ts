export interface QuizQuestion {
  id: string;
  question: string;
  options: string[];
  correctIndex: number;
  explanation: string;
  systemDesignPrinciple: string;
}

export const QUIZ_QUESTIONS: QuizQuestion[] = [
  {
    id: 'q1',
    question:
      'Why is an Epoch Generation Fencing Token required when promoting a Standby database to Primary during a network partition?',
    options: [
      'To encrypt cross-region replication traffic across public Internet transit.',
      'To prevent the old Primary, which might still be alive in a partitioned network, from accepting concurrent stale writes (Split-Brain).',
      'To increase database write throughput by parallelizing IOPS across both regions simultaneously.',
      'To bypass DNS caching by sending unique tokens inside HTTP headers.',
    ],
    correctIndex: 1,
    explanation:
      'In a network partition, the old Primary might still be running and believing it is the leader. Without fencing tokens (monotonically increasing generation IDs), both nodes could accept writes simultaneously, corrupting data permanently (Split-Brain). Storage engines reject any request tagged with an older generation ID than the current lease.',
    systemDesignPrinciple: 'Split-Brain Mitigation & Martin Kleppmann Fencing Tokens',
  },
  {
    id: 'q2',
    question:
      'Why does the Quorum Decision Engine use an odd number of observer nodes (e.g. 3 nodes across Mumbai, Singapore, and Zurich) instead of 2?',
    options: [
      'Two nodes cannot provide high availability because European cloud regulations require 3 data centers.',
      'With 2 nodes, any single network disconnection between them creates a 50/50 tie where neither can obtain a strict majority (> 50%), preventing safe automated consensus.',
      'Odd-numbered nodes reduce replication lag by transmitting packets in parallel three ways.',
      'Three nodes allow active-active load balancing for client write requests.',
    ],
    correctIndex: 1,
    explanation:
      'Quorum consensus requires a strict majority (> N/2). For N=2, required quorum is 2/2 (100%), so if one node disconnects, the entire system is paralyzed. With N=3, required quorum is 2/3 (66.7%), meaning any 1 node can fail or become partitioned while the remaining 2 can still make safe, authoritative decisions.',
    systemDesignPrinciple: 'Distributed Consensus & Majority Quorum Math (N/2 + 1)',
  },
  {
    id: 'q3',
    question:
      'In an active-passive topology with asynchronous cross-region replication, what determines the Recovery Point Objective (RPO) during a sudden power outage in the active region?',
    options: [
      'The time it takes for DNS records to update worldwide.',
      'The amount of un-replicated WAL (write-ahead log) data that was in transit between the regions when the crash occurred.',
      'The time taken for the standby database to boot and finish health checks.',
      'The number of CPU cores provisioned on the Singapore replica.',
    ],
    correctIndex: 1,
    explanation:
      'RPO (Recovery Point Objective) measures maximum acceptable data loss in terms of time. In asynchronous replication, transactions committed on the primary take milliseconds to cross the WAN. If the primary crashes instantly, all buffered un-replicated transactions are lost unless synchronous replication was enforced.',
    systemDesignPrinciple: 'RPO (Data Loss Window) vs RTO (Downtime Duration)',
  },
  {
    id: 'q4',
    question:
      'What critical failure mode occurs if a failover controller does not utilize a Hysteresis Sliding Window or debounce timer?',
    options: [
      'The database will run out of disk space due to excessive logging.',
      'Transient network jitter will trigger rapid ping-pong failovers back and forth between regions, causing cascading thrashing and prolonged service degradation.',
      'DNS servers will permanently blacklist the domain name for excessive record mutations.',
      'The standby database will downgrade itself to a read-only cache.',
    ],
    correctIndex: 1,
    explanation:
      'Network links on the Internet flap (drop packets for 1-2 seconds then restore). If a controller acts on a single failed probe without hysteresis damping, it initiates expensive failovers back and forth, disrupting connections, evicting caches, and triggering thundering herd problems.',
    systemDesignPrinciple: 'Hysteresis Damping & Anti-Flapping Stabilization',
  },
  {
    id: 'q5',
    question:
      'Even after the Failover Controller successfully updates the global DNS record to point to Region B, why do some clients still send traffic to Region A?',
    options: [
      'Client and ISP DNS resolvers cache DNS A/CNAME records for the duration of the Time-To-Live (TTL).',
      'The standby database refuses connections until it receives 1,000 requests.',
      'Web browsers disable DNS lookups whenever network errors occur.',
      'Replication links route client traffic backwards.',
    ],
    correctIndex: 0,
    explanation:
      'DNS relies on distributed caching. Even with low TTLs (e.g. 5 seconds), intermediate recursive resolvers, mobile carrier proxies, and persistent client keep-alive TCP connections continue to send traffic to the old IP until the cache expires or connections close. This is why failover controllers must gracefully handle trailing traffic or use Anycast BGP routing.',
    systemDesignPrinciple: 'DNS Propagation Latency, Cache Invalidation, & Anycast Routing',
  },
];
