import React, { useState } from 'react';
import {
  Shield,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Play,
  RotateCcw,
} from 'lucide-react';
import { controllerClient } from '../../api/controllerClient';
import type { ControllerStateDto, TransitionResponseDto, GateEvaluationResultDto } from '../../api/controllerClient';

interface FailoverWorkflowProgressProps {
  controllerState: ControllerStateDto | null;
  onWorkflowComplete?: () => void;
}

const DEFAULT_STEPS = [
  { id: 1, name: 'Gate 1: Primary Outage Detection', desc: 'Evaluates consecutive health failures against threshold (3 failures).' },
  { id: 2, name: 'Gate 2: Quorum Majority Verification', desc: 'Validates 2/3 majority consensus across 3 independent voters.' },
  { id: 3, name: 'Gate 3: Candidate Evaluation & Selection', desc: 'Evaluates all healthy standby candidates; selects optimal target.' },
  { id: 4, name: 'Gate 4: Replication Lag Policy (RPO)', desc: 'Guarantees candidate replication lag satisfies configured RPO limit (≤5.0s).' },
  { id: 5, name: 'Gate 5: Primary Fencing & Epoch Advance', desc: 'Revokes primary lease and increments monotonic fencing epoch token.' },
  { id: 6, name: 'Gate 6: Dual-Primary Prevention', desc: 'Verifies no dual-writer condition can exist before promoting standby.' },
  { id: 7, name: 'Gate 7: Standby Promotion', desc: 'Promotes candidate database to READ_WRITE with advance epoch.' },
  { id: 8, name: 'Gate 8: Gateway Route Shift', desc: 'Updates ingress proxy routing table to direct customer traffic to new primary.' },
  { id: 9, name: 'Gate 9: Synthetic Route Verification', desc: 'Probes HTTP and database reachable before closing failover transition.' },
  { id: 10, name: 'Step 10: Final Active Region Confirmation', desc: 'Transitions controller state to SECONDARY_ACTIVE and audits transition.' },
];

