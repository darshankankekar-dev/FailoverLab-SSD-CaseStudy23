import React, { useState, useEffect, useCallback } from 'react';
import { Activity, RefreshCw } from 'lucide-react';
import { controllerClient } from '../../api/controllerClient';
import type { ControllerStateDto } from '../../api/controllerClient';
import { FiveRegionsCards } from './FiveRegionsCards';
import { RegionalComparisonTable } from './RegionalComparisonTable';
import { RateLimiterPanel } from './RateLimiterPanel';
import { LoadGeneratorPanel } from './LoadGeneratorPanel';
import { LiveTrafficMonitor } from './LiveTrafficMonitor';
import { SimulationControlsPanel } from './SimulationControlsPanel';
import { FailoverWorkflowProgress } from './FailoverWorkflowProgress';
import './TrafficLab.css';

export const TrafficLabView: React.FC = () => {
  const [controllerState, setControllerState] = useState<ControllerStateDto | null>(null);
  const [measuredLatencies, setMeasuredLatencies] = useState<Record<string, number>>({});
  const [isBackendConnected, setIsBackendConnected] = useState<boolean>(true);
  const [lastRefreshed, setLastRefreshed] = useState<Date>(() => new Date());

  const refreshState = useCallback(async () => {
    try {
      const state = await controllerClient.fetchState();
      if (state) {
        setControllerState(state);
        setIsBackendConnected(true);
        setLastRefreshed(new Date());
      } else {
        setIsBackendConnected(false);
      }
    } catch {
      setIsBackendConnected(false);
    }

    // Attempt to retrieve real measured latencies from Gateway
    try {
      const routeRes = await fetch('/api/v1/route');
      if (routeRes.ok) {
        const routeData = await routeRes.json();
        if (routeData.regional_measured_latency) {
          setMeasuredLatencies(routeData.regional_measured_latency);
        }
      }
    } catch {
      // Gateway probe pending or offline
    }
  }, []);

  useEffect(() => {
    refreshState();
    const interval = setInterval(refreshState, 2000);
    return () => clearInterval(interval);
  }, [refreshState]);

  const activeRegion = controllerState?.active_region || 'region-a';
  const epoch = controllerState?.fencing_epoch || 101;
  const cState = controllerState?.controller_state || 'HEALTHY';

  return (
    <div className="traffic-lab-layout">
      {/* Top Header Cockpit Bar */}
      <div className="traffic-lab-header">
        <div className="traffic-lab-title">
          <h1>
            <Activity className="text-healthy" size={24} />
            <span>Traffic Laboratory & Five-Region Operations Cockpit</span>
          </h1>
          <p>
            Real-time ingress traffic management, Token/Leaky bucket controls, multi-region replication tracking, and safe failover drills.
          </p>
        </div>

        <div className="traffic-lab-header-badges">
          <div className="flex items-center gap-1.5 font-mono text-xs">
            <span className="text-muted">Primary Writer:</span>
            <span className="badge-tag-sm badge-healthy font-bold">{activeRegion}</span>
          </div>

          <div className="flex items-center gap-1.5 font-mono text-xs">
            <span className="text-muted">Fencing Epoch:</span>
            <span className="badge-tag-sm badge-warning font-bold">#{epoch}</span>
          </div>

          <div className="flex items-center gap-1.5 font-mono text-xs">
            <span className="text-muted">Controller State:</span>
            <span
              className={`badge-tag-sm ${
                cState === 'HEALTHY'
                  ? 'badge-healthy'
                  : cState === 'SECONDARY_ACTIVE'
                  ? 'badge-info'
                  : 'badge-danger'
              }`}
            >
              {cState}
            </span>
          </div>

          <div className="flex items-center gap-1.5 font-mono text-xs">
            <span className="text-muted">Backend:</span>
            {isBackendConnected ? (
              <span className="badge-tag-sm badge-healthy flex items-center gap-1">
                <span className="pulse-live-indicator" /> Connected
              </span>
            ) : (
              <span className="badge-tag-sm badge-danger">Disconnected</span>
            )}
          </div>

          <button
            className="btn-console btn-ghost btn-sm text-xs"
            onClick={refreshState}
            title={`Last updated: ${lastRefreshed.toLocaleTimeString()}`}
          >
            <RefreshCw size={12} />
            <span className="font-mono text-[10px] text-muted">{lastRefreshed.toLocaleTimeString()}</span>
          </button>
        </div>
      </div>

      {/* Section 1: Five Regional Topology Cards */}
      <FiveRegionsCards controllerState={controllerState} measuredLatencies={measuredLatencies} />

      {/* Section 2: Regional Comparison Table */}
      <RegionalComparisonTable controllerState={controllerState} measuredLatencies={measuredLatencies} />

      {/* Section 3: 2-Column Split: Rate Limiter Controls & Load Generator */}
      <div className="traffic-two-col">
        <RateLimiterPanel onConfigChanged={refreshState} />
        <LoadGeneratorPanel />
      </div>

      {/* Section 4: Live Traffic Monitor (SSE Streaming) */}
      <LiveTrafficMonitor />

      {/* Section 5: 2-Column Split: Failover Safety Workflow Stepper & Simulation Controls */}
      <div className="traffic-two-col">
        <FailoverWorkflowProgress
          controllerState={controllerState}
          onWorkflowComplete={refreshState}
        />
        <SimulationControlsPanel
          controllerState={controllerState}
          onStateChanged={refreshState}
        />
      </div>
    </div>
  );
};
