import React, { useState, useEffect } from 'react';
import {
  FileText,
  Download,
  FileSpreadsheet,
  Save,
  Trash2,
  CheckCircle,
  AlertOctagon,
  Clock,
  Calculator,
  GraduationCap,
  ArrowRight,
  Sparkles,
} from 'lucide-react';
import { QUIZ_QUESTIONS } from '../../data/quizData';
import { SCENARIOS } from '../../data/scenarios';
import { useSimulation } from '../../simulation/useSimulation';
import { MetricsDashboard } from '../simulator/MetricsDashboard';

interface PersistedRunSummary {
  savedAt: string;
  scenarioTitle: string;
  scenarioId: string;
  initialConditions: string;
  configuredThresholds: {
    healthCheckIntervalSec: number;
    failureThresholdConsecutive: number;
    quorumMajorityRequired: number;
    acceptableReplicationLagSec: number;
  };
  finalState: {
    regionARole: string;
    regionAWrites: boolean;
    regionAFenced: boolean;
    regionBRole: string;
    regionBWrites: boolean;
    activeRoutingTarget: string;
    fencingGenerationId: number;
  };
  simulatedRequests: {
    total: number;
    successful: number;
    failed: number;
    errorRate: number;
  };
  outcome: 'SUCCEEDED' | 'BLOCKED' | 'IN_PROGRESS' | 'NOMINAL';
  outcomeReason: string;
  keyLearningPoints: string[];
  eventCount: number;
}

interface UserPreferences {
  autoSaveRuns: boolean;
  selectedSla: number;
  exportFormat: 'json' | 'csv' | 'md';
}

const DEFAULT_PREFS: UserPreferences = {
  autoSaveRuns: true,
  selectedSla: 99.99,
  exportFormat: 'json',
};

