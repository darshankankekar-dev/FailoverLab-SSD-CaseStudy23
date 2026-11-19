import React, { useState } from 'react';
import {
  Globe2,
  Server,
  ShieldCheck,
  RotateCcw,
  Zap,
} from 'lucide-react';
import { controllerClient } from '../../api/controllerClient';
import type {
  ControllerStateDto,
  RegionalTrafficItemDto,
  TrafficSummaryDto,
} from '../../api/controllerClient';
import { formatBytesPerSec, formatRelativeTime } from './formatters';

interface ControllerRegionalOperationsTabProps {
  controllerState: ControllerStateDto | null;
  regionalTraffic: RegionalTrafficItemDto[];
  trafficSummary: TrafficSummaryDto | null;
  onRefresh: () => void;
}

const REGION_METADATA: Record<string, { city: string; code: string; zone: string; country: string }> = {
  'region-a': { city: 'Mumbai', code: 'IN', zone: 'ap-south-1', country: 'India' },
  'region-b': { city: 'Singapore', code: 'SG', zone: 'ap-southeast-1', country: 'Singapore' },
  'region-c': { city: 'Frankfurt', code: 'DE', zone: 'eu-central-1', country: 'Germany' },
  'region-d': { city: 'N. Virginia', code: 'US', zone: 'us-east-1', country: 'United States' },
  'region-e': { city: 'São Paulo', code: 'BR', zone: 'sa-east-1', country: 'Brazil' },
};

