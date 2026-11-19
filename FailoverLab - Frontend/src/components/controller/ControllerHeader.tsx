import React from 'react';
import {
  Layers,
  Pause,
  Play,
  RotateCw,
  ShoppingBag,
  Sliders,
  ShieldCheck,
  Radio,
} from 'lucide-react';
import type { TrafficSummaryDto, ControllerStateDto } from '../../api/controllerClient';
import { formatRelativeTime } from './formatters';

interface ControllerHeaderProps {
  controllerState: ControllerStateDto | null;
  trafficSummary: TrafficSummaryDto | null;
  isBackendConnected: boolean;
  isPaused: boolean;
  onTogglePause: () => void;
  onRefreshNow: () => void;
  onNavigateToShop: () => void;
  onNavigateToConsole: () => void;
}

export const ControllerHeader: React.FC<ControllerHeaderProps> = ({
  controllerState,
  trafficSummary,
  isBackendConnected,
  isPaused,
  onTogglePause,
  onRefreshNow,
  onNavigateToShop,
  onNavigateToConsole,
}) => {
  const activeRegion = controllerState?.active_region || '—';
  const epoch = controllerState?.fencing_epoch !== undefined ? controllerState.fencing_epoch : '—';
  const cState = controllerState?.controller_state || (isBackendConnected ? 'Loading' : 'DISCONNECTED');
  const freshness = trafficSummary?.telemetry_freshness || (isBackendConnected ? 'UNAVAILABLE' : 'DISCONNECTED');
  const lastUpdate = trafficSummary?.last_received_timestamp;

  return (
    <header className="controller-header">
      {/* Brand & System Title */}
      <div className="controller-header-brand">
        <div className="controller-logo-box">
          <Layers size={18} />
        </div>
        <div className="controller-brand-title">
          <div className="controller-brand-heading">
            <span>FailoverLab</span>
            <span className="controller-brand-tag">Controller Ops</span>
          </div>
          <span className="controller-brand-sub">Multi-Region Distributed Control Plane</span>
        </div>
      </div>

      {/* Header Center Vitals Pills */}
      <div className="controller-header-center">
        {/* Connection State */}
        <div className="controller-vitals-pill">
          <span
            className={`pulse-indicator ${
              isBackendConnected ? 'pulse-green' : 'pulse-red'
            }`}
          />
          <span className="label">Controller:</span>
          <span className="val">{isBackendConnected ? 'CONNECTED' : 'DISCONNECTED'}</span>
        </div>

        {/* Active Writer & Fencing Epoch */}
        <div className="controller-vitals-pill">
          <ShieldCheck size={13} className="text-flow" />
          <span className="label">Active Writer:</span>
          <span className="val text-flow">{activeRegion}</span>
          <span className="badge-tag-sm badge-warning font-mono">
            {typeof epoch === 'number' ? `Epoch #${epoch}` : 'Epoch —'}
          </span>
        </div>

        {/* State Machine Status */}
        <div className="controller-vitals-pill">
          <span className="label">State:</span>
          <span
            className={`val font-mono ${
              cState === 'HEALTHY'
                ? 'text-healthy'
                : cState === 'SECONDARY_ACTIVE'
                ? 'text-flow'
                : 'text-warning'
            }`}
          >
            {cState}
          </span>
        </div>

        {/* Gateway Telemetry Freshness */}
        <div className="controller-vitals-pill">
          <Radio size={13} className={freshness === 'FRESH' ? 'text-healthy' : freshness === 'STALE' ? 'text-warning' : 'text-danger'} />
          <span className="label">Telemetry:</span>
          <span
            className={`val font-mono ${
              freshness === 'FRESH'
                ? 'text-healthy'
                : freshness === 'STALE'
                ? 'text-warning'
                : 'text-danger'
            }`}
          >
            {freshness}
          </span>
          {lastUpdate && (
            <span className="text-muted text-xs font-mono" title={lastUpdate}>
              ({formatRelativeTime(lastUpdate)})
            </span>
          )}
        </div>
      </div>

      {/* Header Action Controls */}
      <div className="controller-header-actions">
        {/* Pause/Resume Live Polling */}
        <button
          type="button"
          className={`btn-console ${isPaused ? 'btn-primary' : ''}`}
          onClick={onTogglePause}
          title={isPaused ? 'Resume real-time data polling' : 'Pause real-time data polling'}
        >
          {isPaused ? <Play size={13} /> : <Pause size={13} />}
          <span>{isPaused ? 'Resume' : 'Pause'}</span>
        </button>

        {/* Manual Refresh Now Button */}
        <button
          type="button"
          className="btn-console"
          onClick={onRefreshNow}
          title="Force immediate telemetry & state fetch"
        >
          <RotateCw size={13} />
          <span>Refresh</span>
        </button>

        {/* Return to Online Store */}
        <button
          type="button"
          className="btn-console"
          style={{ background: '#0284c7', borderColor: '#0369a1', color: '#ffffff' }}
          onClick={onNavigateToShop}
          title="Open customer-facing Online Storefront (/shop)"
        >
          <ShoppingBag size={13} />
          <span>Online Store</span>
        </button>

        {/* Return to FailoverLab Simulation Console */}
        <button
          type="button"
          className="btn-console"
          onClick={onNavigateToConsole}
          title="Return to the canonical FailoverLab Operations Dashboard"
        >
          <Sliders size={13} />
          <span>Simulation Lab</span>
        </button>
      </div>
    </header>
  );
};
