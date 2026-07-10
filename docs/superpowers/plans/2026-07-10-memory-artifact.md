# Memory Artifact Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a polished, self-contained HTML artifact that explains Agent-Smith's Memory lifecycle and design trade-offs.

**Architecture:** Create one standalone document at `docs/artifacts/memory-design.html` with inline CSS and JavaScript so it can be opened without a build step. Use semantic sections for the dossier narrative, CSS grid/flex for responsive layout, and a small event-driven controller for lifecycle navigation and detail-panel updates.

**Tech Stack:** HTML5, CSS3 custom properties, vanilla JavaScript, Mermaid-free inline diagrams built with semantic HTML/CSS, local static HTTP server for verification.

## Global Constraints

- Use the cool light-grey technical dossier treatment defined in the approved spec.
- Keep Markdown files as the Memory source-of-truth and describe SQLite as a disposable derived index.
- Preserve project terminology: `agent` and `project` scopes; `employee_dir` is compatibility-only.
- Keep the artifact self-contained; do not add runtime dependencies or external font/CDN requests.
- Respect `prefers-reduced-motion`, visible focus states, and responsive no-overflow behavior.

---

### Task 1: Create the standalone Memory design artifact

**Files:**
- Create: `docs/artifacts/memory-design.html`

**Interfaces:**
- Consumes: facts and thresholds from `docs/12-记忆系统SDD.md` and `engine/memory/`.
- Produces: one browser-openable HTML document with the sections and interactions in the approved spec.

- [ ] **Step 1: Add document structure and real project copy**

  Create semantic sections for the thesis hero, lifecycle flow, compilation layers, storage model, Dream operations, dual-track reads, retrieval fallback, decisions, and closing pseudocode. Use the exact project values: `had_tools`, four layers, 30 days, 70% overlap, top-5, and RRF `k=60`.

- [ ] **Step 2: Add the visual token system and responsive layout**

  Define named CSS custom properties for the approved palette, type roles, card borders, and spacing. Keep the reading column at `min(1120px, calc(100vw - 32px))`, switch multi-column diagrams to one column below 760px, and put wide diagrams in overflow-safe wrappers.

- [ ] **Step 3: Add lifecycle navigation behavior**

  Implement a small controller that maps each `[data-stage]` button to its explanatory copy and target section. Update `aria-selected`, the active class, and the detail panel without changing the URL or requiring a framework.

- [ ] **Step 4: Add accessibility and motion safeguards**

  Provide real button elements, visible `:focus-visible`, `aria-live` on the detail panel, reduced-motion overrides, and descriptive labels for diagrams.

### Task 2: Render and verify the artifact

**Files:**
- Modify: `docs/artifacts/memory-design.html` only if visual defects are found.

**Interfaces:**
- Consumes: the static HTML artifact from Task 1.
- Produces: a verified local render with no console errors, no horizontal overflow, and working lifecycle interactions.

- [ ] **Step 1: Serve the artifact locally**

  Run `python3 -m http.server 4173 --directory docs/artifacts` from the repository root and open `http://127.0.0.1:4173/memory-design.html`.

- [ ] **Step 2: Check desktop and narrow viewport behavior**

  Confirm the hero, flow diagrams, cards, and closing code block remain readable at desktop width and a narrow mobile width; fix any overlap or overflow in the HTML/CSS.

- [ ] **Step 3: Check interaction and reduced motion**

  Click each lifecycle stage, verify the panel text and active state update, then run a reduced-motion check and confirm the page remains fully usable without animation.

- [ ] **Step 4: Report the deliverable**

  Provide the absolute file link and a short verification summary; do not include unrelated dirty-worktree changes.
