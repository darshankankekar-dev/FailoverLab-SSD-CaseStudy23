import React from 'react';

interface MetricDisplayProps {
  label: string;
  value: string | number;
  unit?: string;
  subtext?: string;
  tone?: 'normal' | 'healthy' | 'warning' | 'danger' | 'flow';
  className?: string;
}

export const MetricDisplay: React.FC<MetricDisplayProps> = ({
  label,
  value,
  unit,
  subtext,
  tone = 'normal',
  className = '',
}) => {
  const toneClass =
    tone === 'healthy'
      ? 'text-healthy'
      : tone === 'warning'
      ? 'text-warning'
      : tone === 'danger'
      ? 'text-danger'
      : tone === 'flow'
      ? 'text-flow'
      : 'text-bright';

  return (
    <div className={`metric-display ${className}`}>
      <div className="metric-label text-muted text-xs font-medium uppercase tracking-wider">
        {label}
      </div>
      <div className="metric-value-row flex items-baseline gap-1 mt-0.5">
        <span className={`metric-value font-mono font-bold text-lg ${toneClass}`}>
          {value}
        </span>
        {unit && (
          <span className="metric-unit text-muted text-xs font-mono">
            {unit}
          </span>
        )}
      </div>
      {subtext && (
        <div className="metric-subtext text-dim text-xs mt-0.5">
          {subtext}
        </div>
      )}
    </div>
  );
};
