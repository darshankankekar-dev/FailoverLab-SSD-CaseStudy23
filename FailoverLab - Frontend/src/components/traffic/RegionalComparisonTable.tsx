import React from 'react';
import type { ControllerStateDto } from '../../api/controllerClient';
import { Layers, CheckCircle2, AlertTriangle, XCircle, ShieldCheck, ShieldX } from 'lucide-react';

interface RegionalComparisonTableProps {
  controllerState: ControllerStateDto | null;
  measuredLatencies?: Record<string, number>;
}

const REGION_INFO: Record<string, { name: string; flag: string; zone: string; nominalWan: number }> = {
  'region-a': { name: 'Mumbai', flag: '🇮🇳', zone: 'ap-south-1', nominalWan: 24 },
  'region-b': { name: 'Singapore', flag: '🇸🇬', zone: 'ap-southeast-1', nominalWan: 42 },
  'region-c': { name: 'Frankfurt', flag: '🇩🇪', zone: 'eu-central-1', nominalWan: 110 },
  'region-d': { name: 'Virginia', flag: '🇺🇸', zone: 'us-east-1', nominalWan: 180 },
  'region-e': { name: 'São Paulo', flag: '🇧🇷', zone: 'sa-east-1', nominalWan: 270 },
};

export const RegionalComparisonTable: React.FC<RegionalComparisonTableProps> = ({
  controllerState,
  measuredLatencies = {},
}) => {
  const allRegionIds = ['region-a', 'region-b', 'region-c', 'region-d', 'region-e'] as const;
  const activeRegion = controllerState?.active_region || 'region-a';
  const acceptableLag = controllerState?.policy?.acceptable_replication_lag_sec ?? 5.0;
  const replicationDestinations = controllerState?.replication?.destinations || {};

  const regionsMap: Record<string, any> = {};
  if (controllerState?.regions && controllerState.regions.length > 0) {
    controllerState.regions.forEach((r) => {
      regionsMap[r.id] = r;
    });
  } else {
    if (controllerState?.region_a) regionsMap['region-a'] = controllerState.region_a;
    if (controllerState?.region_b) regionsMap['region-b'] = controllerState.region_b;
    if (controllerState?.region_c) regionsMap['region-c'] = controllerState.region_c;
    if (controllerState?.region_d) regionsMap['region-d'] = controllerState.region_d;
    if (controllerState?.region_e) regionsMap['region-e'] = controllerState.region_e;
  }

  // Evaluate candidate eligibility dynamically
  const evaluateCandidateEligibility = (rid: string) => {
    const isCurrentActive = activeRegion === rid;
    if (isCurrentActive) {
      return { eligible: false, reason: 'Current Primary Writer' };
    }

    const reg = regionsMap[rid];
    const health = reg?.health || 'HEALTHY';
    if (health === 'DOWN') {
      return { eligible: false, reason: 'Unhealthy / Storage Outage' };
    }
    if (reg?.is_fenced) {
      return { eligible: false, reason: 'Region is Fenced' };
    }

    const lag = reg?.replication_lag_seconds ?? replicationDestinations[rid]?.lag_seconds ?? 0.8;
    if (lag > acceptableLag) {
      return { eligible: false, reason: `Replication lag (${lag.toFixed(1)}s > ${acceptableLag.toFixed(1)}s)` };
    }

    const healthyServers = reg?.app_servers_healthy ?? 8;
    if (healthyServers <= 0) {
      return { eligible: false, reason: 'Zero Healthy App Servers' };
    }

    return { eligible: true, reason: 'Eligible Standby Candidate' };
  };

  return (
    <div className="traffic-panel">
      <div className="traffic-panel-header">
        <h3>
          <Layers size={18} className="text-flow" />
          <span>Multi-Region Operational Comparison Table</span>
        </h3>
        <span className="font-mono text-xs text-muted">
          Dynamic Evaluation (Threshold: ≤{acceptableLag.toFixed(1)}s lag)
        </span>
      </div>

      <div className="traffic-table-container">
        <table className="traffic-table">
          <thead>
            <tr>
              <th>Region / Location</th>
              <th>Health</th>
              <th>Role</th>
              <th>Measured RTT</th>
              <th>Simulated WAN</th>
              <th>Replication Lag</th>
              <th>Applied Sequence</th>
              <th>Write Eligibility</th>
              <th>Candidate Eligibility</th>
            </tr>
          </thead>
          <tbody>
            {allRegionIds.map((rid) => {
              const info = REGION_INFO[rid];
              const reg = regionsMap[rid];
              const isCurrentActive = activeRegion === rid;
              const health = reg?.health || 'HEALTHY';
              const measured = measuredLatencies[rid] ?? (isCurrentActive ? 18.4 : undefined);
              const lag = isCurrentActive
                ? 0.0
                : (reg?.replication_lag_seconds ?? replicationDestinations[rid]?.lag_seconds ?? 0.8);
              const appliedSeq = reg?.applied_sequence ?? (isCurrentActive ? 1050 : (replicationDestinations[rid]?.applied_sequence ?? 1050));
              const acceptsWrites = isCurrentActive && !reg?.is_fenced && health === 'HEALTHY';
              const candidate = evaluateCandidateEligibility(rid);

              return (
                <tr key={rid}>
                  {/* Region / Location */}
                  <td>
                    <div className="flex items-center gap-2">
                      <span>{info.flag}</span>
                      <span className="font-semibold">{info.name}</span>
                      <span className="region-code-badge">{rid}</span>
                    </div>
                  </td>

                  {/* Health */}
                  <td>
                    <span
                      className={`badge-tag-sm ${
                        health === 'HEALTHY'
                          ? 'badge-healthy'
                          : health === 'DEGRADED'
                          ? 'badge-warning'
                          : 'badge-danger'
                      }`}
                    >
                      {health === 'HEALTHY' ? (
                        <CheckCircle2 size={10} />
                      ) : health === 'DEGRADED' ? (
                        <AlertTriangle size={10} />
                      ) : (
                        <XCircle size={10} />
                      )}
                      <span>{health}</span>
                    </span>
                  </td>

                  {/* Role */}
                  <td>
                    <span
                      className={`badge-tag-sm ${
                        isCurrentActive ? 'badge-healthy' : 'badge-info'
                      }`}
                    >
                      {isCurrentActive ? 'ACTIVE' : 'STANDBY'}
                    </span>
                  </td>

                  {/* Measured RTT */}
                  <td className="font-mono">
                    {measured !== undefined ? (
                      <span className="text-flow font-semibold">
                        {measured.toFixed(1)} ms
                      </span>
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                  </td>

                  {/* Simulated WAN */}
                  <td className="font-mono text-muted">{info.nominalWan} ms</td>

                  {/* Replication Lag */}
                  <td className="font-mono">
                    {isCurrentActive ? (
                      <span className="text-muted font-mono">0.0s (Source)</span>
                    ) : (
                      <span
                        className={
                          lag > acceptableLag ? 'text-danger font-bold' : 'text-flow font-semibold'
                        }
                      >
                        {lag.toFixed(2)}s
                      </span>
                    )}
                  </td>

                  {/* Applied Sequence */}
                  <td className="font-mono text-bright">seq-{appliedSeq}</td>

                  {/* Write Eligibility */}
                  <td>
                    {acceptsWrites ? (
                      <span className="text-healthy font-semibold flex items-center gap-1">
                        <ShieldCheck size={12} /> Accepted
                      </span>
                    ) : (
                      <span className="text-muted flex items-center gap-1">
                        <ShieldX size={12} /> Rejected (Read-Only)
                      </span>
                    )}
                  </td>

                  {/* Candidate Eligibility */}
                  <td>
                    {candidate.eligible ? (
                      <span className="badge-tag-sm badge-healthy">
                        <CheckCircle2 size={10} />
                        <span>ELIGIBLE CANDIDATE</span>
                      </span>
                    ) : (
                      <span className="badge-tag-sm badge-secondary text-muted">
                        <span>{candidate.reason}</span>
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
