import React from 'react';
import { ShoppingCart, Star, Eye } from 'lucide-react';
import type { Product } from '../../api/ecommerceClient';
import { ProductIllustration } from './ProductIllustrations';

interface ProductCardProps {
  product: Product;
  onAddToCart: (product: Product) => void;
  onViewDetails: (product: Product) => void;
  isAdding?: boolean;
}

export const ProductCard: React.FC<ProductCardProps> = ({
  product,
  onAddToCart,
  onViewDetails,
  isAdding = false,
}) => {
  const isOutOfStock = product.stock <= 0;
  const isLowStock = product.stock > 0 && product.stock <= 10;

  return (
    <article className={`product-card ${isOutOfStock ? 'card-out-of-stock' : ''}`}>
      {/* Product Image / Illustration Header */}
      <div className="product-media-wrapper" onClick={() => onViewDetails(product)}>
        <ProductIllustration category={product.category} className="product-illustration" />
        <span className="product-category-tag">{product.category}</span>
        {isOutOfStock && <span className="stock-overlay-badge">Sold Out</span>}
      </div>

      {/* Product Content */}
      <div className="product-body">
        <div className="product-meta-row">
          <div className="product-rating">
            <Star size={13} className="star-icon" fill="currentColor" />
            <span className="rating-score font-mono">{product.rating ? product.rating.toFixed(1) : '4.8'}</span>
          </div>
          <span
            className={`stock-indicator-badge ${
              isOutOfStock ? 'stock-none' : isLowStock ? 'stock-low' : 'stock-ok'
            }`}
          >
            {isOutOfStock ? 'Out of Stock' : isLowStock ? `Low: ${product.stock} left` : `In Stock (${product.stock})`}
          </span>
        </div>

        <h3 className="product-title" onClick={() => onViewDetails(product)} title={product.name}>
          {product.name}
        </h3>

        <p className="product-description">{product.description}</p>

        {/* Pricing & Add to Cart Footer */}
        <div className="product-footer">
          <div className="price-box">
            <span className="currency-symbol">$</span>
            <span className="price-amount font-mono">{product.price.toFixed(2)}</span>
          </div>

          <div className="card-actions">
            <button
              type="button"
              className="btn-quick-view"
              onClick={() => onViewDetails(product)}
              title="Inspect specifications & authoritative live inventory"
              aria-label={`View details for ${product.name}`}
            >
              <Eye size={14} />
            </button>

            <button
              type="button"
              className={`btn-add-cart ${isOutOfStock ? 'disabled' : ''}`}
              disabled={isOutOfStock || isAdding}
              onClick={() => onAddToCart(product)}
              aria-label={`Add ${product.name} to cart`}
            >
              <ShoppingCart size={14} />
              <span>{isOutOfStock ? 'Unavailable' : isAdding ? 'Adding...' : 'Add to Cart'}</span>
            </button>
          </div>
        </div>
      </div>
    </article>
  );
};
