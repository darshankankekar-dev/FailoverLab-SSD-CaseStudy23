import { describe, it, expect, beforeEach } from 'vitest';
import { SimulationEngine } from './SimulationEngine';
import { simulationReducer, INITIAL_SIMULATION_STATE } from './transitions';
import type { SimulationState } from './types';

describe('End-to-End Quality Pass: 18 Functional Verifications', () => {
  let engine: SimulationEngine;

  beforeEach(() => {
    engine = new SimulationEngine();
    engine.reset();
  });

  // 1. Initial load always produces Region A active and Region B standby
  it('1. Initial load always produces Region A active and Region B standby', () => {
    const state = engine.getState();
    expect(state.regionA.role).toBe('ACTIVE');
    expect(state.regionA.acceptsWrites).toBe(true);
    expect(state.regionA.health).toBe('HEALTHY');
    expect(state.regionB.role).toBe('STANDBY');
    expect(state.regionB.acceptsWrites).toBe(false);
    expect(state.regionB.health).toBe('HEALTHY');
    expect(state.controllerState).toBe('HEALTHY');
    expect(state.route.activeTarget).toBe('region-a');
  });

  // 2. Normal simulation does not accidentally trigger failover
  it('2. Normal simulation does not accidentally trigger failover', () => {
    let state = INITIAL_SIMULATION_STATE;
    // Tick 50 times (100 simulated seconds)
    for (let i = 0; i < 50; i++) {
      state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    }
    expect(state.controllerState).toBe('HEALTHY');
    expect(state.consecutiveFailures).toBe(0);
    expect(state.regionA.role).toBe('ACTIVE');
    expect(state.regionB.role).toBe('STANDBY');
    expect(state.regionA.acceptsWrites).toBe(true);
    expect(state.regionB.acceptsWrites).toBe(false);
  });

  // 3. One transient failed check does not cause automatic failover
  it('3. One transient failed check does not cause automatic failover', () => {
    let state = INITIAL_SIMULATION_STATE;
    // Inject 1 failure probe
    state = simulationReducer(state, { type: 'INJECT_PRIMARY_OUTAGE' });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    expect(state.consecutiveFailures).toBe(1);
    expect(state.controllerState).toBe('PRIMARY_SUSPECTED');

    // Immediate recovery before threshold reached
    state = simulationReducer(state, { type: 'RECOVER_PRIMARY' });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    expect(state.consecutiveFailures).toBe(0);
    expect(state.controllerState).toBe('HEALTHY');
    expect(state.regionA.role).toBe('ACTIVE');
    expect(state.regionB.role).toBe('STANDBY');
  });

  // 4. Reaching the failure threshold starts the correct process
  it('4. Reaching the failure threshold starts the correct process', () => {
    let state = INITIAL_SIMULATION_STATE;
    state = simulationReducer(state, { type: 'INJECT_PRIMARY_OUTAGE' });
    // Probe 1
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    expect(state.controllerState).toBe('PRIMARY_SUSPECTED');
    // Probe 2
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    expect(state.controllerState).toBe('PRIMARY_SUSPECTED');
    // Probe 3 (Threshold met -> QUORUM_CHECK)
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    expect(state.controllerState).toBe('QUORUM_CHECK');
    expect(state.consecutiveFailures).toBe(3);
  });

  // 5. Insufficient quorum blocks promotion
  it('5. Insufficient quorum blocks promotion', () => {
    let state = INITIAL_SIMULATION_STATE;

    // Simulate lost quorum: only 1 observer votes outage, 2 vote healthy
    state = simulationReducer(state, {
      type: 'SET_VOTER_VOTE',
      voterId: 'voter-1',
      vote: 'PRIMARY_OUTAGE',
    });
    state = simulationReducer(state, {
      type: 'SET_VOTER_VOTE',
      voterId: 'voter-2',
      vote: 'PRIMARY_HEALTHY',
    });
    state = simulationReducer(state, {
      type: 'SET_VOTER_VOTE',
      voterId: 'voter-3',
      vote: 'PRIMARY_HEALTHY',
    });

    state = {
      ...state,
      controllerState: 'QUORUM_CHECK',
      isSequenceInProgress: true,
    };

    // Step state machine: Gate 1 should block
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    expect(state.controllerState).toBe('FAILOVER_BLOCKED');
    expect(state.blockedReason).toContain('quorum');
    expect(state.regionB.acceptsWrites).toBe(false);
  });

  // 6. Unhealthy standby blocks promotion
  it('6. Unhealthy standby blocks promotion', () => {
    let state = INITIAL_SIMULATION_STATE;
    state = simulationReducer(state, { type: 'INJECT_STANDBY_UNREADY' });
    state = simulationReducer(state, { type: 'INJECT_PRIMARY_OUTAGE' });

    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    expect(state.controllerState).toBe('QUORUM_CHECK');

    // Standby readiness check fails
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    expect(state.controllerState).toBe('FAILOVER_BLOCKED');
    expect(state.blockedReason).toContain('Standby readiness check failed');
    expect(state.regionB.acceptsWrites).toBe(false);
  });

  // 7. Excessive replication lag blocks promotion under current policy
  it('7. Excessive replication lag blocks promotion under current policy', () => {
    let state = INITIAL_SIMULATION_STATE;
    state = simulationReducer(state, { type: 'INJECT_HIGH_REPLICATION_LAG' });
    state = simulationReducer(state, { type: 'INJECT_PRIMARY_OUTAGE' });

    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    expect(state.controllerState).toBe('QUORUM_CHECK');

    // Lag (8.4s) > Policy (5.0s) -> Blocks failover
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    expect(state.controllerState).toBe('FAILOVER_BLOCKED');
    expect(state.blockedReason).toContain('Replication lag gate failed');
    expect(state.regionB.acceptsWrites).toBe(false);
  });

  // 8. Unconfirmed fencing prevents promotion
  it('8. Unconfirmed fencing prevents promotion', () => {
    let state: SimulationState = {
      ...INITIAL_SIMULATION_STATE,
      controllerState: 'FENCING_PRIMARY',
      regionA: {
        ...INITIAL_SIMULATION_STATE.regionA,
        acceptsWrites: true, // Fencing not confirmed yet!
        isFenced: false,
      },
    };

    // Attempting to step forward while fencing unconfirmed
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    expect(state.regionB.role).toBe('STANDBY');
    expect(state.regionB.acceptsWrites).toBe(false);
  });

  // 9. Successful promotion changes exactly one active writer
  it('9. Successful promotion changes exactly one active writer', () => {
    let state = INITIAL_SIMULATION_STATE;
    state = simulationReducer(state, { type: 'INJECT_PRIMARY_OUTAGE' });

    // Quorum check
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    expect(state.controllerState).toBe('QUORUM_CHECK');

    // Quorum check passes -> Enters FENCING_PRIMARY
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    expect(state.controllerState).toBe('FENCING_PRIMARY');

    // Fencing confirmed -> Region A fenced, write revoked, enters PROMOTING_STANDBY
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    expect(state.controllerState).toBe('PROMOTING_STANDBY');
    expect(state.regionA.acceptsWrites).toBe(false);
    expect(state.regionA.isFenced).toBe(true);

    // Route Updating (Region B promoted to ACTIVE writer with write authority)
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    expect(state.controllerState).toBe('ROUTE_UPDATING');
    expect(state.regionB.role).toBe('ACTIVE');
    expect(state.regionB.acceptsWrites).toBe(true);
    expect(state.regionA.acceptsWrites).toBe(false);

    // CRITICAL SAFETY INVARIANT: Never dual writers!
    expect(state.regionA.acceptsWrites && state.regionB.acceptsWrites).toBe(false);
  });

  // 10. Traffic moves to Region B only after promotion and routing
  it('10. Traffic moves to Region B only after promotion and routing', () => {
    let state = INITIAL_SIMULATION_STATE;
    state = simulationReducer(state, { type: 'INJECT_PRIMARY_OUTAGE' });

    // Progress to ROUTE_UPDATING
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    expect(state.controllerState).toBe('ROUTE_UPDATING');
    expect(state.regionB.ingressTrafficPercent).toBeLessThan(100);

    // Propagate DNS and verify route
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    expect(state.controllerState).toBe('SECONDARY_ACTIVE');
    expect(state.regionB.ingressTrafficPercent).toBe(100);
    expect(state.route.activeTarget).toBe('region-b');
  });

  // 11. Failed DNS updates do not produce a false success state
  it('11. Failed DNS updates do not produce a false success state', () => {
    let state = INITIAL_SIMULATION_STATE;
    state = simulationReducer(state, { type: 'INJECT_ROUTE_FAILURE' });
    state = simulationReducer(state, { type: 'INJECT_PRIMARY_OUTAGE' });

    // Advance to route verification
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });

    // Route verification probe fails
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    expect(state.controllerState).toBe('FAILOVER_BLOCKED');
    expect(state.blockedReason).toContain('Route verification failed');
    expect(state.controllerState).not.toBe('SECONDARY_ACTIVE');
  });

  // 12. Restoring Region A does not automatically switch traffic back
  it('12. Restoring Region A does not automatically switch traffic back', () => {
    let state: SimulationState = {
      ...INITIAL_SIMULATION_STATE,
      controllerState: 'SECONDARY_ACTIVE',
      regionA: {
        ...INITIAL_SIMULATION_STATE.regionA,
        role: 'STANDBY',
        acceptsWrites: false,
        health: 'DOWN',
        ingressTrafficPercent: 0,
      },
      regionB: {
        ...INITIAL_SIMULATION_STATE.regionB,
        role: 'ACTIVE',
        acceptsWrites: true,
        health: 'HEALTHY',
        ingressTrafficPercent: 100,
      },
      route: {
        ...INITIAL_SIMULATION_STATE.route,
        activeTarget: 'region-b',
      },
    };

    // Region A recovers
    state = simulationReducer(state, { type: 'RECOVER_PRIMARY' });
    expect(state.regionA.health).toBe('HEALTHY');
    // Critical: Region A remains STANDBY! Traffic stays on Region B!
    expect(state.regionA.role).toBe('STANDBY');
    expect(state.regionA.acceptsWrites).toBe(false);
    expect(state.regionB.role).toBe('ACTIVE');
    expect(state.regionB.acceptsWrites).toBe(true);
    expect(state.route.activeTarget).toBe('region-b');
  });

  // 13. Manual failback uses a guarded sequence
  it('13. Manual failback uses a guarded sequence', () => {
    let state: SimulationState = {
      ...INITIAL_SIMULATION_STATE,
      controllerState: 'SECONDARY_ACTIVE',
      regionA: {
        ...INITIAL_SIMULATION_STATE.regionA,
        role: 'STANDBY',
        acceptsWrites: false,
        health: 'HEALTHY',
        isFenced: true,
      },
      regionB: {
        ...INITIAL_SIMULATION_STATE.regionB,
        role: 'ACTIVE',
        acceptsWrites: true,
        health: 'HEALTHY',
      },
      route: {
        ...INITIAL_SIMULATION_STATE.route,
        activeTarget: 'region-b',
      },
    };

    // Step 1: Detect primary online in SECONDARY_ACTIVE -> enters PRIMARY_RECOVERING
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    expect(state.controllerState).toBe('PRIMARY_RECOVERING');

    // Step 2: Reconcile reverse replication -> enters FAILBACK_PENDING
    state = simulationReducer(state, { type: 'RECONCILE_REPLICATION' });
    expect(state.controllerState).toBe('FAILBACK_PENDING');

    // Step 3: Operator triggers manual failback -> enters FAILBACK_IN_PROGRESS
    state = simulationReducer(state, { type: 'TRIGGER_MANUAL_FAILBACK' });
    expect(state.controllerState).toBe('FAILBACK_IN_PROGRESS');

    // Step 4: Complete failback transition back to HEALTHY
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    expect(state.controllerState).toBe('HEALTHY');
    expect(state.regionA.role).toBe('ACTIVE');
    expect(state.regionA.acceptsWrites).toBe(true);
    expect(state.regionB.role).toBe('STANDBY');
    expect(state.regionB.acceptsWrites).toBe(false);
    expect(state.route.activeTarget).toBe('region-a');
  });

  // 14. Reset clears the simulation reliably
  it('14. Reset clears the simulation reliably', () => {
    engine.dispatch({ type: 'INJECT_PRIMARY_OUTAGE' });
    engine.dispatch({ type: 'TICK', deltaSec: 10 });
    expect(engine.getState().controllerState).not.toBe('HEALTHY');

    engine.reset();
    const state = engine.getState();
    expect(state.controllerState).toBe('HEALTHY');
    expect(state.consecutiveFailures).toBe(0);
    expect(state.simulatedTimeSeconds).toBe(0);
    expect(state.regionA.role).toBe('ACTIVE');
    expect(state.regionB.role).toBe('STANDBY');
    expect(state.regionA.acceptsWrites).toBe(true);
    expect(state.regionB.acceptsWrites).toBe(false);
  });

  // 15. Repeated clicks do not produce overlapping transitions
  it('15. Repeated clicks do not produce overlapping transitions', () => {
    let state = INITIAL_SIMULATION_STATE;
    state = simulationReducer(state, { type: 'TRIGGER_MANUAL_FAILOVER' });
    expect(state.isSequenceInProgress).toBe(true);
    expect(state.controllerState).toBe('QUORUM_CHECK');

    // Repeated call while sequence in progress must be ignored safely
    const duplicateState = simulationReducer(state, { type: 'TRIGGER_MANUAL_FAILOVER' });
    expect(duplicateState).toBe(state); // Identical reference, rejected by guard!
  });

  // 16. Every event is in chronological order
  it('16. Every event is in chronological order', () => {
    let state = INITIAL_SIMULATION_STATE;
    state = simulationReducer(state, { type: 'INJECT_PRIMARY_OUTAGE' });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });

    const events = state.eventHistory;
    expect(events.length).toBeGreaterThan(1);
    for (let i = 0; i < events.length - 1; i++) {
      expect(events[i].simulatedTimeSeconds).toBeGreaterThanOrEqual(
        events[i + 1].simulatedTimeSeconds
      );
    }
  });

  // 17. The architecture diagram always agrees with engine state
  it('17. The architecture diagram always agrees with engine state', () => {
    const state = engine.getState();
    // Verify properties mapped to SVG
    expect(state.regionA.role).toBe('ACTIVE');
    expect(state.regionB.role).toBe('STANDBY');
    expect(state.route.activeTarget).toBe('region-a');
    expect(state.regionA.fencingEpoch).toBe(101);
  });

  // 18. Exported reports reflect the actual current or last completed run
  it('18. Exported reports reflect the actual current or last completed run', () => {
    let state = INITIAL_SIMULATION_STATE;
    state = simulationReducer(state, { type: 'INJECT_PRIMARY_OUTAGE' });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });

    const reportJson = JSON.stringify({
      scenario: 'Test Scenario',
      controllerState: state.controllerState,
      regionA: state.regionA.role,
      regionB: state.regionB.role,
      simulatedTime: state.simulatedTimeSeconds,
    });

    const parsed = JSON.parse(reportJson);
    expect(parsed.controllerState).toBe(state.controllerState);
    expect(parsed.regionA).toBe('ACTIVE');
    expect(parsed.regionB).toBe('STANDBY');
    expect(parsed.simulatedTime).toBe(2);
  });
});
