import { describe, it, expect } from 'vitest';
import {
  simulationReducer,
  INITIAL_SIMULATION_STATE,
} from './transitions';

describe('Scenarios A through I Execution & Verification', () => {
  it('Scenario A: Normal Operation maintains single-writer stability', () => {
    let state = INITIAL_SIMULATION_STATE;

    // Simulate several ticks under normal conditions
    for (let i = 0; i < 5; i++) {
      state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    }

    expect(state.controllerState).toBe('HEALTHY');
    expect(state.regionA.role).toBe('ACTIVE');
    expect(state.regionA.acceptsWrites).toBe(true);
    expect(state.regionB.role).toBe('STANDBY');
    expect(state.regionB.acceptsWrites).toBe(false);
    expect(state.consecutiveFailures).toBe(0);
    expect(state.route.activeTarget).toBe('region-a');
  });

  it('Scenario B: Primary Application Crash executes full automated cutover', () => {
    let state = INITIAL_SIMULATION_STATE;

    // Crash Mumbai primary
    state = simulationReducer(state, { type: 'INJECT_PRIMARY_OUTAGE' });
    expect(state.regionA.health).toBe('DOWN');

    // Tick 1: Probe 1 fails (1/3) -> PRIMARY_SUSPECTED
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    expect(state.controllerState).toBe('PRIMARY_SUSPECTED');
    expect(state.consecutiveFailures).toBe(1);

    // Tick 2: Probe 2 fails (2/3)
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    expect(state.consecutiveFailures).toBe(2);

    // Tick 3: Probe 3 fails (3/3) -> QUORUM_CHECK
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    expect(state.controllerState).toBe('QUORUM_CHECK');

    // Tick 4: Evaluates Quorum -> FENCING_PRIMARY
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    expect(state.controllerState).toBe('FENCING_PRIMARY');

    // Tick 5: Fences Region A (Epoch 102) -> PROMOTING_STANDBY
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    expect(state.controllerState).toBe('PROMOTING_STANDBY');
    expect(state.regionA.isFenced).toBe(true);
    expect(state.regionA.acceptsWrites).toBe(false);
    expect(state.regionB.fencingEpoch).toBe(102);

    // Tick 6: Promotes Region B -> ROUTE_UPDATING
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    expect(state.controllerState).toBe('ROUTE_UPDATING');
    expect(state.regionB.role).toBe('ACTIVE');
    expect(state.regionB.acceptsWrites).toBe(true);

    // Tick 7 & 8: DNS propagation converges -> VERIFYING_ROUTE -> SECONDARY_ACTIVE
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    expect(state.controllerState).toBe('VERIFYING_ROUTE');

    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    expect(state.controllerState).toBe('SECONDARY_ACTIVE');
    expect(state.route.activeTarget).toBe('region-b');
    expect(state.route.verificationStatus).toBe('VERIFIED');
  });

  it('Scenario C: Transient Failure / False Positive is suppressed before threshold', () => {
    let state = INITIAL_SIMULATION_STATE;

    // Probe 1 drops
    state = simulationReducer(state, { type: 'INJECT_PRIMARY_OUTAGE' });
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    expect(state.controllerState).toBe('PRIMARY_SUSPECTED');
    expect(state.consecutiveFailures).toBe(1);

    // Probe 2 drops (2/3)
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    expect(state.consecutiveFailures).toBe(2);

    // Primary recovers before probe 3!
    state = simulationReducer(state, { type: 'RECOVER_PRIMARY' });

    // Probe 3 succeeds -> False positive suppression!
    state = simulationReducer(state, { type: 'TICK', deltaSec: 2 });
    expect(state.controllerState).toBe('HEALTHY');
    expect(state.consecutiveFailures).toBe(0);
    expect(state.regionA.role).toBe('ACTIVE');
    expect(state.regionB.role).toBe('STANDBY');

    const suppressionEvent = state.eventHistory.find((e) =>
      e.reason.includes('False Positive Suppressed')
    );
    expect(suppressionEvent).toBeDefined();
  });

  it('Scenario D: Network Partition / Quorum Lost blocks failover', () => {
    let state = INITIAL_SIMULATION_STATE;

    // Simulate lost quorum: only 1 observer detects outage, 2 report healthy
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

    // Advance directly to Quorum Check
    state = {
      ...state,
      controllerState: 'QUORUM_CHECK',
      isSequenceInProgress: true,
    };

    // Step state machine: Gate 1 should block
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    expect(state.controllerState).toBe('FAILOVER_BLOCKED');
    expect(state.blockedReason).toContain('Insufficient quorum consensus');
    expect(state.regionB.role).toBe('STANDBY');
    expect(state.regionB.acceptsWrites).toBe(false);
  });

  it('Scenario E: Standby Unhealthy blocks failover at Gate 2', () => {
    let state = INITIAL_SIMULATION_STATE;

    // Standby corrupted
    state = simulationReducer(state, { type: 'INJECT_STANDBY_UNREADY' });
    expect(state.regionB.health).toBe('DOWN');

    // Crash primary
    state = simulationReducer(state, { type: 'INJECT_PRIMARY_OUTAGE' });

    // Fast-forward to QUORUM_CHECK with majority votes
    state = {
      ...state,
      controllerState: 'QUORUM_CHECK',
      voters: state.voters.map((v) => ({ ...v, vote: 'PRIMARY_OUTAGE' })),
    };

    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    expect(state.controllerState).toBe('FAILOVER_BLOCKED');
    expect(state.blockedReason).toContain('Standby readiness check failed');
    expect(state.regionB.acceptsWrites).toBe(false);
  });

  it('Scenario F: High Replication Lag blocks failover at Gate 3', () => {
    let state = INITIAL_SIMULATION_STATE;

    // Throttle replication to 8.4s (> 5s policy)
    state = simulationReducer(state, { type: 'INJECT_HIGH_REPLICATION_LAG' });
    expect(state.replication.lagSeconds).toBe(8.4);

    state = {
      ...state,
      controllerState: 'QUORUM_CHECK',
      voters: state.voters.map((v) => ({ ...v, vote: 'PRIMARY_OUTAGE' })),
    };

    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    expect(state.controllerState).toBe('FAILOVER_BLOCKED');
    expect(state.blockedReason).toContain('Replication lag gate failed');
    expect(state.regionB.acceptsWrites).toBe(false);
  });

  it('Scenario G: DNS Route Failure retries and blocks until verified', () => {
    let state = INITIAL_SIMULATION_STATE;

    // Inject route failure chaos
    state = simulationReducer(state, { type: 'INJECT_ROUTE_FAILURE' });

    // Advance to VERIFYING_ROUTE
    state = {
      ...state,
      controllerState: 'VERIFYING_ROUTE',
      route: {
        ...state.route,
        verificationStatus: 'VERIFYING',
      },
    };

    // Evaluates route check -> fails Gate 6
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    expect(state.controllerState).toBe('FAILOVER_BLOCKED');
    expect(state.blockedReason).toContain('Route verification failed');

    // Retry routing update: records attempt
    state = simulationReducer(state, { type: 'RETRY_ROUTING_UPDATE' });
    expect(state.routeRetryCount).toBe(1);

    // Restore route health & retry again
    state = simulationReducer(state, { type: 'RESTORE_ROUTE_HEALTH' });
    state = simulationReducer(state, { type: 'RETRY_ROUTING_UPDATE' });
    expect(state.controllerState).toBe('SECONDARY_ACTIVE');
    expect(state.route.verificationStatus).toBe('VERIFIED');
  });

  it('Scenario H: Old Primary Recovers requires manual failback authorization', () => {
    let state = INITIAL_SIMULATION_STATE;

    // Put system into SECONDARY_ACTIVE
    state = {
      ...state,
      controllerState: 'SECONDARY_ACTIVE',
      regionA: {
        ...state.regionA,
        role: 'STANDBY',
        health: 'HEALTHY',
        acceptsWrites: false,
        isFenced: true,
      },
      regionB: {
        ...state.regionB,
        role: 'ACTIVE',
        acceptsWrites: true,
        fencingEpoch: 102,
      },
      outageInjected: false,
    };

    // Ticking triggers PRIMARY_RECOVERING
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    expect(state.controllerState).toBe('PRIMARY_RECOVERING');
    expect(state.regionA.role).toBe('STANDBY'); // Stays standby!

    // Reconcile reverse replication
    state = simulationReducer(state, { type: 'RECONCILE_REPLICATION' });
    expect(state.controllerState).toBe('FAILBACK_PENDING');

    // Trigger deliberate manual failback
    state = simulationReducer(state, { type: 'TRIGGER_MANUAL_FAILBACK' });
    expect(state.controllerState).toBe('FAILBACK_IN_PROGRESS');

    // Complete failback
    state = simulationReducer(state, { type: 'TICK', deltaSec: 1 });
    expect(state.controllerState).toBe('HEALTHY');
    expect(state.regionA.role).toBe('ACTIVE');
    expect(state.regionA.acceptsWrites).toBe(true);
    expect(state.regionA.fencingEpoch).toBe(103);
    expect(state.regionB.role).toBe('STANDBY');
    expect(state.regionB.acceptsWrites).toBe(false);
  });

  it('Scenario I: Controller Interruption pauses sequence and reconciles intent', () => {
    let state = INITIAL_SIMULATION_STATE;

    // Advance to FENCING_PRIMARY
    state = {
      ...state,
      controllerState: 'FENCING_PRIMARY',
      isSequenceInProgress: true,
    };

    // Controller process halts
    state = simulationReducer(state, { type: 'CONTROLLER_INTERRUPT' });
    expect(state.isPausedInterrupted).toBe(true);
    expect(state.persistedIntent).toBe('FENCING_PRIMARY');
    expect(state.isSequenceInProgress).toBe(false);

    // On resume, reconcile persisted intent
    state = simulationReducer(state, { type: 'RESUME_CONTROLLER_RECONCILE' });
    expect(state.isPausedInterrupted).toBe(false);
    expect(state.persistedIntent).toBeNull();
    // Advanced cleanly to PROMOTING_STANDBY without dual-primary
    expect(state.controllerState).toBe('PROMOTING_STANDBY');
    expect(state.regionA.acceptsWrites).toBe(false);
  });
});
