import React from 'react';
import {
  Activity,
  Server,
  Network,
  Clock,
  Shield,
  AlertTriangle,
  CheckCircle,
  Database,
  Radio,
  Info,
} from 'lucide-react';
import { useSimulation } from '../../simulation/useSimulation';

export const MetricsDashboard: React.FC = () => {
  const {
    regionA,
    regionB,
    controllerState,
    consecutiveFailures,
    config,
    voters,
    replication,
    dns,
    simulatedTimeSeconds,
    telemetry,
    eventHistory,
  } = useSimulation();

  // 1. Current Active Region
  const activeRegion =
    regionA.role === 'ACTIVE'
      ? 'Region A (Mumbai)'
      : regionB.role === 'ACTIVE'
      ? 'Region B (Singapore)'
      : regionA.isFenced
      ? 'None (Region A Fenced)'
      : 'None (Standby Mode)';

  // 2. Healthy simulated monitors out of 3
  const healthyMonitorsCount = voters.filter((v) => v.vote !== 'ABSTAIN').length;

  // 3. Dynamic Request calculations derived from actual simulated time & state
  const totalSimulatedRequests = Math.round(simulatedTimeSeconds * telemetry.totalClientRps);
  const failedSimulatedRequests = Math.round(
    totalSimulatedRequests * (telemetry.clientErrorRate / 100)
  );
  const successfulSimulatedRequests = Math.max(0, totalSimulatedRequests - failedSimulatedRequests);

  // 4. Detection Duration derived from consecutive failure probes & interval
  const detectionDurationSec =
    consecutiveFailures > 0
      ? consecutiveFailures * config.healthCheckIntervalSec
      : 0;

  // 5. Failover Duration (Simulated RTO)
  // Derived from the difference between the outage event and the SECONDARY_ACTIVE event
  const outageEvent = eventHistory.find((e) =>
    e.reason.toLowerCase().includes('primary outage') || e.reason.toLowerCase().includes('process crashed')
  );
  const secondaryActiveEvent = eventHistory.find((e) =>
    e.transition?.includes('SECONDARY_ACTIVE')
  );

  let failoverDurationDisplay = 'N/A (Nominal Operation)';
  if (outageEvent && secondaryActiveEvent) {
    const durationSec = Math.abs(
      secondaryActiveEvent.simulatedTimeSeconds - outageEvent.simulatedTimeSeconds
    );
    failoverDurationDisplay = `${durationSec.toFixed(1)}s (Simulated RTO)`;
  } else if (outageEvent && controllerState !== 'HEALTHY') {
    const elapsedSec = Math.max(0, simulatedTimeSeconds - outageEvent.simulatedTimeSeconds);
    failoverDurationDisplay = `${elapsedSec.toFixed(1)}s (In Progress / Gated)`;
  }

  // 6. Approximate time of last transition
  const latestEvent = eventHistory[0];
  const lastTransitionTime = latestEvent
    ? `T+${Math.floor(latestEvent.simulatedTimeSeconds / 60)
        .toString()
        .padStart(2, '0')}:${(latestEvent.simulatedTimeSeconds % 60)
        .toString()
        .padStart(2, '0')} (${latestEvent.wallClockTimestamp})`
    : 'Initialization';

  return (
    <div className="metrics-dashboard">
      <div className="metrics-dashboard-header">
        <div className="dashboard-title-row">
          <Activity size={16} className="text-flow" />
          <h2 className="dashboard-title font-semibold text-xs font-mono uppercase tracking-wider">
            Live Telemetry & Safety Metrics (Simulated State)
          </h2>
          <span className="badge-tag badge-info font-mono text-xs ml-auto">
            100% Derived from Model
          </span>
        </div>
        <p className="dashboard-disclaimer text-xs text-muted mt-1">
          <Info size={12} className="inline mr-1 text-flow" />
          Values demonstrate educational model behavior derived directly from simulation state and do not represent physical cloud measurements. Replication lag is a modelled input state.
        </p>
      </div>

      <div className="metrics-grid-compact">
        {/* Metric 1: Active Region */}
        <div className="metric-box">
          <div className="metric-box-top">
            <Server size={13} className="text-flow" />
            <span className="metric-box-title font-mono text-xs">Active Region</span>
          </div>
          <span className="metric-box-value font-mono text-bright font-bold">
            {activeRegion}
          </span>
          <span className="metric-box-sub font-mono text-xs text-muted">
            {regionA.acceptsWrites ? 'Region A accepts writes' : regionB.acceptsWrites ? 'Region B accepts writes' : 'Writes revoked'}
          </span>
        </div>

        {/* Metric 2: Controller Phase */}
        <div className="metric-box">
          <div className="metric-box-top">
            <Shield size={13} className={controllerState === 'FAILOVER_BLOCKED' ? 'text-danger' : 'text-healthy'} />
            <span className="metric-box-title font-mono text-xs">Controller Phase</span>
          </div>
          <span className={`metric-box-value font-mono font-bold ${controllerState === 'FAILOVER_BLOCKED' ? 'text-danger' : 'text-flow'}`}>
            {controllerState}
          </span>
          <span className="metric-box-sub font-mono text-xs text-muted">
            State machine status
          </span>
        </div>

        {/* Metric 3: Health-Check Failures */}
        <div className="metric-box">
          <div className="metric-box-top">
            <AlertTriangle size={13} className={consecutiveFailures > 0 ? 'text-warning' : 'text-muted'} />
            <span className="metric-box-title font-mono text-xs">Health Probe Failures</span>
          </div>
          <span className={`metric-box-value font-mono font-bold ${consecutiveFailures > 0 ? 'text-warning' : 'text-healthy'}`}>
            {consecutiveFailures} / {config.failureThresholdConsecutive} Probes
          </span>
          <span className="metric-box-sub font-mono text-xs text-muted">
            Interval: {config.healthCheckIntervalSec}s
          </span>
        </div>

        {/* Metric 4: Healthy Simulated Monitors */}
        <div className="metric-box">
          <div className="metric-box-top">
            <Radio size={13} className="text-flow" />
            <span className="metric-box-title font-mono text-xs">Quorum Observers</span>
          </div>
          <span className="metric-box-value font-mono text-bright font-bold">
            {healthyMonitorsCount} / 3 Healthy
          </span>
          <span className="metric-box-sub font-mono text-xs text-muted">
            Majority required: {config.majorityRequired} of 3
          </span>
        </div>

        {/* Metric 5: Current Replication Lag */}
        <div className="metric-box">
          <div className="metric-box-top">
            <Database size={13} className={replication.lagSeconds > config.acceptableReplicationLagSec ? 'text-danger' : 'text-flow'} />
            <span className="metric-box-title font-mono text-xs">Modelled Replication Lag</span>
          </div>
          <span className={`metric-box-value font-mono font-bold ${replication.lagSeconds > config.acceptableReplicationLagSec ? 'text-danger' : 'text-bright'}`}>
            {replication.lagSeconds.toFixed(1)}s ({Math.round(replication.lagSeconds * 1000)}ms)
          </span>
          <span className="metric-box-sub font-mono text-xs text-muted">
            Policy limit: {config.acceptableReplicationLagSec}.0s
          </span>
        </div>

        {/* Metric 6: Current Routing Target */}
        <div className="metric-box">
          <div className="metric-box-top">
            <Network size={13} className="text-flow" />
            <span className="metric-box-title font-mono text-xs">Routing Target</span>
          </div>
          <span className="metric-box-value font-mono text-bright font-bold">
            {dns.activeDnsTarget === 'region-a' ? 'Mumbai (ap-south-1)' : 'Singapore (ap-southeast-1)'}
          </span>
          <span className="metric-box-sub font-mono text-xs text-muted">
            DNS TTL: {dns.ttlSeconds}s • Prop: {dns.propagationProgress}%
          </span>
        </div>

        {/* Metric 7: Simulated Requests Processed */}
        <div className="metric-box">
          <div className="metric-box-top">
            <Clock size={13} className="text-flow" />
            <span className="metric-box-title font-mono text-xs">Simulated Requests</span>
          </div>
          <span className="metric-box-value font-mono text-bright font-bold">
            {totalSimulatedRequests.toLocaleString()} Req
          </span>
          <span className="metric-box-sub font-mono text-xs text-muted">
            Rate: {telemetry.totalClientRps} RPS
          </span>
        </div>

        {/* Metric 8: Simulated Success / Failure Count */}
        <div className="metric-box">
          <div className="metric-box-top">
            <CheckCircle size={13} className="text-healthy" />
            <span className="metric-box-title font-mono text-xs">Request Success / Drop</span>
          </div>
          <span className="metric-box-value font-mono text-xs font-bold">
            <span className="text-healthy">{successfulSimulatedRequests.toLocaleString()} OK</span>
            {' • '}
            <span className={failedSimulatedRequests > 0 ? 'text-danger' : 'text-muted'}>
              {failedSimulatedRequests.toLocaleString()} Err
            </span>
          </span>
          <span className="metric-box-sub font-mono text-xs text-muted">
            Error Rate: {telemetry.clientErrorRate}%
          </span>
        </div>

        {/* Metric 9: Detection Duration */}
        <div className="metric-box">
          <div className="metric-box-top">
            <Clock size={13} className="text-flow" />
            <span className="metric-box-title font-mono text-xs">Detection Duration</span>
          </div>
          <span className="metric-box-value font-mono text-bright font-bold">
            {detectionDurationSec.toFixed(1)}s
          </span>
          <span className="metric-box-sub font-mono text-xs text-muted">
            Probe debounce window
          </span>
        </div>

        {/* Metric 10: Failover Duration (Simulated RTO) */}
        <div className="metric-box">
          <div className="metric-box-top">
            <Activity size={13} className="text-flow" />
            <span className="metric-box-title font-mono text-xs">Failover Duration (RTO)</span>
          </div>
          <span className="metric-box-value font-mono text-bright font-bold">
            {failoverDurationDisplay}
          </span>
          <span className="metric-box-sub font-mono text-xs text-muted">
            Measured cutover span
          </span>
        </div>

        {/* Metric 11: Approximate Time of Last Transition */}
        <div className="metric-box col-span-2">
          <div className="metric-box-top">
            <Clock size={13} className="text-flow" />
            <span className="metric-box-title font-mono text-xs">Last State Transition</span>
          </div>
          <span className="metric-box-value font-mono text-bright text-xs font-bold truncate">
            {lastTransitionTime}
          </span>
          <span className="metric-box-sub font-mono text-xs text-muted truncate">
            Latest: {latestEvent ? (latestEvent.transition || latestEvent.reason).slice(0, 48) : 'Nominal'}
          </span>
        </div>
      </div>
    </div>
  );
};
