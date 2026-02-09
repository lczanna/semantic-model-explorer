# Semantic Model Explorer

A single-file browser app for exploring Power BI semantic models and copying them as LLM-ready Markdown. Drop a file, explore the model, and paste it into ChatGPT / Claude / Copilot.

**No install. No server. No data leaves your browser.**

![Drop Zone](docs/screenshots/01-drop-zone.png)

## Features

### Model Tab

Browse tables, columns, measures, relationships, and roles in a tree panel. Click any item to see its details, including DAX expressions with syntax highlighting and format strings.

![Model Tab - AdventureWorks.bim (15 tables, 67 measures)](docs/screenshots/02-model-tab-overview.png)

Select what to include, pick an optional LLM prompt template, and copy structured Markdown to your clipboard with a token estimate.

![Measure Detail - DAX expression with Copy DAX button](docs/screenshots/03-measure-detail.png)

### Diagram Tab

Interactive ER diagram powered by Cytoscape.js. Nodes are tables, edges are relationships with cardinality labels. Zoom, pan, search, and click any table or relationship for details.

![Diagram - AdventureWorks relationships](docs/screenshots/04-diagram-tab.png)

### PBIT Support

Parses `.pbit` template files (ZIP with UTF-16LE encoded schema), including auto-generated date tables and all relationships.

![PBIT Model - Microsoft MDATP Status Board (29 tables, 27 relationships)](docs/screenshots/05-pbit-model.png)

![PBIT Diagram - MDATP device/alert relationships](docs/screenshots/06-pbit-diagram.png)

## Supported Formats

| Format | Extension | Description |
|--------|-----------|-------------|
| BIM/TMSL | `.bim` | Tabular Model Scripting Language JSON |
| PBIT | `.pbit` | Power BI Template (ZIP with DataModelSchema) |
| TMDL | `.zip` | Tabular Model Definition Language (zipped folder) |
| PBIP | `.pbip` | Power BI Project (zipped) |
| PBIX | `.pbix` | Power BI file (metadata only, data is XPress9 compressed) |

## Copy All Output

The **Copy All** button produces structured Markdown optimized for LLM consumption:

```markdown
# Model: AdventureWorks (CL 1200)
15 Tables | 67 Measures | 27 Relationships | 4 Roles

## Tables
### Internet Sales (27 columns, 17 measures)
| Column | Type | Description |
|--------|------|-------------|
| SalesOrderNumber | string | |
| OrderDate | dateTime | |
...

## Measures
### Internet Sales
#### Internet Total Sales
```dax
SUM('Internet Sales'[Sales Amount])
```
Format: \$#,0.00

## Relationships
| From | To | Cardinality | Cross-filter | Active |
|------|----|-------------|--------------|--------|
| Internet Sales[ProductKey] | Product[ProductKey] | *:1 | Single | Yes |
...

## Roles
### Read
| Table | Filter |
|-------|--------|
| Geography | [Country] = "US" |
```

Token estimates help plan LLM context window usage.

## Architecture

- **Single HTML file** (~553 KB) with all dependencies bundled inline
- **Zero network requests** - works fully offline, strict CSP
- [JSZip](https://stuk.github.io/jszip/) for ZIP extraction (PBIT/TMDL/PBIP)
- [Cytoscape.js](https://js.cytoscape.org/) for the relationship diagram

Inspired by [Power Query Explorer](https://github.com/lczanna/power-query-explorer).

## Development

### Run Tests

```bash
pip install playwright pytest pytest-playwright
python -m pytest scripts/run_tests.py -v --browser chromium
```

42 Playwright tests cover:
- **File parsing**: BIM, PBIT, TMDL formats with generated and real-world files
- **Downloaded test files**: AdventureWorks.bim (TabularEditor), AsPartitionProcessing.bim (Microsoft), MDATP_Status_Board.pbit (Microsoft), TMDL Sales model (Microsoft SamplePBIP)
- **UI interactions**: tab switching, search, select all, detail panel, copy
- **Diagram rendering**: node/edge count, search filtering
- **Error handling**: invalid files, empty JSON
- **Cross-format consistency**: BIM and PBIT of the same model produce identical output
- **Parser internals**: JSON parsing, column filtering, cardinality mapping, token estimation

### Take Screenshots

```bash
python scripts/take_screenshots.py
```

### Generate Test Fixtures

```bash
python scripts/generate_test_files.py
```

## Test Files

Test files from Microsoft and community repos:

| File | Source | Contents |
|------|--------|----------|
| `AdventureWorks.bim` | [TabularEditor](https://github.com/TabularEditor/TabularEditor) | 15 tables, 67 measures, 27 relationships, 4 roles |
| `AsPartitionProcessing.bim` | [Microsoft Analysis Services](https://github.com/microsoft/Analysis-Services) | 9 tables, 21 measures, 13 relationships |
| `MDATP_Status_Board.pbit` | [Microsoft MDE-PowerBI-Templates](https://github.com/microsoft/MDE-PowerBI-Templates) | 29 tables, 7 measures, 27 relationships |
| `tmdl-sales/` | [Microsoft Analysis Services SamplePBIP](https://github.com/microsoft/Analysis-Services) | 11 tables with measures, relationships, calculation groups |

## License

MIT
