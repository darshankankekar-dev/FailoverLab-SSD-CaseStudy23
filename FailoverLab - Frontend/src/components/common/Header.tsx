import React from 'react';
import {
  RotateCcw,
  BookOpen,
  Pause,
  Play,
  Activity,
  Layers,
  AlertTriangle,
} from 'lucide-react';
import { useSimulation } from '../../simulation/useSimulation';

interface HeaderProps {
  onOpenMethodology: () => void;
}

export const Header: React.FC<HeaderProps> = ({ onOpenMethodology }) => {
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
      <div className="header-left">
        <div className="logo-group">
          <div className="logo-icon-box">
            <Layers className="logo-icon" size={20} />
          </div>
          <div className="logo-text">
            <div className="brand-title">
              <span className="brand-accent">Failover</span>Lab
            </div>
            <div className="brand-sub">Multi-Region Controller</div>
          </div>
        </div>

        <div className="case-badge">
          <span className="case-tag">SSD CASE 23</span>
          <span className="case-title">Active-Passive Control Plane</span>
        </div>
      </div>

      <div className="header-center">
        <div className="status-pill-group">
          <div
            className={`status-pill ${
              regionA.role === 'ACTIVE'
                ? regionA.status === 'healthy'
                  ? 'status-pill-active'
                  : 'status-pill-warning'
                : 'status-pill-standby'
            }`}
          >
            <span
              className={`pulse-dot ${
                regionA.role === 'ACTIVE'
                  ? regionA.status === 'healthy'
                    ? 'pulse-healthy'
                    : 'pulse-warning'
                  : 'pulse-standby'
              }`}
            />
            <span className="pill-region">Mumbai (ap-south-1):</span>
            <span className="pill-role font-mono">
              {regionA.role} {regionA.status === 'fenced' ? '[FENCED]' : ''}
            </span>
          </div>

          <div className="status-separator">/</div>

          <div
            className={`status-pill ${
              regionB.role === 'ACTIVE'
                ? 'status-pill-active'
                : 'status-pill-standby'
            }`}
          >
            <span
              className={`pulse-dot ${
                regionB.role === 'ACTIVE' ? 'pulse-healthy' : 'pulse-standby'
              }`}
            />
            <span className="pill-region">Singapore (ap-southeast-1):</span>
            <span className="pill-role font-mono">
              {regionB.role} [Epoch {leaseFence.generationId}]
            </span>
          </div>
        </div>
      </div>

      <div className="header-right">
        {/* Live Backend Connection Indicator */}
        <div
          className={`status-pill ${
            isBackendConnected ? 'status-pill-active' : 'status-pill-standby'
          }`}
          style={{ padding: '3px 8px', fontSize: '11px', display: 'flex', alignItems: 'center', gap: '6px' }}
          title={isBackendConnected ? 'Connected to live Python FastAPI Control Plane (port 8000)' : 'Running in In-Browser Simulation Engine'}
        >
          <span
            className={`pulse-dot ${
              isBackendConnected ? 'pulse-healthy' : 'pulse-standby'
            }`}
          />
          <span className="font-mono text-xs">
            {isBackendConnected ? 'BACKEND LIVE' : 'BROWSER SIM'}
          </span>
        </div>

        {/* Simulation Mode Badge */}
        <div
          className={`sim-mode-badge ${
            isDegradedOrFailing
              ? 'sim-mode-alert'
              : isRunning
              ? 'sim-mode-running'
              : 'sim-mode-paused'
          }`}
          title={isDegradedOrFailing ? 'Controller is resolving an active state transition' : 'Clock state'}
        >
          {isDegradedOrFailing ? (
            <AlertTriangle size={13} className="text-warning" />
          ) : isRunning ? (
            <Activity size={13} className="text-flow" />
          ) : (
            <Pause size={13} className="text-muted" />
          )}
          <span className="sim-mode-text font-mono">
            {isDegradedOrFailing
              ? 'DISRUPTION'
              : isRunning
              ? 'SIM RUNNING'
              : 'SIM PAUSED'}
          </span>
        </div>

        {/* Play/Pause clock toggle */}
        <button
          className="btn-console header-action-btn"
          onClick={() => engine.togglePlay()}
          title={isRunning ? 'Pause simulation clock' : 'Resume simulation clock'}
          aria-label={isRunning ? 'Pause simulation clock' : 'Resume simulation clock'}
        >
          {isRunning ? <Pause size={14} /> : <Play size={14} />}
          <span className="header-btn-label">{isRunning ? 'Pause' : 'Play'}</span>
        </button>

        {/* Reset button */}
        <button
          className="btn-console header-action-btn btn-reset"
          onClick={() => engine.reset()}
          title="Reset entire virtual lab to nominal baseline"
          aria-label="Reset simulation to nominal baseline"
        >
          <RotateCcw size={14} />
          <span className="header-btn-label">Reset</span>
        </button>

        {/* Methodology / Help button */}
        <button
          className="btn-console header-action-btn btn-help"
          onClick={onOpenMethodology}
          title="Open System Design methodology & architectural reference"
          aria-label="Open System Design methodology reference"
        >
          <BookOpen size={14} />
          <span className="header-btn-label">Methodology</span>
        </button>
      </div>
    </header>
  );
};
