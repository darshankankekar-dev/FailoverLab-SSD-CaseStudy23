import React, { useState } from 'react';
import {
  X,
  Lock,
  CreditCard,
  ShieldCheck,
  AlertTriangle,
  RefreshCw,
  Server,
} from 'lucide-react';
import {
  CLIENT_REGIONS,
  ecommerceClient,
  RateLimitError,
} from '../../api/ecommerceClient';
import type {
  CartItem,
  GatewayResponseMetadata,
  OrderConfirmation,
} from '../../api/ecommerceClient';

interface CheckoutModalProps {
  isOpen: boolean;
  onClose: () => void;
  items: CartItem[];
  selectedRegion: string;
  onOrderSuccess: (order: OrderConfirmation, metadata: GatewayResponseMetadata) => void;
}

export const CheckoutModal: React.FC<CheckoutModalProps> = ({
  isOpen,
  onClose,
  items,
  selectedRegion,
  onOrderSuccess,
}) => {
  if (!isOpen) return null;

  const currentRegion = CLIENT_REGIONS.find((r) => r.id === selectedRegion) || CLIENT_REGIONS[0];

  const getDefaultAddress = (regionId: string) => {
    switch (regionId) {
      case 'ap-south-1':
        return '402 High Street, Bandra Kurla Complex, Mumbai, India';
      case 'ap-southeast-1':
        return '18 Marina Gardens Dr, Singapore 018953';
      case 'eu-central-1':
        return 'Taunusanlage 8, 60329 Frankfurt am Main, Germany';
      case 'us-east-1':
        return '1400 Crystal Drive, Arlington, VA 22202, USA';
      case 'sa-east-1':
        return 'Av. Paulista, 1578 - Bela Vista, São Paulo, Brazil';
      default:
        return '123 Cloud Way, Gateway Zone';
    }
  };

  const [customerName, setCustomerName] = useState('Vikram Sharma');
  const [customerEmail, setCustomerEmail] = useState('shopper@failoverlab.internal');
  const [shippingAddress, setShippingAddress] = useState(() => getDefaultAddress(selectedRegion));

  // Idempotency key per checkout session
  const [idempotencyKey] = useState(() => `idemp-${Math.random().toString(36).substring(2, 12)}`);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [rateLimitCountdown, setRateLimitCountdown] = useState<number | null>(null);

  const subtotal = items.reduce((acc, item) => acc + item.product.price * item.quantity, 0);
  const shipping = subtotal > 100 || items.length === 0 ? 0.0 : 15.0;
  const estimatedTax = subtotal * 0.08;
  const total = subtotal + shipping + estimatedTax;

  const handlePlaceOrder = async (e: React.FormEvent) => {
    e.preventDefault();
    if (items.length === 0 || isSubmitting || rateLimitCountdown !== null) return;

    setIsSubmitting(true);
    setErrorMessage(null);

    try {
      const orderPayload = {
        items: items.map((i) => ({ product_id: i.product.id, quantity: i.quantity })),
        product_id: items[0]?.product.id,
        quantity: items.reduce((s, i) => s + i.quantity, 0),
        customer_name: customerName,
        customer_email: customerEmail,
        shipping_address: shippingAddress,
        client_region: selectedRegion,
      };

      const { order, metadata } = await ecommerceClient.submitOrder(
        orderPayload,
        idempotencyKey
      );

      onOrderSuccess(order, metadata);
    } catch (err: any) {
      if (err instanceof RateLimitError) {
        setErrorMessage(err.message);
        setRateLimitCountdown(err.retryAfterSeconds);

        const timer = setInterval(() => {
          setRateLimitCountdown((prev) => {
            if (prev === null || prev <= 1) {
              clearInterval(timer);
              return null;
            }
            return prev - 1;
          });
        }, 1000);
      } else {
        setErrorMessage(err?.message || 'Checkout failed. Please verify writer connectivity.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="shop-checkout-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-labelledby="checkout-modal-title"
      >
        {/* Header */}
        <div className="checkout-modal-header">
          <div className="checkout-title-group">
            <Lock size={18} className="text-flow" />
            <h2 id="checkout-modal-title" className="checkout-title">Secure Demo Checkout</h2>
          </div>
          <button
            type="button"
            className="modal-close-btn"
            onClick={onClose}
            aria-label="Close checkout"
          >
            <X size={18} />
          </button>
        </div>

        {/* Throttled Rate Limit Warning Banner */}
        {rateLimitCountdown !== null && (
          <div className="rate-limit-alert-banner">
            <AlertTriangle size={16} className="text-warning" />
            <div className="rate-limit-text">
              <strong>Gateway Rate Limiting Active</strong>
              <p>
                Incoming write quota exhausted. Automatic backoff enabled. Retrying allowed in{' '}
                <span className="font-mono text-warning font-bold">{rateLimitCountdown}s</span>.
              </p>
            </div>
          </div>
        )}

        {errorMessage && rateLimitCountdown === null && (
          <div className="checkout-error-banner">
            <AlertTriangle size={15} />
            <span>{errorMessage}</span>
          </div>
        )}

        <form onSubmit={handlePlaceOrder} className="checkout-form">
          <div className="checkout-columns-grid">
            {/* Left: Contact & Shipping */}
            <div className="checkout-form-column">
              <section className="checkout-section">
                <h3 className="section-title">1. Customer Information</h3>
                <div className="form-field-group">
                  <label htmlFor="customer-name" className="field-label">Full Name</label>
                  <input
                    id="customer-name"
                    type="text"
                    required
                    value={customerName}
                    onChange={(e) => setCustomerName(e.target.value)}
                    className="shop-input"
                  />
                </div>

                <div className="form-field-group">
                  <label htmlFor="customer-email" className="field-label">Email Address</label>
                  <input
                    id="customer-email"
                    type="email"
                    required
                    value={customerEmail}
                    onChange={(e) => setCustomerEmail(e.target.value)}
                    className="shop-input"
                  />
                </div>
              </section>

              <section className="checkout-section">
                <h3 className="section-title">2. Delivery Destination</h3>
                <div className="form-field-group">
                  <label htmlFor="shipping-address" className="field-label">
                    Shipping Address ({currentRegion.flag} {currentRegion.name})
                  </label>
                  <input
                    id="shipping-address"
                    type="text"
                    required
                    value={shippingAddress}
                    onChange={(e) => setShippingAddress(e.target.value)}
                    className="shop-input"
                  />
                  <span className="field-hint">
                    Requests carry header: <code>X-Client-Region: {selectedRegion}</code>
                  </span>
                </div>
              </section>

              <section className="checkout-section payment-sim-section">
                <div className="section-header-row">
                  <h3 className="section-title">3. Simulated Payment</h3>
                  <span className="sim-pill">TEST MODE • NO REAL CHARGE</span>
                </div>

                <div className="mock-card-box">
                  <div className="mock-card-top">
                    <CreditCard size={18} className="text-secondary" />
                    <span className="card-brand-label">Test Sandbox</span>
                  </div>
                  <div className="mock-card-number font-mono">•••• •••• •••• 4242</div>
                  <div className="mock-card-bottom font-mono">
                    <span>EXP: 12/28</span>
                    <span>CVC: •••</span>
                  </div>
                </div>
              </section>
            </div>

            {/* Right: Order Summary & Ingress Rules */}
            <div className="checkout-summary-column">
              <section className="checkout-section order-review-section">
                <h3 className="section-title">Order Summary ({items.length} items)</h3>
                <div className="checkout-item-previews">
                  {items.map((item) => (
                    <div key={item.product.id} className="summary-item-preview">
                      <span className="preview-name">
                        {item.quantity}x {item.product.name}
                      </span>
                      <span className="preview-price font-mono">
                        ${(item.product.price * item.quantity).toFixed(2)}
                      </span>
                    </div>
                  ))}
                </div>

                <div className="summary-divider" />

                <div className="checkout-cost-breakdown">
                  <div className="breakdown-row">
                    <span>Subtotal</span>
                    <span className="font-mono">${subtotal.toFixed(2)}</span>
                  </div>
                  <div className="breakdown-row">
                    <span>Shipping</span>
                    <span className="font-mono">{shipping === 0 ? 'FREE' : `$${shipping.toFixed(2)}`}</span>
                  </div>
                  <div className="breakdown-row">
                    <span>Estimated Tax (8%)</span>
                    <span className="font-mono">${estimatedTax.toFixed(2)}</span>
                  </div>
                  <div className="breakdown-row total-breakdown-row">
                    <span>Total Due</span>
                    <span className="total-highlight font-mono">${total.toFixed(2)}</span>
                  </div>
                </div>

                {/* Gateway Routing Guarantee */}
                <div className="routing-guarantee-box">
                  <div className="guarantee-header">
                    <Server size={14} className="text-flow" />
                    <span className="guarantee-title">Gateway Consistency Guarantee</span>
                  </div>
                  <p className="guarantee-desc">
                    This order will be strictly routed to the <strong>single active primary writer</strong>. Replicas are never written to directly.
                  </p>
                  <div className="idempotency-badge font-mono">
                    <ShieldCheck size={12} className="text-healthy" />
                    <span>Idempotency-Key: {idempotencyKey.substring(0, 14)}...</span>
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={isSubmitting || rateLimitCountdown !== null}
                  className="btn-submit-order"
                >
                  {isSubmitting ? (
                    <>
                      <RefreshCw size={16} className="spin" />
                      <span>Transacting at Active Region...</span>
                    </>
                  ) : rateLimitCountdown !== null ? (
                    <span>Throttled ({rateLimitCountdown}s)</span>
                  ) : (
                    <>
                      <Lock size={15} />
                      <span>Place Order • ${total.toFixed(2)}</span>
                    </>
                  )}
                </button>
              </section>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
};
