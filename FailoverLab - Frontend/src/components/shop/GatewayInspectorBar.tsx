import React from 'react';
import {
  Activity,
  Sliders,
  ChevronUp,
  ChevronDown,
} from 'lucide-react';
import { CLIENT_REGIONS } from '../../api/ecommerceClient';
import type { GatewayResponseMetadata } from '../../api/ecommerceClient';

interface GatewayInspectorBarProps {
  metadata: GatewayResponseMetadata | null;
  isOpen: boolean;
  onToggle: () => void;
  selectedRegion: string;
}

export const GatewayInspectorBar: React.FC<GatewayInspectorBarProps> = ({
  metadata,
  isOpen,
  onToggle,
  selectedRegion,
}) => {
  const clientReg = CLIENT_REGIONS.find((r) => r.id === selectedRegion) || CLIENT_REGIONS[0];

  if (!metadata) {
    return (
      <aside className="gateway-inspector-docked">
        <button
          type="button"
          className="inspector-dock-pill"
          onClick={onToggle}
          title="Toggle Gateway Telemetry Inspector"
        >
          <Activity size={13} className="text-flow" />
          <span className="font-mono text-xs">Gateway Ready • [{clientReg.flag}] {clientReg.name}</span>
          {isOpen ? <ChevronDown size={13} /> : <ChevronUp size={13} />}
        </button>
      </aside>
    );
  }

  return (
    <aside className="gateway-inspector-docked">
      <button
        type="button"
        className="inspector-dock-pill"
        onClick={onToggle}
        title="Toggle Gateway Telemetry Inspector"
      >
        <span className="pulse-dot pulse-healthy" />
        <span className="font-mono text-xs">
          Served: <strong className="text-flow">{metadata.servedRegion}</strong> ({metadata.latencyMs.toFixed(1)}ms) • {metadata.consistencyLevel.toUpperCase()}
        </span>
        {isOpen ? <ChevronDown size={13} /> : <ChevronUp size={13} />}
      </button>

      {isOpen && (
        <div className="inspector-dock-panel">
          <div className="inspector-panel-header">
            <div className="header-left">
              <Sliders size={14} className="text-flow" />
              <span className="header-title">FailoverLab Ingress Route Telemetry</span>
            </div>
            <span className="header-time font-mono">{metadata.timestamp}</span>
          </div>

          <div className="inspector-stats-grid">
            <div className="stat-item">
              <span className="stat-label">Served Target</span>
              <span className="stat-val font-mono text-flow">{metadata.servedRegion}</span>
            </div>

            <div className="stat-item">
              <span className="stat-label">Active Primary</span>
              <span className="stat-val font-mono text-healthy">{metadata.activeRegion}</span>
            </div>

            <div className="stat-item">
              <span className="stat-label">Consistency</span>
              <span className="stat-val font-mono uppercase">{metadata.consistencyLevel}</span>
            </div>

            <div className="stat-item">
              <span className="stat-label">Backend Latency</span>
              <span className="stat-val font-mono">{metadata.latencyMs.toFixed(1)} ms</span>
            </div>

            <div className="stat-item">
              <span className="stat-label">Simulated WAN</span>
              <span className="stat-val font-mono text-warning">+{metadata.simulatedWanDelayMs.toFixed(1)} ms</span>
            </div>

            <div className="stat-item">
              <span className="stat-label">Client Location</span>
              <span className="stat-val font-mono">[{clientReg.flag}] {clientReg.zone}</span>
            </div>

            <div className="stat-item full-row">
              <span className="stat-label">Request ID</span>
              <span className="stat-val font-mono text-xs text-muted">{metadata.requestId}</span>
            </div>

            {metadata.rateLimitMode && (
              <div className="stat-item full-row rate-limit-row">
                <span className="stat-label">Traffic Limiter</span>
                <span className="stat-val font-mono text-xs">
                  Mode: <strong className="text-flow">{metadata.rateLimitMode}</strong>
                  {metadata.rateLimitRemaining !== undefined && ` • Tokens Remaining: ${metadata.rateLimitRemaining}`}
                </span>
              </div>
            )}
          </div>
        </div>
      )}
    </aside>
  );
};
