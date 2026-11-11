import { describe, it, expect } from 'vitest';
import {
  simulationReducer,
  INITIAL_SIMULATION_STATE,
} from './transitions';
import {
  canInitiateQuorum,
  evaluateQuorumMajority,
  checkStandbyReadiness,
  checkReplicationLagPolicy,
  verifyFencingConfirmed,
  verifyNoDualPrimary,
  verifyRouteOperational,
  checkFailbackReadiness,
} from './safetyGates';

describe('Safety Gates (Pure Decision Functions)', () => {
  it('Gate 1: canInitiateQuorum requires consecutive failure threshold', () => {
    const belowThreshold = canInitiateQuorum(2, 3);
    expect(belowThreshold.passed).toBe(false);
    expect(belowThreshold.reason).toContain('below required threshold');

    const atThreshold = canInitiateQuorum(3, 3);
    expect(atThreshold.passed).toBe(true);
    expect(atThreshold.reason).toContain('Proceeding to independent quorum');
  });

  it('Gate 2: evaluateQuorumMajority requires strict majority (2 of 3)', () => {
    const splitVotes = [
      { id: '1', name: '1', location: 'A', vote: 'PRIMARY_OUTAGE' as const, latencyMs: 5 },
      { id: '2', name: '2', location: 'B', vote: 'PRIMARY_HEALTHY' as const, latencyMs: 10 },
      { id: '3', name: '3', location: 'C', vote: 'ABSTAIN' as const, latencyMs: 20 },
    ];
    const failedResult = evaluateQuorumMajority(splitVotes, 2);
    expect(failedResult.passed).toBe(false);
    expect(failedResult.outageVotesCount).toBe(1);
    expect(failedResult.reason).toContain('Insufficient quorum consensus');

    const majorityVotes = [
      { id: '1', name: '1', location: 'A', vote: 'PRIMARY_HEALTHY' as const, latencyMs: 5 },
      { id: '2', name: '2', location: 'B', vote: 'PRIMARY_OUTAGE' as const, latencyMs: 10 },
      { id: '3', name: '3', location: 'C', vote: 'PRIMARY_OUTAGE' as const, latencyMs: 20 },
    ];
    const passResult = evaluateQuorumMajority(majorityVotes, 2);
    expect(passResult.passed).toBe(true);
    expect(passResult.outageVotesCount).toBe(2);
    expect(passResult.reason).toContain('Quorum consensus achieved');
  });

  it('Gate 3: checkStandbyReadiness prevents promoting unhealthy secondary', () => {
    const unhealthyStandby = {
      ...INITIAL_SIMULATION_STATE.regionB,
      health: 'DOWN' as const,
    };
    const result = checkStandbyReadiness(unhealthyStandby);
    expect(result.passed).toBe(false);
    expect(result.reason).toContain('Standby readiness check failed');

    const healthyStandby = { ...INITIAL_SIMULATION_STATE.regionB };
    expect(checkStandbyReadiness(healthyStandby).passed).toBe(true);
  });

  it('Gate 4: checkReplicationLagPolicy blocks promotion on excessive WAL lag', () => {
    const excessiveLag = {
      ...INITIAL_SIMULATION_STATE.replication,
      lagSeconds: 8.4,
    };
    const result = checkReplicationLagPolicy(excessiveLag, 5.0);
    expect(result.passed).toBe(false);
    expect(result.reason).toContain('Replication lag gate failed');
    expect(result.reason).toContain('RPO data loss');

    const nominalLag = {
      ...INITIAL_SIMULATION_STATE.replication,
      lagSeconds: 1.2,
    };
    expect(checkReplicationLagPolicy(nominalLag, 5.0).passed).toBe(true);
  });

  it('Gate 5: verifyFencingConfirmed enforces storage fence before promotion', () => {
    const unfencedPrimary = {
      ...INITIAL_SIMULATION_STATE.regionA,
      acceptsWrites: true,
      isFenced: false,
    };
    const failResult = verifyFencingConfirmed(unfencedPrimary);
    expect(failResult.passed).toBe(false);
    expect(failResult.reason).toContain('SPLIT-BRAIN');

    const fencedPrimary = {
      ...INITIAL_SIMULATION_STATE.regionA,
      acceptsWrites: false,
      isFenced: true,
    };
    expect(verifyFencingConfirmed(fencedPrimary).passed).toBe(true);
  });

  it('Gate 6: verifyNoDualPrimary protects dual-master invariant', () => {
    const state = INITIAL_SIMULATION_STATE;
    const dualActiveA = { ...state.regionA, acceptsWrites: true };
    const dualActiveB = { ...state.regionB, acceptsWrites: true };
    const check = verifyNoDualPrimary(dualActiveA, dualActiveB);
    expect(check.passed).toBe(false);
    expect(check.reason).toContain('CRITICAL SAFETY INVARIANT VIOLATED');

    const safeA = { ...state.regionA, acceptsWrites: false };
    const safeB = { ...state.regionB, acceptsWrites: true };
    expect(verifyNoDualPrimary(safeA, safeB).passed).toBe(true);
  });

  it('Gate 7: verifyRouteOperational catches route failures', () => {
    const route = { ...INITIAL_SIMULATION_STATE.route, activeTarget: 'region-b' as const, propagationPercent: 100 };
    const failureResult = verifyRouteOperational(route, 'region-b', true);
    expect(failureResult.passed).toBe(false);
    expect(failureResult.reason).toContain('Route verification failed');

    const successResult = verifyRouteOperational(route, 'region-b', false);
    expect(successResult.passed).toBe(true);
  });

  it('Gate 8: checkFailbackReadiness requires healthy primary and reconciled reverse replication', () => {
    const stateUnhealthy = {
      ...INITIAL_SIMULATION_STATE,
      regionA: { ...INITIAL_SIMULATION_STATE.regionA, health: 'DOWN' as const },
    };
    expect(checkFailbackReadiness(stateUnhealthy).passed).toBe(false);

    const stateLagging = {
      ...INITIAL_SIMULATION_STATE,
      replication: { ...INITIAL_SIMULATION_STATE.replication, status: 'DEGRADED' as const, lagSeconds: 8.0 },
    };
    expect(checkFailbackReadiness(stateLagging).passed).toBe(false);

    const stateReady = {
      ...INITIAL_SIMULATION_STATE,
      replication: { ...INITIAL_SIMULATION_STATE.replication, status: 'SYNCED' as const, lagSeconds: 0.5 },
    };
    expect(checkFailbackReadiness(stateReady).passed).toBe(true);
  });
});

