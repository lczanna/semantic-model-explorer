# Semantic Model Explorer — Product Specification v3

## One-Liner

Drop a Power BI file, see the model, copy everything to an LLM.

---

## 1. Design Philosophy

Follow the same principles as [Power Query Explorer](https://github.com/lczanna/power-query-explorer):

1. **Single HTML file.** All dependencies bundled inline. No CDN, no network requests, no build step. Works offline, works from `file://`, works behind corporate proxies.
2. **Drop and go.** No settings. Parse everything, show the result.
3. **Copy what the LLM does better.** The tool's job is to make copying fast and structured. DAX analysis, documentation, refactoring — that's the LLM's job.
4. **Only render what text can't do.** Relationship diagrams are the one thing genuinely better as a visual. Everything else is a copy target.

---

## 2. Supported Files

| Format | What's Inside | Parsing Approach |
|---|---|---|
| `.pbit` | `DataModelSchema` — JSON (UTF-16LE) inside ZIP | Unzip, strip BOM, JSON.parse |
| `.pbip` folder (TMSL) | `model.bim` — JSON | JSON.parse |
| `.pbip` folder (TMDL) | `/definition/` folder with `.tmdl` files | Line-by-line state machine parser |
| `.bim` | Same as TMSL — standalone JSON | JSON.parse |
| `.pbix` | `DataModel` — XPress9 compressed ABF | WASM decompress, extract metadata |

Auto-detect format from file contents, not extension. For `.pbip` folders, support folder drag-and-drop via `webkitGetAsEntry()` and zipped folder upload as fallback.

**Note on `.pbix`:** Most users have `.pbix` files. The XPress9 WASM decompressor and ABF metadata extractor already exist in Power Query Explorer — reuse them. Schema extraction from `.pbix` is a proven path. Full data export (reading VertiPaq column stores) is a separate, harder problem deferred to a later phase.

---

## 3. User Flow

### 3.1 Landing Page

A single centered drop zone. Same pattern as Power Query Explorer.

```
+-------------------------------------------+
|                                           |
|     Drop a Power BI file here             |
|     .pbix  .pbit  .pbip  .bim            |
|                                           |
|     [Browse Files]                        |
|     or drop a .pbip folder                |
|                                           |
|  Runs locally in your browser.            |
|  Your files never leave your machine.     |
|                                           |
+-------------------------------------------+
```

One browse button. Not two. The folder drop is handled automatically when a user drags a folder — no separate button needed.

Privacy notice on the landing page: "Runs locally in your browser. Your files never leave your machine."

### 3.2 Error Handling

Errors are routine in file-parsing tools. Handle them gracefully:

| Condition | Message |
|---|---|
| Unrecognized file | "This doesn't look like a Power BI file. Supported: .pbix, .pbit, .pbip, .bim" |
| Corrupted / password-protected | "Couldn't read this file. It may be corrupted or password-protected." |
| WASM decompression failure | "Couldn't decompress this .pbix file." |
| Partial parse | Show what succeeded, grey out what failed |
| Large file (>100MB) | Show file size in progress: "Parsing 487MB model..." |

Errors appear as a banner above the drop zone (same pattern as PQ Explorer's error log). File-level errors don't block other files if multiple are dropped.

### 3.3 Explorer View

After parsing, the user sees a header and two tabs.

```
+--------------------------------------------------------------+
|  Sales Report Model                              [Copy All]  |
|  pbix | 12 Tables | 47 Measures | 18 Relationships          |
+--------------------------------------------------------------+
|  [Diagram]  [Model (LLM Ready)]                              |
|                                                               |
|         ... active tab content ...                            |
|                                                               |
+--------------------------------------------------------------+
```

**Header:** Model name, format badge, summary counts. Always visible, one line. A **[Copy All]** button in the top-right copies the full model as structured Markdown (Section 6). This is the hero feature — always accessible, never buried.

**Tabs:** Two tabs only. Diagram and Model.

A small "New File" link in the header returns to the drop zone.

---

## 4. Tab: Diagram

**Purpose:** The one thing an LLM cannot do — show the model structure as a visual.

### 4.1 Relationship Diagram

An entity-relationship diagram using Cytoscape.js (same library as PQ Explorer's dependency graph — proven, bundleable, handles interaction well).

**Each table node shows:**
- Table name
- Type badge: `Import` / `DirectQuery` / `Dual` / `Calculated`

**Relationship edges show:**
- Cardinality: `1:*`, `*:1`, `1:1`, `*:*`
- Cross-filter direction: arrow from "one" side to "many" side (single) or both directions (both)
- Active/inactive: solid vs. dashed line
- Column names on the edge label (e.g., `ProductKey`)

**Interactions:**
- Click a table node: side panel shows column list, measures, partition source
- Click a relationship edge: tooltip with full details
- Zoom, pan, fit (same toolbar pattern as PQ Explorer: zoom in/out, fit, relayout)
- Toggle: show/hide hidden tables
- Search: filter nodes by name

**Layout:** COSE layout (Cytoscape's compound spring embedder) — fast, stable, handles star schemas well. Relayout button if the user wants to reset.

**Multiple relationships between same tables:** Show as separate offset edges with column-name labels. This handles role-playing dimensions (e.g., Date table linked via OrderDate, ShipDate).

### 4.2 What's NOT in the Diagram

No measure dependency graph. The regex approach (`[MeasureName]` extraction from DAX) produces false positives because DAX column references use the same bracket syntax. A misleading graph is worse than no graph. If added later, it must cross-reference against the known measure name set and strip comments/string literals first.

No treemap. Model size visualization requires VertiPaq statistics from `.pbix` data export, which is deferred.

---

## 5. Tab: Model (LLM Ready)

**Purpose:** See everything in the model. Select and copy any subset for an LLM.

This follows the same UX pattern as Power Query Explorer's Code tab: a master-detail layout with checkboxes for multi-select and copy.

### 5.1 Layout

```
+---------------------+----------------------------------------+
|                     |                                        |
|  [x] Select All     |  Total Sales                           |
|                     |  ----------------------------------------|
|  v Tables (12)      |  SUM(Sales[Amount])                    |
|    [x] Sales        |                                        |
|    [x] Date         |  Table: Sales                          |
|    [ ] Product      |  Folder: Revenue Metrics               |
|                     |  Format: $#,##0                        |
|  v Measures (47)    |  Description: Total revenue from...    |
|    v Sales (8)      |                                        |
|      [x] Total Sales|  References: [Margin], [Total Cost]    |
|      [ ] YoY Growth |                                        |
|    v Date (3)       |                                        |
|      [ ] Current Yr |                                        |
|                     |                                        |
|  v Relationships(18)|                                        |
|    [x] Sales->Date  |                                        |
|                     |                                        |
|  v Roles (2)        |                          [Copy DAX]    |
|    [x] Reg. Manager |                                        |
|                     |                                        |
|  [Copy Selected]    |                                        |
|                     |                                        |
|  ~12,400 tokens     |                                        |
+---------------------+----------------------------------------+
```

### 5.2 Left Panel: Object Tree

A single tree containing all model objects, grouped by type:

- **Tables**: each table expandable to show columns (with type, format, hidden/calc flags)
- **Measures**: grouped by table, then by display folder (nested with `\` separator). Shows DAX expression, format string, description.
- **Calculation Groups**: if present, shown as a section with calculation items and their DAX expressions
- **Relationships**: listed as `FromTable -> ToTable` with cardinality
- **Roles**: each role with its table filter expressions

Every item has a checkbox. "Select All" at the top. The tree supports expand/collapse per section.

### 5.3 Right Panel: Detail View

Click any item in the tree to see its full details in the right panel. What appears depends on the item type:

- **Table**: column listing (name, type, format, hidden, calculated), partition source expression, row count (if available from `.pbix`)
- **Measure**: DAX expression with syntax highlighting, format string, display folder, description
- **Calculation Item**: DAX expression
- **Column**: data type, format, sort-by column, description, whether hidden/calculated
- **Relationship**: from/to table and column, cardinality, filter direction, active/inactive
- **Role**: name, table permissions with filter expressions

**Copy DAX** button (right panel): copies just the expression for the selected measure.

### 5.4 Copy Selected

**Copy Selected** button (left panel footer): copies all checked items as structured Markdown. The output format follows Section 6.

A live **token estimate** below the button updates as items are checked/unchecked: "~12,400 tokens". This helps users gauge whether their selection fits an LLM context window.

### 5.5 LLM Prompt Templates

Same pattern as Power Query Explorer: a dropdown next to Copy Selected offering pre-built prompts:

- **Analyze**: "Review this Power BI model for best practices and potential issues."
- **Document**: "Generate documentation for this Power BI model."
- **Optimize**: "Suggest performance optimizations for this DAX and model structure."
- **Explain**: "Explain what this model does in plain language."

The selected prompt is prepended to the copied content.

### 5.6 Search

A search box at the top of the left panel. Filters the tree to show only matching items (searches names, DAX expressions, descriptions). Same pattern as PQ Explorer's code panel.

---

## 6. Copy Format

When a user clicks **[Copy All]** or **[Copy Selected]**, the output is structured Markdown optimized for LLM consumption.

### 6.1 Format

```markdown
# Model: Sales Report
Compatibility Level: 1604 | Tables: 12 | Measures: 47 | Relationships: 18

## Tables

### Sales [Import, 125,342 rows]
| Column | Type | Hidden | Calculated | Format |
|--------|------|:------:|:----------:|--------|
| OrderID | Int64 | | | |
| OrderDate | DateTime | | | d/m/yyyy |
| Amount | Decimal | | | $#,##0 |
| Margin | Decimal | | Yes | 0.0% |

Source (M):
```
Source = Sql.Database("server", "db"),
Sales = Source{[Schema="dbo",Item="Sales"]}[Data]
```

### Date [Import, 1,461 rows]
...

## Measures

### Table: Sales

**Total Sales** | Format: $#,##0
```dax
SUM(Sales[Amount])
```

**YoY Growth** | Format: 0.0%
```dax
VAR CurrentYear = [Total Sales]
VAR PriorYear = CALCULATE([Total Sales], SAMEPERIODLASTYEAR('Date'[Date]))
RETURN DIVIDE(CurrentYear - PriorYear, PriorYear)
```

## Calculation Groups

### Time Intelligence
**YTD**
```dax
CALCULATE(SELECTEDMEASURE(), DATESYTD('Date'[Date]))
```

## Relationships
| From | To | Cardinality | Direction | Active |
|------|-----|:-----------:|:---------:|:------:|
| Sales[ProductKey] | Product[ProductKey] | *:1 | Single | Yes |
| Sales[OrderDate] | Date[Date] | *:1 | Single | Yes |

## Roles

**Regional Manager**
- Sales: `[Region] = USERPRINCIPALNAME()`
```

### 6.2 Rules

- Row counts only shown when available (`.pbix` with parsed metadata)
- Partition source expressions included when available
- Calculated columns include their DAX expression
- Format is human-readable Markdown that LLMs parse well
- No silent truncation — the user controls what's selected via checkboxes
- The token estimate is always visible so the user knows the size before copying

---

## 7. Technical Architecture

### 7.1 Single HTML File

One `.html` file containing all HTML, CSS, JS, and bundled dependencies. Same architecture as Power Query Explorer. No build step, no framework, deployable on GitHub Pages or openable from disk.

Content Security Policy: `default-src 'none'; script-src 'unsafe-inline' 'wasm-unsafe-eval'; style-src 'unsafe-inline'; img-src data:`

No external network requests. Works offline. Works behind corporate firewalls.

### 7.2 Bundled Dependencies

| Library | Purpose | Size (approx) |
|---------|---------|---------------|
| JSZip | Unzip .pbit/.pbix/.pbip files | ~45KB min |
| Cytoscape.js | Relationship diagram | ~300KB min |
| XPress9 WASM | Decompress .pbix DataModel | Reuse from PQ Explorer |

**Not included:**
- No D3.js (Cytoscape handles the diagram)
- No sql.js (use PQ Explorer's lightweight SQLite reader)
- No parquet-wasm (CSV-only export, deferred)
- No CDN dependencies of any kind

Total bundle: ~500-600KB (comparable to PQ Explorer's ~540KB).

### 7.3 Internal Data Model

All file formats parse into one normalized structure:

```javascript
{
  name: "string",
  compatibilityLevel: 1604,
  tables: [{
    name: "Sales",
    type: "import",             // import | directQuery | dual | calculated
    isHidden: false,
    description: "",
    columns: [{
      name: "Amount",
      dataType: "decimal",
      type: "data",             // data | calculated | rowNumber
      isHidden: false,
      expression: null,         // DAX for calculated columns
      formatString: "$#,##0",
      sortByColumn: null,
      displayFolder: "",
      description: ""
    }],
    measures: [{
      name: "Total Sales",
      expression: "SUM(Sales[Amount])",
      formatString: "$#,##0",
      displayFolder: "Revenue Metrics",
      description: "",
      isHidden: false
    }],
    hierarchies: [{
      name: "Date Hierarchy",
      levels: ["Year", "Quarter", "Month"]
    }],
    partitions: [{
      type: "m",                // m | dax | entity | calculated
      expression: "Source = ..."
    }],
    // Calculation Group specific:
    calculationItems: [{        // only for calculation group tables
      name: "YTD",
      expression: "CALCULATE(SELECTEDMEASURE(), DATESYTD('Date'[Date]))",
      ordinal: 0
    }]
  }],
  relationships: [{
    fromTable: "Sales", fromColumn: "ProductKey",
    toTable: "Product", toColumn: "ProductKey",
    cardinality: "manyToOne",   // manyToOne | oneToMany | oneToOne | manyToMany
    crossFilterDirection: "single", // single | both
    isActive: true
  }],
  roles: [{
    name: "Regional Manager",
    tablePermissions: [{
      table: "Sales",
      filterExpression: "[Region] = USERPRINCIPALNAME()"
    }]
  }],
  // Only from .pbix metadata:
  statistics: {
    tables: [{
      name: "Sales",
      rowCount: 125342
    }]
  }
}
```

### 7.4 Parser Modules

```javascript
async function parseFile(file) -> SemanticModel

// Dispatches to:
function parsePbit(zipContents) -> SemanticModel       // Unzip, UTF-16LE decode, strip BOM, JSON.parse
function parseBim(jsonText) -> SemanticModel            // JSON.parse (same format as pbit schema)
function parsePbipTmdl(tmdlFiles) -> SemanticModel      // Line-by-line state machine
function parsePbix(zipContents, xpress9) -> SemanticModel // XPress9 decompress, ABF extract, metadata read
```

**TMDL Parser notes:**
- Indentation-based nesting (like Python/YAML)
- Multi-line expressions in triple-backtick blocks
- Expected file structure: `model.tmdl`, `tables/*.tmdl`, `relationships.tmdl`, `roles/*.tmdl`, `cultures/*.tmdl`, `expressions.tmdl`
- Best-effort parsing: extract what's recognized, silently skip unrecognized constructs
- Must handle nested display folders (backslash separator)

**PBIX Parser notes:**
- Reuse XPress9 WASM decompressor from Power Query Explorer
- Reuse ABF container parser and lightweight SQLite reader from Power Query Explorer
- Phase 1: extract model schema from `metadata.sqlitedb` only (tables, columns, measures, relationships)
- Defer: VertiPaq column store data extraction (complex, memory-intensive, separate engineering effort)

### 7.5 Clipboard Handling

- Write synchronously from click handlers (Safari requires same call stack)
- Pre-build clipboard text on selection change, cache it
- Fallback on clipboard failure: modal with `<textarea>` pre-selected
- Toast notification on copy success: "Copied ~12,400 tokens"

---

## 8. Error Handling

Follow Power Query Explorer's pattern: accumulate errors per file, show them in a banner, don't block what succeeded.

```javascript
const errors = [];
try { /* parse path 1 */ } catch(e) { errors.push(e.message); }
try { /* parse path 2 */ } catch(e) { errors.push(e.message); }
// Show results for whatever succeeded
// Show error banner if errors.length > 0
```

For `.pbix` files: try multiple extraction paths in order (same as PQ Explorer):
1. Try `DataModelSchema` entry (present in some `.pbix` as JSON)
2. Try `DataModel` via XPress9 → ABF → metadata extraction
3. If all paths fail, show specific error message

Library initialization check on load (same as PQ Explorer):
```javascript
if (typeof JSZip === 'undefined') {
  // Show warning, disable drop zone
}
```

---

## 9. Implementation Phases

### Phase 1 — Ship This First

**Scope:** `.pbit` + `.bim` + `.pbip` (both TMSL and TMDL) + `.pbix` metadata.

- Drop zone with auto-format detection
- All five parsers (reuse PQ Explorer's XPress9/ABF/SQLite for `.pbix`)
- Overview header with counts and [Copy All]
- Model tab: full object tree with checkboxes, detail panel, Copy Selected, LLM prompt templates, token estimate, search
- Error handling and graceful degradation
- Privacy notice
- Deploy on GitHub Pages

**Why all formats in Phase 1:** `.pbit` and `.bim` are trivial (JSON.parse). `.pbip` TMSL is the same. The TMDL parser is the only real work. `.pbix` metadata extraction reuses proven code from PQ Explorer. Shipping all formats means every user can use the tool on day one.

**Why no diagram in Phase 1:** The Model tab with Copy All is the hero feature and the competitive differentiator. The diagram is valuable but secondary. Ship the core, validate with users, then add the visual.

### Phase 2 — Diagram

- Relationship diagram (Cytoscape.js, bundled)
- Table detail side panel
- Zoom/pan/fit/relayout/search toolbar
- Show/hide hidden tables toggle

### Phase 3 — Data Export

- VertiPaq column store extraction from `.pbix` (research spike first — if infeasible, skip this phase)
- Row counts and table sizes in the schema view
- CSV export per table
- ZIP download for all tables
- Model size treemap (if VertiPaq stats are available)
- Memory management: streaming export via File System Access API, size warnings for large models

### Phase 4 — Polish

- Keyboard navigation (tab order, arrow keys, Enter/Space activation, Escape)
- ARIA roles (`tablist`, `tree`, `treeitem`, `aria-live` for copy confirmations)
- Shareable URL state (encode selected tab in URL hash)
- Enhanced TMDL edge case handling
- Perspectives and cultures display (if present)

---

## 10. What This Tool Is NOT

- **Not a model editor.** Read-only.
- **Not a documentation generator.** Copy to an LLM; it writes better docs than any template.
- **Not a best-practice analyzer.** No "things to review" panel — that's opinionated, and the LLM does it better when given the full model context.
- **Not a diff tool.** Copy two models into an LLM and ask "what changed?"
- **Not a Tabular Editor replacement.** TE is for editing and deploying. This is for understanding and extracting.
- **Not a data extraction tool (initially).** Data export is Phase 3, contingent on VertiPaq feasibility.

---

## 11. Why This Tool, Why Now

**Zero install.** Tabular Editor, DAX Studio, pbi-tools all require installation. This runs in a browser tab.

**Zero configuration.** No connection strings, no XMLA endpoints, no Azure AD auth. Drop a file, get answers.

**LLM-native.** The structured Markdown output, token estimates, and prompt templates are designed for the workflow that Power BI developers increasingly use: paste model context into an LLM, ask questions. No other tool optimizes for this.

**Offline and private.** Single HTML file, no network requests, no telemetry. Enterprise users can use it without security review.

**Complementary, not competitive.** Microsoft Copilot works inside Power BI Service on published models. This works on local files before publishing. Tabular Editor is for editing. This is for understanding. They serve different moments.

---

## 12. Success Metrics

1. A user can go from "I have a Power BI file" to "I have the full model in my LLM context" in under 10 seconds.
2. The Copy All output is useful in an LLM without any cleanup.
3. The tool handles all five file formats without errors on well-formed files.
4. Power BI developers share the tool link because it solves a real workflow gap.
