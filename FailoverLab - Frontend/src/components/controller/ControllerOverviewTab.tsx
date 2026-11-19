import React from 'react';
import {
  ShieldCheck,
  Server,
  Activity,
  ArrowRight,
  Radio,
  CheckCircle2,
  AlertTriangle,
  GitBranch,
  History,
} from 'lucide-react';
import type {
  ControllerStateDto,
  TrafficSummaryDto,
  RegionalTrafficItemDto,
  AuditEventDto,
} from '../../api/controllerClient';
import { formatBytesPerSec, formatBytes, formatRelativeTime } from './formatters';

interface ControllerOverviewTabProps {
  controllerState: ControllerStateDto | null;
  trafficSummary: TrafficSummaryDto | null;
  regionalTraffic: RegionalTrafficItemDto[];
  auditEvents: AuditEventDto[];
  isBackendConnected: boolean;
  onNavigateTab: (tab: 'traffic' | 'regional' | 'replication' | 'history') => void;
}

const REGION_METADATA: Record<string, { city: string; code: string; zone: string }> = {
  'region-a': { city: 'Mumbai', code: 'IN', zone: 'ap-south-1' },
  'region-b': { city: 'Singapore', code: 'SG', zone: 'ap-southeast-1' },
  'region-c': { city: 'Frankfurt', code: 'DE', zone: 'eu-central-1' },
  'region-d': { city: 'N. Virginia', code: 'US', zone: 'us-east-1' },
  'region-e': { city: 'São Paulo', code: 'BR', zone: 'sa-east-1' },
};

