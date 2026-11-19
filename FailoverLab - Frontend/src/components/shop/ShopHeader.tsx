import React, { useState } from 'react';
import {
  ShoppingBag,
  ShoppingCart,
  Globe,
  Sliders,
  ArrowLeft,
  Search,
  Check,
  ChevronDown,
} from 'lucide-react';
import { CLIENT_REGIONS } from '../../api/ecommerceClient';
import type { ClientRegionOption } from '../../api/ecommerceClient';

interface ShopHeaderProps {
  selectedRegion: string;
  onSelectRegion: (regionId: string) => void;
  cartCount: number;
  onOpenCart: () => void;
  onNavigateToConsole: () => void;
  onNavigateToController?: () => void;
  selectedCategory: string;
  onSelectCategory: (cat: string) => void;
  searchQuery: string;
  onSearchChange: (query: string) => void;
  categories: string[];
  isInspectorOpen: boolean;
  onToggleInspector: () => void;
}

export const ShopHeader: React.FC<ShopHeaderProps> = ({
  selectedRegion,
  onSelectRegion,
  cartCount,
  onOpenCart,
  onNavigateToConsole,
  onNavigateToController,
  selectedCategory,
  onSelectCategory,
  searchQuery,
  onSearchChange,
  categories,
  isInspectorOpen,
  onToggleInspector,
}) => {
  const [isRegionMenuOpen, setIsRegionMenuOpen] = useState(false);
  const currentRegion = CLIENT_REGIONS.find((r) => r.id === selectedRegion) || CLIENT_REGIONS[0];

  return (
    <header className="shop-header">
      {/* Top Banner: Global Ingress & Console Link */}
      <div className="shop-top-announcement">
        <div className="shop-container shop-announcement-inner">
          <div className="announcement-left">
            <span className="announcement-badge">FAILOVERLAB DEMO STORE</span>
            <span className="announcement-text">
              Real-world distributed traffic simulation routed via Gateway (Port 8080)
            </span>
          </div>

          <div className="announcement-right">
            {/* Live Client Region Selector Dropdown */}
            <div className="region-selector-wrapper">
              <button
                type="button"
                className="region-selector-btn"
                onClick={() => setIsRegionMenuOpen(!isRegionMenuOpen)}
                title="Change your simulated customer browsing location"
              >
                <Globe size={13} className="text-flow" />
                <span className="region-flag font-mono font-semibold">[{currentRegion.countryCode || currentRegion.flag}]</span>
                <span className="region-name">{currentRegion.name}</span>
                <ChevronDown size={12} className={`chevron-icon ${isRegionMenuOpen ? 'open' : ''}`} />
              </button>

              {isRegionMenuOpen && (
                <div className="region-dropdown-menu">
                  <div className="dropdown-header">
                    <span className="dropdown-title">Select Customer Location</span>
                    <span className="dropdown-desc">Sets X-Client-Region header for WAN latency routing</span>
                  </div>
                  {CLIENT_REGIONS.map((reg: ClientRegionOption) => (
                    <button
                      key={reg.id}
                      type="button"
                      className={`region-option-item ${reg.id === selectedRegion ? 'selected' : ''}`}
                      onClick={() => {
                        onSelectRegion(reg.id);
                        setIsRegionMenuOpen(false);
                      }}
                    >
                      <span className="option-flag font-mono font-bold">[{reg.countryCode || reg.flag}]</span>
                      <div className="option-info">
                        <span className="option-name">{reg.name}</span>
                        <span className="option-latency font-mono">{reg.zone} • ~{reg.nominalLatency}</span>
                      </div>
                      {reg.id === selectedRegion && <Check size={14} className="check-icon" />}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Toggle Gateway Route Inspector */}
            <button
              type="button"
              className={`shop-pill-btn ${isInspectorOpen ? 'active' : ''}`}
              onClick={onToggleInspector}
              title="Toggle Gateway Telemetry Inspector"
            >
              <Sliders size={13} />
              <span>Route Telemetry</span>
            </button>

            {/* Link to Controller Console */}
            {onNavigateToController && (
              <button
                type="button"
                className="shop-pill-btn"
                style={{ background: 'rgba(14, 165, 233, 0.2)', borderColor: '#0284c7', color: '#38bdf8' }}
                onClick={onNavigateToController}
                title="Open Controller Observability Console"
              >
                <Sliders size={13} />
                <span>Controller Console</span>
              </button>
            )}

            {/* Link to Root Operations Dashboard */}
            <button
              type="button"
              className="shop-pill-btn console-return-btn"
              onClick={onNavigateToConsole}
              title="Return to FailoverLab Operations Dashboard"
            >
              <ArrowLeft size={13} />
              <span>Operations Console</span>
            </button>
          </div>
        </div>
      </div>

      {/* Main Navbar */}
      <div className="shop-main-nav">
        <div className="shop-container shop-nav-inner">
          <div className="shop-brand">
            <div className="brand-logo-mark">
              <ShoppingBag size={18} className="brand-icon" />
            </div>
            <div className="brand-titles">
              <h1 className="brand-name">AuraStore</h1>
              <span className="brand-tagline">Infrastructure & Hardware Gear</span>
            </div>
          </div>

          {/* Search Bar */}
          <div className="shop-search-bar">
            <Search size={15} className="search-icon" />
            <input
              type="text"
              placeholder="Search catalog (e.g. laptop, 4K, audio)..."
              value={searchQuery}
              onChange={(e) => onSearchChange(e.target.value)}
              className="shop-search-input"
            />
            {searchQuery && (
              <button
                type="button"
                className="search-clear-btn"
                onClick={() => onSearchChange('')}
              >
                ×
              </button>
            )}
          </div>

          {/* Cart Button with Count Badge */}
          <button
            type="button"
            className="shop-cart-btn"
            onClick={onOpenCart}
            aria-label="View Shopping Cart"
          >
            <ShoppingCart size={18} />
            <span className="cart-btn-label">Cart</span>
            {cartCount > 0 && <span className="cart-badge font-mono">{cartCount}</span>}
          </button>
        </div>
      </div>

      {/* Category Pills Bar */}
      <div className="shop-category-bar">
        <div className="shop-container category-pills-list">
          {categories.map((cat) => (
            <button
              key={cat}
              type="button"
              className={`category-pill ${selectedCategory === cat ? 'active' : ''}`}
              onClick={() => onSelectCategory(cat)}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>
    </header>
  );
};
