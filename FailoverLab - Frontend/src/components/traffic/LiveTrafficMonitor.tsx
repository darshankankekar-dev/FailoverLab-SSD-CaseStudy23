import React, { useState, useEffect, useMemo, useRef } from 'react';
import { Activity, Play, Pause, Trash2 } from 'lucide-react';
import { controllerClient } from '../../api/controllerClient';
import type { TrafficEvent } from '../../api/controllerClient';

const MAX_BUFFER_EVENTS = 150;

export const LiveTrafficMonitor: React.FC = () => {
  const [events, setEvents] = useState<TrafficEvent[]>([]);
  const [isPaused, setIsPaused] = useState(false);
  const [methodFilter, setMethodFilter] = useState('ALL');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [decisionFilter, setDecisionFilter] = useState('ALL');
  const [regionFilter, setRegionFilter] = useState('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const isPausedRef = useRef(isPaused);

  useEffect(() => {
    isPausedRef.current = isPaused;
  }, [isPaused]);

  // Initial history load
  useEffect(() => {
    let mounted = true;
    controllerClient.fetchTrafficHistory(50).then((hist) => {
      if (mounted && hist.length > 0) {
        setEvents(hist.slice(-MAX_BUFFER_EVENTS));
      }
    });

    // Subscribe to SSE event stream
    const unsubscribe = controllerClient.subscribeTrafficEvents((ev) => {
      if (isPausedRef.current) return;
      setEvents((prev) => {
        const next = [...prev, ev];
        return next.length > MAX_BUFFER_EVENTS ? next.slice(-MAX_BUFFER_EVENTS) : next;
      });
    });

    return () => {
      mounted = false;
      unsubscribe();
    };
  }, []);

  const handleClear = () => {
    setEvents([]);
  };

  const filteredEvents = useMemo(() => {
    return events.filter((ev) => {
      if (methodFilter !== 'ALL' && ev.method !== methodFilter) return false;
      if (decisionFilter !== 'ALL' && ev.rate_limiter_decision !== decisionFilter) return false;
      if (regionFilter !== 'ALL' && ev.served_region !== regionFilter) return false;

      if (statusFilter !== 'ALL') {
        if (statusFilter === '2xx' && (ev.status_code < 200 || ev.status_code >= 300)) return false;
        if (statusFilter === '429' && ev.status_code !== 429) return false;
        if (statusFilter === '5xx' && ev.status_code < 500) return false;
      }

      if (searchQuery.trim() !== '') {
        const query = searchQuery.toLowerCase();
        const matches =
          ev.endpoint.toLowerCase().includes(query) ||
          ev.request_id.toLowerCase().includes(query) ||
          ev.client_region.toLowerCase().includes(query) ||
          ev.served_region.toLowerCase().includes(query) ||
          ev.request_type.toLowerCase().includes(query);
        if (!matches) return false;
      }

      return true;
    });
  }, [events, methodFilter, statusFilter, decisionFilter, regionFilter, searchQuery]);

  return (
    <div className="traffic-panel">
      <div className="traffic-panel-header">
        <div className="flex items-center gap-2">
          <Activity size={18} className="text-healthy" />
          <h3>Real-Time Live Traffic Monitor (Gateway SSE)</h3>
          {!isPaused ? (
            <span className="badge-tag-sm badge-healthy">
              <span className="pulse-live-indicator" />
              <span>LIVE STREAM</span>
            </span>
          ) : (
            <span className="badge-tag-sm badge-warning">PAUSED</span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            className={`btn-console btn-sm text-xs ${isPaused ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setIsPaused(!isPaused)}
          >
            {isPaused ? <Play size={12} /> : <Pause size={12} />}
            <span>{isPaused ? 'Resume Stream' : 'Pause'}</span>
          </button>
          <button
            className="btn-console btn-ghost btn-sm text-xs"
            onClick={handleClear}
            title="Clear buffer in view"
          >
            <Trash2 size={12} />
            <span>Clear ({events.length})</span>
          </button>
        </div>
      </div>

      {/* Filter Toolbar */}
      <div className="monitor-toolbar">
        <div className="monitor-filters">
          <select
            className="monitor-filter-select"
            value={methodFilter}
            onChange={(e) => setMethodFilter(e.target.value)}
          >
            <option value="ALL">All Methods</option>
            <option value="GET">GET</option>
            <option value="POST">POST</option>
            <option value="DELETE">DELETE</option>
            <option value="PUT">PUT</option>
          </select>

          <select
            className="monitor-filter-select"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="ALL">All Status Codes</option>
            <option value="2xx">2xx OK</option>
            <option value="429">429 Rate Limited</option>
            <option value="5xx">5xx Errors</option>
          </select>

          <select
            className="monitor-filter-select"
            value={decisionFilter}
            onChange={(e) => setDecisionFilter(e.target.value)}
          >
            <option value="ALL">All Rate Decisions</option>
            <option value="accepted">Accepted</option>
            <option value="rejected">Rejected (429)</option>
            <option value="delayed">Delayed / Queued</option>
          </select>

          <select
            className="monitor-filter-select"
            value={regionFilter}
            onChange={(e) => setRegionFilter(e.target.value)}
          >
            <option value="ALL">All Served Regions</option>
            <option value="region-a">region-a (Mumbai)</option>
            <option value="region-b">region-b (Singapore)</option>
            <option value="region-c">region-c (Frankfurt)</option>
            <option value="region-d">region-d (Virginia)</option>
            <option value="region-e">region-e (São Paulo)</option>
          </select>
        </div>

        <div className="flex items-center gap-1">
          <input
            type="text"
            className="monitor-search-input"
            placeholder="Search endpoint / request ID..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
      </div>

      {/* Events Table */}
      <div className="monitor-table-wrap">
        <table className="traffic-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Request ID</th>
              <th>Method</th>
              <th>Endpoint</th>
              <th>Client Region</th>
              <th>Served Region</th>
              <th>Routing Type</th>
              <th>Rate Limiter</th>
              <th>Status</th>
              <th>Actual RTT</th>
              <th>WAN Delay</th>
              <th>Queue Wait</th>
            </tr>
          </thead>
          <tbody>
            {filteredEvents.length === 0 ? (
              <tr>
                <td colSpan={12} className="text-center py-8 text-muted font-mono">
                  No traffic events recorded yet. Trigger requests in the Online Store (/shop) or Load Generator below.
                </td>
              </tr>
            ) : (
              [...filteredEvents].reverse().map((ev) => {
                const timeStr = ev.timestamp ? new Date(ev.timestamp).toLocaleTimeString() : '—';
                const is2xx = ev.status_code >= 200 && ev.status_code < 300;
                const is429 = ev.status_code === 429;
                const is5xx = ev.status_code >= 500;

                return (
                  <tr key={ev.id || `${ev.request_id}-${ev.timestamp}`}>
                    {/* Timestamp */}
                    <td className="font-mono text-xs text-muted">{timeStr}</td>

                    {/* Request ID */}
                    <td className="font-mono text-xs text-bright">{ev.request_id}</td>

                    {/* Method */}
                    <td>
                      <span
                        className={`badge-tag-sm font-mono ${
                          ev.method === 'GET'
                            ? 'badge-info'
                            : ev.method === 'POST'
                            ? 'badge-healthy'
                            : 'badge-danger'
                        }`}
                      >
                        {ev.method}
                      </span>
                    </td>

                    {/* Endpoint */}
                    <td className="font-mono text-xs text-flow">{ev.endpoint}</td>

                    {/* Client Region */}
                    <td className="font-mono text-xs text-secondary">{ev.client_region}</td>

                    {/* Served Region */}
                    <td>
                      <span className="region-code-badge font-mono">{ev.served_region}</span>
                    </td>

                    {/* Routing Type */}
                    <td className="font-mono text-xs">
                      {ev.request_type === 'write' ? (
                        <span className="text-warning font-semibold">WRITE</span>
                      ) : ev.request_type === 'strong_read' ? (
                        <span className="text-flow font-semibold">STRONG READ</span>
                      ) : (
                        <span className="text-secondary">EVENTUAL READ</span>
                      )}
                    </td>

                    {/* Rate Limiter Decision */}
                    <td>
                      {ev.rate_limiter_decision === 'accepted' ? (
                        <span className="badge-tag-sm badge-healthy">Accepted</span>
                      ) : ev.rate_limiter_decision === 'rejected' ? (
                        <span className="badge-tag-sm badge-danger">Throttled</span>
                      ) : (
                        <span className="badge-tag-sm badge-warning">Delayed</span>
                      )}
                    </td>

                    {/* Status Code */}
                    <td className="font-mono font-bold">
                      <span
                        className={
                          is2xx
                            ? 'text-healthy'
                            : is429
                            ? 'text-warning'
                            : is5xx
                            ? 'text-danger'
                            : 'text-muted'
                        }
                      >
                        {ev.status_code}
                      </span>
                    </td>

                    {/* Actual RTT Duration */}
                    <td className="font-mono text-xs font-semibold text-flow">
                      {ev.duration_ms.toFixed(1)} ms
                    </td>

                    {/* Simulated WAN Delay */}
                    <td className="font-mono text-xs text-muted">
                      {ev.simulated_wan_delay_ms > 0 ? `${ev.simulated_wan_delay_ms.toFixed(1)} ms` : '—'}
                    </td>

                    {/* Queue Wait Time */}
                    <td className="font-mono text-xs">
                      {ev.queue_wait_time_ms > 0 ? (
                        <span className="text-warning font-semibold">
                          +{ev.queue_wait_time_ms.toFixed(1)} ms
                        </span>
                      ) : (
                        <span className="text-muted">0 ms</span>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
