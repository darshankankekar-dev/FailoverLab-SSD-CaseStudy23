import React from 'react';
import {
  X,
  BookOpen,
  ShieldAlert,
  Cpu,
  Network,
  GitBranch,
  Clock,
  Database,
} from 'lucide-react';

interface MethodologyModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const MethodologyModal: React.FC<MethodologyModalProps> = ({
  isOpen,
  onClose,
}) => {
  if (!isOpen) return null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal-container"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="methodology-title"
      >
        <div className="modal-header">
          <div className="modal-header-left">
            <BookOpen className="text-flow" size={20} />
            <div>
              <h2 id="methodology-title" className="modal-title">
                Academic Methodology & System Design Reference
              </h2>
              <p className="modal-subtitle">
                Software Systems Development (SSD) — Case Study 23: Multi-Region
                Active-Passive Failover Controller
              </p>
            </div>
          </div>
          <button
            className="btn-console modal-close-btn"
            onClick={onClose}
            aria-label="Close modal"
          >
            <X size={16} />
          </button>
        </div>

        <div className="modal-body">
          <div className="methodology-grid">
            {/* Section 1: The Core Problem */}
            <div className="methodology-card">
              <div className="card-header-icon">
                <ShieldAlert size={18} className="text-danger" />
                <h3>1. The Split-Brain Disaster in Active-Passive</h3>
              </div>
              <p className="text-sm text-secondary">
                In an active-passive multi-region architecture, if Region A
                becomes partitioned from Region B across WAN transit, both
                regions might independently believe the other region has crashed.
              </p>
              <div className="methodology-code-box font-mono text-xs">
                <div>[WAN Partition]</div>
                <div>Region A (Mumbai)    ---x--- Region B (Singapore)</div>
                <div>[Believes it is alive]        [Promotes itself to Primary]</div>
                <div className="text-danger mt-1">
                  CRITICAL HAZARD: Dual-master writes result in irreconcilable
                  divergent database state.
                </div>
              </div>
              <p className="text-xs text-muted mt-2">
                FailoverLab demonstrates why naive ping-based failover is dangerous
                without distributed locking and strict fencing tokens.
              </p>
            </div>

            {/* Section 2: Fencing Tokens & Generation IDs */}
            <div className="methodology-card">
              <div className="card-header-icon">
                <Database size={18} className="text-healthy" />
                <h3>2. Epoch Generation Tokens (Kleppmann Fencing)</h3>
              </div>
              <p className="text-sm text-secondary">
                To guarantee safety, every promotion issues a monotonically
                increasing <strong>Generation ID / Epoch Token</strong> (e.g.,
                Epoch 101 → 102).
              </p>
              <ul className="methodology-list text-xs text-secondary mt-2">
                <li>
                  <strong>Lease Expiration:</strong> The primary holds a renewable
                  lease (5s TTL). If unrenewed, the lease expires.
                </li>
                <li>
                  <strong>Storage Validation:</strong> Underlying storage rejects any
                  write tagged with an outdated Epoch number.
                </li>
                <li>
                  <strong>STONITH / Hard Fence:</strong> The old primary node is
                  forcibly fenced or set to Read-Only before the secondary starts
                  accepting writes.
                </li>
              </ul>
            </div>

            {/* Section 3: Quorum Mathematics */}
            <div className="methodology-card">
              <div className="card-header-icon">
                <Cpu size={18} className="text-flow" />
                <h3>3. Majority Quorum Mathematics (N/2 + 1)</h3>
              </div>
              <p className="text-sm text-secondary">
                Automated failover decisions must never rely on a 2-node consensus
                because a single partition yields a 50/50 tie.
              </p>
              <div className="math-callout font-mono text-xs">
                <div>Total Observers (N) = 3</div>
                <div>Quorum Majority = floor(3/2) + 1 = 2 votes</div>
                <div className="text-healthy mt-1">
                  ✓ Mumbai (ap-south-1)
                  <br />
                  ✓ Singapore (ap-southeast-1)
                  <br />
                  ✓ Zurich Neutral Tiebreaker (eu-central-1)
                </div>
              </div>
              <p className="text-xs text-muted mt-2">
                If Mumbai is severed, Singapore and Zurich form the 2-vote
                majority, authorizing safe automated promotion.
              </p>
            </div>

            {/* Section 4: RTO vs RPO Metrics */}
            <div className="methodology-card">
              <div className="card-header-icon">
                <Clock size={18} className="text-warning" />
                <h3>4. RTO and RPO Trade-Off Dynamics</h3>
              </div>
              <div className="metric-compare-grid">
                <div className="metric-compare-box">
                  <div className="font-mono text-xs text-flow">RTO (Recovery Time)</div>
                  <div className="text-xs text-secondary mt-1">
                    Duration of outage between initial crash and full traffic
                    stabilization on Region B.
                  </div>
                  <div className="font-mono text-xs text-bright mt-2">
                    RTO = Probe + Lease TTL + Standby Promote + DNS TTL
                  </div>
                </div>
                <div className="metric-compare-box">
                  <div className="font-mono text-xs text-warning">RPO (Recovery Point)</div>
                  <div className="text-xs text-secondary mt-1">
                    Maximum data loss caused by replication lag in asynchronous WAL
                    shipping.
                  </div>
                  <div className="font-mono text-xs text-bright mt-2">
                    RPO Loss = Lag (sec) × Ingress Write Rate
                  </div>
                </div>
              </div>
            </div>

            {/* Section 5: Hysteresis Window */}
            <div className="methodology-card">
              <div className="card-header-icon">
                <Network size={18} className="text-flow" />
                <h3>5. Flapping Suppression via Hysteresis</h3>
              </div>
              <p className="text-sm text-secondary">
                Public WAN internet transit frequently experiences transient
                jitter (e.g. 500ms packet bursts).
              </p>
              <p className="text-xs text-secondary mt-2">
                A sliding hysteresis window (e.g. 3 consecutive failed probes over
                4 seconds) prevents destructive ping-pong failovers, preserving
                cache warmth and database connection pools.
              </p>
            </div>

            {/* Section 6: DNS Propagation Latency */}
            <div className="methodology-card">
              <div className="card-header-icon">
                <GitBranch size={18} className="text-bright" />
                <h3>6. DNS Routing vs Anycast BGP</h3>
              </div>
              <p className="text-sm text-secondary">
                Even with a 5-second DNS TTL, intermediate recursive resolvers and
                browsers cache IP addresses.
              </p>
              <p className="text-xs text-secondary mt-2">
                Failover controllers simulate the gradual traffic shift as DNS
                caches expire globally, illustrating why read-only maintenance
                pages or Anycast BGP route withdrawal are often paired with DNS.
              </p>
            </div>
          </div>

          <div className="methodology-footer-callout">
            <div className="text-xs text-muted">
              <strong>Academic Citation:</strong> Kleppmann, M. (2017).{' '}
              <em>Designing Data-Intensive Applications</em> (Ch. 5 & 8: Replication,
              Fencing Tokens, and Consensus). O'Reilly Media.
            </div>
            <button className="btn-console btn-primary text-xs" onClick={onClose}>
              Got It, Return to Console
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