describe('Simulation Engine Transitions & State Machine', () => {
  it('Initializes in documented baseline with Region A active and Region B standby', () => {
    const state = INITIAL_SIMULATION_STATE;
    expect(state.controllerState).toBe('HEALTHY');
    expect(state.regionA.role).toBe('ACTIVE');
    expect(state.regionA.acceptsWrites).toBe(true);
    expect(state.regionB.role).toBe('STANDBY');
    expect(state.regionB.acceptsWrites).toBe(false);
    expect(state.route.activeTarget).toBe('region-a');
  });

  it('False Positive Handling: Primary recovers before threshold, restoring HEALTHY', () => {
    let state = INITIAL_SIMULATION_STATE;

    // Inject outage
    state = simulationReducer(state, { type: 'INJECT_PRIMARY_OUTAGE' });

    // Tick 2 simulated seconds -> Probe 1 fails -> PRIMARY_SUSPECTED
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    expect(state.controllerState).toBe('PRIMARY_SUSPECTED');
    expect(state.consecutiveFailures).toBe(1);

    // Primary recovers before reaching threshold 3
    state = simulationReducer(state, { type: 'RECOVER_PRIMARY' });

    // Next probe tick -> False positive suppressed!
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    expect(state.controllerState).toBe('HEALTHY');
    expect(state.consecutiveFailures).toBe(0);
    expect(state.eventHistory[0].reason).toContain('False Positive Suppressed');
  });

  it('Executes full automatic failover flow through all safety gates to SECONDARY_ACTIVE', () => {
    let state = INITIAL_SIMULATION_STATE;

    // 1. Inject primary outage
    state = simulationReducer(state, { type: 'INJECT_PRIMARY_OUTAGE' });

    // Probe 1 (T+2s) -> PRIMARY_SUSPECTED (1/3)
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    expect(state.controllerState).toBe('PRIMARY_SUSPECTED');
    expect(state.consecutiveFailures).toBe(1);

    // Probe 2 (T+4s) -> PRIMARY_SUSPECTED (2/3)
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    expect(state.controllerState).toBe('PRIMARY_SUSPECTED');
    expect(state.consecutiveFailures).toBe(2);

    // Probe 3 (T+6s) -> Threshold reached (3/3) -> QUORUM_CHECK
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    expect(state.controllerState).toBe('QUORUM_CHECK');
    expect(state.consecutiveFailures).toBe(3);

    // Step to FENCING_PRIMARY (Quorum 2/3 passed, standby ready, lag 0.8s <= 5s)
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    expect(state.controllerState).toBe('FENCING_PRIMARY');

    // Step to PROMOTING_STANDBY (Region A fenced, epoch advanced 101 -> 102)
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    expect(state.controllerState).toBe('PROMOTING_STANDBY');
    expect(state.regionA.acceptsWrites).toBe(false);
    expect(state.regionA.isFenced).toBe(true);
    expect(state.regionB.fencingEpoch).toBe(102);

    // Step to ROUTE_UPDATING (Region B promoted to ACTIVE with write authority)
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    expect(state.controllerState).toBe('ROUTE_UPDATING');
    expect(state.regionB.role).toBe('ACTIVE');
    expect(state.regionB.acceptsWrites).toBe(true);
    expect(state.regionA.acceptsWrites).toBe(false); // Invariant holds!

    // DNS propagation ticks to 100% -> VERIFYING_ROUTE
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    expect(state.controllerState).toBe('VERIFYING_ROUTE');

    // Route verified -> SECONDARY_ACTIVE
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    expect(state.controllerState).toBe('SECONDARY_ACTIVE');
    expect(state.route.verificationStatus).toBe('VERIFIED');
    expect(state.regionB.role).toBe('ACTIVE');
    expect(state.regionB.ingressTrafficPercent).toBe(100);
  });

  it('Blocks failover with human-readable reason when replication lag exceeds policy', () => {
    let state = INITIAL_SIMULATION_STATE;

    // Inject high replication lag (8.4s > 5s limit)
    state = simulationReducer(state, { type: 'INJECT_HIGH_REPLICATION_LAG' });
    state = simulationReducer(state, { type: 'INJECT_PRIMARY_OUTAGE' });

    // Advance 3 failed probes to trigger QUORUM_CHECK
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    expect(state.controllerState).toBe('QUORUM_CHECK');

    // Next step evaluates safety gates -> Replication lag gate triggers FAILOVER_BLOCKED
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    expect(state.controllerState).toBe('FAILOVER_BLOCKED');
    expect(state.blockedReason).toContain('Replication lag gate failed');
    expect(state.blockedReason).toContain('RPO data loss');
    expect(state.blockedAtState).toBe('QUORUM_CHECK');
  });

  it('Blocks failover when standby readiness fails (Region B unhealthy)', () => {
    let state = INITIAL_SIMULATION_STATE;

    // Region B corrupted
    state = simulationReducer(state, { type: 'INJECT_STANDBY_UNREADY' });
    state = simulationReducer(state, { type: 'INJECT_PRIMARY_OUTAGE' });

    // Advance 3 failed probes
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });

    // Step state machine -> Standby readiness gate fails!
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    expect(state.controllerState).toBe('FAILOVER_BLOCKED');
    expect(state.blockedReason).toContain('Standby readiness check failed');
  });

  it('Recovery & Controlled Failback: Never auto-switches back on health alone; requires manual action', () => {
    let state = INITIAL_SIMULATION_STATE;

    // Drive to SECONDARY_ACTIVE
    state = simulationReducer(state, { type: 'INJECT_PRIMARY_OUTAGE' });
    for (let i = 0; i < 15; i++) {
      state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    }
    expect(state.controllerState).toBe('SECONDARY_ACTIVE');

    // Region A recovers
    state = simulationReducer(state, { type: 'RECOVER_PRIMARY' });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });

    // Must transition to PRIMARY_RECOVERING, NOT automatically back to HEALTHY!
    expect(state.controllerState).toBe('PRIMARY_RECOVERING');
    expect(state.regionA.role).toBe('STANDBY'); // Stays standby!
    expect(state.regionA.acceptsWrites).toBe(false);

    // Reverse replication catches up
    state = simulationReducer(state, { type: 'RECONCILE_REPLICATION' });
    expect(state.controllerState).toBe('FAILBACK_PENDING');

    // Deliberate manual failback authorized
    state = simulationReducer(state, { type: 'TRIGGER_MANUAL_FAILBACK' });
    expect(state.controllerState).toBe('FAILBACK_IN_PROGRESS');

    // Failback completes safely
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    expect(state.controllerState).toBe('HEALTHY');
    expect(state.regionA.role).toBe('ACTIVE');
    expect(state.regionA.acceptsWrites).toBe(true);
    expect(state.regionB.role).toBe('STANDBY');
    expect(state.regionB.acceptsWrites).toBe(false);
  });

  it('Blocks failover when route verification fails', () => {
    let state = INITIAL_SIMULATION_STATE;

    // Inject route failure
    state = simulationReducer(state, { type: 'INJECT_ROUTE_FAILURE' });
    state = simulationReducer(state, { type: 'INJECT_PRIMARY_OUTAGE' });

    // 3 probes to trigger QUORUM_CHECK
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    expect(state.controllerState).toBe('QUORUM_CHECK');

    // FENCING_PRIMARY
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    // PROMOTING_STANDBY
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    // ROUTE_UPDATING
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    // ROUTE_UPDATING (propagation +50%)
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    // VERIFYING_ROUTE (propagation 100%)
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    expect(state.controllerState).toBe('VERIFYING_ROUTE');

    // Attempt route verification step -> routeFailureInjected triggers FAILOVER_BLOCKED
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    expect(state.controllerState).toBe('FAILOVER_BLOCKED');
    expect(state.blockedReason).toContain('Route verification failed');
    expect(state.route.verificationStatus).toBe('FAILED');
  });

  it('Monotonically increments fencing epoch on failover and failback (101 -> 102 -> 103)', () => {
    let state = INITIAL_SIMULATION_STATE;
    expect(state.regionA.fencingEpoch).toBe(101);
    expect(state.regionB.fencingEpoch).toBe(101);

    // Failover
    state = simulationReducer(state, { type: 'INJECT_PRIMARY_OUTAGE' });
    for (let i = 0; i < 15; i++) {
      state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    }
    expect(state.controllerState).toBe('SECONDARY_ACTIVE');
    expect(state.regionB.fencingEpoch).toBe(102);

    // Recover & reconcile
    state = simulationReducer(state, { type: 'RECOVER_PRIMARY' });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    state = simulationReducer(state, { type: 'RECONCILE_REPLICATION' });
    state = simulationReducer(state, { type: 'TRIGGER_MANUAL_FAILBACK' });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });

    expect(state.controllerState).toBe('HEALTHY');
    expect(state.regionA.fencingEpoch).toBe(103);
  });

  it('Reset restores baseline and increments resetEpoch to invalidate pending async work', () => {
    let state = INITIAL_SIMULATION_STATE;
    const initialEpoch = state.resetEpoch;

    state = simulationReducer(state, { type: 'INJECT_PRIMARY_OUTAGE' });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    expect(state.controllerState).toBe('PRIMARY_SUSPECTED');

    state = simulationReducer(state, { type: 'RESET_SIMULATION' });
    expect(state.controllerState).toBe('HEALTHY');
    expect(state.consecutiveFailures).toBe(0);
    expect(state.resetEpoch).toBe(initialEpoch + 1);
    expect(state.regionA.role).toBe('ACTIVE');
  });
});
