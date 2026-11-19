import React from 'react';
import {
  RotateCcw,
  BookOpen,
  Pause,
  Play,
  Terminal,
  ShoppingBag,
  Sliders,
} from 'lucide-react';
import { useSimulation } from '../../simulation/useSimulation';
import { StatusDot } from './StatusDot';

interface HeaderProps {
  onOpenMethodology: () => void;
  onNavigateToShop?: () => void;
  onNavigateToController?: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  onOpenMethodology,
  onNavigateToShop,
  onNavigateToController,
}) => {
  const {
    regionA,
    regionB,
    leaseFence,
    controllerState,
    isRunning,
    isBackendConnected,
    engine,
  } = useSimulation();

  const isDegradedOrFailing =
    controllerState !== 'HEALTHY' && controllerState !== 'SECONDARY_ACTIVE';

  return (
    <header className="failover-header">
      {/* Brand & System Context */}
      <div className="header-left">
        <div className="logo-group">
          <div className="logo-icon-box">
            <Terminal size={15} />
          </div>
          <div className="logo-text">
            <div className="brand-title">
              FailoverLab
            </div>
            <div className="brand-sub">Multi-Region Controller</div>
          </div>
        </div>

        <div className="case-badge">
          <span className="case-tag">CASE 23</span>
          <span className="case-title">Active-Passive Control Plane</span>
        </div>
      </div>

      {/* Center Regional Routing State */}
      <div className="header-center">
        <div className="status-pill-group">
          {/* Mumbai ap-south-1 */}
          <div className="status-pill">
            <StatusDot
              status={
                regionA.role === 'ACTIVE'
                  ? regionA.status === 'healthy'
                    ? 'healthy'
                    : 'warning'
                  : 'standby'
              }
            />
            <span className="pill-region font-mono text-xs">[IN] Mumbai:</span>
            <span className="pill-role font-mono text-xs">
              {regionA.role} {regionA.status === 'fenced' ? '[FENCED]' : ''}
            </span>
          </div>

          <span className="status-separator">/</span>

          {/* Singapore ap-southeast-1 */}
          <div className="status-pill">
            <StatusDot
              status={regionB.role === 'ACTIVE' ? 'healthy' : 'standby'}
            />
            <span className="pill-region font-mono text-xs">[SG] Singapore:</span>
            <span className="pill-role font-mono text-xs">
              {regionB.role} [Epoch {leaseFence.generationId}]
            </span>
          </div>
        </div>
      </div>

      {/* Right Actions & Navigation */}
      <div className="header-right">
        {/* Backend live / simulation engine mode */}
        <div
          className="status-pill"
          title={isBackendConnected ? 'Connected to live Python FastAPI Control Plane (Port 8000)' : 'Running in In-Browser Simulation Engine'}
        >
          <StatusDot status={isBackendConnected ? 'healthy' : 'standby'} />
          <span className="font-mono text-xs" style={{ color: 'var(--text-muted)' }}>
            {isBackendConnected ? 'BACKEND LIVE' : 'BROWSER SIM'}
          </span>
        </div>

        {/* Clock state */}
        <div
          className="sim-mode-badge font-mono text-xs"
          title={isDegradedOrFailing ? 'Controller resolving state transition' : 'Clock state'}
        >
          <span className={isDegradedOrFailing ? 'text-warning' : isRunning ? 'text-flow' : 'text-muted'}>
            {isDegradedOrFailing
              ? 'DISRUPTION'
              : isRunning
              ? 'CLOCK RUNNING'
              : 'CLOCK PAUSED'}
          </span>
        </div>

        {/* Play/Pause toggle */}
        <button
          type="button"
          className="btn-console header-action-btn"
          onClick={() => engine.togglePlay()}
          title={isRunning ? 'Pause simulation clock' : 'Resume simulation clock'}
          aria-label={isRunning ? 'Pause simulation clock' : 'Resume simulation clock'}
        >
          {isRunning ? <Pause size={13} /> : <Play size={13} />}
          <span>{isRunning ? 'Pause' : 'Play'}</span>
        </button>

        {/* Reset simulation */}
        <button
          type="button"
          className="btn-console header-action-btn"
          onClick={() => engine.reset()}
          title="Reset entire virtual lab to nominal baseline"
          aria-label="Reset simulation to nominal baseline"
        >
          <RotateCcw size={13} />
          <span>Reset</span>
        </button>

        {/* System Design Methodology */}
        <button
          type="button"
          className="btn-console header-action-btn"
          onClick={onOpenMethodology}
          title="Open System Design architectural specifications"
          aria-label="Open System Design specifications"
        >
          <BookOpen size={13} />
          <span>Methodology</span>
        </button>

        {/* Controller UI Navigation */}
        {onNavigateToController && (
          <button
            type="button"
            className="btn-console header-action-btn btn-primary"
            onClick={onNavigateToController}
            title="Open the dedicated Controller Observability & Traffic Console (/controller)"
            aria-label="Open Controller Console"
          >
            <Sliders size={13} />
            <span>Controller UI</span>
          </button>
        )}

        {/* Online Store Navigation */}
        {onNavigateToShop && (
          <button
            type="button"
            className="btn-console header-action-btn"
            onClick={onNavigateToShop}
            title="Launch the integrated Online Shopping storefront (/shop)"
            aria-label="Open Online Store demonstration"
          >
            <ShoppingBag size={13} />
            <span>Online Store</span>
          </button>
        )}
      </div>
    </header>
  );
};
