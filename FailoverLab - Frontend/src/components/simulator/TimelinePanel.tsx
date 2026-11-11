import React, { useState } from 'react';
import {
  Clock,
  Download,
  AlertTriangle,
  CheckCircle,
  Info,
  Flame,
  ArrowRight,
  Search,
  Trash2,
  FileSpreadsheet,
  RotateCcw,
} from 'lucide-react';
import { useSimulation } from '../../simulation/useSimulation';
import type { EventSeverity } from '../../types/simulation';

export const TimelinePanel: React.FC = () => {
  const { auditEvents } = useSimulation();
  const [selectedSeverity, setSelectedSeverity] = useState<string>('ALL');
  const [selectedSubsystem, setSelectedSubsystem] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [clearedBeforeSimTime, setClearedBeforeSimTime] = useState<number | null>(null);

  // Derive outcome for each event
  const getEventOutcome = (ev: {
    severity: string;
    title: string;
    description: string;
  }): 'SUCCESS' | 'FAILURE' | 'BLOCKED' | 'ACTION' | 'WARNING' | 'INFO' => {
    const text = (ev.title + ' ' + ev.description).toLowerCase();
    if (text.includes('blocked')) return 'BLOCKED';
    if (ev.severity === 'critical' || text.includes('failed') || text.includes('down') || text.includes('crashed')) {
      return 'FAILURE';
    }
    if (ev.severity === 'success' || text.includes('complete') || text.includes('verified') || text.includes('restored')) {
      return 'SUCCESS';
    }
    if (ev.severity === 'action') return 'ACTION';
    if (ev.severity === 'warn') return 'WARNING';
    return 'INFO';
  };

  const visibleEvents = auditEvents.filter((ev) => {
    if (clearedBeforeSimTime !== null && ev.simTime <= clearedBeforeSimTime) {
      return false;
    }
    const matchesSeverity =
      selectedSeverity === 'ALL' || ev.severity === selectedSeverity.toLowerCase();
    const matchesSubsystem =
      selectedSubsystem === 'ALL' || ev.subsystem === selectedSubsystem;
    const matchesSearch =
      searchQuery === '' ||
      ev.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      ev.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
      ev.subsystem.toLowerCase().includes(searchQuery.toLowerCase());

    return matchesSeverity && matchesSubsystem && matchesSearch;
  });

  const getSeverityBadge = (severity: EventSeverity) => {
    switch (severity) {
      case 'critical':
        return (
          <span className="badge-tag badge-danger font-mono text-xs">
            <Flame size={10} />
            <span>CRITICAL</span>
          </span>
        );
      case 'warn':
        return (
          <span className="badge-tag badge-warning font-mono text-xs">
            <AlertTriangle size={10} />
            <span>WARN</span>
          </span>
        );
      case 'success':
        return (
          <span className="badge-tag badge-healthy font-mono text-xs">
            <CheckCircle size={10} />
            <span>SUCCESS</span>
          </span>
        );
      case 'action':
        return (
          <span className="badge-tag badge-info font-mono text-xs">
            <ArrowRight size={10} />
            <span>ACTION</span>
          </span>
        );
      default:
        return (
          <span className="badge-tag font-mono text-xs">
            <Info size={10} />
            <span>INFO</span>
          </span>
        );
    }
  };

  const getOutcomeTag = (outcome: string) => {
    switch (outcome) {
      case 'SUCCESS':
        return <span className="outcome-tag outcome-success font-mono text-xs">SUCCESS</span>;
      case 'FAILURE':
        return <span className="outcome-tag outcome-failure font-mono text-xs">FAILURE</span>;
      case 'BLOCKED':
        return <span className="outcome-tag outcome-blocked font-mono text-xs">BLOCKED</span>;
      case 'WARNING':
        return <span className="outcome-tag outcome-warning font-mono text-xs">WARNING</span>;
      case 'ACTION':
        return <span className="outcome-tag outcome-action font-mono text-xs">ACTION</span>;
      default:
        return <span className="outcome-tag outcome-info font-mono text-xs">INFO</span>;
    }
  };

  const handleExportJson = () => {
    const dataStr =
      'data:text/json;charset=utf-8,' +
      encodeURIComponent(JSON.stringify(auditEvents, null, 2));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute('href', dataStr);
    downloadAnchor.setAttribute('download', `failoverlab-audit-log-${Date.now()}.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  const handleExportCsv = () => {
    const headers = ['Sequence', 'SimulatedTime', 'Severity', 'Subsystem', 'Outcome', 'Title', 'Description'];
    const rows = auditEvents.map((ev, idx) => {
      const outcome = getEventOutcome(ev);
      const seq = auditEvents.length - idx;
      return [
        seq,
        `"${ev.timestamp}"`,
        `"${ev.severity}"`,
        `"${ev.subsystem}"`,
        `"${outcome}"`,
        `"${ev.title.replace(/"/g, '""')}"`,
        `"${ev.description.replace(/"/g, '""')}"`,
      ].join(',');
    });

    const csvContent = 'data:text/csv;charset=utf-8,' + encodeURIComponent([headers.join(','), ...rows].join('\n'));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute('href', csvContent);
    downloadAnchor.setAttribute('download', `failoverlab-timeline-${Date.now()}.csv`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  const handleClearVisibleLog = () => {
    if (auditEvents.length > 0) {
      setClearedBeforeSimTime(auditEvents[0].simTime);
    }
  };

  const handleRestoreVisibleLog = () => {
    setClearedBeforeSimTime(null);
  };

  return (
    <div className="timeline-panel">
      <div className="timeline-header">
        <div className="timeline-title-group">
          <Clock size={16} className="text-flow" />
          <h2 className="timeline-title">Event Timeline & Controller Audit Log</h2>
          <span className="badge-tag font-mono text-xs">
            {visibleEvents.length} of {auditEvents.length} Events
          </span>
          {clearedBeforeSimTime !== null && (
            <span className="badge-tag badge-warning font-mono text-xs">
              Filtered (Log Cleared)
            </span>
          )}
        </div>

        <div className="timeline-filters-group">
          {/* Severity filter chips */}
          <div className="filter-chips-list">
            <span className="text-xs text-muted font-mono mr-1">Severity:</span>
            {['ALL', 'CRITICAL', 'WARN', 'SUCCESS', 'ACTION', 'INFO'].map((sev) => (
              <button
                key={sev}
                className={`filter-chip font-mono text-xs ${
                  selectedSeverity === sev ? 'filter-chip-active' : ''
                }`}
                onClick={() => setSelectedSeverity(sev)}
              >
                {sev}
              </button>
            ))}
          </div>

          {/* Subsystem filter chips */}
          <div className="filter-chips-list">
            <span className="text-xs text-muted font-mono mr-1">System:</span>
            {['ALL', 'CONTROLLER', 'DATABASE', 'FENCING', 'QUORUM', 'DNS', 'SAFETY_GATE'].map((sub) => (
              <button
                key={sub}
                className={`filter-chip font-mono text-xs ${
                  selectedSubsystem === sub ? 'filter-chip-active' : ''
                }`}
                onClick={() => setSelectedSubsystem(sub)}
              >
                {sub}
              </button>
            ))}
          </div>

          {/* Search box */}
          <div className="timeline-search-box">
            <Search size={13} className="search-icon" />
            <input
              type="text"
              placeholder="Search event reasons, epochs..."
              aria-label="Search event log by reason, epoch, or title"
              className="timeline-search-input font-mono text-xs"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>

          {/* Clear / Restore Visible Log */}
          {clearedBeforeSimTime === null ? (
            <button
              className="btn-console text-xs"
              onClick={handleClearVisibleLog}
              title="Clear visible events from current view (Simulation reset restores full history)"
              aria-label="Clear visible events from current view"
            >
              <Trash2 size={12} />
              <span>Clear View</span>
            </button>
          ) : (
            <button
              className="btn-console text-xs btn-primary"
              onClick={handleRestoreVisibleLog}
              title="Restore hidden historical events"
              aria-label="Restore hidden historical events to view"
            >
              <RotateCcw size={12} />
              <span>Restore Log</span>
            </button>
          )}

          {/* Export CSV action */}
          <button
            className="btn-console text-xs btn-export"
            onClick={handleExportCsv}
            title="Download audit timeline as comma-separated values (CSV)"
            aria-label="Export timeline as CSV file"
          >
            <FileSpreadsheet size={13} />
            <span>CSV</span>
          </button>

          {/* Export JSON action */}
          <button
            className="btn-console text-xs btn-export"
            onClick={handleExportJson}
            title="Export complete structured audit timeline as JSON"
            aria-label="Export timeline as JSON file"
          >
            <Download size={13} />
            <span>JSON</span>
          </button>
        </div>
      </div>

      <div className="timeline-events-container">
        {visibleEvents.length === 0 ? (
          <div className="timeline-empty-state font-mono text-xs text-muted">
            No events match current filter or log has been cleared for this view.
          </div>
        ) : (
          <div className="timeline-events-list">
            {visibleEvents.map((ev, idx) => {
              const outcome = getEventOutcome(ev);
              const sequenceNum = `#${(visibleEvents.length - idx).toString().padStart(3, '0')}`;
              return (
                <div key={ev.id} className="timeline-event-row">
                  <span className="event-seq font-mono text-muted text-xs">{sequenceNum}</span>
                  <span className="event-time font-mono">{ev.timestamp}</span>
                  <span className="event-subsystem badge-tag font-mono text-xs">
                    {ev.subsystem}
                  </span>
                  <div className="event-severity-box">{getSeverityBadge(ev.severity)}</div>
                  <div className="event-outcome-box">{getOutcomeTag(outcome)}</div>
                  <div className="event-text-group">
                    <span className="event-title font-semibold">{ev.title}</span>
                    <span className="event-desc text-secondary text-xs">{ev.description}</span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
