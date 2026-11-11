import React, { useState } from 'react';
import {
  BookOpen,
  HelpCircle,
  Eye,
  AlertTriangle,
  Search,
  ChevronDown,
  ChevronUp,
  Layers,
} from 'lucide-react';
import { LEARNING_CONCEPTS } from '../../data/learningConcepts';
import type { LearningConcept } from '../../data/learningConcepts';

export const LearningPanel: React.FC = () => {
  const [selectedConceptId, setSelectedConceptId] = useState<string>(
    LEARNING_CONCEPTS[0].id
  );
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [expandedAll, setExpandedAll] = useState<boolean>(false);

  const filteredConcepts = LEARNING_CONCEPTS.filter((concept) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      concept.title.toLowerCase().includes(q) ||
      concept.shortDesc.toLowerCase().includes(q) ||
      concept.whatItMeans.toLowerCase().includes(q) ||
      concept.whyNeeded.toLowerCase().includes(q) ||
      concept.whatToObserve.toLowerCase().includes(q)
    );
  });

  const activeConcept =
    filteredConcepts.find((c) => c.id === selectedConceptId) ||
    filteredConcepts[0] ||
    LEARNING_CONCEPTS[0];

  return (
    <div className="learning-panel-container">
      <div className="section-header mb-4">
        <div className="section-title-group">
          <div className="badge-tag badge-info mb-2 font-mono text-xs">
            Distributed Systems Pedagogy
          </div>
          <h2 className="section-title">
            Core Distributed Systems Concepts (Case Study 23)
          </h2>
          <p className="section-subtitle">
            Essential principles of multi-region active-passive failover, consensus, fencing, and recovery.
            Each concept explains theoretical meaning, architectural necessity, observable simulation behaviour, and educational model limitations.
          </p>
        </div>

        <div className="learning-actions-bar">
          {/* Search box */}
          <div className="timeline-search-box">
            <Search size={14} className="search-icon" />
            <input
              type="text"
              placeholder="Search concepts, RTO, fencing..."
              aria-label="Search educational concepts"
              className="timeline-search-input font-mono text-xs"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>

          <button
            className="btn-console text-xs"
            onClick={() => setExpandedAll(!expandedAll)}
            title="Toggle between single-concept deep dive and all-concept expanded grid"
            aria-label={expandedAll ? 'Switch to tabbed single concept view' : 'Expand all 10 concepts in grid'}
          >
            {expandedAll ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
            <span>{expandedAll ? 'Tabbed View' : 'Expand All 10'}</span>
          </button>
        </div>
      </div>

      {!expandedAll ? (
        /* Tabbed / Detail View */
        <div className="learning-layout-split">
          {/* Left Concept Selector List */}
          <div className="learning-nav-column">
            <div className="learning-nav-header font-mono text-xs text-muted mb-2">
              <Layers size={13} className="inline mr-1 text-flow" />
              CONCEPTS (10 CORE MODULES)
            </div>
            <div className="learning-nav-list">
              {filteredConcepts.map((concept) => {
                const isSelected = concept.id === activeConcept.id;
                return (
                  <button
                    key={concept.id}
                    className={`learning-nav-item ${
                      isSelected ? 'learning-nav-item-active' : ''
                    }`}
                    onClick={() => setSelectedConceptId(concept.id)}
                  >
                    <span className="concept-nav-num font-mono">
                      #{concept.number.toString().padStart(2, '0')}
                    </span>
                    <div className="concept-nav-text">
                      <span className="concept-nav-title font-semibold text-xs">
                        {concept.title}
                      </span>
                      <span className="concept-nav-sub text-muted text-xs truncate">
                        {concept.shortDesc}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Right Concept Detail Body */}
          <div className="learning-detail-column">
            {activeConcept && (
              <ConceptDetailCard concept={activeConcept} />
            )}
          </div>
        </div>
      ) : (
        /* Expanded All Grid View */
        <div className="learning-grid-expanded">
          {filteredConcepts.map((concept) => (
            <ConceptDetailCard key={concept.id} concept={concept} />
          ))}
        </div>
      )}
    </div>
  );
};

interface ConceptDetailCardProps {
  concept: LearningConcept;
}

const ConceptDetailCard: React.FC<ConceptDetailCardProps> = ({ concept }) => {
  return (
    <div className="learning-concept-card">
      <div className="concept-card-header">
        <div className="concept-number-badge font-mono text-xs">
          CONCEPT {concept.number.toString().padStart(2, '0')} OF 10
        </div>
        <h3 className="concept-card-title text-base font-bold text-bright">
          {concept.title}
        </h3>
        <p className="concept-card-short text-xs text-secondary font-mono">
          {concept.shortDesc}
        </p>
      </div>

      <div className="concept-sections-grid">
        {/* 1. What It Means */}
        <div className="concept-section-box">
          <div className="concept-section-header">
            <BookOpen size={14} className="text-flow" />
            <span className="concept-section-label font-mono text-xs font-semibold">
              1. What It Means
            </span>
          </div>
          <p className="concept-section-body text-xs text-secondary">
            {concept.whatItMeans}
          </p>
        </div>

        {/* 2. Why This Design Needs It */}
        <div className="concept-section-box">
          <div className="concept-section-header">
            <HelpCircle size={14} className="text-warning" />
            <span className="concept-section-label font-mono text-xs font-semibold">
              2. Why This Design Needs It
            </span>
          </div>
          <p className="concept-section-body text-xs text-secondary">
            {concept.whyNeeded}
          </p>
        </div>

        {/* 3. What to Observe in the Simulation */}
        <div className="concept-section-box">
          <div className="concept-section-header">
            <Eye size={14} className="text-healthy" />
            <span className="concept-section-label font-mono text-xs font-semibold">
              3. What to Observe in FailoverLab
            </span>
          </div>
          <p className="concept-section-body text-xs text-secondary">
            {concept.whatToObserve}
          </p>
        </div>

        {/* 4. Limitation of the Educational Model */}
        <div className="concept-section-box limitation-box">
          <div className="concept-section-header">
            <AlertTriangle size={14} className="text-danger" />
            <span className="concept-section-label font-mono text-xs font-semibold text-danger">
              4. Model Limitation
            </span>
          </div>
          <p className="concept-section-body text-xs text-secondary">
            {concept.modelLimitation}
          </p>
        </div>
      </div>
    </div>
  );
};
