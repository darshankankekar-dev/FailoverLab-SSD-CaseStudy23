import React, { useState } from 'react';
import { AlertTriangle, RotateCcw, Pause, Play, Cpu, Check, X } from 'lucide-react';
import { controllerClient } from '../../api/controllerClient';
import type { ControllerStateDto } from '../../api/controllerClient';

interface SimulationControlsPanelProps {
  controllerState: ControllerStateDto | null;
  onStateChanged?: () => void;
}

const ALL_REGIONS = [
  { id: 'region-a', name: 'Mumbai (region-a)' },
  { id: 'region-b', name: 'Singapore (region-b)' },
  { id: 'region-c', name: 'Frankfurt (region-c)' },
  { id: 'region-d', name: 'Virginia (region-d)' },
  { id: 'region-e', name: 'São Paulo (region-e)' },
];

export const SimulationControlsPanel: React.FC<SimulationControlsPanelProps> = ({
  controllerState,
  onStateChanged,
}) => {
  const [selectedRegion, setSelectedRegion] = useState<string>('region-b');
  const [targetHealth, setTargetHealth] = useState<string>('DOWN');
  const [lagInput, setLagInput] = useState<number>(8.4);
  const [sequenceInput, setSequenceInput] = useState<number>(1045);
  const [wanLatencyInput, setWanLatencyInput] = useState<number>(120);

  // Confirmation state modal / popover
  const [pendingAction, setPendingAction] = useState<{
    type: string;
    description: string;
    execute: () => Promise<void>;
  } | null>(null);

  const [feedback, setFeedback] = useState<string | null>(null);
  const [isExecuting, setIsExecuting] = useState(false);

  const showConfirmation = (type: string, description: string, execute: () => Promise<void>) => {
    setPendingAction({ type, description, execute });
  };

  const confirmAction = async () => {
    if (!pendingAction) return;
    setIsExecuting(true);
    setFeedback(null);
    try {
      await pendingAction.execute();
      setFeedback(`Successfully applied: ${pendingAction.type}`);
      onStateChanged?.();
      setTimeout(() => setFeedback(null), 4000);
    } catch (err: any) {
      setFeedback(`Action failed: ${err.message}`);
    } finally {
      setIsExecuting(false);
      setPendingAction(null);
    }
  };

  const cancelAction = () => {
    setPendingAction(null);
  };

  // Actions
  const handleSetHealth = () => {
    showConfirmation(
      `Set ${selectedRegion} health to ${targetHealth}`,
      `This will mark ${selectedRegion} as ${targetHealth} in the controller registry. If marking active region DOWN, failover candidate selector will become triggerable.`,
      async () => {
        await controllerClient.setRegionalHealth(selectedRegion, targetHealth);
      }
    );
  };

  const handleSetLag = () => {
    showConfirmation(
      `Set ${selectedRegion} replication lag to ${lagInput}s`,
      `Injects ${lagInput}s replication lag for ${selectedRegion}. If exceeding threshold (${controllerState?.policy?.acceptable_replication_lag_sec ?? 5.0}s), RPO safety gate will block promotion.`,
      async () => {
        await controllerClient.setRegionalLag(selectedRegion, lagInput);
      }
    );
  };

  const handleSetSequence = () => {
    showConfirmation(
      `Set ${selectedRegion} applied sequence to ${sequenceInput}`,
      `Manually updates applied outbox event sequence position to #${sequenceInput}. Candidate selector uses this sequence for freshness ranking.`,
      async () => {
        await controllerClient.setRegionalSequence(selectedRegion, sequenceInput);
      }
    );
  };

  const handleSetWan = () => {
    showConfirmation(
      `Set ${selectedRegion} simulated WAN delay to ${wanLatencyInput}ms`,
      `Configures nominal WAN propagation delay for ${selectedRegion} requests to ${wanLatencyInput}ms.`,
      async () => {
        await controllerClient.setRegionalWanLatency(selectedRegion, wanLatencyInput);
      }
    );
  };

  const handlePauseReplication = () => {
    showConfirmation(
      `Pause replication to ${selectedRegion}`,
      `Temporarily stops outbox event delivery to ${selectedRegion}. Replication lag will steadily accumulate.`,
      async () => {
        await controllerClient.pauseReplication(selectedRegion);
      }
    );
  };

  const handleResumeReplication = () => {
    showConfirmation(
      `Resume replication to ${selectedRegion}`,
      `Resumes outbox event streaming to ${selectedRegion} to allow checkpoint catching up.`,
      async () => {
        await controllerClient.resumeReplication(selectedRegion);
      }
    );
  };

  const handleResetSingleRegion = () => {
    showConfirmation(
      `Restore ${selectedRegion} to Healthy Baseline`,
      `Resets ${selectedRegion} health to HEALTHY, replication lag to 0.8s, and resumes streaming replication.`,
      async () => {
        await controllerClient.resetRegional(selectedRegion);
      }
    );
  };

  const handleResetAll = () => {
    showConfirmation(
      `Reset Entire 5-Region Architecture to Baseline`,
      `Restores Region A (Mumbai) as active primary, marks all 4 standbys healthy with synchronized replication, resets fencing epoch to 101, and shifts gateway route to region-a.`,
      async () => {
        await controllerClient.resetSystem(false);
      }
    );
  };

  return (
    <div className="traffic-panel">
      <div className="traffic-panel-header">
        <h3>
          <Cpu size={18} className="text-warning" />
          <span>Regional Simulation & Administrative Chaos Controls</span>
        </h3>
        <div className="flex items-center gap-2">
          {feedback && <span className="text-xs text-healthy font-mono">{feedback}</span>}
          <button
            className="btn-console btn-ghost btn-sm text-xs text-danger"
            onClick={handleResetAll}
            title="Reset all five regions to initial baseline"
          >
            <RotateCcw size={12} />
            <span>Reset All to Baseline</span>
          </button>
        </div>
      </div>

      {/* Confirmation Banner if pending action */}
      {pendingAction && (
        <div className="mb-4 p-3 bg-amber-950/40 border border-amber-500/60 rounded-md">
          <div className="flex items-start gap-2 mb-2">
            <AlertTriangle size={16} className="text-amber-400 mt-0.5 shrink-0" />
            <div>
              <div className="font-semibold text-sm text-amber-200">
                Confirm Action: {pendingAction.type}
              </div>
              <p className="text-xs text-amber-300/80 mt-1">{pendingAction.description}</p>
            </div>
          </div>
          <div className="flex justify-end gap-2 mt-3">
            <button
              className="btn-console btn-ghost btn-sm text-xs"
              onClick={cancelAction}
              disabled={isExecuting}
            >
              <X size={12} />
              <span>Cancel</span>
            </button>
            <button
              className="btn-console btn-primary btn-sm text-xs"
              onClick={confirmAction}
              disabled={isExecuting}
            >
              <Check size={12} />
              <span>{isExecuting ? 'Applying...' : 'Confirm & Execute'}</span>
            </button>
          </div>
        </div>
      )}

      {/* Region Selector Bar */}
      <div className="flex items-center gap-3 mb-4 bg-slate-900/60 p-2.5 rounded border border-slate-700/60 flex-wrap">
        <label className="text-xs font-semibold text-muted">Target Application Region:</label>
        <select
          className="monitor-filter-select"
          value={selectedRegion}
          onChange={(e) => setSelectedRegion(e.target.value)}
        >
          {ALL_REGIONS.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name}
            </option>
          ))}
        </select>

        <button
          className="btn-console btn-ghost btn-sm text-xs ml-auto"
          onClick={handleResetSingleRegion}
          title="Restore this region to baseline"
        >
          <RotateCcw size={12} />
          <span>Restore {selectedRegion}</span>
        </button>
      </div>

      {/* Administrative Action Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 text-xs">
        {/* Control 1: Health State */}
        <div className="bg-slate-900/60 p-3 rounded border border-slate-800 flex flex-col justify-between">
          <div>
            <span className="font-semibold text-muted block mb-1">1. Regional Health Injection</span>
            <p className="text-secondary text-[11px] mb-2">Simulates instance collapse or recovery.</p>
            <select
              className="monitor-filter-select w-full mb-3"
              value={targetHealth}
              onChange={(e) => setTargetHealth(e.target.value)}
            >
              <option value="HEALTHY">HEALTHY (Normal)</option>
              <option value="DEGRADED">DEGRADED (High error rate)</option>
              <option value="DOWN">DOWN (Complete Outage)</option>
            </select>
          </div>
          <button className="btn-console btn-secondary btn-sm w-full" onClick={handleSetHealth}>
            <span>Apply Health ({targetHealth})</span>
          </button>
        </div>

        {/* Control 2: Replication Lag */}
        <div className="bg-slate-900/60 p-3 rounded border border-slate-800 flex flex-col justify-between">
          <div>
            <div className="flex justify-between items-center mb-1">
              <span className="font-semibold text-muted">2. Replication Lag Spike</span>
              <span className="font-mono text-bright font-bold">{lagInput.toFixed(1)}s</span>
            </div>
            <p className="text-secondary text-[11px] mb-2">Spikes async replication lag for testing Gate 4.</p>
            <input
              type="range"
              min="0.1"
              max="20.0"
              step="0.1"
              value={lagInput}
              onChange={(e) => setLagInput(Number(e.target.value))}
              className="w-full accent-cyan-400 mb-3"
            />
          </div>
          <button className="btn-console btn-secondary btn-sm w-full" onClick={handleSetLag}>
            <span>Inject {lagInput.toFixed(1)}s Lag</span>
          </button>
        </div>

        {/* Control 3: Sequence Number */}
        <div className="bg-slate-900/60 p-3 rounded border border-slate-800 flex flex-col justify-between">
          <div>
            <span className="font-semibold text-muted block mb-1">3. Applied Outbox Sequence</span>
            <p className="text-secondary text-[11px] mb-2">Forces checkpoint position for freshness tie-breaker.</p>
            <input
              type="number"
              min="0"
              max="99999"
              value={sequenceInput}
              onChange={(e) => setSequenceInput(Number(e.target.value))}
              className="monitor-filter-select w-full mb-3"
            />
          </div>
          <button className="btn-console btn-secondary btn-sm w-full" onClick={handleSetSequence}>
            <span>Set Sequence #{sequenceInput}</span>
          </button>
        </div>

        {/* Control 4: WAN Latency */}
        <div className="bg-slate-900/60 p-3 rounded border border-slate-800 flex flex-col justify-between">
          <div>
            <div className="flex justify-between items-center mb-1">
              <span className="font-semibold text-muted">4. WAN Delay Model</span>
              <span className="font-mono text-bright font-bold">{wanLatencyInput} ms</span>
            </div>
            <p className="text-secondary text-[11px] mb-2">Adjusts simulated geographic transit delay.</p>
            <input
              type="range"
              min="10"
              max="500"
              step="5"
              value={wanLatencyInput}
              onChange={(e) => setWanLatencyInput(Number(e.target.value))}
              className="w-full accent-cyan-400 mb-3"
            />
          </div>
          <button className="btn-console btn-secondary btn-sm w-full" onClick={handleSetWan}>
            <span>Set WAN {wanLatencyInput}ms</span>
          </button>
        </div>

        {/* Control 5: Pause / Resume Replication Target */}
        <div className="bg-slate-900/60 p-3 rounded border border-slate-800 flex flex-col justify-between col-span-1 md:col-span-2">
          <div>
            <span className="font-semibold text-muted block mb-1">5. Outbox Channel Pipeline State</span>
            <p className="text-secondary text-[11px] mb-2">
              Selectively pauses or resumes outbox event consumption and streaming for {selectedRegion}.
            </p>
          </div>
          <div className="flex gap-2">
            <button className="btn-console btn-secondary btn-sm flex-1" onClick={handlePauseReplication}>
              <Pause size={12} />
              <span>Pause Replication</span>
            </button>
            <button className="btn-console btn-primary btn-sm flex-1" onClick={handleResumeReplication}>
              <Play size={12} />
              <span>Resume Streaming</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
