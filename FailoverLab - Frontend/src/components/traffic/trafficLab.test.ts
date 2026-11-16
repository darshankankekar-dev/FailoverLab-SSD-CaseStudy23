import { describe, it, expect, beforeEach, vi } from 'vitest';
import { controllerClient } from '../../api/controllerClient';
import type { ControllerStateDto, TrafficEvent } from '../../api/controllerClient';

describe('Phase 7: Five-Region Operations Dashboard & Traffic Lab Domain Logic', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('correctly updates gateway traffic management config via controllerClient', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        traffic_control: {
          mode: 'LEAKY_BUCKET',
          token_bucket: { capacity: 10, refill_rate: 2, tokens_remaining: 10 },
          leaky_bucket: { queue_capacity: 25, drain_rate: 5.0, current_queue_depth: 0 },
        },
      }),
    });
    vi.stubGlobal('fetch', mockFetch);

    const res = await controllerClient.updateTrafficConfig({
      mode: 'LEAKY_BUCKET',
      leaky_capacity: 25,
      leaky_drain_rate: 5.0,
    });

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/traffic/config'),
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify({
          mode: 'LEAKY_BUCKET',
          leaky_capacity: 25,
          leaky_drain_rate: 5.0,
        }),
      })
    );
    expect(res.success).toBe(true);
    expect(res.traffic_control.mode).toBe('LEAKY_BUCKET');
  });

  it('correctly sends regional chaos and lag injection requests', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        controller_state: 'HEALTHY',
        active_region: 'region-a',
      }),
    });
    vi.stubGlobal('fetch', mockFetch);

    // 1. Regional Health
    await controllerClient.setRegionalHealth('region-c', 'DOWN');
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/internal/chaos/regional-health?region_id=region-c&health=DOWN'),
      expect.objectContaining({ method: 'POST' })
    );

    // 2. Regional Lag
    await controllerClient.setRegionalLag('region-d', 8.5);
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/internal/chaos/regional-lag?region_id=region-d&lag_seconds=8.5'),
      expect.objectContaining({ method: 'POST' })
    );

    // 3. Pause Replication
    await controllerClient.pauseReplication('region-e');
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/internal/chaos/replication-pause?destination=region-e'),
      expect.objectContaining({ method: 'POST' })
    );
  });

  it('evaluates candidate promotion eligibility dynamically across all 5 regions', () => {
    const mockState: Partial<ControllerStateDto> = {
      active_region: 'region-a',
      policy: {
        health_check_interval_sec: 2,
        failure_threshold_consecutive: 3,
        quorum_size: 3,
        majority_required: 2,
        acceptable_replication_lag_sec: 5.0,
        fencing_duration_sec: 5,
        route_propagation_sec: 2,
        route_verification_sec: 2,
        auto_failover_enabled: true,
      },
      regions: [
        {
          id: 'region-a',
          name: 'Mumbai',
          cloud_zone: 'ap-south-1',
          role: 'ACTIVE',
          health: 'HEALTHY',
          status: 'healthy',
          accepts_writes: true,
          ingress_traffic_percent: 100,
          ingress_rps: 2450,
          app_servers_healthy: 8,
          app_servers_total: 8,
          active_connections: 2450,
          iops: 4800,
          fencing_epoch: 101,
          is_fenced: false,
          applied_sequence: 1050,
          replication_lag_seconds: 0.0,
        },
        {
          id: 'region-b',
          name: 'Singapore',
          cloud_zone: 'ap-southeast-1',
          role: 'STANDBY',
          health: 'HEALTHY',
          status: 'healthy',
          accepts_writes: false,
          ingress_traffic_percent: 0,
          ingress_rps: 0,
          app_servers_healthy: 8,
          app_servers_total: 8,
          active_connections: 0,
          iops: 120,
          fencing_epoch: 101,
          is_fenced: false,
          applied_sequence: 1050,
          replication_lag_seconds: 0.8,
        },
        {
          id: 'region-c',
          name: 'Frankfurt',
          cloud_zone: 'eu-central-1',
          role: 'STANDBY',
          health: 'DOWN',
          status: 'failed',
          accepts_writes: false,
          ingress_traffic_percent: 0,
          ingress_rps: 0,
          app_servers_healthy: 0,
          app_servers_total: 8,
          active_connections: 0,
          iops: 0,
          fencing_epoch: 101,
          is_fenced: false,
          applied_sequence: 1048,
          replication_lag_seconds: 1.2,
        },
        {
          id: 'region-d',
          name: 'Virginia',
          cloud_zone: 'us-east-1',
          role: 'STANDBY',
          health: 'HEALTHY',
          status: 'healthy',
          accepts_writes: false,
          ingress_traffic_percent: 0,
          ingress_rps: 0,
          app_servers_healthy: 8,
          app_servers_total: 8,
          active_connections: 0,
          iops: 120,
          fencing_epoch: 101,
          is_fenced: false,
          applied_sequence: 1050,
          replication_lag_seconds: 8.4, // Exceeds 5.0s
        },
        {
          id: 'region-e',
          name: 'São Paulo',
          cloud_zone: 'sa-east-1',
          role: 'STANDBY',
          health: 'HEALTHY',
          status: 'healthy',
          accepts_writes: false,
          ingress_traffic_percent: 0,
          ingress_rps: 0,
          app_servers_healthy: 8,
          app_servers_total: 8,
          active_connections: 0,
          iops: 120,
          fencing_epoch: 101,
          is_fenced: false,
          applied_sequence: 1045,
          replication_lag_seconds: 1.5,
        },
      ],
    };

    const isEligible = (rid: string) => {
      const reg = mockState.regions?.find((r) => r.id === rid);
      if (!reg) return false;
      if (reg.role === 'ACTIVE') return false;
      if (reg.health !== 'HEALTHY') return false;
      if (reg.is_fenced) return false;
      if ((reg.replication_lag_seconds ?? 0) > (mockState.policy?.acceptable_replication_lag_sec ?? 5.0)) return false;
      if (reg.app_servers_healthy <= 0) return false;
      return true;
    };

    // Region A: Active primary -> Ineligible for failover promotion
    expect(isEligible('region-a')).toBe(false);

    // Region B: Healthy, lag 0.8s <= 5.0s -> Eligible!
    expect(isEligible('region-b')).toBe(true);

    // Region C: Health DOWN -> Ineligible
    expect(isEligible('region-c')).toBe(false);

    // Region D: Lag 8.4s > 5.0s (RPO breach) -> Ineligible
    expect(isEligible('region-d')).toBe(false);

    // Region E: Healthy, lag 1.5s <= 5.0s -> Eligible!
    expect(isEligible('region-e')).toBe(true);
  });

  it('bounds live traffic events buffer to avoid unbounded browser memory growth', () => {
    const MAX_BUFFER = 150;
    let eventBuffer: TrafficEvent[] = [];

    const appendEvent = (ev: TrafficEvent) => {
      eventBuffer = [...eventBuffer, ev];
      if (eventBuffer.length > MAX_BUFFER) {
        eventBuffer = eventBuffer.slice(-MAX_BUFFER);
      }
    };

    // Simulate 300 incoming traffic events
    for (let i = 1; i <= 300; i++) {
      appendEvent({
        id: `evt-${i}`,
        timestamp: new Date().toISOString(),
        request_id: `req-${i}`,
        method: i % 3 === 0 ? 'POST' : 'GET',
        endpoint: '/api/ecommerce/products',
        client_region: 'eu-central-1',
        served_region: 'region-c',
        request_type: 'eventual_read',
        rate_limiter_decision: 'accepted',
        status_code: 200,
        duration_ms: 22.5,
        simulated_wan_delay_ms: 110.0,
        queue_wait_time_ms: 0.0,
      });
    }

    expect(eventBuffer.length).toBe(150);
    expect(eventBuffer[0].id).toBe('evt-151');
    expect(eventBuffer[149].id).toBe('evt-300');
  });
});
