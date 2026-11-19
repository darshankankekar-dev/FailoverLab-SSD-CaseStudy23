import React, { useState, useEffect } from 'react';
import { Sliders, RefreshCw, RotateCcw, Check, Zap, Hourglass, ShieldOff } from 'lucide-react';
import { controllerClient } from '../../api/controllerClient';
import type { TrafficStatusDto } from '../../api/controllerClient';

interface RateLimiterPanelProps {
  onConfigChanged?: () => void;
}

export const RateLimiterPanel: React.FC<RateLimiterPanelProps> = ({ onConfigChanged }) => {
  const [status, setStatus] = useState<TrafficStatusDto | null>(null);
  const [mode, setMode] = useState<'OFF' | 'TOKEN_BUCKET' | 'LEAKY_BUCKET'>('TOKEN_BUCKET');
  const [tokenCapacity, setTokenCapacity] = useState<number>(10);
  const [tokenRefillRate, setTokenRefillRate] = useState<number>(2.0);
  const [leakyCapacity, setLeakyCapacity] = useState<number>(20);
  const [leakyDrainRate, setLeakyDrainRate] = useState<number>(2.0);
  const [isApplying, setIsApplying] = useState(false);
  const [feedbackMsg, setFeedbackMsg] = useState<string | null>(null);

  const pollStatus = async () => {
    const data = await controllerClient.fetchTrafficStatus();
    if (data) {
      setStatus(data);
      setMode(data.mode);
      if (data.token_bucket) {
        setTokenCapacity(data.token_bucket.capacity);
        setTokenRefillRate(data.token_bucket.refill_rate);
      }
      if (data.leaky_bucket) {
        setLeakyCapacity(data.leaky_bucket.queue_capacity);
        setLeakyDrainRate(data.leaky_bucket.drain_rate);
      }
    }
  };

  useEffect(() => {
    pollStatus();
    const interval = setInterval(pollStatus, 1500);
    return () => clearInterval(interval);
  }, []);

  const handleApplyConfig = async (newMode?: 'OFF' | 'TOKEN_BUCKET' | 'LEAKY_BUCKET') => {
    setIsApplying(true);
    setFeedbackMsg(null);
    const targetMode = newMode || mode;
    try {
      const res = await controllerClient.updateTrafficConfig({
        mode: targetMode,
        token_capacity: tokenCapacity,
        token_refill_rate: tokenRefillRate,
        leaky_capacity: leakyCapacity,
        leaky_drain_rate: leakyDrainRate,
      });
      if (res && res.traffic_control) {
        setStatus(res.traffic_control);
        setMode(res.traffic_control.mode);
      }
      setFeedbackMsg(`Applied: ${targetMode}`);
      onConfigChanged?.();
      setTimeout(() => setFeedbackMsg(null), 3000);
    } catch (err: any) {
      setFeedbackMsg(`Error: ${err.message}`);
    } finally {
      setIsApplying(false);
    }
  };

  const handleReset = async () => {
    try {
      await controllerClient.resetTrafficState();
      await pollStatus();
      setFeedbackMsg('Traffic state reset');
      onConfigChanged?.();
      setTimeout(() => setFeedbackMsg(null), 3000);
    } catch (err: any) {
      setFeedbackMsg(`Reset failed: ${err.message}`);
    }
  };

  const tokensRemaining = status?.token_bucket?.tokens_remaining ?? tokenCapacity;
  const queueDepth = status?.leaky_bucket?.current_queue_depth ?? 0;
  const accepted = status?.common?.accepted_requests ?? 0;
  const throttled = status?.common?.throttled_requests ?? 0;
  const avgWait = status?.leaky_bucket?.average_wait_time_ms ?? 0;

  return (
    <div className="traffic-panel">
      <div className="traffic-panel-header">
        <h3>
          <Sliders size={18} className="text-flow" />
          <span>Gateway Traffic Management & Rate Limiter</span>
        </h3>
        <div className="flex items-center gap-2">
          {feedbackMsg && (
            <span className="text-xs text-healthy font-mono">{feedbackMsg}</span>
          )}
          <button
            className="btn-console btn-ghost btn-sm text-xs"
            onClick={handleReset}
            title="Reset counters and buckets"
          >
            <RotateCcw size={12} />
            <span>Reset Counters</span>
          </button>
        </div>
      </div>

      {/* Mode Switcher */}
      <div className="rate-limiter-modes">
        <button
          className={`mode-btn ${mode === 'OFF' ? 'active' : ''}`}
          onClick={() => {
            setMode('OFF');
            handleApplyConfig('OFF');
          }}
        >
          <ShieldOff size={14} className="inline mr-1" />
          <span>OFF (Bypass)</span>
        </button>
        <button
          className={`mode-btn ${mode === 'TOKEN_BUCKET' ? 'active' : ''}`}
          onClick={() => {
            setMode('TOKEN_BUCKET');
            handleApplyConfig('TOKEN_BUCKET');
          }}
        >
          <Zap size={14} className="inline mr-1" />
          <span>Token Bucket</span>
        </button>
        <button
          className={`mode-btn ${mode === 'LEAKY_BUCKET' ? 'active' : ''}`}
          onClick={() => {
            setMode('LEAKY_BUCKET');
            handleApplyConfig('LEAKY_BUCKET');
          }}
        >
          <Hourglass size={14} className="inline mr-1" />
          <span>Leaky Bucket Shaper</span>
        </button>
      </div>

      {/* Configuration Controls based on mode */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 bg-slate-900/60 p-3 rounded border border-slate-700/60 text-xs">
        {mode === 'TOKEN_BUCKET' && (
          <>
            <div>
              <div className="flex justify-between mb-1">
                <span className="text-muted">Burst Capacity (Tokens):</span>
                <span className="font-mono text-bright font-bold">{tokenCapacity} tokens</span>
              </div>
              <input
                type="range"
                min="2"
                max="50"
                step="1"
                value={tokenCapacity}
                onChange={(e) => setTokenCapacity(Number(e.target.value))}
                className="w-full accent-cyan-400"
              />
            </div>
            <div>
              <div className="flex justify-between mb-1">
                <span className="text-muted">Refill Rate:</span>
                <span className="font-mono text-bright font-bold">{tokenRefillRate.toFixed(1)} tokens/sec</span>
              </div>
              <input
                type="range"
                min="0.5"
                max="20"
                step="0.5"
                value={tokenRefillRate}
                onChange={(e) => setTokenRefillRate(Number(e.target.value))}
                className="w-full accent-cyan-400"
              />
            </div>
          </>
        )}

        {mode === 'LEAKY_BUCKET' && (
          <>
            <div>
              <div className="flex justify-between mb-1">
                <span className="text-muted">FIFO Queue Capacity:</span>
                <span className="font-mono text-bright font-bold">{leakyCapacity} requests</span>
              </div>
              <input
                type="range"
                min="5"
                max="50"
                step="1"
                value={leakyCapacity}
                onChange={(e) => setLeakyCapacity(Number(e.target.value))}
                className="w-full accent-cyan-400"
              />
            </div>
            <div>
              <div className="flex justify-between mb-1">
                <span className="text-muted">Drain Rate:</span>
                <span className="font-mono text-bright font-bold">{leakyDrainRate.toFixed(1)} req/sec</span>
              </div>
              <input
                type="range"
                min="0.5"
                max="20"
                step="0.5"
                value={leakyDrainRate}
                onChange={(e) => setLeakyDrainRate(Number(e.target.value))}
                className="w-full accent-cyan-400"
              />
            </div>
          </>
        )}

        {mode === 'OFF' && (
          <div className="col-span-2 text-muted text-center py-2">
            Traffic limiter is currently <strong className="text-white">OFF</strong>. All customer requests pass directly to the backend without rate throttling or queuing.
          </div>
        )}
      </div>

      {mode !== 'OFF' && (
        <div className="mt-3 flex justify-end">
          <button
            className="btn-console btn-primary btn-sm text-xs"
            onClick={() => handleApplyConfig()}
            disabled={isApplying}
          >
            {isApplying ? <RefreshCw size={12} className="animate-spin" /> : <Check size={12} />}
            <span>Apply Parameters</span>
          </button>
        </div>
      )}

      {/* Live Metrics Grid */}
      <div className="rate-metrics-grid">
        <div className="rate-metric-card">
          <div className="val text-healthy">
            {mode === 'TOKEN_BUCKET'
              ? `${tokensRemaining.toFixed(1)} / ${tokenCapacity}`
              : `${queueDepth} / ${leakyCapacity}`}
          </div>
          <div className="lbl">
            {mode === 'TOKEN_BUCKET' ? 'Tokens Available' : 'Current Queue Depth'}
          </div>
        </div>

        <div className="rate-metric-card">
          <div className="val text-flow">{accepted.toLocaleString()}</div>
          <div className="lbl">Accepted Requests</div>
        </div>

        <div className="rate-metric-card">
          <div className="val text-danger">{throttled.toLocaleString()}</div>
          <div className="lbl">Throttled (429)</div>
        </div>

        <div className="rate-metric-card">
          <div className="val text-bright">
            {mode === 'LEAKY_BUCKET' ? `${avgWait.toFixed(1)} ms` : `${status?.common?.average_latency_ms ?? 0} ms`}
          </div>
          <div className="lbl">
            {mode === 'LEAKY_BUCKET' ? 'Avg Queue Wait' : 'Avg RTT'}
          </div>
        </div>
      </div>
    </div>
  );
};
