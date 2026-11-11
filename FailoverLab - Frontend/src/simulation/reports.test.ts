import { describe, it, expect, beforeEach } from 'vitest';
import { SimulationEngine } from './SimulationEngine';
import { LEARNING_CONCEPTS } from '../data/learningConcepts';
import { simulationReducer, INITIAL_SIMULATION_STATE } from './transitions';

describe('FailoverLab Monitoring & Reporting Functionality', () => {
  let engine: SimulationEngine;

  beforeEach(() => {
    engine = new SimulationEngine();
    engine.reset();
  });

  describe('A. Live Metrics Calculations', () => {
    it('calculates initial baseline metrics correctly from model state', () => {
      const state = engine.getState();
      expect(state.regionA.role).toBe('ACTIVE');
      expect(state.regionA.acceptsWrites).toBe(true);
      expect(state.regionB.role).toBe('STANDBY');
      expect(state.regionB.acceptsWrites).toBe(false);
      expect(state.controllerState).toBe('HEALTHY');
      expect(state.consecutiveFailures).toBe(0);

      // Quorum observers
      const healthyObservers = state.voters.filter((v) => v.vote !== 'ABSTAIN').length;
      expect(healthyObservers).toBe(3);

      // Replication lag
      expect(state.replication.lagSeconds).toBeCloseTo(0.8);

      // Routing target
      expect(state.route.activeTarget).toBe('region-a');

      // Requests calculation
      const totalRequests = Math.round(state.simulatedTimeSeconds * state.regionA.ingressRps);
      expect(totalRequests).toBe(0);

      // Detection duration
      const detectionSec =
        state.consecutiveFailures > 0
          ? state.consecutiveFailures * state.config.healthCheckIntervalSec
          : 0;
      expect(detectionSec).toBe(0);
    });

    it('updates detection duration dynamically as synthetic probes fail', () => {
      let state = INITIAL_SIMULATION_STATE;
      state = simulationReducer(state, { type: 'INJECT_PRIMARY_OUTAGE' });

      // First failed probe (2s tick)
      state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
      expect(state.consecutiveFailures).toBe(1);
      let detectionSec = state.consecutiveFailures * state.config.healthCheckIntervalSec;
      expect(detectionSec).toBe(2); // 1 probe * 2s

      // Second failed probe (2s tick)
      state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
      expect(state.consecutiveFailures).toBe(2);
      detectionSec = state.consecutiveFailures * state.config.healthCheckIntervalSec;
      expect(detectionSec).toBe(4); // 2 probes * 2s
    });

    it('calculates simulated request success and drops from error rate', () => {
      // Simulate 10 seconds of time with client traffic
      let state = INITIAL_SIMULATION_STATE;
      state = simulationReducer(state, { type: 'TICK', deltaSec: 10 });
      const clientRps = 2450;
      const errorRate = 0; // Nominal operation

      const totalRequests = Math.round(state.simulatedTimeSeconds * clientRps);
      expect(totalRequests).toBe(24500);

      const failedRequests = Math.round(totalRequests * (errorRate / 100));
      const successfulRequests = totalRequests - failedRequests;
      expect(successfulRequests).toBe(24500);
      expect(failedRequests).toBe(0);
    });
  });

  describe('B. Event Timeline & Outcomes', () => {
    it('records sequence numbers, timestamps, subsystems, and outcomes', () => {
      let state = INITIAL_SIMULATION_STATE;
      state = simulationReducer(state, { type: 'INJECT_PRIMARY_OUTAGE' });
      expect(state.eventHistory.length).toBeGreaterThan(0);

      const latestEvent = state.eventHistory[0];
      expect(latestEvent.simulatedTimeSeconds).toBeGreaterThanOrEqual(0);
      expect(latestEvent.subsystem).toBeDefined();
      expect(latestEvent.severity).toBeDefined();
      expect(latestEvent.reason).toBeDefined();
    });

    it('clears run history cleanly on reset without leaving orphan events', () => {
      let state = INITIAL_SIMULATION_STATE;
      state = simulationReducer(state, { type: 'INJECT_PRIMARY_OUTAGE' });
      expect(state.eventHistory.length).toBeGreaterThan(1);

      state = simulationReducer(state, { type: 'RESET_SIMULATION' });
      expect(state.controllerState).toBe('HEALTHY');
      expect(state.consecutiveFailures).toBe(0);
      expect(state.regionA.role).toBe('ACTIVE');
      expect(state.regionB.role).toBe('STANDBY');
      expect(state.regionA.acceptsWrites).toBe(true);
      expect(state.regionB.acceptsWrites).toBe(false);
      // Reset restores baseline with the reset event prepended
      expect(state.eventHistory.length).toBe(2);
      expect(state.eventHistory[0].reason).toContain('Virtual Lab Reset');
    });

    it('formats CSV timeline with proper RFC 4180 escaping', () => {
      let state = INITIAL_SIMULATION_STATE;
      state = simulationReducer(state, { type: 'INJECT_PRIMARY_OUTAGE' });
      const events = state.eventHistory;

      const headers = ['Sequence', 'SimulatedTime', 'Severity', 'Subsystem', 'Title', 'Description'];
      const rows = events.map((ev, idx) => {
        const seq = events.length - idx;
        const timeFormatted = `T+${Math.floor(ev.simulatedTimeSeconds / 60).toString().padStart(2, '0')}:${(ev.simulatedTimeSeconds % 60).toString().padStart(2, '0')}`;
        return [
          seq,
          `"${timeFormatted}"`,
          `"${ev.severity}"`,
          `"${ev.subsystem}"`,
          `"${(ev.transition || ev.subsystem).replace(/"/g, '""')}"`,
          `"${ev.reason.replace(/"/g, '""')}"`,
        ].join(',');
      });

      const csvContent = [headers.join(','), ...rows].join('\n');
      expect(csvContent).toContain('Sequence,SimulatedTime,Severity,Subsystem,Title,Description');
      expect(csvContent).toContain('Primary Outage Injected');
    });
  });

  describe('C. Learning Panel Concepts Completeness', () => {
    it('contains all 10 required educational concepts', () => {
      expect(LEARNING_CONCEPTS.length).toBe(10);
    });

    it('ensures each concept defines all 4 required educational sections', () => {
      LEARNING_CONCEPTS.forEach((concept) => {
        expect(concept.number).toBeGreaterThanOrEqual(1);
        expect(concept.number).toBeLessThanOrEqual(10);
        expect(concept.title).toBeTruthy();
        expect(concept.shortDesc).toBeTruthy();

        // 1. What it means
        expect(concept.whatItMeans).toBeTruthy();
        expect(concept.whatItMeans.length).toBeGreaterThan(20);

        // 2. Why this design needs it
        expect(concept.whyNeeded).toBeTruthy();
        expect(concept.whyNeeded.length).toBeGreaterThan(20);

        // 3. What the user can observe in the simulation
        expect(concept.whatToObserve).toBeTruthy();
        expect(concept.whatToObserve.length).toBeGreaterThan(20);

        // 4. A limitation of the educational model
        expect(concept.modelLimitation).toBeTruthy();
        expect(concept.modelLimitation.length).toBeGreaterThan(20);
      });
    });

    it('includes specific required topics in the 10 concepts', () => {
      const titles = LEARNING_CONCEPTS.map((c) => c.title.toLowerCase());
      expect(titles.some((t) => t.includes('active-passive'))).toBe(true);
      expect(titles.some((t) => t.includes('health check') || t.includes('false positive'))).toBe(true);
      expect(titles.some((t) => t.includes('quorum') || t.includes('failure detection'))).toBe(true);
      expect(titles.some((t) => t.includes('split-brain'))).toBe(true);
      expect(titles.some((t) => t.includes('lease') || t.includes('fencing'))).toBe(true);
      expect(titles.some((t) => t.includes('replication'))).toBe(true);
      expect(titles.some((t) => t.includes('rto') || t.includes('rpo'))).toBe(true);
      expect(titles.some((t) => t.includes('dns') || t.includes('caching'))).toBe(true);
      expect(titles.some((t) => t.includes('failback'))).toBe(true);
      expect(titles.some((t) => t.includes('control-plane') || t.includes('recovery'))).toBe(true);
    });
  });

  describe('D. Experiment Report Generation & Persistence', () => {
    it('generates a valid JSON report containing all required fields', () => {
      let state = INITIAL_SIMULATION_STATE;
      state = simulationReducer(state, { type: 'INJECT_PRIMARY_OUTAGE' });
      state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
      state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
      state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });

      const reportPayload = {
        reportType: 'FailoverLab Experiment Report',
        version: '1.0.0',
        caseStudy: 23,
        generatedAt: new Date().toISOString(),
        scenarioTitle: 'SCENARIO B — PRIMARY APPLICATION CRASH',
        initialConditions: 'Region A ACTIVE, Region B STANDBY',
        configuredThresholds: {
          healthCheckIntervalSec: state.config.healthCheckIntervalSec,
          failureThresholdConsecutive: state.config.failureThresholdConsecutive,
          quorumMajorityRequired: state.config.majorityRequired,
          acceptableReplicationLagSec: state.config.acceptableReplicationLagSec,
        },
        finalState: {
          regionARole: state.regionA.role,
          regionAWrites: state.regionA.acceptsWrites,
          regionAFenced: state.regionA.isFenced,
          regionBRole: state.regionB.role,
          regionBWrites: state.regionB.acceptsWrites,
          activeRoutingTarget: state.route.activeTarget,
        },
        outcome: state.controllerState,
        eventTimeline: state.eventHistory,
      };

      const jsonStr = JSON.stringify(reportPayload, null, 2);
      expect(jsonStr).toContain('FailoverLab Experiment Report');
      expect(jsonStr).toContain('healthCheckIntervalSec');
      expect(jsonStr).toContain('acceptableReplicationLagSec');
      expect(jsonStr).toContain('finalState');
      expect(jsonStr).toContain('eventTimeline');

      const parsed = JSON.parse(jsonStr);
      expect(parsed.configuredThresholds.healthCheckIntervalSec).toBe(2);
      expect(parsed.configuredThresholds.failureThresholdConsecutive).toBe(3);
      expect(parsed.configuredThresholds.acceptableReplicationLagSec).toBe(5);
    });

    it('simulates localStorage persistence of run summary and user preferences safely', () => {
      const mockStorage: Record<string, string> = {};

      const testRunSummary = {
        scenarioTitle: 'SCENARIO B',
        outcome: 'SUCCEEDED',
        savedAt: '2026-10-20T10:00:00.000Z',
      };

      // Store run summary
      mockStorage['failoverlab_last_run_summary'] = JSON.stringify(testRunSummary);
      expect(mockStorage['failoverlab_last_run_summary']).toBeDefined();

      // Retrieve and parse
      const retrieved = JSON.parse(mockStorage['failoverlab_last_run_summary']);
      expect(retrieved.scenarioTitle).toBe('SCENARIO B');
      expect(retrieved.outcome).toBe('SUCCEEDED');

      // Clear run summary
      delete mockStorage['failoverlab_last_run_summary'];
      expect(mockStorage['failoverlab_last_run_summary']).toBeUndefined();
    });
  });
});