export const ControllerOverviewTab: React.FC<ControllerOverviewTabProps> = ({
  controllerState,
  trafficSummary,
  regionalTraffic,
  auditEvents,
  isBackendConnected,
  onNavigateTab,
}) => {
  const activeRegionId = controllerState?.active_region || '—';
  const epoch = controllerState?.fencing_epoch !== undefined ? controllerState.fencing_epoch : '—';
  const cState = controllerState?.controller_state || (isBackendConnected ? 'Loading' : 'DISCONNECTED');
  const replLag = controllerState?.replication?.lag_seconds;
  const replStatus = controllerState?.replication?.status || (isBackendConnected ? 'Unavailable' : 'Disconnected');

  // Compute healthy and unavailable regions
  const regionsList = controllerState?.regions || [
    controllerState?.region_a,
    controllerState?.region_b,
    controllerState?.region_c,
    controllerState?.region_d,
    controllerState?.region_e,
  ].filter(Boolean);

  const hasRegionData = regionsList.length > 0;
  const healthyCount = regionsList.filter((r) => r && r.health === 'HEALTHY').length;
  const totalRegionsCount = 5;
  const unavailableCount = totalRegionsCount - healthyCount;

  // Find latest failover / transition event
  const latestFailoverEvent = auditEvents.find(
    (e) => e.subsystem === 'CONTROLLER' || e.subsystem === 'LEASE' || e.transition?.includes('ACTIVE')
  ) || auditEvents[0];

  return (
    <div className="controller-tab-pane">
      {/* 4 Primary System Vitals Cards */}
      <div className="ctrl-vitals-grid">
        {/* Card 1: Active Primary Writer */}
        <div className="ctrl-vital-card accent-flow">
          <div className="ctrl-vital-top">
            <span className="ctrl-vital-label">Active Writer</span>
            <ShieldCheck size={16} className="text-flow" />
          </div>
          <div className="ctrl-vital-value text-flow">
            {activeRegionId !== '—' ? (REGION_METADATA[activeRegionId]?.city || activeRegionId) : '—'}
          </div>
          <div className="ctrl-vital-sub">
            <span className="font-mono text-xs text-muted">
              {activeRegionId !== '—' ? `${activeRegionId} • ${REGION_METADATA[activeRegionId]?.zone || 'primary'}` : 'Not assigned'}
            </span>
            <span className="badge-tag-sm badge-info font-mono">
              {typeof epoch === 'number' ? `Epoch #${epoch}` : 'Epoch —'}
            </span>
          </div>
        </div>

        {/* Card 2: Cluster Regional Health */}
        <div className="ctrl-vital-card accent-healthy">
          <div className="ctrl-vital-top">
            <span className="ctrl-vital-label">Regional Health</span>
            <Server size={16} className="text-healthy" />
          </div>
          <div className="ctrl-vital-value text-healthy">
            {hasRegionData ? `${healthyCount} / ${totalRegionsCount}` : '—'}
          </div>
          <div className="ctrl-vital-sub">
            {!hasRegionData ? (
              <span className="text-muted flex items-center gap-1">
                Loading regional states...
              </span>
            ) : unavailableCount === 0 ? (
              <span className="text-healthy flex items-center gap-1">
                <CheckCircle2 size={12} /> All regions operational
              </span>
            ) : (
              <span className="text-warning flex items-center gap-1">
                <AlertTriangle size={12} /> {unavailableCount} region(s) degraded/down
              </span>
            )}
          </div>
        </div>

        {/* Card 3: Gateway Payload Traffic Ingress */}
        <div className="ctrl-vital-card accent-flow">
          <div className="ctrl-vital-top">
            <span className="ctrl-vital-label">Customer Ingress</span>
            <Activity size={16} className="text-flow" />
          </div>
          <div className="ctrl-vital-value">
            {trafficSummary && trafficSummary.is_available ? formatBytesPerSec(trafficSummary.current_ingress_bytes_per_sec) : '0.0 B/s'}
          </div>
          <div className="ctrl-vital-sub">
            <span className="font-mono">
              {trafficSummary && trafficSummary.is_available ? trafficSummary.request_rate.toFixed(1) : '0.0'} req/s
            </span>
            <span className="text-muted">•</span>
            <span className="text-muted">
              P95 {trafficSummary && trafficSummary.is_available ? `${trafficSummary.latency_p95_ms.toFixed(1)}ms` : '—'}
            </span>
          </div>
        </div>

        {/* Card 4: Replication Pipeline Freshness */}
        <div className="ctrl-vital-card accent-warning">
          <div className="ctrl-vital-top">
            <span className="ctrl-vital-label">Replication Lag</span>
            <GitBranch size={16} className="text-warning" />
          </div>
          <div className="ctrl-vital-value font-mono">
            {replLag !== undefined ? `${replLag.toFixed(2)}s` : '—'}
          </div>
          <div className="ctrl-vital-sub">
            <span className="badge-tag-sm badge-info font-mono">{replStatus}</span>
            <span className="text-muted">
              Bandwidth: {controllerState?.replication?.bandwidth_mbps !== undefined ? `${controllerState.replication.bandwidth_mbps} Mbps` : '—'}
            </span>
          </div>
        </div>
      </div>

      {/* Five Regional Health Status Row */}
      <div className="ctrl-panel">
        <div className="ctrl-panel-header">
          <div className="ctrl-panel-title">
            <Server size={15} />
            <span>Five-Region Cluster Deployment Status</span>
          </div>
          <button
            type="button"
            className="btn-console btn-sm"
            onClick={() => onNavigateTab('regional')}
          >
            <span>View Regional Operations</span>
            <ArrowRight size={13} />
          </button>
        </div>

        <div className="ctrl-panel-body">
          <div className="ctrl-regional-cards-grid">
            {['region-a', 'region-b', 'region-c', 'region-d', 'region-e'].map((rId) => {
              const meta = REGION_METADATA[rId] || { city: rId, code: 'GL', zone: '' };
              const regData = regionsList.find((r) => r && r.id === rId);
              const trafficItem = regionalTraffic.find((t) => t.region_id === rId);
              const isWriter = rId === activeRegionId;
              const isHealthy = regData?.health === 'HEALTHY';
              const healthStatus = regData?.health || (isBackendConnected ? 'Not reported' : 'Unavailable');

              return (
                <div
                  key={rId}
                  className={`ctrl-region-card ${isWriter ? 'active-writer' : ''}`}
                >
                  <div className="ctrl-region-top">
                    <div>
                      <div className="ctrl-region-city">
                        <span className="font-mono text-xs text-muted" style={{ marginRight: '6px', fontWeight: 700 }}>[{meta.code}]</span>
                        <span>{meta.city}</span>
                      </div>
                      <div className="ctrl-region-code">{meta.zone || rId}</div>
                    </div>
                    {isWriter ? (
                      <span className="badge-tag-sm badge-healthy font-mono">PRIMARY</span>
                    ) : (
                      <span className="badge-tag-sm badge-info font-mono">STANDBY</span>
                    )}
                  </div>

                  <div className="ctrl-region-meta-grid">
                    <div className="ctrl-region-meta-item">
                      <span className="ctrl-region-meta-label">Health</span>
                      <span
                        className={`ctrl-region-meta-val ${isHealthy ? 'text-healthy' : 'text-danger'
                          }`}
                      >
                        {healthStatus}
                      </span>
                    </div>

                    <div className="ctrl-region-meta-item">
                      <span className="ctrl-region-meta-label">Writes</span>
                      <span className="ctrl-region-meta-val">
                        {isWriter ? 'ENABLED' : 'READ-ONLY'}
                      </span>
                    </div>

                    <div className="ctrl-region-meta-item">
                      <span className="ctrl-region-meta-label">Gateway → Region</span>
                      <span className="ctrl-region-meta-val font-mono">
                        {trafficItem && trafficItem.upstream_egress_rate > 0
                          ? formatBytesPerSec(trafficItem.upstream_egress_rate)
                          : '0.0 B/s (Idle)'}
                      </span>
                    </div>

                    <div className="ctrl-region-meta-item">
                      <span className="ctrl-region-meta-label">Replication</span>
                      <span className="ctrl-region-meta-val font-mono">
                        {isWriter
                          ? 'SOURCE'
                          : regData?.replication_lag_seconds !== undefined
                            ? `${regData.replication_lag_seconds.toFixed(1)}s lag`
                            : replLag !== undefined
                              ? `${replLag.toFixed(1)}s lag`
                              : '—'}
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Lower Row: Telemetry Health and Latest Failover Audit */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.25rem' }}>
        {/* Gateway Telemetry Observability Status */}
        <div className="ctrl-panel">
          <div className="ctrl-panel-header">
            <div className="ctrl-panel-title">
              <Radio size={15} />
              <span>Gateway Telemetry Pipeline Health</span>
            </div>
            <button
              type="button"
              className="btn-console btn-sm"
              onClick={() => onNavigateTab('traffic')}
            >
              <span>Traffic Charts</span>
              <ArrowRight size={13} />
            </button>
          </div>

          <div className="ctrl-panel-body" style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', fontSize: '0.8rem' }}>
              <div style={{ padding: '0.65rem', background: 'var(--bg-panel)', borderRadius: '4px' }}>
                <div style={{ color: 'var(--text-muted)', fontSize: '0.72rem' }}>Freshness Status</div>
                <div style={{ fontWeight: 700, fontFamily: 'var(--font-mono)' }} className={
                  trafficSummary?.telemetry_freshness === 'FRESH'
                    ? 'text-healthy'
                    : trafficSummary?.telemetry_freshness === 'STALE'
                      ? 'text-warning'
                      : 'text-danger'
                }>
                  {trafficSummary?.telemetry_freshness || (isBackendConnected ? 'PENDING' : 'UNAVAILABLE')}
                </div>
              </div>

              <div style={{ padding: '0.65rem', background: 'var(--bg-panel)', borderRadius: '4px' }}>
                <div style={{ color: 'var(--text-muted)', fontSize: '0.72rem' }}>Reporting Source</div>
                <div style={{ fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                  {trafficSummary?.measurement_source || '—'}
                </div>
              </div>

              <div style={{ padding: '0.65rem', background: 'var(--bg-panel)', borderRadius: '4px' }}>
                <div style={{ color: 'var(--text-muted)', fontSize: '0.72rem' }}>Cumulative Ingress</div>
                <div style={{ fontWeight: 700, fontFamily: 'var(--font-mono)' }} className="text-flow">
                  {trafficSummary && trafficSummary.is_available ? formatBytes(trafficSummary.cumulative_ingress_bytes) : '0 B'}
                </div>
              </div>

              <div style={{ padding: '0.65rem', background: 'var(--bg-panel)', borderRadius: '4px' }}>
                <div style={{ color: 'var(--text-muted)', fontSize: '0.72rem' }}>Cumulative Egress</div>
                <div style={{ fontWeight: 700, fontFamily: 'var(--font-mono)' }} className="text-healthy">
                  {trafficSummary && trafficSummary.is_available ? formatBytes(trafficSummary.cumulative_egress_bytes) : '0 B'}
                </div>
              </div>
            </div>

            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              Ingress pipeline measures live application & HTTP payload bytes received by the Gateway from the Online Store.
            </div>
          </div>
        </div>

        {/* Latest Transition / Failover Audit */}
        <div className="ctrl-panel">
          <div className="ctrl-panel-header">
            <div className="ctrl-panel-title">
              <History size={15} />
              <span>Latest Controller Transition & Safety Gates</span>
            </div>
            <button
              type="button"
              className="btn-console btn-sm"
              onClick={() => onNavigateTab('history')}
            >
              <span>Full Audit Trail</span>
              <ArrowRight size={13} />
            </button>
          </div>

          <div className="ctrl-panel-body">
            {latestFailoverEvent ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem', fontSize: '0.8rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span className="badge-tag-sm badge-info font-mono">
                    {latestFailoverEvent.subsystem}
                  </span>
                  <span className="text-muted font-mono text-xs">
                    {formatRelativeTime(latestFailoverEvent.wall_clock_timestamp)}
                  </span>
                </div>

                <div style={{ fontWeight: 600, color: 'var(--text-bright)' }}>
                  {latestFailoverEvent.transition || 'Nominal Operation State Maintained'}
                </div>

                <div style={{ color: 'var(--text-secondary)', fontSize: '0.75rem' }}>
                  {latestFailoverEvent.reason || 'Controller active and monitoring consensus.'}
                </div>

                <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.25rem', flexWrap: 'wrap' }}>
                  <span className="badge-tag-sm badge-info">
                    {controllerState?.voters && controllerState.voters.length > 0
                      ? `Quorum Peers (${controllerState.voters.filter(v => v.vote === 'PRIMARY_HEALTHY' || v.vote === 'PRIMARY_OUTAGE').length}/${controllerState.voters.length})`
                      : 'Quorum (Consensus Active)'}
                  </span>
                  <span className="badge-tag-sm badge-info font-mono">
                    {typeof epoch === 'number' ? `Epoch #${epoch}` : 'Epoch —'}
                  </span>
                  <span className="badge-tag-sm badge-info font-mono">
                    Replication: {replStatus}
                  </span>
                </div>
              </div>
            ) : (
              <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                No state transitions recorded yet. Controller running baseline state: {cState}.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
