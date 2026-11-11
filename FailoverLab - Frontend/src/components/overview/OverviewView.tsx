import React from 'react';
import {
  ArrowRight,
  CheckCircle2,
  Cpu,
  Info,
  Play,
} from 'lucide-react';
import { SCENARIOS } from '../../data/scenarios';
import { useSimulation } from '../../simulation/useSimulation';

interface OverviewViewProps {
  onStartExperiment: () => void;
  onSelectScenario: (scenarioId: string) => void;
}

export const OverviewView: React.FC<OverviewViewProps> = ({
  onStartExperiment,
  onSelectScenario,
}) => {
  const { regionA, regionB, leaseFence, controllerState } = useSimulation();

  const controlPlaneSteps = [
    {
      step: '01',
      title: 'Synthetic Health Probing',
      desc: 'Local and remote observer nodes send UDP/TCP synthetic health probes every 1,000ms to evaluate ingress, database heartbeats, and disk latency.',
      subsystem: 'MONITORING',
    },
    {
      step: '02',
      title: 'Quorum & Anomaly Detection',
      desc: 'When failures persist past the hysteresis threshold (3 consecutive probes), an odd-numbered quorum cluster (2/3 majority) votes to initiate failover.',
      subsystem: 'CONSENSUS',
    },
    {
      step: '03',
      title: 'Lease Revocation & Fencing',
      desc: 'The controller waits for the primary 5-second lease to expire and applies a hard storage barrier (Generation ID check) to strictly avoid split-brain writes.',
      subsystem: 'FENCING',
    },
    {
      step: '04',
      title: 'Standby DB Promotion',
      desc: 'The standby replica in Singapore replays remaining in-transit WAL logs and is promoted to Read-Write Primary with a new monotonic Generation ID (#102).',
      subsystem: 'DATABASE',
    },
    {
      step: '05',
      title: 'DNS / Anycast Traffic Shift',
      desc: 'Global traffic router updates DNS CNAME and health routing. Ingress smoothly shifts 100% of incoming client traffic to Singapore as TTL expires.',
      subsystem: 'ROUTING',
    },
    {
      step: '06',
      title: 'Quarantine & Verification',
      desc: 'Region A is isolated in quarantine to prevent flapping or dual-primary conflicts. Automated verification confirms 0% error rate on Region B.',
      subsystem: 'VERIFICATION',
    },
  ];

  const learningOutcomes = [
    {
      title: 'Split-Brain Mitigation & Generation IDs',
      desc: 'Understand why naive heartbeats cause dual-master write divergence and how monotonically increasing epoch fencing tokens guarantee consistency.',
    },
    {
      title: 'Quorum Mathematics (N/2 + 1)',
      desc: 'Learn why a 2-node cluster cannot perform safe automated failovers and how a 3rd neutral observer breaks network partition ties authoritatively.',
    },
    {
      title: 'RTO & RPO Operational Trade-offs',
      desc: 'Quantify exact downtime (RTO) against potential transactional data loss (RPO) caused by asynchronous cross-region WAL replication queues.',
    },
    {
      title: 'Hysteresis Damping & Anti-Flapping',
      desc: 'Observe sliding-window damping that suppresses transient WAN network jitter and prevents catastrophic cascading thundering-herd failovers.',
    },
  ];

  return (
    <div className="overview-view">
      {/* Hero / Executive Problem Section */}
      <section className="overview-hero">
        <div className="hero-content">
          <div className="badge-tag badge-info mb-3">
            <Cpu size={12} />
            <span>SSD Case Study 23 — System Design Virtual Lab</span>
          </div>
          <h1 className="hero-title">
            Multi-Region Active-Passive Failover Controller
          </h1>
          <p className="hero-statement">
            In multi-region distributed systems, unexpected regional outages, silent network
            partitions, and database degradation require automated failover to a passive
            standby region while strictly avoiding split-brain scenarios.
          </p>
          <p className="hero-statement-secondary">
            FailoverLab simulates an Active-Passive topology between Region A (Mumbai) and
            Region B (Singapore), demonstrating health probing, Raft-style quorum consensus,
            epoch-fenced database promotion, and dynamic DNS traffic routing.
          </p>

          <div className="hero-actions">
            <button
              className="btn-console btn-primary hero-cta-btn"
              onClick={onStartExperiment}
            >
              <Play size={16} />
              <span>Start Experiment in Simulator</span>
              <ArrowRight size={16} />
            </button>

            <div className="hero-stats font-mono">
              <div className="hero-stat-item">
                <span className="stat-label">Topology:</span>
                <span className="stat-val text-flow">Active-Passive (2 Regions)</span>
              </div>
              <div className="hero-stat-item">
                <span className="stat-label">Quorum Cluster:</span>
                <span className="stat-val text-healthy">3 Nodes (2/3 Majority)</span>
              </div>
              <div className="hero-stat-item">
                <span className="stat-label">Fencing:</span>
                <span className="stat-val text-warning">Epoch Generation Tokens</span>
              </div>
            </div>
          </div>
        </div>

        {/* Live Architecture Mini-Preview Card */}
        <div className="hero-preview-card">
          <div className="preview-card-header">
            <div className="font-mono text-xs text-bright font-semibold">
              LIVE TOPOLOGY SNAPSHOT
            </div>
            <div className="badge-tag badge-healthy text-xs font-mono">
              <span className="pulse-dot pulse-healthy" />
              <span>{controllerState}</span>
            </div>
          </div>

          <div className="preview-regions-grid">
            {/* Region A */}
            <div
              className={`preview-region-box ${
                regionA.role === 'ACTIVE'
                  ? 'preview-box-active'
                  : 'preview-box-standby'
              }`}
            >
              <div className="preview-box-title">
                <span className="font-semibold">Region A (Mumbai)</span>
                <span className="badge-tag badge-healthy font-mono text-xs">
                  {regionA.role}
                </span>
              </div>
              <div className="preview-subtext font-mono text-xs text-muted">
                Zone: ap-south-1
              </div>
              <div className="preview-metrics font-mono text-xs">
                <div>Ingress: {regionA.ingressRps.toLocaleString()} RPS</div>
                <div>Status: {regionA.status.toUpperCase()}</div>
                <div>DB Mode: {regionA.role === 'ACTIVE' ? 'READ_WRITE (Epoch 101)' : 'FENCED'}</div>
              </div>
            </div>

            {/* Replication Channel Vector */}
            <div className="preview-replication-vector font-mono text-xs">
              <div className="vector-label">Async WAL Shipping</div>
              <div className="vector-line">
                <div className="vector-pulse" />
              </div>
              <div className="text-secondary text-xs">Lag: ~24ms | 450 Mbps</div>
            </div>

            {/* Region B */}
            <div
              className={`preview-region-box ${
                regionB.role === 'ACTIVE'
                  ? 'preview-box-active'
                  : 'preview-box-standby'
              }`}
            >
              <div className="preview-box-title">
                <span className="font-semibold">Region B (Singapore)</span>
                <span className="badge-tag badge-info font-mono text-xs">
                  {regionB.role}
                </span>
              </div>
              <div className="preview-subtext font-mono text-xs text-muted">
                Zone: ap-southeast-1
              </div>
              <div className="preview-metrics font-mono text-xs">
                <div>Ingress: {regionB.ingressRps.toLocaleString()} RPS</div>
                <div>Status: {regionB.status.toUpperCase()}</div>
                <div>DB Mode: {regionB.role === 'ACTIVE' ? 'READ_WRITE' : 'READ_ONLY REPLICA'}</div>
              </div>
            </div>
          </div>

          <div className="preview-bottom-bar font-mono text-xs">
            <span>Fencing Token: Generation ID #{leaseFence.generationId}</span>
            <span className="text-flow">DNS Target: {regionA.role === 'ACTIVE' ? 'ap-south-1' : 'ap-southeast-1'}</span>
          </div>
        </div>
      </section>

      {/* Control-Plane Intended Sequence */}
      <section className="overview-section">
        <div className="section-header">
          <div className="section-title-group">
            <h2 className="section-title">Automated Control-Plane Failover Sequence</h2>
            <p className="section-subtitle">
              The rigorous 6-step lifecycle executed by the controller during regional degradation
            </p>
          </div>
        </div>

        <div className="sequence-cards-grid">
          {controlPlaneSteps.map((step) => (
            <div key={step.step} className="sequence-card">
              <div className="sequence-card-top">
                <span className="sequence-num font-mono">{step.step}</span>
                <span className="badge-tag badge-info font-mono text-xs">
                  {step.subsystem}
                </span>
              </div>
              <h3 className="sequence-name">{step.title}</h3>
              <p className="sequence-desc">{step.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Learning Objectives & Supported Failure Scenarios */}
      <section className="overview-section">
        <div className="section-header">
          <div className="section-title-group">
            <h2 className="section-title">System Design Learning Objectives</h2>
            <p className="section-subtitle">
              Key concepts validated through interactive simulation and failure injection
            </p>
          </div>
        </div>

        <div className="learning-cards-grid">
          {learningOutcomes.map((item, idx) => (
            <div key={idx} className="learning-card">
              <div className="learning-card-header">
                <CheckCircle2 size={18} className="text-healthy" />
                <h3 className="learning-title">{item.title}</h3>
              </div>
              <p className="learning-desc">{item.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Supported Failure Scenarios Preview */}
      <section className="overview-section">
        <div className="section-header">
          <div className="section-title-group">
            <h2 className="section-title">Supported Failure Scenarios</h2>
            <p className="section-subtitle">
              Pre-configured educational failure models available in the simulator
            </p>
          </div>
        </div>

        <div className="scenarios-preview-grid">
          {SCENARIOS.map((sc) => (
            <div key={sc.id} className="scenario-preview-card">
              <div className="scenario-preview-top">
                <span className="badge-tag badge-warning font-mono text-xs">
                  {sc.category}
                </span>
                <span className="font-mono text-xs text-muted">
                  Difficulty: {sc.difficulty}
                </span>
              </div>
              <h3 className="scenario-preview-title">{sc.title}</h3>
              <p className="scenario-preview-summary">{sc.summary}</p>
              <div className="scenario-preview-footer">
                <div className="font-mono text-xs text-secondary">
                  Target RTO: <span className="text-bright">{sc.expectedRto}</span>
                </div>
                <button
                  className="btn-console text-xs"
                  onClick={() => onSelectScenario(sc.id)}
                >
                  <span>Inspect Scenario</span>
                  <ArrowRight size={12} />
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Academic Disclaimer */}
      <section className="overview-disclaimer">
        <div className="disclaimer-icon">
          <Info size={20} className="text-flow" />
        </div>
        <div className="disclaimer-text">
          <div className="disclaimer-title">Academic Simulation Notice</div>
          <p className="disclaimer-desc">
            FailoverLab is an educational virtual laboratory for System Design and Software Systems
            Development (SSD) Case Study 23. It simulates control plane logic, consensus engines,
            lease fencing, and failure detectors within browser memory and localStorage. No actual
            cloud servers, DNS records, or production databases are provisioned or altered.
          </p>
        </div>
      </section>
    </div>
  );
};
