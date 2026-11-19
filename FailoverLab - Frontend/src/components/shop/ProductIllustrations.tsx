import React from 'react';

interface IllustrationProps {
  category: string;
  className?: string;
}

export const ProductIllustration: React.FC<IllustrationProps> = ({ category, className = '' }) => {
  const cat = category.toLowerCase();

  // Laptop / Workstation schematic
  if (cat.includes('laptop') || cat.includes('workstation')) {
    return (
      <svg viewBox="0 0 120 90" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
        <rect x="22" y="14" width="76" height="48" rx="2" fill="#141926" stroke="#242e42" strokeWidth="1.5" />
        <rect x="26" y="18" width="68" height="40" rx="1" fill="#0d111a" />
        <path d="M36 34H84M36 40H66M36 46H74" stroke="#3b82f6" strokeWidth="1.5" strokeLinecap="round" opacity="0.8" />
        <circle cx="60" cy="16" r="1" fill="#64748b" />
        <path d="M14 66H106L102 74H18L14 66Z" fill="#1a2130" stroke="#242e42" strokeWidth="1.5" />
        <rect x="48" y="68" width="24" height="2" rx="1" fill="#64748b" />
      </svg>
    );
  }

  // Smartphone / Edge Handheld schematic
  if (cat.includes('phone') || cat.includes('handheld') || cat.includes('mobile')) {
    return (
      <svg viewBox="0 0 90 110" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
        <rect x="24" y="10" width="42" height="90" rx="3" fill="#141926" stroke="#242e42" strokeWidth="1.5" />
        <rect x="27" y="16" width="36" height="78" rx="2" fill="#0d111a" />
        <circle cx="45" cy="13" r="1" fill="#64748b" />
        <rect x="32" y="26" width="26" height="16" rx="2" fill="#1a2130" stroke="#333f56" strokeWidth="1" />
        <path d="M32 52H58M32 58H48M32 64H54" stroke="#3b82f6" strokeWidth="1.25" strokeLinecap="round" opacity="0.8" />
        <line x1="38" y1="88" x2="52" y2="88" stroke="#475569" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    );
  }

  // Audio / Headset schematic
  if (cat.includes('audio') || cat.includes('head') || cat.includes('sound')) {
    return (
      <svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
        <path d="M24 55C24 36 35 22 50 22C65 22 76 36 76 55" stroke="#334155" strokeWidth="2.5" strokeLinecap="round" />
        <rect x="16" y="50" width="16" height="28" rx="2" fill="#141926" stroke="#242e42" strokeWidth="1.5" />
        <rect x="68" y="50" width="16" height="28" rx="2" fill="#141926" stroke="#242e42" strokeWidth="1.5" />
        <line x1="32" y1="64" x2="68" y2="64" stroke="#3b82f6" strokeWidth="1" strokeDasharray="2 3" opacity="0.7" />
        <circle cx="50" cy="22" r="2" fill="#475569" />
      </svg>
    );
  }

  // Wearables / Sensor Watch schematic
  if (cat.includes('watch') || cat.includes('wear') || cat.includes('sensor')) {
    return (
      <svg viewBox="0 0 90 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
        <rect x="36" y="8" width="18" height="22" rx="1" fill="#1a2130" stroke="#242e42" strokeWidth="1.2" />
        <rect x="36" y="70" width="18" height="22" rx="1" fill="#1a2130" stroke="#242e42" strokeWidth="1.2" />
        <rect x="25" y="26" width="40" height="48" rx="3" fill="#141926" stroke="#242e42" strokeWidth="1.5" />
        <rect x="29" y="30" width="32" height="40" rx="2" fill="#0d111a" />
        <circle cx="45" cy="50" r="10" stroke="#334155" strokeWidth="1.2" strokeDasharray="3 2" />
        <polyline points="45,44 45,50 49,53" stroke="#3b82f6" strokeWidth="1.2" strokeLinecap="round" />
      </svg>
    );
  }

  // Default: Enterprise Display / Server Rack schematic
  return (
    <svg viewBox="0 0 110 95" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
      <rect x="12" y="10" width="86" height="54" rx="2" fill="#141926" stroke="#242e42" strokeWidth="1.5" />
      <rect x="16" y="14" width="78" height="46" rx="1" fill="#0d111a" />
      <path d="M26 34L45 44L60 38L84 50" stroke="#3b82f6" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" opacity="0.85" />
      <rect x="52" y="64" width="6" height="14" fill="#1e2638" />
      <path d="M38 78H72" stroke="#242e42" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  );
};
