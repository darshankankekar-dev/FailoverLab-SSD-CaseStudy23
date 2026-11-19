/**
 * FailoverLab Controller and Gateway Typed HTTP Client
 * Connects the React application to the Python/FastAPI control plane
 * and the Dynamic Ingress Gateway via same-origin paths or configured URLs.
 */

export type RegionIdType = 'region-a' | 'region-b' | 'region-c' | 'region-d' | 'region-e';

export interface QuorumVoterDto {
  id: string;
  name: string;
  location: string;
  vote: 'PRIMARY_OUTAGE' | 'PRIMARY_HEALTHY' | 'ABSTAIN';
  latency_ms: number;
}

export interface RegionDto {
  id: RegionIdType;
  name: string;
  cloud_zone: string;
  role: 'ACTIVE' | 'STANDBY';
  health: 'HEALTHY' | 'DEGRADED' | 'DOWN';
  status: 'healthy' | 'degraded' | 'failed' | 'fenced';
  accepts_writes: boolean;
  ingress_traffic_percent: number;
  ingress_rps: number;
  app_servers_healthy: number;
  app_servers_total: number;
  active_connections: number;
  iops: number;
  fencing_epoch: number;
  is_fenced: boolean;
  applied_sequence?: number;
  replication_lag_seconds?: number;
  latency_ms?: number;
}

export interface PolicyDto {
  health_check_interval_sec: number;
  failure_threshold_consecutive: number;
  quorum_size: number;
  majority_required: number;
  acceptable_replication_lag_sec: number;
  fencing_duration_sec: number;
  route_propagation_sec: number;
  route_verification_sec: number;
  auto_failover_enabled: boolean;
}

export interface DestinationReplicationDto {
  region_id: string;
  status: string;
  lag_seconds: number;
  lag_ms: number;
  applied_sequence: number;
  source_highest_sequence: number;
  sequence_lag?: number;
  time_lag_seconds?: number;
  retry_count: number;
  consecutive_failures: number;
  is_simulated_lag?: boolean;
  injected_delay_sec?: number;
}

export interface ReplicationStateDto {
  status: 'STREAMING' | 'DEGRADED' | 'SEVERED' | 'REVERSED' | 'SYNCED';
  lag_seconds: number;
  lag_ms: number;
  bandwidth_mbps: number;
  packet_loss_percent: number;
  pending_bytes: number;
  bytes_transferred: number;
  mode: string;
  destinations?: Record<string, DestinationReplicationDto>;
}

export interface RouteStateDto {
  active_target: RegionIdType;
  dns_ttl_seconds: number;
  propagation_percent: number;
  verification_status: 'UNVERIFIED' | 'VERIFYING' | 'VERIFIED' | 'FAILED';
}

export interface TelemetryMetricsDto {
  uptime_seconds: number;
  total_client_rps: number;
  overall_success_rate: number;
  client_error_rate: number;
  p95_latency_ms: number;
  total_failovers_count: number;
  last_failover_duration_ms: number | null;
  estimated_rpo_loss_tx: number;
}

export interface ControllerStateDto {
  controller_state: string;
  active_region: RegionIdType;
  fencing_epoch: number;
  simulated_time_seconds: number;
  consecutive_failures: number;
  blocked_reason: string | null;
  blocked_at_state: string | null;
  is_sequence_in_progress: boolean;
  route_retry_count: number;
  persisted_intent: string | null;
  is_paused_interrupted: boolean;
  region_a: RegionDto;
  region_b: RegionDto;
  region_c?: RegionDto | null;
  region_d?: RegionDto | null;
  region_e?: RegionDto | null;
  regions?: RegionDto[];
  policy: PolicyDto;
  replication: ReplicationStateDto;
  route: RouteStateDto;
  voters: QuorumVoterDto[];
  telemetry: TelemetryMetricsDto;
}

export interface GateEvaluationResultDto {
  gate_name: string;
  passed: boolean;
  reason: string;
  details?: Record<string, any>;
}

