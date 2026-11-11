import React from 'react';
import {
  Compass,
  PlaySquare,
  Network,
  Cpu,
  GraduationCap,
} from 'lucide-react';

export type NavTabId =
  | 'overview'
  | 'simulator'
  | 'architecture'
  | 'scenarios'
  | 'reports';

interface NavigationTabsProps {
  activeTab: NavTabId;
  onSelectTab: (tab: NavTabId) => void;
}

export const NavigationTabs: React.FC<NavigationTabsProps> = ({
  activeTab,
  onSelectTab,
}) => {
  const tabs = [
    {
      id: 'overview' as NavTabId,
      label: 'Overview',
      icon: Compass,
      badge: null,
    },
    {
      id: 'simulator' as NavTabId,
      label: 'Live Simulator',
      icon: PlaySquare,
      badge: 'Interactive',
    },
    {
      id: 'architecture' as NavTabId,
      label: 'Architecture',
      icon: Network,
      badge: 'Deep-Dive',
    },
    {
      id: 'scenarios' as NavTabId,
      label: 'Scenarios',
      icon: Cpu,
      badge: '5 Scenarios',
    },
    {
      id: 'reports' as NavTabId,
      label: 'Learning & Reports',
      icon: GraduationCap,
      badge: 'SLA / Quiz',
    },
  ];

  return (
    <nav className="console-navigation" aria-label="Console navigation">
      <div className="nav-container">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              className={`nav-tab-btn ${isActive ? 'nav-tab-active' : ''}`}
              onClick={() => onSelectTab(tab.id)}
            >
              <Icon size={16} className="nav-icon" />
              <span className="nav-label">{tab.label}</span>
              {tab.badge && (
                <span
                  className={`nav-badge ${
                    isActive ? 'nav-badge-active' : 'nav-badge-inactive'
                  }`}
                >
                  {tab.badge}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </nav>
  );
};
