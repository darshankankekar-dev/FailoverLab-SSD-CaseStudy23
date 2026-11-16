/**
 * FailoverLab Online Store API Client
 * Connects the customer-facing storefront to the Dynamic Ingress Gateway
 * Routes requests according to multi-region policies:
 * - Product catalog & details: Eventual consistency (nearest eligible replica)
 * - Live stock & inventory: Strong consistency (active writer)
 * - Order placement & checkout: Single active writer with Idempotency-Key
 */

export interface Product {
  id: string;
  name: string;
  category: string;
  price: number;
  description: string;
  stock: number;
  rating?: number;
  image_url?: string;
  badge?: string;
  features?: string[];
}

export interface CartItem {
  product: Product;
  quantity: number;
}

export interface OrderItemDetail {
  product_id: string;
  product_name: string;
  quantity: number;
  unit_price: number;
  total_price: number;
}

export interface OrderConfirmation {
  order_id: string;
  product_id?: string;
  product_name?: string;
  quantity?: number;
  unit_price?: number;
  items?: OrderItemDetail[];
  total_amount: number;
  status: string;
  customer_name?: string;
  customer_email: string;
  shipping_address?: string;
  client_region: string;
  created_in_region: string;
  fencing_epoch: number;
  created_at: string;
}

export interface GatewayResponseMetadata {
  servedRegion: string;
  activeRegion: string;
  requestId: string;
  latencyMs: number;
  simulatedWanDelayMs: number;
  consistencyLevel: 'eventual' | 'strong' | 'write' | string;
  routeReason: string;
  isReplay: boolean;
  rateLimitMode?: string;
  rateLimitRemaining?: string;
  retryAfterSeconds?: number;
  timestamp: string;
}

export interface ClientRegionOption {
  id: string;
  name: string;
  zone: string;
  flag: string;
  nominalLatency: string;
}

export const CLIENT_REGIONS: ClientRegionOption[] = [
  { id: 'ap-south-1', name: 'India (Mumbai)', zone: 'ap-south-1', flag: '🇮🇳', nominalLatency: '15ms - 25ms' },
  { id: 'ap-southeast-1', name: 'Southeast Asia (Singapore)', zone: 'ap-southeast-1', flag: '🇸🇬', nominalLatency: '35ms - 45ms' },
  { id: 'eu-central-1', name: 'Europe (Frankfurt)', zone: 'eu-central-1', flag: '🇩🇪', nominalLatency: '110ms - 130ms' },
  { id: 'us-east-1', name: 'North America (Virginia)', zone: 'us-east-1', flag: '🇺🇸', nominalLatency: '175ms - 210ms' },
  { id: 'sa-east-1', name: 'South America (São Paulo)', zone: 'sa-east-1', flag: '🇧🇷', nominalLatency: '240ms - 290ms' },
];

export class RateLimitError extends Error {
  public retryAfterSeconds: number;
  public mode: string;

  constructor(message: string, retryAfterSeconds: number = 2, mode: string = 'TOKEN_BUCKET') {
    super(message);
    this.name = 'RateLimitError';
    this.retryAfterSeconds = retryAfterSeconds;
    this.mode = mode;
  }
}

class EcommerceClient {
  private gatewayBaseUrl: string;

  constructor() {
    this.gatewayBaseUrl = '';
  }

  private extractMetadata(res: Response, elapsedMs: number): GatewayResponseMetadata {
    const served = res.headers.get('X-Served-Region') || res.headers.get('X-Routed-To-Region') || 'unknown';
    const active = res.headers.get('X-Active-Region') || served;
    const reqId = res.headers.get('X-Request-ID') || res.headers.get('X-Correlation-ID') || `req-${Math.random().toString(36).substring(2, 9)}`;
    const gwLatencyStr = res.headers.get('X-Gateway-Latency-Ms');
    const wanDelayStr = res.headers.get('X-Simulated-WAN-Delay-Ms');
    const consistency = res.headers.get('X-Consistency-Level') || 'eventual';
    const reason = res.headers.get('X-Route-Reason') || 'standard_ingress';
    const isReplay = res.headers.get('X-Idempotency-Replay') === 'true';
    const rateLimitMode = res.headers.get('X-RateLimit-Mode') || undefined;
    const rateLimitRemaining = res.headers.get('X-RateLimit-Remaining') || undefined;
    const retryAfterStr = res.headers.get('Retry-After');

    return {
      servedRegion: served,
      activeRegion: active,
      requestId: reqId,
      latencyMs: gwLatencyStr ? parseFloat(gwLatencyStr) : Math.round(elapsedMs),
      simulatedWanDelayMs: wanDelayStr ? parseFloat(wanDelayStr) : 0,
      consistencyLevel: consistency,
      routeReason: reason,
      isReplay,
      rateLimitMode,
      rateLimitRemaining,
      retryAfterSeconds: retryAfterStr ? parseInt(retryAfterStr, 10) : undefined,
      timestamp: new Date().toLocaleTimeString(),
    };
  }

