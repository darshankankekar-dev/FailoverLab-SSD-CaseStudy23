import React, { useState } from 'react';
import {
  Network,
  Database,
  Cpu,
  Shield,
  Clock,
  CheckCircle,
} from 'lucide-react';
import { ArchitectureSvg } from '../simulator/ArchitectureSvg';
import { InspectorPanel } from '../simulator/InspectorPanel';
import { LearningPanel } from './LearningPanel';

export const ArchitectureView: React.FC = () => {
  const [activeSubsystem, setActiveSubsystem] = useState<string>('fencing');

  const subsystems = [
    {
      id: 'fencing',
      title: 'Lease & Fencing Mechanism',
      icon: Shield,
      summary:
        'Prevents split-brain by assigning monotonically increasing Generation IDs (Epoch Tokens) and enforcing hard storage barriers.',
      details: [
        {
          heading: 'Martin Kleppmann Fencing Tokens',
          content:
            'A client or controller that believes it is the primary receives a lease token tagged with a generation number (e.g., Epoch 101). When failover is authorized, the new primary receives Epoch 102. The shared storage layer automatically rejects any transaction carrying an outdated token.',
        },
        {
          heading: 'Lease TTL Expiration Barrier',
          content:
            'The failover coordinator enforces a mandatory waiting period equal to the lease TTL (5 seconds). Even if a node has crashed or partitioned, its lease will guaranteed expire before the standby is permitted to accept writes with the new generation token.',
        },
        {
          heading: 'STONITH (Shoot The Other Node In The Head)',
          content:
            'Where hardware or cloud API fencing is supported, the controller actively powers down or isolates the old primary storage volume to guarantee it cannot write to disk.',
        },
      ],
    },
    {
      id: 'quorum',
      title: 'Quorum & Decision Engine',
      icon: Cpu,
      summary:
        'Uses an odd number of distributed observers (2/3 majority) to break network partition ties authoritatively.',
      details: [
        {
          heading: 'Why 2 Nodes Fail in Partitions',
          content:
            'In a 2-node cluster (Mumbai + Singapore), any severance of the transit link splits the cluster 50/50. Neither node can distinguish between the other node crashing or the network link breaking, leading to deadlock or split-brain.',
        },
        {
          heading: '3-Node Majority Rule (N/2 + 1)',
          content:
            'By introducing an independent 3rd observer in a neutral region (e.g., Zurich), quorum is defined as 2 out of 3 votes. If Mumbai becomes isolated, Singapore and Zurich form a 2-node majority (66.7%), authorizing safe automated promotion.',
        },
        {
          heading: 'Raft / Paxos Heartbeat Consensus',
          content:
            'The decision engine uses Raft-style leader election heartbeats to ensure only one coordinator can execute state transitions at any given time.',
        },
      ],
    },
    {
      id: 'database',
      title: 'Primary & Standby Database Topologies',
      icon: Database,
      summary:
        'PostgreSQL/Aurora streaming replication with asynchronous Write-Ahead Logging (WAL) and promotion safeguards.',
      details: [
        {
          heading: 'Asynchronous WAL Shipping',
          content:
            'Transactions are committed locally in Mumbai with 18ms latency. WAL delta records are continuously streamed across the WAN to Singapore. Under nominal conditions, replication lag hovers around 20-30ms.',
        },
        {
          heading: 'Replication Catch-Up Phase',
          content:
            'Before the standby assumes the Primary role, the controller allows the replica to replay any buffered WAL segments already received across the wire to minimize RPO transactional loss.',
        },
        {
          heading: 'Storage Fencing Verification',
          content:
            'During promotion, the storage volume in Singapore transitions from READ_ONLY to READ_WRITE, while the Mumbai volume is demoted and isolated in quarantine.',
        },
      ],
    },
    {
      id: 'traffic',
      title: 'Global DNS & Traffic Routing',
      icon: Network,
      summary:
        'Low-TTL CNAME resolution paired with Anycast health checking to redirect client ingress dynamically.',
      details: [
        {
          heading: 'Low-TTL DNS CNAMEs',
          content:
            'The public domain entrypoint (e.g. api.failoverlab.internal) points to a canonical name with a 5-second TTL. Upon failover, the DNS provider updates the CNAME target from ap-south-1 to ap-southeast-1.',
        },
        {
          heading: 'DNS Cache Propagation Lag',
          content:
            'Client web browsers and recursive DNS resolvers cache records for the TTL window. During the 5-10 second propagation phase, traffic splits between both regions, necessitating graceful HTTP 503 retry headers or Anycast BGP route shifting.',
        },
        {
          heading: 'Health-Check Probing Frequency',
          content:
            'Global route resolvers ping region ingress points every 1,000ms. An automated failover route is triggered if 3 consecutive synthetic probes time out.',
        },
      ],
    },
    {
      id: 'hysteresis',
      title: 'Hysteresis & Anti-Flapping Damping',
      icon: Clock,
      summary:
        'Sliding-window thresholding that prevents destructive rapid ping-pong failovers during transient WAN jitter.',
      details: [
        {
          heading: 'The Flapping Hazard',
          content:
            'Internet transit providers frequently drop packets for 1-2 seconds before recovering. If a failover controller acts instantly on a single dropped probe, it triggers an expensive database promotion and DNS change.',
        },
        {
          heading: 'Consecutive Probe Windows',
          content:
            'FailoverLab requires 3 consecutive failed probes before quorum voting begins. If a probe succeeds during this window, the failure counter resets to 0.',
        },
        {
          heading: 'Cooldown Quarantining',
          content:
            'Once failover to Region B completes, Region A is placed in a mandatory 15-minute quarantine even if it appears to recover, preventing thundering-herd switchbacks until verified by an operator.',
        },
      ],
    },
  ];

  const currentSubsystem =
    subsystems.find((s) => s.id === activeSubsystem) || subsystems[0];

  return (
    <div className="architecture-view">
      <div className="section-header">
        <div className="section-title-group">
          <div className="badge-tag badge-info mb-2 font-mono text-xs">
            System Design Specification
          </div>
          <h1 className="section-title">
            Multi-Region Failover Architecture & Subsystems
          </h1>
          <p className="section-subtitle">
            Deep architectural breakdown of consensus, storage fencing, replication mechanics, and
            the state transition lifecycle.
          </p>
        </div>
      </div>

      {/* Interactive System Topology Diagram */}
      <div className="architecture-diagram-section mb-5">
        <div className="section-title-group mb-3">
          <div className="badge-tag badge-healthy font-mono text-xs">
            Interactive Architecture Topology
          </div>
          <h2 className="section-title">
            System Topology & Component Interconnections
          </h2>
          <p className="section-subtitle">
            Live interactive SVG topology reflecting simulated health, consensus quorum, fencing states, and cross-region WAL replication. Select any component to inspect its role, policies, and failure modes.
          </p>
        </div>

        <div className="architecture-diagram-grid">
          <div className="arch-diagram-canvas-col">
            <ArchitectureSvg />
          </div>
          <div className="arch-diagram-inspector-col">
            <InspectorPanel />
          </div>
        </div>
      </div>

      {/* Subsystem Navigation Tabs */}
      <div className="subsystem-nav-bar">
        {subsystems.map((sub) => {
          const Icon = sub.icon;
          const isActive = sub.id === activeSubsystem;
          return (
            <button
              key={sub.id}
              className={`subsystem-tab-btn ${isActive ? 'subsystem-tab-active' : ''}`}
              onClick={() => setActiveSubsystem(sub.id)}
            >
              <Icon size={16} />
              <span>{sub.title}</span>
            </button>
          );
        })}
      </div>

      {/* Subsystem Deep-Dive Body */}
      <div className="subsystem-detail-card">
        <div className="subsystem-card-top">
          <div className="subsystem-title-row">
            <h2 className="subsystem-heading">{currentSubsystem.title}</h2>
            <span className="badge-tag badge-healthy font-mono text-xs">
              CORE SUBSYSTEM
            </span>
          </div>
          <p className="subsystem-lead text-secondary">{currentSubsystem.summary}</p>
        </div>

        <div className="subsystem-breakdown-grid">
          {currentSubsystem.details.map((detail, idx) => (
            <div key={idx} className="subsystem-breakdown-box">
              <div className="breakdown-box-header">
                <CheckCircle size={15} className="text-flow" />
                <h3 className="breakdown-box-title">{detail.heading}</h3>
              </div>
              <p className="breakdown-box-content text-xs text-secondary">
                {detail.content}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* Educational Concept Guide */}
      <div className="architecture-learning-section mt-5">
        <LearningPanel />
      </div>

      {/* Failover Lifecycle Sequence Flow */}
      <div className="architecture-lifecycle-section mt-5">
        <div className="section-title-group mb-3">
          <h2 className="section-title">Automated Failover State Transition Matrix</h2>
          <p className="section-subtitle">
            Formal state machine transitions executed by the Failover Orchestrator
          </p>
        </div>

        <div className="state-matrix-table-wrapper">
          <table className="state-matrix-table font-mono text-xs">
            <thead>
              <tr>
                <th>Current State</th>
                <th>Trigger Event</th>
                <th>Guard / Safety Condition</th>
                <th>Target State</th>
                <th>Action Executed</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="text-healthy">HEALTHY</td>
                <td>Synthetic Probe Failure (1/3)</td>
                <td>Consecutive failures &lt; 3</td>
                <td className="text-warning">PRIMARY_SUSPECTED</td>
                <td>Mark suspected; hold in debounce window to filter jitter</td>
              </tr>
              <tr>
                <td className="text-warning">PRIMARY_SUSPECTED</td>
                <td>Probe Restored Before Threshold</td>
                <td>Probe succeeds before 3 failures</td>
                <td className="text-healthy">HEALTHY</td>
                <td>False-positive suppressed; reset counter without failover</td>
              </tr>
              <tr>
                <td className="text-warning">PRIMARY_SUSPECTED</td>
                <td>Failure Threshold Met (3/3)</td>
                <td>Consecutive failures &gt;= 3</td>
                <td className="text-warning">QUORUM_CHECK</td>
                <td>Query 3 independent simulated observers</td>
              </tr>
              <tr>
                <td className="text-warning">QUORUM_CHECK</td>
                <td>Gate Check (Quorum / Lag / Standby)</td>
                <td>Quorum &lt; 2 or Lag &gt; 5s or Standby down</td>
                <td className="text-danger">FAILOVER_BLOCKED</td>
                <td>Block transition with explicit human-readable reason</td>
              </tr>
              <tr>
                <td className="text-warning">QUORUM_CHECK</td>
                <td>All Safety Gates Pass</td>
                <td>Majority &gt;= 2, Standby healthy, Lag &lt;= 5s</td>
                <td className="text-danger">FENCING_PRIMARY</td>
                <td>Revoke primary write authority; advance fencing epoch</td>
              </tr>
              <tr>
                <td className="text-danger">FENCING_PRIMARY</td>
                <td>Fencing Confirmed</td>
                <td>Region A acceptsWrites == false &amp; isFenced</td>
                <td className="text-flow">PROMOTING_STANDBY</td>
                <td>Authorize promotion of Region B with Epoch #102</td>
              </tr>
              <tr>
                <td className="text-flow">PROMOTING_STANDBY</td>
                <td>Dual-Primary Invariant Verified</td>
                <td>!(RegionA.writes &amp;&amp; RegionB.writes)</td>
                <td className="text-flow">ROUTE_UPDATING</td>
                <td>Promote Region B to ACTIVE; begin DNS cutover</td>
              </tr>
              <tr>
                <td className="text-flow">ROUTE_UPDATING</td>
                <td>DNS Propagation Reaches 100%</td>
                <td>Propagation percent == 100%</td>
                <td className="text-flow">VERIFYING_ROUTE</td>
                <td>Send simulated synthetic test request to Region B</td>
              </tr>
              <tr>
                <td className="text-flow">VERIFYING_ROUTE</td>
                <td>Route Verification Probe Verified</td>
                <td>Test request resolves successfully</td>
                <td className="text-healthy">SECONDARY_ACTIVE</td>
                <td>Failover complete; Region B actively serving 100% traffic</td>
              </tr>
              <tr>
                <td className="text-healthy">SECONDARY_ACTIVE</td>
                <td>Primary Restored Online</td>
                <td>Region A health == HEALTHY</td>
                <td className="text-flow">PRIMARY_RECOVERING</td>
                <td>Keep Region A in STANDBY; initiate reverse replication sync</td>
              </tr>
              <tr>
                <td className="text-flow">PRIMARY_RECOVERING</td>
                <td>Reverse Replication Reconciled</td>
                <td>Reverse WAL lag &lt;= policy limit</td>
                <td className="text-warning">FAILBACK_PENDING</td>
                <td>Readiness confirmed; await deliberate manual operator command</td>
              </tr>
              <tr>
                <td className="text-warning">FAILBACK_PENDING</td>
                <td>Manual Failback Authorized</td>
                <td>Operator triggers controlled switchback</td>
                <td className="text-flow">FAILBACK_IN_PROGRESS</td>
                <td>Fence Region B, promote Region A, repoint DNS, return to HEALTHY</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