export interface TransitionResponseDto {
  status: 'SUCCESS' | 'BLOCKED' | 'FAILED' | 'IN_PROGRESS';
  previous_state: string;
  current_state: string;
  fencing_epoch: number;
  message: string;
  blocked_reason?: string | null;
  gate_results: GateEvaluationResultDto[];
}

export interface FailoverRequestPayload {
  force?: boolean;
  target_region?: RegionIdType | 'auto' | string;
  reason?: string;
}

export interface FailbackRequestPayload {
  operator_id: string;
  confirmation: boolean;
  target_region?: RegionIdType | string;
  reason?: string;
}

export interface TrafficEvent {
  id: string;
  timestamp: string;
  request_id: string;
  method: string;
  endpoint: string;
  client_region: string;
  served_region: string;
  request_type: string;
  rate_limiter_decision: 'accepted' | 'rejected' | 'delayed';
  status_code: number;
  duration_ms: number;
  simulated_wan_delay_ms: number;
  queue_wait_time_ms: number;
}

export interface TrafficStatusDto {
  mode: 'OFF' | 'TOKEN_BUCKET' | 'LEAKY_BUCKET';
  token_bucket: {
    capacity: number;
    refill_rate: number;
    tokens_remaining: number;
    accepted_requests: number;
    rejected_requests: number;
    total_refilled: number;
    active_client_buckets: number;
  };
  leaky_bucket: {
    queue_capacity: number;
    drain_rate: number;
    current_queue_depth: number;
    processed_requests: number;
    overflow_requests: number;
    average_wait_time_ms: number;
    last_wait_time_ms: number;
  };
  common: {
    total_requests: number;
    accepted_requests: number;
    throttled_requests: number;
    server_failures: number;
    average_latency_ms: number;
    p95_latency_ms: number;
  };
}

export interface RecordItemDto {
  id: string;
  key: string;
  value: Record<string, any>;
  version: number;
  fencing_epoch: number;
  created_at: string;
  updated_at: string;
}

export interface TrafficSummaryDto {
  current_ingress_bytes_per_sec: number;
  current_egress_bytes_per_sec: number;
  cumulative_ingress_bytes: number;
  cumulative_egress_bytes: number;
  upstream_ingress_bytes_per_sec: number;
  upstream_egress_bytes_per_sec: number;
  request_rate: number;
  total_requests: number;
  status_2xx: number;
  status_3xx: number;
  status_4xx: number;
  status_5xx: number;
  rate_limited_429: number;
  latency_avg_ms: number;
  latency_p50_ms: number;
  latency_p95_ms: number;
  latency_p99_ms: number;
  last_received_timestamp: string | null;
  telemetry_freshness: 'FRESH' | 'STALE' | 'UNAVAILABLE' | 'PENDING';
  telemetry_age_seconds: number | null;
  is_available: boolean;
  measurement_source: string;
  measurement_unit: string;
  measurement_type: string;
  note: string;
}

export interface TrafficTimeseriesPointDto {
  timestamp: string;
  client_ingress_bytes: number;
  client_egress_bytes: number;
  client_ingress_rate: number;
  client_egress_rate: number;
  upstream_ingress_rate: number;
  upstream_egress_rate: number;
  request_rate: number;
  error_rate: number;
  status_2xx: number;
  status_4xx: number;
  status_5xx: number;
  latency_p95_ms: number;
}

export interface TrafficTimeseriesResponseDto {
  time_range_seconds: number;
  step_seconds: number;
  point_count: number;
  points: TrafficTimeseriesPointDto[];
}

export interface RegionalTrafficItemDto {
  region_id: string;
  region_name: string;
  cloud_zone: string;
  requests_total: number;
  request_rate: number;
  upstream_request_bytes: number;
  upstream_response_bytes: number;
  upstream_ingress_rate: number;
  upstream_egress_rate: number;
  status_2xx: number;
  status_3xx: number;
  status_4xx: number;
  status_5xx: number;
  failed_requests: number;
  timeouts: number;
  latency_avg_ms: number;
}

