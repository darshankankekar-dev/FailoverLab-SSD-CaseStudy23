import React from 'react';
import {
  Activity,
  Network,
  Shield,
  Radio,
  Clock,
  AlertTriangle,
  CheckCircle,
  Flame,
  ArrowRight,
  RefreshCw,
} from 'lucide-react';
import { useSimulation } from '../../simulation/useSimulation';

export const InspectorPanel: React.FC = () => {
  const {
    selectedComponent,
    regionA,
    regionB,
    primaryDb,
    standbyDb,
    dns,
    leaseFence,
    replication,
    quorum,
    telemetry,
    controllerState,
    config,
    consecutiveFailures,
    eventHistory,
    isSequenceInProgress,
    engine,
  } = useSimulation();

  const isAOutage = regionA.status === 'failed' || regionA.health === 'DOWN';
  const isASuspected = controllerState === 'PRIMARY_SUSPECTED';
  const isAFenced = regionA.isFenced;

  const renderComponentDetails = () => {
    switch (selectedComponent) {
      case 'CLIENTS':
        return (
          <div className="inspector-content">
            <div className="inspector-top-meta">
              <div className="badge-tag badge-info font-mono text-xs">GLOBAL TIER</div>
              <span className="font-mono text-xs text-muted">Edge Clients</span>
            </div>
            <h3 className="inspector-component-title">Client / Traffic Generator</h3>
            <p className="inspector-desc text-xs text-secondary">
              Simulates global end-user application traffic hitting public API endpoints. Measures client-perceived
              availability, p95 latency, and dropped requests during cutovers.
            </p>
            <div className="inspector-metric-grid">
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Purpose</span>
                <span className="metric-value font-mono text-bright text-xs">Ingress Traffic Generation</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Simulated Health</span>
                <span className="metric-value font-mono text-healthy text-xs">HEALTHY (100% Load)</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Role</span>
                <span className="metric-value font-mono text-flow text-xs">Synthetic Traffic Producer</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Total Ingress</span>
                <span className="metric-value font-mono text-bright">{telemetry.totalClientRps.toLocaleString()} RPS</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Client Success Rate</span>
                <span className={`metric-value font-mono ${telemetry.overallSuccessRate > 95 ? 'text-healthy' : 'text-danger'}`}>
                  {telemetry.overallSuccessRate}%
                </span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">p95 Client RTT</span>
                <span className="metric-value font-mono text-bright">{telemetry.p95LatencyMs}ms</span>
              </div>
            </div>
            <div className="system-design-note">
              <div className="note-title font-mono text-xs text-flow">
                <Network size={12} />
                <span>Client Retry Storm Hazard</span>
              </div>
              <p className="text-xs text-muted mt-1">
                When the primary crashes, client timeouts cause automated retry bursts. Exponential backoff and circuit
                breakers prevent thundering herd on the newly promoted standby.
              </p>
            </div>
          </div>
        );

      case 'DNS':
        return (
          <div className="inspector-content">
            <div className="inspector-top-meta">
              <div className={`badge-tag ${dns.resolutionStatus === 'NOMINAL' ? 'badge-healthy' : 'badge-warning'} font-mono text-xs`}>
                {dns.resolutionStatus}
              </div>
              <span className="font-mono text-xs text-muted">Global Anycast</span>
            </div>
            <h3 className="inspector-component-title">DNS / Traffic Router</h3>
            <p className="inspector-desc text-xs text-secondary">
              Directs client requests worldwide using low-TTL CNAME records. During failover, updates target from Mumbai to Singapore.
            </p>
            <div className="inspector-metric-grid">
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Purpose</span>
                <span className="metric-value font-mono text-bright text-xs">Global Ingress Routing</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Simulated Health</span>
                <span className={`metric-value font-mono text-xs ${dns.resolutionStatus === 'NOMINAL' ? 'text-healthy' : 'text-warning'}`}>
                  {dns.resolutionStatus}
                </span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Active Target</span>
                <span className="metric-value font-mono text-flow text-xs">
                  {dns.activeDnsTarget === 'region-a' ? 'Region A (Mumbai)' : 'Region B (Singapore)'}
                </span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Configured TTL</span>
                <span className="metric-value font-mono text-bright">{dns.ttlSeconds}s (Low-TTL Policy)</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">DNS Propagation</span>
                <span className="metric-value font-mono text-bright">{dns.propagationProgress}%</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Routing Policy</span>
                <span className="metric-value font-mono text-bright text-xs">ACTIVE_PASSIVE_CNAME</span>
              </div>
            </div>
            <div className="system-design-note">
              <div className="note-title font-mono text-xs text-flow">
                <Network size={12} />
                <span>DNS Cache Reality</span>
              </div>
              <p className="text-xs text-muted mt-1">
                Recursive resolvers may cache records beyond TTL. Clients with cached A-records continue hitting the old IP until local TTL expiration.
              </p>
            </div>
            <div className="inspector-actions-section">
              <label className="section-label font-mono">ROUTER ACTIONS</label>
              <div className="action-buttons-stack">
                <button
                  className="btn-console btn-warning text-xs"
                  onClick={() => engine.injectRouteFailure()}
                  disabled={dns.resolutionStatus === 'FAILED'}
                >
                  <AlertTriangle size={13} />
                  <span>Simulate Route Propagation Failure</span>
                </button>
                <button
                  className="btn-console text-xs"
                  onClick={() => engine.restoreRouteHealth()}
                >
                  <RefreshCw size={13} />
                  <span>Restore Router Health</span>
                </button>
              </div>
            </div>
          </div>
        );

      case 'REGION_A':
        return (
          <div className="inspector-content">
            <div className="inspector-top-meta">
              <div className={`badge-tag ${regionA.role === 'ACTIVE' ? 'badge-healthy' : 'badge-danger'} font-mono text-xs`}>
                {regionA.role}
              </div>
              <span className="font-mono text-xs text-muted">ap-south-1 (Mumbai)</span>
            </div>
            <h3 className="inspector-component-title">Region A Container — Mumbai</h3>
            <p className="inspector-desc text-xs text-secondary">
              Primary cloud facility hosting active API microservices, primary storage instance, and local synthetic health agents.
            </p>
            <div className="inspector-metric-grid">
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Purpose</span>
                <span className="metric-value font-mono text-bright text-xs">Primary Deployment Zone</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Simulated Health</span>
                <span className={`metric-value font-mono text-xs ${regionA.health === 'HEALTHY' ? 'text-healthy' : 'text-danger'}`}>
                  {regionA.health}
                </span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Role</span>
                <span className="metric-value font-mono text-flow text-xs">{regionA.role}</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Accepts Writes</span>
                <span className={`metric-value font-mono text-xs ${regionA.acceptsWrites ? 'text-healthy' : 'text-danger'}`}>
                  {regionA.acceptsWrites ? 'TRUE (Active Writer)' : 'FALSE (Revoked)'}
                </span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Fencing Epoch</span>
                <span className="metric-value font-mono text-bright">#{regionA.fencingEpoch}</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Fenced State</span>
                <span className={`metric-value font-mono text-xs ${regionA.isFenced ? 'text-danger' : 'text-healthy'}`}>
                  {regionA.isFenced ? 'HARD FENCED' : 'UNFENCED'}
                </span>
              </div>
            </div>
            <div className="inspector-actions-section">
              <label className="section-label font-mono">REGIONAL ACTIONS</label>
              <div className="action-buttons-stack">
                <button
                  className="btn-console btn-danger text-xs"
                  onClick={() => engine.injectPrimaryOutage()}
                  disabled={regionA.status === 'failed'}
                >
                  <Flame size={13} />
                  <span>Inject Complete Mumbai Outage</span>
                </button>
                <button
                  className="btn-console text-xs"
                  onClick={() => engine.recoverPrimary()}
                  disabled={regionA.status === 'healthy'}
                >
                  <RefreshCw size={13} />
                  <span>Recover Mumbai Region</span>
                </button>
              </div>
            </div>
          </div>
        );

      case 'REGION_A_APP':
        return (
          <div className="inspector-content">
            <div className="inspector-top-meta">
              <div className={`badge-tag ${regionA.appServersHealthy > 0 ? 'badge-healthy' : 'badge-danger'} font-mono text-xs`}>
                {regionA.appServersHealthy > 0 ? 'RUNNING' : 'OFFLINE'}
              </div>
              <span className="font-mono text-xs text-muted">Mumbai Ingress Pool</span>
            </div>
            <h3 className="inspector-component-title">Application Service (Region A)</h3>
            <p className="inspector-desc text-xs text-secondary">
              Stateless Kubernetes/container compute pool handling HTTP/gRPC ingress, user authentication, and business logic.
            </p>
            <div className="inspector-metric-grid">
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Purpose</span>
                <span className="metric-value font-mono text-bright text-xs">Stateless API Processing</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Simulated Health</span>
                <span className={`metric-value font-mono text-xs ${regionA.status === 'failed' ? 'text-danger' : 'text-healthy'}`}>
                  {regionA.status === 'failed' ? 'OFFLINE' : 'HEALTHY'}
                </span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Healthy Nodes</span>
                <span className="metric-value font-mono text-bright">{regionA.appServersHealthy} / {regionA.appServersTotal} Nodes</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Current Ingress</span>
                <span className="metric-value font-mono text-bright">{regionA.ingressRps.toLocaleString()} RPS</span>
              </div>
            </div>
          </div>
        );

      case 'REGION_A_HEALTH':
        return (
          <div className="inspector-content">
            <div className="inspector-top-meta">
              <div className={`badge-tag ${consecutiveFailures > 0 ? 'badge-warning' : 'badge-healthy'} font-mono text-xs`}>
                {consecutiveFailures > 0 ? `FAILED (${consecutiveFailures}/3)` : 'HEARTBEAT OK'}
              </div>
              <span className="font-mono text-xs text-muted">Local Probe</span>
            </div>
            <h3 className="inspector-component-title">Health Agent (Region A)</h3>
            <p className="inspector-desc text-xs text-secondary">
              Synthetic health probe daemon executing health checks against local APIs and databases, streaming heartbeats to the Failover Controller.
            </p>
            <div className="inspector-metric-grid">
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Purpose</span>
                <span className="metric-value font-mono text-bright text-xs">Synthetic Heartbeat Probing</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Simulated Health</span>
                <span className={`metric-value font-mono text-xs ${regionA.status === 'failed' ? 'text-danger' : 'text-healthy'}`}>
                  {regionA.status === 'failed' ? 'TIMEOUT / FAILED' : 'HEALTHY'}
                </span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Consecutive Fails</span>
                <span className="metric-value font-mono text-bright">{consecutiveFailures} / {config.failureThresholdConsecutive} Probes</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Probe Interval</span>
                <span className="metric-value font-mono text-bright">{config.healthCheckIntervalSec}s (Simulated)</span>
              </div>
            </div>
          </div>
        );

      case 'PRIMARY_DB':
      case 'REGION_A_DB':
        return (
          <div className="inspector-content">
            <div className="inspector-top-meta">
              <div className={`badge-tag ${regionA.acceptsWrites ? 'badge-healthy' : isAFenced ? 'badge-danger' : 'badge-warning'} font-mono text-xs`}>
                {primaryDb.accessMode}
              </div>
              <span className="font-mono text-xs text-muted">ap-south-1 (Mumbai)</span>
            </div>
            <h3 className="inspector-component-title">Primary Database (Storage Engine)</h3>
            <p className="inspector-desc text-xs text-secondary">
              Relational PostgreSQL/Aurora primary instance managing read-write transactions. Holds the active write lease secured by Epoch #{primaryDb.generationId}.
            </p>
            <div className="inspector-metric-grid">
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Purpose</span>
                <span className="metric-value font-mono text-bright text-xs">Transactional Read-Write Storage</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Simulated Health</span>
                <span className={`metric-value font-mono text-xs ${isAOutage ? 'text-danger' : isASuspected ? 'text-warning' : 'text-healthy'}`}>
                  {isAOutage ? 'CRASHED / OFFLINE' : isASuspected ? 'SUSPECTED' : 'HEALTHY'}
                </span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Access Mode</span>
                <span className={`metric-value font-mono ${primaryDb.accessMode === 'READ_WRITE' ? 'text-healthy' : 'text-danger'}`}>
                  {primaryDb.accessMode}
                </span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Generation Epoch</span>
                <span className="metric-value font-mono text-flow">#{primaryDb.generationId}</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Current IOPS</span>
                <span className="metric-value font-mono text-bright">{primaryDb.iops.toLocaleString()}</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Storage Used</span>
                <span className="metric-value font-mono text-bright">{primaryDb.storageGb} GB</span>
              </div>
            </div>
            <div className="system-design-note">
              <div className="note-title font-mono text-xs text-warning">
                <AlertTriangle size={12} />
                <span>Split-Brain Prevention Invariant</span>
              </div>
              <p className="text-xs text-muted mt-1">
                CRITICAL INVARIANT: The database driver must reject writes if its lease expires or if incoming transactions carry an outdated Epoch token &lt; #{leaseFence.generationId}.
              </p>
            </div>
            <div className="inspector-actions-section">
              <label className="section-label font-mono">NODE ACTIONS</label>
              <div className="action-buttons-stack">
                <button
                  className="btn-console btn-danger text-xs"
                  onClick={() => engine.injectPrimaryOutage()}
                  disabled={isAOutage}
                >
                  <Flame size={13} />
                  <span>Crash Database Instance</span>
                </button>
                <button
                  className="btn-console text-xs"
                  onClick={() => engine.recoverPrimary()}
                  disabled={!isAOutage}
                >
                  <RefreshCw size={13} />
                  <span>Recover Database Process</span>
                </button>
              </div>
            </div>
          </div>
        );

      case 'REGION_B':
        return (
          <div className="inspector-content">
            <div className="inspector-top-meta">
              <div className={`badge-tag ${regionB.role === 'ACTIVE' ? 'badge-healthy' : 'badge-info'} font-mono text-xs`}>
                {regionB.role}
              </div>
              <span className="font-mono text-xs text-muted">ap-southeast-1 (Singapore)</span>
            </div>
            <h3 className="inspector-component-title">Region B Container — Singapore</h3>
            <p className="inspector-desc text-xs text-secondary">
              Secondary disaster-recovery facility. Holds warm standby app compute and an asynchronous read replica ready for promotion.
            </p>
            <div className="inspector-metric-grid">
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Purpose</span>
                <span className="metric-value font-mono text-bright text-xs">Standby & Failover Target</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Simulated Health</span>
                <span className="metric-value font-mono text-healthy text-xs">{regionB.health}</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Role</span>
                <span className="metric-value font-mono text-flow text-xs">{regionB.role}</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Accepts Writes</span>
                <span className={`metric-value font-mono text-xs ${regionB.acceptsWrites ? 'text-healthy' : 'text-flow'}`}>
                  {regionB.acceptsWrites ? 'TRUE (Promoted Writer)' : 'FALSE (Standby)'}
                </span>
              </div>
            </div>
          </div>
        );

      case 'REGION_B_APP':
        return (
          <div className="inspector-content">
            <div className="inspector-top-meta">
              <div className={`badge-tag ${regionB.role === 'ACTIVE' ? 'badge-healthy' : 'badge-info'} font-mono text-xs`}>
                {regionB.role === 'ACTIVE' ? 'ACTIVE' : 'STANDBY'}
              </div>
              <span className="font-mono text-xs text-muted">Singapore Compute Pool</span>
            </div>
            <h3 className="inspector-component-title">Standby Application Service (Region B)</h3>
            <p className="inspector-desc text-xs text-secondary">
              Pre-warmed compute cluster configured to scale up and accept client traffic the moment DNS cutover points to Singapore.
            </p>
            <div className="inspector-metric-grid">
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Purpose</span>
                <span className="metric-value font-mono text-bright text-xs">Failover Target Compute</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Simulated Health</span>
                <span className="metric-value font-mono text-healthy text-xs">HEALTHY</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Ingress RPS</span>
                <span className="metric-value font-mono text-bright">{regionB.ingressRps.toLocaleString()} RPS</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Pool Nodes</span>
                <span className="metric-value font-mono text-bright">{regionB.appServersHealthy} / {regionB.appServersTotal} Nodes</span>
              </div>
            </div>
          </div>
        );

      case 'REGION_B_HEALTH':
        return (
          <div className="inspector-content">
            <div className="inspector-top-meta">
              <div className="badge-tag badge-healthy font-mono text-xs">HEARTBEAT OK</div>
              <span className="font-mono text-xs text-muted">Singapore Probe</span>
            </div>
            <h3 className="inspector-component-title">Health Agent (Region B)</h3>
            <p className="inspector-desc text-xs text-secondary">
              Verifies standby readiness, WAL receiver status, and API health, reporting metrics to the Quorum and Decision Engine.
            </p>
            <div className="inspector-metric-grid">
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Purpose</span>
                <span className="metric-value font-mono text-bright text-xs">Standby Readiness Verification</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Simulated Health</span>
                <span className="metric-value font-mono text-healthy text-xs">HEALTHY (32ms WAN)</span>
              </div>
            </div>
            <div className="inspector-actions-section">
              <label className="section-label font-mono">STANDBY READINESS ACTIONS</label>
              <div className="action-buttons-stack">
                <button
                  className="btn-console btn-warning text-xs"
                  onClick={() => engine.injectStandbyUnready()}
                  disabled={regionB.health !== 'HEALTHY'}
                >
                  <AlertTriangle size={13} />
                  <span>Break Standby Readiness (Safety Gate Test)</span>
                </button>
                <button
                  className="btn-console text-xs"
                  onClick={() => engine.restoreStandbyReadiness()}
                  disabled={regionB.health === 'HEALTHY'}
                >
                  <RefreshCw size={13} />
                  <span>Restore Standby Readiness</span>
                </button>
              </div>
            </div>
          </div>
        );

      case 'STANDBY_DB':
      case 'REGION_B_DB':
        return (
          <div className="inspector-content">
            <div className="inspector-top-meta">
              <div className={`badge-tag ${standbyDb.role === 'PRIMARY' ? 'badge-healthy' : 'badge-info'} font-mono text-xs`}>
                {standbyDb.role}
              </div>
              <span className="font-mono text-xs text-muted">ap-southeast-1 (Singapore)</span>
            </div>
            <h3 className="inspector-component-title">
              {standbyDb.role === 'PRIMARY' ? 'Promoted Primary Database' : 'Standby Read Replica'}
            </h3>
            <p className="inspector-desc text-xs text-secondary">
              Cross-region replica continuously tailing the asynchronous Write-Ahead Log (WAL) stream. Authoritatively promoted upon fencing token receipt.
            </p>
            <div className="inspector-metric-grid">
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Purpose</span>
                <span className="metric-value font-mono text-bright text-xs">Disaster Recovery Storage</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Simulated Health</span>
                <span className="metric-value font-mono text-healthy text-xs">{standbyDb.status.toUpperCase()}</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Access Mode</span>
                <span className={`metric-value font-mono ${standbyDb.accessMode === 'READ_WRITE' ? 'text-healthy' : 'text-flow'}`}>
                  {standbyDb.accessMode}
                </span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Replication Lag</span>
                <span className={`metric-value font-mono ${replication.lagSeconds > config.acceptableReplicationLagSec ? 'text-warning' : 'text-healthy'}`}>
                  {replication.lagSeconds.toFixed(1)}s ({Math.round(replication.lagSeconds * 1000)}ms)
                </span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Assigned Epoch</span>
                <span className="metric-value font-mono text-bright">#{standbyDb.generationId}</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Storage Alloc</span>
                <span className="metric-value font-mono text-bright">{standbyDb.storageGb} GB</span>
              </div>
            </div>
            <div className="system-design-note">
              <div className="note-title font-mono text-xs text-healthy">
                <CheckCircle size={12} />
                <span>Safe Promotion Barrier</span>
              </div>
              <p className="text-xs text-muted mt-1">
                Promotion advances the generation ID to #{leaseFence.generationId + (standbyDb.role === 'STANDBY' ? 1 : 0)}. Trailing packets from old primary with older epochs are discarded at storage driver.
              </p>
            </div>
          </div>
        );

      case 'REPLICATION_LINK':
      case 'REPLICATION':
        return (
          <div className="inspector-content">
            <div className="inspector-top-meta">
              <div className={`badge-tag ${replication.status === 'STREAMING' ? 'badge-healthy' : 'badge-danger'} font-mono text-xs`}>
                {replication.status}
              </div>
              <span className="font-mono text-xs text-muted">Trans-Oceanic WAN</span>
            </div>
            <h3 className="inspector-component-title">Cross-Region Replication Link</h3>
            <p className="inspector-desc text-xs text-secondary">
              Asynchronous PostgreSQL Write-Ahead Log (WAL) streaming pipeline between Mumbai and Singapore.
            </p>
            <div className="inspector-metric-grid">
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Purpose</span>
                <span className="metric-value font-mono text-bright text-xs">Cross-Region Data Replication</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Simulated Health</span>
                <span className={`metric-value font-mono text-xs ${replication.status === 'STREAMING' ? 'text-healthy' : 'text-danger'}`}>
                  {replication.status}
                </span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Replication Lag</span>
                <span className={`metric-value font-mono ${replication.lagSeconds > config.acceptableReplicationLagSec ? 'text-danger' : 'text-flow'}`}>
                  {replication.lagSeconds.toFixed(1)}s ({Math.round(replication.lagSeconds * 1000)}ms)
                </span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Acceptable Limit</span>
                <span className="metric-value font-mono text-bright">{config.acceptableReplicationLagSec}s Max</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Bandwidth</span>
                <span className="metric-value font-mono text-bright">{replication.bandwidthMbps} Mbps</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Pending Buffer</span>
                <span className="metric-value font-mono text-bright">{(replication.pendingBytes / 1024).toFixed(1)} KB</span>
              </div>
            </div>
            <div className="inspector-actions-section">
              <label className="section-label font-mono">CHAOS INJECTIONS</label>
              <div className="action-buttons-stack">
                <button
                  className="btn-console btn-danger text-xs"
                  onClick={() => engine.injectNetworkPartition()}
                >
                  <Radio size={13} />
                  <span>Sever Cross-Region Network Link</span>
                </button>
                <button
                  className="btn-console btn-warning text-xs"
                  onClick={() => engine.injectHighReplicationLag()}
                >
                  <Clock size={13} />
                  <span>Throttle WAN (Lag &gt; {config.acceptableReplicationLagSec}s Gate)</span>
                </button>
                <button
                  className="btn-console text-xs"
                  onClick={() => engine.restoreBaseline()}
                >
                  <RefreshCw size={13} />
                  <span>Restore WAN Baseline</span>
                </button>
              </div>
            </div>
          </div>
        );

      case 'CONTROLLER_HEALTH_MONITOR':
        return (
          <div className="inspector-content">
            <div className="inspector-top-meta">
              <div className="badge-tag badge-info font-mono text-xs">CONTROL PLANE</div>
              <span className="font-mono text-xs text-muted">Probe Aggregator</span>
            </div>
            <h3 className="inspector-component-title">Health Monitor Subsystem</h3>
            <p className="inspector-desc text-xs text-secondary">
              Central heartbeat collector receiving synthetic telemetry from regional agents. Debounces transient jitter to prevent flapping.
            </p>
            <div className="inspector-metric-grid">
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Purpose</span>
                <span className="metric-value font-mono text-bright text-xs">Failure Detection & Debouncing</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Consecutive Fails</span>
                <span className="metric-value font-mono text-bright">{consecutiveFailures} / {config.failureThresholdConsecutive} Threshold</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Probe Interval</span>
                <span className="metric-value font-mono text-bright">{config.healthCheckIntervalSec}s</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Current Phase</span>
                <span className="metric-value font-mono text-flow text-xs">{controllerState}</span>
              </div>
            </div>
          </div>
        );

      case 'CONTROLLER_QUORUM':
      case 'QUORUM':
        return (
          <div className="inspector-content">
            <div className="inspector-top-meta">
              <div className={`badge-tag ${quorum.consensusReached ? 'badge-healthy' : 'badge-danger'} font-mono text-xs`}>
                {quorum.consensusReached ? 'QUORUM REACHED' : 'SPLIT VOTES'}
              </div>
              <span className="font-mono text-xs text-muted">2 of 3 Required</span>
            </div>
            <h3 className="inspector-component-title">Quorum & Decision Engine</h3>
            <p className="inspector-desc text-xs text-secondary">
              Three simulated independent observer nodes (Mumbai, Singapore, Zurich) evaluate reachability to break ties authoritatively without split-brain.
            </p>
            <div className="inspector-metric-grid">
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Purpose</span>
                <span className="metric-value font-mono text-bright text-xs">Split-Brain Partition Arbiter</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Majority Policy</span>
                <span className="metric-value font-mono text-bright text-xs">{config.majorityRequired} of {config.quorumSize} Votes Required</span>
              </div>
            </div>
            <div className="quorum-nodes-list mt-2">
              {quorum.nodes.map((node) => (
                <div key={node.id} className="quorum-node-row">
                  <div className="node-row-top">
                    <span className="node-row-name font-mono text-xs font-semibold">{node.name}</span>
                    <span className="font-mono text-xs text-muted">{node.location}</span>
                  </div>
                  <div className="node-row-bottom">
                    <span className="text-xs text-secondary">Voted State:</span>
                    <span className={`badge-tag font-mono text-xs ${node.vote === 'region-a' ? 'badge-healthy' : 'badge-info'}`}>
                      {node.vote.toUpperCase()}
                    </span>
                    <span className="text-xs text-muted font-mono ml-auto">{node.latencyMs}ms RTT</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        );

      case 'CONTROLLER_LEASE':
      case 'LEASE_FENCE':
      case 'FENCING':
        return (
          <div className="inspector-content">
            <div className="inspector-top-meta">
              <div className={`badge-tag ${leaseFence.fenceStatus === 'ACTIVE_LOCK' ? 'badge-healthy' : 'badge-warning'} font-mono text-xs`}>
                {leaseFence.fenceStatus}
              </div>
              <span className="font-mono text-xs text-muted">Distributed Lock</span>
            </div>
            <h3 className="inspector-component-title">Lease Manager & Fencing Coordinator</h3>
            <p className="inspector-desc text-xs text-secondary">
              Distributed locking coordinator implementing Martin Kleppmann fencing tokens. Guarantees only one region holds a valid write token.
            </p>
            <div className="inspector-metric-grid">
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Purpose</span>
                <span className="metric-value font-mono text-bright text-xs">Write Authority Locking</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Epoch Token</span>
                <span className="metric-value font-mono text-healthy">#{leaseFence.generationId}</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Current Holder</span>
                <span className="metric-value font-mono text-flow text-xs">{leaseFence.currentHolder || 'None (Expired)'}</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Lock Status</span>
                <span className="metric-value font-mono text-bright text-xs">{leaseFence.fenceStatus}</span>
              </div>
            </div>
            <div className="system-design-note">
              <div className="note-title font-mono text-xs text-flow">
                <Shield size={12} />
                <span>Monotonic Epoch Tokens</span>
              </div>
              <p className="text-xs text-muted mt-1">
                When failover begins, the old primary is fenced and the epoch is incremented. The storage layer rejects any delayed packet from the old primary.
              </p>
            </div>
          </div>
        );

      case 'CONTROLLER_EXECUTOR':
        return (
          <div className="inspector-content">
            <div className="inspector-top-meta">
              <div className="badge-tag badge-info font-mono text-xs">ORCHESTRATOR</div>
              <span className="font-mono text-xs text-muted">Pipeline Runner</span>
            </div>
            <h3 className="inspector-component-title">Failover Executor</h3>
            <p className="inspector-desc text-xs text-secondary">
              Automates the strict multi-step cutover state machine: Fence Old Primary $\rightarrow$ Promote Standby $\rightarrow$ Repoint DNS $\rightarrow$ Verify Route.
            </p>
            <div className="inspector-metric-grid">
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Purpose</span>
                <span className="metric-value font-mono text-bright text-xs">Failover Sequence Execution</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Current Phase</span>
                <span className="metric-value font-mono text-flow text-xs">{controllerState}</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Sequence Status</span>
                <span className="metric-value font-mono text-bright text-xs">
                  {isSequenceInProgress ? 'ACTIVE CUTOVER' : 'IDLE / MONITORING'}
                </span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Safety Gates</span>
                <span className="metric-value font-mono text-healthy text-xs">8 Gates Active</span>
              </div>
            </div>
          </div>
        );

      case 'CONTROLLER_METADATA':
        return (
          <div className="inspector-content">
            <div className="inspector-top-meta">
              <div className="badge-tag badge-healthy font-mono text-xs">LINEARIZABLE</div>
              <span className="font-mono text-xs text-muted">Authoritative Store</span>
            </div>
            <h3 className="inspector-component-title">Metadata Store</h3>
            <p className="inspector-desc text-xs text-secondary">
              Distributed key-value store (etcd/Consul style) maintaining cluster topology, active epoch tokens, routing targets, and gate results.
            </p>
            <div className="inspector-metric-grid">
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Purpose</span>
                <span className="metric-value font-mono text-bright text-xs">Cluster State of Record</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Active Target</span>
                <span className="metric-value font-mono text-flow text-xs">{dns.activeDnsTarget}</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Epoch Version</span>
                <span className="metric-value font-mono text-bright">#{leaseFence.generationId}</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Consistency</span>
                <span className="metric-value font-mono text-healthy text-xs">Strict Linearizable</span>
              </div>
            </div>
          </div>
        );

      case 'CONTROLLER_AUDIT':
        return (
          <div className="inspector-content">
            <div className="inspector-top-meta">
              <div className="badge-tag badge-info font-mono text-xs">APPEND ONLY</div>
              <span className="font-mono text-xs text-muted">Audit Journal</span>
            </div>
            <h3 className="inspector-component-title">Audit and Event Log</h3>
            <p className="inspector-desc text-xs text-secondary">
              Immutable journal recording all state transitions, health probe timeouts, quorum votes, and gate verification checks with microsecond accuracy.
            </p>
            <div className="inspector-metric-grid">
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Purpose</span>
                <span className="metric-value font-mono text-bright text-xs">Tamper-Evident History</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Total Events</span>
                <span className="metric-value font-mono text-bright">{eventHistory.length} Recorded</span>
              </div>
            </div>
          </div>
        );

      default: // 'CONTROLLER' or fallback
        return (
          <div className="inspector-content">
            <div className="inspector-top-meta">
              <div className="badge-tag badge-info font-mono text-xs">{controllerState}</div>
              <span className="font-mono text-xs text-muted">Distributed Control Plane</span>
            </div>
            <h3 className="inspector-component-title">Failover Controller</h3>
            <p className="inspector-desc text-xs text-secondary">
              Central orchestrator managing multi-region health evaluation, lease management, fencing tokens, and automated failover pipelines.
            </p>
            <div className="inspector-metric-grid">
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Simulated Uptime</span>
                <span className="metric-value font-mono text-bright">{telemetry.uptimeSeconds}s</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Client Success</span>
                <span className={`metric-value font-mono ${telemetry.overallSuccessRate > 95 ? 'text-healthy' : 'text-danger'}`}>
                  {telemetry.overallSuccessRate}%
                </span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Total Failovers</span>
                <span className="metric-value font-mono text-flow">{telemetry.totalFailoversCount}</span>
              </div>
              <div className="inspector-metric-card">
                <span className="metric-label font-mono">Current Epoch</span>
                <span className="metric-value font-mono text-bright">#{leaseFence.generationId}</span>
              </div>
            </div>
            <div className="inspector-actions-section">
              <label className="section-label font-mono">CONTROLLER ACTIONS</label>
              <div className="action-buttons-stack">
                <button
                  className="btn-console btn-primary text-xs"
                  onClick={() => engine.injectPrimaryOutage()}
                >
                  <ArrowRight size={13} />
                  <span>Simulate Primary Outage (Initiate Failover)</span>
                </button>
                <button
                  className="btn-console text-xs"
                  onClick={() => engine.restoreBaseline()}
                >
                  <RefreshCw size={13} />
                  <span>Restore Nominal Baseline</span>
                </button>
              </div>
            </div>
          </div>
        );
    }
  };

  return (
    <div className="inspector-panel">
      <div className="panel-header">
        <div className="panel-title-group">
          <Activity size={16} className="text-flow" />
          <h2 className="panel-title">Component Inspector</h2>
        </div>
        <span className="font-mono text-xs text-muted">Interactive Node</span>
      </div>

      <div className="panel-scroll-content">
        {renderComponentDetails()}
      </div>
    </div>
  );
};
