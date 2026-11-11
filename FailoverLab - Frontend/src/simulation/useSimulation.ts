// FailoverLab: useSimulation Hook
// Exposes the pure simulation state, clock status, and projection models for the UI

import { useEffect, useState } from 'react';
import { simulationEngine } from './SimulationEngine';
import { controllerClient } from '../api/controllerClient';
import type {
  SimulationState,
  AuditRecord,
} from './types';

export interface UseSimulationReturn extends SimulationState {
  engine: typeof simulationEngine;
  isRunning: boolean;
  tickSpeed: number;
  isBackendConnected: boolean;

  // UI Projections
  primaryDb: {
    id: string;
    region: 'region-a' | 'region-b';
    name: string;
    role: 'PRIMARY' | 'STANDBY';
    accessMode: 'READ_WRITE' | 'READ_ONLY' | 'FENCED';
    status: 'healthy' | 'degraded' | 'failed' | 'fenced';
    generationId: number;
    replicationLagMs: number;
    iops: number;
    storageGb: number;
  };

  standbyDb: {
    id: string;
    region: 'region-a' | 'region-b';
    name: string;
    role: 'PRIMARY' | 'STANDBY';
    accessMode: 'READ_WRITE' | 'READ_ONLY' | 'FENCED';
    status: 'healthy' | 'degraded' | 'failed' | 'fenced';
    generationId: number;
    replicationLagMs: number;
    iops: number;
    storageGb: number;
  };

  dns: {
    primaryTarget: 'region-a' | 'region-b';
    ttlSeconds: number;
    activeDnsTarget: 'region-a' | 'region-b';
    propagationProgress: number;
    resolutionStatus: 'NOMINAL' | 'PROPAGATING' | 'FAILED';
  };

  leaseFence: {
    currentHolder: 'region-a' | 'region-b' | null;
    generationId: number;
    leaseTtlMs: number;
    leaseRemainingMs: number;
    fenceStatus: 'ACTIVE_LOCK' | 'HARD_FENCED' | 'EXPIRED';
  };

  quorum: {
    nodes: Array<{
      id: string;
      name: string;
      location: string;
      alive: boolean;
      vote: 'region-a' | 'region-b';
      latencyMs: number;
    }>;
    requiredVotes: number;
    currentLeaderVote: 'region-a' | 'region-b';
    consensusReached: boolean;
  };

  telemetry: {
    uptimeSeconds: number;
    totalClientRps: number;
    overallSuccessRate: number;
    clientErrorRate: number;
    p95LatencyMs: number;
    totalFailoversCount: number;
    lastFailoverDurationMs: number | null;
    estimatedRpoLossTx: number;
  };

  auditEvents: Array<{
    id: string;
    timestamp: string;
    simTime: number;
    severity: AuditRecord['severity'];
    subsystem: AuditRecord['subsystem'];
    title: string;
    description: string;
  }>;
}