export const FailoverWorkflowProgress: React.FC<FailoverWorkflowProgressProps> = ({
  controllerState,
  onWorkflowComplete,
}) => {
  const [targetSelection, setTargetSelection] = useState<string>('auto');
  const [forceOverride, setForceOverride] = useState<boolean>(false);
  const [isExecuting, setIsExecuting] = useState<boolean>(false);
  const [lastTransition, setLastTransition] = useState<TransitionResponseDto | null>(null);
  const [errorFeedback, setErrorFeedback] = useState<string | null>(null);

  const activeRegion = controllerState?.active_region || 'region-a';
  const fencingEpoch = controllerState?.fencing_epoch || 101;
  const currentState = controllerState?.controller_state || 'HEALTHY';

  const handleTriggerFailover = async () => {
    setIsExecuting(true);
    setErrorFeedback(null);
    try {
      const res = await controllerClient.triggerFailover({
        force: forceOverride,
        target_region: targetSelection,
        reason: targetSelection === 'auto'
          ? 'Automated failover drill with 5-region candidate selection'
          : `Targeted manual failover drill to ${targetSelection}`,
      });
      setLastTransition(res);
      onWorkflowComplete?.();
    } catch (err: any) {
      setErrorFeedback(err.message || 'Failover blocked or rejected by controller.');
    } finally {
      setIsExecuting(false);
    }
  };

  const handleFailback = async () => {
    setIsExecuting(true);
    setErrorFeedback(null);
    try {
      const res = await controllerClient.triggerFailback({
        operator_id: 'ops-lead',
        confirmation: true,
        target_region: 'region-a',
        reason: 'Operator authorized guarded failback to Region A (Mumbai)',
      });
      setLastTransition(res);
      onWorkflowComplete?.();
    } catch (err: any) {
      setErrorFeedback(err.message || 'Failback rejected.');
    } finally {
      setIsExecuting(false);
    }
  };

  // Map results to steps
  const gateResultsMap = new Map<number, GateEvaluationResultDto>();
  if (lastTransition && lastTransition.gate_results) {
    lastTransition.gate_results.forEach((gr, idx) => {
      gateResultsMap.set(idx + 1, gr);
    });
  }

  return (
    <div className="traffic-panel">
      <div className="traffic-panel-header">
        <h3>
          <Shield size={18} className="text-healthy" />
          <span>Multi-Region Failover Safety Gates & Execution Visibility</span>
        </h3>
        <div className="flex items-center gap-2">
          <span className="badge-tag-sm badge-info font-mono">
            Active: <strong className="text-white ml-1">{activeRegion}</strong>
          </span>
          <span className="badge-tag-sm badge-warning font-mono">
            Epoch: <strong className="text-white ml-1">#{fencingEpoch}</strong>
          </span>
          <span
            className={`badge-tag-sm ${
              currentState === 'HEALTHY'
                ? 'badge-healthy'
                : currentState === 'SECONDARY_ACTIVE'
                ? 'badge-info'
                : 'badge-danger'
            }`}
          >
            {currentState}
          </span>
        </div>
      </div>

      {/* Control Action Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-3 bg-slate-900/60 rounded border border-slate-700/60 mb-4">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-1.5">
            <label className="text-xs font-semibold text-muted">Target Selection:</label>
            <select
              className="monitor-filter-select"
              value={targetSelection}
              onChange={(e) => setTargetSelection(e.target.value)}
              disabled={isExecuting}
            >
              <option value="auto">Auto (Dynamic Candidate Selection)</option>
              <option value="region-b">region-b (Singapore)</option>
              <option value="region-c">region-c (Frankfurt)</option>
              <option value="region-d">region-d (Virginia)</option>
              <option value="region-e">region-e (São Paulo)</option>
            </select>
          </div>

          <label className="flex items-center gap-1.5 text-xs text-muted cursor-pointer select-none">
            <input
              type="checkbox"
              checked={forceOverride}
              onChange={(e) => setForceOverride(e.target.checked)}
              disabled={isExecuting}
              className="rounded accent-cyan-400"
            />
            <span>Force Bypass (Drill Mode)</span>
          </label>
        </div>

        <div className="flex items-center gap-2">
          <button
            className="btn-console btn-primary btn-sm"
            onClick={handleTriggerFailover}
            disabled={isExecuting}
          >
            <Play size={12} />
            <span>{isExecuting ? 'Executing Workflow...' : 'Trigger Failover'}</span>
          </button>

          {activeRegion !== 'region-a' && (
            <button
              className="btn-console btn-secondary btn-sm"
              onClick={handleFailback}
              disabled={isExecuting}
              title="Guarded failback back to Mumbai"
            >
              <RotateCcw size={12} />
              <span>Guarded Failback</span>
            </button>
          )}
        </div>
      </div>

      {/* Status Feedback / Blocked Banner */}
      {errorFeedback && (
        <div className="mb-4 p-3 bg-rose-950/40 border border-rose-500/60 rounded flex items-start gap-2">
          <AlertTriangle size={16} className="text-rose-400 mt-0.5 shrink-0" />
          <div className="text-xs text-rose-200">
            <strong>Transition Rejected:</strong> {errorFeedback}
          </div>
        </div>
      )}

      {lastTransition && (
        <div
          className={`mb-4 p-3 rounded border text-xs ${
            lastTransition.status === 'SUCCESS'
              ? 'bg-emerald-950/40 border-emerald-500/60 text-emerald-200'
              : 'bg-rose-950/40 border-rose-500/60 text-rose-200'
          }`}
        >
          <div className="font-bold flex items-center gap-2">
            {lastTransition.status === 'SUCCESS' ? (
              <CheckCircle2 size={14} className="text-emerald-400" />
            ) : (
              <XCircle size={14} className="text-rose-400" />
            )}
            <span>Transition Outcome: {lastTransition.status}</span>
          </div>
          <p className="mt-1 text-slate-300">{lastTransition.message}</p>
          {lastTransition.blocked_reason && (
            <p className="mt-1 text-rose-300 font-mono">Blocked Reason: {lastTransition.blocked_reason}</p>
          )}
        </div>
      )}

      {/* 10-Step Safety Workflow Stepper */}
      <div className="failover-steps-list">
        {DEFAULT_STEPS.map((step) => {
          const evalResult = gateResultsMap.get(step.id);
          const hasRun = evalResult !== undefined;
          const passed = evalResult?.passed ?? false;

          return (
            <div
              key={step.id}
              className={`failover-step-item ${
                hasRun ? (passed ? 'step-passed' : 'step-failed') : ''
              }`}
            >
              <div className="failover-step-num">
                {hasRun ? (
                  passed ? (
                    <CheckCircle2 size={14} />
                  ) : (
                    <XCircle size={14} />
                  )
                ) : (
                  step.id
                )}
              </div>

              <div className="flex-1">
                <div className="flex justify-between items-center">
                  <span className="font-semibold text-white">{step.name}</span>
                  {hasRun ? (
                    <span
                      className={`badge-tag-sm ${passed ? 'badge-healthy' : 'badge-danger'}`}
                    >
                      {passed ? 'PASSED' : 'BLOCKED / FAILED'}
                    </span>
                  ) : (
                    <span className="badge-tag-sm badge-secondary text-muted">IDLE / READY</span>
                  )}
                </div>

                <p className="text-secondary text-xs mt-0.5">{step.desc}</p>

                {hasRun && evalResult?.reason && (
                  <div className="mt-1 font-mono text-[11px] text-slate-300 bg-slate-900/50 p-1.5 rounded">
                    Result: {evalResult.reason}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
