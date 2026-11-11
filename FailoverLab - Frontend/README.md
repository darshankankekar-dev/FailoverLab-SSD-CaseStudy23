# FailoverLab — Multi-Region Active-Passive Failover Controller

> **Academic Context:** System Design & Software Systems Development (SSD) — Case Study 23: Multi-Region Active-Passive Failover Controller  
> **Repository:** Standalone educational virtual laboratory for distributed systems, consensus quorums, storage fencing, and disaster recovery.

---

## 1. Executive Overview

**FailoverLab** is an interactive, browser-native virtual simulation laboratory designed to teach the intricate failure modes, consensus mechanisms, and storage-level invariants of **Multi-Region Active-Passive Failover Architectures**.

In enterprise distributed systems, orchestrating automated regional failover without incurring silent data corruption (split-brain) or unacceptable transaction loss ($RPO$ breach) is one of the most hazardous operations an engineering team can automate. FailoverLab models the entire lifecycle of an active-passive deployment across trans-oceanic regions, enforcing formal safety gates, monotonically increasing fencing epoch tokens, and multi-observer quorum consensus.

---

## 2. Architecture & Regional Topology

The system models two geographical cloud regions connected by trans-oceanic WAN links, orchestrated by an independent, multi-observer control plane:

```
                          ┌───────────────────────────┐
                          │ Client / Global Ingress   │
                          │   (Synthetic 2,450 RPS)   │
                          └─────────────┬─────────────┘
                                        │
                                        ▼
                          ┌───────────────────────────┐
                          │ Global DNS / Route 53     │
                          │ Low-TTL CNAME Anycast     │
                          └──────┬─────────────┬──────┘
                                 │             │
        Traffic Route (Nominal)  │             │  Traffic Route (Failover)
                                 ▼             ▼
  ┌─────────────────────────────────┐       ┌─────────────────────────────────┐
  │ REGION A — MUMBAI (ap-south-1)  │       │ REGION B — SINGAPORE (ap-se-1)  │
  │ • App Service (12 pods)         │       │ • Standby App Service (12 pods) │
  │ • Primary Database (READ_WRITE) │══════>│ • Standby Database (READ_ONLY)  │
  │ • Health Agent (Probe Port)     │  WAL  │ • Health Agent (Probe Port)     │
  └─────────────────────────────────┘ Delta └─────────────────────────────────┘
                   ▲                                       ▲
                   │ Heartbeat                             │ Heartbeat
                   └───────────────────┬───────────────────┘
                                       │
  ┌────────────────────────────────────┴────────────────────────────────────┐
  │                 DISTRIBUTED FAILOVER CONTROLLER (CONTROL PLANE)         │
  │ • Synthetic Health Monitor (2s probe interval, 3-probe debounce window) │
  │ • Quorum Decision Engine (3 Observers: Mumbai, Singapore, Zurich)       │
  │ • Write Lease & Fencing Manager (Martin Kleppmann Generation Epochs)    │
  │ • Failover State Machine Executor (Idempotent 12-State Transitions)     │
  │ • Replicated Metadata Store (Persisted Intent Checkpoints)              │
  │ • Append-Only Audit & Telemetry Log (Chronological Event Trail)         │
  └─────────────────────────────────────────────────────────────────────────┘
```

### Components

1. **Client / Traffic Generator:** Generates simulated client requests ($2,450\text{ RPS}$ nominal ingress) with dynamic tracking of successful vs dropped requests and client HTTP error rate.
2. **DNS & Global Router:** Low-TTL Anycast CNAME routing pointing to the active region with explicit propagation delay modeling ($5\text{s}$ TTL) and route verification testing.
3. **Region A (Mumbai — `ap-south-1`):** Initially `ACTIVE`, holds exclusive `READ_WRITE` write authority under Generation Epoch #101, serving 100% of ingress traffic.
4. **Region B (Singapore — `ap-southeast-1`):** Initially `STANDBY`, strictly `READ_ONLY`, passively receiving continuous asynchronous Write-Ahead Log (WAL) replication stream.
5. **Failover Controller Control Plane:** Independent multi-observer orchestrator with quorum observers in Mumbai, Singapore, and a neutral tie-breaker in Zurich (`eu-central-1`).

---

## 3. Formal State Machine & Safety Invariants

FailoverLab operates as a deterministic, pure state machine (`simulationReducer`) with 12 distinct controller phases:

