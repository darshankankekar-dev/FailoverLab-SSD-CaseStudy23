import React, { useState } from 'react';
import {
  Play,
  CheckCircle,
  AlertTriangle,
  Clock,
  Radio,
  Flame,
  Shuffle,
  RefreshCw,
  ArrowRight,
  RotateCcw,
} from 'lucide-react';
import { SCENARIOS } from '../../data/scenarios';
import { simulationEngine } from '../../simulation/SimulationEngine';

interface ScenariosViewProps {
  onLaunchScenario: (scenarioId: string) => void;
}

export const ScenariosView: React.FC<ScenariosViewProps> = ({
  onLaunchScenario,
}) => {
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>(
    SCENARIOS[0].id
  );

  const activeScenario =
    SCENARIOS.find((s) => s.id === selectedScenarioId) || SCENARIOS[0];

  const getCategoryIcon = (category: string) => {
    switch (category) {
      case 'Partition':
        return <Radio size={16} className="text-danger" />;
      case 'Crash':
        return <Flame size={16} className="text-danger" />;
      case 'Flapping':
        return <Shuffle size={16} className="text-warning" />;
      case 'Degradation':
        return <Clock size={16} className="text-warning" />;
      case 'Maintenance':
        return <RefreshCw size={16} className="text-flow" />;
      default:
        return <AlertTriangle size={16} className="text-flow" />;
    }
  };

  return (
    <div className="scenarios-view">
      <div className="section-header">
        <div className="section-title-group">
          <div className="badge-tag badge-warning mb-2 font-mono text-xs">
            Simulation Catalog
          </div>
          <h1 className="section-title">Pre-Configured Failure Scenarios</h1>
          <p className="section-subtitle">
            Hands-on experiments demonstrating edge cases in multi-region failover, network
            partitions, and split-brain prevention.
          </p>
        </div>
      </div>

      <div className="scenarios-layout-grid">
        {/* Left column: Scenario Selector List */}
        <div className="scenarios-nav-list">
          {SCENARIOS.map((sc) => {
            const isSelected = sc.id === activeScenario.id;
            return (
              <div
                key={sc.id}
                className={`scenario-list-item ${isSelected ? 'scenario-item-selected' : ''}`}
                onClick={() => setSelectedScenarioId(sc.id)}
              >
                <div className="item-header-row">
                  <div className="item-icon-title">
                    {getCategoryIcon(sc.category)}
                    <span className="item-category font-mono text-xs">
                      {sc.category.toUpperCase()}
                    </span>
                  </div>
                  <span
                    className={`badge-tag text-xs font-mono ${
                      sc.difficulty === 'Advanced'
                        ? 'badge-danger'
                        : sc.difficulty === 'Intermediate'
                        ? 'badge-warning'
                        : 'badge-healthy'
                    }`}
                  >
                    {sc.difficulty}
                  </span>
                </div>
                <h3 className="item-title">{sc.title}</h3>
                <p className="item-subtitle text-xs text-secondary">{sc.subtitle}</p>
              </div>
            );
          })}
        </div>

        {/* Right column: Active Scenario Inspector & Launcher */}
        <div className="scenario-detail-card">
          <div className="detail-card-top">
            <div className="detail-meta-row">
              <span className="badge-tag badge-warning font-mono text-xs">
                {activeScenario.category}
              </span>
              <span className="font-mono text-xs text-muted">
                Difficulty: {activeScenario.difficulty}
              </span>
            </div>
            <h2 className="detail-scenario-title">{activeScenario.title}</h2>
            <p className="detail-scenario-subtitle text-secondary">
              {activeScenario.subtitle}
            </p>
          </div>

          <div className="detail-body-section">
            <h3 className="section-subheading font-mono text-xs">EXECUTIVE SUMMARY</h3>
            <p className="detail-summary-text text-sm text-secondary">
              {activeScenario.summary}
            </p>
          </div>

          {/* Setup & Expected Behaviour Box */}
          <div className="detail-body-section">
            <h3 className="section-subheading font-mono text-xs">SCENARIO SETUP</h3>
            <p className="detail-summary-text text-xs text-bright font-mono bg-panel p-2 rounded border border-subtle">
              {activeScenario.setup}
            </p>
          </div>

          <div className="detail-body-section">
            <h3 className="section-subheading font-mono text-xs">EXPECTED BEHAVIOUR & SAFETY INVARIANTS</h3>
            <p className="detail-summary-text text-xs text-healthy font-mono bg-panel p-2 rounded border border-subtle">
              {activeScenario.expectedBehaviour}
            </p>
          </div>

          {/* Metrics Target Box */}
          <div className="scenario-metrics-bar">
            <div className="scenario-metric-box">
              <span className="metric-box-label font-mono text-xs text-flow">
                Target RTO
              </span>
              <span className="metric-box-value font-mono text-bright">
                {activeScenario.expectedRto}
              </span>
            </div>
            <div className="scenario-metric-box">
              <span className="metric-box-label font-mono text-xs text-warning">
                Target RPO
              </span>
              <span className="metric-box-value font-mono text-bright">
                {activeScenario.expectedRpo}
              </span>
            </div>
          </div>

          {/* Learning Objectives */}
          <div className="detail-body-section">
            <h3 className="section-subheading font-mono text-xs">LEARNING OBJECTIVES</h3>
            <div className="objectives-list">
              {activeScenario.objectives.map((obj, i) => (
                <div key={i} className="objective-item text-xs text-secondary">
                  <CheckCircle size={14} className="text-healthy obj-icon" />
                  <span>{obj}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Step-by-Step Failure Progression */}
          <div className="detail-body-section">
            <h3 className="section-subheading font-mono text-xs">
              EXECUTION PROGRESSION
            </h3>
            <div className="steps-timeline">
              {activeScenario.steps.map((step, idx) => (
                <div key={idx} className="step-row">
                  <div className="step-num font-mono">0{idx + 1}</div>
                  <div className="step-content">
                    <div className="step-phase font-semibold text-bright text-xs">
                      {step.phase}
                    </div>
                    <div className="step-desc text-xs text-secondary">
                      {step.description}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Launch & Reset Actions */}
          <div className="detail-action-footer">
            <div className="footer-callout text-xs text-muted">
              Launch this failure topology into the Live Simulator and observe the safety gate evaluation.
            </div>
            <div className="flex gap-2 w-full mt-2">
              <button
                className="btn-console text-xs flex-1"
                onClick={() => {
                  if (activeScenario.resetScenario) {
                    activeScenario.resetScenario(simulationEngine);
                  } else {
                    simulationEngine.reset();
                  }
                  onLaunchScenario(activeScenario.id);
                }}
              >
                <RotateCcw size={14} />
                <span>Reset Scenario</span>
              </button>
              <button
                className="btn-console btn-primary launch-scenario-btn flex-2"
                onClick={() => onLaunchScenario(activeScenario.id)}
              >
                <Play size={15} />
                <span>Run Scenario {activeScenario.letter} in Simulator</span>
                <ArrowRight size={15} />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
