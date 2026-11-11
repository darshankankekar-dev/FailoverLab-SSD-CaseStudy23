import React from 'react';
import { MetricsDashboard } from './MetricsDashboard';
import { ControlsPanel } from './ControlsPanel';
import { ArchitectureSvg } from './ArchitectureSvg';
import { InspectorPanel } from './InspectorPanel';
import { TimelinePanel } from './TimelinePanel';

export const LiveSimulatorView: React.FC = () => {
  return (
    <div className="live-simulator-layout">
      {/* Top compact metrics dashboard */}
      <div className="simulator-metrics-header-row mb-3">
        <MetricsDashboard />
      </div>

      {/* Top 3-column workspace */}
      <div className="simulator-main-grid">
        {/* Left column: Controls & Scenarios */}
        <div className="sim-grid-col sim-col-left">
          <ControlsPanel />
        </div>

        {/* Center column: Large Architecture SVG */}
        <div className="sim-grid-col sim-col-center">
          <ArchitectureSvg />
        </div>

        {/* Right column: Inspector & Live Telemetry */}
        <div className="sim-grid-col sim-col-right">
          <InspectorPanel />
        </div>
      </div>

      {/* Bottom row: Timeline & Audit Log */}
      <div className="simulator-bottom-row">
        <TimelinePanel />
      </div>
    </div>
  );
};
