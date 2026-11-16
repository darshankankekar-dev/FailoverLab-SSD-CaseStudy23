import { describe, it, expect, beforeEach, vi } from 'vitest';
import { ecommerceClient } from '../../api/ecommerceClient';
import type { Product, CartItem } from '../../api/ecommerceClient';

describe('Phase 8: Shop End-to-End Workflow Integration Test', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('executes full shop journey: catalog browse -> cart aggregation -> checkout mutation -> header verification', async () => {
    // 1. Mock catalog fetch from Gateway
    const catalogData: Product[] = [
      { id: 'prod-001', name: 'CloudKey Pro Hardware', category: 'Security', price: 149.0, stock: 25, description: 'FIDO2 Key' },
      { id: 'prod-002', name: 'EdgeRouter 10G', category: 'Networking', price: 799.0, stock: 10, description: '10Gbps SFP+ Router' },
    ];

    const catalogHeaders = new Headers({
      'X-Served-Region': 'region-a',
      'X-Active-Region': 'region-a',
      'X-Request-ID': 'req-browse-101',
      'X-Gateway-Latency-Ms': '12.4',
      'X-Simulated-WAN-Delay-Ms': '18.0',
      'X-Consistency-Level': 'eventual',
      'X-Route-Reason': 'lowest_latency_replica',
      'X-RateLimit-Mode': 'TOKEN_BUCKET',
      'X-RateLimit-Remaining': '9',
    });

    const catalogResponse = new Response(JSON.stringify(catalogData), {
      status: 200,
      headers: catalogHeaders,
    });

    // 2. Mock order placement to Gateway
    const orderConfirmation = {
      order_id: 'ord-integration-999',
      customer_name: 'Priya Sharma',
      customer_email: 'priya@example.com',
      shipping_address: '42 MG Road, Bengaluru, India',
      items: [
        { product_id: 'prod-001', product_name: 'CloudKey Pro Hardware', quantity: 2, unit_price: 149.0, total_price: 298.0 },
      ],
      total_amount: 321.84,
      status: 'CONFIRMED',
      region_id: 'region-a',
      fencing_epoch: 101,
      outbox_event_id: 'evt-outbox-888',
      sequence_number: 1055,
      created_at: new Date().toISOString(),
    };

    const orderHeaders = new Headers({
      'X-Served-Region': 'region-a',
      'X-Active-Region': 'region-a',
      'X-Request-ID': 'req-order-202',
      'X-Gateway-Latency-Ms': '18.5',
      'X-Simulated-WAN-Delay-Ms': '18.0',
      'X-Consistency-Level': 'write',
      'X-Route-Reason': 'active_primary_writer',
      'X-RateLimit-Mode': 'TOKEN_BUCKET',
    });

    const orderResponse = new Response(JSON.stringify(orderConfirmation), {
      status: 201,
      headers: orderHeaders,
    });

    const fetchMock = vi.fn().mockImplementation(async (url: string) => {
      if (url.includes('/api/ecommerce/products') || url.includes('/api/shop/products')) {
        return catalogResponse;
      }
      if (url.includes('/api/ecommerce/orders') || url.includes('/api/shop/orders')) {
        return orderResponse;
      }
      return new Response('Not found', { status: 404 });
    });

    vi.stubGlobal('fetch', fetchMock);

    // Step A: Browse catalog with India client region
    const { products, metadata: browseMeta } = await ecommerceClient.getCatalog('ap-south-1');
    expect(products).toHaveLength(2);
    expect(products[0].name).toBe('CloudKey Pro Hardware');
    expect(browseMeta.servedRegion).toBe('region-a');
    expect(browseMeta.consistencyLevel).toBe('eventual');
    expect(browseMeta.simulatedWanDelayMs).toBe(18.0);

    // Step B: Cart accumulation
    const cart: CartItem[] = [
      { product: products[0], quantity: 2 },
    ];
    const subtotal = cart.reduce((sum, item) => sum + item.product.price * item.quantity, 0);
    expect(subtotal).toBe(298.0);
    const freeShipping = subtotal > 100;
    expect(freeShipping).toBe(true);
    const tax = subtotal * 0.08;
    const total = subtotal + (freeShipping ? 0 : 15) + tax;
    expect(total).toBeCloseTo(321.84, 2);

    // Step C: Place order
    const orderPayload = {
      customer_name: 'Priya Sharma',
      customer_email: 'priya@example.com',
      shipping_address: '42 MG Road, Bengaluru, India',
      client_region: 'ap-south-1',
      items: [
        { product_id: products[0].id, quantity: 2 },
      ],
      total_amount: total,
    };

    const { order, metadata: orderMeta } = await ecommerceClient.submitOrder(
      orderPayload,
      'idem-key-priya-01'
    );
    expect(order.order_id).toBe('ord-integration-999');
    expect(order.status).toBe('CONFIRMED');
    expect(orderMeta.servedRegion).toBe('region-a');
    expect(orderMeta.consistencyLevel).toBe('write');
  });
});
