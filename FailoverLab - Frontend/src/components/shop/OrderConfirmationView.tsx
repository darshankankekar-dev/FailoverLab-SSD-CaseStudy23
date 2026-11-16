import React, { useState } from 'react';
import {
  CheckCircle2,
  Server,
  ChevronDown,
  ChevronUp,
  ShoppingBag,
  ExternalLink,
  Layers,
  Copy,
  Check,
} from 'lucide-react';
import { CLIENT_REGIONS } from '../../api/ecommerceClient';
import type {
  GatewayResponseMetadata,
  OrderConfirmation,
} from '../../api/ecommerceClient';

interface OrderConfirmationViewProps {
  order: OrderConfirmation;
  metadata: GatewayResponseMetadata;
  onContinueShopping: () => void;
  onNavigateToConsole: () => void;
}

export const OrderConfirmationView: React.FC<OrderConfirmationViewProps> = ({
  order,
  metadata,
  onContinueShopping,
  onNavigateToConsole,
}) => {
  const [isCopied, setIsCopied] = useState(false);
  const [isTechDetailsOpen, setIsTechDetailsOpen] = useState(true);

  const clientReg = CLIENT_REGIONS.find((r) => r.id === order.client_region) || CLIENT_REGIONS[0];

  const handleCopyOrderId = () => {
    navigator.clipboard.writeText(order.order_id);
    setIsCopied(true);
    setTimeout(() => setIsCopied(false), 2000);
  };

  return (
    <div className="order-confirmation-container">
      <div className="order-confirmation-card">
        {/* Success Header */}
        <div className="confirmation-header">
          <div className="success-badge-circle">
            <CheckCircle2 size={40} className="text-healthy" />
          </div>
          <h2 className="confirmation-title">Order Confirmed!</h2>
          <p className="confirmation-subtitle">
            Thank you for your simulated purchase. Your order has been committed to the active database.
          </p>

          <div className="order-id-pill">
            <span className="order-id-label">Order Reference:</span>
            <span className="order-id-val font-mono">{order.order_id}</span>
            <button
              type="button"
              className="btn-copy-id"
              onClick={handleCopyOrderId}
              title="Copy Order ID"
            >
              {isCopied ? <Check size={14} className="text-healthy" /> : <Copy size={14} />}
            </button>
          </div>
        </div>

        {/* Order Summary Receipt */}
        <div className="confirmation-receipt-box">
          <h3 className="receipt-heading">Receipt Summary</h3>
          <div className="receipt-meta-grid">
            <div className="receipt-meta-item">
              <span className="meta-label">Customer Name</span>
              <span className="meta-val">{order.customer_name || 'Demo Customer'}</span>
            </div>
            <div className="receipt-meta-item">
              <span className="meta-label">Customer Email</span>
              <span className="meta-val font-mono">{order.customer_email}</span>
            </div>
            <div className="receipt-meta-item">
              <span className="meta-label">Client Location</span>
              <span className="meta-val">{clientReg.flag} {clientReg.name}</span>
            </div>
            <div className="receipt-meta-item">
              <span className="meta-label">Order Status</span>
              <span className="meta-val status-confirmed-badge">{order.status}</span>
            </div>
          </div>

          <div className="receipt-items-table">
            <div className="receipt-table-header">
              <span>Item Description</span>
              <span className="text-center">Qty</span>
              <span className="text-right">Amount</span>
            </div>
            {order.items && order.items.length > 0 ? (
              order.items.map((it) => (
                <div key={it.product_id} className="receipt-table-row">
                  <span className="item-title">{it.product_name}</span>
                  <span className="item-qty font-mono text-center">{it.quantity}</span>
                  <span className="item-price font-mono text-right">${it.total_price.toFixed(2)}</span>
                </div>
              ))
            ) : (
              <div className="receipt-table-row">
                <span className="item-title">{order.product_name || order.product_id}</span>
                <span className="item-qty font-mono text-center">{order.quantity || 1}</span>
                <span className="item-price font-mono text-right">${order.total_amount.toFixed(2)}</span>
              </div>
            )}
            <div className="receipt-total-row">
              <span>Total Paid (Simulated)</span>
              <span className="total-highlight font-mono">${order.total_amount.toFixed(2)}</span>
            </div>
          </div>
        </div>

        {/* Technical Response Details Panel (Customer-Visible Architecture) */}
        <div className="technical-panel-box">
          <button
            type="button"
            className="technical-panel-toggle"
            onClick={() => setIsTechDetailsOpen(!isTechDetailsOpen)}
          >
            <div className="toggle-left">
              <Server size={16} className="text-flow" />
              <span className="toggle-title">Technical Dispatch & Routing Telemetry</span>
              <span className="toggle-sub">Verified Gateway Response</span>
            </div>
            {isTechDetailsOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>

          {isTechDetailsOpen && (
            <div className="technical-panel-body">
              <div className="tech-telemetry-grid">
                <div className="telemetry-card">
                  <span className="telemetry-label">Served Region</span>
                  <span className="telemetry-value font-mono text-flow">
                    {order.created_in_region || metadata.servedRegion}
                  </span>
                  <span className="telemetry-hint">Target that committed the write</span>
                </div>

                <div className="telemetry-card">
                  <span className="telemetry-label">Active Writer</span>
                  <span className="telemetry-value font-mono text-healthy">
                    {metadata.activeRegion}
                  </span>
                  <span className="telemetry-hint">Sole authoritative primary node</span>
                </div>

                <div className="telemetry-card">
                  <span className="telemetry-label">Fencing Epoch</span>
                  <span className="telemetry-value font-mono">
                    #{order.fencing_epoch}
                  </span>
                  <span className="telemetry-hint">Monotonic split-brain guard</span>
                </div>

                <div className="telemetry-card">
                  <span className="telemetry-label">Gateway Roundtrip</span>
                  <span className="telemetry-value font-mono">
                    {metadata.latencyMs.toFixed(1)} ms
                  </span>
                  <span className="telemetry-hint">Backend execution time</span>
                </div>

                <div className="telemetry-card">
                  <span className="telemetry-label">Simulated WAN Delay</span>
                  <span className="telemetry-value font-mono">
                    +{metadata.simulatedWanDelayMs.toFixed(1)} ms
                  </span>
                  <span className="telemetry-hint">{clientReg.name} nominal</span>
                </div>

                <div className="telemetry-card">
                  <span className="telemetry-label">Consistency Mode</span>
                  <span className="telemetry-value font-mono uppercase">
                    {metadata.consistencyLevel}
                  </span>
                  <span className="telemetry-hint">Single-writer isolation</span>
                </div>

                <div className="telemetry-card full-width">
                  <span className="telemetry-label">Request Correlation ID</span>
                  <span className="telemetry-value font-mono text-xs">
                    {metadata.requestId}
                  </span>
                </div>

                <div className="telemetry-card full-width">
                  <span className="telemetry-label">Idempotency & Replication Invariant</span>
                  <div className="invariant-status-row">
                    <span className={`replay-tag ${metadata.isReplay ? 'replay-active' : 'replay-fresh'}`}>
                      {metadata.isReplay ? 'CACHED IDEMPOTENT REPLAY' : 'FIRST-TIME COMMIT'}
                    </span>
                    <span className="outbox-note">
                      Transactional outbox event emitted; asynchronously fanout to 4 standbys.
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Action Buttons */}
        <div className="confirmation-actions">
          <button
            type="button"
            className="btn-continue-shopping"
            onClick={onContinueShopping}
          >
            <ShoppingBag size={16} />
            <span>Continue Shopping</span>
          </button>

          <button
            type="button"
            className="btn-open-console"
            onClick={onNavigateToConsole}
          >
            <Layers size={16} />
            <span>Inspect in Failover Console</span>
            <ExternalLink size={14} />
          </button>
        </div>
      </div>
    </div>
  );
};
