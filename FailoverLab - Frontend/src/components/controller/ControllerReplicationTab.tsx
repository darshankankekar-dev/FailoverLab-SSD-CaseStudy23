import React, { useState } from 'react';
import {
  GitBranch,
  Play,
  Pause,
  ShieldCheck,
  Server,
} from 'lucide-react';
import { controllerClient } from '../../api/controllerClient';
import type { ControllerStateDto } from '../../api/controllerClient';

interface ControllerReplicationTabProps {
  controllerState: ControllerStateDto | null;
  onRefresh: () => void;
}

const REGION_NAMES: Record<string, string> = {
  'region-a': 'Mumbai (ap-south-1)',
  'region-b': 'Singapore (ap-southeast-1)',
  'region-c': 'Frankfurt (eu-central-1)',
  'region-d': 'Virginia (us-east-1)',
  'region-e': 'São Paulo (sa-east-1)',
};

export const ControllerReplicationTab: React.FC<ControllerReplicationTabProps> = ({
  controllerState,
  onRefresh,
}) => {
  const [isProcessing, setIsProcessing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const replication = controllerState?.replication;
  const destinations = replication?.destinations || {};
  const activeRegion = controllerState?.active_region || '—';
  const hasReplication = !!replication;

  const handlePause = async (destId?: string) => {
    setIsProcessing(true);
    setMessage(null);
    try {
      await controllerClient.pauseReplication(destId);
      setMessage(destId ? `Replication to ${destId} paused.` : 'Global replication paused.');
      onRefresh();
    } catch (err: any) {
      setMessage(`Error pausing replication: ${err.message}`);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleResume = async (destId?: string) => {
    setIsProcessing(true);
    setMessage(null);
    try {
      await controllerClient.resumeReplication(destId);
      setMessage(destId ? `Replication to ${destId} resumed.` : 'Global replication resumed.');
      onRefresh();
    } catch (err: any) {
      setMessage(`Error resuming replication: ${err.message}`);
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div className="controller-tab-pane">
      {message && (
        <div
          style={{
            padding: '0.65rem 1rem',
            background: 'rgba(14, 165, 233, 0.15)',
            border: '1px solid #0ea5e9',
            borderRadius: '4px',
            fontSize: '0.8rem',
            color: '#7dd3fc',
            display: 'flex',
            justifyContent: 'space-between',
          }}
        >
          <span>{message}</span>
          <button type="button" className="btn-console btn-sm" onClick={() => setMessage(null)}>
            Dismiss
          </button>
        </div>
      )}

      {/* Global Replication Vitals */}
      <div className="ctrl-vitals-grid">
        <div className="ctrl-vital-card accent-flow">
          <div className="ctrl-vital-top">
            <span className="ctrl-vital-label">Replication Pipeline</span>
            <GitBranch size={16} className="text-flow" />
          </div>
          <div className="ctrl-vital-value text-flow font-mono">
            {replication?.status || (hasReplication ? 'STREAMING' : 'Unavailable')}
          </div>
          <div className="ctrl-vital-sub">
            <span className="text-muted">Outbox Protocol:</span>
            <span className="font-mono">Transactional CDC</span>
          </div>
        </div>

        <div className="ctrl-vital-card accent-warning">
          <div className="ctrl-vital-top">
            <span className="ctrl-vital-label">Aggregate Time Lag</span>
            <span className="badge-tag-sm badge-warning font-mono">
              {replication?.lag_seconds !== undefined ? `${replication.lag_seconds.toFixed(2)}s` : '—'}
            </span>
          </div>
          <div className="ctrl-vital-value font-mono">
            {replication?.lag_ms !== undefined
              ? `${replication.lag_ms} ms`
              : replication?.lag_seconds !== undefined
                ? `${(replication.lag_seconds * 1000).toFixed(0)} ms`
                : '—'}
          </div>
          <div className="ctrl-vital-sub">
            <span className="text-muted">Acceptable SLA limit:</span>
            <span className="font-mono">5.00s</span>
          </div>
        </div>

        <div className="ctrl-vital-card accent-healthy">
          <div className="ctrl-vital-top">
            <span className="ctrl-vital-label">Replication Bandwidth</span>
            <Server size={16} className="text-healthy" />
          </div>
          <div className="ctrl-vital-value font-mono text-healthy">
            {replication?.bandwidth_mbps !== undefined ? `${replication.bandwidth_mbps} Mbps` : '—'}
          </div>
          <div className="ctrl-vital-sub">
            <span className="text-muted">Packet Loss:</span>
            <span className="font-mono">{replication?.packet_loss_percent !== undefined ? `${replication.packet_loss_percent.toFixed(1)}%` : '—'}</span>
          </div>
        </div>

        <div className="ctrl-vital-card accent-flow">
          <div className="ctrl-vital-top">
            <span className="ctrl-vital-label">Source Sequence</span>
            <ShieldCheck size={16} className="text-flow" />
          </div>
          <div className="ctrl-vital-value font-mono">
            {controllerState?.region_a?.applied_sequence !== undefined
              ? `#${controllerState.region_a.applied_sequence}`
              : (Object.values(destinations)[0]?.source_highest_sequence !== undefined
                ? `#${Object.values(destinations)[0].source_highest_sequence}`
                : '—')}
          </div>
          <div className="ctrl-vital-sub">
            <span className="text-muted">Source:</span>
            <span className="text-flow font-mono">{activeRegion}</span>
          </div>
        </div>
      </div>

      {/* Destination Regions Outbox Table */}
      <div className="ctrl-panel">
        <div className="ctrl-panel-header">
          <div className="ctrl-panel-title">
            <GitBranch size={16} />
            <span>Multi-Region Transactional Outbox Destinations</span>
          </div>

          <div className="ctrl-panel-actions">
            <button
              type="button"
              className="btn-console btn-sm btn-danger"
              disabled={isProcessing}
              onClick={() => handlePause()}
              title="Pause all outgoing replication streams"
            >
              <Pause size={12} />
              <span>Pause Global</span>
            </button>
            <button
              type="button"
              className="btn-console btn-sm btn-primary"
              disabled={isProcessing}
              onClick={() => handleResume()}
              title="Resume all replication streams"
            >
              <Play size={12} />
              <span>Resume Global</span>
            </button>
          </div>
        </div>

        <div className="ctrl-panel-body" style={{ padding: 0 }}>
          <div className="ctrl-table-wrapper">
            <table className="ctrl-table">
              <thead>
                <tr>
                  <th>Destination Region</th>
                  <th>Stream Status</th>
                  <th>Applied Sequence</th>
                  <th>Sequence Lag</th>
                  <th>Time Lag</th>
                  <th>Retries</th>
                  <th>Failures</th>
                  <th>Replication Controls</th>
                </tr>
              </thead>
              <tbody>
                {['region-a', 'region-b', 'region-c', 'region-d', 'region-e'].map((rId) => {
                  const isSource = rId === activeRegion;
                  const destInfo = destinations[rId];
                  const lagSec = destInfo?.lag_seconds ?? (isSource ? 0 : replication?.lag_seconds);
                  const status = isSource ? 'SOURCE' : destInfo?.status || replication?.status || (isSource ? 'SOURCE' : 'Unavailable');
                  const appliedSeq = destInfo?.applied_sequence;
                  const seqLag = isSource ? 0 : destInfo?.sequence_lag;

                  return (
                    <tr key={rId} className={isSource ? 'active-row' : ''}>
                      {/* Destination Region */}
                      <td>
                        <div style={{ fontWeight: 700, color: 'var(--text-bright)' }}>{rId}</div>
                        <div className="text-muted text-xs font-mono">{REGION_NAMES[rId] || rId}</div>
                      </td>

                      {/* Stream Status */}
                      <td>
                        <span
                          className={`badge-tag-sm font-mono ${
                            isSource
                              ? 'badge-info'
                              : status === 'STREAMING' || status === 'SYNCED'
                              ? 'badge-healthy'
                              : status === 'PAUSED'
                              ? 'badge-warning'
                              : 'badge-danger'
                          }`}
                        >
                          {status}
                        </span>
                      </td>

                      {/* Applied Sequence */}
                      <td className="font-mono">
                        {appliedSeq !== undefined ? `#${appliedSeq}` : <span className="text-muted">—</span>}
                      </td>

                      {/* Sequence Lag */}
                      <td className="font-mono">
                        {isSource ? (
                          <span className="text-muted">0 (Source)</span>
                        ) : seqLag !== undefined ? (
                          seqLag > 0 ? (
                            <span className="text-warning font-bold">{seqLag} tx behind</span>
                          ) : (
                            <span className="text-healthy">0 tx (In-Sync)</span>
                          )
                        ) : (
                          <span className="text-muted">—</span>
                        )}
                      </td>

                      {/* Time Lag */}
                      <td className="font-mono">
                        {isSource ? (
                          <span className="text-muted">0.00s</span>
                        ) : lagSec !== undefined ? (
                          <span className={lagSec > 3 ? 'text-danger font-bold' : lagSec > 1 ? 'text-warning' : 'text-primary'}>
                            {lagSec.toFixed(2)}s
                          </span>
                        ) : (
                          <span className="text-muted">—</span>
                        )}
                      </td>

                      {/* Retries */}
                      <td className="font-mono text-muted">
                        {destInfo?.retry_count ?? '—'}
                      </td>

                      {/* Failures */}
                      <td className="font-mono text-muted">
                        {destInfo?.consecutive_failures ?? '—'}
                      </td>

                      {/* Controls */}
                      <td>
                        {!isSource && (
                          <div style={{ display: 'flex', gap: '0.35rem' }}>
                            {status === 'PAUSED' ? (
                              <button
                                type="button"
                                className="btn-console btn-sm btn-primary"
                                disabled={isProcessing}
                                onClick={() => handleResume(rId)}
                              >
                                <Play size={12} />
                                <span>Resume</span>
                              </button>
                            ) : (
                              <button
                                type="button"
                                className="btn-console btn-sm btn-danger"
                                disabled={isProcessing}
                                onClick={() => handlePause(rId)}
                              >
                                <Pause size={12} />
                                <span>Pause</span>
                              </button>
                            )}
                          </div>
                        )}
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