export interface RegionalTrafficResponseDto {
  timestamp: string;
  regions: Record<string, RegionalTrafficItemDto>;
}

export interface TrafficEventItemDto {
  id: string;
  request_id: string;
  timestamp: string;
  method: string;
  endpoint: string;
  client_region: string;
  served_region: string;
  request_type: string;
  rate_limiter_decision: string;
  status_code: number;
  duration_ms: number;
  request_payload_bytes: number;
  response_payload_bytes: number;
  request_category: string;
  upstream_region?: string | null;
  upstream_request_bytes: number;
  upstream_response_bytes: number;
  upstream_duration_ms: number;
  traffic_source: string;
  is_replay: boolean;
}

export interface TrafficEventsResponseDto {
  total: number;
  page: number;
  page_size: number;
  events: TrafficEventItemDto[];
}

export interface AuditEventDto {
  id: string;
  simulated_time_seconds: number;
  wall_clock_timestamp: string;
  severity: 'INFO' | 'WARNING' | 'CRITICAL';
  subsystem: string;
  transition: string;
  reason: string;
  details?: Record<string, any>;
  metadata_json?: Record<string, any>;
}

export class ControllerClient {
  private controllerUrl: string;
  private gatewayUrl: string;

  constructor() {
    // In browser, prefer empty prefix to leverage same-origin proxy (Vite / Nginx)
    const isBrowser = typeof window !== 'undefined';
    const envController = isBrowser ? (window as any).__CONTROLLER_URL__ : undefined;
    const envGateway = isBrowser ? (window as any).__GATEWAY_URL__ : undefined;

    this.controllerUrl = envController ?? (isBrowser ? '' : 'http://localhost:8000');
    this.gatewayUrl = envGateway ?? (isBrowser ? '' : 'http://localhost:8080');
  }

  public setControllerUrl(url: string) {
    this.controllerUrl = url.replace(/\/$/, '');
  }

  public getControllerUrl(): string {
    return this.controllerUrl || '(same-origin)';
  }

  public getAdminHeaders(): Record<string, string> {
    const isBrowser = typeof window !== 'undefined';
    const secret = isBrowser
      ? (window as any).__ADMIN_SECRET__ || localStorage.getItem('FAILOVERLAB_ADMIN_SECRET') || ''
      : '';
    return secret ? { 'X-Admin-Secret': secret, 'X-Internal-Secret': secret } : {};
  }