```
  [HEALTHY] ──(1-2 Probe Drops)──> [PRIMARY_SUSPECTED] ──(Probe Restores)──> [HEALTHY]
      │                                   │
      │                             (3/3 Drops)
      │                                   ▼
      │                            [QUORUM_CHECK] ──(Gate Fails)──> [FAILOVER_BLOCKED]
      │                                   │ (All Gates Pass)
      │                                   ▼
      │                           [FENCING_PRIMARY]
      │                                   │ (Fencing Confirmed)
      │                                   ▼
      │                          [PROMOTING_STANDBY]
      │                                   │ (Dual-Master Invariant Checked)
      │                                   ▼
      │                           [ROUTE_UPDATING]
      │                                   │ (DNS Propagation 100%)
      │                                   ▼
      │                           [VERIFYING_ROUTE] ──(Probe Fails)──> [FAILOVER_BLOCKED]
      │                                   │ (Probe Verified)
      │                                   ▼
      │                          [SECONDARY_ACTIVE]
      │                                   │
      │                        (Region A Recovers Online)
      │                                   ▼
      │                         [PRIMARY_RECOVERING]
      │                                   │ (Reverse Replication Synced)
      │                                   ▼
      │                          [FAILBACK_PENDING]
      │                                   │ (Operator Manual Approval)
      │                                   ▼
      └─────────────────────── [FAILBACK_IN_PROGRESS]
```

### Mandatory Safety Gates

