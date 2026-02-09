# Semantic Model Explorer — Specification Review

Four expert perspectives reviewing the Product Specification v2.

---

## Table of Contents

1. [UX/UI Expert Review](#1-uxui-expert-review)
2. [Power BI Domain Expert Review](#2-power-bi-domain-expert-review)
3. [Full-Stack Web Dev Expert Review](#3-full-stack-web-dev-expert-review)
4. [Devil's Advocate Review](#4-devils-advocate-review)
5. [Cross-Cutting Themes](#5-cross-cutting-themes)

---

## 1. UX/UI Expert Review

### Strengths

- **Design philosophy is exceptional.** The three rules ("Drop and go," "See what you can't paste," "Copy what the LLM does better") form a genuine decision framework that tells you what to say *no* to — rare in product specs.
- **Zero-configuration file handling.** Auto-detecting format from contents rather than requiring user selection is correct.
- **"Things to Review" panel restraint.** No severity colors, no error/warning hierarchy, no scores — avoids the trap of best-practice-analyzer tools where users debate severity instead of understanding their model.
- **Overview-as-header architecture.** Persistent header prevents disorientation when navigating between tabs.
- **Measures tab follows established master-detail pattern.** Two distinct copy actions serve different workflows without adding modals.

### Issues & Concerns

#### 1.1 Drop Zone Has No Error States

The spec describes only the happy path. No defined behavior for:
- Non-Power BI files dropped (`.xlsx`, `.pdf`)
- Corrupted or password-protected `.pbix`
- WASM decompressor failure / OOM
- Missing files in `.pbip` folder structure
- Browsers lacking required APIs (e.g., `webkitdirectory` in Firefox)

Without error states, the implementation will crash silently or show JS errors, destroying user trust.

#### 1.2 Two Browse Buttons Create a False Choice

"Browse Files" vs. "Browse Folder" requires the user to understand file format distinctions before opening anything. This contradicts the "no configuration" philosophy.

**Proposal:** Single "Browse" button with a smaller text link: "Have a .pbip folder? Drop the folder here or [upload as .zip]."

#### 1.3 Overview Header Will Not Scale Vertically

The header consumes ~150-180px. With 7 review items, it could reach 250px+. On a 768px laptop screen, this leaves ~580px for tab content. The diagram needs maximum vertical space.

**Proposal:** After initial load, collapse the header to a slim bar (model name + format badge + review count badge). Click to expand.

#### 1.4 "Things to Review" Navigation Is Underspecified

"Each item is clickable — it navigates to the relevant object" — but where does "2 bi-directional cross-filters" navigate? To the Diagram tab with those lines highlighted? To a filtered list? Aggregate items ("5 measures without descriptions") need a disambiguation step.

**Proposal:** Define click behavior per check type — e.g., bi-directional filters → Diagram tab with highlighted lines; measures without descriptions → Measures tab with those pre-selected.

#### 1.5 Force-Directed Diagram Has Interaction Problems

- **Unstable layout:** D3 force simulations produce different layouts on each load, undermining spatial memory.
- **Click-to-expand causes reflow:** Expanding a table card pushes other nodes away — the "everything moves when I click" antipattern.
- **Dependency graph is hidden:** A "toggle or small button" has no information scent. Users who don't know it exists will never find it.

**Proposals:**
- Persist layout positions in `sessionStorage` keyed by model hash.
- Use a side panel for table details instead of inline expansion.
- Make "Relationships" and "Measure Dependencies" two clearly labeled sub-tabs.

#### 1.6 "Copy Full Model" Is Misplaced

The button is described as being "at the top" of the Measures tab, but its output includes tables, columns, relationships, and roles — none of which are visible in that tab. Information architecture mismatch.

**Proposal:** Move "Copy Full Model" to the persistent header. Add a preview popover showing: "Copies [N] tables, [N] columns, [N] measures, [N] relationships as Markdown. Estimated [N] tokens."

#### 1.7 No "Start Over" Affordance

Once a file is loaded, there is no described mechanism for dropping a different file.

#### 1.8 Responsive Design Not Addressed

The master-detail Measures layout, Diagram, and persistent header all assume wide screens. No mention of viewport widths below desktop.

#### 1.9 Accessibility Deferred Too Late

Keyboard navigation in Phase 4 means Phases 1-3 ship an inaccessible product. Basic keyboard operability (tab order, Enter to activate, Escape to close, ARIA roles) should be Phase 1.

#### 1.10 No Copy Preview for Large Models

Users have no way to see what "Copy Full Model" will produce before it's on their clipboard. A 50K-character payload that's silently truncated leads to bad LLM interactions.

**Proposal:** Before copying, if output exceeds ~30K tokens, show a dialog with checkboxes (Tables & Columns, Measures & DAX, Relationships, Roles) and a live token estimate.

---

## 2. Power BI Domain Expert Review

### Strengths

- **File format understanding is accurate.** All four formats are correctly described with appropriate parsing approaches.
- **User insight is correct.** Most users have `.pbix`; the tool must handle this well.
- **"Things to Review" checks are real-world pain points** that any experienced consultant would flag.
- **Copy Full Model format is appropriate.** Structured Markdown with tables, measures, relationships, and roles covers the metadata an LLM needs.
- **Design philosophy alignment.** The "visual vs. copy" split matches what's actually hard to communicate as text (relationship topology, column sizing, dependency chains).

### Issues & Concerns

#### 2.1 Missing Model Objects

The spec covers tables, columns, measures, relationships, and roles. Missing entirely:

| Object | Importance | Notes |
|--------|-----------|-------|
| **Calculation Groups** | High | Increasingly common in enterprise models. Contain DAX expressions. Omitting them drops important logic silently. |
| **Field Parameters** | Medium | Used for dynamic axis switching. DAX expression is meaningful. |
| **Perspectives** | Low-Medium | Named model subsets. Present in enterprise models. |
| **Translations/Cultures** | Low | Localization metadata for international deployments. |
| **Data Sources / Shared Expressions** | Medium | Connection strings and shared M parameters. |
| **Annotations** | Low | Key-value metadata used by external tools (e.g., Tabular Editor BPA rules). |
| **Object-Level Security (OLS)** | Medium | Column-level security rules within roles. Section 7 mentions RLS but not OLS. |

Underspecified: Hierarchies (mentioned once in 9.3, never surfaced), KPIs, partition details (type/source not in schema view).

**Minimum recommendation:** Add Calculation Groups and Field Parameters to the Measures tab. Add partition type/source to Schema view. Surface hierarchies.

#### 2.2 PBIX Parsing Complexity Is Massively Underspecified

"WASM decompress → ABF → SQLite" describes a five-stage pipeline in six words:

1. `.pbix` is a ZIP (OPC convention)
2. `DataModel` entry is XPress9-compressed
3. After decompression: ABF container (structured binary, must be parsed to locate embedded files)
4. ABF contains `metadata.sqlite` + VertiPaq segment files (`.idf` dictionaries, `.isf` data segments)
5. VertiPaq column stores use dictionary encoding, RLE, bit-packing, NULL bitmaps, multi-segment tables

The ABF is **not** "XPress9 → SQLite." It's a binary container format that must be parsed to extract both the SQLite metadata database and the VertiPaq column data. This is a non-trivial reverse-engineering task.

#### 2.3 VertiPaq Data Reconstruction Challenges

For data export (Section 6.2), reconstructing tables from VertiPaq requires:
- Reading dictionary-encoded columns (map integer IDs → actual values)
- Handling RLE for low-cardinality columns, bit-packing for high-cardinality
- Reassembling across segments (~1M-8M rows per segment)
- Converting internal 64-bit integers back to original types (dates, decimals, strings)
- Handling NULL bitmaps per column segment
- A 500MB .pbix can decompress to 2-3GB+ of raw data

#### 2.4 DAX Reference Extraction Will Produce False Positives

`[MeasureName]` in DAX is also used for column references (`Table[Column]`). A naive regex matches column refs, table refs, and even string literals containing brackets. The spec acknowledges imprecision but a dependency graph with incorrect edges is worse than no graph.

**Proposal:** Build a set of all known measure names, then match `[BracketedName]` tokens only if they exist in the measure set. Strip comments and string literals before extraction.

#### 2.5 Phase Ordering Contradicts User Reality

Spec says "most users have .pbix" then ships Phase 1 as `.pbit` only with `.pbix` in Phase 3. Users who arrive with a `.pbix` will see it rejected and never return.

**Proposals (pick one):**
- Move `.pbix` metadata parsing (without data export) to Phase 1
- Launch with a very prominent "Convert to .pbit" instruction (File → Save As → Power BI Template)
- Restructure: Phase 1 = .pbit + .pbix metadata, Phase 2 = .pbip + data export, Phase 3 = diagrams + polish

#### 2.6 Relationship Diagram Missing Key Details

- **Filter direction arrows** for single-direction cross-filters (not just bi-directional)
- **Relationship column names** — essential for disambiguation when multiple relationships exist between the same tables
- **Role-playing dimensions** — common pattern (e.g., Date table with OrderDate, ShipDate, DueDate relationships) requires showing multiple lines between same table pair

#### 2.7 Display Folders Are More Complex Than Implied

- Can be nested (`Financial\Revenue\Actuals`)
- Use backslash separator, not forward slash
- Apply to both measures and columns
- Same measure can appear in different folders per perspective

#### 2.8 Compatibility Level Should Drive Feature Detection

| Level | Features Available |
|-------|-------------------|
| 1500+ | Enhanced metadata format (V3), M partition expressions |
| 1565+ | Calculation Groups |
| 1569+ | Field Parameters, Dynamic Format Strings |
| 1604+ | Direct Lake mode (Fabric) |

The parser should use compatibility level to conditionally look for features.

#### 2.9 Additional Recommendations

- **Add "Copy with Prompt" option** — wrap model content in an LLM prompt template for even less friction
- **Show lineage** — extract source table/file name from M expressions (`Sql.Database`, `Excel.Workbook`, etc.)
- **Handle incremental refresh partitions** — models with incremental refresh have multiple partitions per table
- **Warn on composite models** — mixed Import + DirectQuery fundamentally affects behavior and data availability
- **Support standalone `.bim` files** — common export from Tabular Editor, trivially easy to support (just JSON)
- **Privacy notice** — state explicitly on landing page: "Your files never leave your browser"
- **Handle "never refreshed" state** — `.pbix` saved before refresh may have empty VertiPaq stores

---

## 3. Full-Stack Web Dev Expert Review

### Strengths

- **Single-file architecture is pragmatic** for distribution — sharable via Teams chat, bookmarkable from GitHub Pages.
- **Normalized internal data model** cleanly separates parsing from rendering.
- **Phase ordering minimizes rework** — UI stabilizes before tackling binary parsing.
- **D3 is the right choice** for force-directed ER diagram and treemap.
- **"Copy Full Model" is high-value** and drives organic adoption.

### Issues & Concerns

#### 3.1 PBIX Pipeline Is Severely Underspecified

ABF/VertiPaq extraction is reverse-engineered, undocumented, and fragile. Community tooling (pbi-tools, VertiPaq Analyzer) is in C#/.NET. No production-ready JS/WASM equivalent exists.

**Risk:** Phase 3 could take longer than Phases 1 and 2 combined. Need a fallback: what does the tool show for .pbix if full data export is not achievable?

#### 3.2 No Memory Management Strategy

500MB .pbix → several GB decompressed. No mention of:
- Streaming decompression (block-by-block)
- Web Worker offloading (all parsers run on main thread as spec'd)
- Memory budgeting (browsers have 2-4GB per-tab limits)
- Progressive buffer release
- Streaming data export

**Proposal:** Add a "Memory Management Strategy" section:
- All heavy parsing in Web Workers
- Block-by-block decompression with intermediate buffer release
- Streaming export via File System Access API (`showSaveFilePicker`)
- Explicit maximum model size with graceful degradation

#### 3.3 CDN Dependencies Create Fragility

- **No version pinning** — D3 v7 vs v6, sql.js breaking changes, parquet-wasm pre-1.0 API changes
- **No SRI hashes** — CDN compromise serves arbitrary JS
- **No offline fallback** — corporate proxies blocking cdnjs break everything
- **No CDN redundancy** — single CDN outage kills the tool

**Proposal:**
- Pin exact versions (e.g., `d3@7.9.0/dist/d3.min.js`)
- Add `integrity` and `crossorigin="anonymous"` to all script tags
- Use single CDN with fallback loader
- Service Worker for caching in Phase 1 (not Phase 4)
- Inline fflate (~12KB gzipped) directly into HTML

#### 3.4 fflate vs. JSZip: Choose fflate

| Aspect | JSZip | fflate |
|--------|-------|--------|
| Size (min+gz) | ~28KB | ~12KB |
| Performance | Slower (pure JS) | 2-5x faster |
| Memory | Full in-memory copy | Lower overhead |
| Streaming | No | Yes |

For 500MB files, fflate is clearly superior. Inline it to eliminate a CDN dependency.

#### 3.5 TMDL Parser Is Non-Trivial

The spec describes it in one sentence but it's a custom language parser handling:
- Significant whitespace (indentation-based nesting)
- Multi-line string literals (triple backticks for DAX/M expressions)
- Typed properties, reference syntax, comments
- Specific directory structure (`model.tmdl`, `tables/*.tmdl`, `relationships.tmdl`, `roles/*.tmdl`, etc.)

Needs a test corpus and "best effort" parsing strategy.

#### 3.6 Clipboard API Limitations

- `writeText()` requires user gesture and page focus
- Large strings (1MB+) cause perceptible UI pause
- Firefox requires HTTPS/localhost — `file://` fails silently
- Safari requires write in same call stack as user gesture (no `await` between click and write)

**Proposals:**
- Pre-build clipboard text on tab switch / selection change, write synchronously from click handler
- Fallback: modal with `<textarea>` pre-selected for manual Ctrl+C
- Toast notification confirming copy

#### 3.7 D3 Force Layout Performance at Scale

50+ tables with 100+ relationships: 2-5 seconds to stabilize, visual clutter.

**Proposals:**
- Set `simulation.alphaDecay(0.05)` or higher for faster equilibrium
- For 30+ tables, consider hierarchical/layered layout (dagre-d3 or elkjs)
- Level-of-detail: simplified rectangles at small zoom levels
- Cap simulation at 300 iterations

#### 3.8 Web Worker Architecture Needed from Day One

Structure with main-thread/worker-thread boundary from Phase 1:

| Main Thread | Worker Thread |
|-------------|---------------|
| UI rendering (D3, DOM) | File reading |
| Tab management | ZIP extraction |
| Clipboard operations | JSON parsing |
| User interaction | TMDL parsing |
| | XPress9 decompression |
| | ABF/VertiPaq parsing |
| | Parquet generation |

Feasible in single HTML via Blob URL workers, but CDN imports in workers need special handling.

#### 3.9 Additional Recommendations

- **Lazy tab rendering** — only render active tab, cache on switch
- **File System Access API for large exports** — stream to disk instead of in-memory Blob
- **Reframe 2-second target** — "First meaningful render within 2 seconds" (show progress + metadata before full parse completes)
- **Module pattern over global scope** — IIFE for testability and clean namespace
- **XPress9 WASM hosting** — host in same repo; deployment becomes HTML + WASM (acknowledge "two files, not one")
- **Testing strategy** — parser unit tests, Copy Full Model snapshot tests, cross-browser smoke tests (Playwright)
- **Make Parquet lazy-loaded** — only fetch the 2.5MB WASM when user clicks "Export as Parquet"

---

## 4. Devil's Advocate Review

### What's Genuinely Strong

- The core insight (model metadata + LLM context = underserved need) is real
- Zero-install browser-based is a genuine differentiator vs. installed tools
- "Copy Full Model" structured format is the most differentiated feature

### Uncomfortable Truths

#### 4.1 The Product Tries to Serve Three Different Users

1. **"Help me understand this model"** — diagrams, schema, quality checks
2. **"Help me feed this model to an LLM"** — copy buttons, structured markdown
3. **"Help me extract data from this model"** — CSV/Parquet export

These are three different products for three different moments. Trying to serve all three in v1 means none gets deep attention. The LLM copy workflow — the most differentiated and least-served-by-competitors — gets the same priority as an ER diagram that Tabular Editor and Power BI Desktop already provide.

**Recommendation:** Ruthlessly prioritize the LLM copy workflow. Make it the best in the world. Diagram and data export can come later.

#### 4.2 The Single HTML File Bet Will Break

What this "single file" must contain: TMDL parser, XPress9 WASM, ABF parser, SQLite WASM (~1.2MB), Parquet WASM (~2.5MB), D3.js, treemap rendering, tree views, tabs, search, checkboxes, 7 quality checks, ZIP handling, UTF-16LE decoding.

This is an application, not a file. WASM binaries can't be cleanly inlined. CDN dependencies mean it's not actually self-contained. You get the worst of both worlds: no build step AND no reliability guarantee.

**Prediction:** By Phase 3, the single-file constraint will be quietly abandoned or become the primary source of bugs.

#### 4.3 Phase 1 Audience Is Tiny

Phase 1 ships `.pbit` only. The users who have `.pbit` files and know what they are are precisely the power users who already have Tabular Editor. You're building the easy part first for the users who need you least, and deferring the hard part for the users who need you most.

**Risk:** Lukewarm Phase 1 reception → motivation drops → Phases 2-3 never ship. Classic "abandoned prototype" pattern.

#### 4.4 PBIX Parsing Is a Research Problem

XPress9 is a proprietary compression algorithm. ABF is not publicly documented. VertiPaq column reconstruction is reverse-engineered. There is no production-ready JS/WASM implementation.

**The spec hand-waves the hardest problem.** If it doesn't work, you lose `.pbix` support, data export, and the treemap — ~40% of the product.

**Recommendation:** Do the PBIX proof-of-concept in week one, not month three. If it works, you have a product. If it doesn't, you need a different product.

#### 4.5 Competitive Threats Not Addressed

| Threat | Risk Level |
|--------|-----------|
| **Microsoft Copilot in Power BI** | High — if Copilot answers "explain this measure" natively, the copy-to-LLM workflow becomes unnecessary |
| **Tabular Editor 3** | Medium — already has BPA, diagrams, scripting; adding "copy for LLM" is a weekend project |
| **pbi-tools** | Medium — already extracts .pbix to TMDL; adding LLM-friendly output is trivial |
| **LLM file upload** | Growing — users can already drop .pbit into ChatGPT/Claude and say "explain this" |

The spec needs a "why us, why now" section. The answer is probably "zero install, instant, in-browser" — but it needs to be stated and defended.

#### 4.6 The Copy-to-LLM Format Has a Shelf Life

Context windows are growing rapidly. Within 12-18 months, users may paste raw `DataModelSchema` JSON into an LLM without formatting. The carefully designed copy format becomes overhead rather than value.

Not a reason not to build it — but don't over-invest in the formatting engine.

#### 4.7 "Things to Review" Is Opinionated Without Earning Trust

For a v1 tool with no track record, unsolicited quality checks risk alienating power users who have legitimate reasons for flagged patterns. Bidirectional relationships are sometimes necessary. Inactive relationships exist for USERELATIONSHIP. Missing descriptions are normal in early-stage development.

A tool opened to quickly copy DAX should not lecture about modeling practices.

#### 4.8 The 2-Second Promise Contradicts the 500MB Target

Design Philosophy: "Parses everything within 2 seconds."
Success Metric 3: "Data export works for models up to ~500MB."

A 500MB .pbix will take 10-30+ seconds to decompress, parse, and load. These two promises cannot coexist.

#### 4.9 Alternative Phasing That Optimizes for Survival

1. **Phase 1:** `.pbit` + `.pbip` TMSL + `.pbip` TMDL + Copy Full Model + Measures tab. Widest non-PBIX audience, easiest engineering.
2. **Phase 2:** PBIX spike. Prove or disprove the WASM pipeline. If it works, ship schema-only PBIX support. If it fails, pivot.
3. **Phase 3:** Diagram + data export (only if Phase 2 succeeded).
4. **Phase 4:** Quality checks + polish.

---

## 5. Cross-Cutting Themes

Issues raised by multiple reviewers, representing the highest-confidence findings.

### Theme 1: PBIX Parsing Is the Biggest Risk (All 4 reviewers)

Every reviewer flagged that the `.pbix` pipeline (XPress9 → ABF → VertiPaq) is severely underspecified and represents the project's largest technical risk. The Devil's Advocate argues it's a research problem, not an engineering task. The Web Dev expert notes Phase 3 could take longer than Phases 1+2 combined.

**Consensus:** Run a proof-of-concept spike for PBIX parsing before committing to the full spec. If it fails, the product must be rescoped.

### Theme 2: Phase Ordering Needs Restructuring (3 of 4 reviewers)

The UX expert, Power BI expert, and Devil's Advocate all flag that shipping Phase 1 as `.pbit`-only contradicts the stated user reality. The Devil's Advocate predicts the "abandoned prototype" pattern.

**Consensus:** At minimum, expand Phase 1 to include `.pbip` TMSL (trivial — just JSON). Consider adding `.pbix` metadata-only support earlier. Add a prominent "Convert to .pbit" instruction as a bridge.

### Theme 3: Error States and Edge Cases Are Missing (UX + Web Dev)

Both the UX and Web Dev experts independently identified the complete absence of error handling, fallback states, and degradation strategies. File parsing tools fail regularly — this is a routine occurrence, not an edge case.

**Consensus:** Add an "Error Handling" section defining user-visible messages for: unrecognized files, corrupted files, WASM failures, CDN failures, memory exhaustion, and partial parse success.

### Theme 4: Memory Management Must Be Designed Upfront (Web Dev + Power BI)

Both technical reviewers flag that 500MB .pbix files will exhaust browser memory without streaming decompression, Web Workers, and progressive buffer release. The spec has no memory management strategy.

**Consensus:** Add Web Worker architecture from Phase 1. Design the parsing pipeline for streaming. Use File System Access API for large exports.

### Theme 5: "Copy Full Model" Placement and Preview (UX + Devil's Advocate)

The UX expert identifies the information architecture mismatch of placing a model-level action inside the Measures tab. The Devil's Advocate argues the LLM copy workflow should be the ruthless priority.

**Consensus:** Move "Copy Full Model" to the persistent header. Add a token estimate preview. Make this the hero feature, not a button buried in a tab.

### Theme 6: Missing Power BI Model Objects (Power BI expert)

Calculation Groups and Field Parameters are increasingly common in enterprise models and completely absent from the spec. The tool will silently drop important logic.

**Consensus:** Add Calculation Groups and Field Parameters to the data model and Measures tab. Acknowledge Perspectives, Translations, and OLS as out of initial scope.

### Theme 7: DAX Dependency Regex Will Mislead (3 of 4 reviewers)

UX, Power BI, and Web Dev experts all flag that `[BracketedName]` regex matches columns, not just measures, producing false edges in the dependency graph.

**Consensus:** Cross-reference extracted bracket tokens against the known measure name set. Strip comments and string literals before extraction. Document the limitation.

### Theme 8: CDN and Offline Fragility (Web Dev + Devil's Advocate)

No version pinning, no SRI hashes, no fallback CDN, no offline capability. Enterprise Power BI users often work behind restrictive proxies.

**Consensus:** Pin versions, add SRI, implement fallback loader, add Service Worker caching in Phase 1.

### Theme 9: Competitive Positioning Unaddressed (Devil's Advocate)

Microsoft Copilot in Power BI, Tabular Editor 3, pbi-tools, and direct LLM file upload are all threats. The spec has no "why us, why now" section.

**Consensus:** Add a competitive positioning section. The likely answer is "zero-install, instant, in-browser, structured-for-LLM" — but it needs to be explicit.

### Theme 10: Accessibility Cannot Wait Until Phase 4 (UX expert)

Basic keyboard operability (tab order, Enter/Space activation, ARIA roles, focus indicators) is not polish — it's a baseline requirement that becomes exponentially harder to retrofit.

**Consensus:** Move basic accessibility to Phase 1. Defer complex accessibility (diagram keyboard nav, treemap alternatives) to later.
