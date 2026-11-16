import React from 'react';

interface IllustrationProps {
  category: string;
  className?: string;
}

export const ProductIllustration: React.FC<IllustrationProps> = ({ category, className = '' }) => {
  const cat = category.toLowerCase();

  if (cat.includes('laptop')) {
    return (
      <svg viewBox="0 0 120 90" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
        <rect x="22" y="14" width="76" height="48" rx="4" fill="#1e293b" stroke="#38bdf8" strokeWidth="2" />
        <rect x="28" y="20" width="64" height="36" rx="2" fill="#0f172a" />
        <path d="M40 38H80M40 44H65" stroke="#38bdf8" strokeWidth="2" strokeLinecap="round" />
        <circle cx="60" cy="17" r="1.5" fill="#38bdf8" />
        <path d="M12 66H108C110 66 111 67.5 110 69L105 74C104 75 102 76 100 76H20C18 76 16 75 15 74L10 69C9 67.5 10 66 12 66Z" fill="#334155" stroke="#475569" strokeWidth="1.5" />
        <rect x="50" y="67" width="20" height="2" rx="1" fill="#94a3b8" />
      </svg>
    );
  }

  if (cat.includes('phone') || cat.includes('smartphone')) {
    return (
      <svg viewBox="0 0 90 110" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
        <rect x="22" y="10" width="46" height="90" rx="8" fill="#1e293b" stroke="#818cf8" strokeWidth="2" />
        <rect x="26" y="16" width="38" height="78" rx="4" fill="#0f172a" />
        <circle cx="45" cy="13" r="1.5" fill="#818cf8" />
        <rect x="32" y="30" width="26" height="18" rx="3" fill="#312e81" stroke="#6366f1" strokeWidth="1" />
        <path d="M32 58H58M32 64H48" stroke="#818cf8" strokeWidth="1.5" strokeLinecap="round" />
        <line x1="38" y1="90" x2="52" y2="90" stroke="#64748b" strokeWidth="2" strokeLinecap="round" />
      </svg>
    );
  }

  if (cat.includes('audio') || cat.includes('head')) {
    return (
      <svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
        <path d="M22 55C22 35 34 20 50 20C66 20 78 35 78 55" stroke="#34d399" strokeWidth="3" strokeLinecap="round" />
        <rect x="14" y="50" width="16" height="28" rx="6" fill="#1e293b" stroke="#34d399" strokeWidth="2" />
        <rect x="70" y="50" width="16" height="28" rx="6" fill="#1e293b" stroke="#34d399" strokeWidth="2" />
        <line x1="30" y1="64" x2="70" y2="64" stroke="#10b981" strokeWidth="1" strokeDasharray="2 3" />
        <circle cx="50" cy="20" r="3" fill="#10b981" />
      </svg>
    );
  }

  if (cat.includes('watch') || cat.includes('wear')) {
    return (
      <svg viewBox="0 0 90 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
        <rect x="35" y="8" width="20" height="22" rx="3" fill="#334155" stroke="#475569" strokeWidth="1.5" />
        <rect x="35" y="70" width="20" height="22" rx="3" fill="#334155" stroke="#475569" strokeWidth="1.5" />
        <rect x="24" y="26" width="42" height="48" rx="10" fill="#1e293b" stroke="#fbbf24" strokeWidth="2" />
        <rect x="28" y="30" width="34" height="40" rx="6" fill="#0f172a" />
        <circle cx="45" cy="50" r="10" stroke="#f59e0b" strokeWidth="1.5" strokeDasharray="3 2" />
        <polyline points="45,44 45,50 49,53" stroke="#fef3c7" strokeWidth="1.5" strokeLinecap="round" />
        <circle cx="68" cy="42" r="2" fill="#fbbf24" />
      </svg>
    );
  }

  // Default: Monitor / Display
  return (
    <svg viewBox="0 0 110 95" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
      <rect x="12" y="10" width="86" height="54" rx="4" fill="#1e293b" stroke="#f43f5e" strokeWidth="2" />
      <rect x="16" y="14" width="78" height="46" rx="2" fill="#0f172a" />
      <path d="M26 30L45 42L60 34L84 50" stroke="#f43f5e" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <rect x="52" y="64" width="6" height="14" fill="#475569" />
      <path d="M38 78H72" stroke="#64748b" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
};