| Safety Gate | Verification Condition | Purpose & Distributed Failure Mode Prevented |
|---|---|---|
| **Gate 1: Debounce Threshold** | $\text{Consecutive Failures} \ge 3$ probes ($6\text{s}$) | Filters transient WAN jitter; prevents catastrophic failover flapping. |
| **Gate 2: Consensus Quorum** | $\text{Outage Votes} \ge 2$ of $3$ independent observers | Solves split-brain tie in 2-region network severance ($N/2 + 1$ majority). |
| **Gate 3: Standby Readiness** | $\text{Region B Health} == \text{HEALTHY} \land \text{Ready}$ | Prevents promoting a damaged, partitioned, or corrupted replica. |
| **Gate 4: Replication Lag** | $\text{Lag} \le \text{Policy Threshold}$ ($5.0\text{s}$) | Bounds transaction loss; halts failover if promotion violates $RPO$ contract. |
| **Gate 5: Storage Fencing** | $\text{Region A Revoked} \land \text{isFenced} == \text{true}$ | Monotonic generation epoch (#101 $\to$ #102); guarantees zombie writes rejected. |
| **Gate 6: Route Verification** | Synthetic probe resolves to Region B successfully | Ensures traffic cutover is operational before marking failover complete. |

### Mathematical Single-Writer Invariant
$$\forall t: \neg (\text{RegionA.acceptsWrites}_t \land \text{RegionB.acceptsWrites}_t)$$
FailoverLab programmatically asserts that two regions can **never** accept write transactions simultaneously under any failure combination.

---

## 4. Guided Scenarios Catalog (Scenarios A through I)

FailoverLab features 9 pre-configured educational failure scenarios:

* **Scenario A — Normal Operation (Baseline Stability):** Steady-state active-passive baseline. Proves zero unnecessary failovers occur and single-writer invariant holds.
* **Scenario B — Primary Application Crash (Full Automated Cutover):** Total database crash in Mumbai. Demonstrates the complete 6-stage automated failover pipeline.
* **Scenario C — Transient Network Glitch (False-Positive Suppression):** 1 or 2 synthetic probes drop due to WAN latency. Demonstrates sliding-window debounce suppression without failover.
* **Scenario D — Network Partition / Quorum Lost:** WAN link between Mumbai and Singapore breaks, but Zurich neutral observer confirms Mumbai is alive. Quorum check fails ($1/3$ votes) and failover is safely blocked.
* **Scenario E — Corrupted Standby Storage:** Mumbai crashes while Singapore's storage volume is degraded. Safety Gate 3 blocks failover to prevent promoting unready storage.
* **Scenario F — Excessive Replication Lag ($RPO$ Policy Breach):** Mumbai crashes while replication lag spikes to $8.4\text{s}$ ($> 5.0\text{s}$ policy). Controller halts at Gate 4 to prevent silent data loss.
* **Scenario G — Stale DNS & Route Verification Failure:** Anycast DNS provider drops route update packets. Verification probe fails, preventing false-success state. Demonstrates the `Retry Routing Update` operator action.
* **Scenario H — Post-Disaster Recovery & Controlled Failback:** Mumbai reboots after disaster. Proves that Mumbai re-joins safely as `STANDBY` (anti-ping-pong pattern), reverses WAL synchronization, and waits for explicit operator authorization before switchback.
* **Scenario I — Mid-Transition Controller Crash & Recovery:** Failover orchestrator crashes during `FENCING_PRIMARY`. On reboot, controller validates persisted intent from metadata store and safely resumes idempotently.

---

## 5. Live Monitoring & Educational Modules

### A. Live Metrics Dashboard
Compact real-time dashboard derived 100% from actual simulation engine state:
1. **Active Region:** Resolves writer authority (`Region A`, `Region B`, or `None / Fenced`).
2. **Controller Phase:** State machine status badge.
3. **Health Probe Failures:** Consecutive timeouts against policy ($k/3$).
4. **Quorum Observers:** Healthy voters out of 3 ($N/2 + 1$ majority required).
5. **Modelled Replication Lag:** Model input lag in seconds and milliseconds.
6. **Current Routing Target:** Active DNS resolution CNAME and TTL countdown.
7. **Simulated Requests Processed:** Derived from elapsed simulated time ($\text{Time} \times \text{RPS}$).
8. **Simulated Request Success & Drops:** Calculated from active network and cutover error rates.
9. **Simulated Request Error Rate:** Client-facing HTTP error ratio.
10. **Detection Duration:** Configured debounce detection duration ($\text{Failures} \times \text{Interval}$).
11. **Failover Duration ($RTO$):** Measured cutover elapsed time from outage to route stabilization.
12. **Last Transition Time:** Formatted simulation clock ($T+mm:ss$) and wall-clock timestamp.

### B. Event Timeline & Audit Log
Chronological event logging with sequence numbers (`#001`), simulated timestamps ($T+mm:ss$), severity chips, subsystem categorization, explicit outcome badges (`SUCCESS`, `FAILURE`, `BLOCKED`, `WARNING`, `ACTION`, `INFO`), text search, subsystem filtering, and **CSV / JSON export**.

### C. Learning Panel (10 Core Modules)
Concise, structured breakdowns for:
1. Active-Passive Architecture
2. Health Checks & False Positives
3. Quorum & Failure Detection
4. Split-Brain Vulnerability
5. Write Leases & Fencing Tokens
6. Primary-to-Standby Replication
7. Replication Lag, RTO, and RPO Trade-offs
8. DNS Failover & Client-Side Caching
9. Controlled Manual Failback
10. Control-Plane Interruption & Recovery

*Each concept provides: (1) What it means, (2) Why needed, (3) What to observe in FailoverLab, and (4) Educational model limitation.*

### D. Experiment Report & Browser Persistence
* **Experiment Run Summary Card:** Records scenario, initial conditions, configured policies, final roles, request metrics, outcome & reason, and key takeaways.
* **Reproducible Exports:** One-click download as **JSON Report**, **CSV Timeline**, or **Markdown Incident Post-Mortem**.
* **Browser Local Storage:** Persists completed run summaries and safe user preferences without restoring old failures on reset.

---

## 6. Installation & Quickstart

### Prerequisites
* Node.js v18.0.0 or higher
* npm v9.0.0 or higher

### Local Development Setup

```bash
# 1. Clone repository or navigate to workspace
cd FailoverLab

# 2. Install dependencies
npm install

# 3. Start local development server
npm run dev
```

Open your browser at `http://localhost:5173` (or the port displayed in your terminal).

---

## 7. Testing & Quality Verification

FailoverLab includes comprehensive Vitest unit test suites covering the pure reducer, safety gates, all 9 scenarios, monitoring calculations, and the 18 quality pass requirements:

```bash
# Run full Vitest test suite once
npm test -- --run

# Run Vitest in interactive watch mode
npm test
```

### Test Suite Summary (55 Tests Across 4 Suites)

* `src/simulation/simulation.test.ts` (17 tests): Pure safety gate unit functions, quorum majorities, fencing verification, and single-writer invariant proofs.
* `src/simulation/scenarios.test.ts` (9 tests): Deterministic execution of Scenarios A through I.
* `src/simulation/reports.test.ts` (11 tests): Live metrics calculations, CSV/JSON report exports, learning concept completeness, and local storage persistence.
* `src/simulation/qualityPass.test.ts` (18 tests): Verification of all 18 functional requirements specified in the quality audit.

---

## 8. Production Build & Netlify Public Deployment

FailoverLab is built as a zero-backend, pure client-side Single Page Application (SPA). It requires zero server runtimes, zero databases, and zero external APIs.

### Build Verification Command

```bash
# Compile TypeScript and bundle production assets
npm run build

# Preview production build locally on http://localhost:4173
npm run preview
```

The production output is generated in `dist/`:
* `dist/index.html` (Static HTML5 entry point)
* `dist/_redirects` (Netlify SPA client-side routing redirect rule)
* `dist/favicon.svg` (Application vector icon)
* `dist/assets/index-[hash].css` (Compiled vanilla CSS design tokens)
* `dist/assets/index-[hash].js` (Tree-shaken JavaScript bundle)

---

### Netlify Deployment Configuration

The repository includes a root `netlify.toml` file configured for automated builds and security headers:

```toml
[build]
  command = "npm run build"
  publish = "dist"

[[redirects]]
  from = "/*"
  to = "/index.html"
  status = 200

[[headers]]
  for = "/*"
  [headers.values]
    X-Frame-Options = "DENY"
    X-Content-Type-Options = "nosniff"
    Referrer-Policy = "strict-origin-when-cross-origin"
```

---

### Procedure A: Automated Git Deployment (Recommended)

1. Push your repository to **GitHub**, **GitLab**, or **Bitbucket**.
2. Log in to [Netlify](https://app.netlify.com) and click **"Add new site" > "Import an existing project"**.
3. Select your Git provider and choose the `FailoverLab` repository.
4. Netlify will automatically detect `netlify.toml` with the exact required settings:
   * **Base directory:** *(leave blank / root)*
   * **Build command:** `npm run build`
   * **Publish directory:** `dist`
5. Click **"Deploy site"**.
6. Deployment will complete in ~30 seconds, generating a public URL (e.g., `https://failoverlab-demo.netlify.app`).

---

### Procedure B: Manual Drag-and-Drop Deployment (Netlify Drop)

If you do not wish to connect a Git repository, you can deploy manually in 60 seconds without Git credentials:

1. In your local terminal, run:
   ```bash
   npm run build
   ```
2. Confirm the `dist/` directory exists and contains `index.html`, `_redirects`, and the `assets/` subfolder.
3. Open your browser and navigate to **[app.netlify.com/drop](https://app.netlify.com/drop)**.
4. Drag and drop the `dist/` folder directly onto the upload area in the browser window.
5. Netlify will deploy the site immediately and provide a live public HTTPS URL.
6. The bundled `dist/_redirects` file ensures that direct page loading, URL sharing, and page refreshes work seamlessly without 404 errors.

---

### Post-Deployment Verification Checklist

Once deployed to Netlify:
* [x] **Direct Page Loading:** Loading the root URL or refreshing any view resolves `index.html` without 404s.
* [x] **Zero Localhost Leaks:** No hardcoded `localhost` or `127.0.0.1` endpoints exist in client code.
* [x] **No Secrets / Credentials:** The application contains zero API keys, secrets, or server environment variables.
* [x] **Full Offline Operation:** All state transitions, safety gates, metrics calculations, SVG rendering, and report exports operate completely in-browser.

---

## 9. Educational Model Limitations

FailoverLab is an academic simulation designed for pedagogical clarity. The following simplifications are intentional:
1. **Clock Model:** Employs discrete simulated-second ticks rather than true continuous asynchronous network sockets.
2. **Consensus Implementation:** Quorum observer voting is modeled via deterministic state variables rather than asynchronous Raft/Paxos RPC packet serialization.
3. **Storage Fencing:** Simulated via monotonic epoch state variables rather than physical SCSI-3 persistent reservations or cloud storage IAM condition barriers.
4. **DNS Caching:** Modeled as a global propagation progress percentage rather than thousands of distributed ISP resolver cache expiries.

---

## 10. License & Academic Attribution

Created for **System Design & Software Systems Development (SSD) — Case Study 23: Multi-Region Active-Passive Failover Controller**.
Distributed under the MIT License for educational and research use.
