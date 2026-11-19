import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  formatBytes,
  formatBytesPerSec,
  formatLatency,
  formatNumber,
  formatRelativeTime,
} from './formatters';
import { controllerClient } from '../../api/controllerClient';

describe('Controller UI Formatters', () => {
  it('formats payload bytes correctly across scales', () => {
    expect(formatBytes(0)).toBe('0 B');
    expect(formatBytes(512)).toBe('512 B');
    expect(formatBytes(1024)).toBe('1 KB');
    expect(formatBytes(1536)).toBe('1.5 KB');
    expect(formatBytes(1048576)).toBe('1 MB');
    expect(formatBytes(2621440, 2)).toBe('2.5 MB');
  });

  it('formats throughput rates correctly', () => {
    expect(formatBytesPerSec(0)).toBe('0.0 B/s');
    expect(formatBytesPerSec(1024)).toBe('1 KB/s');
    expect(formatBytesPerSec(2500, 1)).toBe('2.4 KB/s');
    expect(formatBytesPerSec(1048576 * 3.5, 1)).toBe('3.5 MB/s');
  });

  it('formats latency milliseconds correctly', () => {
    expect(formatLatency(0)).toBe('0.0 ms');
    expect(formatLatency(14.24)).toBe('14.2 ms');
    expect(formatLatency(120.678, 2)).toBe('120.68 ms');
  });

  it('formats numbers with comma separators', () => {
    expect(formatNumber(0)).toBe('0');
    expect(formatNumber(1250)).toBe('1,250');
    expect(formatNumber(1000000)).toBe('1,000,000');
  });

  it('formats relative timestamps gracefully', () => {
    expect(formatRelativeTime(null)).toBe('Never');
    const nowIso = new Date().toISOString();
    expect(formatRelativeTime(nowIso)).toBe('Just now');
    const tenSecAgo = new Date(Date.now() - 10000).toISOString();
    expect(formatRelativeTime(tenSecAgo)).toBe('10s ago');
  });
});

describe('ControllerClient Telemetry Methods', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('fetchTrafficSummary returns typed summary payload', async () => {
    const mockSummary = {
      current_ingress_bytes_per_sec: 1024.0,
      current_egress_bytes_per_sec: 4096.0,
      cumulative_ingress_bytes: 50000,
      cumulative_egress_bytes: 200000,
      upstream_ingress_bytes_per_sec: 4000.0,
      upstream_egress_bytes_per_sec: 1000.0,
      request_rate: 12.5,
      total_requests: 350,
      status_2xx: 345,
      status_3xx: 0,
      status_4xx: 5,
      status_5xx: 0,
      rate_limited_429: 0,
      latency_p50_ms: 8.5,
      latency_p95_ms: 18.2,
      latency_p99_ms: 25.0,
      latency_avg_ms: 10.1,
      last_received_timestamp: new Date().toISOString(),
      telemetry_freshness: 'FRESH' as const,
      telemetry_age_seconds: 0.5,
      is_available: true,
      measurement_source: 'gateway-1',
      measurement_unit: 'bytes',
      measurement_type: 'application_payload_bytes',
      note: 'Application/API payload bytes measured at Gateway proxy boundaries.',
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockSummary,
    });

    const res = await controllerClient.fetchTrafficSummary();
    expect(res).not.toBeNull();
    expect(res?.current_ingress_bytes_per_sec).toBe(1024.0);
    expect(res?.telemetry_freshness).toBe('FRESH');
    expect(res?.latency_p95_ms).toBe(18.2);
    expect(res?.total_requests).toBe(350);
  });

  it('fetchTrafficTimeseries returns timeseries points with custom range', async () => {
    const mockTimeseries = {
      time_range_seconds: 60,
      step_seconds: 1,
      point_count: 2,
      points: [
        {
          timestamp: '2026-11-19T02:00:00Z',
          client_ingress_bytes: 5000,
          client_egress_bytes: 20000,
          client_ingress_rate: 100.0,
          client_egress_rate: 400.0,
          upstream_ingress_rate: 350.0,
          upstream_egress_rate: 90.0,
          request_rate: 5.0,
          error_rate: 0.0,
          status_2xx: 5,
          status_4xx: 0,
          status_5xx: 0,
          latency_p95_ms: 12.0,
        },
      ],
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockTimeseries,
    });

    const res = await controllerClient.fetchTrafficTimeseries(60, 1);
    expect(res).not.toBeNull();
    expect(res?.point_count).toBe(2);
    expect(res?.points[0].client_ingress_rate).toBe(100.0);
  });

  it('fetchRegionalTraffic returns five regions data', async () => {
    const mockRegions = {
      timestamp: new Date().toISOString(),
      regions: {
        'region-a': {
          region_id: 'region-a',
          region_name: 'Mumbai',
          cloud_zone: 'ap-south-1',
          requests_total: 100,
          request_rate: 10.0,
          upstream_request_bytes: 50000,
          upstream_response_bytes: 200000,
          upstream_ingress_rate: 8192.0,
          upstream_egress_rate: 2048.0,
          status_2xx: 100,
          status_3xx: 0,
          status_4xx: 0,
          status_5xx: 0,
          failed_requests: 0,
          timeouts: 0,
          latency_avg_ms: 15.0,
        },
        'region-b': {
          region_id: 'region-b',
          region_name: 'Singapore',
          cloud_zone: 'ap-southeast-1',
          requests_total: 0,
          request_rate: 0.0,
          upstream_request_bytes: 0,
          upstream_response_bytes: 0,
          upstream_ingress_rate: 0.0,
          upstream_egress_rate: 0.0,
          status_2xx: 0,
          status_3xx: 0,
          status_4xx: 0,
          status_5xx: 0,
          failed_requests: 0,
          timeouts: 0,
          latency_avg_ms: 0.0,
        },
      },
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockRegions,
    });

    const res = await controllerClient.fetchRegionalTraffic();
    expect(res).not.toBeNull();
    expect(Object.keys(res?.regions || {}).length).toBe(2);
    expect(res?.regions['region-a'].region_name).toBe('Mumbai');
    expect(res?.regions['region-b'].upstream_ingress_rate).toBe(0.0);
  });

  it('fetchTrafficEvents supports pagination and filtering', async () => {
    const mockEvents = {
      total: 1,
      page: 1,
      page_size: 20,
      events: [
        {
          id: 'ev-1',
          timestamp: new Date().toISOString(),
          request_id: 'req-abc1234',
          method: 'POST',
          endpoint: '/api/shop/checkout',
          client_region: 'ap-south-1',
          served_region: 'region-a',
          status_code: 200,
          duration_ms: 15.4,
          request_payload_bytes: 256,
          response_payload_bytes: 512,
          request_type: 'write',
          rate_limiter_decision: 'accepted',
          request_category: 'orders',
          traffic_source: 'online_store',
          is_replay: false,
        },
      ],
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockEvents,
    });

    const res = await controllerClient.fetchTrafficEvents(1, 20, {
      region: 'region-a',
      requestType: 'write',
      method: 'POST',
    });

    expect(res).not.toBeNull();
    expect(res?.events.length).toBe(1);
    expect(res?.events[0].method).toBe('POST');
    expect(res?.events[0].request_payload_bytes).toBe(256);
    expect(res?.events[0].response_payload_bytes).toBe(512);
  });
});
