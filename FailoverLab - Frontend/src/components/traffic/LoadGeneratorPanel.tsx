import React, { useState, useRef } from 'react';
import { Play, Square, Gauge } from 'lucide-react';

type RequestType = 'catalog' | 'product_detail' | 'order_create';
type BurstSize = 1 | 10 | 25 | 50 | 100;

const BURST_SIZES: BurstSize[] = [1, 10, 25, 50, 100];

const CLIENT_REGIONS = [
  { id: 'ap-south-1', name: 'Mumbai (ap-south-1)', code: '[IN]' },
  { id: 'ap-southeast-1', name: 'Singapore (ap-southeast-1)', code: '[SG]' },
  { id: 'eu-central-1', name: 'Frankfurt (eu-central-1)', code: '[DE]' },
  { id: 'us-east-1', name: 'Virginia (us-east-1)', code: '[US]' },
  { id: 'sa-east-1', name: 'São Paulo (sa-east-1)', code: '[BR]' },
];

export const LoadGeneratorPanel: React.FC = () => {
  const [requestType, setRequestType] = useState<RequestType>('catalog');
  const [burstSize, setBurstSize] = useState<BurstSize>(10);
  const [clientRegion, setClientRegion] = useState<string>('eu-central-1');
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [progress, setProgress] = useState<{ current: number; total: number }>({ current: 0, total: 0 });

  // Metrics
  const [metrics, setMetrics] = useState<{
    sent: number;
    success: number;
    rateLimited: number;
    failed: number;
    avgLatency: number;
    p95Latency: number;
    regionDistribution: Record<string, number>;
  }>({
    sent: 0,
    success: 0,
    rateLimited: 0,
    failed: 0,
    avgLatency: 0,
    p95Latency: 0,
    regionDistribution: {
      'region-a': 0,
      'region-b': 0,
      'region-c': 0,
      'region-d': 0,
      'region-e': 0,
    },
  });

  const abortControllerRef = useRef<AbortController | null>(null);

  const handleStart = async () => {
    if (isRunning) return;

    setIsRunning(true);
    const controller = new AbortController();
    abortControllerRef.current = controller;

    const total = burstSize;
    setProgress({ current: 0, total });

    let sent = 0;
    let success = 0;
    let rateLimited = 0;
    let failed = 0;
    const latencies: number[] = [];
    const regionDist: Record<string, number> = {
      'region-a': 0,
      'region-b': 0,
      'region-c': 0,
      'region-d': 0,
      'region-e': 0,
    };

    const runSingleRequest = async (i: number) => {
      if (controller.signal.aborted) return;

      let url = '/api/ecommerce/products';
      let method = 'GET';
      let body: string | undefined = undefined;

      if (requestType === 'product_detail') {
        url = '/api/ecommerce/products/prod-laptop-01';
      } else if (requestType === 'order_create') {
        url = '/api/ecommerce/orders';
        method = 'POST';
        body = JSON.stringify({
          product_id: 'prod-laptop-01',
          quantity: 1,
          items: [{ product_id: 'prod-laptop-01', quantity: 1 }],
          customer_name: `Load Test Customer ${i}`,
          customer_email: `loadgen-${Date.now()}-${i}@example.com`,
          shipping_address: '100 Gateway Blvd, Cloud Zone',
          client_region: clientRegion,
        });
      }

      const headers: Record<string, string> = {
        'X-Client-Region': clientRegion,
        'X-Client-ID': 'load-generator-harness',
        'X-Request-ID': `burst-${Date.now().toString(36)}-${i}-${Math.random().toString(36).substring(2, 7)}`,
      };
      if (requestType === 'order_create') {
        // Generate a fresh, unique idempotency key for each logically distinct order request
        headers['Idempotency-Key'] = `idem-load-${Date.now().toString(36)}-${i}-${Math.random().toString(36).substring(2, 9)}`;
      }
      if (body) {
        headers['Content-Type'] = 'application/json';
      }

      const t0 = performance.now();
      try {
        const res = await fetch(url, {
          method,
          headers,
          body,
          signal: controller.signal,
        });

        const elapsed = performance.now() - t0;
        latencies.push(elapsed);
        sent += 1;

        if (res.status >= 200 && res.status < 300) {
          success += 1;
        } else if (res.status === 429) {
          rateLimited += 1;
        } else {
          failed += 1;
        }

        const servedRegion =
          res.headers.get('X-Served-Region') ||
          res.headers.get('X-Routed-To-Region') ||
          'region-a';
        if (regionDist[servedRegion] !== undefined) {
          regionDist[servedRegion] += 1;
        } else {
          regionDist[servedRegion] = 1;
        }
      } catch (err: any) {
        if (err.name === 'AbortError') return;
        const elapsed = performance.now() - t0;
        latencies.push(elapsed);
        sent += 1;
        failed += 1;
      } finally {
        setProgress({ current: sent, total });

        // Update running stats
        const avg = latencies.length > 0 ? latencies.reduce((a, b) => a + b, 0) / latencies.length : 0;
        const sorted = [...latencies].sort((a, b) => a - b);
        const p95 = sorted.length > 0 ? sorted[Math.min(Math.floor(sorted.length * 0.95), sorted.length - 1)] : 0;

        setMetrics({
          sent,
          success,
          rateLimited,
          failed,
          avgLatency: Math.round(avg),
          p95Latency: Math.round(p95),
          regionDistribution: { ...regionDist },
        });
      }
    };

    // Concurrency control: batches of 5
    const batchSize = 5;
    for (let i = 0; i < total; i += batchSize) {
      if (controller.signal.aborted) break;
      const currentBatch = [];
      for (let j = i; j < Math.min(i + batchSize, total); j++) {
        currentBatch.push(runSingleRequest(j + 1));
      }
      await Promise.all(currentBatch);
    }

    setIsRunning(false);
    abortControllerRef.current = null;
  };

  const handleStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsRunning(false);
  };

  const percentComplete = progress.total > 0 ? Math.round((progress.current / progress.total) * 100) : 0;
  const totalCompleted = metrics.success + metrics.rateLimited + metrics.failed;

  return (
    <div className="traffic-panel">
      <div className="traffic-panel-header">
        <h3>
          <Gauge size={18} className="text-flow" />
          <span>Controlled Traffic Load Generator</span>
        </h3>
        <span className="font-mono text-xs text-muted">
          Real Gateway Execution · Max 100 Requests
        </span>
      </div>

      <div className="load-gen-controls">
        <div className="load-gen-options-row">
          {/* Request Type */}
          <div>
            <label className="block text-xs font-semibold text-muted mb-1">Request Profile</label>
            <select
              className="monitor-filter-select w-full"
              value={requestType}
              onChange={(e) => setRequestType(e.target.value as RequestType)}
              disabled={isRunning}
            >
              <option value="catalog">Eventual Read (Product Catalog)</option>
              <option value="product_detail">Eventual Read (Product Detail)</option>
              <option value="order_create">Write / Mutation (Create Order)</option>
            </select>
          </div>

          {/* Client Origin Region */}
          <div>
            <label className="block text-xs font-semibold text-muted mb-1">Simulated Client Region</label>
            <select
              className="monitor-filter-select w-full"
              value={clientRegion}
              onChange={(e) => setClientRegion(e.target.value)}
              disabled={isRunning}
            >
              {CLIENT_REGIONS.map((cr) => (
                <option key={cr.id} value={cr.id}>
                  {cr.code} {cr.name}
                </option>
              ))}
            </select>
          </div>

          {/* Burst Size */}
          <div>
            <label className="block text-xs font-semibold text-muted mb-1">Burst Volume</label>
            <div className="load-btn-group">
              {BURST_SIZES.map((sz) => (
                <button
                  key={sz}
                  className={`load-size-btn ${burstSize === sz ? 'active' : ''}`}
                  onClick={() => setBurstSize(sz)}
                  disabled={isRunning}
                >
                  {sz}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Action Button Row */}
        <div className="flex items-center justify-between pt-2">
          <div className="flex items-center gap-3">
            {!isRunning ? (
              <button className="btn-console btn-primary btn-sm" onClick={handleStart}>
                <Play size={14} />
                <span>Launch {burstSize} Requests</span>
              </button>
            ) : (
              <button className="btn-console btn-danger btn-sm" onClick={handleStop}>
                <Square size={14} />
                <span>Stop Burst Cleanly</span>
              </button>
            )}

            {isRunning && (
              <span className="font-mono text-xs text-flow animate-pulse">
                Executing against Gateway... ({progress.current}/{progress.total})
              </span>
            )}
          </div>

          <div className="font-mono text-xs text-muted">
            {percentComplete}% Completed
          </div>
        </div>

        {/* Progress Bar */}
        <div className="progress-track">
          <div className="progress-bar-fill" style={{ width: `${percentComplete}%` }} />
        </div>

        {/* Metrics Grid */}
        <div className="rate-metrics-grid">
          <div className="rate-metric-card">
            <div className="val text-flow">{metrics.sent}</div>
            <div className="lbl">Total Sent</div>
          </div>

          <div className="rate-metric-card">
            <div className="val text-healthy">{metrics.success}</div>
            <div className="lbl">Success (2xx)</div>
          </div>

          <div className="rate-metric-card">
            <div className="val text-warning">{metrics.rateLimited}</div>
            <div className="lbl">Rate Limited (429)</div>
          </div>

          <div className="rate-metric-card">
            <div className="val text-danger">{metrics.failed}</div>
            <div className="lbl">Failed (5xx)</div>
          </div>

          <div className="rate-metric-card">
            <div className="val text-bright">{metrics.avgLatency} ms</div>
            <div className="lbl">Avg Latency</div>
          </div>

          <div className="rate-metric-card">
            <div className="val text-bright">{metrics.p95Latency} ms</div>
            <div className="lbl">P95 Latency</div>
          </div>
        </div>

        {/* Per-Region Distribution */}
        {totalCompleted > 0 && (
          <div className="mt-2 bg-slate-900/60 p-3 rounded border border-slate-700/60">
            <span className="text-xs font-semibold text-muted block mb-2">
              Served Region Distribution:
            </span>
            <div className="region-dist-bars">
              {Object.entries(metrics.regionDistribution).map(([rid, count]) => {
                const pct = totalCompleted > 0 ? Math.round((count / totalCompleted) * 100) : 0;
                return (
                  <div key={rid} className="dist-bar-row">
                    <span className="w-20 text-muted">{rid}:</span>
                    <div className="dist-bar-track">
                      <div className="dist-bar-fill" style={{ width: `${pct}%` }} />
                    </div>
                    <span className="w-16 text-right font-bold text-flow">
                      {count} ({pct}%)
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
