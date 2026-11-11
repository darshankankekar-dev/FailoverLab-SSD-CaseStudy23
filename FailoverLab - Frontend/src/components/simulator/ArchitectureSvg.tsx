import { ShieldAlert } from 'lucide-react';
import { useSimulation } from '../../simulation/useSimulation';
import type { SelectedComponentType } from '../../simulation/types';

export const ArchitectureSvg: React.FC = () => {
  const {
    regionA,
    regionB,
    primaryDb,
    standbyDb,
    dns,
    leaseFence,
    replication,
    quorum,
    selectedComponent,
    controllerState,
    blockedReason,
    isSequenceInProgress,
    simulatedTimeSeconds,
    eventHistory,
    isRunning,
    config,
    consecutiveFailures,
    engine,
  } = useSimulation();

  const handleSelect = (component: SelectedComponentType) => {
    engine.selectComponent(component);
  };

  const isDnsPointingToA = dns.activeDnsTarget === 'region-a';
  const isDnsPropagating = dns.resolutionStatus === 'PROPAGATING';

  // State styling helpers
  const isAOutage = regionA.status === 'failed' || regionA.health === 'DOWN';
  const isASuspected = controllerState === 'PRIMARY_SUSPECTED';
  const isAFenced = regionA.isFenced;
  const isBActive = regionB.role === 'ACTIVE';

  // Path flow colors
  const clientFlowColor = isAOutage && isDnsPointingToA ? '#ef4444' : '#0ea5e9';
  const routeAColor = isDnsPointingToA
    ? isAOutage
      ? '#ef4444'
      : isASuspected
      ? '#f59e0b'
      : '#0ea5e9'
    : '#334155';

  const routeBColor = isBActive
    ? '#10b981'
    : isDnsPropagating
    ? '#f59e0b'
    : '#334155';

  const repFlowColor =
    replication.status === 'SEVERED'
      ? '#ef4444'
      : replication.status === 'DEGRADED'
      ? '#f59e0b'
      : '#38bdf8';

  const formatSimTime = (totalSec: number) => {
    const mins = Math.floor(totalSec / 60);
    const secs = totalSec % 60;
    return `T+${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const isSelected = (ids: SelectedComponentType[]) => ids.includes(selectedComponent);

  return (
    <div className="architecture-svg-wrapper">
      {/* Visual Legend Bar */}
      <div className="architecture-legend-bar">
        <div className="legend-item">
          <span className="legend-indicator legend-active" />
          <span className="text-xs text-secondary font-mono">Active Writer (Green)</span>
        </div>
        <div className="legend-item">
          <span className="legend-indicator legend-standby" />
          <span className="text-xs text-secondary font-mono">Standby / Read Replica (Cyan)</span>
        </div>
        <div className="legend-item">
          <span className="legend-indicator legend-degraded" />
          <span className="text-xs text-secondary font-mono">Suspected / Warning (Amber)</span>
        </div>
        <div className="legend-item">
          <span className="legend-indicator legend-fenced" />
          <span className="text-xs text-secondary font-mono">Outage / Fenced (Red)</span>
        </div>
        <div className="legend-divider-vertical" />
        <div className="legend-item">
          <span className="legend-line legend-line-solid" />
          <span className="text-xs text-muted font-mono">Solid: Client Ingress & Data</span>
        </div>
        <div className="legend-item">
          <span className="legend-line legend-line-dashed" />
          <span className="text-xs text-muted font-mono">Dashed: Health & Control Signals</span>
        </div>
        <div className="legend-item">
          <span className="legend-line legend-line-rep" />
          <span className="text-xs text-muted font-mono">WAL: Database Replication</span>
        </div>
      </div>

      {/* Blocked State Prominent Warning Banner */}
      {controllerState === 'FAILOVER_BLOCKED' && (
        <div className="diagram-blocked-banner">
          <div className="diagram-blocked-header">
            <ShieldAlert size={18} className="text-danger animate-pulse" />
            <span className="font-mono text-xs font-bold text-danger">
              AUTOMATED FAILOVER BLOCKED BY SAFETY GATES
            </span>
          </div>
          <p className="font-mono text-xs text-bright mt-1">
            {blockedReason || 'Mandatory safety precondition violated. Fencing halted to protect data integrity.'}
          </p>
          <div className="diagram-blocked-actions">
            <span className="text-xs text-muted">
              Invariant: Standby must be healthy & replication lag must not exceed {config.acceptableReplicationLagSec}s limit.
            </span>
            <button
              className="btn-console btn-danger text-xs ml-auto"
              onClick={() => engine.dismissBlockedState()}
            >
              Dismiss Block Alert
            </button>
          </div>
        </div>
      )}

      {/* Responsive SVG Architecture Diagram Canvas */}
      <svg
        className="architecture-svg-canvas"
        viewBox="0 0 1100 880"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-label="FailoverLab Multi-Region Architecture Topology Diagram"
      >
        <defs>
          {/* Gradients */}
          <linearGradient id="regionAGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#141a29" />
            <stop offset="100%" stopColor="#0d111c" />
          </linearGradient>
          <linearGradient id="regionBGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#141a29" />
            <stop offset="100%" stopColor="#0d111c" />
          </linearGradient>
          <linearGradient id="controllerGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#111726" />
            <stop offset="100%" stopColor="#090d16" />
          </linearGradient>
          <linearGradient id="moduleGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#182236" />
            <stop offset="100%" stopColor="#101726" />
          </linearGradient>

          {/* Glow Filters */}
          <filter id="glowActive" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
          <filter id="glowWarning" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
        </defs>

        {/* ============================================================== */}
        {/* CONNECTION PATH DEFINITIONS (Used for layout & animation)      */}
        {/* ============================================================== */}

        {/* 1. Client to Router: Solid Client-Request Flow */}
        <path
          id="path-client-to-router"
          d="M 550 74 L 550 114"
          stroke={clientFlowColor}
          strokeWidth="2.5"
        />

        {/* 2. Router to Regional APIs: Solid Traffic Routes */}
        {/* Route to Region A App Service */}
        <path
          id="path-router-to-a"
          d="M 410 186 C 410 226, 160 216, 160 268"
          stroke={routeAColor}
          strokeWidth={isDnsPointingToA ? '3' : '1.5'}
          strokeDasharray={isDnsPointingToA ? 'none' : '4 4'}
          opacity={isDnsPointingToA ? 1 : 0.4}
        />

        {/* Route to Region B App Service */}
        <path
          id="path-router-to-b"
          d="M 690 186 C 690 226, 720 216, 720 268"
          stroke={routeBColor}
          strokeWidth={isBActive ? '3' : isDnsPropagating ? '2.5' : '1.5'}
          strokeDasharray={isBActive ? 'none' : isDnsPropagating ? '6 3' : '4 4'}
          opacity={isBActive || isDnsPropagating ? 1 : 0.4}
        />

        {/* 3. API to Database: Solid Application Data Paths */}
        {/* Region A: App Service -> Database */}
        <path
          id="path-app-to-db-a"
          d="M 160 342 L 160 372"
          stroke={regionA.acceptsWrites ? '#10b981' : isAOutage ? '#ef4444' : '#64748b'}
          strokeWidth={regionA.acceptsWrites ? '2.5' : '1.5'}
        />

        {/* Region B: App Service -> Database */}
        <path
          id="path-app-to-db-b"
          d="M 720 342 L 720 372"
          stroke={regionB.acceptsWrites ? '#10b981' : '#38bdf8'}
          strokeWidth={regionB.acceptsWrites ? '2.5' : '1.5'}
        />

        {/* 4. Primary DB to Standby DB: Labelled Replication Relationship */}
        <path
          id="path-replication"
          d="M 494 440 L 608 440"
          stroke={repFlowColor}
          strokeWidth="3"
          strokeDasharray={replication.status === 'STREAMING' ? 'none' : '5 4'}
        />

        {/* 5. Regional Health Agents to Monitor: Dashed Monitoring Paths */}
        {/* Region A Health Agent -> Health Monitor */}
        <path
          id="path-health-a-to-monitor"
          d="M 389 342 C 389 540, 208 540, 208 605"
          stroke={isAOutage ? '#ef4444' : isASuspected ? '#f59e0b' : '#38bdf8'}
          strokeWidth="1.5"
          strokeDasharray="4 4"
          opacity="0.85"
        />

        {/* Region B Health Agent -> Health Monitor */}
        <path
          id="path-health-b-to-monitor"
          d="M 949 342 C 949 550, 230 550, 230 605"
          stroke="#38bdf8"
          strokeWidth="1.5"
          strokeDasharray="4 4"
          opacity="0.85"
        />

        {/* 6. Controller to Fencing/Promotion Actions: Dashed Control Paths */}
        {/* Controller -> Region A DB (Fencing Action Path) */}
        <path
          id="path-control-fence-a"
          d="M 300 605 C 300 545, 271 545, 271 508"
          stroke={controllerState === 'FENCING_PRIMARY' ? '#ef4444' : '#475569'}
          strokeWidth={controllerState === 'FENCING_PRIMARY' ? '2.5' : '1.2'}
          strokeDasharray="5 3"
          opacity={controllerState === 'FENCING_PRIMARY' ? 1 : 0.5}
        />

        {/* Controller -> Region B DB (Promotion Action Path) */}
        <path
          id="path-control-promote-b"
          d="M 366 725 C 550 725, 831 630, 831 508"
          stroke={controllerState === 'PROMOTING_STANDBY' ? '#10b981' : '#475569'}
          strokeWidth={controllerState === 'PROMOTING_STANDBY' ? '2.5' : '1.2'}
          strokeDasharray="5 3"
          opacity={controllerState === 'PROMOTING_STANDBY' ? 1 : 0.5}
        />

        {/* 7. Controller to Router: DNS/Routing-Update Control Path */}
        <path
          id="path-control-dns"
          d="M 550 560 L 550 186"
          stroke={controllerState === 'ROUTE_UPDATING' ? '#f59e0b' : '#475569'}
          strokeWidth={controllerState === 'ROUTE_UPDATING' ? '2.5' : '1.2'}
          strokeDasharray="5 4"
          opacity={controllerState === 'ROUTE_UPDATING' ? 1 : 0.5}
        />

        {/* ============================================================== */}
        {/* ANIMATED TRAFFIC INDICATORS (Rendered ONLY when running)       */}
        {/* ============================================================== */}
        {isRunning && (
          <g className="animated-traffic-flow">
            {/* Client -> DNS pulse */}
            <circle r="4" fill={clientFlowColor}>
              <animateMotion dur="0.9s" repeatCount="indefinite">
                <mpath href="#path-client-to-router" />
              </animateMotion>
            </circle>

            {/* DNS -> Active Region App pulse */}
            {isDnsPointingToA && !isAOutage && (
              <circle r="4" fill="#0ea5e9">
                <animateMotion dur="1.3s" repeatCount="indefinite">
                  <mpath href="#path-router-to-a" />
                </animateMotion>
              </circle>
            )}
            {(!isDnsPointingToA || isDnsPropagating) && (
              <circle r="4" fill="#10b981">
                <animateMotion dur="1.3s" repeatCount="indefinite">
                  <mpath href="#path-router-to-b" />
                </animateMotion>
              </circle>
            )}

            {/* App -> DB pulse */}
            {regionA.acceptsWrites && (
              <circle r="3.5" fill="#10b981">
                <animateMotion dur="0.8s" repeatCount="indefinite">
                  <mpath href="#path-app-to-db-a" />
                </animateMotion>
              </circle>
            )}
            {regionB.acceptsWrites && (
              <circle r="3.5" fill="#10b981">
                <animateMotion dur="0.8s" repeatCount="indefinite">
                  <mpath href="#path-app-to-db-b" />
                </animateMotion>
              </circle>
            )}

            {/* Replication pulse from A to B (only if streaming) */}
            {replication.status === 'STREAMING' && (
              <circle r="3.5" fill="#38bdf8">
                <animateMotion dur="1.8s" repeatCount="indefinite">
                  <mpath href="#path-replication" />
                </animateMotion>
              </circle>
            )}
          </g>
        )}

        {/* ============================================================== */}
        {/* TOP: CLIENT / TRAFFIC GENERATOR                                */}
        {/* ============================================================== */}
        <g
          className={`interactive-node ${isSelected(['CLIENTS']) ? 'node-selected' : ''}`}
          onClick={() => handleSelect('CLIENTS')}
          transform="translate(370, 18)"
          cursor="pointer"
        >
          <rect
            width="360"
            height="56"
            rx="6"
            fill="#121724"
            stroke={isSelected(['CLIENTS']) ? '#0ea5e9' : '#232d42'}
            strokeWidth={isSelected(['CLIENTS']) ? '2' : '1'}
          />
          <text x="180" y="24" textAnchor="middle" fill="#f8fafc" fontSize="13" fontWeight="600" fontFamily="Inter, sans-serif">
            CLIENT / TRAFFIC GENERATOR
          </text>
          <text x="180" y="44" textAnchor="middle" fill="#94a3b8" fontSize="11" fontFamily="JetBrains Mono, monospace">
            2,450 Ingress RPS • Synthetic Client Load • p95: 22ms
          </text>
        </g>

        {/* ============================================================== */}
        {/* BELOW: DNS / TRAFFIC ROUTER                                    */}
        {/* ============================================================== */}
        <g
          className={`interactive-node ${isSelected(['DNS']) ? 'node-selected' : ''}`}
          onClick={() => handleSelect('DNS')}
          transform="translate(350, 114)"
          cursor="pointer"
        >
          <rect
            width="400"
            height="72"
            rx="6"
            fill="#141a29"
            stroke={
              isSelected(['DNS'])
                ? '#0ea5e9'
                : isDnsPropagating
                ? '#f59e0b'
                : '#2a354d'
            }
            strokeWidth={isSelected(['DNS']) ? '2' : '1'}
          />
          <text x="200" y="24" textAnchor="middle" fill="#f8fafc" fontSize="13" fontWeight="600" fontFamily="Inter, sans-serif">
            DNS / TRAFFIC ROUTER (Global Anycast)
          </text>
          <text x="200" y="44" textAnchor="middle" fill={isDnsPropagating ? '#fbbf24' : '#38bdf8'} fontSize="11" fontFamily="JetBrains Mono, monospace">
            Target: {dns.activeDnsTarget === 'region-a' ? 'Region A — Mumbai (ap-south-1)' : 'Region B — Singapore (ap-southeast-1)'}
          </text>
          <text x="200" y="61" textAnchor="middle" fill="#64748b" fontSize="10" fontFamily="JetBrains Mono, monospace">
            TTL: {dns.ttlSeconds}s • Propagation: {dns.propagationProgress}% • Status: {dns.resolutionStatus}
          </text>
        </g>

        {/* ============================================================== */}
        {/* MIDDLE LEFT CONTAINER: REGION A — MUMBAI                       */}
        {/* ============================================================== */}
        <g
          className={`interactive-node ${isSelected(['REGION_A']) ? 'node-selected' : ''}`}
          onClick={() => handleSelect('REGION_A')}
          transform="translate(30, 226)"
          cursor="pointer"
        >
          {/* Outer Boundary */}
          <rect
            width="480"
            height="300"
            rx="8"
            fill="url(#regionAGrad)"
            stroke={
              isAOutage
                ? '#ef4444'
                : isASuspected
                ? '#f59e0b'
                : isAFenced
                ? '#b91c1c'
                : regionA.role === 'ACTIVE'
                ? '#10b981'
                : '#334155'
            }
            strokeWidth={isSelected(['REGION_A']) || regionA.role === 'ACTIVE' ? '2' : '1'}
          />

          {/* Region A Header */}
          <text x="20" y="28" fill="#f8fafc" fontSize="13" fontWeight="700" fontFamily="Inter, sans-serif">
            REGION A — MUMBAI (ap-south-1)
          </text>

          {/* Region Role & Status Badges */}
          <g transform="translate(320, 12)">
            <rect
              width="140"
              height="22"
              rx="4"
              fill={
                isAOutage
                  ? 'rgba(239, 68, 68, 0.2)'
                  : isASuspected
                  ? 'rgba(245, 158, 11, 0.2)'
                  : isAFenced
                  ? 'rgba(185, 28, 28, 0.25)'
                  : regionA.role === 'ACTIVE'
                  ? 'rgba(16, 185, 129, 0.2)'
                  : 'rgba(100, 116, 139, 0.2)'
              }
              stroke={
                isAOutage
                  ? '#ef4444'
                  : isASuspected
                  ? '#f59e0b'
                  : isAFenced
                  ? '#b91c1c'
                  : regionA.role === 'ACTIVE'
                  ? '#10b981'
                  : '#64748b'
              }
            />
            <text x="70" y="15" textAnchor="middle" fill={
              isAOutage
                ? '#f87171'
                : isASuspected
                ? '#fbbf24'
                : isAFenced
                ? '#fca5a5'
                : regionA.role === 'ACTIVE'
                ? '#10b981'
                : '#94a3b8'
            } fontSize="10" fontWeight="700" fontFamily="JetBrains Mono, monospace">
              {isAOutage
                ? 'OUTAGE / DOWN'
                : isASuspected
                ? 'SUSPECTED (WARN)'
                : isAFenced
                ? 'ISOLATED / FENCED'
                : 'ACTIVE (PRIMARY)'}
            </text>
          </g>

          {/* 1. Application Service */}
          <g
            className={`interactive-node ${isSelected(['REGION_A_APP']) ? 'node-selected' : ''}`}
            onClick={(e) => {
              e.stopPropagation();
              handleSelect('REGION_A_APP');
            }}
            transform="translate(18, 42)"
          >
            <rect
              width="224"
              height="74"
              rx="6"
              fill="#182133"
              stroke={isSelected(['REGION_A_APP']) ? '#0ea5e9' : '#2a3752'}
              strokeWidth={isSelected(['REGION_A_APP']) ? '2' : '1'}
            />
            <text x="12" y="22" fill="#f1f5f9" fontSize="11" fontWeight="600">Application Service</text>
            <text x="12" y="42" fill="#94a3b8" fontSize="10" fontFamily="JetBrains Mono, monospace">
              Ingress Pool • NGINX / K8s
            </text>
            <text x="12" y="60" fill={regionA.status === 'failed' ? '#ef4444' : '#38bdf8'} fontSize="10" fontFamily="JetBrains Mono, monospace">
              {regionA.appServersHealthy}/{regionA.appServersTotal} Nodes • {regionA.ingressRps.toLocaleString()} RPS
            </text>
          </g>

          {/* 2. Health Agent */}
          <g
            className={`interactive-node ${isSelected(['REGION_A_HEALTH']) ? 'node-selected' : ''}`}
            onClick={(e) => {
              e.stopPropagation();
              handleSelect('REGION_A_HEALTH');
            }}
            transform="translate(254, 42)"
          >
            <rect
              width="210"
              height="74"
              rx="6"
              fill="#182133"
              stroke={isSelected(['REGION_A_HEALTH']) ? '#0ea5e9' : isASuspected ? '#f59e0b' : '#2a3752'}
              strokeWidth={isSelected(['REGION_A_HEALTH']) ? '2' : '1'}
            />
            <text x="12" y="22" fill="#f1f5f9" fontSize="11" fontWeight="600">Health Agent</text>
            <text x="12" y="42" fill="#94a3b8" fontSize="10" fontFamily="JetBrains Mono, monospace">
              Synthetic Prober (2s tick)
            </text>
            <text x="12" y="60" fill={isAOutage ? '#ef4444' : isASuspected ? '#f59e0b' : '#10b981'} fontSize="10" fontWeight="600" fontFamily="JetBrains Mono, monospace">
              {isAOutage ? 'TIMEOUT (3/3 FAIL)' : isASuspected ? `FAIL (${consecutiveFailures}/3)` : 'HEARTBEAT OK (18ms)'}
            </text>
          </g>

          {/* 3. Primary Database */}
          <g
            className={`interactive-node ${isSelected(['PRIMARY_DB', 'REGION_A_DB']) ? 'node-selected' : ''}`}
            onClick={(e) => {
              e.stopPropagation();
              handleSelect('PRIMARY_DB');
            }}
            transform="translate(18, 144)"
          >
            <rect
              width="446"
              height="136"
              rx="6"
              fill="#101624"
              stroke={
                isAOutage
                  ? '#ef4444'
                  : isASuspected
                  ? '#f59e0b'
                  : isAFenced
                  ? '#b91c1c'
                  : regionA.acceptsWrites
                  ? '#10b981'
                  : '#2a3752'
              }
              strokeWidth={isSelected(['PRIMARY_DB', 'REGION_A_DB']) ? '2.5' : '1.5'}
            />
            <text x="16" y="26" fill="#f8fafc" fontSize="12" fontWeight="700">
              Primary Database (Aurora / Postgres)
            </text>

            {/* Access Mode Tag */}
            <g transform="translate(300, 12)">
              <rect
                width="130"
                height="22"
                rx="4"
                fill={
                  regionA.acceptsWrites
                    ? 'rgba(16, 185, 129, 0.2)'
                    : isAFenced
                    ? 'rgba(185, 28, 28, 0.25)'
                    : 'rgba(100, 116, 139, 0.2)'
                }
              />
              <text x="65" y="15" textAnchor="middle" fill={
                regionA.acceptsWrites ? '#10b981' : isAFenced ? '#fca5a5' : '#94a3b8'
              } fontSize="10" fontWeight="700" fontFamily="JetBrains Mono, monospace">
                {regionA.acceptsWrites ? 'READ_WRITE (Active)' : isAFenced ? 'FENCED (Revoked)' : 'READ_ONLY'}
              </text>
            </g>

            <text x="16" y="54" fill="#94a3b8" fontSize="10" fontFamily="JetBrains Mono, monospace">
              Role: PRIMARY • Generation Epoch: #{primaryDb.generationId}
            </text>
            <text x="16" y="74" fill={isAOutage ? '#ef4444' : isASuspected ? '#fbbf24' : '#cbd5e1'} fontSize="10" fontFamily="JetBrains Mono, monospace">
              Node Health: {isAOutage ? 'PROCESS CRASHED / OUTAGE' : isASuspected ? 'SUSPECTED UNREACHABLE' : isAFenced ? 'STORAGE FENCED' : 'SYNCHRONOUS MASTER OK'}
            </text>
            <text x="16" y="94" fill="#64748b" fontSize="10" fontFamily="JetBrains Mono, monospace">
              Active IOPS: {primaryDb.iops.toLocaleString()} • Storage: {primaryDb.storageGb} GB
            </text>
            <text x="16" y="114" fill="#64748b" fontSize="9" fontFamily="JetBrains Mono, monospace">
              WAL Generation: 0/18A4F00 • Write Lock: {regionA.acceptsWrites ? 'HELD' : 'RELEASED'}
            </text>
          </g>
        </g>

        {/* ============================================================== */}
        {/* MIDDLE RIGHT CONTAINER: REGION B — SINGAPORE                  */}
        {/* ============================================================== */}
        <g
          className={`interactive-node ${isSelected(['REGION_B']) ? 'node-selected' : ''}`}
          onClick={() => handleSelect('REGION_B')}
          transform="translate(590, 226)"
          cursor="pointer"
        >
          {/* Outer Boundary */}
          <rect
            width="480"
            height="300"
            rx="8"
            fill="url(#regionBGrad)"
            stroke={
              isBActive
                ? '#10b981'
                : isSelected(['REGION_B'])
                ? '#0ea5e9'
                : '#232d42'
            }
            strokeWidth={isSelected(['REGION_B']) || isBActive ? '2' : '1'}
          />

          {/* Region B Header */}
          <text x="20" y="28" fill="#f8fafc" fontSize="13" fontWeight="700" fontFamily="Inter, sans-serif">
            REGION B — SINGAPORE (ap-southeast-1)
          </text>

          {/* Region Role Badge */}
          <g transform="translate(320, 12)">
            <rect
              width="140"
              height="22"
              rx="4"
              fill={isBActive ? 'rgba(16, 185, 129, 0.2)' : 'rgba(56, 189, 248, 0.15)'}
              stroke={isBActive ? '#10b981' : '#0ea5e9'}
            />
            <text x="70" y="15" textAnchor="middle" fill={isBActive ? '#10b981' : '#38bdf8'} fontSize="10" fontWeight="700" fontFamily="JetBrains Mono, monospace">
              {isBActive ? 'ACTIVE (PROMOTED)' : 'STANDBY (PASSIVE)'}
            </text>
          </g>

          {/* 1. Standby Application Service */}
          <g
            className={`interactive-node ${isSelected(['REGION_B_APP']) ? 'node-selected' : ''}`}
            onClick={(e) => {
              e.stopPropagation();
              handleSelect('REGION_B_APP');
            }}
            transform="translate(18, 42)"
          >
            <rect
              width="224"
              height="74"
              rx="6"
              fill="#182133"
              stroke={isSelected(['REGION_B_APP']) ? '#0ea5e9' : '#2a3752'}
              strokeWidth={isSelected(['REGION_B_APP']) ? '2' : '1'}
            />
            <text x="12" y="22" fill="#f1f5f9" fontSize="11" fontWeight="600">
              {isBActive ? 'Application Service' : 'Standby App Service'}
            </text>
            <text x="12" y="42" fill="#94a3b8" fontSize="10" fontFamily="JetBrains Mono, monospace">
              {isBActive ? 'Active Ingress Gateway' : 'Warm Standby Compute'}
            </text>
            <text x="12" y="60" fill={isBActive ? '#10b981' : '#94a3b8'} fontSize="10" fontFamily="JetBrains Mono, monospace">
              {regionB.appServersHealthy}/{regionB.appServersTotal} Nodes • {regionB.ingressRps.toLocaleString()} RPS
            </text>
          </g>

          {/* 2. Health Agent */}
          <g
            className={`interactive-node ${isSelected(['REGION_B_HEALTH']) ? 'node-selected' : ''}`}
            onClick={(e) => {
              e.stopPropagation();
              handleSelect('REGION_B_HEALTH');
            }}
            transform="translate(254, 42)"
          >
            <rect
              width="210"
              height="74"
              rx="6"
              fill="#182133"
              stroke={isSelected(['REGION_B_HEALTH']) ? '#0ea5e9' : '#2a3752'}
              strokeWidth={isSelected(['REGION_B_HEALTH']) ? '2' : '1'}
            />
            <text x="12" y="22" fill="#f1f5f9" fontSize="11" fontWeight="600">Health Agent</text>
            <text x="12" y="42" fill="#94a3b8" fontSize="10" fontFamily="JetBrains Mono, monospace">
              Synthetic Prober (2s tick)
            </text>
            <text x="12" y="60" fill="#10b981" fontSize="10" fontWeight="600" fontFamily="JetBrains Mono, monospace">
              HEARTBEAT OK (32ms WAN)
            </text>
          </g>

          {/* 3. Standby Database */}
          <g
            className={`interactive-node ${isSelected(['STANDBY_DB', 'REGION_B_DB']) ? 'node-selected' : ''}`}
            onClick={(e) => {
              e.stopPropagation();
              handleSelect('STANDBY_DB');
            }}
            transform="translate(18, 144)"
          >
            <rect
              width="446"
              height="136"
              rx="6"
              fill="#101624"
              stroke={
                isBActive
                  ? '#10b981'
                  : isSelected(['STANDBY_DB', 'REGION_B_DB'])
                  ? '#0ea5e9'
                  : '#2a3752'
              }
              strokeWidth={isSelected(['STANDBY_DB', 'REGION_B_DB']) || isBActive ? '2.5' : '1.5'}
            />
            <text x="16" y="26" fill="#f8fafc" fontSize="12" fontWeight="700">
              {isBActive ? 'Promoted Primary Database' : 'Standby Database (Read Replica)'}
            </text>

            {/* Access Mode Tag */}
            <g transform="translate(300, 12)">
              <rect
                width="130"
                height="22"
                rx="4"
                fill={
                  regionB.acceptsWrites
                    ? 'rgba(16, 185, 129, 0.2)'
                    : 'rgba(14, 165, 233, 0.2)'
                }
              />
              <text x="65" y="15" textAnchor="middle" fill={
                regionB.acceptsWrites ? '#10b981' : '#38bdf8'
              } fontSize="10" fontWeight="700" fontFamily="JetBrains Mono, monospace">
                {regionB.acceptsWrites ? 'READ_WRITE (Promoted)' : 'READ_ONLY (Replica)'}
              </text>
            </g>

            <text x="16" y="54" fill="#94a3b8" fontSize="10" fontFamily="JetBrains Mono, monospace">
              Role: {isBActive ? 'PRIMARY' : 'STANDBY'} • Generation Epoch: #{standbyDb.generationId}
            </text>
            <text x="16" y="74" fill={replication.lagSeconds > config.acceptableReplicationLagSec ? '#f59e0b' : '#38bdf8'} fontSize="10" fontFamily="JetBrains Mono, monospace">
              Replication Lag: {replication.lagSeconds.toFixed(1)}s ({Math.round(replication.lagSeconds * 1000)}ms) • {replication.status}
            </text>
            <text x="16" y="94" fill="#64748b" fontSize="10" fontFamily="JetBrains Mono, monospace">
              Active IOPS: {standbyDb.iops.toLocaleString()} • Storage: {standbyDb.storageGb} GB
            </text>
            <text x="16" y="114" fill="#64748b" fontSize="9" fontFamily="JetBrains Mono, monospace">
              WAL Receiver: {replication.status === 'STREAMING' ? 'CONNECTED' : replication.status} • Buffer: {(replication.pendingBytes / 1024).toFixed(1)} KB
            </text>
          </g>
        </g>

        {/* ============================================================== */}
        {/* CROSS-REGION WAL REPLICATION BADGE                             */}
        {/* ============================================================== */}
        <g
          className={`interactive-node ${isSelected(['REPLICATION_LINK', 'REPLICATION']) ? 'node-selected' : ''}`}
          onClick={() => handleSelect('REPLICATION_LINK')}
          transform="translate(508, 416)"
          cursor="pointer"
        >
          <rect
            width="84"
            height="48"
            rx="4"
            fill="#101522"
            stroke={repFlowColor}
            strokeWidth="1.5"
          />
          <text x="42" y="20" textAnchor="middle" fill="#f8fafc" fontSize="10" fontWeight="700" fontFamily="Inter, sans-serif">
            {replication.status === 'SEVERED'
              ? 'SEVERED'
              : replication.status === 'DEGRADED'
              ? 'LAG CRIT'
              : 'ASYNC WAL'}
          </text>
          <text x="42" y="38" textAnchor="middle" fill={repFlowColor} fontSize="9" fontWeight="600" fontFamily="JetBrains Mono, monospace">
            {replication.lagSeconds.toFixed(1)}s lag
          </text>
        </g>

        {/* ============================================================== */}
        {/* BOTTOM CONTROL-PLANE CONTAINER: FAILOVER CONTROLLER            */}
        {/* ============================================================== */}
        <g
          className={`interactive-node ${isSelected(['CONTROLLER']) ? 'node-selected' : ''}`}
          onClick={() => handleSelect('CONTROLLER')}
          transform="translate(30, 560)"
          cursor="pointer"
        >
          {/* Outer Boundary */}
          <rect
            width="1040"
            height="290"
            rx="8"
            fill="url(#controllerGrad)"
            stroke={
              isSelected(['CONTROLLER'])
                ? '#0ea5e9'
                : isSequenceInProgress
                ? '#f59e0b'
                : '#232d42'
            }
            strokeWidth={isSelected(['CONTROLLER']) ? '2' : '1'}
          />

          {/* Control Plane Header Bar */}
          <text x="24" y="28" fill="#f8fafc" fontSize="13" fontWeight="700" fontFamily="Inter, sans-serif">
            FAILOVER CONTROLLER — DISTRIBUTED CONTROL PLANE
          </text>

          {/* Phase Badge & Simulation Clock */}
          <g transform="translate(680, 12)">
            <rect
              width="336"
              height="24"
              rx="4"
              fill="rgba(14, 165, 233, 0.15)"
              stroke="#0ea5e9"
            />
            <text x="168" y="16" textAnchor="middle" fill="#38bdf8" fontSize="10" fontWeight="700" fontFamily="JetBrains Mono, monospace">
              PHASE: {controllerState} • CLOCK: {formatSimTime(simulatedTimeSeconds)}
            </text>
          </g>

          {/* 6 Control Plane Submodules (3x2 Grid) */}

          {/* 1. Health Monitor */}
          <g
            className={`interactive-node ${isSelected(['CONTROLLER_HEALTH_MONITOR']) ? 'node-selected' : ''}`}
            onClick={(e) => {
              e.stopPropagation();
              handleSelect('CONTROLLER_HEALTH_MONITOR');
            }}
            transform="translate(20, 45)"
          >
            <rect
              width="316"
              height="100"
              rx="6"
              fill="url(#moduleGrad)"
              stroke={isSelected(['CONTROLLER_HEALTH_MONITOR']) ? '#0ea5e9' : isASuspected ? '#f59e0b' : '#232d42'}
              strokeWidth={isSelected(['CONTROLLER_HEALTH_MONITOR']) ? '2' : '1'}
            />
            <text x="14" y="24" fill="#f8fafc" fontSize="11" fontWeight="700">
              1. Health Monitor
            </text>
            <text x="14" y="44" fill="#94a3b8" fontSize="10" fontFamily="JetBrains Mono, monospace">
              Role: Regional Heartbeat Collector
            </text>
            <text x="14" y="64" fill={isAOutage ? '#ef4444' : isASuspected ? '#fbbf24' : '#10b981'} fontSize="10" fontFamily="JetBrains Mono, monospace">
              Consecutive Fails: {consecutiveFailures} / {config.failureThresholdConsecutive} Probes
            </text>
            <text x="14" y="84" fill="#64748b" fontSize="9" fontFamily="JetBrains Mono, monospace">
              Interval: {config.healthCheckIntervalSec}s • Heartbeat Protocol: REST/gRPC
            </text>
          </g>

          {/* 2. Quorum and Decision Engine */}
          <g
            className={`interactive-node ${isSelected(['CONTROLLER_QUORUM', 'QUORUM']) ? 'node-selected' : ''}`}
            onClick={(e) => {
              e.stopPropagation();
              handleSelect('CONTROLLER_QUORUM');
            }}
            transform="translate(362, 45)"
          >
            <rect
              width="316"
              height="100"
              rx="6"
              fill="url(#moduleGrad)"
              stroke={isSelected(['CONTROLLER_QUORUM', 'QUORUM']) ? '#0ea5e9' : '#232d42'}
              strokeWidth={isSelected(['CONTROLLER_QUORUM', 'QUORUM']) ? '2' : '1'}
            />
            <text x="14" y="24" fill="#f8fafc" fontSize="11" fontWeight="700">
              2. Quorum and Decision Engine
            </text>
            <text x="14" y="44" fill="#94a3b8" fontSize="10" fontFamily="JetBrains Mono, monospace">
              Role: Split-Brain Consensus Arbiter
            </text>
            <text x="14" y="64" fill={quorum.consensusReached ? '#10b981' : '#f59e0b'} fontSize="10" fontFamily="JetBrains Mono, monospace">
              Consensus: {quorum.consensusReached ? 'MAJORITY REACHED' : 'VOTES SPLIT'} (2/3 Req)
            </text>
            <text x="14" y="84" fill="#64748b" fontSize="9" fontFamily="JetBrains Mono, monospace">
              Voters: Mumbai, Singapore, Zurich (N/2 + 1)
            </text>
          </g>

          {/* 3. Split-Brain Prevention / Lease Manager */}
          <g
            className={`interactive-node ${isSelected(['CONTROLLER_LEASE', 'LEASE_FENCE', 'FENCING']) ? 'node-selected' : ''}`}
            onClick={(e) => {
              e.stopPropagation();
              handleSelect('CONTROLLER_LEASE');
            }}
            transform="translate(704, 45)"
          >
            <rect
              width="316"
              height="100"
              rx="6"
              fill="url(#moduleGrad)"
              stroke={isSelected(['CONTROLLER_LEASE', 'LEASE_FENCE', 'FENCING']) ? '#0ea5e9' : '#232d42'}
              strokeWidth={isSelected(['CONTROLLER_LEASE', 'LEASE_FENCE', 'FENCING']) ? '2' : '1'}
            />
            <text x="14" y="24" fill="#f8fafc" fontSize="11" fontWeight="700">
              3. Lease & Fencing Manager
            </text>
            <text x="14" y="44" fill="#94a3b8" fontSize="10" fontFamily="JetBrains Mono, monospace">
              Role: Martin Kleppmann Fencing Tokens
            </text>
            <text x="14" y="64" fill="#38bdf8" fontSize="10" fontFamily="JetBrains Mono, monospace">
              Current Epoch: #{leaseFence.generationId} • Holder: {leaseFence.currentHolder || 'None'}
            </text>
            <text x="14" y="84" fill={leaseFence.fenceStatus === 'HARD_FENCED' ? '#ef4444' : '#10b981'} fontSize="9" fontFamily="JetBrains Mono, monospace">
              Lock Status: {leaseFence.fenceStatus} • STONITH Guard Active
            </text>
          </g>

          {/* 4. Failover Executor */}
          <g
            className={`interactive-node ${isSelected(['CONTROLLER_EXECUTOR']) ? 'node-selected' : ''}`}
            onClick={(e) => {
              e.stopPropagation();
              handleSelect('CONTROLLER_EXECUTOR');
            }}
            transform="translate(20, 165)"
          >
            <rect
              width="316"
              height="105"
              rx="6"
              fill="url(#moduleGrad)"
              stroke={isSelected(['CONTROLLER_EXECUTOR']) ? '#0ea5e9' : isSequenceInProgress ? '#f59e0b' : '#232d42'}
              strokeWidth={isSelected(['CONTROLLER_EXECUTOR']) ? '2' : '1'}
            />
            <text x="14" y="24" fill="#f8fafc" fontSize="11" fontWeight="700">
              4. Failover Executor
            </text>
            <text x="14" y="44" fill="#94a3b8" fontSize="10" fontFamily="JetBrains Mono, monospace">
              Role: Multi-Step State Machine Pipeline
            </text>
            <text x="14" y="64" fill={isSequenceInProgress ? '#fbbf24' : '#38bdf8'} fontSize="10" fontFamily="JetBrains Mono, monospace">
              Pipeline: Fence → Promote → Cutover → Verify
            </text>
            <text x="14" y="84" fill="#64748b" fontSize="9" fontFamily="JetBrains Mono, monospace">
              Execution: {isSequenceInProgress ? 'ACTIVE CUTOVER IN PROGRESS' : 'IDLE / NOMINAL MONITORING'}
            </text>
          </g>

          {/* 5. Metadata Store */}
          <g
            className={`interactive-node ${isSelected(['CONTROLLER_METADATA']) ? 'node-selected' : ''}`}
            onClick={(e) => {
              e.stopPropagation();
              handleSelect('CONTROLLER_METADATA');
            }}
            transform="translate(362, 165)"
          >
            <rect
              width="316"
              height="105"
              rx="6"
              fill="url(#moduleGrad)"
              stroke={isSelected(['CONTROLLER_METADATA']) ? '#0ea5e9' : '#232d42'}
              strokeWidth={isSelected(['CONTROLLER_METADATA']) ? '2' : '1'}
            />
            <text x="14" y="24" fill="#f8fafc" fontSize="11" fontWeight="700">
              5. Metadata Store
            </text>
            <text x="14" y="44" fill="#94a3b8" fontSize="10" fontFamily="JetBrains Mono, monospace">
              Role: Authoritative Cluster Topology & Routing
            </text>
            <text x="14" y="64" fill="#cbd5e1" fontSize="10" fontFamily="JetBrains Mono, monospace">
              Active Route: {dns.activeDnsTarget} • DNS TTL: {dns.ttlSeconds}s
            </text>
            <text x="14" y="84" fill="#64748b" fontSize="9" fontFamily="JetBrains Mono, monospace">
              Consistency: Raft-backed Strict Linearizability
            </text>
          </g>

          {/* 6. Audit and Event Log */}
          <g
            className={`interactive-node ${isSelected(['CONTROLLER_AUDIT']) ? 'node-selected' : ''}`}
            onClick={(e) => {
              e.stopPropagation();
              handleSelect('CONTROLLER_AUDIT');
            }}
            transform="translate(704, 165)"
          >
            <rect
              width="316"
              height="105"
              rx="6"
              fill="url(#moduleGrad)"
              stroke={isSelected(['CONTROLLER_AUDIT']) ? '#0ea5e9' : '#232d42'}
              strokeWidth={isSelected(['CONTROLLER_AUDIT']) ? '2' : '1'}
            />
            <text x="14" y="24" fill="#f8fafc" fontSize="11" fontWeight="700">
              6. Audit and Event Log
            </text>
            <text x="14" y="44" fill="#94a3b8" fontSize="10" fontFamily="JetBrains Mono, monospace">
              Role: Tamper-Evident Chronological Journal
            </text>
            <text x="14" y="64" fill="#cbd5e1" fontSize="10" fontFamily="JetBrains Mono, monospace">
              Total Logged Entries: {eventHistory.length} Transitions
            </text>
            <text x="14" y="84" fill="#64748b" fontSize="9" fontFamily="JetBrains Mono, monospace">
              Latest: {eventHistory[0] ? (eventHistory[0].transition || eventHistory[0].reason).slice(0, 36) : 'Cluster nominal'}
            </text>
          </g>
        </g>
      </svg>

      {/* Educational Simulated Representation Note */}
      <div className="architecture-sim-notice font-mono text-xs text-muted">
        <span className="notice-highlight">Simulated Representation Note:</span> DNS propagation, WAL streaming replication, fencing epoch tokens, and regional cloud infrastructure are simulated models created for academic analysis in System Design & Software Systems Development (Case Study 23).
      </div>
    </div>
  );
};