export const ControllerRegionalOperationsTab: React.FC<ControllerRegionalOperationsTabProps> = ({
  controllerState,
  regionalTraffic,
  trafficSummary,
  onRefresh,
}) => {
  const [actionMessage, setActionMessage] = useState<{ text: string; isError?: boolean } | null>(null);
  const [isExecuting, setIsExecuting] = useState(false);

  const activeRegion = controllerState?.active_region || 'region-a';
  const regionsList = controllerState?.regions || [
    controllerState?.region_a,
    controllerState?.region_b,
    controllerState?.region_c,
    controllerState?.region_d,
    controllerState?.region_e,
  ].filter(Boolean);

  // Compute total ingress throughput across all regions for proportional bar
  let totalIngressBps = 0;
  regionalTraffic.forEach((r) => {
    totalIngressBps += r.ingress_bytes_per_sec || 0;
  });
  if (totalIngressBps === 0 && trafficSummary && trafficSummary.client_ingress_bytes_per_sec > 0) {
    totalIngressBps = trafficSummary.client_ingress_bytes_per_sec;
  }

  const handlePromote = async (targetRegionId: string) => {
    if (targetRegionId === activeRegion) return;
    setIsExecuting(true);
    setActionMessage(null);
    try {
      const res = await controllerClient.triggerFailover({
        target_region: targetRegionId,
        force: false,
        reason: `Manual operator promotion to ${targetRegionId} via Controller UI`,
      });
      setActionMessage({
        text: `Promotion transition initiated: ${res.status} (New epoch #${res.fencing_epoch})`,
      });
      onRefresh();
    } catch (err: any) {
      setActionMessage({
        text: `Failover failed: ${err.message || 'Verification gates rejected promotion'}`,
        isError: true,
      });
    } finally {
      setIsExecuting(false);
    }
  };

  const handleToggleHealth = async (regionId: string, currentHealth: string) => {
    setIsExecuting(true);
    setActionMessage(null);
    const newHealth = currentHealth === 'DOWN' ? 'HEALTHY' : 'DOWN';
    try {
      await controllerClient.setRegionalHealth(regionId, newHealth);
      setActionMessage({
        text: `Region ${regionId} health updated to ${newHealth}`,
      });
      onRefresh();
    } catch (err: any) {
      setActionMessage({
        text: `Update failed: ${err.message}`,
        isError: true,
      });
    } finally {
      setIsExecuting(false);
    }
  };

  const handleResetRegional = async (regionId: string) => {
    setIsExecuting(true);
    setActionMessage(null);
    try {
      await controllerClient.resetRegional(regionId);
      setActionMessage({
        text: `Region ${regionId} restored to nominal baseline.`,
      });
      onRefresh();
    } catch (err: any) {
      setActionMessage({
        text: `Reset failed: ${err.message}`,
        isError: true,
      });
    } finally {
      setIsExecuting(false);
    }
  };

  return (
    <div className="controller-tab-pane">
      {/* Action Status Feedback Banner */}
      {actionMessage && (
        <div
          style={{
            padding: '0.65rem 1rem',
            borderRadius: '4px',
            fontSize: '0.8rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            background: actionMessage.isError ? 'rgba(239, 68, 68, 0.15)' : 'rgba(16, 185, 129, 0.15)',
            border: `1px solid ${actionMessage.isError ? '#ef4444' : '#10b981'}`,
            color: actionMessage.isError ? '#fca5a5' : '#86efac',
          }}
        >
          <span>{actionMessage.text}</span>
          <button
            type="button"
            className="btn-console btn-sm"
            onClick={() => setActionMessage(null)}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Proportional Regional Traffic Distribution Graph */}
      <div className="ctrl-panel">
        <div className="ctrl-panel-header">
          <div className="ctrl-panel-title">
            <Globe2 size={16} />
            <span>Regional Traffic Distribution & Proportional Ingress Share</span>
          </div>
          <span className="font-mono text-xs text-muted">
            Total Aggregate: {formatBytesPerSec(totalIngressBps)}
          </span>
        </div>

        <div className="ctrl-panel-body">
          {totalIngressBps > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {/* Stacked Percentage Bar */}
              <div
                style={{
                  height: '24px',
                  width: '100%',
                  borderRadius: '4px',
                  overflow: 'hidden',
                  display: 'flex',
                  background: 'var(--bg-panel)',
                  border: '1px solid var(--border-default)',
                }}
              >
                {['region-a', 'region-b', 'region-c', 'region-d', 'region-e'].map((rId, i) => {
                  const tItem = regionalTraffic.find((t) => t.region_id === rId);
                  const isWriter = rId === activeRegion;
                  const bps = (tItem && tItem.ingress_bytes_per_sec) || (isWriter && trafficSummary ? trafficSummary.client_ingress_bytes_per_sec : 0);
                  const pct = totalIngressBps > 0 ? (bps / totalIngressBps) * 100 : 0;
                  if (pct <= 0) return null;

                  const colors = ['#0ea5e9', '#10b981', '#f59e0b', '#a855f7', '#ec4899'];
                  return (
                    <div
                      key={rId}
                      style={{
                        width: `${pct}%`,
                        background: colors[i % colors.length],
                        height: '100%',
                        transition: 'width 0.3s ease',
                      }}
                      title={`${rId}: ${pct.toFixed(1)}% (${formatBytesPerSec(bps)})`}
                    />
                  );
                })}
              </div>

              {/* Legend with exact percentages */}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', fontSize: '0.75rem' }}>
                {['region-a', 'region-b', 'region-c', 'region-d', 'region-e'].map((rId, i) => {
                  const meta = REGION_METADATA[rId];
                  const tItem = regionalTraffic.find((t) => t.region_id === rId);
                  const isWriter = rId === activeRegion;
                  const bps = (tItem && tItem.ingress_bytes_per_sec) || (isWriter && trafficSummary ? trafficSummary.client_ingress_bytes_per_sec : 0);
                  const pct = totalIngressBps > 0 ? (bps / totalIngressBps) * 100 : 0;
                  const colors = ['#0ea5e9', '#10b981', '#f59e0b', '#a855f7', '#ec4899'];

                  return (
                    <div key={rId} style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                      <span
                        style={{
                          width: '10px',
                          height: '10px',
                          borderRadius: '2px',
                          background: colors[i % colors.length],
                        }}
                      />
                      <span className="font-mono text-muted">{meta.city}:</span>
                      <span className="font-mono font-bold">
                        {pct > 0 ? `${pct.toFixed(1)}% (${formatBytesPerSec(bps)})` : '0.0% (Idle)'}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', fontFamily: 'var(--font-mono)' }}>
              No ingress traffic currently flowing to regional backends. Generate orders or catalog queries from the Online Store to visualize regional distribution.
            </div>
          )}
        </div>
      </div>

      {/* Five Rows Regional Traffic & Operations Table */}
      <div className="ctrl-panel">
        <div className="ctrl-panel-header">
          <div className="ctrl-panel-title">
            <Server size={16} />
            <span>Regional Fleet Operations (5 Regions)</span>
          </div>
          <span className="font-mono text-xs text-muted">
            Active Fencing Epoch: #{controllerState?.fencing_epoch ?? 101}
          </span>
        </div>

        <div className="ctrl-panel-body" style={{ padding: 0 }}>
          <div className="ctrl-table-wrapper">
            <table className="ctrl-table">
              <thead>
                <tr>
                  <th>Region & Zone</th>
                  <th>Location</th>
                  <th>Role</th>
                  <th>Health Status</th>
                  <th>Requests / Sec</th>
                  <th>Ingress Throughput</th>
                  <th>Egress Throughput</th>
                  <th>Replication Lag</th>
                  <th>Last Telemetry</th>
                  <th>Administrative Actions</th>
                </tr>
              </thead>
              <tbody>
                {['region-a', 'region-b', 'region-c', 'region-d', 'region-e'].map((rId) => {
                  const meta = REGION_METADATA[rId];
                  const regData = regionsList.find((r) => r && r.id === rId);
                  const tItem = regionalTraffic.find((t) => t.region_id === rId);
                  const isWriter = rId === activeRegion;
                  const health = regData?.health || 'HEALTHY';
                  const isHealthy = health === 'HEALTHY';

                  // Compute truthful rates without fabricating data
                  const rps = (tItem && tItem.requests_per_sec) || (isWriter && trafficSummary ? trafficSummary.requests_per_sec : 0);
                  const ingressBps = (tItem && tItem.ingress_bytes_per_sec) || (isWriter && trafficSummary ? trafficSummary.client_ingress_bytes_per_sec : 0);
                  const egressBps = (tItem && tItem.egress_bytes_per_sec) || (isWriter && trafficSummary ? trafficSummary.client_egress_bytes_per_sec : 0);
                  const lag = regData?.replication_lag_seconds ?? (isWriter ? 0 : controllerState?.replication?.lag_seconds ?? 0);
                  const lastSeen = tItem?.last_telemetry_timestamp || (isWriter ? trafficSummary?.last_telemetry_timestamp : null);

                  return (
                    <tr key={rId} className={isWriter ? 'active-row' : ''}>
                      {/* Region & Zone */}
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                          <span className="font-mono text-xs text-muted" style={{ fontWeight: 700 }}>[{meta.code}]</span>
                          <div>
                            <div style={{ fontWeight: 700, color: 'var(--text-bright)' }}>{rId}</div>
                            <div className="text-muted text-xs font-mono">{meta.zone}</div>
                          </div>
                        </div>
                      </td>

                      {/* City */}
                      <td>
                        <div>{meta.city}</div>
                        <div className="text-muted text-xs">{meta.country}</div>
                      </td>

                      {/* Role */}
                      <td>
                        {isWriter ? (
                          <span className="badge-tag-sm badge-healthy font-mono">PRIMARY WRITER</span>
                        ) : (
                          <span className="badge-tag-sm badge-info font-mono">STANDBY REPLICA</span>
                        )}
                      </td>

                      {/* Health */}
                      <td>
                        <span
                          className={`badge-tag-sm font-mono ${
                            isHealthy ? 'badge-healthy' : 'badge-danger'
                          }`}
                        >
                          {health}
                        </span>
                      </td>

                      {/* Requests / Sec */}
                      <td className="font-mono">
                        {rps > 0 ? `${rps.toFixed(1)} req/s` : <span className="text-muted">0.0 req/s</span>}
                      </td>

                      {/* Ingress Throughput */}
                      <td className="font-mono">
                        {ingressBps > 0 ? (
                          <span className="text-flow font-bold">{formatBytesPerSec(ingressBps)}</span>
                        ) : (
                          <span className="text-muted">0.0 B/s (Idle)</span>
                        )}
                      </td>

                      {/* Egress Throughput */}
                      <td className="font-mono">
                        {egressBps > 0 ? (
                          <span className="text-healthy font-bold">{formatBytesPerSec(egressBps)}</span>
                        ) : (
                          <span className="text-muted">0.0 B/s (Idle)</span>
                        )}
                      </td>

                      {/* Replication Lag */}
                      <td className="font-mono">
                        {isWriter ? (
                          <span className="text-muted font-mono">0.00s (Source)</span>
                        ) : (
                          <span className={lag > 3 ? 'text-danger font-bold' : lag > 1 ? 'text-warning' : 'text-primary'}>
                            {lag.toFixed(2)}s
                          </span>
                        )}
                      </td>

                      {/* Last Telemetry */}
                      <td className="font-mono text-xs text-muted">
                        {formatRelativeTime(lastSeen || null)}
                      </td>

                      {/* Administrative Actions */}
                      <td>
                        <div style={{ display: 'flex', gap: '0.35rem' }}>
                          {!isWriter && (
                            <button
                              type="button"
                              className="btn-console btn-sm"
                              disabled={isExecuting || !isHealthy}
                              onClick={() => handlePromote(rId)}
                              title={`Promote ${meta.city} to active primary writer`}
                            >
                              <ShieldCheck size={12} />
                              <span>Promote</span>
                            </button>
                          )}

                          <button
                            type="button"
                            className={`btn-console btn-sm ${isHealthy ? 'btn-danger' : 'btn-primary'}`}
                            disabled={isExecuting}
                            onClick={() => handleToggleHealth(rId, health)}
                            title={isHealthy ? `Inject failure into ${meta.city}` : `Recover ${meta.city}`}
                          >
                            <Zap size={12} />
                            <span>{isHealthy ? 'Kill' : 'Recover'}</span>
                          </button>

                          <button
                            type="button"
                            className="btn-console btn-sm"
                            disabled={isExecuting}
                            onClick={() => handleResetRegional(rId)}
                            title={`Reset ${meta.city} regional simulator state`}
                          >
                            <RotateCcw size={12} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};
