import React, { useState, useMemo } from 'react';
import {
  History,
  Download,
  RotateCw,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';
import type { AuditEventDto } from '../../api/controllerClient';
import { formatRelativeTime } from './formatters';

interface ControllerFailoverHistoryTabProps {
  events: AuditEventDto[];
  onRefresh: () => void;
}

export const ControllerFailoverHistoryTab: React.FC<ControllerFailoverHistoryTabProps> = ({
  events,
  onRefresh,
}) => {
  const [severityFilter, setSeverityFilter] = useState('ALL');
  const [subsystemFilter, setSubsystemFilter] = useState('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedRowId, setExpandedRowId] = useState<string | null>(null);

  const toggleExpand = (id: string) => {
    setExpandedRowId((prev) => (prev === id ? null : id));
  };

  const handleExportJson = () => {
    const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(events, null, 2));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute('href', dataStr);
    downloadAnchor.setAttribute('download', `controller-audit-trail-${Date.now()}.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  const filteredEvents = useMemo(() => {
    return events.filter((ev) => {
      if (severityFilter !== 'ALL' && ev.severity !== severityFilter) return false;
      if (subsystemFilter !== 'ALL' && ev.subsystem !== subsystemFilter) return false;
      if (searchQuery.trim() !== '') {
        const q = searchQuery.toLowerCase();
        const matches =
          (ev.transition && ev.transition.toLowerCase().includes(q)) ||
          (ev.reason && ev.reason.toLowerCase().includes(q)) ||
          (ev.subsystem && ev.subsystem.toLowerCase().includes(q));
        if (!matches) return false;
      }
      return true;
    });
  }, [events, severityFilter, subsystemFilter, searchQuery]);

  return (
    <div className="controller-tab-pane">
      <div className="ctrl-panel">
        <div className="ctrl-panel-header">
          <div className="ctrl-panel-title">
            <History size={16} />
            <span>Controller Transition Audit Trail & Consensus Log</span>
          </div>

          <div className="ctrl-panel-actions">
            <button
              type="button"
              className="btn-console btn-sm"
              onClick={onRefresh}
              title="Refresh audit events"
            >
              <RotateCw size={12} />
              <span>Refresh</span>
            </button>
            <button
              type="button"
              className="btn-console btn-sm"
              onClick={handleExportJson}
              title="Export append-only audit trail to JSON"
            >
              <Download size={12} />
              <span>Export Audit Trail</span>
            </button>
          </div>
        </div>

        {/* Filter Bar */}
        <div className="ctrl-inspector-filter-bar">
          <div className="ctrl-filter-group">
            <span className="ctrl-filter-label">Severity:</span>
            <select
              className="ctrl-select"
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value)}
            >
              <option value="ALL">All Severities</option>
              <option value="INFO">INFO</option>
              <option value="WARNING">WARNING</option>
              <option value="CRITICAL">CRITICAL</option>
            </select>
          </div>

          <div className="ctrl-filter-group">
            <span className="ctrl-filter-label">Subsystem:</span>
            <select
              className="ctrl-select"
              value={subsystemFilter}
              onChange={(e) => setSubsystemFilter(e.target.value)}
            >
              <option value="ALL">All Subsystems</option>
              <option value="CONTROLLER">CONTROLLER</option>
              <option value="LEASE">LEASE</option>
              <option value="QUORUM">QUORUM</option>
              <option value="ROUTE">ROUTE</option>
              <option value="REPLICATION">REPLICATION</option>
              <option value="FENCING">FENCING</option>
            </select>
          </div>

          <div className="ctrl-filter-group" style={{ flex: 1, minWidth: '180px' }}>
            <input
              type="text"
              placeholder="Search transition, reason, or subsystem..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="ctrl-search-input"
              style={{ width: '100%' }}
            />
          </div>
        </div>

        {/* Audit Events Table */}
        <div className="ctrl-panel-body" style={{ padding: 0 }}>
          <div className="ctrl-table-wrapper" style={{ maxHeight: '600px', overflowY: 'auto' }}>
            <table className="ctrl-table">
              <thead>
                <tr>
                  <th style={{ width: '28px' }} />
                  <th>Timestamp</th>
                  <th>Severity</th>
                  <th>Subsystem</th>
                  <th>State Machine Transition</th>
                  <th>Reason / Cause</th>
                  <th>Sim Time</th>
                </tr>
              </thead>
              <tbody>
                {filteredEvents.length > 0 ? (
                  filteredEvents.map((ev) => {
                    const isExpanded = expandedRowId === ev.id;
                    const isCrit = ev.severity === 'CRITICAL';
                    const isWarn = ev.severity === 'WARNING';

                    return (
                      <React.Fragment key={ev.id}>
                        <tr
                          style={{ cursor: 'pointer' }}
                          onClick={() => toggleExpand(ev.id)}
                          className={isExpanded ? 'active-row' : ''}
                        >
                          {/* Expansion arrow */}
                          <td style={{ textAlign: 'center', color: 'var(--text-muted)' }}>
                            {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                          </td>

                          {/* Timestamp */}
                          <td className="font-mono text-xs">
                            <span title={ev.wall_clock_timestamp}>
                              {formatRelativeTime(ev.wall_clock_timestamp)}
                            </span>
                          </td>

                          {/* Severity */}
                          <td>
                            <span
                              className={`badge-tag-sm font-mono ${
                                isCrit
                                  ? 'badge-danger'
                                  : isWarn
                                  ? 'badge-warning'
                                  : 'badge-info'
                              }`}
                            >
                              {ev.severity}
                            </span>
                          </td>

                          {/* Subsystem */}
                          <td>
                            <span className="badge-tag-sm font-mono">
                              {ev.subsystem}
                            </span>
                          </td>

                          {/* Transition */}
                          <td className="font-mono font-semibold" style={{ color: 'var(--text-bright)' }}>
                            {ev.transition}
                          </td>

                          {/* Reason */}
                          <td style={{ maxWidth: '380px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            <span title={ev.reason}>{ev.reason}</span>
                          </td>

                          {/* Sim Time */}
                          <td className="font-mono text-xs text-muted">
                            +{ev.simulated_time_seconds?.toFixed(1) || 0}s
                          </td>
                        </tr>

                        {/* Expanded details row */}
                        {isExpanded && (
                          <tr>
                            <td colSpan={7} style={{ background: '#0a0d14', padding: '0.85rem 1.25rem' }}>
                              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', fontSize: '0.78rem' }}>
                                <div>
                                  <strong className="text-flow">Detailed Audit Record:</strong> {ev.reason}
                                </div>
                                {ev.details && Object.keys(ev.details).length > 0 && (
                                  <div>
                                    <div className="text-muted" style={{ marginBottom: '4px' }}>Evaluation Gate Metadata:</div>
                                    <pre
                                      style={{
                                        background: '#040608',
                                        padding: '0.5rem',
                                        borderRadius: '4px',
                                        overflowX: 'auto',
                                        fontFamily: 'var(--font-mono)',
                                        fontSize: '0.72rem',
                                        color: '#38bdf8',
                                      }}
                                    >
                                      {JSON.stringify(ev.details, null, 2)}
                                    </pre>
                                  </div>
                                )}
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })
                ) : (
                  <tr>
                    <td colSpan={7} style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>
                      No audit events recorded yet. Failover actions or consensus votes will appear here in chronological order.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};
