import React from 'react';

const REGION_MAP: Record<string, { code: string; name: string; zone: string }> = {
  'region-a': { code: 'IN', name: 'Mumbai', zone: 'ap-south-1' },
  'region-b': { code: 'SG', name: 'Singapore', zone: 'ap-southeast-1' },
  'region-c': { code: 'DE', name: 'Frankfurt', zone: 'eu-central-1' },
  'region-d': { code: 'US', name: 'Virginia', zone: 'us-east-1' },
  'region-e': { code: 'BR', name: 'São Paulo', zone: 'sa-east-1' },
  'ap-south-1': { code: 'IN', name: 'Mumbai', zone: 'ap-south-1' },
  'ap-southeast-1': { code: 'SG', name: 'Singapore', zone: 'ap-southeast-1' },
  'eu-central-1': { code: 'DE', name: 'Frankfurt', zone: 'eu-central-1' },
  'us-east-1': { code: 'US', name: 'Virginia', zone: 'us-east-1' },
  'sa-east-1': { code: 'BR', name: 'São Paulo', zone: 'sa-east-1' },
};

interface RegionBadgeProps {
  regionId: string;
  showZone?: boolean;
  className?: string;
}

export const RegionBadge: React.FC<RegionBadgeProps> = ({
  regionId,
  showZone = true,
  className = '',
}) => {
  const info = REGION_MAP[regionId] || { code: 'GL', name: regionId, zone: regionId };

  return (
    <span
      className={`region-badge inline-flex items-center gap-1.5 font-mono text-xs ${className}`}
      style={{
        padding: '1px 5px',
        background: 'var(--bg-subtle)',
        border: '1px solid var(--border-default)',
        borderRadius: 'var(--radius-xs)',
      }}
    >
      <span
        style={{
          fontSize: '0.65rem',
          fontWeight: 700,
          color: 'var(--text-muted)',
          letterSpacing: '0.04em',
        }}
      >
        [{info.code}]
      </span>
      <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>
        {info.name}
      </span>
      {showZone && (
        <span style={{ color: 'var(--text-dim)', fontSize: '0.7rem' }}>
          ({info.zone})
        </span>
      )}
    </span>
  );
};
