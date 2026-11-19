import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
  Play,
  Pause,
  Trash2,
  Download,
  Activity,
} from 'lucide-react';
import { controllerClient } from '../../api/controllerClient';
import type { TrafficEventItemDto } from '../../api/controllerClient';
import { formatBytes, formatLatency } from './formatters';

interface ControllerLiveInspectorTabProps {
  isBackendConnected: boolean;
}

const MAX_EVENT_BUFFER = 250;

export const ControllerLiveInspectorTab: React.FC<ControllerLiveInspectorTabProps> = ({
  isBackendConnected,
}) => {
  const [events, setEvents] = useState<TrafficEventItemDto[]>([]);
  const [isPaused, setIsPaused] = useState(false);
  const [regionFilter, setRegionFilter] = useState('ALL');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [categoryFilter, setCategoryFilter] = useState('ALL');
  const [methodFilter, setMethodFilter] = useState('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const isPausedRef = useRef(isPaused);

  useEffect(() => {
    isPausedRef.current = isPaused;
  }, [isPaused]);

  // Initial event page fetch
  useEffect(() => {
    let mounted = true;
    controllerClient.fetchTrafficEvents(1, 50).then((res) => {
      if (mounted && res && res.events) {
        setEvents(res.events);
      }
    });

    // Subscribe to Controller SSE stream
    const unsubscribe = controllerClient.subscribeControllerTrafficStream(
      undefined,
      (ev) => {
        if (isPausedRef.current) return;
        setEvents((prev) => {
          const next = [ev, ...prev];
          return next.length > MAX_EVENT_BUFFER ? next.slice(0, MAX_EVENT_BUFFER) : next;
        });
      }
    );

    return () => {
      mounted = false;
      unsubscribe();
    };
  }, []);

  const handleClear = () => {
    setEvents([]);
  };

  const handleExportJson = () => {
    const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(events, null, 2));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute('href', dataStr);
    downloadAnchor.setAttribute('download', `controller-events-${Date.now()}.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  const filteredEvents = useMemo(() => {
    return events.filter((ev) => {
      if (regionFilter !== 'ALL' && ev.served_region !== regionFilter && ev.client_region !== regionFilter) {
        return false;
      }
      if (methodFilter !== 'ALL' && ev.method !== methodFilter) {
        return false;
      }
      if (categoryFilter !== 'ALL' && ev.request_type !== categoryFilter) {
        return false;
      }
      if (statusFilter !== 'ALL') {
        const code = ev.status_code;
        if (statusFilter === '2xx' && (code < 200 || code >= 300)) return false;
        if (statusFilter === '3xx' && (code < 300 || code >= 400)) return false;
        if (statusFilter === '4xx' && (code < 400 || code >= 500)) return false;
        if (statusFilter === '429' && code !== 429) return false;
        if (statusFilter === '5xx' && code < 500) return false;
      }
      if (searchQuery.trim() !== '') {
        const q = searchQuery.toLowerCase();
        const matches =
          ev.endpoint.toLowerCase().includes(q) ||
          ev.request_id.toLowerCase().includes(q) ||
          ev.client_region.toLowerCase().includes(q) ||
          ev.served_region.toLowerCase().includes(q);
        if (!matches) return false;
      }
      return true;
    });
  }, [events, regionFilter, statusFilter, categoryFilter, methodFilter, searchQuery]);

  return (
    <div className="controller-tab-pane">
      <div className="ctrl-panel">
        <div className="ctrl-panel-header">
          <div className="ctrl-panel-title">
            <Activity size={16} />
            <span>Live Request Telemetry Inspector</span>
            {isBackendConnected && !isPaused ? (
              <span className="badge-tag-sm badge-healthy">
                <span className="pulse-indicator pulse-green" />
                <span>LIVE STREAM</span>
              </span>
            ) : isPaused ? (
              <span className="badge-tag-sm badge-warning">PAUSED</span>
            ) : (
              <span className="badge-tag-sm badge-danger">DISCONNECTED</span>
            )}
          </div>

          <div className="ctrl-panel-actions">
            <button
              type="button"
              className={`btn-console btn-sm ${isPaused ? 'btn-primary' : ''}`}
              onClick={() => setIsPaused(!isPaused)}
            >
              {isPaused ? <Play size={12} /> : <Pause size={12} />}
              <span>{isPaused ? 'Resume' : 'Pause'}</span>
            </button>

            <button
              type="button"
              className="btn-console btn-sm"
              onClick={handleClear}
              title="Clear event buffer"
            >
              <Trash2 size={12} />
              <span>Clear</span>
            </button>

            <button
              type="button"
              className="btn-console btn-sm"
              onClick={handleExportJson}
              title="Export captured events to JSON file"
            >
              <Download size={12} />
              <span>Export</span>
            </button>
          </div>
        </div>

        {/* Filter Bar */}
        <div className="ctrl-inspector-filter-bar">
          {/* Region filter */}
          <div className="ctrl-filter-group">
            <span className="ctrl-filter-label">Region:</span>
            <select
              className="ctrl-select"
              value={regionFilter}
              onChange={(e) => setRegionFilter(e.target.value)}
            >
              <option value="ALL">All Regions</option>
              <option value="region-a">Region A (Mumbai)</option>
              <option value="region-b">Region B (Singapore)</option>
              <option value="region-c">Region C (Frankfurt)</option>
              <option value="region-d">Region D (Virginia)</option>
              <option value="region-e">Region E (São Paulo)</option>
            </select>
          </div>

          {/* Status filter */}
          <div className="ctrl-filter-group">
            <span className="ctrl-filter-label">Status:</span>
            <select
              className="ctrl-select"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="ALL">All Statuses</option>
              <option value="2xx">2xx Success</option>
              <option value="3xx">3xx Redirect</option>
              <option value="4xx">4xx Client Error</option>
              <option value="429">429 Rate-Limited</option>
              <option value="5xx">5xx Server Error</option>
            </select>
          </div>

          {/* Request Category filter */}
          <div className="ctrl-filter-group">
            <span className="ctrl-filter-label">Category:</span>
            <select
              className="ctrl-select"
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
            >
              <option value="ALL">All Categories</option>
              <option value="write">Write Operations</option>
              <option value="strong_read">Strong Read</option>
              <option value="eventual_read">Eventual Read</option>
              <option value="system">System / Health</option>
            </select>
          </div>

          {/* HTTP Method filter */}
          <div className="ctrl-filter-group">
            <span className="ctrl-filter-label">Method:</span>
            <select
              className="ctrl-select"
              value={methodFilter}
              onChange={(e) => setMethodFilter(e.target.value)}
            >
              <option value="ALL">All Methods</option>
              <option value="GET">GET</option>
              <option value="POST">POST</option>
              <option value="PUT">PUT</option>
              <option value="DELETE">DELETE</option>
            </select>
          </div>

          {/* Text search */}
          <div className="ctrl-filter-group" style={{ flex: 1, minWidth: '180px' }}>
            <input
              type="text"
              placeholder="Search request ID, URL endpoint..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="ctrl-search-input"
              style={{ width: '100%' }}
            />
          </div>
        </div>

        {/* Live Events Table */}
        <div className="ctrl-panel-body" style={{ padding: 0 }}>
          <div className="ctrl-table-wrapper" style={{ maxHeight: '600px', overflowY: 'auto' }}>
            <table className="ctrl-table">
              <thead style={{ position: 'sticky', top: 0, zIndex: 5 }}>
                <tr>
                  <th>Timestamp</th>
                  <th>Request ID</th>
                  <th>Method</th>
                  <th>Normalized Endpoint</th>
                  <th>Client Region</th>
                  <th>Served Region</th>
                  <th>Status</th>
                  <th>Ingress Payload</th>
                  <th>Egress Payload</th>
                  <th>Latency</th>
                </tr>
              </thead>
              <tbody>
                {filteredEvents.length > 0 ? (
                  filteredEvents.map((ev, idx) => {
                    const isSuccess = ev.status_code >= 200 && ev.status_code < 400;
                    const is429 = ev.status_code === 429;
                    const is5xx = ev.status_code >= 500;

                    return (
                      <tr key={ev.id || `${ev.request_id}-${idx}`}>
                        {/* Timestamp */}
                        <td className="font-mono text-xs text-muted">
                          {new Date(ev.timestamp).toLocaleTimeString()}
                        </td>

                        {/* Request ID */}
                        <td className="font-mono text-xs">
                          <span style={{ color: '#38bdf8' }}>{ev.request_id}</span>
                        </td>

                        {/* Method */}
                        <td>
                          <span
                            className="badge-tag-sm font-mono"
                            style={{
                              background: ev.method === 'POST' ? 'rgba(245, 158, 11, 0.15)' : 'var(--bg-subtle)',
                              color: ev.method === 'POST' ? '#f59e0b' : 'var(--text-primary)',
                            }}
                          >
                            {ev.method}
                          </span>
                        </td>

                        {/* Endpoint */}
                        <td className="font-mono text-xs" style={{ maxWidth: '240px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          <span title={ev.endpoint}>{ev.endpoint}</span>
                        </td>

                        {/* Client Region */}
                        <td className="font-mono text-xs text-muted">
                          {ev.client_region}
                        </td>

                        {/* Served Region */}
                        <td>
                          <span className="badge-tag-sm badge-info font-mono">
                            {ev.served_region}
                          </span>
                        </td>

                        {/* Response Status */}
                        <td>
                          <span
                            className={`badge-tag-sm font-mono ${isSuccess
                              ? 'badge-healthy'
                              : is429
                                ? 'badge-warning'
                                : is5xx
                                  ? 'badge-danger'
                                  : 'badge-danger'
                              }`}
                          >
                            {ev.status_code}
                          </span>
                        </td>

                        {/* Payload Ingress Bytes */}
                        <td className="font-mono text-xs text-flow">
                          {formatBytes(ev.payload_ingress_bytes)}
                        </td>

                        {/* Payload Egress Bytes */}
                        <td className="font-mono text-xs text-healthy">
                          {formatBytes(ev.payload_egress_bytes)}
                        </td>

                        {/* Latency */}
                        <td className="font-mono text-xs">
                          {formatLatency(ev.duration_ms)}
                        </td>
                      </tr>
                    );
                  })
                ) : (
                  <tr>
                    <td colSpan={10} style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>
                      {events.length === 0
                        ? 'No live traffic events recorded yet. Perform actions in the Online Store to stream requests.'
                        : 'No events match the current filter criteria.'}
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
