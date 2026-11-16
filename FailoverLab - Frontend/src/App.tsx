import { useState, useEffect, useCallback } from 'react';
import { Header } from './components/common/Header';
import { NavigationTabs } from './components/common/NavigationTabs';
import type { NavTabId } from './components/common/NavigationTabs';
import { MethodologyModal } from './components/common/MethodologyModal';
import { OverviewView } from './components/overview/OverviewView';
import { LiveSimulatorView } from './components/simulator/LiveSimulatorView';
import { ArchitectureView } from './components/architecture/ArchitectureView';
import { ScenariosView } from './components/scenarios/ScenariosView';
import { ReportsView } from './components/reports/ReportsView';
import { OnlineStoreView } from './components/shop/OnlineStoreView';
import { TrafficLabView } from './components/traffic/TrafficLabView';
import { simulationEngine } from './simulation/SimulationEngine';
import { SCENARIOS } from './data/scenarios';
import './App.css';

type AppRoute = 'console' | 'shop';

function App() {
  // Routing state: detects /shop pathname or #shop hash
  const [currentRoute, setCurrentRoute] = useState<AppRoute>(() => {
    if (typeof window !== 'undefined') {
      const path = window.location.pathname.toLowerCase();
      const hash = window.location.hash.toLowerCase();
      if (path.startsWith('/shop') || hash === '#shop' || hash.startsWith('#/shop')) {
        return 'shop';
      }
    }
    return 'console';
  });

  const [activeTab, setActiveTab] = useState<NavTabId>(() => {
    const saved = localStorage.getItem('failoverlab_active_tab');
    if (
      saved &&
      ['overview', 'traffic-lab', 'simulator', 'architecture', 'scenarios', 'reports'].includes(saved)
    ) {
      return saved as NavTabId;
    }
    return 'overview';
  });

  const [isMethodologyOpen, setIsMethodologyOpen] = useState<boolean>(false);

  // Sync route on browser back/forward buttons
  useEffect(() => {
    const handlePopState = () => {
      const path = window.location.pathname.toLowerCase();
      const hash = window.location.hash.toLowerCase();
      if (path.startsWith('/shop') || hash === '#shop' || hash.startsWith('#/shop')) {
        setCurrentRoute('shop');
      } else {
        setCurrentRoute('console');
      }
    };

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  const handleNavigateToShop = useCallback(() => {
    window.history.pushState(null, '', '/shop');
    setCurrentRoute('shop');
    window.scrollTo(0, 0);
  }, []);

  const handleNavigateToConsole = useCallback(() => {
    window.history.pushState(null, '', '/');
    setCurrentRoute('console');
    window.scrollTo(0, 0);
  }, []);

  useEffect(() => {
    localStorage.setItem('failoverlab_active_tab', activeTab);
  }, [activeTab]);

  const handleStartExperiment = () => {
    setActiveTab('simulator');
  };

  const handleSelectScenario = (scenarioId: string) => {
    const sc = SCENARIOS.find((s) => s.id === scenarioId);
    if (sc) {
      simulationEngine.restoreBaseline();
      sc.setupChaos(simulationEngine);
    }
    setActiveTab('simulator');
  };

  // Dedicated, isolated Online Shopping Customer Storefront
  if (currentRoute === 'shop') {
    return <OnlineStoreView onNavigateToConsole={handleNavigateToConsole} />;
  }

  // Canonical FailoverLab Operations Dashboard
  return (
    <div className="failover-app">
      {/* Global Engineering Header */}
      <Header
        onOpenMethodology={() => setIsMethodologyOpen(true)}
        onNavigateToShop={handleNavigateToShop}
      />

      {/* Main Console Navigation (5 Sections) */}
      <NavigationTabs
        activeTab={activeTab}
        onSelectTab={(tab) => setActiveTab(tab)}
      />

      {/* Primary Section Content */}
      <main className="main-console-content">
        {activeTab === 'overview' && (
          <OverviewView
            onStartExperiment={handleStartExperiment}
            onSelectScenario={handleSelectScenario}
            onNavigateToTrafficLab={() => setActiveTab('traffic-lab')}
          />
        )}

        {activeTab === 'traffic-lab' && <TrafficLabView />}

        {activeTab === 'simulator' && <LiveSimulatorView />}

        {activeTab === 'architecture' && <ArchitectureView />}

        {activeTab === 'scenarios' && (
          <ScenariosView onLaunchScenario={handleSelectScenario} />
        )}

        {activeTab === 'reports' && <ReportsView />}
      </main>

      {/* Methodology & Academic Reference Modal */}
      <MethodologyModal
        isOpen={isMethodologyOpen}
        onClose={() => setIsMethodologyOpen(false)}
      />
    </div>
  );
}

export default App;
