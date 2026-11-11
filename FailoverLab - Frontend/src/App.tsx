import { useState, useEffect } from 'react';
import { Header } from './components/common/Header';
import { NavigationTabs } from './components/common/NavigationTabs';
import type { NavTabId } from './components/common/NavigationTabs';
import { MethodologyModal } from './components/common/MethodologyModal';
import { OverviewView } from './components/overview/OverviewView';
import { LiveSimulatorView } from './components/simulator/LiveSimulatorView';
import { ArchitectureView } from './components/architecture/ArchitectureView';
import { ScenariosView } from './components/scenarios/ScenariosView';
import { ReportsView } from './components/reports/ReportsView';
import { simulationEngine } from './simulation/SimulationEngine';
import { SCENARIOS } from './data/scenarios';
import './App.css';

function App() {
  const [activeTab, setActiveTab] = useState<NavTabId>(() => {
    const saved = localStorage.getItem('failoverlab_active_tab');
    if (
      saved &&
      ['overview', 'simulator', 'architecture', 'scenarios', 'reports'].includes(saved)
    ) {
      return saved as NavTabId;
    }
    return 'overview';
  });

  const [isMethodologyOpen, setIsMethodologyOpen] = useState<boolean>(false);

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

  return (
    <div className="failover-app">
      {/* Global Engineering Header */}
      <Header onOpenMethodology={() => setIsMethodologyOpen(true)} />

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
          />
        )}

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