export const ReportsView: React.FC = () => {
  const {
    regionA,
    regionB,
    controllerState,
    consecutiveFailures,
    config,
    voters,
    replication,
    dns,
    simulatedTimeSeconds,
    telemetry,
    auditEvents,
    leaseFence,
  } = useSimulation();

  // Local storage state for user preferences & saved completed run
  const [userPrefs, setUserPrefs] = useState<UserPreferences>(() => {
    try {
      const saved = localStorage.getItem('failoverlab_user_prefs');
      return saved ? JSON.parse(saved) : DEFAULT_PREFS;
    } catch {
      return DEFAULT_PREFS;
    }
  });

  const [savedRunSummary, setSavedRunSummary] = useState<PersistedRunSummary | null>(() => {
    try {
      const saved = localStorage.getItem('failoverlab_last_run_summary');
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  });

  const [selectedScenarioId, setSelectedScenarioId] = useState<string>('scenario-b-primary-crash');
  const [saveStatusMsg, setSaveStatusMsg] = useState<string | null>(null);

  // Quiz state
  const [userAnswers, setUserAnswers] = useState<Record<string, number>>({});
  const [submittedQuiz, setSubmittedQuiz] = useState<boolean>(false);

  // SLA calculator state
  const [selectedSla, setSelectedSla] = useState<number>(userPrefs.selectedSla);

  // Sync preferences to localStorage
  useEffect(() => {
    try {
      localStorage.setItem('failoverlab_user_prefs', JSON.stringify({ ...userPrefs, selectedSla }));
    } catch (e) {
      console.error('Failed to save preferences to localStorage', e);
    }
  }, [userPrefs, selectedSla]);

  const slaTiers = [
    { tier: '99.0%', value: 99.0, yearlyDown: '3.65 days', monthlyDown: '7.2 hours' },
    { tier: '99.9%', value: 99.9, yearlyDown: '8.76 hours', monthlyDown: '43.2 minutes' },
    { tier: '99.95%', value: 99.95, yearlyDown: '4.38 hours', monthlyDown: '21.6 minutes' },
    { tier: '99.99%', value: 99.99, yearlyDown: '52.56 mins', monthlyDown: '4.32 minutes' },
    { tier: '99.999%', value: 99.999, yearlyDown: '5.26 mins', monthlyDown: '25.9 seconds' },
  ];

  // Request & Metrics calculations derived strictly from model
  const totalSimulatedRequests = Math.round(simulatedTimeSeconds * telemetry.totalClientRps);
  const failedSimulatedRequests = Math.round(
    totalSimulatedRequests * (telemetry.clientErrorRate / 100)
  );
  const successfulSimulatedRequests = Math.max(0, totalSimulatedRequests - failedSimulatedRequests);

  // Failover outcome derivation
  const determineOutcome = (): 'SUCCEEDED' | 'BLOCKED' | 'IN_PROGRESS' | 'NOMINAL' => {
    if (controllerState === 'FAILOVER_BLOCKED') return 'BLOCKED';
    if (controllerState === 'SECONDARY_ACTIVE' || regionB.role === 'ACTIVE') return 'SUCCEEDED';
    if (controllerState === 'HEALTHY' && consecutiveFailures === 0 && auditEvents.length <= 1) {
      return 'NOMINAL';
    }
    return 'IN_PROGRESS';
  };

  const outcome = determineOutcome();

  // Determine outcome reason
  const determineOutcomeReason = (): string => {
    if (outcome === 'BLOCKED') {
      const blockedEvent = auditEvents.find((e) =>
        e.title.toLowerCase().includes('blocked') || e.description.toLowerCase().includes('blocked')
      );
      return blockedEvent
        ? `${blockedEvent.title}: ${blockedEvent.description}`
        : 'Safety gate halted transition to prevent violation of single-writer or lag safety policies.';
    }
    if (outcome === 'SUCCEEDED') {
      return `All 5 safety gates passed cleanly. Primary isolated with Generation #${leaseFence.generationId}, Region B promoted to ACTIVE, DNS route verified operational.`;
    }
    if (outcome === 'NOMINAL') {
      return 'Initial steady-state baseline. Single-writer invariant verified in Region A with 0 consecutive heartbeat failures.';
    }
    return `State machine is currently executing transition phase [${controllerState}]. Evaluating safety gates and consensus.`;
  };

  // Derive key educational learning points for current outcome
  const deriveKeyLearningPoints = (): string[] => {
    const points: string[] = [];
    if (outcome === 'SUCCEEDED') {
      points.push(
        'Monotonic fencing tokens (Martin Kleppmann generation ID) strictly prevented split-brain writes during promotion.',
        'Majority quorum (2 of 3 votes) broke network partition ambiguity, authorizing automated failover.',
        'Pre-promotion replication check verified WAL delta within policy (< 5.0s), guaranteeing acceptable RPO.',
        'Low-TTL DNS CNAME propagation safely diverted ingress client traffic to the newly promoted active region.'
      );
    } else if (outcome === 'BLOCKED') {
      points.push(
        'Safety gate enforcement successfully prioritized data integrity over premature availability.',
        'High replication lag or split quorum stopped the controller from promoting a stale or partition-isolated node.',
        'Human intervention or recovery of replication is required before promotion can proceed safely.'
      );
    } else if (outcome === 'NOMINAL') {
      points.push(
        'In active-passive architecture, only the primary accepts write transactions; standby strictly receives WAL logs.',
        'Consecutive-failure debouncing prevents false-positive failovers caused by transient network spikes.',
        'Zero data divergence exists while replication lag remains nominal.'
      );
    } else {
      points.push(
        'Failover coordination follows an idempotent multi-step state machine with explicit checkpoints.',
        'Primary write permissions must be unequivocally revoked before secondary write leases can be granted.'
      );
    }
    return points;
  };

  const currentScenario =
    SCENARIOS.find((s) => s.id === selectedScenarioId) || SCENARIOS[1];

  // Build the complete current run summary object
  const currentRunSummary: PersistedRunSummary = {
    savedAt: new Date().toISOString(),
    scenarioTitle: currentScenario.title,
    scenarioId: currentScenario.id,
    initialConditions:
      'Region A (Mumbai) ACTIVE [Epoch 101, writes allowed], Region B (Singapore) STANDBY [Epoch 101, writes blocked], WAL replication nominal (0.8s lag), 3 Quorum Observers healthy.',
    configuredThresholds: {
      healthCheckIntervalSec: config.healthCheckIntervalSec,
      failureThresholdConsecutive: config.failureThresholdConsecutive,
      quorumMajorityRequired: config.majorityRequired,
      acceptableReplicationLagSec: config.acceptableReplicationLagSec,
    },
    finalState: {
      regionARole: regionA.role,
      regionAWrites: regionA.acceptsWrites,
      regionAFenced: regionA.isFenced,
      regionBRole: regionB.role,
      regionBWrites: regionB.acceptsWrites,
      activeRoutingTarget: dns.activeDnsTarget === 'region-a' ? 'Region A (Mumbai)' : 'Region B (Singapore)',
      fencingGenerationId: leaseFence.generationId,
    },
    simulatedRequests: {
      total: totalSimulatedRequests,
      successful: successfulSimulatedRequests,
      failed: failedSimulatedRequests,
      errorRate: telemetry.clientErrorRate,
    },
    outcome,
    outcomeReason: determineOutcomeReason(),
    keyLearningPoints: deriveKeyLearningPoints(),
    eventCount: auditEvents.length,
  };

  // Local storage persistence handlers
  const handleSaveCurrentRun = () => {
    try {
      localStorage.setItem('failoverlab_last_run_summary', JSON.stringify(currentRunSummary));
      setSavedRunSummary(currentRunSummary);
      setSaveStatusMsg('Run summary saved locally to browser storage!');
      setTimeout(() => setSaveStatusMsg(null), 3000);
    } catch (e) {
      console.error('Failed to save run summary', e);
      setSaveStatusMsg('Error saving run summary to browser storage.');
      setTimeout(() => setSaveStatusMsg(null), 3000);
    }
  };

  const handleClearSavedRun = () => {
    try {
      localStorage.removeItem('failoverlab_last_run_summary');
      setSavedRunSummary(null);
      setSaveStatusMsg('Saved run history cleared.');
      setTimeout(() => setSaveStatusMsg(null), 2500);
    } catch (e) {
      console.error('Failed to clear saved run', e);
    }
  };

  // Export handlers
  const handleExportJson = () => {
    const fullReportPayload = {
      reportType: 'FailoverLab Experiment Report',
      version: '1.0.0',
      caseStudy: 23,
      topic: 'Multi-Region Active-Passive Failover Controller',
      generatedAt: new Date().toISOString(),
      runSummary: currentRunSummary,
      activeConfig: config,
      orderedEventTimeline: auditEvents.map((ev, idx) => ({
        sequenceNumber: auditEvents.length - idx,
        timestamp: ev.timestamp,
        simulatedTimeSeconds: ev.simTime,
        subsystem: ev.subsystem,
        severity: ev.severity,
        title: ev.title,
        description: ev.description,
      })),
      stateSnapshot: {
        controllerState,
        simulatedTimeSeconds,
        regionA,
        regionB,
        dns,
        leaseFence,
        replication,
        voters,
      },
    };

    const dataStr =
      'data:text/json;charset=utf-8,' +
      encodeURIComponent(JSON.stringify(fullReportPayload, null, 2));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute('href', dataStr);
    downloadAnchor.setAttribute(
      'download',
      `failoverlab-experiment-report-${currentScenario.id}-${Date.now()}.json`
    );
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  const handleExportCsvTimeline = () => {
    const headers = [
      'Sequence',
      'SimulatedTime',
      'Severity',
      'Subsystem',
      'Title',
      'Description',
    ];
    const rows = auditEvents.map((ev, idx) => {
      const seq = auditEvents.length - idx;
      return [
        seq,
        `"${ev.timestamp}"`,
        `"${ev.severity}"`,
        `"${ev.subsystem}"`,
        `"${ev.title.replace(/"/g, '""')}"`,
        `"${ev.description.replace(/"/g, '""')}"`,
      ].join(',');
    });

    const csvContent =
      'data:text/csv;charset=utf-8,' +
      encodeURIComponent([headers.join(','), ...rows].join('\n'));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute('href', csvContent);
    downloadAnchor.setAttribute(
      'download',
      `failoverlab-timeline-${currentScenario.id}-${Date.now()}.csv`
    );
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  const handleExportPostMortem = () => {
    const postMortemMarkdown = `# FailoverLab Incident Post-Mortem Report
**Case Study 23: Multi-Region Active-Passive Failover Controller**
**Date Generated:** ${new Date().toISOString()}
**Scenario:** ${currentScenario.title}

## 1. Executive Summary
- **Outcome Status:** ${outcome}
- **Outcome Reason:** ${determineOutcomeReason()}
- **Current State:** ${controllerState}
- **Active Serving Region:** ${regionB.role === 'ACTIVE' ? 'Region B (Singapore)' : 'Region A (Mumbai)'}
- **Active Fencing Token:** Generation ID #${leaseFence.generationId}
- **Simulation Uptime:** ${simulatedTimeSeconds} simulated seconds
- **Simulated Requests Processed:** ${totalSimulatedRequests.toLocaleString()} (Successful: ${successfulSimulatedRequests.toLocaleString()}, Dropped: ${failedSimulatedRequests.toLocaleString()})
- **Simulated Error Rate:** ${telemetry.clientErrorRate}%

## 2. Configured Safety Policies
- Synthetic Probe Interval: ${config.healthCheckIntervalSec}s
- Consecutive Failure Threshold: ${config.failureThresholdConsecutive} probes
- Quorum Size: ${config.quorumSize} nodes (Majority required: ${config.majorityRequired} votes)
- Acceptable Replication Lag: ${config.acceptableReplicationLagSec}.0s

## 3. Initial vs. Final State Comparison
- **Initial:** Region A ACTIVE (writes allowed), Region B STANDBY (writes blocked), Epoch #101
- **Final:** Region A ${regionA.role} (writes: ${regionA.acceptsWrites ? 'Yes' : 'No'}, fenced: ${regionA.isFenced ? 'Yes' : 'No'}), Region B ${regionB.role} (writes: ${regionB.acceptsWrites ? 'Yes' : 'No'}), Routing Target: ${dns.activeDnsTarget}

## 4. Key Architectural Learning Points
${deriveKeyLearningPoints().map((pt) => `- ${pt}`).join('\n')}

## 5. Ordered Event Timeline (${auditEvents.length} Events)
${auditEvents
  .map(
    (ev, idx) =>
      `${auditEvents.length - idx}. [${ev.timestamp}] [${ev.subsystem}] [${ev.severity.toUpperCase()}] ${ev.title}: ${ev.description}`
  )
  .join('\n')}

---
*Generated by FailoverLab - System Design & Software Systems Development Virtual Laboratory.*
`;

    const blob = new Blob([postMortemMarkdown], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute('href', url);
    downloadAnchor.setAttribute(
      'download',
      `failoverlab-postmortem-${currentScenario.id}-${Date.now()}.md`
    );
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  // Quiz evaluation
  const handleSelectOption = (questionId: string, optionIndex: number) => {
    if (submittedQuiz) return;
    setUserAnswers((prev) => ({
      ...prev,
      [questionId]: optionIndex,
    }));
  };

  const calculateScore = () => {
    let score = 0;
    QUIZ_QUESTIONS.forEach((q) => {
      if (userAnswers[q.id] === q.correctIndex) {
        score += 1;
      }
    });
    return score;
  };

  const score = calculateScore();

  return (
    <div className="reports-view">
      {/* Page Header */}
      <div className="section-header">
        <div className="section-title-group">
          <div className="badge-tag badge-info mb-2 font-mono text-xs">
            Evaluation & Analytics Console
          </div>
          <h1 className="section-title">Telemetry Reports & Experiment Summary</h1>
          <p className="section-subtitle">
            Comprehensive audit reports, SLA budget calculators, and academic knowledge checks.
            Export reproducible experiment data in JSON, CSV, or Markdown.
          </p>
        </div>
      </div>

      {/* Live Compact Metrics Dashboard */}
      <div className="reports-metrics-row mb-5">
        <MetricsDashboard />
      </div>

      {/* Save status notification */}
      {saveStatusMsg && (
        <div className="saved-run-alert mb-4 font-mono text-xs">
          <Sparkles size={14} className="text-flow" />
          <span>{saveStatusMsg}</span>
        </div>
      )}

      {/* SECTION D: EXPERIMENT REPORT RUN SUMMARY */}
      <div className="experiment-report-card mb-5">
        <div className="report-summary-header">
          <div className="report-summary-title-group">
            <FileText size={18} className="text-flow" />
            <div>
              <h2 className="report-card-title text-base font-bold">
                Experiment Run Summary
              </h2>
              <p className="text-xs text-muted font-mono">
                Model run audit and safety outcome analysis
              </p>
            </div>
          </div>

          <div className="report-actions-bar">
            {/* Scenario Picker */}
            <div className="scenario-select-wrapper font-mono text-xs">
              <span className="text-muted mr-1">Scenario:</span>
              <select
                className="btn-console text-xs"
                value={selectedScenarioId}
                onChange={(e) => setSelectedScenarioId(e.target.value)}
                aria-label="Select scenario for report summary"
              >
                {SCENARIOS.map((sc) => (
                  <option key={sc.id} value={sc.id}>
                    {sc.letter}: {sc.title.replace('SCENARIO ', '')}
                  </option>
                ))}
              </select>
            </div>

            {/* Save Run button */}
            <button
              className="btn-console text-xs"
              onClick={handleSaveCurrentRun}
              title="Save current run summary to browser local storage"
              aria-label="Save current run summary to local storage"
            >
              <Save size={13} />
              <span>Save Run</span>
            </button>

            {/* Export JSON */}
            <button
              className="btn-console text-xs btn-primary"
              onClick={handleExportJson}
              title="Download complete structured experiment report as JSON"
              aria-label="Export complete experiment report as JSON"
            >
              <Download size={13} />
              <span>Export Report (.json)</span>
            </button>

            {/* Export CSV Timeline */}
            <button
              className="btn-console text-xs btn-export"
              onClick={handleExportCsvTimeline}
              title="Download event timeline as CSV"
              aria-label="Export event timeline as CSV"
            >
              <FileSpreadsheet size={13} />
              <span>Export Timeline (.csv)</span>
            </button>

            {/* Export Markdown Post-Mortem */}
            <button
              className="btn-console text-xs"
              onClick={handleExportPostMortem}
              title="Download Markdown incident post-mortem"
              aria-label="Export incident post-mortem as Markdown"
            >
              <FileText size={13} />
              <span>Post-Mortem (.md)</span>
            </button>
          </div>
        </div>

        {/* Experiment Outcome Banner */}
        <div
          className={`outcome-banner mb-4 ${
            outcome === 'SUCCEEDED'
              ? 'outcome-banner-success'
              : outcome === 'BLOCKED'
              ? 'outcome-banner-blocked'
              : outcome === 'NOMINAL'
              ? 'outcome-banner-info'
              : 'outcome-banner-progress'
          }`}
        >
          <div className="outcome-banner-left">
            {outcome === 'SUCCEEDED' ? (
              <CheckCircle size={20} className="text-healthy" />
            ) : outcome === 'BLOCKED' ? (
              <AlertOctagon size={20} className="text-danger" />
            ) : (
              <Clock size={20} className="text-flow" />
            )}
            <div>
              <span className="outcome-banner-label font-mono font-bold text-xs uppercase">
                Failover Outcome: {outcome}
              </span>
              <p className="outcome-banner-desc text-xs mt-0.5">
                {currentRunSummary.outcomeReason}
              </p>
            </div>
          </div>
          <span className="badge-tag font-mono text-xs">
            {auditEvents.length} Events Logged
          </span>
        </div>

        {/* 4-Box Summary Grid: Scenario, Initial Conditions, Configured Policies, Requests */}
        <div className="report-summary-meta-grid mb-4">
          {/* Box 1: Selected Scenario */}
          <div className="summary-box">
            <span className="summary-box-title font-mono text-xs text-muted">
              1. Selected Scenario
            </span>
            <span className="summary-box-heading font-semibold text-bright text-xs mt-1">
              {currentScenario.title}
            </span>
            <p className="text-xs text-secondary mt-1">
              {currentScenario.summary}
            </p>
          </div>

          {/* Box 2: Initial Conditions */}
          <div className="summary-box">
            <span className="summary-box-title font-mono text-xs text-muted">
              2. Initial Conditions
            </span>
            <div className="font-mono text-xs text-secondary mt-1 space-y-1">
              <div>• Region A (Mumbai): ACTIVE writer (Epoch #101)</div>
              <div>• Region B (Singapore): STANDBY replica (Epoch #101)</div>
              <div>• WAL replication: Nominal (~0.8s lag)</div>
              <div>• Quorum: 3 observers healthy, 0 consecutive failures</div>
            </div>
          </div>

          {/* Box 3: Configured Policies */}
          <div className="summary-box">
            <span className="summary-box-title font-mono text-xs text-muted">
              3. Configured Thresholds & Policies
            </span>
            <div className="font-mono text-xs text-secondary mt-1 space-y-1">
              <div>• Health Check Interval: {config.healthCheckIntervalSec}.0s</div>
              <div>• Failure Threshold: {config.failureThresholdConsecutive} consecutive probes</div>
              <div>• Quorum Majority: {config.majorityRequired} of {config.quorumSize} votes (66.7%)</div>
              <div>• Max Acceptable Lag: {config.acceptableReplicationLagSec}.0s</div>
            </div>
          </div>

          {/* Box 4: Simulated Client Requests */}
          <div className="summary-box">
            <span className="summary-box-title font-mono text-xs text-muted">
              4. Simulated Client Traffic (Model State)
            </span>
            <div className="font-mono text-xs text-secondary mt-1 space-y-1">
              <div>
                • Processed: <span className="text-bright font-bold">{totalSimulatedRequests.toLocaleString()}</span> req
              </div>
              <div>
                • Succeeded: <span className="text-healthy font-semibold">{successfulSimulatedRequests.toLocaleString()}</span> req
              </div>
              <div>
                • Dropped/Failed: <span className={failedSimulatedRequests > 0 ? 'text-danger font-semibold' : 'text-muted'}>{failedSimulatedRequests.toLocaleString()}</span> req
              </div>
              <div>
                • Model Error Rate: <span className="text-warning">{telemetry.clientErrorRate}%</span>
              </div>
            </div>
          </div>
        </div>

        {/* Final Region Roles & Routing Target */}
        <div className="report-initial-vs-final-grid mb-4">
          <div className="final-state-box">
            <div className="final-state-header font-mono text-xs text-muted mb-2">
              FINAL REGIONAL ROLES & ROUTING TARGET
            </div>
            <div className="final-roles-row">
              <div className="role-col">
                <span className="text-xs text-muted font-mono">Region A (Mumbai):</span>
                <span className={`font-mono text-xs font-bold ${regionA.role === 'ACTIVE' ? 'text-healthy' : 'text-secondary'}`}>
                  {regionA.role} {regionA.acceptsWrites ? '(WRITER)' : '(READ_ONLY)'} {regionA.isFenced ? '[FENCED]' : ''}
                </span>
              </div>

              <div className="role-col">
                <span className="text-xs text-muted font-mono">Region B (Singapore):</span>
                <span className={`font-mono text-xs font-bold ${regionB.role === 'ACTIVE' ? 'text-healthy' : 'text-secondary'}`}>
                  {regionB.role} {regionB.acceptsWrites ? '(WRITER)' : '(READ_ONLY)'}
                </span>
              </div>

              <div className="role-col">
                <span className="text-xs text-muted font-mono">Active Routing Target:</span>
                <span className="font-mono text-xs font-bold text-flow">
                  {dns.activeDnsTarget === 'region-a' ? 'Region A (Mumbai)' : 'Region B (Singapore)'}
                </span>
              </div>

              <div className="role-col">
                <span className="text-xs text-muted font-mono">Active Fencing Epoch:</span>
                <span className="font-mono text-xs font-bold text-bright">
                  Generation #{leaseFence.generationId}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Key Educational Learning Points */}
        <div className="key-learning-points-box mb-4">
          <div className="learning-points-header font-mono text-xs text-muted mb-2">
            KEY ARCHITECTURAL LEARNING POINTS
          </div>
          <ul className="learning-points-list">
            {deriveKeyLearningPoints().map((point, idx) => (
              <li key={idx} className="learning-point-item text-xs text-secondary">
                <CheckCircle size={13} className="text-flow inline mr-1.5 flex-shrink-0 mt-0.5" />
                <span>{point}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Ordered Event Timeline Table Summary */}
        <div className="ordered-timeline-summary">
          <div className="timeline-summary-header mb-2 flex items-center justify-between">
            <span className="font-mono text-xs text-muted">
              ORDERED EVENT AUDIT TRAIL ({auditEvents.length} TOTAL EVENTS)
            </span>
            <span className="text-xs text-muted font-mono">
              Chronological order (Newest first)
            </span>
          </div>

          <div className="timeline-summary-table-wrapper">
            <table className="timeline-summary-table font-mono text-xs">
              <thead>
                <tr>
                  <th>Seq</th>
                  <th>Sim Time</th>
                  <th>System</th>
                  <th>Severity</th>
                  <th>Title</th>
                  <th>Description</th>
                </tr>
              </thead>
              <tbody>
                {auditEvents.slice(0, 8).map((ev, idx) => (
                  <tr key={ev.id}>
                    <td className="text-muted">#{(auditEvents.length - idx).toString().padStart(3, '0')}</td>
                    <td className="text-flow">{ev.timestamp}</td>
                    <td>
                      <span className="badge-tag font-mono text-xs">{ev.subsystem}</span>
                    </td>
                    <td>
                      <span
                        className={`badge-tag font-mono text-xs ${
                          ev.severity === 'critical'
                            ? 'badge-danger'
                            : ev.severity === 'warn'
                            ? 'badge-warning'
                            : ev.severity === 'success'
                            ? 'badge-healthy'
                            : 'badge-info'
                        }`}
                      >
                        {ev.severity.toUpperCase()}
                      </span>
                    </td>
                    <td className="font-semibold text-bright">{ev.title}</td>
                    <td className="text-secondary truncate max-w-xs">{ev.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Saved Run History Box (localStorage) */}
      {savedRunSummary && (
        <div className="report-card mb-5">
          <div className="report-card-header">
            <div className="card-header-icon">
              <Save size={16} className="text-healthy" />
              <h2 className="report-card-title text-sm font-semibold">
                Persisted Previous Run Summary (from Browser Storage)
              </h2>
            </div>
            <div className="flex gap-2">
              <span className="badge-tag font-mono text-xs text-muted">
                Saved {new Date(savedRunSummary.savedAt).toLocaleTimeString()}
              </span>
              <button
                className="btn-console text-xs"
                onClick={handleClearSavedRun}
                title="Clear saved run summary from browser storage"
              >
                <Trash2 size={12} />
                <span>Clear Stored Run</span>
              </button>
            </div>
          </div>
          <div className="saved-run-details font-mono text-xs text-secondary space-y-1">
            <div>• <strong className="text-bright">Scenario:</strong> {savedRunSummary.scenarioTitle}</div>
            <div>• <strong className="text-bright">Outcome:</strong> <span className={savedRunSummary.outcome === 'SUCCEEDED' ? 'text-healthy' : 'text-danger'}>{savedRunSummary.outcome}</span> ({savedRunSummary.outcomeReason})</div>
            <div>• <strong className="text-bright">Final Routing Target:</strong> {savedRunSummary.finalState.activeRoutingTarget} (Fencing Epoch #{savedRunSummary.finalState.fencingGenerationId})</div>
            <div>• <strong className="text-bright">Simulated Requests:</strong> {savedRunSummary.simulatedRequests.total.toLocaleString()} total ({savedRunSummary.simulatedRequests.successful.toLocaleString()} OK, {savedRunSummary.simulatedRequests.failed.toLocaleString()} dropped, Error Rate: {savedRunSummary.simulatedRequests.errorRate}%)</div>
          </div>
        </div>
      )}

      {/* SLA Downtime Calculator & Assessment Quiz */}
      <div className="reports-top-grid mb-5">
        {/* SLA Downtime Calculator */}
        <div className="report-card">
          <div className="report-card-header">
            <div className="card-header-icon">
              <Calculator size={18} className="text-warning" />
              <h2 className="report-card-title">High-Availability SLA Calculator</h2>
            </div>
            <span className="badge-tag font-mono text-xs">Tier Analysis</span>
          </div>

          <p className="text-xs text-secondary mb-3">
            Compare annual downtime budgets for different service level agreements.
            See how a single 5-second failover impacts your monthly availability budget.
          </p>

          <div className="sla-selector-chips">
            {slaTiers.map((tier) => (
              <button
                key={tier.value}
                className={`sla-chip font-mono text-xs ${
                  selectedSla === tier.value ? 'sla-chip-active' : ''
                }`}
                onClick={() => setSelectedSla(tier.value)}
              >
                {tier.tier}
              </button>
            ))}
          </div>

          {(() => {
            const currentTier =
              slaTiers.find((t) => t.value === selectedSla) || slaTiers[3];
            const lastRtoSec = telemetry.lastFailoverDurationMs
              ? telemetry.lastFailoverDurationMs / 1000
              : 5.0;
            return (
              <div className="sla-output-box font-mono text-xs mt-3">
                <div className="sla-row">
                  <span className="text-muted">Target SLA Tier:</span>
                  <span className="text-bright font-semibold">{currentTier.tier}</span>
                </div>
                <div className="sla-row">
                  <span className="text-muted">Allowed Downtime / Year:</span>
                  <span className="text-flow">{currentTier.yearlyDown}</span>
                </div>
                <div className="sla-row">
                  <span className="text-muted">Allowed Downtime / Month:</span>
                  <span className="text-warning">{currentTier.monthlyDown}</span>
                </div>
                <div className="sla-row mt-2 pt-2 border-t border-subtle">
                  <span className="text-muted">Failover Impact ({lastRtoSec}s):</span>
                  <span className="text-healthy font-semibold">
                    Consumed {((lastRtoSec / (52.56 * 60)) * 100).toFixed(2)}% of annual budget
                  </span>
                </div>
              </div>
            );
          })()}
        </div>

        {/* User Preferences Card */}
        <div className="report-card">
          <div className="report-card-header">
            <div className="card-header-icon">
              <Save size={18} className="text-flow" />
              <h2 className="report-card-title">Lab Preferences & Export Config</h2>
            </div>
            <span className="badge-tag font-mono text-xs">Local State</span>
          </div>

          <p className="text-xs text-secondary mb-3">
            Preferences are saved in your local browser storage. Resetting the simulation clears runtime telemetry without wiping user preferences.
          </p>

          <div className="space-y-3 font-mono text-xs">
            <div className="flex items-center justify-between p-2 bg-panel rounded">
              <span className="text-secondary">Auto-persist completed run:</span>
              <button
                className={`btn-console text-xs ${userPrefs.autoSaveRuns ? 'btn-primary' : ''}`}
                onClick={() =>
                  setUserPrefs((prev) => ({ ...prev, autoSaveRuns: !prev.autoSaveRuns }))
                }
              >
                {userPrefs.autoSaveRuns ? 'ENABLED' : 'DISABLED'}
              </button>
            </div>

            <div className="flex items-center justify-between p-2 bg-panel rounded">
              <span className="text-secondary">Default Export Format:</span>
              <span className="text-flow font-bold">JSON (.json)</span>
            </div>

            <div className="flex items-center justify-between p-2 bg-panel rounded">
              <span className="text-secondary">Reset Safety:</span>
              <span className="text-healthy font-semibold">Strict Single-Writer</span>
            </div>
          </div>
        </div>
      </div>

      {/* System Design Quiz Section */}
      <section className="quiz-section mt-5">
        <div className="section-header">
          <div className="section-title-group">
            <div className="quiz-title-row">
              <GraduationCap size={20} className="text-flow" />
              <h2 className="section-title">System Design Knowledge Check (Case Study 23)</h2>
            </div>
            <p className="section-subtitle">
              Verify your understanding of fencing tokens, majority quorums, split-brain, and RTO/RPO trade-offs.
            </p>
          </div>

          {submittedQuiz && (
            <div className="badge-tag badge-healthy font-mono text-sm px-3 py-1">
              Score: {score} / {QUIZ_QUESTIONS.length} Correct ({Math.round((score / QUIZ_QUESTIONS.length) * 100)}%)
            </div>
          )}
        </div>

        <div className="quiz-questions-list">
          {QUIZ_QUESTIONS.map((q, qIndex) => {
            const selectedOpt = userAnswers[q.id];
            const isCorrect = selectedOpt === q.correctIndex;
            return (
              <div key={q.id} className="quiz-question-card">
                <div className="question-header">
                  <span className="question-num font-mono text-xs text-flow">
                    QUESTION 0{qIndex + 1}
                  </span>
                  <span className="badge-tag font-mono text-xs text-muted">
                    {q.systemDesignPrinciple}
                  </span>
                </div>
                <h3 className="question-text">{q.question}</h3>

                <div className="options-stack">
                  {q.options.map((opt, optIdx) => {
                    let optClass = 'option-btn';
                    if (selectedOpt === optIdx) optClass += ' option-selected';
                    if (submittedQuiz) {
                      if (optIdx === q.correctIndex) {
                        optClass += ' option-correct';
                      } else if (selectedOpt === optIdx && !isCorrect) {
                        optClass += ' option-wrong';
                      }
                    }

                    return (
                      <button
                        key={optIdx}
                        className={optClass}
                        onClick={() => handleSelectOption(q.id, optIdx)}
                        disabled={submittedQuiz}
                      >
                        <span className="option-letter font-mono">
                          {String.fromCharCode(65 + optIdx)}
                        </span>
                        <span className="option-label">{opt}</span>
                      </button>
                    );
                  })}
                </div>

                {submittedQuiz && (
                  <div
                    className={`explanation-box text-xs mt-3 ${
                      isCorrect ? 'explanation-correct' : 'explanation-wrong'
                    }`}
                  >
                    <div className="explanation-title font-semibold mb-1">
                      {isCorrect ? '✓ Correct Principle:' : '✗ Concept Review:'}
                    </div>
                    <p className="explanation-body text-secondary">{q.explanation}</p>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        <div className="quiz-footer-actions">
          {!submittedQuiz ? (
            <button
              className="btn-console btn-primary text-sm px-4 py-2"
              onClick={() => setSubmittedQuiz(true)}
              disabled={Object.keys(userAnswers).length === 0}
            >
              <span>Submit Assessment & View Explanations</span>
              <ArrowRight size={14} />
            </button>
          ) : (
            <button
              className="btn-console text-sm px-4 py-2"
              onClick={() => {
                setSubmittedQuiz(false);
                setUserAnswers({});
              }}
            >
              <span>Retake Knowledge Check</span>
            </button>
          )}
        </div>
      </section>
    </div>
  );
};
