// FailoverLab: Pure Safety Gates and Decision Functions
// System Design & SSD Case Study 23

import type {
  QuorumVoter,
  RegionModel,
  ReplicationState,
  RouteState,
  SimulationState,
} from './types';

export interface GateResult {
  passed: boolean;
  reason: string;
}

/**
 * Gate 1: Outage Threshold / Quorum Initiation Gate
 * Evaluates whether consecutive failed probes have reached the policy threshold.
 */
export function canInitiateQuorum(
  consecutiveFailures: number,
  threshold: number
): GateResult {
  if (consecutiveFailures >= threshold) {
    return {
      passed: true,
      reason: `Consecutive probe failure threshold reached (${consecutiveFailures}/${threshold}). Proceeding to independent quorum evaluation.`,
    };
  }
  return {
    passed: false,
    reason: `Consecutive failures (${consecutiveFailures}) below required threshold (${threshold}). Primary suspected but failover suppressed to avoid false positives.`,
  };
}

/**
 * Gate 2: Quorum Majority Gate
 * Requires a strict majority (e.g., 2 of 3 independent simulated observers)
 * confirming the primary outage before any failover sequence can proceed.
 */
export function evaluateQuorumMajority(
  voters: QuorumVoter[],
  majorityRequired: number
): GateResult & { outageVotesCount: number } {
  const outageVotesCount = voters.filter(
    (v) => v.vote === 'PRIMARY_OUTAGE'
  ).length;

  if (outageVotesCount >= majorityRequired) {
    return {
      passed: true,
      outageVotesCount,
      reason: `Quorum consensus achieved: ${outageVotesCount} of ${voters.length} independent voters confirmed primary outage (required: ${majorityRequired}).`,
    };
  }

  return {
    passed: false,
    outageVotesCount,
    reason: `Insufficient quorum consensus: Only ${outageVotesCount} of ${voters.length} voters confirmed outage (required: ${majorityRequired}). Transition blocked to prevent false partition failover.`,
  };
}

/**
 * Gate 3: Standby Readiness Gate
 * Verifies that Region B (Singapore) is in a healthy state and capable of accepting promotion.
 */
export function checkStandbyReadiness(regionB: RegionModel): GateResult {
  if (regionB.health !== 'HEALTHY') {
    return {
      passed: false,
      reason: `Standby readiness check failed: Region B (${regionB.name}) is currently ${regionB.health}. Promoting an unhealthy standby would cause total service outage.`,
    };
  }
  return {
    passed: true,
    reason: `Standby readiness verified: Region B (${regionB.name}) is HEALTHY and ready for promotion.`,
  };
}

/**
 * Gate 4: Replication Lag Policy Gate
 * Prohibits promotion if asynchronous replication lag exceeds the acceptable policy limit,
 * directly preventing uncommitted transactional data loss (RPO violation).
 */
export function checkReplicationLagPolicy(
  replication: ReplicationState,
  acceptableLagSec: number
): GateResult {
  if (replication.status === 'SEVERED') {
    return {
      passed: false,
      reason: `Replication policy check failed: Replication link is SEVERED. Unsynchronized WAL delta cannot be verified.`,
    };
  }

  if (replication.lagSeconds > acceptableLagSec) {
    return {
      passed: false,
      reason: `Replication lag gate failed: Current replication lag (${replication.lagSeconds}s) exceeds acceptable threshold (${acceptableLagSec}s). Promotion blocked to protect against catastrophic RPO data loss.`,
    };
  }

  return {
    passed: true,
    reason: `Replication lag satisfies policy: Current lag (${replication.lagSeconds}s) is within acceptable limit (${acceptableLagSec}s).`,
  };
}

/**
 * Gate 5: Fencing Confirmation Gate
 * Strictly prohibits promoting Region B until Region A is confirmed to be fenced
 * and stripped of write authority.
 */
export function verifyFencingConfirmed(regionA: RegionModel): GateResult {
  if (regionA.acceptsWrites) {
    return {
      passed: false,
      reason: `Fencing safety gate violated: Old primary (${regionA.name}) is still marked as accepting writes. Promoting standby now would create a catastrophic SPLIT-BRAIN.`,
    };
  }

  if (!regionA.isFenced) {
    return {
      passed: false,
      reason: `Fencing safety gate violated: Storage fence for old primary (${regionA.name}) has not been acknowledged by coordinator.`,
    };
  }

  return {
    passed: true,
    reason: `Fencing confirmed: Old primary (${regionA.name}) is hard-fenced and revoked of all write authorization. Epoch advanced safely.`,
  };
}

/**
 * Gate 6: Dual Primary Invariant Check
 * Universal safety invariant: At no point can both Region A and Region B simultaneously accept writes.
 */
export function verifyNoDualPrimary(
  regionA: RegionModel,
  regionB: RegionModel
): GateResult {
  if (regionA.acceptsWrites && regionB.acceptsWrites) {
    return {
      passed: false,
      reason: `CRITICAL SAFETY INVARIANT VIOLATED: Both ${regionA.name} and ${regionB.name} are marked as accepting writes simultaneously (Split-Brain).`,
    };
  }
  return {
    passed: true,
    reason: `Dual-primary invariant satisfied: Exactly one (or zero) writable region authorized.`,
  };
}

/**
 * Gate 7: Route Switching & Verification Gate
 * Validates that the global DNS / router has successfully pointed to Region B
 * and that simulated synthetic requests reach the newly promoted primary.
 */
export function verifyRouteOperational(
  route: RouteState,
  expectedTarget: 'region-a' | 'region-b',
  routeFailureInjected: boolean
): GateResult {
  if (routeFailureInjected || route.verificationStatus === 'FAILED') {
    return {
      passed: false,
      reason: `Route verification failed: Synthetic test requests to ${expectedTarget.toUpperCase()} timed out or failed to resolve. Failover marked unverified.`,
    };
  }

  if (route.activeTarget !== expectedTarget) {
    return {
      passed: false,
      reason: `Route verification failed: Active routing target (${route.activeTarget}) does not match promoted region (${expectedTarget}).`,
    };
  }

  if (route.propagationPercent < 100) {
    return {
      passed: false,
      reason: `Route verification in progress: DNS propagation at ${route.propagationPercent}%. Test probe pending complete convergence.`,
    };
  }

  return {
    passed: true,
    reason: `Route operational: 100% traffic successfully routed and synthetic test probe verified on ${expectedTarget.toUpperCase()}.`,
  };
}

/**
 * Gate 8: Failback Readiness Gate
 * When primary recovers, verifies health reconciliation and reverse replication
 * before allowing a deliberate, controlled failback.
 */
export function checkFailbackReadiness(state: SimulationState): GateResult {
  if (state.regionA.health !== 'HEALTHY') {
    return {
      passed: false,
      reason: `Failback blocked: Original primary (${state.regionA.name}) is still ${state.regionA.health}.`,
    };
  }

  if (state.replication.status !== 'SYNCED' && state.replication.lagSeconds > state.config.acceptableReplicationLagSec) {
    return {
      passed: false,
      reason: `Failback blocked: Reverse replication lag (${state.replication.lagSeconds}s) has not yet reconciled with active secondary (${state.regionB.name}).`,
    };
  }

  return {
    passed: true,
    reason: `Failback readiness verified: ${state.regionA.name} is HEALTHY and reverse replication is reconciled. Awaiting deliberate operator authorization.`,
  };
}
