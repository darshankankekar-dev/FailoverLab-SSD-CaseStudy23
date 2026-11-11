import React, { useState } from 'react';
import {
  Play,
  Pause,
  Flame,
  Clock,
  Shield,
  Sliders,
  PlayCircle,
  RefreshCw,
  RotateCcw,
  ArrowRight,
  ShieldAlert,
  HelpCircle,
  RotateCw,
  CheckCircle,
  AlertTriangle,
} from 'lucide-react';
import { useSimulation } from '../../simulation/useSimulation';
import { SCENARIOS } from '../../data/scenarios';
import { controllerClient } from '../../api/controllerClient';

export const ControlsPanel: React.FC = () => {
  const {
    isRunning,
    tickSpeed,
    config,
    controllerState,
    blockedReason,
    consecutiveFailures,
    isSequenceInProgress,
    regionA,
    regionB,
    dns,
    isPausedInterrupted,
    persistedIntent,
    isBackendConnected,
    engine,
  } = useSimulation();

  const [activeScenarioId, setActiveScenarioId] = useState<string>(SCENARIOS[0].id);
  const [actionFeedback, setActionFeedback] = useState<{
    type: 'loading' | 'success' | 'blocked' | 'error' | 'timeout';
    message: string;
  } | null>(null);

  const activeScenario =
    SCENARIOS.find((s) => s.id === activeScenarioId) || SCENARIOS[0];

  const isAOutage = regionA.status === 'failed' || regionA.health === 'DOWN';

  // Disabled evaluation and human-readable reasons
  const injectPrimaryDisabled =
    isAOutage || isSequenceInProgress || controllerState === 'FENCING_PRIMARY' || controllerState === 'PROMOTING_STANDBY';
  const injectPrimaryReason = isAOutage
    ? 'Primary database is already failed / outage active'
    : isSequenceInProgress
    ? 'Transition sequence currently in progress'
    : '';

  const restorePrimaryDisabled = !isAOutage && regionA.health === 'HEALTHY' && !regionA.isFenced;
  const restorePrimaryReason = restorePrimaryDisabled
    ? 'Primary is already healthy and active'
    : '';

  const manualFailoverDisabled =
    regionB.role === 'ACTIVE' || isSequenceInProgress || regionB.health !== 'HEALTHY';
  const manualFailoverReason =
    regionB.role === 'ACTIVE'
      ? 'Region B is already the active primary'
      : isSequenceInProgress
      ? 'Failover sequence already in progress'
      : regionB.health !== 'HEALTHY'
      ? 'Region B standby is unhealthy'
      : '';

  const stepDisabled = isRunning;
  const stepReason = isRunning ? 'Pause simulation clock to step manually' : '';

  const retryRouteDisabled =
    dns.resolutionStatus !== 'FAILED' &&
    controllerState !== 'VERIFYING_ROUTE' &&
    controllerState !== 'FAILOVER_BLOCKED';
  const retryRouteReason = retryRouteDisabled
    ? 'Routing is currently nominal; no failed update pending'
    : '';

  const approveFailbackDisabled =
    controllerState !== 'FAILBACK_PENDING' && controllerState !== 'PRIMARY_RECOVERING';
  const approveFailbackReason = approveFailbackDisabled
    ? 'Requires Region A to be recovered and synchronized in standby first'
    : '';

  const handleRunScenario = () => {
    setActionFeedback({ type: 'loading', message: `Setting up ${activeScenario.title}...` });
    if (activeScenario) {
      activeScenario.setupChaos(engine);
      setTimeout(() => setActionFeedback({ type: 'success', message: `${activeScenario.title} active.` }), 400);
    }
  };

  const handleResetScenario = () => {
    setActionFeedback({ type: 'loading', message: 'Resetting environment to nominal state...' });
    if (activeScenario && activeScenario.resetScenario) {
      activeScenario.resetScenario(engine);
    } else {
      engine.reset();
    }
    setTimeout(() => setActionFeedback({ type: 'success', message: 'Cluster reset to nominal baseline.' }), 400);
  };

  const handleManualFailover = async () => {
    if (!isBackendConnected) {
      engine.triggerManualFailover();
      return;
    }

    setActionFeedback({ type: 'loading', message: 'Executing 10-step failover workflow on controller...' });
    try {
      const res = await controllerClient.triggerFailover({ target_region: 'region-b' });
      if (res.status === 'SUCCESS') {
        setActionFeedback({
          type: 'success',
          message: `Failover complete: Region B promoted to ACTIVE [Epoch ${res.fencing_epoch}]`,
        });
        const st = await controllerClient.fetchState();
        if (st) engine.applyBackendState(st);
      } else if (res.status === 'BLOCKED') {
        setActionFeedback({
          type: 'blocked',
          message: `Blocked: ${res.blocked_reason || res.message}`,
        });
        const st = await controllerClient.fetchState();
        if (st) engine.applyBackendState(st);
      } else {
        setActionFeedback({
          type: 'error',
          message: `Transition ${res.status}: ${res.message}`,
        });
      }
    } catch (err: any) {
      setActionFeedback({
        type: 'error',
        message: `Failover error: ${err.message || 'Network request failed'}`,
      });
    }
  };

  const handleApproveFailback = async () => {
    if (!isBackendConnected) {
      engine.triggerManualFailback();
      return;
    }

    setActionFeedback({ type: 'loading', message: 'Authorizing guarded failback to Region A...' });
    try {
      const res = await controllerClient.triggerFailback({ target_region: 'region-a' });
      if (res.status === 'SUCCESS') {
        setActionFeedback({
          type: 'success',
          message: 'Failback succeeded: Traffic restored to Mumbai',
        });
        const st = await controllerClient.fetchState();
        if (st) engine.applyBackendState(st);
      } else if (res.status === 'BLOCKED') {
        setActionFeedback({
          type: 'blocked',
          message: `Failback blocked: ${res.blocked_reason || res.message}`,
        });
      } else {
        setActionFeedback({
          type: 'error',
          message: `Failback ${res.status}: ${res.message}`,
        });
      }
    } catch (err: any) {
      setActionFeedback({
        type: 'error',
        message: `Failback error: ${err.message || 'Request failed'}`,
      });
    }
  };

  return (
    <div className="controls-panel">
      {/* Panel Header */}
      <div className="panel-header">
        <div className="panel-title-group">
          <Sliders size={16} className="text-flow" />
          <h2 className="panel-title">Experiment Controls</h2>
        </div>
        <div
          className={`badge-tag font-mono text-xs ${
            controllerState === 'FAILOVER_BLOCKED'
              ? 'badge-danger'
              : controllerState === 'HEALTHY' || controllerState === 'SECONDARY_ACTIVE'
              ? 'badge-healthy'
              : 'badge-warning'
          }`}
        >
          {controllerState}
        </div>
      </div>

      <div className="panel-scroll-content">
        {/* BACKEND MODE BANNER */}
        <div
          className="backend-mode-card"
          style={{
            padding: '8px 12px',
            borderRadius: '6px',
            background: isBackendConnected ? 'rgba(34, 197, 94, 0.08)' : 'rgba(234, 179, 8, 0.08)',
            border: `1px solid ${isBackendConnected ? 'rgba(34, 197, 94, 0.25)' : 'rgba(234, 179, 8, 0.25)'}`,
            marginBottom: '12px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span className={`pulse-dot ${isBackendConnected ? 'pulse-healthy' : 'pulse-warning'}`} />
              <span className={`font-mono text-xs font-bold ${isBackendConnected ? 'text-healthy' : 'text-warning'}`}>
                {isBackendConnected ? 'LIVE BACKEND MODE' : 'OFFLINE DEMO MODE'}
              </span>
            </div>
            <span className="font-mono text-xs text-muted">
              {isBackendConnected ? 'FastAPI + PostgreSQL' : 'In-Browser State'}
            </span>
          </div>
          <div className="font-mono text-xs text-secondary mt-1" style={{ fontSize: '11px' }}>
            {isBackendConnected
              ? 'Control Plane (:8000) & Gateway (:8080) active. Server is source of truth.'
              : 'Python backend offline. Running interactive in-browser simulation engine.'}
          </div>
        </div>

        {/* ACTION FEEDBACK ALERT */}
        {actionFeedback && (
          <div
            className={`action-feedback-card ${
              actionFeedback.type === 'error' || actionFeedback.type === 'timeout'
                ? 'border-danger text-danger'
                : actionFeedback.type === 'blocked'
                ? 'border-warning text-warning'
                : actionFeedback.type === 'loading'
                ? 'border-flow text-flow'
                : 'border-healthy text-healthy'
            }`}
            style={{
              padding: '8px 12px',
              borderRadius: '6px',
              borderWidth: '1px',
              borderStyle: 'solid',
              background: 'rgba(255, 255, 255, 0.04)',
              marginBottom: '12px',
              fontSize: '12px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              {actionFeedback.type === 'loading' && <RefreshCw size={13} className="animate-spin" />}
              {actionFeedback.type === 'error' && <AlertTriangle size={13} />}
              {actionFeedback.type === 'timeout' && <Clock size={13} />}
              {actionFeedback.type === 'blocked' && <ShieldAlert size={13} />}
              {actionFeedback.type === 'success' && <CheckCircle size={13} />}
              <span className="font-mono">{actionFeedback.message}</span>
            </div>
            {actionFeedback.type !== 'loading' && (
              <button
                onClick={() => setActionFeedback(null)}
                style={{ background: 'transparent', border: 'none', color: 'inherit', cursor: 'pointer', fontSize: '14px', lineHeight: 1 }}
                aria-label="Dismiss message"
              >
                ×
              </button>
            )}
          </div>
        )}
        {/* CONTROLLER INTERRUPTION BANNER (Scenario I) */}
        {isPausedInterrupted && (
          <div className="blocked-state-card" style={{ borderColor: '#f59e0b', background: 'rgba(245, 158, 11, 0.12)' }}>
            <div className="blocked-header">
              <ShieldAlert size={16} className="text-warning" />
              <span className="font-mono text-xs font-bold text-warning">
                CONTROLLER INTERRUPTED MID-TRANSITION
              </span>
            </div>
            <p className="blocked-reason-text text-xs text-bright mt-1">
              Controller halted at state <strong>{persistedIntent || controllerState}</strong>. Persistent intent saved to metadata store.
            </p>
            <div className="blocked-action-row mt-2">
              <button
                className="btn-console btn-primary text-xs w-full"
                onClick={() => engine.resumeControllerReconcile()}
              >
                <RefreshCw size={12} />
                <span>Resume & Reconcile Intent</span>
              </button>
            </div>
          </div>
        )}

        {/* BLOCKED STATE BANNER */}
        {controllerState === 'FAILOVER_BLOCKED' && !isPausedInterrupted && (
          <div className="blocked-state-card">
            <div className="blocked-header">
              <ShieldAlert size={16} className="text-danger" />
              <span className="font-mono text-xs font-bold text-danger">
                TRANSITION BLOCKED BY SAFETY GATE
              </span>
            </div>
            <p className="blocked-reason-text text-xs text-bright mt-1">
              {blockedReason || 'Transition blocked by safety policy check.'}
            </p>
            <div className="blocked-action-row mt-2">
              <button
                className="btn-console btn-danger text-xs w-full"
                onClick={() => engine.dismissBlockedState()}
              >
                <span>Dismiss & Restore Controller</span>
              </button>
            </div>
          </div>
        )}

        {/* FAILBACK RECOVERY BANNER */}
        {(controllerState === 'PRIMARY_RECOVERING' || controllerState === 'FAILBACK_PENDING') && (
          <div className="failback-banner-card">
            <div className="failback-header">
              <RotateCcw size={15} className="text-flow" />
              <span className="font-mono text-xs font-bold text-flow">
                {controllerState === 'FAILBACK_PENDING'
                  ? 'FAILBACK AUTHORIZATION REQUIRED'
                  : 'PRIMARY RECOVERING (STANDBY)'}
              </span>
            </div>
            <p className="text-xs text-secondary mt-1">
              {controllerState === 'FAILBACK_PENDING'
                ? 'Region A (Mumbai) is healthy and reverse replication is reconciled. Click below to execute deliberate manual failback.'
                : 'Region A is back online in standby. Reverse replication stream must reconcile before failback.'}
            </p>
            <div className="failback-actions-row mt-2">
              {controllerState === 'PRIMARY_RECOVERING' && (
                <button
                  className="btn-console text-xs btn-primary w-full"
                  onClick={() => engine.reconcileReplication()}
                >
                  <RefreshCw size={12} />
                  <span>Reconcile Reverse Replication Now</span>
                </button>
              )}
              {controllerState === 'FAILBACK_PENDING' && (
                <button
                  className="btn-console btn-primary text-xs w-full"
                  onClick={handleApproveFailback}
                >
                  <ArrowRight size={13} />
                  <span>Execute Controlled Failback to Mumbai</span>
                </button>
              )}
            </div>
          </div>
        )}

        {/* ============================================================== */}
        {/* 1. PRIMARY CONTROLS (8 Discrete Operations)                    */}
        {/* ============================================================== */}
        <div className="control-section">
          <div className="section-header-flex">
            <label className="section-label font-mono">PRIMARY CONTROLS</label>
            <span className="font-mono text-xs text-muted">
              Failures: {consecutiveFailures}/{config.failureThresholdConsecutive}
            </span>
          </div>

          <div className="primary-controls-stack">
            {/* 1. Inject Primary Failure */}
            <div className="control-button-wrapper">
              <button
                className="btn-console btn-danger text-xs w-full"
                onClick={() => engine.injectPrimaryOutage()}
                disabled={injectPrimaryDisabled}
              >
                <Flame size={13} />
                <span>1. Inject Primary Failure</span>
              </button>
              {injectPrimaryDisabled && (
                <div className="disabled-reason-caption font-mono text-muted">
                  {injectPrimaryReason}
                </div>
              )}
            </div>

            {/* 2. Restore Primary */}
            <div className="control-button-wrapper">
              <button
                className="btn-console text-xs w-full"
                onClick={() => engine.recoverPrimary()}
                disabled={restorePrimaryDisabled}
              >
                <RefreshCw size={13} />
                <span>2. Restore Primary</span>
              </button>
              {restorePrimaryDisabled && (
                <div className="disabled-reason-caption font-mono text-muted">
                  {restorePrimaryReason}
                </div>
              )}
            </div>

            {/* 3. Trigger Manual Failover */}
            <div className="control-button-wrapper">
              <button
                className="btn-console btn-primary text-xs w-full"
                onClick={handleManualFailover}
                disabled={manualFailoverDisabled}
              >
                <ArrowRight size={13} />
                <span>3. Trigger Manual Failover</span>
              </button>
              {manualFailoverDisabled && (
                <div className="disabled-reason-caption font-mono text-muted">
                  {manualFailoverReason}
                </div>
              )}
            </div>

            {/* 4. Start / Pause Simulation */}
            <div className="control-button-wrapper">
              <div className="clock-controls-grid">
                <button
                  className={`btn-console ${isRunning ? 'btn-warning' : 'btn-primary'} text-xs`}
                  onClick={() => engine.togglePlay()}
                >
                  {isRunning ? <Pause size={13} /> : <Play size={13} />}
                  <span>{isRunning ? '4. Pause Simulation' : '4. Start Simulation'}</span>
                </button>

                {/* 5. Step Through Failover */}
                <button
                  className="btn-console clock-step-btn text-xs"
                  onClick={() => engine.stepFailover()}
                  disabled={stepDisabled}
                >
                  <PlayCircle size={13} />
                  <span>5. Step Failover</span>
                </button>
              </div>
              {stepDisabled && (
                <div className="disabled-reason-caption font-mono text-muted">
                  {stepReason}
                </div>
              )}
            </div>

            {/* 6. Retry Routing Update */}
            <div className="control-button-wrapper">
              <button
                className="btn-console btn-warning text-xs w-full"
                onClick={() => engine.retryRoutingUpdate()}
                disabled={retryRouteDisabled}
              >
                <RotateCw size={13} />
                <span>6. Retry Routing Update</span>
              </button>
              {retryRouteDisabled && (
                <div className="disabled-reason-caption font-mono text-muted">
                  {retryRouteReason}
                </div>
              )}
            </div>

            {/* 7. Approve Failback */}
            <div className="control-button-wrapper">
              <button
                className="btn-console btn-success text-xs w-full"
                onClick={() => {
                  if (controllerState === 'PRIMARY_RECOVERING') {
                    engine.reconcileReplication();
                  } else {
                    engine.triggerManualFailback();
                  }
                }}
                disabled={approveFailbackDisabled}
              >
                <RotateCcw size={13} />
                <span>7. Approve Failback</span>
              </button>
              {approveFailbackDisabled && (
                <div className="disabled-reason-caption font-mono text-muted">
                  {approveFailbackReason}
                </div>
              )}
            </div>

            {/* 8. Reset Simulation */}
            <div className="control-button-wrapper">
              <button
                className="btn-console text-xs w-full"
                onClick={() => engine.reset()}
              >
                <RefreshCw size={13} />
                <span>8. Reset Simulation</span>
              </button>
            </div>
          </div>

          {/* Tick Speed Selector */}
          <div className="tick-speed-selector mt-2">
            <span className="text-xs text-muted font-mono">Clock Rate:</span>
            {[1, 2, 5].map((speed) => (
              <button
                key={speed}
                className={`speed-btn font-mono ${
                  tickSpeed === speed ? 'speed-btn-active' : ''
                }`}
                onClick={() => engine.setTickSpeed(speed)}
              >
                {speed}x
              </button>
            ))}
          </div>
        </div>

        {/* ============================================================== */}
        {/* 2. GUIDED SCENARIO SELECTOR (Scenarios A through I)            */}
        {/* ============================================================== */}
        <div className="control-section">
          <div className="section-header-flex">
            <label className="section-label font-mono">SCENARIO SELECTOR</label>
            <HelpCircle size={14} className="text-flow" />
          </div>

          <select
            className="scenario-select font-mono"
            value={activeScenarioId}
            onChange={(e) => setActiveScenarioId(e.target.value)}
          >
            {SCENARIOS.map((sc) => (
              <option key={sc.id} value={sc.id}>
                {sc.letter}: {sc.title.replace('SCENARIO ', '')}
              </option>
            ))}
          </select>

          {/* Scenario Details Box */}
          <div className="scenario-mini-card">
            <div className="scenario-mini-header">
              <span className="badge-tag badge-warning font-mono text-xs">
                Scenario {activeScenario.letter}
              </span>
              <span className="font-mono text-xs text-muted">{activeScenario.category}</span>
            </div>
            <p className="scenario-mini-desc text-xs text-secondary mt-1">
              {activeScenario.summary}
            </p>
            <div className="scenario-mini-meta mt-2">
              <div className="mini-meta-item">
                <span className="mini-meta-label font-mono text-xs text-flow">Setup:</span>
                <span className="mini-meta-val text-xs text-muted">{activeScenario.setup}</span>
              </div>
              <div className="mini-meta-item mt-1">
                <span className="mini-meta-label font-mono text-xs text-healthy">Expected:</span>
                <span className="mini-meta-val text-xs text-muted">{activeScenario.expectedBehaviour}</span>
              </div>
            </div>

            <div className="scenario-mini-actions mt-3">
              <button
                className="btn-console btn-primary text-xs flex-1"
                onClick={handleRunScenario}
              >
                <Play size={12} />
                <span>Run Scenario {activeScenario.letter}</span>
              </button>
              <button
                className="btn-console text-xs"
                onClick={handleResetScenario}
                title="Reset simulation to initial baseline"
              >
                <RotateCcw size={12} />
                <span>Reset</span>
              </button>
            </div>
          </div>
        </div>

        {/* ============================================================== */}
        {/* 3. USER POLICY CONFIGURATION & RESTORE DEFAULTS                 */}
        {/* ============================================================== */}
        <div className="control-section">
          <div className="section-header-flex">
            <label className="section-label font-mono">USER POLICY CONTROLS</label>
            <Shield size={14} className="text-healthy" />
          </div>
          <div className="config-disclaimer-tag font-mono text-xs text-muted mb-2">
            Dynamic threshold & timing tuning for educational experimentation.
          </div>

          <div className="config-form">
            {/* Health Check Interval */}
            <div className="config-item">
              <div className="config-label-row">
                <span className="config-title">Health Check Timing</span>
                <span className="config-val font-mono">
                  {config.healthCheckIntervalSec}s
                </span>
              </div>
              <input
                type="range"
                min="1"
                max="5"
                step="1"
                className="config-slider"
                value={config.healthCheckIntervalSec}
                onChange={(e) =>
                  engine.updateConfig({
                    healthCheckIntervalSec: parseInt(e.target.value, 10),
                  })
                }
              />
              <span className="config-hint text-xs text-muted">
                Simulated interval between synthetic health checks (1s - 5s)
              </span>
            </div>

            {/* Failure Threshold */}
            <div className="config-item">
              <div className="config-label-row">
                <span className="config-title">Failed-Check Threshold</span>
                <span className="config-val font-mono">
                  {config.failureThresholdConsecutive} probes
                </span>
              </div>
              <input
                type="range"
                min="1"
                max="5"
                step="1"
                className="config-slider"
                value={config.failureThresholdConsecutive}
                onChange={(e) =>
                  engine.updateConfig({
                    failureThresholdConsecutive: parseInt(e.target.value, 10),
                  })
                }
              />
              <span className="config-hint text-xs text-muted">
                Consecutive probe timeouts before invoking quorum voting (1 - 5)
              </span>
            </div>

            {/* Replication Lag Limit */}
            <div className="config-item">
              <div className="config-label-row">
                <span className="config-title">Replication-Lag Limit</span>
                <span className="config-val font-mono">
                  {config.acceptableReplicationLagSec}s
                </span>
              </div>
              <input
                type="range"
                min="2"
                max="10"
                step="1"
                className="config-slider"
                value={config.acceptableReplicationLagSec}
                onChange={(e) =>
                  engine.updateConfig({
                    acceptableReplicationLagSec: parseInt(e.target.value, 10),
                  })
                }
              />
              <span className="config-hint text-xs text-muted">
                RPO Safety Gate: Blocks standby promotion if lag exceeds limit (2s - 10s)
              </span>
            </div>

            {/* Restore Defaults Action */}
            <button
              className="btn-console text-xs w-full mt-1"
              onClick={() => engine.restoreConfigDefaults()}
            >
              <Clock size={12} />
              <span>Restore Policy Defaults</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
