import React from 'react';

export type StatusTone = 'healthy' | 'warning' | 'danger' | 'flow' | 'standby';

interface StatusDotProps {
  status: StatusTone;
  size?: number;
  className?: string;
  title?: string;
}

export const StatusDot: React.FC<StatusDotProps> = ({
  status,
  size = 6,
  className = '',
  title,
}) => {
  const colorMap: Record<StatusTone, string> = {
    healthy: 'var(--status-healthy)',
    warning: 'var(--status-warning)',
    danger: 'var(--status-danger)',
    flow: 'var(--accent-blue)',
    standby: 'var(--text-muted)',
  };

  return (
    <span
      className={`status-dot ${className}`}
      title={title}
      style={{
        width: `${size}px`,
        height: `${size}px`,
        borderRadius: '50%',
        backgroundColor: colorMap[status] || colorMap.standby,
        display: 'inline-block',
        flexShrink: 0,
      }}
    />
  );
};
