import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  ArrowDownLeft,
  ArrowUpRight,
  TrendingUp,
  Gauge,
  CheckCircle2,
} from 'lucide-react';
import { controllerClient } from '../../api/controllerClient';
import type {
  TrafficSummaryDto,
  TrafficTimeseriesPointDto,
} from '../../api/controllerClient';
import {
  formatBytes,
  formatBytesPerSec,
  formatNumber,
  formatLatency,
} from './formatters';

interface ControllerNetworkTrafficTabProps {
  summary: TrafficSummaryDto | null;
  isBackendConnected: boolean;
}

type TimeRangeKey = '1m' | '5m' | '15m' | '1h';

const RANGE_CONFIGS: Record<TimeRangeKey, { seconds: number; step: number; label: string }> = {
  '1m': { seconds: 60, step: 1, label: '1m (1s step)' },
  '5m': { seconds: 300, step: 1, label: '5m (1s step)' },
  '15m': { seconds: 900, step: 5, label: '15m (5s step)' },
  '1h': { seconds: 3600, step: 15, label: '1h (15s step)' },
};

export const ControllerNetworkTrafficTab: React.FC<ControllerNetworkTrafficTabProps> = ({
  summary,
  isBackendConnected,
}) => {
  const [selectedRange, setSelectedRange] = useState<TimeRangeKey>('5m');
  const [timeseries, setTimeseries] = useState<TrafficTimeseriesPointDto[]>([]);
  const [isLoadingChart, setIsLoadingChart] = useState(false);
  const [hoveredPoint, setHoveredPoint] = useState<TrafficTimeseriesPointDto | null>(null);

  const fetchTimeseries = useCallback(async () => {
    const config = RANGE_CONFIGS[selectedRange];
    setIsLoadingChart(true);
    try {
      const res = await controllerClient.fetchTrafficTimeseries(config.seconds, config.step);
      if (res && res.points) {
        setTimeseries(res.points);
      }
    } catch {
      // offline or pending
    } finally {
      setIsLoadingChart(false);
    }
  }, [selectedRange]);

  useEffect(() => {
    fetchTimeseries();
    const interval = setInterval(fetchTimeseries, 3000);
    return () => clearInterval(interval);
  }, [fetchTimeseries]);

  // Compute SVG chart coordinates and paths
  const chartData = useMemo(() => {
    if (!timeseries || timeseries.length === 0) return null;

    const width = 1000;
    const height = 240;
    const padding = { top: 20, right: 30, bottom: 30, left: 60 };

    const plotWidth = width - padding.left - padding.right;
    const plotHeight = height - padding.top - padding.bottom;

    // Find max ingress/egress bytes for Left Y axis
    let maxBytes = 1024; // default minimum scale 1 KB/s
    let maxRps = 5; // default minimum scale 5 req/s

    timeseries.forEach((p) => {
      const ingress = p.client_ingress_bytes_per_sec || 0;
      const egress = p.client_egress_bytes_per_sec || 0;
      const rps = p.requests_per_sec || 0;
      if (ingress > maxBytes) maxBytes = ingress;
      if (egress > maxBytes) maxBytes = egress;
      if (rps > maxRps) maxRps = rps;
    });

    // Add 15% headroom
    maxBytes = maxBytes * 1.15;
    maxRps = maxRps * 1.2;

    const n = timeseries.length;
    const stepX = n > 1 ? plotWidth / (n - 1) : plotWidth;

    const ingressPoints = timeseries.map((p, idx) => {
      const x = padding.left + idx * stepX;
      const y = padding.top + plotHeight - ((p.client_ingress_bytes_per_sec || 0) / maxBytes) * plotHeight;
      return { x, y, point: p };
    });

    const egressPoints = timeseries.map((p, idx) => {
      const x = padding.left + idx * stepX;
      const y = padding.top + plotHeight - ((p.client_egress_bytes_per_sec || 0) / maxBytes) * plotHeight;
      return { x, y, point: p };
    });

    const rpsPoints = timeseries.map((p, idx) => {
      const x = padding.left + idx * stepX;
      const y = padding.top + plotHeight - ((p.requests_per_sec || 0) / maxRps) * plotHeight;
      return { x, y, point: p };
    });

    const ingressPath = ingressPoints.map((pt, i) => `${i === 0 ? 'M' : 'L'} ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`).join(' ');
    const egressPath = egressPoints.map((pt, i) => `${i === 0 ? 'M' : 'L'} ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`).join(' ');
    const rpsPath = rpsPoints.map((pt, i) => `${i === 0 ? 'M' : 'L'} ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`).join(' ');

    // Fill areas for ingress
    const ingressArea = `${ingressPath} L ${padding.left + plotWidth} ${padding.top + plotHeight} L ${padding.left} ${padding.top + plotHeight} Z`;

    return {
      width,
      height,
      padding,
      plotWidth,
      plotHeight,
      maxBytes,
      maxRps,
      ingressPath,
      ingressArea,
      egressPath,
      rpsPath,
      ingressPoints,
    };
  }, [timeseries]);

  const totalRequests = summary?.requests_total ?? 0;
  const s2xx = summary?.status_2xx ?? 0;
  const s3xx = summary?.status_3xx ?? 0;
  const s4xx = summary?.status_4xx ?? 0;
  const s5xx = summary?.status_5xx ?? 0;
  const s429 = summary?.status_429 ?? 0;

  return (
    <div className="controller-tab-pane">
      {/* 4 Dedicated Payload Bandwidth Metric Cards */}
      <div className="ctrl-traffic-metrics-grid">
        {/* Metric 1: Customer Ingress (Store -> Gateway) */}
        <div className="ctrl-traffic-metric-card">
          <div className="ctrl-traffic-metric-header">
            <span className="ctrl-traffic-direction-badge badge-customer-ingress">
              <ArrowDownLeft size={11} style={{ marginRight: '4px', display: 'inline' }} />
              Customer Ingress
            </span>
            <span className="ctrl-traffic-metric-sub">Store → Gateway</span>
          </div>
          <div className="ctrl-traffic-metric-title">Client Request Payload</div>
          <div className="ctrl-traffic-rate-val text-flow">
            {summary ? formatBytesPerSec(summary.client_ingress_bytes_per_sec) : '0.0 B/s'}
          </div>
          <div className="ctrl-traffic-cumulative-box">
            <span className="text-muted">Cumulative Payload</span>
            <span className="font-mono font-bold text-flow">
              {summary ? formatBytes(summary.client_ingress_bytes_total) : '0 B'}
            </span>
          </div>
        </div>

        {/* Metric 2: Customer Egress (Gateway -> Store) */}
        <div className="ctrl-traffic-metric-card">
          <div className="ctrl-traffic-metric-header">
            <span className="ctrl-traffic-direction-badge badge-customer-egress">
              <ArrowUpRight size={11} style={{ marginRight: '4px', display: 'inline' }} />
              Customer Egress
            </span>
            <span className="ctrl-traffic-metric-sub">Gateway → Store</span>
          </div>
          <div className="ctrl-traffic-metric-title">Client Response Payload</div>
          <div className="ctrl-traffic-rate-val text-healthy">
            {summary ? formatBytesPerSec(summary.client_egress_bytes_per_sec) : '0.0 B/s'}
          </div>
          <div className="ctrl-traffic-cumulative-box">
            <span className="text-muted">Cumulative Payload</span>
            <span className="font-mono font-bold text-healthy">
              {summary ? formatBytes(summary.client_egress_bytes_total) : '0 B'}
            </span>
          </div>
        </div>

        {/* Metric 3: Upstream Egress (Gateway -> Regional Services) */}
        <div className="ctrl-traffic-metric-card">
          <div className="ctrl-traffic-metric-header">
            <span className="ctrl-traffic-direction-badge badge-upstream-egress">
              <ArrowUpRight size={11} style={{ marginRight: '4px', display: 'inline' }} />
              Upstream Egress
            </span>
            <span className="ctrl-traffic-metric-sub">Gateway → Regional</span>
          </div>
          <div className="ctrl-traffic-metric-title">Backend Forward Payload</div>
          <div className="ctrl-traffic-rate-val" style={{ color: '#fbbf24' }}>
            {summary ? formatBytesPerSec(summary.upstream_egress_bytes_per_sec) : '0.0 B/s'}
          </div>
          <div className="ctrl-traffic-cumulative-box">
            <span className="text-muted">Cumulative Payload</span>
            <span className="font-mono font-bold" style={{ color: '#fbbf24' }}>
              {summary ? formatBytes(summary.upstream_egress_bytes_total) : '0 B'}
            </span>
          </div>
        </div>

        {/* Metric 4: Upstream Ingress (Regional Services -> Gateway) */}
        <div className="ctrl-traffic-metric-card">
          <div className="ctrl-traffic-metric-header">
            <span className="ctrl-traffic-direction-badge badge-upstream-ingress">
              <ArrowDownLeft size={11} style={{ marginRight: '4px', display: 'inline' }} />
              Upstream Ingress
            </span>
            <span className="ctrl-traffic-metric-sub">Regional → Gateway</span>
          </div>
          <div className="ctrl-traffic-metric-title">Backend Response Payload</div>
          <div className="ctrl-traffic-rate-val text-primary">
            {summary ? formatBytesPerSec(summary.upstream_ingress_bytes_per_sec) : '0.0 B/s'}
          </div>
          <div className="ctrl-traffic-cumulative-box">
            <span className="text-muted">Cumulative Payload</span>
            <span className="font-mono font-bold text-primary">
              {summary ? formatBytes(summary.upstream_ingress_bytes_total) : '0 B'}
            </span>
          </div>
        </div>
      </div>

      {/* Interactive Time-Series Throughput Chart */}
      <div className="ctrl-panel">
        <div className="ctrl-panel-header">
          <div className="ctrl-panel-title">
            <TrendingUp size={16} />
            <span>Real-Time Traffic Throughput & Request Rate Time-Series</span>
            {isLoadingChart && (
              <span className="text-muted text-xs font-mono" style={{ marginLeft: '6px' }}>
                (syncing...)
              </span>
            )}
            {!isBackendConnected && (
              <span className="badge-tag-sm badge-danger" style={{ marginLeft: '6px' }}>
                OFFLINE
              </span>
            )}
          </div>

          <div className="ctrl-chart-controls">
            {/* Legend */}
            <div className="ctrl-chart-legend">
              <div className="ctrl-legend-item">
                <span className="ctrl-legend-color" style={{ background: '#0ea5e9' }} />
                <span>Ingress Throughput (B/s)</span>
              </div>
              <div className="ctrl-legend-item">
                <span className="ctrl-legend-color" style={{ background: '#10b981' }} />
                <span>Egress Throughput (B/s)</span>
              </div>
              <div className="ctrl-legend-item">
                <span className="ctrl-legend-color" style={{ background: '#f59e0b' }} />
                <span>Request Rate (req/s)</span>
              </div>
            </div>

            {/* Range Selector Buttons */}
            <div className="ctrl-range-selector">
              {(['1m', '5m', '15m', '1h'] as TimeRangeKey[]).map((r) => (
                <button
                  key={r}
                  type="button"
                  className={`ctrl-range-btn ${selectedRange === r ? 'active' : ''}`}
                  onClick={() => setSelectedRange(r)}
                >
                  {r}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="ctrl-panel-body">
          <div className="ctrl-svg-chart-wrapper">
            {chartData ? (
              <svg
                viewBox={`0 0 ${chartData.width} ${chartData.height}`}
                className="ctrl-svg-chart"
                preserveAspectRatio="none"
              >
                <defs>
                  <linearGradient id="ingressGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#0ea5e9" stopOpacity="0.25" />
                    <stop offset="100%" stopColor="#0ea5e9" stopOpacity="0.0" />
                  </linearGradient>
                </defs>

                {/* Horizontal Grid lines */}
                {[0, 0.25, 0.5, 0.75, 1].map((pct, i) => {
                  const y = chartData.padding.top + chartData.plotHeight * pct;
                  const byteVal = chartData.maxBytes * (1 - pct);
                  return (
                    <g key={i}>
                      <line
                        x1={chartData.padding.left}
                        y1={y}
                        x2={chartData.width - chartData.padding.right}
                        y2={y}
                        stroke="#1c2333"
                        strokeDasharray="4 4"
                      />
                      <text
                        x={chartData.padding.left - 8}
                        y={y + 4}
                        fill="#64748b"
                        fontSize="10"
                        fontFamily="var(--font-mono)"
                        textAnchor="end"
                      >
                        {formatBytesPerSec(byteVal, 0)}
                      </text>
                    </g>
                  );
                })}

                {/* Area Fill for Ingress */}
                <path d={chartData.ingressArea} fill="url(#ingressGrad)" />

                {/* Ingress Line (Cyan) */}
                <path
                  d={chartData.ingressPath}
                  fill="none"
                  stroke="#0ea5e9"
                  strokeWidth="2"
                  strokeLinecap="round"
                />

                {/* Egress Line (Green) */}
                <path
                  d={chartData.egressPath}
                  fill="none"
                  stroke="#10b981"
                  strokeWidth="2"
                  strokeLinecap="round"
                />

                {/* Request Rate Line (Amber) */}
                <path
                  d={chartData.rpsPath}
                  fill="none"
                  stroke="#f59e0b"
                  strokeWidth="1.75"
                  strokeDasharray="3 3"
                />

                {/* Interactive Points on hover */}
                {chartData.ingressPoints.map((pt, i) => (
                  <circle
                    key={i}
                    cx={pt.x}
                    cy={pt.y}
                    r={hoveredPoint?.timestamp === pt.point.timestamp ? 5 : 2}
                    fill={hoveredPoint?.timestamp === pt.point.timestamp ? '#ffffff' : '#0ea5e9'}
                    stroke="#0284c7"
                    strokeWidth="1.5"
                    style={{ cursor: 'pointer', transition: 'r 0.1s ease' }}
                    onMouseEnter={() => setHoveredPoint(pt.point)}
                    onMouseLeave={() => setHoveredPoint(null)}
                  />
                ))}
              </svg>
            ) : (
              <div
                style={{
                  height: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: 'var(--text-muted)',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.82rem',
                }}
              >
                No traffic samples recorded in the last {selectedRange}. Generating requests will populate this chart.
              </div>
            )}
          </div>

          {/* Hovered point inspector readout */}
          {hoveredPoint && (
            <div
              style={{
                marginTop: '0.5rem',
                padding: '0.45rem 0.75rem',
                background: 'var(--bg-panel)',
                borderRadius: '4px',
                display: 'flex',
                gap: '1.25rem',
                fontSize: '0.75rem',
                fontFamily: 'var(--font-mono)',
              }}
            >
              <span className="text-muted">Time: {new Date(hoveredPoint.timestamp).toLocaleTimeString()}</span>
              <span className="text-flow">Ingress: {formatBytesPerSec(hoveredPoint.client_ingress_bytes_per_sec)}</span>
              <span className="text-healthy">Egress: {formatBytesPerSec(hoveredPoint.client_egress_bytes_per_sec)}</span>
              <span style={{ color: '#f59e0b' }}>RPS: {hoveredPoint.requests_per_sec.toFixed(1)} req/s</span>
              <span className="text-muted">P95: {hoveredPoint.latency_p95_ms.toFixed(1)}ms</span>
            </div>
          )}
        </div>
      </div>

      {/* Operational Latency & HTTP Response Breakdown Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.25rem' }}>
        {/* Latency Percentiles Card */}
        <div className="ctrl-panel">
          <div className="ctrl-panel-header">
            <div className="ctrl-panel-title">
              <Gauge size={15} />
              <span>Gateway Proxy Measured Latency</span>
            </div>
            <span className="badge-tag-sm badge-info font-mono">
              Avg: {summary ? formatLatency(summary.latency_avg_ms) : '0.0 ms'}
            </span>
          </div>

          <div className="ctrl-panel-body">
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.75rem' }}>
              <div style={{ padding: '0.75rem', background: 'var(--bg-panel)', borderRadius: '4px', textAlign: 'center' }}>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>P50 Median</div>
                <div style={{ fontSize: '1.35rem', fontWeight: 800, fontFamily: 'var(--font-mono)', color: 'var(--text-bright)' }}>
                  {summary ? formatLatency(summary.latency_p50_ms) : '0.0 ms'}
                </div>
                <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>Nominal experience</div>
              </div>

              <div style={{ padding: '0.75rem', background: 'var(--bg-panel)', borderRadius: '4px', textAlign: 'center' }}>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>P95 Latency</div>
                <div style={{ fontSize: '1.35rem', fontWeight: 800, fontFamily: 'var(--font-mono)', color: '#38bdf8' }}>
                  {summary ? formatLatency(summary.latency_p95_ms) : '0.0 ms'}
                </div>
                <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>SLA critical threshold</div>
              </div>

              <div style={{ padding: '0.75rem', background: 'var(--bg-panel)', borderRadius: '4px', textAlign: 'center' }}>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>P99 Tail</div>
                <div style={{ fontSize: '1.35rem', fontWeight: 800, fontFamily: 'var(--font-mono)', color: '#f59e0b' }}>
                  {summary ? formatLatency(summary.latency_p99_ms) : '0.0 ms'}
                </div>
                <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>Worst 1% tail delay</div>
              </div>
            </div>

            <div style={{ marginTop: '0.75rem', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
              Note: Excludes artificial WAN injection delays; represents actual gateway pipeline duration.
            </div>
          </div>
        </div>

        {/* HTTP Response Status Breakdown Card */}
        <div className="ctrl-panel">
          <div className="ctrl-panel-header">
            <div className="ctrl-panel-title">
              <CheckCircle2 size={15} />
              <span>HTTP Response Code Distribution</span>
            </div>
            <span className="font-mono text-xs text-muted">
              Total: {formatNumber(totalRequests)} requests
            </span>
          </div>

          <div className="ctrl-panel-body">
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '0.5rem', textAlign: 'center' }}>
              {/* 2xx Success */}
              <div style={{ padding: '0.65rem 0.35rem', background: 'var(--bg-panel)', borderRadius: '4px' }}>
                <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>2xx OK</div>
                <div style={{ fontSize: '1.15rem', fontWeight: 700, fontFamily: 'var(--font-mono)' }} className="text-healthy">
                  {formatNumber(s2xx)}
                </div>
              </div>

              {/* 3xx Redirect */}
              <div style={{ padding: '0.65rem 0.35rem', background: 'var(--bg-panel)', borderRadius: '4px' }}>
                <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>3xx Redir</div>
                <div style={{ fontSize: '1.15rem', fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
                  {formatNumber(s3xx)}
                </div>
              </div>

              {/* 4xx Client Error */}
              <div style={{ padding: '0.65rem 0.35rem', background: 'var(--bg-panel)', borderRadius: '4px' }}>
                <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>4xx Client</div>
                <div style={{ fontSize: '1.15rem', fontWeight: 700, fontFamily: 'var(--font-mono)', color: '#f59e0b' }}>
                  {formatNumber(s4xx)}
                </div>
              </div>

              {/* 429 Rate-Limited */}
              <div style={{ padding: '0.65rem 0.35rem', background: 'var(--bg-panel)', borderRadius: '4px' }}>
                <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>429 Limited</div>
                <div style={{ fontSize: '1.15rem', fontWeight: 700, fontFamily: 'var(--font-mono)', color: '#ef4444' }}>
                  {formatNumber(s429)}
                </div>
              </div>

              {/* 5xx Server Error */}
              <div style={{ padding: '0.65rem 0.35rem', background: 'var(--bg-panel)', borderRadius: '4px' }}>
                <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>5xx Server</div>
                <div style={{ fontSize: '1.15rem', fontWeight: 700, fontFamily: 'var(--font-mono)', color: '#ef4444' }}>
                  {formatNumber(s5xx)}
                </div>
              </div>
            </div>

            <div style={{ marginTop: '0.75rem', display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
              <span>Gateway Instance: {summary?.active_gateway_instances?.join(', ') || 'gateway-primary'}</span>
              <span>Telemetry Source: {summary?.measurement_source || 'application_payload'}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
