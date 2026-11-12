/**
 * FailoverLab Controller and Gateway Typed HTTP Client
 * Connects the React application to the Python/FastAPI control plane
 * and the Dynamic Ingress Gateway via same-origin paths or configured URLs.
 */

export interface QuorumVoterDto {
  id: string;
  name: string;
  location: string;
  vote: 'PRIMARY_OUTAGE' | 'PRIMARY_HEALTHY' | 'ABSTAIN';
  latency_ms: number;
}

export interface RegionDto {
  id: 'region-a' | 'region-b';
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

export interface ReplicationStateDto {
  status: 'STREAMING' | 'DEGRADED' | 'SEVERED' | 'REVERSED' | 'SYNCED';
  lag_seconds: number;
  lag_ms: number;
  bandwidth_mbps: number;
  packet_loss_percent: number;
  pending_bytes: number;
  bytes_transferred: number;
  mode: string;
}

export interface RouteStateDto {
  active_target: 'region-a' | 'region-b';
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
  active_region: 'region-a' | 'region-b';
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
  target_region?: 'region-a' | 'region-b';
  reason?: string;
}

export interface FailbackRequestPayload {
  operator_id: string;
  confirmation: boolean;
  target_region?: 'region-a' | 'region-b';
  reason?: string;
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
}

export const controllerClient = new ControllerClient();
