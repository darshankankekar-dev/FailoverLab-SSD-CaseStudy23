import React from 'react';
import {
  X,
  Trash2,
  Plus,
  Minus,
  ShoppingBag,
  ArrowRight,
  ShieldCheck,
} from 'lucide-react';
import type { CartItem } from '../../api/ecommerceClient';
import { ProductIllustration } from './ProductIllustrations';

interface CartDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  items: CartItem[];
  onUpdateQuantity: (productId: string, quantity: number) => void;
  onRemoveItem: (productId: string) => void;
  onClearCart: () => void;
  onProceedToCheckout: () => void;
}

export const CartDrawer: React.FC<CartDrawerProps> = ({
  isOpen,
  onClose,
  items,
  onUpdateQuantity,
  onRemoveItem,
  onClearCart,
  onProceedToCheckout,
}) => {
  if (!isOpen) return null;

  const subtotal = items.reduce((acc, item) => acc + item.product.price * item.quantity, 0);
  const shipping = subtotal > 100 || items.length === 0 ? 0.0 : 15.0;
  const estimatedTax = subtotal * 0.08;
  const total = subtotal + shipping + estimatedTax;

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside
        className="shop-cart-drawer"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="Shopping Cart"
      >
        {/* Drawer Header */}
        <div className="drawer-header">
          <div className="drawer-title-group">
            <ShoppingBag size={18} className="text-flow" />
            <h2 className="drawer-title">Shopping Cart</h2>
            <span className="drawer-count-badge font-mono">
              {items.reduce((s, i) => s + i.quantity, 0)} items
            </span>
          </div>
          <button
            type="button"
            className="drawer-close-btn"
            onClick={onClose}
            aria-label="Close cart"
          >
            <X size={18} />
          </button>
        </div>

        {/* Drawer Body: Item List */}
        <div className="drawer-body">
          {items.length === 0 ? (
            <div className="cart-empty-state">
              <div className="empty-icon-circle">
                <ShoppingBag size={32} className="text-muted" />
              </div>
              <h3 className="empty-title">Your cart is empty</h3>
              <p className="empty-subtitle">Browse our catalogue to add items to your cart.</p>
              <button
                type="button"
                className="btn-browse-catalog"
                onClick={onClose}
              >
                Browse Products
              </button>
            </div>
          ) : (
            <div className="cart-items-list">
              {items.map((item) => (
                <div key={item.product.id} className="cart-item-row">
                  <div className="item-thumb-box">
                    <ProductIllustration category={item.product.category} className="item-thumb-img" />
                  </div>

                  <div className="item-info-col">
                    <h4 className="item-name">{item.product.name}</h4>
                    <span className="item-unit-price font-mono">
                      ${item.product.price.toFixed(2)} each
                    </span>

                    <div className="item-stepper-row">
                      <div className="item-stepper">
                        <button
                          type="button"
                          className="item-step-btn"
                          onClick={() => onUpdateQuantity(item.product.id, item.quantity - 1)}
                          disabled={item.quantity <= 1}
                          aria-label="Decrease quantity"
                        >
                          <Minus size={11} />
                        </button>
                        <span className="item-step-val font-mono">{item.quantity}</span>
                        <button
                          type="button"
                          className="item-step-btn"
                          onClick={() => onUpdateQuantity(item.product.id, item.quantity + 1)}
                          disabled={item.quantity >= item.product.stock}
                          aria-label="Increase quantity"
                        >
                          <Plus size={11} />
                        </button>
                      </div>

                      <button
                        type="button"
                        className="btn-remove-item"
                        onClick={() => onRemoveItem(item.product.id)}
                        aria-label={`Remove ${item.product.name} from cart`}
                        title="Remove item"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </div>

                  <div className="item-total-col">
                    <span className="item-line-total font-mono">
                      ${(item.product.price * item.quantity).toFixed(2)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Drawer Footer: Order Summary & Checkout */}
        {items.length > 0 && (
          <div className="drawer-footer">
            <div className="cart-summary-box">
              <div className="summary-row">
                <span className="summary-label">Subtotal</span>
                <span className="summary-val font-mono">${subtotal.toFixed(2)}</span>
              </div>
              <div className="summary-row">
                <span className="summary-label">Shipping</span>
                <span className="summary-val font-mono">
                  {shipping === 0 ? <span className="text-healthy">FREE</span> : `$${shipping.toFixed(2)}`}
                </span>
              </div>
              <div className="summary-row">
                <span className="summary-label">Estimated Tax (8%)</span>
                <span className="summary-val font-mono">${estimatedTax.toFixed(2)}</span>
              </div>
              <div className="summary-divider" />
              <div className="summary-row total-row">
                <span className="total-label">Estimated Total</span>
                <span className="total-val font-mono">${total.toFixed(2)}</span>
              </div>
            </div>

            <button
              type="button"
              className="btn-checkout-primary"
              onClick={onProceedToCheckout}
            >
              <span>Proceed to Checkout</span>
              <ArrowRight size={16} />
            </button>

            <div className="drawer-footer-actions">
              <button
                type="button"
                className="btn-clear-cart"
                onClick={onClearCart}
              >
                Clear Cart
              </button>
              <div className="cart-security-badge">
                <ShieldCheck size={12} className="text-healthy" />
                <span>Idempotent Ingress Protected</span>
              </div>
            </div>
          </div>
        )}
      </aside>
    </div>
  );
};
