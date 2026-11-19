import React from 'react';
import {
  LayoutDashboard,
  Activity,
  Globe2,
  GitBranch,
  History,
} from 'lucide-react';

export type ControllerTabId = 'overview' | 'traffic' | 'regional' | 'replication' | 'history';

interface ControllerNavTabsProps {
  activeTab: ControllerTabId;
  onSelectTab: (tab: ControllerTabId) => void;
  eventCount?: number;
  replicationLag?: number;
}

export const ControllerNavTabs: React.FC<ControllerNavTabsProps> = ({
  activeTab,
  onSelectTab,
  eventCount,
  replicationLag,
}) => {
  const tabs: Array<{ id: ControllerTabId; label: string; icon: React.ReactNode; badge?: string | number }> = [
    {
      id: 'overview',
      label: 'Overview',
      icon: <LayoutDashboard size={15} />,
    },
    {
      id: 'traffic',
      label: 'Network Traffic',
      icon: <Activity size={15} />,
    },
    {
      id: 'regional',
      label: 'Regional Operations',
      icon: <Globe2 size={15} />,
      badge: '5 Regions',
    },
    {
      id: 'replication',
      label: 'Replication',
      icon: <GitBranch size={15} />,
      badge: replicationLag !== undefined && replicationLag > 0 ? `${replicationLag.toFixed(1)}s lag` : undefined,
    },
    {
      id: 'history',
      label: 'Failover History',
      icon: <History size={15} />,
      badge: eventCount !== undefined ? eventCount : undefined,
    },
  ];

  return (
    <nav className="controller-nav-bar" aria-label="Controller Operations Navigation">
      <div className="controller-tabs-list" role="tablist">
        {tabs.map((t) => {
          const isActive = activeTab === t.id;
          return (
            <button
              key={t.id}
              role="tab"
              aria-selected={isActive}
              className={`controller-nav-tab ${isActive ? 'active' : ''}`}
              onClick={() => onSelectTab(t.id)}
            >
              {t.icon}
              <span>{t.label}</span>
              {t.badge !== undefined && <span className="tab-badge">{t.badge}</span>}
            </button>
          );
        })}
      </div>
    </nav>
  );
};
