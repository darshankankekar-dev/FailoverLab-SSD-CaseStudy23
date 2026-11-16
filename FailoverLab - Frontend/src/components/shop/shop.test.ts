import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  CLIENT_REGIONS,
  ecommerceClient,
  RateLimitError,
} from '../../api/ecommerceClient';
import type {
  Product,
  CartItem,
} from '../../api/ecommerceClient';

describe('Online Store E-Commerce Client & Domain Logic', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('configures five client regions with appropriate cloud zones and latency estimates', () => {
    expect(CLIENT_REGIONS).toHaveLength(5);

    const india = CLIENT_REGIONS.find((r) => r.id === 'ap-south-1');
    expect(india).toBeDefined();
    expect(india?.name).toContain('India');

    const seAsia = CLIENT_REGIONS.find((r) => r.id === 'ap-southeast-1');
    expect(seAsia).toBeDefined();
    expect(seAsia?.name).toContain('Singapore');

    const europe = CLIENT_REGIONS.find((r) => r.id === 'eu-central-1');
    expect(europe).toBeDefined();
    expect(europe?.name).toContain('Frankfurt');

    const northAmerica = CLIENT_REGIONS.find((r) => r.id === 'us-east-1');
    expect(northAmerica).toBeDefined();
    expect(northAmerica?.name).toContain('Virginia');

    const southAmerica = CLIENT_REGIONS.find((r) => r.id === 'sa-east-1');
    expect(southAmerica).toBeDefined();
    expect(southAmerica?.name).toContain('São Paulo');
  });

  it('correctly calculates cart subtotals, shipping, and taxes', () => {
    const p1: Product = {
      id: 'prod-headset-03',
      name: 'NoiseCancel Elite X',
      category: 'Audio',
      price: 199.0,
      description: 'Headphones',
      stock: 50,
    };

    const p2: Product = {
      id: 'prod-watch-04',
      name: 'PulseTracker BioSmart',
      category: 'Wearables',
      price: 249.0,
      description: 'Smartwatch',
      stock: 30,
    };

    const cart: CartItem[] = [
      { product: p1, quantity: 2 },
      { product: p2, quantity: 1 },
    ];

    const subtotal = cart.reduce((acc, item) => acc + item.product.price * item.quantity, 0);
    expect(subtotal).toBe(199.0 * 2 + 249.0); // 647.0

    const freeShipping = subtotal > 100;
    expect(freeShipping).toBe(true);

    const tax = subtotal * 0.08;
    expect(tax).toBeCloseTo(51.76, 2);

    const total = subtotal + (freeShipping ? 0 : 15) + tax;
    expect(total).toBeCloseTo(698.76, 2);
  });

  it('parses Gateway metadata headers correctly on successful response', async () => {
    const mockHeaders = new Headers({
      'X-Served-Region': 'region-a',
      'X-Active-Region': 'region-a',
      'X-Request-ID': 'req-test-99',
      'X-Gateway-Latency-Ms': '14.25',
      'X-Simulated-WAN-Delay-Ms': '22.0',
      'X-Consistency-Level': 'eventual',
      'X-Route-Reason': 'lowest_latency_replica',
      'X-RateLimit-Mode': 'TOKEN_BUCKET',
      'X-RateLimit-Remaining': '9',
    });

    const mockResponse = new Response(
      JSON.stringify([
        { id: 'prod-laptop-01', name: 'ThinkStation Ultra 16', price: 1299.0, stock: 45, category: 'Laptops', description: 'Test' },
      ]),
      { status: 200, headers: mockHeaders }
    );

    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse);

    const { products, metadata } = await ecommerceClient.getCatalog('ap-south-1');
    expect(products).toHaveLength(1);
    expect(products[0].name).toBe('ThinkStation Ultra 16');
    expect(metadata.servedRegion).toBe('region-a');
    expect(metadata.latencyMs).toBe(14.25);
    expect(metadata.simulatedWanDelayMs).toBe(22.0);
    expect(metadata.consistencyLevel).toBe('eventual');
    expect(metadata.rateLimitMode).toBe('TOKEN_BUCKET');
    expect(metadata.rateLimitRemaining).toBe('9');
  });

  it('raises RateLimitError with retry-after seconds when Gateway returns HTTP 429', async () => {
    const mockHeaders = new Headers({
      'Retry-After': '5',
      'X-RateLimit-Mode': 'TOKEN_BUCKET',
      'X-RateLimit-Remaining': '0',
    });

    const mockResponse = new Response(
      JSON.stringify({
        error: 'Rate limit exceeded',
        message: 'Token bucket capacity exhausted',
        retry_after_seconds: 5,
        mode: 'TOKEN_BUCKET',
      }),
      { status: 429, headers: mockHeaders }
    );

    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse);

    await expect(ecommerceClient.getCatalog('ap-south-1')).rejects.toThrow(RateLimitError);

    try {
      await ecommerceClient.getCatalog('ap-south-1');
    } catch (err: any) {
      expect(err).toBeInstanceOf(RateLimitError);
      expect(err.retryAfterSeconds).toBe(5);
      expect(err.mode).toBe('TOKEN_BUCKET');
    }
  });

  it('identifies idempotent replay responses via X-Idempotency-Replay header', async () => {
    const mockHeaders = new Headers({
      'X-Served-Region': 'region-a',
      'X-Active-Region': 'region-a',
      'X-Request-ID': 'req-replay-1',
      'X-Consistency-Level': 'write',
      'X-Idempotency-Replay': 'true',
    });

    const mockResponse = new Response(
      JSON.stringify({
        order_id: 'ord-cached-1234',
        product_id: 'prod-laptop-01',
        quantity: 1,
        total_amount: 1299.0,
        status: 'CONFIRMED',
        customer_email: 'shopper@example.com',
        client_region: 'ap-south-1',
        created_in_region: 'region-a',
        fencing_epoch: 1,
        created_at: new Date().toISOString(),
      }),
      { status: 201, headers: mockHeaders }
    );

    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse);

    const { order, metadata } = await ecommerceClient.submitOrder(
      {
        product_id: 'prod-laptop-01',
        quantity: 1,
        customer_name: 'Test Customer',
        customer_email: 'shopper@example.com',
        shipping_address: '123 Test St',
        client_region: 'ap-south-1',
      },
      'idemp-test-session-key'
    );

    expect(order.order_id).toBe('ord-cached-1234');
    expect(metadata.isReplay).toBe(true);
  });
});
