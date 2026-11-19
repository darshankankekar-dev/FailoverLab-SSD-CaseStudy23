import React, { useState, useEffect, useCallback, useRef } from 'react';
import { controllerClient } from '../../api/controllerClient';
import type {
  ControllerStateDto,
  TrafficSummaryDto,
  RegionalTrafficItemDto,
  AuditEventDto,
} from '../../api/controllerClient';
import { ControllerHeader } from './ControllerHeader';
import { ControllerNavTabs } from './ControllerNavTabs';
import type { ControllerTabId } from './ControllerNavTabs';
import { ControllerOverviewTab } from './ControllerOverviewTab';
import { ControllerNetworkTrafficTab } from './ControllerNetworkTrafficTab';
import { ControllerRegionalOperationsTab } from './ControllerRegionalOperationsTab';
import { ControllerReplicationTab } from './ControllerReplicationTab';
import { ControllerFailoverHistoryTab } from './ControllerFailoverHistoryTab';
import { ControllerLiveInspectorTab } from './ControllerLiveInspectorTab';
import { AlertTriangle } from 'lucide-react';
import './ControllerDashboard.css';

interface ControllerDashboardViewProps {
  onNavigateToConsole: () => void;
  onNavigateToShop: () => void;
}

export const ControllerDashboardView: React.FC<ControllerDashboardViewProps> = ({
  onNavigateToConsole,
  onNavigateToShop,
}) => {
  const [activeTab, setActiveTab] = useState<ControllerTabId>('overview');
  const [controllerState, setControllerState] = useState<ControllerStateDto | null>(null);
  const [trafficSummary, setTrafficSummary] = useState<TrafficSummaryDto | null>(null);
  const [regionalTraffic, setRegionalTraffic] = useState<RegionalTrafficItemDto[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEventDto[]>([]);
  const [isBackendConnected, setIsBackendConnected] = useState<boolean>(true);
  const [isPaused, setIsPaused] = useState<boolean>(false);
  const [lastFetchTime, setLastFetchTime] = useState<Date>(() => new Date());

  const isPausedRef = useRef(isPaused);
  useEffect(() => {
    isPausedRef.current = isPaused;
  }, [isPaused]);

  // Primary data refresh handler
  const refreshAllData = useCallback(async () => {
    try {
      const [stateRes, summaryRes, regionalRes, eventsRes] = await Promise.all([
        controllerClient.fetchState(),
        controllerClient.fetchTrafficSummary(),
        controllerClient.fetchRegionalTraffic(),
        controllerClient.fetchAuditEvents(50),
      ]);

      if (stateRes) {
        setControllerState(stateRes);
        setIsBackendConnected(true);
      } else {
        setIsBackendConnected(false);
      }

      if (summaryRes) {
        setTrafficSummary(summaryRes);
      }

      if (regionalRes && regionalRes.regions) {
        setRegionalTraffic(regionalRes.regions);
      }

      if (eventsRes) {
        setAuditEvents(eventsRes);
      }

      setLastFetchTime(new Date());
    } catch {
      setIsBackendConnected(false);
    }
  }, []);

  // Set up 1-second interval polling (with pause support)
  useEffect(() => {
    refreshAllData();

    const interval = setInterval(() => {
      if (!isPausedRef.current) {
        refreshAllData();
      }
    }, 1200);

    return () => clearInterval(interval);
  }, [refreshAllData]);

  // Subscribe to real-time Controller SSE stream for instant metric broadcasts
  useEffect(() => {
    const unsubscribe = controllerClient.subscribeControllerTrafficStream(
      (metricSummary) => {
        if (!isPausedRef.current) {
          setTrafficSummary(metricSummary);
          setLastFetchTime(new Date());
        }
      },
      undefined,
      (initialSummary) => {
        setTrafficSummary(initialSummary);
      }
    );

    return () => unsubscribe();
  }, []);

  const handleTogglePause = () => {
    setIsPaused((prev) => !prev);
  };

  const isStale = trafficSummary?.telemetry_freshness === 'STALE' || (
    Date.now() - lastFetchTime.getTime() > 4000 && !isPaused
  );

  return (
    <div className="controller-app">
      {/* Operations Console Top Header */}
      <ControllerHeader
        controllerState={controllerState}
        trafficSummary={trafficSummary}
        isBackendConnected={isBackendConnected}
        isPaused={isPaused}
        onTogglePause={handleTogglePause}
        onRefreshNow={refreshAllData}
        onNavigateToShop={onNavigateToShop}
        onNavigateToConsole={onNavigateToConsole}
      />

      {/* Stale Telemetry Warning Banner */}
      {isStale && isBackendConnected && (
        <div
          style={{
            background: 'rgba(245, 158, 11, 0.12)',
            borderBottom: '1px solid rgba(245, 158, 11, 0.3)',
            padding: '0.4rem 1.25rem',
            fontSize: '0.75rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            color: '#fbbf24',
          }}
        >
          <AlertTriangle size={14} />
          <span>
            <strong>Telemetry Stale:</strong> No metric batches received from Gateway within the reporting threshold (&gt;3s). Live rates may temporarily show previous values.
          </span>
          <button
            type="button"
            className="btn-console btn-sm"
            style={{ marginLeft: 'auto', padding: '0.15rem 0.5rem', fontSize: '0.7rem' }}
            onClick={refreshAllData}
          >
            Force Probe
          </button>
        </div>
      )}

      {/* Disconnected Backend Warning Banner */}
      {!isBackendConnected && (
        <div
          style={{
            background: 'rgba(239, 68, 68, 0.15)',
            borderBottom: '1px solid rgba(239, 68, 68, 0.35)',
            padding: '0.5rem 1.25rem',
            fontSize: '0.78rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.6rem',
            color: '#f87171',
          }}
        >
          <AlertTriangle size={15} />
          <span>
            <strong>Controller Plane Disconnected:</strong> Could not establish connection to Python FastAPI Controller (Port 8000). Verify service container or local dev server is running.
          </span>
          <button
            type="button"
            className="btn-console btn-sm btn-primary"
            style={{ marginLeft: 'auto' }}
            onClick={refreshAllData}
          >
            Retry Connection
          </button>
        </div>
      )}

      {/* 5-Section Navigation Tabs */}
      <ControllerNavTabs
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        eventCount={auditEvents.length}
        replicationLag={controllerState?.replication?.lag_seconds}
      />

      {/* Main Tab Content Pane */}
      <main className="controller-main">
        {activeTab === 'overview' && (
          <ControllerOverviewTab
            controllerState={controllerState}
            trafficSummary={trafficSummary}
            regionalTraffic={regionalTraffic}
            auditEvents={auditEvents}
            isBackendConnected={isBackendConnected}
            onNavigateTab={(tab) => {
              if (tab === 'traffic') setActiveTab('traffic');
              else if (tab === 'regional') setActiveTab('regional');
              else if (tab === 'replication') setActiveTab('replication');
              else if (tab === 'history') setActiveTab('history');
            }}
          />
        )}

        {activeTab === 'traffic' && (
          <>
            <ControllerNetworkTrafficTab
              summary={trafficSummary}
              isBackendConnected={isBackendConnected}
            />
            {/* Live request inspector integrated into the traffic view as well */}
            <div style={{ marginTop: '1.25rem' }}>
              <ControllerLiveInspectorTab isBackendConnected={isBackendConnected} />
            </div>
          </>
        )}

        {activeTab === 'regional' && (
          <ControllerRegionalOperationsTab
            controllerState={controllerState}
            regionalTraffic={regionalTraffic}
            trafficSummary={trafficSummary}
            onRefresh={refreshAllData}
          />
        )}

        {activeTab === 'replication' && (
          <ControllerReplicationTab
            controllerState={controllerState}
            onRefresh={refreshAllData}
          />
        )}

        {activeTab === 'history' && (
          <ControllerFailoverHistoryTab
            events={auditEvents}
            onRefresh={refreshAllData}
          />
        )}
      </main>
    </div>
  );
};
