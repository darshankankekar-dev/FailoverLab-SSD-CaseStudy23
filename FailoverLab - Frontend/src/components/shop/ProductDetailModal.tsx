import React, { useState, useEffect } from 'react';
import {
  X,
  ShoppingCart,
  Star,
  CheckCircle2,
  RefreshCw,
  Plus,
  Minus,
  Server,
} from 'lucide-react';
import { ecommerceClient } from '../../api/ecommerceClient';
import type { Product, GatewayResponseMetadata } from '../../api/ecommerceClient';
import { ProductIllustration } from './ProductIllustrations';

interface ProductDetailModalProps {
  product: Product | null;
  onClose: () => void;
  onAddToCart: (product: Product, quantity: number) => void;
  selectedRegion: string;
}

export const ProductDetailModal: React.FC<ProductDetailModalProps> = ({
  product,
  onClose,
  onAddToCart,
  selectedRegion,
}) => {
  const [quantity, setQuantity] = useState(1);
  const [liveStock, setLiveStock] = useState<number | null>(null);
  const [isLoadingStock, setIsLoadingStock] = useState(false);
  const [stockMetadata, setStockMetadata] = useState<GatewayResponseMetadata | null>(null);
  const [addedAnimation, setAddedAnimation] = useState(false);

  useEffect(() => {
    if (!product) return;
    setQuantity(1);
    setLiveStock(product.stock);

    let isMounted = true;
    const fetchStrongInventory = async () => {
      setIsLoadingStock(true);
      try {
        const { stock, metadata } = await ecommerceClient.getProductInventory(product.id, selectedRegion);
        if (isMounted) {
          setLiveStock(stock);
          setStockMetadata(metadata);
        }
      } catch (err) {
        // Fallback to catalog cached stock
        if (isMounted) setLiveStock(product.stock);
      } finally {
        if (isMounted) setIsLoadingStock(false);
      }
    };

    fetchStrongInventory();
    return () => {
      isMounted = false;
    };
  }, [product, selectedRegion]);

  if (!product) return null;

  const currentStock = liveStock !== null ? liveStock : product.stock;
  const isOutOfStock = currentStock <= 0;

  const handleAdd = () => {
    onAddToCart(product, quantity);
    setAddedAnimation(true);
    setTimeout(() => {
      setAddedAnimation(false);
      onClose();
    }, 600);
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="shop-detail-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-labelledby="product-detail-title"
      >
        <button
          type="button"
          className="modal-close-btn"
          onClick={onClose}
          aria-label="Close modal"
        >
          <X size={18} />
        </button>

        <div className="detail-grid">
          {/* Left: Product Visual */}
          <div className="detail-media-column">
            <div className="detail-illustration-box">
              <ProductIllustration category={product.category} className="detail-illustration" />
            </div>
            <div className="detail-badges-row">
              <span className="detail-category-badge">{product.category}</span>
              <div className="detail-rating-pill">
                <Star size={13} fill="currentColor" className="text-warning" />
                <span className="font-mono">{product.rating ? product.rating.toFixed(1) : '4.8'}</span>
              </div>
            </div>
          </div>

          {/* Right: Product Information & Controls */}
          <div className="detail-info-column">
            <h2 id="product-detail-title" className="detail-title">{product.name}</h2>
            <div className="detail-price-row">
              <span className="detail-price font-mono">${product.price.toFixed(2)}</span>
              <span className="detail-vat-note">Taxes & shipping calculated at checkout</span>
            </div>

            <p className="detail-description">{product.description}</p>

            {/* Authoritative Live Inventory Check */}
            <div className="detail-stock-box">
              <div className="stock-header">
                <div className="stock-title-left">
                  <Server size={14} className="text-flow" />
                  <span className="stock-label">Strong-Consistency Live Stock:</span>
                </div>
                {isLoadingStock ? (
                  <RefreshCw size={12} className="spin text-muted" />
                ) : (
                  <span className={`stock-val-pill ${isOutOfStock ? 'pill-none' : currentStock < 10 ? 'pill-low' : 'pill-ok'}`}>
                    {isOutOfStock ? '0 units (Out of Stock)' : `${currentStock} units available`}
                  </span>
                )}
              </div>

              {stockMetadata && (
                <div className="stock-telemetry-note font-mono">
                  Verified via Gateway → {stockMetadata.servedRegion} ({stockMetadata.latencyMs}ms)
                </div>
              )}
            </div>

            {/* Quantity Selector & Add to Cart */}
            <div className="detail-actions-section">
              <div className="quantity-control-group">
                <span className="qty-label">Quantity:</span>
                <div className="qty-stepper">
                  <button
                    type="button"
                    className="stepper-btn"
                    disabled={quantity <= 1 || isOutOfStock}
                    onClick={() => setQuantity(Math.max(1, quantity - 1))}
                    aria-label="Decrease quantity"
                  >
                    <Minus size={13} />
                  </button>
                  <span className="stepper-value font-mono">{quantity}</span>
                  <button
                    type="button"
                    className="stepper-btn"
                    disabled={quantity >= currentStock || isOutOfStock}
                    onClick={() => setQuantity(Math.min(currentStock, quantity + 1))}
                    aria-label="Increase quantity"
                  >
                    <Plus size={13} />
                  </button>
                </div>
              </div>

              <button
                type="button"
                className={`btn-detail-add-cart ${addedAnimation ? 'btn-added' : ''}`}
                disabled={isOutOfStock}
                onClick={handleAdd}
              >
                {addedAnimation ? (
                  <>
                    <CheckCircle2 size={16} />
                    <span>Added to Cart!</span>
                  </>
                ) : (
                  <>
                    <ShoppingCart size={16} />
                    <span>{isOutOfStock ? 'Out of Stock' : `Add to Cart • $${(product.price * quantity).toFixed(2)}`}</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