export function useSimulation(): UseSimulationReturn {
  const [state, setState] = useState<SimulationState>(() =>
    simulationEngine.getState()
  );
  const [isRunning, setIsRunning] = useState<boolean>(() =>
    simulationEngine.getIsRunning()
  );
  const [tickSpeed, setTickSpeed] = useState<number>(() =>
    simulationEngine.getTickSpeed()
  );
  const [isBackendConnected, setIsBackendConnected] = useState<boolean>(() =>
    simulationEngine.getIsBackendConnected()
  );

  useEffect(() => {
    const unsubscribe = simulationEngine.subscribe((nextState) => {
      setState(nextState);
      setIsRunning(simulationEngine.getIsRunning());
      setTickSpeed(simulationEngine.getTickSpeed());
      setIsBackendConnected(simulationEngine.getIsBackendConnected());
    });
    return () => {
      unsubscribe();
    };
  }, []);

  useEffect(() => {
    let isMounted = true;
    let pollInterval: ReturnType<typeof setInterval> | null = null;

    const checkAndSync = async () => {
      try {
        const { controller } = await controllerClient.checkHealth();
        if (!isMounted) return;
        if (controller) {
          simulationEngine.setBackendConnected(true);
          setIsBackendConnected(true);
          const backendState = await controllerClient.fetchState();
          if (backendState && isMounted) {
            simulationEngine.applyBackendState(backendState);
          }
        } else {
          simulationEngine.setBackendConnected(false);
          setIsBackendConnected(false);
        }
      } catch {
        if (isMounted) {
          simulationEngine.setBackendConnected(false);
          setIsBackendConnected(false);
        }
      }
    };

    checkAndSync();
    pollInterval = setInterval(checkAndSync, 2000);

    return () => {
      isMounted = false;
      if (pollInterval) clearInterval(pollInterval);
    };
  }, []);

  // Compute UI projections
  const isRegionAActive = state.regionA.role === 'ACTIVE';
  const isRegionBActive = state.regionB.role === 'ACTIVE';

  const primaryDb = {
    id: 'db-region-a',
    region: 'region-a' as const,
    name: 'Primary Database (Aurora / Postgres)',
    role: (isRegionAActive ? 'PRIMARY' : 'STANDBY') as 'PRIMARY' | 'STANDBY',
    accessMode: (state.regionA.acceptsWrites
      ? 'READ_WRITE'
      : state.regionA.isFenced
      ? 'FENCED'
      : 'READ_ONLY') as 'READ_WRITE' | 'READ_ONLY' | 'FENCED',
    status: (state.regionA.health === 'HEALTHY'
      ? state.regionA.isFenced
        ? 'fenced'
        : 'healthy'
      : 'failed') as 'healthy' | 'degraded' | 'failed' | 'fenced',
    generationId: state.regionA.fencingEpoch,
    replicationLagMs: 0,
    iops: state.regionA.acceptsWrites ? state.regionA.iops : 0,
    storageGb: 850,
  };

  const standbyDb = {
    id: 'db-region-b',
    region: 'region-b' as const,
    name: isRegionBActive
      ? 'Promoted Primary Database'
      : 'Standby Read Replica',
    role: (isRegionBActive ? 'PRIMARY' : 'STANDBY') as 'PRIMARY' | 'STANDBY',
    accessMode: (state.regionB.acceptsWrites
      ? 'READ_WRITE'
      : 'READ_ONLY') as 'READ_WRITE' | 'READ_ONLY' | 'FENCED',
    status: (state.regionB.health === 'HEALTHY'
      ? 'healthy'
      : 'failed') as 'healthy' | 'degraded' | 'failed' | 'fenced',
    generationId: state.regionB.fencingEpoch,
    replicationLagMs: Math.round(state.replication.lagSeconds * 1000),
    iops: state.regionB.acceptsWrites ? 4800 : 120,
    storageGb: 850,
  };

  const dns = {
    primaryTarget: state.route.activeTarget,
    ttlSeconds: state.route.dnsTtlSeconds,
    activeDnsTarget: state.route.activeTarget,
    propagationProgress: state.route.propagationPercent,
    resolutionStatus: (state.route.verificationStatus === 'FAILED'
      ? 'FAILED'
      : state.route.propagationPercent < 100
      ? 'PROPAGATING'
      : 'NOMINAL') as 'NOMINAL' | 'PROPAGATING' | 'FAILED',
  };

  const leaseFence = {
    currentHolder: state.regionA.acceptsWrites
      ? ('region-a' as const)
      : state.regionB.acceptsWrites
      ? ('region-b' as const)
      : null,
    generationId: Math.max(
      state.regionA.fencingEpoch,
      state.regionB.fencingEpoch
    ),
    leaseTtlMs: 5000,
    leaseRemainingMs: state.regionA.acceptsWrites ? 5000 : 0,
    fenceStatus: (state.regionA.isFenced
      ? 'HARD_FENCED'
      : 'ACTIVE_LOCK') as 'ACTIVE_LOCK' | 'HARD_FENCED' | 'EXPIRED',
  };

  const quorum = {
    nodes: state.voters.map((v) => ({
      id: v.id,
      name: v.name,
      location: v.location,
      alive: true,
      vote: (v.vote === 'PRIMARY_OUTAGE'
        ? 'region-b'
        : 'region-a') as 'region-a' | 'region-b',
      latencyMs: v.latencyMs,
    })),
    requiredVotes: state.config.majorityRequired,
    currentLeaderVote: (state.voters.filter(
      (v) => v.vote === 'PRIMARY_OUTAGE'
    ).length >= state.config.majorityRequired
      ? 'region-b'
      : 'region-a') as 'region-a' | 'region-b',
    consensusReached:
      state.voters.filter((v) => v.vote === 'PRIMARY_OUTAGE').length >=
        state.config.majorityRequired ||
      state.voters.filter((v) => v.vote === 'PRIMARY_HEALTHY').length >=
        state.config.majorityRequired,
  };

  // Telemetry calculation
  const isHealthyState =
    state.controllerState === 'HEALTHY' ||
    state.controllerState === 'SECONDARY_ACTIVE';
  const isFailingState =
    state.controllerState === 'PRIMARY_SUSPECTED' ||
    state.controllerState === 'QUORUM_CHECK' ||
    state.controllerState === 'FENCING_PRIMARY' ||
    state.controllerState === 'PROMOTING_STANDBY';

  const overallSuccessRate = isHealthyState
    ? 99.98
    : isFailingState
    ? 14.5
    : state.controllerState === 'ROUTE_UPDATING'
    ? 20 + state.route.propagationPercent * 0.75
    : 95.0;

  const clientErrorRate = Math.max(0, 100 - overallSuccessRate);
  const p95LatencyMs = isHealthyState
    ? state.regionB.role === 'ACTIVE'
      ? 32
      : 18
    : isFailingState
    ? 850
    : 120;

  const telemetry = {
    uptimeSeconds: state.simulatedTimeSeconds,
    totalClientRps: 2450,
    overallSuccessRate: parseFloat(overallSuccessRate.toFixed(2)),
    clientErrorRate: parseFloat(clientErrorRate.toFixed(2)),
    p95LatencyMs,
    totalFailoversCount: state.regionB.fencingEpoch > 101 ? 1 : 0,
    lastFailoverDurationMs: state.regionB.role === 'ACTIVE' ? 6200 : null,
    estimatedRpoLossTx:
      state.replication.status === 'DEGRADED' ||
      state.replication.lagSeconds > state.config.acceptableReplicationLagSec
        ? Math.round(state.replication.lagSeconds * 2450)
        : 0,
  };

  const auditEvents = state.eventHistory.map((ev) => {
    const mins = Math.floor(ev.simulatedTimeSeconds / 60);
    const secs = ev.simulatedTimeSeconds % 60;
    const timeFormatted = `T+${mins.toString().padStart(2, '0')}:${secs
      .toString()
      .padStart(2, '0')}`;
    return {
      id: ev.id,
      timestamp: timeFormatted,
      simTime: ev.simulatedTimeSeconds,
      severity: ev.severity,
      subsystem: ev.subsystem,
      title: ev.transition ? `[${ev.transition}]` : ev.reason.slice(0, 48),
      description: ev.details ? `${ev.reason} — ${ev.details}` : ev.reason,
    };
  });

  return {
    ...state,
    engine: simulationEngine,
    isRunning,
    tickSpeed,
    primaryDb,
    standbyDb,
    dns,
    leaseFence,
    quorum,
    telemetry,
    auditEvents,
    isBackendConnected,
  };
}
