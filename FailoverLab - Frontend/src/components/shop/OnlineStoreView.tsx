import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  RefreshCw,
  AlertTriangle,
  ShoppingBag,
  Sparkles,
  WifiOff,
} from 'lucide-react';
import {
  ecommerceClient,
  RateLimitError,
} from '../../api/ecommerceClient';
import type {
  Product,
  CartItem,
  OrderConfirmation,
  GatewayResponseMetadata,
} from '../../api/ecommerceClient';
import { ShopHeader } from './ShopHeader';
import { ProductCard } from './ProductCard';
import { ProductDetailModal } from './ProductDetailModal';
import { CartDrawer } from './CartDrawer';
import { CheckoutModal } from './CheckoutModal';
import { OrderConfirmationView } from './OrderConfirmationView';
import { GatewayInspectorBar } from './GatewayInspectorBar';
import './Shop.css';

interface OnlineStoreViewProps {
  onNavigateToConsole: () => void;
}

export const OnlineStoreView: React.FC<OnlineStoreViewProps> = ({ onNavigateToConsole }) => {
  // Region Selection State
  const [selectedRegion, setSelectedRegion] = useState<string>(() => {
    return localStorage.getItem('failoverlab_client_region') || 'ap-south-1';
  });

  // Catalog & Filter State
  const [products, setProducts] = useState<Product[]>([]);
  const [isLoadingCatalog, setIsLoadingCatalog] = useState(true);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<string>('All');
  const [searchQuery, setSearchQuery] = useState<string>('');

  // Cart State (Persisted in localStorage)
  const [cart, setCart] = useState<CartItem[]>(() => {
    try {
      const saved = localStorage.getItem('failoverlab_shop_cart');
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });

  // Modal / UI States
  const [isCartOpen, setIsCartOpen] = useState(false);
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [isCheckoutOpen, setIsCheckoutOpen] = useState(false);
  const [completedOrder, setCompletedOrder] = useState<{
    order: OrderConfirmation;
    metadata: GatewayResponseMetadata;
  } | null>(null);

  // Gateway Route Telemetry State
  const [lastMetadata, setLastMetadata] = useState<GatewayResponseMetadata | null>(null);
  const [isInspectorOpen, setIsInspectorOpen] = useState(false);
  const [rateLimitCountdown, setRateLimitCountdown] = useState<number | null>(null);

  // Save cart changes
  useEffect(() => {
    try {
      localStorage.setItem('failoverlab_shop_cart', JSON.stringify(cart));
    } catch (e) {
      // Storage unavailable
    }
  }, [cart]);

  // Save region preference
  useEffect(() => {
    localStorage.setItem('failoverlab_client_region', selectedRegion);
  }, [selectedRegion]);

  // Load Catalog from Gateway
  const fetchCatalog = useCallback(async () => {
    setIsLoadingCatalog(true);
    setCatalogError(null);
    try {
      const { products: fetched, metadata } = await ecommerceClient.getCatalog(selectedRegion);
      setProducts(fetched);
      setLastMetadata(metadata);
    } catch (err: any) {
      if (err instanceof RateLimitError) {
        setCatalogError(`Traffic limit reached (${err.mode}). Retrying in ${err.retryAfterSeconds}s.`);
        setRateLimitCountdown(err.retryAfterSeconds);
      } else {
        setCatalogError(err?.message || 'Could not load products. Verify that Gateway is operational.');
      }
    } finally {
      setIsLoadingCatalog(false);
    }
  }, [selectedRegion]);

  useEffect(() => {
    fetchCatalog();
  }, [fetchCatalog]);

  // Countdown timer for 429 rate limit
  useEffect(() => {
    if (rateLimitCountdown === null) return;
    const interval = setInterval(() => {
      setRateLimitCountdown((prev) => {
        if (prev === null || prev <= 1) {
          clearInterval(interval);
          fetchCatalog();
          return null;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [rateLimitCountdown, fetchCatalog]);

  // Compute Categories from products
  const categories = useMemo(() => {
    const set = new Set<string>();
    set.add('All');
    products.forEach((p) => {
      if (p.category) set.add(p.category);
    });
    return Array.from(set);
  }, [products]);

  // Filtered Products
  const filteredProducts = useMemo(() => {
    return products.filter((p) => {
      const matchesCategory =
        selectedCategory === 'All' || p.category.toLowerCase() === selectedCategory.toLowerCase();
      const matchesSearch =
        !searchQuery.trim() ||
        p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        p.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
        p.category.toLowerCase().includes(searchQuery.toLowerCase());
      return matchesCategory && matchesSearch;
    });
  }, [products, selectedCategory, searchQuery]);

  // Cart actions
  const handleAddToCart = (product: Product, quantityToAdd: number = 1) => {
    setCart((prev) => {
      const existingIndex = prev.findIndex((item) => item.product.id === product.id);
      if (existingIndex > -1) {
        const next = [...prev];
        const newQty = Math.min(product.stock, next[existingIndex].quantity + quantityToAdd);
        next[existingIndex] = { ...next[existingIndex], quantity: newQty };
        return next;
      }
      return [...prev, { product, quantity: Math.min(product.stock, quantityToAdd) }];
    });
  };

  const handleUpdateQuantity = (productId: string, quantity: number) => {
    if (quantity <= 0) {
      handleRemoveItem(productId);
      return;
    }
    setCart((prev) =>
      prev.map((item) => (item.product.id === productId ? { ...item, quantity } : item))
    );
  };

  const handleRemoveItem = (productId: string) => {
    setCart((prev) => prev.filter((item) => item.product.id !== productId));
  };

  const handleClearCart = () => {
    setCart([]);
  };

  const handleProceedToCheckout = () => {
    setIsCartOpen(false);
    setIsCheckoutOpen(true);
  };

  const handleOrderSuccess = (order: OrderConfirmation, metadata: GatewayResponseMetadata) => {
    setIsCheckoutOpen(false);
    setCart([]);
    setLastMetadata(metadata);
    setCompletedOrder({ order, metadata });

    // Deduct stock in local view
    setProducts((prev) =>
      prev.map((p) => {
        const matchingItem = order.items?.find((i) => i.product_id === p.id);
        if (matchingItem) {
          return { ...p, stock: Math.max(0, p.stock - matchingItem.quantity) };
        }
        if (p.id === order.product_id && order.quantity) {
          return { ...p, stock: Math.max(0, p.stock - order.quantity) };
        }
        return p;
      })
    );
  };

  const totalCartCount = cart.reduce((sum, item) => sum + item.quantity, 0);

  return (
    <div className="failover-shop-root">
      {/* Customer Header & Navigation */}
      <ShopHeader
        selectedRegion={selectedRegion}
        onSelectRegion={setSelectedRegion}
        cartCount={totalCartCount}
        onOpenCart={() => setIsCartOpen(true)}
        onNavigateToConsole={onNavigateToConsole}
        selectedCategory={selectedCategory}
        onSelectCategory={setSelectedCategory}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        categories={categories}
        isInspectorOpen={isInspectorOpen}
        onToggleInspector={() => setIsInspectorOpen(!isInspectorOpen)}
      />

      {/* Main Store Content Area */}
      <main className="shop-main-content">
        {completedOrder ? (
          <OrderConfirmationView
            order={completedOrder.order}
            metadata={completedOrder.metadata}
            onContinueShopping={() => setCompletedOrder(null)}
            onNavigateToConsole={onNavigateToConsole}
          />
        ) : (
          <div className="shop-container">
            {/* Rate-Limit Warning Banner */}
            {rateLimitCountdown !== null && (
              <div className="rate-limit-banner">
                <AlertTriangle size={16} className="text-warning" />
                <div className="banner-content">
                  <strong>Traffic Throttling Triggered</strong>
                  <p>
                    FailoverLab Gateway rate limiter is enforcing traffic shaping. Refilling in{' '}
                    <span className="font-mono text-warning font-bold">{rateLimitCountdown}s</span>.
                  </p>
                </div>
              </div>
            )}

            {/* Error State */}
            {catalogError && rateLimitCountdown === null && (
              <div className="catalog-error-box">
                <WifiOff size={24} className="text-danger" />
                <div className="error-text">
                  <h3>Catalog Load Failure</h3>
                  <p>{catalogError}</p>
                </div>
                <button
                  type="button"
                  className="btn-retry-catalog"
                  onClick={fetchCatalog}
                >
                  <RefreshCw size={14} />
                  <span>Retry Request</span>
                </button>
              </div>
            )}

            {/* Catalog Hero Banner */}
            <div className="shop-hero-banner">
              <div className="hero-content">
                <span className="hero-tag">
                  <Sparkles size={13} className="text-flow" />
                  <span>Enterprise Multi-Region Delivery</span>
                </span>
                <h2 className="hero-title">High-Performance Hardware & Peripherals</h2>
                <p className="hero-desc">
                  Simulating realistic customer transactions routed across 5 data regions with single-writer guarantees, replication lag protection, and guarded failover.
                </p>
              </div>
            </div>

            {/* Products Grid */}
            <div className="catalog-section-header">
              <h3 className="section-title">
                {selectedCategory === 'All' ? 'All Products' : selectedCategory}
              </h3>
              <span className="section-count font-mono">
                {isLoadingCatalog ? 'Loading catalog...' : `${filteredProducts.length} items`}
              </span>
            </div>

            {isLoadingCatalog ? (
              <div className="product-skeleton-grid">
                {[1, 2, 3, 4, 5].map((i) => (
                  <div key={i} className="product-skeleton-card">
                    <div className="skeleton-media" />
                    <div className="skeleton-line short" />
                    <div className="skeleton-line title" />
                    <div className="skeleton-line desc" />
                    <div className="skeleton-footer" />
                  </div>
                ))}
              </div>
            ) : filteredProducts.length === 0 ? (
              <div className="catalog-empty-state">
                <ShoppingBag size={40} className="text-muted" />
                <h3>No products found</h3>
                <p>Try searching for a different keyword or select another category.</p>
                <button
                  type="button"
                  className="btn-reset-filters"
                  onClick={() => {
                    setSelectedCategory('All');
                    setSearchQuery('');
                  }}
                >
                  Reset Filters
                </button>
              </div>
            ) : (
              <div className="products-grid">
                {filteredProducts.map((prod) => (
                  <ProductCard
                    key={prod.id}
                    product={prod}
                    onAddToCart={(p) => handleAddToCart(p, 1)}
                    onViewDetails={(p) => setSelectedProduct(p)}
                  />
                ))}
              </div>
            )}
          </div>
        )}
      </main>

      {/* Product Detail Modal */}
      <ProductDetailModal
        product={selectedProduct}
        onClose={() => setSelectedProduct(null)}
        onAddToCart={handleAddToCart}
        selectedRegion={selectedRegion}
      />

      {/* Shopping Cart Drawer */}
      <CartDrawer
        isOpen={isCartOpen}
        onClose={() => setIsCartOpen(false)}
        items={cart}
        onUpdateQuantity={handleUpdateQuantity}
        onRemoveItem={handleRemoveItem}
        onClearCart={handleClearCart}
        onProceedToCheckout={handleProceedToCheckout}
      />

      {/* Checkout Modal */}
      <CheckoutModal
        isOpen={isCheckoutOpen}
        onClose={() => setIsCheckoutOpen(false)}
        items={cart}
        selectedRegion={selectedRegion}
        onOrderSuccess={handleOrderSuccess}
      />

      {/* Docked Gateway Route Inspector */}
      <GatewayInspectorBar
        metadata={lastMetadata}
        isOpen={isInspectorOpen}
        onToggle={() => setIsInspectorOpen(!isInspectorOpen)}
        selectedRegion={selectedRegion}
      />
    </div>
  );
};