  private async fetchWithHeaders(
    endpoint: string,
    options: RequestInit = {},
    clientRegion: string = 'ap-south-1',
    idempotencyKey?: string
  ): Promise<{ data: any; metadata: GatewayResponseMetadata }> {
    const url = `${this.gatewayBaseUrl}${endpoint}`;
    const headers: Record<string, string> = {
      'Accept': 'application/json',
      'X-Client-Region': clientRegion,
      'X-Client-ID': `shopper-${clientRegion}`,
      ...(options.headers as Record<string, string> || {}),
    };

    if (idempotencyKey) {
      headers['Idempotency-Key'] = idempotencyKey;
    }

    const start = performance.now();
    let res: Response;
    try {
      res = await fetch(url, { ...options, headers });
    } catch (err: any) {
      throw new Error(`Gateway unreachable (${err?.message || 'Network error'}). Ensure FailoverLab services are running.`);
    }

    const elapsedMs = performance.now() - start;
    const metadata = this.extractMetadata(res, elapsedMs);

    if (res.status === 429) {
      const body = await res.json().catch(() => ({}));
      const retryAfter = metadata.retryAfterSeconds || body.retry_after_seconds || 2;
      const mode = metadata.rateLimitMode || body.mode || 'TOKEN_BUCKET';
      throw new RateLimitError(
        body.message || `Traffic limit exceeded. Please wait ${retryAfter}s.`,
        retryAfter,
        mode
      );
    }

    if (!res.ok) {
      const errBody = await res.json().catch(() => ({ detail: res.statusText }));
      const msg = typeof errBody.detail === 'string'
        ? errBody.detail
        : (errBody.message || errBody.error || `HTTP ${res.status}`);
      throw new Error(msg);
    }

    const data = await res.json();
    return { data, metadata };
  }

  /**
   * Fetch online shopping catalog (Eventual-consistency read)
   */
  public async getCatalog(clientRegion: string = 'ap-south-1'): Promise<{ products: Product[]; metadata: GatewayResponseMetadata }> {
    const { data, metadata } = await this.fetchWithHeaders('/api/shop/products', { method: 'GET' }, clientRegion);
    return { products: data, metadata };
  }

  /**
   * Fetch single product details (Eventual-consistency read)
   */
  public async getProductDetails(productId: string, clientRegion: string = 'ap-south-1'): Promise<{ product: Product; metadata: GatewayResponseMetadata }> {
    const { data, metadata } = await this.fetchWithHeaders(`/api/shop/products/${productId}`, { method: 'GET' }, clientRegion);
    return { product: data, metadata };
  }

  /**
   * Fetch live authoritative stock (Strong-consistency read - Active Writer)
   */
  public async getProductInventory(productId: string, clientRegion: string = 'ap-south-1'): Promise<{ stock: number; reserved: number; metadata: GatewayResponseMetadata }> {
    const { data, metadata } = await this.fetchWithHeaders(`/api/shop/inventory/${productId}`, { method: 'GET' }, clientRegion);
    return { stock: data.stock, reserved: data.reserved || 0, metadata };
  }

  /**
   * Place an order (Write - Single Active Writer with Idempotency)
   */
  public async submitOrder(
    payload: {
      items?: { product_id: string; quantity: number }[];
      product_id?: string;
      quantity?: number;
      customer_name: string;
      customer_email: string;
      shipping_address: string;
      client_region: string;
    },
    idempotencyKey?: string
  ): Promise<{ order: OrderConfirmation; metadata: GatewayResponseMetadata }> {
    const { data, metadata } = await this.fetchWithHeaders(
      '/api/shop/orders',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      },
      payload.client_region,
      idempotencyKey
    );
    return { order: data, metadata };
  }

  /**
   * Fetch order confirmation status (Strong-consistency read)
   */
  public async getOrderStatus(orderId: string, clientRegion: string = 'ap-south-1'): Promise<{ order: OrderConfirmation; metadata: GatewayResponseMetadata }> {
    const { data, metadata } = await this.fetchWithHeaders(`/api/shop/orders/${orderId}`, { method: 'GET' }, clientRegion);
    return { order: data, metadata };
  }
}

export const ecommerceClient = new EcommerceClient();