  private async fetchWithTimeout(url: string, options: RequestInit = {}, timeoutMs = 3000): Promise<Response> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      return await fetch(url, { ...options, signal: controller.signal });
    } finally {
      clearTimeout(timer);
    }
  }

  public async checkHealth(): Promise<{ controller: boolean; gateway: boolean }> {
    // 1. Try same-origin first (Vite proxy / Nginx reverse proxy)
    try {
      const res = await this.fetchWithTimeout('/health/live', {}, 1000);
      if (res.ok) {
        this.controllerUrl = '';
        this.gatewayUrl = '';
        return { controller: true, gateway: true };
      }
    } catch {
      // not on same-origin proxy, fallback to explicit URLs
    }

    let cOk = false;
    let gOk = false;

    try {
      const cRes = await this.fetchWithTimeout('http://localhost:8000/health/live', {}, 1200);
      cOk = cRes.ok;
      if (cOk) this.controllerUrl = 'http://localhost:8000';
    } catch {
      cOk = false;
    }

    try {
      const gRes = await this.fetchWithTimeout('http://localhost:8080/health/live', {}, 1200);
      gOk = gRes.ok;
      if (gOk) this.gatewayUrl = 'http://localhost:8080';
    } catch {
      gOk = false;
    }

    return { controller: cOk, gateway: gOk };
  }

  public async fetchState(): Promise<ControllerStateDto | null> {
    try {
      const base = this.controllerUrl;
      const res = await this.fetchWithTimeout(`${base}/api/v1/state`, {}, 2500);
      if (!res.ok) return null;
      return await res.json();
    } catch {
      return null;
    }
  }

  public async triggerFailover(params?: FailoverRequestPayload): Promise<TransitionResponseDto> {
    const base = this.controllerUrl;
    const payload: FailoverRequestPayload = {
      force: params?.force ?? false,
      target_region: params?.target_region ?? 'region-b',
      reason: params?.reason ?? 'Manual failover trigger from UI',
    };
    const res = await this.fetchWithTimeout(`${base}/api/v1/failover`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...this.getAdminHeaders() },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: `HTTP ${res.status} error` }));
      throw new Error(err.detail || err.message || `Failover request rejected (HTTP ${res.status})`);
    }
    return await res.json();
  }

  public async triggerFailback(params?: Partial<FailbackRequestPayload>): Promise<TransitionResponseDto> {
    const base = this.controllerUrl;
    const payload: FailbackRequestPayload = {
      operator_id: params?.operator_id ?? 'operator-ui',
      confirmation: params?.confirmation ?? true,
      target_region: params?.target_region ?? 'region-a',
      reason: params?.reason ?? 'Guarded failback authorized by operator from UI',
    };
    const res = await this.fetchWithTimeout(`${base}/api/v1/failback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...this.getAdminHeaders() },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: `HTTP ${res.status} error` }));
      throw new Error(err.detail || err.message || `Failback request rejected (HTTP ${res.status})`);
    }
    return await res.json();
  }

  public async resetSystem(preservePolicy = false): Promise<ControllerStateDto> {
    const base = this.controllerUrl;
    const res = await this.fetchWithTimeout(`${base}/api/v1/reset`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...this.getAdminHeaders() },
      body: JSON.stringify({ preserve_policy: preservePolicy }),
    });
    if (!res.ok) {
      throw new Error(`Reset failed (HTTP ${res.status})`);
    }
    return await res.json();
  }

  public async updatePolicy(partialPolicy: Partial<PolicyDto>): Promise<PolicyDto> {
    const base = this.controllerUrl;
    const res = await this.fetchWithTimeout(`${base}/api/v1/policy`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...this.getAdminHeaders() },
      body: JSON.stringify(partialPolicy),
    });
    if (!res.ok) {
      throw new Error(`Policy update failed (HTTP ${res.status})`);
    }
    return await res.json();
  }

  public async injectPrimaryOutage(): Promise<ControllerStateDto> {
    const base = this.controllerUrl;
    const res = await this.fetchWithTimeout(`${base}/internal/chaos/primary-outage`, {
      method: 'POST',
      headers: this.getAdminHeaders(),
    });
    if (!res.ok) throw new Error(`Inject primary outage failed (HTTP ${res.status})`);
    return await res.json();
  }

  public async recoverPrimary(): Promise<ControllerStateDto> {
    const base = this.controllerUrl;
    const res = await this.fetchWithTimeout(`${base}/internal/chaos/recover-primary`, {
      method: 'POST',
      headers: this.getAdminHeaders(),
    });
    if (!res.ok) throw new Error(`Recover primary failed (HTTP ${res.status})`);
    return await res.json();
  }

  public async injectPartition(): Promise<ControllerStateDto> {
    const base = this.controllerUrl;
    const res = await this.fetchWithTimeout(`${base}/internal/chaos/partition`, {
      method: 'POST',
      headers: this.getAdminHeaders(),
    });
    if (!res.ok) throw new Error(`Inject partition failed (HTTP ${res.status})`);
    return await res.json();
  }

  public async injectReplicationLag(lagSeconds: number): Promise<ControllerStateDto> {
    const base = this.controllerUrl;
    const res = await this.fetchWithTimeout(`${base}/internal/chaos/replication-lag?lag_seconds=${lagSeconds}`, {
      method: 'POST',
      headers: this.getAdminHeaders(),
    });
    if (!res.ok) throw new Error(`Inject replication lag failed (HTTP ${res.status})`);
    return await res.json();
  }

  // Regional simulation chaos controls
  public async setRegionalHealth(regionId: string, health: string): Promise<ControllerStateDto> {
    const base = this.controllerUrl;
    const res = await this.fetchWithTimeout(`${base}/internal/chaos/regional-health?region_id=${encodeURIComponent(regionId)}&health=${encodeURIComponent(health)}`, {
      method: 'POST',
      headers: this.getAdminHeaders(),
    });
    if (!res.ok) throw new Error(`Set regional health failed (HTTP ${res.status})`);
    return await res.json();
  }

  public async setRegionalLag(regionId: string, lagSeconds: number): Promise<ControllerStateDto> {
    const base = this.controllerUrl;
    const res = await this.fetchWithTimeout(`${base}/internal/chaos/regional-lag?region_id=${encodeURIComponent(regionId)}&lag_seconds=${lagSeconds}`, {
      method: 'POST',
      headers: this.getAdminHeaders(),
    });
    if (!res.ok) throw new Error(`Set regional lag failed (HTTP ${res.status})`);
    return await res.json();
  }

  public async setRegionalSequence(regionId: string, appliedSequence: number): Promise<ControllerStateDto> {
    const base = this.controllerUrl;
    const res = await this.fetchWithTimeout(`${base}/internal/chaos/regional-sequence?region_id=${encodeURIComponent(regionId)}&applied_sequence=${appliedSequence}`, {
      method: 'POST',
      headers: this.getAdminHeaders(),
    });
    if (!res.ok) throw new Error(`Set regional sequence failed (HTTP ${res.status})`);
    return await res.json();
  }

  public async setRegionalWanLatency(regionId: string, latencyMs: number): Promise<ControllerStateDto> {
    const base = this.controllerUrl;
    const res = await this.fetchWithTimeout(`${base}/internal/chaos/regional-wan-latency?region_id=${encodeURIComponent(regionId)}&latency_ms=${latencyMs}`, {
      method: 'POST',
      headers: this.getAdminHeaders(),
    });
    if (!res.ok) throw new Error(`Set regional WAN latency failed (HTTP ${res.status})`);
    return await res.json();
  }

  public async pauseReplication(destination?: string): Promise<ControllerStateDto> {
    const base = this.controllerUrl;
    const query = destination ? `?destination=${encodeURIComponent(destination)}` : '';
    const res = await this.fetchWithTimeout(`${base}/internal/chaos/replication-pause${query}`, {
      method: 'POST',
      headers: this.getAdminHeaders(),
    });
    if (!res.ok) throw new Error(`Pause replication failed (HTTP ${res.status})`);
    return await res.json();
  }

  public async resumeReplication(destination?: string): Promise<ControllerStateDto> {
    const base = this.controllerUrl;
    const query = destination ? `?destination=${encodeURIComponent(destination)}` : '';
    const res = await this.fetchWithTimeout(`${base}/internal/chaos/replication-resume${query}`, {
      method: 'POST',
      headers: this.getAdminHeaders(),
    });
    if (!res.ok) throw new Error(`Resume replication failed (HTTP ${res.status})`);
    return await res.json();
  }

  public async resetRegional(regionId: string): Promise<ControllerStateDto> {
    const base = this.controllerUrl;
    const res = await this.fetchWithTimeout(`${base}/internal/chaos/reset-regional?region_id=${encodeURIComponent(regionId)}`, {
      method: 'POST',
      headers: this.getAdminHeaders(),
    });
    if (!res.ok) throw new Error(`Reset regional failed (HTTP ${res.status})`);
    return await res.json();
  }

  // Traffic management & real-time monitoring
  public async fetchTrafficStatus(): Promise<TrafficStatusDto | null> {
    try {
      const base = this.gatewayUrl;
      const res = await this.fetchWithTimeout(`${base}/api/v1/traffic/status`, {}, 2500);
      if (!res.ok) return null;
      return await res.json();
    } catch {
      return null;
    }
  }

  public async updateTrafficConfig(config: {
    mode?: string;
    token_capacity?: number;
    token_refill_rate?: number;
    leaky_capacity?: number;
    leaky_drain_rate?: number;
  }): Promise<any> {
    const base = this.gatewayUrl;
    const res = await this.fetchWithTimeout(`${base}/api/v1/traffic/config`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    });
    if (!res.ok) throw new Error(`Update traffic config failed (HTTP ${res.status})`);
    return await res.json();
  }

  public async resetTrafficState(): Promise<any> {
    const base = this.gatewayUrl;
    const res = await this.fetchWithTimeout(`${base}/api/v1/traffic/reset`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    if (!res.ok) throw new Error(`Reset traffic state failed (HTTP ${res.status})`);
    return await res.json();
  }

  public async fetchTrafficHistory(limit = 100): Promise<TrafficEvent[]> {
    try {
      const base = this.gatewayUrl;
      const res = await this.fetchWithTimeout(`${base}/api/v1/traffic/history?limit=${limit}`, {}, 3000);
      if (!res.ok) return [];
      const data = await res.json();
      return data.events || [];
    } catch {
      return [];
    }
  }

  public subscribeTrafficEvents(onEvent: (event: TrafficEvent) => void): () => void {
    if (typeof window === 'undefined' || typeof EventSource === 'undefined') {
      return () => {};
    }
    const base = this.gatewayUrl;
    const url = `${base}/api/v1/traffic/events`;
    let es: EventSource | null = null;
    let isClosed = false;

    try {
      es = new EventSource(url);
      es.onmessage = (e) => {
        if (!e.data || isClosed) return;
        try {
          const parsed = JSON.parse(e.data);
          if (parsed && parsed.request_id) {
            onEvent(parsed);
          }
        } catch {
          // ignore parse errors for ping heartbeats
        }
      };
      es.onerror = () => {
        // Fallback or retry handled by browser EventSource
      };
    } catch {
      // EventSource failed to instantiate
    }

    return () => {
      isClosed = true;
      if (es) {
        es.close();
        es = null;
      }
    };
  }

  // Gateway data proxying
  public async getRecords(): Promise<RecordItemDto[]> {
    try {
      const base = this.gatewayUrl;
      const res = await this.fetchWithTimeout(`${base}/api/records`, {}, 3000);
      if (!res.ok) return [];
      return await res.json();
    } catch {
      return [];
    }
  }

  public async writeRecord(key: string, value: Record<string, any>, epoch?: number): Promise<{ ok: boolean; status: number; data: any }> {
    const base = this.gatewayUrl;
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (epoch !== undefined) {
      headers['X-Fencing-Epoch'] = String(epoch);
    }
    const res = await this.fetchWithTimeout(`${base}/api/records`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ key, value, fencing_epoch: epoch }),
    });
    const data = await res.json().catch(() => ({}));
    return { ok: res.ok, status: res.status, data };
  }

  // Controller Real-Time Traffic Telemetry APIs
  public async fetchTrafficSummary(): Promise<TrafficSummaryDto | null> {
    try {
      const base = this.controllerUrl;
      const res = await this.fetchWithTimeout(`${base}/api/v1/traffic/summary`, {}, 2500);
      if (!res.ok) return null;
      return await res.json();
    } catch {
      return null;
    }
  }

  public async fetchTrafficTimeseries(rangeSeconds = 300, stepSeconds = 1): Promise<TrafficTimeseriesResponseDto | null> {
    try {
      const base = this.controllerUrl;
      const res = await this.fetchWithTimeout(
        `${base}/api/v1/traffic/timeseries?time_range_seconds=${rangeSeconds}&step_seconds=${stepSeconds}`,
        {},
        3000
      );
      if (!res.ok) return null;
      return await res.json();
    } catch {
      return null;
    }
  }

  public async fetchRegionalTraffic(): Promise<RegionalTrafficResponseDto | null> {
    try {
      const base = this.controllerUrl;
      const res = await this.fetchWithTimeout(`${base}/api/v1/traffic/regions`, {}, 2500);
      if (!res.ok) return null;
      return await res.json();
    } catch {
      return null;
    }
  }

  public async fetchTrafficEvents(
    page = 1,
    pageSize = 20,
    filters?: {
      trafficSource?: string;
      clientRegion?: string;
      servedRegion?: string;
      statusCode?: number;
      requestType?: string;
      region?: string;
      method?: string;
    }
  ): Promise<TrafficEventsResponseDto | null> {
    try {
      const base = this.controllerUrl;
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
      });
      if (filters?.trafficSource && filters.trafficSource !== 'ALL') {
        params.append('traffic_source', filters.trafficSource);
      }
      if (filters?.clientRegion && filters.clientRegion !== 'ALL') {
        params.append('client_region', filters.clientRegion);
      }
      if (filters?.servedRegion && filters.servedRegion !== 'ALL') {
        params.append('served_region', filters.servedRegion);
      }
      if (filters?.region && filters.region !== 'ALL') {
        params.append('served_region', filters.region);
      }
      if (filters?.statusCode) {
        params.append('status_code', String(filters.statusCode));
      }
      if (filters?.requestType && filters.requestType !== 'ALL') {
        params.append('request_type', filters.requestType);
      }

      const res = await this.fetchWithTimeout(`${base}/api/v1/traffic/recent-events?${params.toString()}`, {}, 3000);
      if (!res.ok) return null;
      return await res.json();
    } catch {
      return null;
    }
  }

  public async fetchAuditEvents(limit = 100, severity?: string, subsystem?: string): Promise<AuditEventDto[]> {
    try {
      const base = this.controllerUrl;
      const params = new URLSearchParams({ limit: String(limit) });
      if (severity && severity !== 'ALL') params.append('severity', severity);
      if (subsystem && subsystem !== 'ALL') params.append('subsystem', subsystem);

      const res = await this.fetchWithTimeout(`${base}/api/v1/events?${params.toString()}`, {}, 3000);
      if (!res.ok) return [];
      return await res.json();
    } catch {
      return [];
    }
  }

  public subscribeControllerTrafficStream(
    onMetric?: (summary: TrafficSummaryDto) => void,
    onEvent?: (event: TrafficEventItemDto) => void,
    onConnect?: (summary: TrafficSummaryDto) => void
  ): () => void {
    if (typeof window === 'undefined' || typeof EventSource === 'undefined') {
      return () => {};
    }
    const base = this.controllerUrl;
    const url = `${base}/api/v1/traffic/stream`;
    let es: EventSource | null = null;
    let isClosed = false;

    try {
      es = new EventSource(url);

      es.addEventListener('connect', (e: MessageEvent) => {
        if (!e.data || isClosed) return;
        try {
          const parsed = JSON.parse(e.data);
          if (parsed && parsed.summary) {
            if (onConnect) onConnect(parsed.summary);
            if (onMetric) onMetric(parsed.summary);
          }
        } catch {
          // ignore parse error
        }
      });

      es.addEventListener('traffic_metric', (e: MessageEvent) => {
        if (!e.data || isClosed) return;
        try {
          const parsed = JSON.parse(e.data);
          if (parsed && onMetric) {
            onMetric(parsed);
          }
        } catch {
          // ignore parse error
        }
      });

      es.addEventListener('traffic_event', (e: MessageEvent) => {
        if (!e.data || isClosed) return;
        try {
          const parsed = JSON.parse(e.data);
          if (parsed && onEvent) {
            onEvent(parsed);
          }
        } catch {
          // ignore parse error
        }
      });

      es.onerror = () => {
        // Browser EventSource automatically reconnects
      };
    } catch {
      // EventSource initialization failed
    }

    return () => {
      isClosed = true;
      if (es) {
        es.close();
        es = null;
      }
    };
  }
}

export const controllerClient = new ControllerClient();
