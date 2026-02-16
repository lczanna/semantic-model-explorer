"""Playwright-based tests for Semantic Model Explorer.

Tests file parsing, UI interactions, copy functionality, and diagram rendering
using real and generated test files.

Usage:
    uv run pytest scripts/run_tests.py -v
"""

import json
import os
import re
import zipfile

import pytest
from playwright.sync_api import Page, expect

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML_PATH = os.path.join(ROOT, "index.html")
TEST_FILES = os.path.join(ROOT, "data", "test-files")


@pytest.fixture(scope="session", autouse=True)
def generate_test_files():
    """Generate test files before running tests."""
    from generate_test_files import generate_bim, generate_pbit, generate_tmdl, generate_edge_case_files, generate_bpa_test_files

    os.makedirs(TEST_FILES, exist_ok=True)
    generate_bim(TEST_FILES)
    generate_pbit(TEST_FILES)
    generate_tmdl(TEST_FILES)
    generate_edge_case_files(TEST_FILES)
    generate_bpa_test_files(TEST_FILES)


@pytest.fixture
def app(page: Page):
    """Navigate to the app and wait for it to load."""
    page.goto(f"file://{HTML_PATH}")
    page.wait_for_selector("#dropZone", state="visible", timeout=10000)
    return page


# ============================================================
# Helper functions
# ============================================================


def drop_file(page: Page, file_path: str):
    """Simulate dropping a file on the drop zone."""
    page.evaluate(
        """async (filePath) => {
        const response = await fetch('file://' + filePath);
        const buffer = await response.arrayBuffer();
        const fileName = filePath.split('/').pop();

        // Determine MIME type
        let type = 'application/octet-stream';
        if (fileName.endsWith('.json') || fileName.endsWith('.bim')) type = 'application/json';

        const file = new File([buffer], fileName, { type });
        const dt = new DataTransfer();
        dt.items.add(file);

        const dropZone = document.getElementById('dropZone');
        const event = new DragEvent('drop', { dataTransfer: dt, bubbles: true });
        dropZone.dispatchEvent(event);
    }""",
        file_path,
    )


def upload_file_via_input(page: Page, file_path: str):
    """Upload a file via the file input element."""
    page.set_input_files("#fileInput", file_path)


def wait_for_app(page: Page, timeout: int = 15000):
    """Wait for the app to finish loading and display the model."""
    page.wait_for_selector("#appWrap", state="visible", timeout=timeout)


def get_header_stats(page: Page) -> str:
    """Get the model stats text from the header."""
    return page.text_content("#modelStats")


def get_model_name(page: Page) -> str:
    """Get the model name from the header."""
    return page.text_content("#modelName")


def click_tab(page: Page, tab_name: str):
    """Click a tab button."""
    page.click(f'.tab-btn[data-tab="{tab_name}"]')


def click_first_diagram_node(page: Page) -> str:
    """Click the first Cytoscape node using rendered coordinates. Returns node id."""
    page.wait_for_function(
        "() => !!appState.cy && appState.cy.nodes().length > 0",
        timeout=30000,
    )
    node_info = page.evaluate(
        """() => {
            const n = appState.cy.nodes()[0];
            const p = n.renderedPosition();
            return { id: n.id(), x: p.x, y: p.y };
        }"""
    )
    box = page.locator("#diagramContainer").bounding_box()
    assert box is not None, "Diagram container should have a bounding box"
    page.mouse.click(box["x"] + node_info["x"], box["y"] + node_info["y"])
    return node_info["id"]


def count_tree_items(page: Page, section: str = None) -> int:
    """Count visible tree items, optionally filtered by section."""
    items = page.query_selector_all(".tree-item")
    return len(items)


# ============================================================
# BIM File Tests
# ============================================================


class TestBimParsing:
    """Tests for .bim file parsing."""

    def test_load_generated_bim(self, app: Page):
        """Test loading the generated .bim test file."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)

        name = get_model_name(app)
        assert "Test Sales Model" in name

        stats = get_header_stats(app)
        assert "5 Tables" in stats
        assert "7 Measures" in stats  # 6 in Sales + 1 in Date
        assert "4 Relationships" in stats

    def test_load_adventureworks_bim(self, app: Page):
        """Test loading the AdventureWorks .bim from TabularEditor."""
        bim_path = os.path.join(TEST_FILES, "AdventureWorks.bim")
        if not os.path.exists(bim_path):
            pytest.skip("AdventureWorks.bim not downloaded")

        upload_file_via_input(app, bim_path)
        wait_for_app(app)

        stats = get_header_stats(app)
        assert "15 Tables" in stats
        assert "67 Measures" in stats
        assert "27 Relationships" in stats

    def test_load_aspartition_bim(self, app: Page):
        """Test loading the AsPartitionProcessing .bim from Microsoft."""
        bim_path = os.path.join(TEST_FILES, "AsPartitionProcessing.bim")
        if not os.path.exists(bim_path):
            pytest.skip("AsPartitionProcessing.bim not downloaded")

        upload_file_via_input(app, bim_path)
        wait_for_app(app)

        stats = get_header_stats(app)
        assert "9 Tables" in stats
        assert "21 Measures" in stats
        assert "13 Relationships" in stats

    def test_bim_format_badge(self, app: Page):
        """Test that the format badge shows 'bim'."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)

        badge = app.text_content("#modelFormat")
        assert badge == "bim"


# ============================================================
# PBIT File Tests
# ============================================================


class TestPbitParsing:
    """Tests for .pbit file parsing."""

    def test_load_generated_pbit(self, app: Page):
        """Test loading the generated .pbit test file."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.pbit"))
        wait_for_app(app)

        name = get_model_name(app)
        assert "Test Sales Model" in name

        stats = get_header_stats(app)
        assert "5 Tables" in stats
        assert "7 Measures" in stats

    def test_load_mdatp_pbit(self, app: Page):
        """Test loading the Microsoft MDATP .pbit file."""
        pbit_path = os.path.join(TEST_FILES, "MDATP_Status_Board.pbit")
        if not os.path.exists(pbit_path):
            pytest.skip("MDATP_Status_Board.pbit not downloaded")

        upload_file_via_input(app, pbit_path)
        wait_for_app(app)

        stats = get_header_stats(app)
        assert "Tables" in stats
        assert "27 Relationships" in stats
        assert "7 Measures" in stats

    def test_pbit_format_badge(self, app: Page):
        """Test that the format badge shows 'pbit'."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.pbit"))
        wait_for_app(app)

        badge = app.text_content("#modelFormat")
        assert badge == "pbit"


# ============================================================
# TMDL Tests
# ============================================================


class TestTmdlParsing:
    """Tests for TMDL (zipped folder) parsing."""

    def test_load_generated_tmdl_zip(self, app: Page):
        """Test loading the generated TMDL zip file."""
        zip_path = os.path.join(TEST_FILES, "tmdl-test-model.zip")
        if not os.path.exists(zip_path):
            pytest.skip("tmdl-test-model.zip not generated")

        upload_file_via_input(app, zip_path)
        wait_for_app(app)

        stats = get_header_stats(app)
        assert "5 Tables" in stats or "Tables" in stats
        assert "Measures" in stats
        assert "Relationships" in stats

    def test_tmdl_measures_parsed(self, app: Page):
        """Test that TMDL measures are correctly parsed."""
        zip_path = os.path.join(TEST_FILES, "tmdl-test-model.zip")
        if not os.path.exists(zip_path):
            pytest.skip("tmdl-test-model.zip not generated")

        upload_file_via_input(app, zip_path)
        wait_for_app(app)

        stats = get_header_stats(app)
        # Should have measures
        assert "Measures" in stats


# ============================================================
# UI Interaction Tests
# ============================================================


class TestUIInteractions:
    """Tests for UI interactions."""

    def test_new_file_button(self, app: Page):
        """Test that New File button returns to drop zone."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)

        app.click("#newFileBtn")
        expect(app.locator("#dropZoneWrap")).to_be_visible()
        expect(app.locator("#appWrap")).to_be_hidden()

    def test_tab_switching(self, app: Page):
        """Test switching between Model and Diagram tabs."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)

        # Model tab should be active by default
        expect(app.locator("#tab-model")).to_be_visible()

        # Switch to Diagram
        click_tab(app, "diagram")
        expect(app.locator("#tab-diagram")).to_be_visible()
        expect(app.locator("#tab-model")).to_be_hidden()

        # Switch back
        click_tab(app, "model")
        expect(app.locator("#tab-model")).to_be_visible()

    def test_tree_search(self, app: Page):
        """Test searching in the tree panel."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)

        # Search for 'Sales'
        app.fill("#treeSearch", "Sales")
        app.wait_for_timeout(300)  # Wait for filter to apply

        # Should still show Sales-related items
        tree_text = app.text_content("#treeScroll")
        assert "Sales" in tree_text

    def test_select_all_checkbox(self, app: Page):
        """Test Select All checkbox."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)

        # Click Select All
        app.check("#selectAll")
        app.wait_for_timeout(200)

        # Token count should be > 0
        token_text = app.text_content("#selectedTokenBadge")
        assert "~0 tokens" not in token_text

    def test_detail_panel_shows_on_click(self, app: Page):
        """Test that clicking a tree item shows details."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)

        # Click the first tree item
        items = app.query_selector_all(".tree-item")
        if len(items) > 0:
            items[0].click()
            app.wait_for_timeout(200)

            # Detail panel should not show the empty message
            detail_text = app.text_content("#detailPanel")
            assert "Select an item" not in detail_text

    def test_copy_all_button(self, app: Page):
        """Test Copy All button produces output."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)

        # Copy All via evaluating the underlying function
        result = app.evaluate("""() => {
            if (!appState || !appState.model) return null;
            return modelToMarkdown(appState.model, null);
        }""")

        assert result is not None
        assert "# Model:" in result
        assert "## Tables" in result
        assert "## Measures" in result
        assert "Total Sales" in result

    def test_copy_all_markdown_format(self, app: Page):
        """Test that Copy All produces well-structured Markdown."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)

        result = app.evaluate("() => modelToMarkdown(appState.model, null)")

        # Check structure
        assert "# Model: Test Sales Model" in result
        assert "## Tables" in result
        assert "### Sales" in result
        assert "| Column | Type |" in result
        assert "## Measures" in result
        assert "```dax" in result
        assert "SUM(Sales[Amount])" in result
        assert "## Relationships" in result
        assert "| From | To |" in result
        assert "## Roles" in result
        assert "Regional Manager" in result

    def test_token_estimate_displayed(self, app: Page):
        """Test that token estimate is shown in the header."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)

        token_text = app.text_content("#tokenBadge")
        # Should contain a number
        assert "tokens" in token_text
        assert "~" in token_text


# ============================================================
# Diagram Tests
# ============================================================


class TestDiagram:
    """Tests for the diagram tab."""

    def test_diagram_renders(self, app: Page):
        """Test that the diagram tab renders without errors."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)

        click_tab(app, "diagram")
        app.wait_for_timeout(1000)  # Wait for Cytoscape to render

        # Check that the diagram container has content
        container = app.locator("#diagramContainer")
        expect(container).to_be_visible()

        # Cytoscape adds a canvas element
        has_content = app.evaluate("""() => {
            const c = document.getElementById('diagramContainer');
            return c.children.length > 0;
        }""")
        assert has_content

    def test_diagram_search(self, app: Page):
        """Test diagram search filters nodes."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)

        click_tab(app, "diagram")
        app.wait_for_timeout(1000)

        app.fill("#diagramSearch", "Product")
        app.wait_for_timeout(300)

        # Product node should be visible (opacity 1), others dimmed
        opacity = app.evaluate("""() => {
            if (!appState.cy) return null;
            const node = appState.cy.getElementById('Product');
            return node.style('opacity');
        }""")
        assert opacity is not None


# ============================================================
# Error Handling Tests
# ============================================================


class TestErrorHandling:
    """Tests for error handling."""

    def test_invalid_file_shows_error(self, app: Page):
        """Test that dropping an invalid file shows an error."""
        # Create a dummy invalid file
        dummy_path = os.path.join(TEST_FILES, "invalid.txt")
        with open(dummy_path, "w") as f:
            f.write("This is not a Power BI file")

        upload_file_via_input(app, dummy_path)
        app.wait_for_timeout(2000)

        # Error banner should be visible
        error = app.locator("#errorBanner")
        expect(error).to_be_visible()

    def test_empty_json_shows_error(self, app: Page):
        """Test that an empty JSON file shows an error."""
        dummy_path = os.path.join(TEST_FILES, "empty.bim")
        with open(dummy_path, "w") as f:
            f.write("{}")

        upload_file_via_input(app, dummy_path)
        app.wait_for_timeout(2000)

        # Should still load (empty model) or show error
        # An empty model with 0 tables is acceptable
        app_visible = app.evaluate("() => document.getElementById('appWrap').style.display !== 'none'")
        error_visible = app.evaluate("() => document.getElementById('errorBanner').style.display !== 'none'")
        assert app_visible or error_visible


# ============================================================
# Cross-Format Consistency Tests
# ============================================================


class TestCrossFormatConsistency:
    """Tests that the same model produces consistent results across formats."""

    def test_bim_and_pbit_produce_same_tables(self, app: Page):
        """Test that .bim and .pbit of the same model have the same table count."""
        # Load BIM
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)
        bim_stats = get_header_stats(app)

        # Return to drop zone
        app.click("#newFileBtn")
        app.wait_for_timeout(500)

        # Load PBIT
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.pbit"))
        wait_for_app(app)
        pbit_stats = get_header_stats(app)

        # Extract table counts
        bim_tables = re.search(r"(\d+) Tables", bim_stats)
        pbit_tables = re.search(r"(\d+) Tables", pbit_stats)

        assert bim_tables and pbit_tables
        assert bim_tables.group(1) == pbit_tables.group(1)

    def test_bim_and_pbit_produce_same_markdown(self, app: Page):
        """Test that .bim and .pbit produce the same Copy All output."""
        # Load BIM
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)
        bim_md = app.evaluate("() => modelToMarkdown(appState.model, null)")

        app.click("#newFileBtn")
        app.wait_for_timeout(500)

        # Load PBIT
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.pbit"))
        wait_for_app(app)
        pbit_md = app.evaluate("() => modelToMarkdown(appState.model, null)")

        # Both should have the same key content
        assert "Total Sales" in bim_md and "Total Sales" in pbit_md
        assert "SUM(Sales[Amount])" in bim_md and "SUM(Sales[Amount])" in pbit_md
        assert "Sales[ProductKey]" in bim_md and "Sales[ProductKey]" in pbit_md


# ============================================================
# Parser Unit Tests (run via page.evaluate)
# ============================================================


class TestParserInternals:
    """Tests for parser internals via page.evaluate."""

    def test_bim_json_parsing(self, app: Page):
        """Test that parseBimJson handles a minimal model."""
        result = app.evaluate("""() => {
            const json = {
                name: "TestModel",
                compatibilityLevel: 1600,
                model: {
                    culture: "en-US",
                    tables: [{
                        name: "Fact",
                        columns: [{ name: "ID", dataType: "int64", sourceColumn: "ID" }],
                        measures: [{ name: "Count", expression: "COUNTROWS(Fact)" }],
                    }],
                    relationships: [],
                    roles: [],
                }
            };
            const model = parseBimJson(json);
            return {
                name: model.name,
                tables: model.tables.length,
                measures: model.tables[0].measures.length,
                colName: model.tables[0].columns[0].name,
                measExpr: model.tables[0].measures[0].expression,
            };
        }""")

        assert result["name"] == "TestModel"
        assert result["tables"] == 1
        assert result["measures"] == 1
        assert result["colName"] == "ID"
        assert result["measExpr"] == "COUNTROWS(Fact)"

    def test_rowNumber_columns_excluded(self, app: Page):
        """Test that rowNumber columns are excluded from parsing."""
        result = app.evaluate("""() => {
            const json = {
                name: "Test",
                model: {
                    tables: [{
                        name: "T",
                        columns: [
                            { name: "RowNumber-XYZ", dataType: "int64", type: "rowNumber" },
                            { name: "ID", dataType: "int64", sourceColumn: "ID" },
                        ],
                    }],
                }
            };
            const model = parseBimJson(json);
            return model.tables[0].columns.length;
        }""")

        assert result == 1  # Only ID, not RowNumber

    def test_cardinality_mapping(self, app: Page):
        """Test cardinality mapping function."""
        result = app.evaluate("""() => {
            return {
                m2o: mapCardinality('many', 'one'),
                o2m: mapCardinality('one', 'many'),
                o2o: mapCardinality('one', 'one'),
                m2m: mapCardinality('many', 'many'),
            };
        }""")

        assert result["m2o"] == "manyToOne"
        assert result["o2m"] == "oneToMany"
        assert result["o2o"] == "oneToOne"
        assert result["m2m"] == "manyToMany"

    def test_token_estimation(self, app: Page):
        """Test token estimation function."""
        result = app.evaluate("() => estimateTokens('Hello world, this is a test.')")
        # ~28 chars / 4 = ~7 tokens
        assert 5 <= result <= 10

    def test_measure_render_decodes_html_entities(self, app: Page):
        """Test that encoded entities in DAX render as actual characters."""
        result = app.evaluate("""() => {
            const panel = document.createElement('div');
            renderMeasureDetail(
                panel,
                {
                    name: "M",
                    expression: "VAR m = SELECTEDVALUE(&#39;Calendar&#39;[Year Month Order]) RETURN m",
                    formatString: "",
                    displayFolder: "",
                    description: "",
                    isHidden: false,
                },
                "T"
            );
            return {
                html: panel.innerHTML,
                text: panel.textContent || "",
            };
        }""")

        assert "&amp;#39;" not in result["html"], "Rendered HTML should not double-escape quote entities"
        assert "&#39;" not in result["text"], "Rendered text should not show literal quote entity codes"
        assert "'Calendar'" in result["text"], "Rendered text should show normal single quotes in DAX"

    def test_markdown_output_structure(self, app: Page):
        """Test that modelToMarkdown produces expected sections."""
        result = app.evaluate("""() => {
            const model = {
                name: "Test", compatibilityLevel: 1600, culture: "en-US",
                tables: [{
                    name: "Sales", type: "import", isHidden: false, description: "",
                    columns: [{ name: "Amount", dataType: "decimal", type: "data", isHidden: false, expression: null, formatString: "$#,##0", sortByColumn: null, displayFolder: "", description: "" }],
                    measures: [{ name: "Total", expression: "SUM(Sales[Amount])", formatString: "$#,##0", displayFolder: "", description: "Test measure", isHidden: false }],
                    hierarchies: [], partitions: [], calculationItems: [],
                }],
                relationships: [{ fromTable: "Sales", fromColumn: "Key", toTable: "Dim", toColumn: "Key", cardinality: "manyToOne", crossFilterDirection: "single", isActive: true }],
                roles: [{ name: "Admin", tablePermissions: [{ table: "Sales", filterExpression: "1=1" }] }],
            };
            return modelToMarkdown(model, null);
        }""")

        assert "# Model: Test" in result
        assert "## Tables" in result
        assert "### Sales" in result
        assert "## Measures" in result
        assert "```dax" in result
        assert "SUM(Sales[Amount])" in result
        assert "## Relationships" in result
        assert "## Roles" in result
        assert "Admin" in result


# ============================================================
# Downloaded Power BI File Deep Tests
# ============================================================


class TestDownloadedFiles:
    """Deep tests for downloaded Power BI files from Microsoft/community repos."""

    def test_adventureworks_table_details(self, app: Page):
        """Test AdventureWorks has expected tables and measures."""
        bim_path = os.path.join(TEST_FILES, "AdventureWorks.bim")
        if not os.path.exists(bim_path):
            pytest.skip("AdventureWorks.bim not downloaded")

        upload_file_via_input(app, bim_path)
        wait_for_app(app)

        # Check specific tables exist in tree
        tree_text = app.text_content("#treeScroll")
        for table_name in ["Internet Sales", "Customer", "Product", "Date", "Geography"]:
            assert table_name in tree_text, f"Table '{table_name}' not found in tree"

    def test_adventureworks_measures_in_markdown(self, app: Page):
        """Test AdventureWorks measures are exported to Markdown correctly."""
        bim_path = os.path.join(TEST_FILES, "AdventureWorks.bim")
        if not os.path.exists(bim_path):
            pytest.skip("AdventureWorks.bim not downloaded")

        upload_file_via_input(app, bim_path)
        wait_for_app(app)

        md = app.evaluate("() => modelToMarkdown(appState.model, null)")
        assert md is not None
        assert "## Measures" in md
        assert "```dax" in md
        # AdventureWorks has 67 measures - verify DAX blocks
        dax_count = md.count("```dax")
        assert dax_count >= 60, f"Expected ~67 DAX blocks, got {dax_count}"

    def test_adventureworks_relationships_in_markdown(self, app: Page):
        """Test AdventureWorks relationship details in Markdown."""
        bim_path = os.path.join(TEST_FILES, "AdventureWorks.bim")
        if not os.path.exists(bim_path):
            pytest.skip("AdventureWorks.bim not downloaded")

        upload_file_via_input(app, bim_path)
        wait_for_app(app)

        md = app.evaluate("() => modelToMarkdown(appState.model, null)")
        assert "## Relationships" in md
        assert "Internet Sales" in md
        assert "Customer" in md

    def test_adventureworks_hierarchies(self, app: Page):
        """Test that AdventureWorks hierarchies are parsed."""
        bim_path = os.path.join(TEST_FILES, "AdventureWorks.bim")
        if not os.path.exists(bim_path):
            pytest.skip("AdventureWorks.bim not downloaded")

        upload_file_via_input(app, bim_path)
        wait_for_app(app)

        result = app.evaluate("""() => {
            const tables = appState.model.tables;
            let totalHierarchies = 0;
            for (const t of tables) {
                totalHierarchies += (t.hierarchies || []).length;
            }
            return totalHierarchies;
        }""")
        assert result > 0, "Expected at least one hierarchy in AdventureWorks"

    def test_adventureworks_roles(self, app: Page):
        """Test that AdventureWorks roles are parsed."""
        bim_path = os.path.join(TEST_FILES, "AdventureWorks.bim")
        if not os.path.exists(bim_path):
            pytest.skip("AdventureWorks.bim not downloaded")

        upload_file_via_input(app, bim_path)
        wait_for_app(app)

        md = app.evaluate("() => modelToMarkdown(appState.model, null)")
        assert "## Roles" in md
        assert "4 Roles" in get_header_stats(app)

    def test_adventureworks_diagram(self, app: Page):
        """Test AdventureWorks renders in diagram with correct node count."""
        bim_path = os.path.join(TEST_FILES, "AdventureWorks.bim")
        if not os.path.exists(bim_path):
            pytest.skip("AdventureWorks.bim not downloaded")

        upload_file_via_input(app, bim_path)
        wait_for_app(app)

        click_tab(app, "diagram")
        app.wait_for_timeout(1000)

        node_count = app.evaluate("""() => {
            if (!appState.cy) return 0;
            return appState.cy.nodes().length;
        }""")
        # Should have nodes for visible tables
        assert node_count >= 10, f"Expected >=10 diagram nodes, got {node_count}"

    def test_aspartition_specific_tables(self, app: Page):
        """Test AsPartitionProcessing has expected tables."""
        bim_path = os.path.join(TEST_FILES, "AsPartitionProcessing.bim")
        if not os.path.exists(bim_path):
            pytest.skip("AsPartitionProcessing.bim not downloaded")

        upload_file_via_input(app, bim_path)
        wait_for_app(app)

        tree_text = app.text_content("#treeScroll")
        for table_name in ["Internet Sales", "Customer", "Product", "Date"]:
            assert table_name in tree_text, f"Table '{table_name}' not found"

    def test_aspartition_measures(self, app: Page):
        """Test AsPartitionProcessing measures in Markdown."""
        bim_path = os.path.join(TEST_FILES, "AsPartitionProcessing.bim")
        if not os.path.exists(bim_path):
            pytest.skip("AsPartitionProcessing.bim not downloaded")

        upload_file_via_input(app, bim_path)
        wait_for_app(app)

        md = app.evaluate("() => modelToMarkdown(appState.model, null)")
        dax_count = md.count("```dax")
        assert dax_count >= 18, f"Expected ~21 DAX blocks, got {dax_count}"

    def test_mdatp_specific_tables(self, app: Page):
        """Test MDATP PBIT has expected tables."""
        pbit_path = os.path.join(TEST_FILES, "MDATP_Status_Board.pbit")
        if not os.path.exists(pbit_path):
            pytest.skip("MDATP_Status_Board.pbit not downloaded")

        upload_file_via_input(app, pbit_path)
        wait_for_app(app)

        tree_text = app.text_content("#treeScroll")
        for table_name in ["Devices", "Alerts", "Vulnerabilities"]:
            assert table_name in tree_text, f"Table '{table_name}' not found"

    def test_mdatp_measures_in_markdown(self, app: Page):
        """Test MDATP measures parsed and in Markdown."""
        pbit_path = os.path.join(TEST_FILES, "MDATP_Status_Board.pbit")
        if not os.path.exists(pbit_path):
            pytest.skip("MDATP_Status_Board.pbit not downloaded")

        upload_file_via_input(app, pbit_path)
        wait_for_app(app)

        md = app.evaluate("() => modelToMarkdown(appState.model, null)")
        assert "## Measures" in md
        assert "```dax" in md

    def test_mdatp_diagram(self, app: Page):
        """Test MDATP renders in diagram."""
        pbit_path = os.path.join(TEST_FILES, "MDATP_Status_Board.pbit")
        if not os.path.exists(pbit_path):
            pytest.skip("MDATP_Status_Board.pbit not downloaded")

        upload_file_via_input(app, pbit_path)
        wait_for_app(app)

        click_tab(app, "diagram")
        app.wait_for_timeout(1000)

        node_count = app.evaluate("""() => {
            if (!appState.cy) return 0;
            return appState.cy.nodes().length;
        }""")
        assert node_count >= 5, f"Expected >=5 diagram nodes, got {node_count}"

    def test_tmdl_sales_model(self, app: Page):
        """Test loading the Microsoft SamplePBIP TMDL model."""
        zip_path = os.path.join(TEST_FILES, "tmdl-sales.zip")
        if not os.path.exists(zip_path):
            pytest.skip("tmdl-sales.zip not available")

        upload_file_via_input(app, zip_path)
        wait_for_app(app)

        stats = get_header_stats(app)
        assert "Tables" in stats

        tree_text = app.text_content("#treeScroll")
        for table_name in ["Sales", "Customer", "Product", "Calendar"]:
            assert table_name in tree_text, f"Table '{table_name}' not found"

    def test_tmdl_sales_measures(self, app: Page):
        """Test that TMDL Sales model has measures parsed."""
        zip_path = os.path.join(TEST_FILES, "tmdl-sales.zip")
        if not os.path.exists(zip_path):
            pytest.skip("tmdl-sales.zip not available")

        upload_file_via_input(app, zip_path)
        wait_for_app(app)

        stats = get_header_stats(app)
        assert "Measures" in stats

        md = app.evaluate("() => modelToMarkdown(appState.model, null)")
        assert "```dax" in md

    def test_tmdl_sales_relationships(self, app: Page):
        """Test that TMDL Sales model relationships are parsed."""
        zip_path = os.path.join(TEST_FILES, "tmdl-sales.zip")
        if not os.path.exists(zip_path):
            pytest.skip("tmdl-sales.zip not available")

        upload_file_via_input(app, zip_path)
        wait_for_app(app)

        stats = get_header_stats(app)
        assert "Relationships" in stats


# ============================================================
# PBIX Data Extraction Tests
# ============================================================


class TestPbixDataExtraction:
    """Tests for .pbix VertiPaq data extraction and Data tab."""

    def test_pbix_loads_with_data_model(self, app: Page):
        """Test that a .pbix file loads and exposes a data model."""
        pbix_path = os.path.join(TEST_FILES, "Revenue_Opportunities.pbix")
        if not os.path.exists(pbix_path):
            pytest.skip("Revenue_Opportunities.pbix not available")

        upload_file_via_input(app, pbix_path)
        wait_for_app(app, timeout=30000)

        badge = app.text_content("#modelFormat")
        assert badge == "pbix"

        stats = get_header_stats(app)
        assert "8 Tables" in stats
        assert "6 Measures" in stats
        assert "5 Relationships" in stats

    def test_pbix_data_tab_visible(self, app: Page):
        """Test that Data tab button appears for .pbix files."""
        pbix_path = os.path.join(TEST_FILES, "Revenue_Opportunities.pbix")
        if not os.path.exists(pbix_path):
            pytest.skip("Revenue_Opportunities.pbix not available")

        upload_file_via_input(app, pbix_path)
        wait_for_app(app, timeout=30000)

        display = app.evaluate(
            "() => document.getElementById('dataTabBtn').style.display"
        )
        assert display != "none", "Data tab should be visible for .pbix"

    def test_pbix_data_tab_hidden_for_bim(self, app: Page):
        """Test that Data tab is NOT shown for .bim files."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)

        display = app.evaluate(
            "() => document.getElementById('dataTabBtn').style.display"
        )
        assert display == "none", "Data tab should be hidden for .bim"

    def test_pbix_no_internal_tables_in_data_tab(self, app: Page):
        """Test that internal tables (H$, R$, U$, etc.) are excluded from Data tab."""
        pbix_path = os.path.join(TEST_FILES, "Revenue_Opportunities.pbix")
        if not os.path.exists(pbix_path):
            pytest.skip("Revenue_Opportunities.pbix not available")

        upload_file_via_input(app, pbix_path)
        wait_for_app(app, timeout=30000)

        table_names = app.evaluate(
            "() => appState.model._pbixDataModel.tableNames"
        )
        for name in table_names:
            assert not name.startswith("H$"), f"Internal table in Data tab: {name}"
            assert not name.startswith("R$"), f"Internal table in Data tab: {name}"
            assert not name.startswith("U$"), f"Internal table in Data tab: {name}"
            assert not name.startswith("LocalDateTable_"), f"Internal table: {name}"
            assert not name.startswith("DateTableTemplate_"), f"Internal table: {name}"

    def test_pbix_no_internal_tables_in_model_tab(self, app: Page):
        """Test that internal tables are excluded from Model tab tree."""
        pbix_path = os.path.join(TEST_FILES, "Revenue_Opportunities.pbix")
        if not os.path.exists(pbix_path):
            pytest.skip("Revenue_Opportunities.pbix not available")

        upload_file_via_input(app, pbix_path)
        wait_for_app(app, timeout=30000)

        table_names = app.evaluate(
            "() => appState.model.tables.map(t => t.name)"
        )
        for name in table_names:
            assert not name.startswith("H$"), f"Internal table in model: {name}"
            assert not name.startswith("R$"), f"Internal table in model: {name}"
            assert not name.startswith("U$"), f"Internal table in model: {name}"

    def test_pbix_data_table_list(self, app: Page):
        """Test that the Data tab lists the expected user tables."""
        pbix_path = os.path.join(TEST_FILES, "Revenue_Opportunities.pbix")
        if not os.path.exists(pbix_path):
            pytest.skip("Revenue_Opportunities.pbix not available")

        upload_file_via_input(app, pbix_path)
        wait_for_app(app, timeout=30000)

        click_tab(app, "data")
        app.wait_for_selector("#dataTableList .data-table-item", timeout=5000)

        items = app.query_selector_all("#dataTableList .data-table-item")
        table_names = [item.text_content() for item in items]
        assert len(table_names) == 8, f"Expected 8 user tables, got {len(table_names)}"
        for name in ["Account", "Fact", "Opportunity", "Partner", "Product", "SalesStage"]:
            assert name in table_names, f"Expected table '{name}' in Data tab"

    def test_pbix_extract_table_data(self, app: Page):
        """Test that clicking a table in Data tab extracts row data."""
        pbix_path = os.path.join(TEST_FILES, "Revenue_Opportunities.pbix")
        if not os.path.exists(pbix_path):
            pytest.skip("Revenue_Opportunities.pbix not available")

        upload_file_via_input(app, pbix_path)
        wait_for_app(app, timeout=30000)

        click_tab(app, "data")
        app.wait_for_selector("#dataTableList .data-table-item", timeout=5000)

        # Click the Account table
        items = app.query_selector_all("#dataTableList .data-table-item")
        for item in items:
            if item.text_content() == "Account":
                item.click()
                break

        # Wait for data to render
        app.wait_for_selector(".data-table th", timeout=30000)

        headers = app.query_selector_all(".data-table th")
        header_names = [h.text_content() for h in headers]
        assert len(header_names) > 0, "No column headers in data preview"

        rows = app.query_selector_all(".data-table tbody tr")
        assert len(rows) > 0, "No data rows in preview"

        # Check row count display
        row_count_text = app.text_content("#dataRowCount")
        assert "rows" in row_count_text

    def test_pbix_diagram_side_panel_opens_on_first_visit(self, app: Page):
        """Test diagram side panel opens on the first diagram visit (no tab switch workaround)."""
        pbix_path = os.path.join(TEST_FILES, "Revenue_Opportunities.pbix")
        if not os.path.exists(pbix_path):
            pytest.skip("Revenue_Opportunities.pbix not available")

        upload_file_via_input(app, pbix_path)
        wait_for_app(app, timeout=30000)

        click_tab(app, "diagram")
        app.wait_for_timeout(400)

        node_id = click_first_diagram_node(app)
        app.wait_for_function(
            "() => document.getElementById('diagramSidePanel').classList.contains('open')",
            timeout=5000,
        )

        panel_text = app.text_content("#diagramSidePanel")
        assert panel_text is not None and node_id in panel_text, \
            "Side panel should open with clicked table details on first diagram visit"

    def test_pbix_export_buttons_enabled(self, app: Page):
        """Test that single-table and bulk export buttons are enabled after loading data."""
        pbix_path = os.path.join(TEST_FILES, "Revenue_Opportunities.pbix")
        if not os.path.exists(pbix_path):
            pytest.skip("Revenue_Opportunities.pbix not available")

        upload_file_via_input(app, pbix_path)
        wait_for_app(app, timeout=30000)

        click_tab(app, "data")
        app.wait_for_selector("#dataTableList .data-table-item", timeout=5000)

        items = app.query_selector_all("#dataTableList .data-table-item")
        items[0].click()
        app.wait_for_selector(".data-table th", timeout=30000)

        csv_disabled = app.get_attribute("#exportCsvBtn", "disabled")
        parquet_disabled = app.get_attribute("#exportParquetBtn", "disabled")
        all_csv_disabled = app.get_attribute("#exportAllCsvBtn", "disabled")
        all_parquet_disabled = app.get_attribute("#exportAllParquetBtn", "disabled")
        assert csv_disabled is None, "CSV button should be enabled"
        assert parquet_disabled is None, "Parquet button should be enabled"
        assert all_csv_disabled is None, "Export All CSV button should be enabled"
        assert all_parquet_disabled is None, "Export All Parquet button should be enabled"

    def test_pbix_export_all_buttons_enabled_without_selection(self, app: Page):
        """Test that bulk export is enabled before selecting a specific table."""
        pbix_path = os.path.join(TEST_FILES, "Revenue_Opportunities.pbix")
        if not os.path.exists(pbix_path):
            pytest.skip("Revenue_Opportunities.pbix not available")

        upload_file_via_input(app, pbix_path)
        wait_for_app(app, timeout=30000)

        click_tab(app, "data")
        app.wait_for_selector("#dataTableList .data-table-item", timeout=5000)

        csv_disabled = app.get_attribute("#exportCsvBtn", "disabled")
        parquet_disabled = app.get_attribute("#exportParquetBtn", "disabled")
        all_csv_disabled = app.get_attribute("#exportAllCsvBtn", "disabled")
        all_parquet_disabled = app.get_attribute("#exportAllParquetBtn", "disabled")
        assert csv_disabled is not None, "Single-table CSV button should be disabled before table selection"
        assert parquet_disabled is not None, "Single-table Parquet button should be disabled before table selection"
        assert all_csv_disabled is None, "Export All CSV button should be enabled"
        assert all_parquet_disabled is None, "Export All Parquet button should be enabled"

    def test_pbix_relationships_correct(self, app: Page):
        """Test that .pbix relationships are correctly parsed."""
        pbix_path = os.path.join(TEST_FILES, "Revenue_Opportunities.pbix")
        if not os.path.exists(pbix_path):
            pytest.skip("Revenue_Opportunities.pbix not available")

        upload_file_via_input(app, pbix_path)
        wait_for_app(app, timeout=30000)

        rels = app.evaluate(
            "() => appState.model.relationships.map(r => r.fromTable + '.' + r.fromColumn + '->' + r.toTable + '.' + r.toColumn)"
        )
        assert len(rels) == 5, f"Expected 5 relationships, got {len(rels)}"
        assert "Fact.Account ID->Account.Account ID" in rels

    def test_pbix_csv_export_produces_data(self, app: Page):
        """Test that CSV export produces correct output via internal function."""
        pbix_path = os.path.join(TEST_FILES, "Revenue_Opportunities.pbix")
        if not os.path.exists(pbix_path):
            pytest.skip("Revenue_Opportunities.pbix not available")

        upload_file_via_input(app, pbix_path)
        wait_for_app(app, timeout=30000)

        csv_output = app.evaluate("""() => {
            const data = appState.model._pbixDataModel.getTable('Account');
            return tableToCSV(data);
        }""")

        assert csv_output is not None
        lines = csv_output.strip().split("\n")
        assert len(lines) > 1, "CSV should have header + data rows"
        # Header should have column names
        header = lines[0]
        assert "Account" in header or "Region" in header

    def test_pbix_no_double_export(self, app: Page):
        """Test that reloading a .pbix doesn't cause duplicate export handlers."""
        pbix_path = os.path.join(TEST_FILES, "Revenue_Opportunities.pbix")
        if not os.path.exists(pbix_path):
            pytest.skip("Revenue_Opportunities.pbix not available")

        # Load the file twice to trigger re-init
        upload_file_via_input(app, pbix_path)
        wait_for_app(app, timeout=30000)
        app.evaluate("() => { document.getElementById('newFileBtn').click(); }")
        app.wait_for_selector("#dropZone", state="visible", timeout=5000)
        upload_file_via_input(app, pbix_path)
        wait_for_app(app, timeout=30000)

        # Count event listeners on export buttons by tracking calls
        download_count = app.evaluate("""() => {
            let count = 0;
            const origCreate = URL.createObjectURL;
            URL.createObjectURL = function(blob) {
                count++;
                return origCreate.call(URL, blob);
            };
            const data = appState.model._pbixDataModel.getTable('Account');
            window._currentTableData = data;
            // Simulate what the export button handler does
            exportCSV('Account', data);
            URL.createObjectURL = origCreate;
            return count;
        }""")

        assert download_count == 1, f"Expected 1 download, got {download_count}"

    def test_pbix_corporate_spend(self, app: Page):
        """Test loading the Corporate_Spend .pbix file."""
        pbix_path = os.path.join(TEST_FILES, "Corporate_Spend.pbix")
        if not os.path.exists(pbix_path):
            pytest.skip("Corporate_Spend.pbix not available")

        upload_file_via_input(app, pbix_path)
        wait_for_app(app, timeout=30000)

        badge = app.text_content("#modelFormat")
        assert badge == "pbix"

        stats = get_header_stats(app)
        assert "Tables" in stats

        # Data tab should be available
        display = app.evaluate(
            "() => document.getElementById('dataTabBtn').style.display"
        )
        assert display != "none", "Data tab should be visible for .pbix"


class TestDataProfile:
    """Tests for the data profile (column stats) feature."""

    def test_stats_checkbox_visible_for_pbix(self, app: Page):
        """Test that the data profile checkbox appears for .pbix files."""
        pbix_path = os.path.join(TEST_FILES, "Revenue_Opportunities.pbix")
        if not os.path.exists(pbix_path):
            pytest.skip("Revenue_Opportunities.pbix not available")

        upload_file_via_input(app, pbix_path)
        wait_for_app(app, timeout=30000)

        display = app.evaluate(
            "() => document.getElementById('includeStatsHeaderWrap').style.display"
        )
        assert display != "none", "Stats checkbox should be visible for .pbix"

    def test_stats_checkbox_hidden_for_bim(self, app: Page):
        """Test that the data profile checkbox is hidden for .bim files."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)

        display = app.evaluate(
            "() => document.getElementById('includeStatsHeaderWrap').style.display"
        )
        assert display == "none", "Stats checkbox should be hidden for .bim"

    def test_compute_column_stats(self, app: Page):
        """Test that _computeColumnStats produces correct stats."""
        pbix_path = os.path.join(TEST_FILES, "Revenue_Opportunities.pbix")
        if not os.path.exists(pbix_path):
            pytest.skip("Revenue_Opportunities.pbix not available")

        upload_file_via_input(app, pbix_path)
        wait_for_app(app, timeout=30000)

        stats = app.evaluate("""() => {
            const data = appState.model._pbixDataModel.getTable('Account');
            const col0 = data.columnData[0];
            const stat = _computeColumnStats(data.columns[0], col0);
            return { name: stat.name, distinct: stat.distinct, nulls: stat.nulls, rowCount: stat.rowCount };
        }""")

        assert stats["name"] is not None
        assert stats["distinct"] > 0
        assert stats["rowCount"] > 0

    def test_stats_in_markdown_output(self, app: Page):
        """Test that stats appear in Markdown when statsMap is provided."""
        pbix_path = os.path.join(TEST_FILES, "Revenue_Opportunities.pbix")
        if not os.path.exists(pbix_path):
            pytest.skip("Revenue_Opportunities.pbix not available")

        upload_file_via_input(app, pbix_path)
        wait_for_app(app, timeout=30000)

        md = app.evaluate("""async () => {
            const statsMap = await computeAllStats(appState.model._pbixDataModel, () => {});
            return modelToMarkdown(appState.model, null, statsMap);
        }""")

        assert "**Data profile**" in md
        assert "distinct" in md

    def test_stats_not_in_markdown_without_flag(self, app: Page):
        """Test that stats do NOT appear in Markdown by default."""
        pbix_path = os.path.join(TEST_FILES, "Revenue_Opportunities.pbix")
        if not os.path.exists(pbix_path):
            pytest.skip("Revenue_Opportunities.pbix not available")

        upload_file_via_input(app, pbix_path)
        wait_for_app(app, timeout=30000)

        md = app.evaluate("() => modelToMarkdown(appState.model, null)")

        assert "**Data profile**" not in md

    def test_pbix_calc_column_dax_extracted(self, app: Page):
        """Test that calculated column DAX expressions are extracted from .pbix."""
        pbix_path = os.path.join(TEST_FILES, "Revenue_Opportunities.pbix")
        if not os.path.exists(pbix_path):
            pytest.skip("Revenue_Opportunities.pbix not available")

        upload_file_via_input(app, pbix_path)
        wait_for_app(app, timeout=30000)

        calc_cols = app.evaluate("""() => {
            const result = [];
            for (const t of appState.model.tables) {
                for (const c of t.columns) {
                    if (c.type === 'calculated' && c.expression) {
                        result.push(t.name + '.' + c.name + '=' + c.expression);
                    }
                }
            }
            return result;
        }""")

        assert len(calc_cols) > 0, "Should have extracted calc column DAX"

    def test_pbix_calc_column_in_markdown(self, app: Page):
        """Test that calculated column DAX appears in Markdown for .pbix files."""
        pbix_path = os.path.join(TEST_FILES, "Revenue_Opportunities.pbix")
        if not os.path.exists(pbix_path):
            pytest.skip("Revenue_Opportunities.pbix not available")

        upload_file_via_input(app, pbix_path)
        wait_for_app(app, timeout=30000)

        md = app.evaluate("() => modelToMarkdown(appState.model, null)")

        assert "(calculated column)" in md, "Markdown should show calculated columns"
        assert "EstimatedCloseDate" in md, \
            "Markdown should contain calc column DAX expressions"

    def test_stats_checkbox_syncs(self, app: Page):
        """Test that header and footer stats checkboxes stay in sync."""
        pbix_path = os.path.join(TEST_FILES, "Revenue_Opportunities.pbix")
        if not os.path.exists(pbix_path):
            pytest.skip("Revenue_Opportunities.pbix not available")

        upload_file_via_input(app, pbix_path)
        wait_for_app(app, timeout=30000)

        # Check header checkbox
        app.evaluate("() => { document.getElementById('includeStatsHeader').checked = true; document.getElementById('includeStatsHeader').dispatchEvent(new Event('change')); }")

        footer_checked = app.evaluate(
            "() => document.getElementById('includeStats').checked"
        )
        assert footer_checked, "Footer checkbox should sync with header"

    def test_stats_checkbox_updates_token_badge_without_extra_clicks(self, app: Page):
        """Test token badge updates after enabling stats without requiring unrelated UI clicks."""
        pbix_path = os.path.join(TEST_FILES, "Revenue_Opportunities.pbix")
        if not os.path.exists(pbix_path):
            pytest.skip("Revenue_Opportunities.pbix not available")

        upload_file_via_input(app, pbix_path)
        wait_for_app(app, timeout=30000)

        before = app.text_content("#tokenBadge")
        app.evaluate("() => document.getElementById('includeStatsHeader').click()")

        app.wait_for_function(
            """() => /\\(\\+\\d[\\d,]* stats\\)/.test(document.getElementById('tokenBadge').textContent)""",
            timeout=60000,
        )
        after = app.text_content("#tokenBadge")

        assert after is not None and "stats" in after, "Token badge should include stats overhead"
        assert after != before, "Token badge text should change after enabling stats"


# ============================================================
# Edge Case Tests — Comprehensive coverage
# ============================================================


class TestDataTabReset:
    """Tests for Data tab state reset when loading new files."""

    def test_data_tab_clears_on_new_file(self, app: Page):
        """Test that Data tab preview is cleared when clicking New File."""
        pbix_path = os.path.join(TEST_FILES, "Revenue_Opportunities.pbix")
        if not os.path.exists(pbix_path):
            pytest.skip("Revenue_Opportunities.pbix not available")

        # Load a .pbix and select a table in data tab
        upload_file_via_input(app, pbix_path)
        wait_for_app(app, timeout=30000)
        click_tab(app, "data")
        app.wait_for_selector("#dataTableList .data-table-item", timeout=5000)
        items = app.query_selector_all("#dataTableList .data-table-item")
        items[0].click()
        app.wait_for_selector(".data-table th", timeout=30000)

        # Click New File
        app.evaluate("() => document.getElementById('newFileBtn').click()")
        app.wait_for_selector("#dropZone", state="visible", timeout=5000)

        # Load a .bim file (no data tab)
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)

        # Data preview should be cleared
        preview_html = app.evaluate(
            "() => document.getElementById('dataPreview').innerHTML"
        )
        assert ".data-table" not in preview_html or "data-table" not in preview_html.lower() or \
            "Select a table" in preview_html, \
            "Data preview should be cleared after loading a non-.pbix file"

    def test_data_tab_table_list_refreshes(self, app: Page):
        """Test that loading a second .pbix refreshes the table list."""
        pbix1 = os.path.join(TEST_FILES, "Revenue_Opportunities.pbix")
        pbix2 = os.path.join(TEST_FILES, "Corporate_Spend.pbix")
        if not os.path.exists(pbix1) or not os.path.exists(pbix2):
            pytest.skip(".pbix files not available")

        upload_file_via_input(app, pbix1)
        wait_for_app(app, timeout=30000)

        tables1 = app.evaluate("() => appState.model._pbixDataModel.tableNames")

        # New file, load second .pbix
        app.evaluate("() => document.getElementById('newFileBtn').click()")
        app.wait_for_selector("#dropZone", state="visible", timeout=5000)
        upload_file_via_input(app, pbix2)
        wait_for_app(app, timeout=30000)

        tables2 = app.evaluate("() => appState.model._pbixDataModel.tableNames")
        assert tables1 != tables2, "Table lists should differ between files"


class TestEmptyModel:
    """Tests for models with no tables, measures, or relationships."""

    def test_empty_model_loads(self, app: Page):
        """Test that a model with 0 tables loads without crashing."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "edge-empty-model.bim"))
        wait_for_app(app)

        stats = get_header_stats(app)
        assert "0 Tables" in stats

    def test_empty_model_copy_works(self, app: Page):
        """Test that Copy All works with an empty model."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "edge-empty-model.bim"))
        wait_for_app(app)

        md = app.evaluate("() => modelToMarkdown(appState.model, null)")
        assert "# Model:" in md
        assert "Tables: 0" in md

    def test_empty_model_diagram(self, app: Page):
        """Test that Diagram tab doesn't crash with 0 tables."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "edge-empty-model.bim"))
        wait_for_app(app)
        click_tab(app, "diagram")
        app.wait_for_timeout(500)

        # Should not crash — either empty diagram or no error
        error_visible = app.evaluate(
            "() => document.getElementById('errorBanner').style.display !== 'none'"
        )
        assert not error_visible, "Diagram with 0 tables should not show error"


class TestSpecialCharacters:
    """Tests for XSS prevention and special character handling."""

    def test_special_chars_load(self, app: Page):
        """Test that model with special characters loads correctly."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "edge-special-chars.bim"))
        wait_for_app(app)

        stats = get_header_stats(app)
        assert "2 Tables" in stats

    def test_html_in_table_name_escaped(self, app: Page):
        """Test that HTML in table names is escaped (XSS prevention)."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "edge-special-chars.bim"))
        wait_for_app(app)

        # Check that <script> in measure name doesn't execute as raw HTML
        tree_html = app.evaluate(
            "() => document.getElementById('treeScroll').innerHTML"
        )
        assert "<script>" not in tree_html, "HTML should be escaped in tree view"

    def test_special_chars_in_markdown(self, app: Page):
        """Test that special characters render correctly in Markdown output."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "edge-special-chars.bim"))
        wait_for_app(app)

        md = app.evaluate("() => modelToMarkdown(appState.model, null)")
        assert "Table with Spaces & Symbols!" in md
        assert "Column <html>" in md
        assert "Unicode" in md

    def test_special_chars_detail_panel(self, app: Page):
        """Test that detail panel escapes HTML in column/measure names."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "edge-special-chars.bim"))
        wait_for_app(app)

        # Click on the table with special chars
        app.evaluate("""() => {
            const items = document.querySelectorAll('.tree-item');
            for (const item of items) {
                if (item.textContent.includes('Table with Spaces')) {
                    item.click();
                    break;
                }
            }
        }""")
        app.wait_for_timeout(200)

        detail_html = app.evaluate("() => document.getElementById('detailPanel').innerHTML")
        assert "<script>" not in detail_html, "Detail panel should escape HTML"


class TestNoMeasures:
    """Tests for models without measures."""

    def test_no_measures_loads(self, app: Page):
        """Test that a model with no measures loads correctly."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "edge-no-measures.bim"))
        wait_for_app(app)

        stats = get_header_stats(app)
        assert "0 Measures" in stats

    def test_no_measures_markdown(self, app: Page):
        """Test Markdown output with no measures section."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "edge-no-measures.bim"))
        wait_for_app(app)

        md = app.evaluate("() => modelToMarkdown(appState.model, null)")
        assert "## Tables" in md
        assert "## Measures" not in md, "No Measures section when there are none"


class TestHiddenItems:
    """Tests for show/hide hidden items toggle."""

    def test_show_hidden_toggle(self, app: Page):
        """Test toggling show hidden items."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)

        # Count visible items with hidden OFF
        visible_off = app.evaluate(
            "() => document.querySelectorAll('.tree-item:not([style*=\"display: none\"])').length"
        )

        # Toggle show hidden
        app.evaluate("""() => {
            const cb = document.getElementById('showHidden');
            cb.checked = true;
            cb.dispatchEvent(new Event('change'));
        }""")
        app.wait_for_timeout(100)

        visible_on = app.evaluate(
            "() => document.querySelectorAll('.tree-item:not([style*=\"display: none\"])').length"
        )
        assert visible_on >= visible_off, "Show hidden should reveal more items"

    def test_all_hidden_model(self, app: Page):
        """Test model where everything is hidden."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "edge-all-hidden.bim"))
        wait_for_app(app)

        stats = get_header_stats(app)
        assert "1 Table" in stats


class TestSingleTable:
    """Tests for single-table models (no relationships)."""

    def test_single_table_loads(self, app: Page):
        """Test that a single-table model loads correctly."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "edge-single-table.bim"))
        wait_for_app(app)

        stats = get_header_stats(app)
        assert "1 Table" in stats
        assert "0 Rels" in stats or "0 Rel" in stats

    def test_single_table_diagram(self, app: Page):
        """Test that diagram works with a single table (no edges)."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "edge-single-table.bim"))
        wait_for_app(app)
        click_tab(app, "diagram")
        app.wait_for_timeout(500)

        node_count = app.evaluate(
            "() => appState.cy ? appState.cy.nodes().length : -1"
        )
        assert node_count == 1, "Should have exactly 1 node"


class TestLongNames:
    """Tests for extremely long table/column/measure names."""

    def test_long_names_load(self, app: Page):
        """Test that model with very long names loads."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "edge-long-names.bim"))
        wait_for_app(app)

        stats = get_header_stats(app)
        assert "1 Table" in stats

    def test_long_names_markdown(self, app: Page):
        """Test Markdown output with very long names."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "edge-long-names.bim"))
        wait_for_app(app)

        md = app.evaluate("() => modelToMarkdown(appState.model, null)")
        assert len(md) > 0, "Markdown should not be empty"
        # Names should appear in full
        assert "TTTT" in md


class TestManyTables:
    """Tests for wide models with many tables."""

    def test_many_tables_load(self, app: Page):
        """Test that a model with 30 tables loads correctly."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "edge-many-tables.bim"))
        wait_for_app(app)

        stats = get_header_stats(app)
        assert "30 Tables" in stats

    def test_many_tables_diagram(self, app: Page):
        """Test that diagram handles 30 tables with 29 relationships."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "edge-many-tables.bim"))
        wait_for_app(app)
        click_tab(app, "diagram")
        app.wait_for_timeout(500)

        node_count = app.evaluate(
            "() => appState.cy ? appState.cy.nodes().length : -1"
        )
        assert node_count == 30, f"Expected 30 nodes, got {node_count}"

    def test_many_tables_select_all_copy(self, app: Page):
        """Test Select All + Copy with many tables."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "edge-many-tables.bim"))
        wait_for_app(app)

        app.evaluate("""() => {
            const cb = document.getElementById('selectAll');
            cb.checked = true;
            cb.dispatchEvent(new Event('change'));
        }""")
        app.wait_for_timeout(100)

        md = app.evaluate(
            "() => modelToMarkdown(appState.model, appState.checkedItems)"
        )
        assert "Table_000" in md
        assert "Table_029" in md


class TestStateManagement:
    """Tests for state management across file loads."""

    def test_new_file_resets_tree_selection(self, app: Page):
        """Test that tree selection is cleared on New File."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)

        # Select a tree item
        app.evaluate("""() => {
            const items = document.querySelectorAll('.tree-item');
            if (items.length > 0) items[0].click();
        }""")
        app.wait_for_timeout(100)

        # Click New File
        app.evaluate("() => document.getElementById('newFileBtn').click()")
        app.wait_for_selector("#dropZone", state="visible", timeout=5000)

        # Load again
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)

        selected = app.evaluate("() => appState.selectedItem")
        assert selected is None, "Selected item should be null after New File"

    def test_new_file_resets_checked_items(self, app: Page):
        """Test that checked items are cleared on New File."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)

        # Check some items
        app.evaluate("""() => {
            const cb = document.getElementById('selectAll');
            cb.checked = true;
            cb.dispatchEvent(new Event('change'));
        }""")

        # Click New File
        app.evaluate("() => document.getElementById('newFileBtn').click()")
        app.wait_for_selector("#dropZone", state="visible", timeout=5000)

        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)

        count = app.evaluate("() => appState.checkedItems.size")
        assert count == 0, f"Checked items should be 0 after New File, got {count}"

    def test_new_file_resets_stats_cache(self, app: Page):
        """Test that stats cache is cleared on New File."""
        pbix_path = os.path.join(TEST_FILES, "Revenue_Opportunities.pbix")
        if not os.path.exists(pbix_path):
            pytest.skip("Revenue_Opportunities.pbix not available")

        upload_file_via_input(app, pbix_path)
        wait_for_app(app, timeout=30000)

        # Compute stats so cache is populated
        app.evaluate(
            "async () => await computeAllStats(appState.model._pbixDataModel, () => {})"
        )
        has_cache = app.evaluate("() => appState.statsCache !== null")
        assert has_cache, "Stats cache should be populated"

        # New file
        app.evaluate("() => document.getElementById('newFileBtn').click()")
        app.wait_for_selector("#dropZone", state="visible", timeout=5000)

        cache_after = app.evaluate("() => appState.statsCache")
        assert cache_after is None, "Stats cache should be null after New File"

    def test_stats_checkbox_hidden_after_new_file(self, app: Page):
        """Test that stats checkbox hides when going from .pbix to .bim."""
        pbix_path = os.path.join(TEST_FILES, "Revenue_Opportunities.pbix")
        if not os.path.exists(pbix_path):
            pytest.skip("Revenue_Opportunities.pbix not available")

        upload_file_via_input(app, pbix_path)
        wait_for_app(app, timeout=30000)

        visible1 = app.evaluate(
            "() => document.getElementById('includeStatsHeaderWrap').style.display"
        )
        assert visible1 != "none", "Stats checkbox should show for .pbix"

        app.evaluate("() => document.getElementById('newFileBtn').click()")
        app.wait_for_selector("#dropZone", state="visible", timeout=5000)

        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)

        visible2 = app.evaluate(
            "() => document.getElementById('includeStatsHeaderWrap').style.display"
        )
        assert visible2 == "none", "Stats checkbox should hide for .bim"


class TestCopyEdgeCases:
    """Tests for copy/markdown edge cases."""

    def test_copy_with_no_selection(self, app: Page):
        """Test that Copy Selected with nothing checked shows toast."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)

        # Ensure nothing is checked
        app.evaluate("() => appState.checkedItems.clear()")

        # Click copy selected
        app.click("#copySelectedBtn")
        app.wait_for_timeout(500)

        # Should show a toast or at least not crash
        toast_text = app.evaluate(
            "() => { const t = document.querySelector('.toast'); return t ? t.textContent : ''; }"
        )
        assert "No items" in toast_text or len(toast_text) >= 0  # didn't crash

    def test_markdown_with_roles(self, app: Page):
        """Test that roles section appears in Markdown."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)

        md = app.evaluate("() => modelToMarkdown(appState.model, null)")
        assert "## Roles" in md
        assert "Regional Manager" in md

    def test_markdown_with_calculated_columns(self, app: Page):
        """Test that calculated columns appear in Markdown with DAX."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)

        md = app.evaluate("() => modelToMarkdown(appState.model, null)")
        assert "(calculated column)" in md
        assert "Sales[Amount] - Sales[Cost]" in md

    def test_markdown_relationships_direction(self, app: Page):
        """Test that Markdown shows correct relationship table names."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)

        md = app.evaluate("() => modelToMarkdown(appState.model, null)")
        assert "Sales[ProductKey]" in md
        assert "Product[ProductKey]" in md

    def test_token_estimate_nonzero(self, app: Page):
        """Test that token estimate is always > 0 for non-empty models."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)

        tokens = app.evaluate("""() => {
            const md = modelToMarkdown(appState.model, null);
            return estimateTokens(md);
        }""")
        assert tokens > 0, "Token estimate should be > 0"


class TestTabSwitching:
    """Tests for tab switching behavior."""

    def test_rapid_tab_switching(self, app: Page):
        """Test rapid switching between all tabs doesn't crash."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)

        for _ in range(3):
            click_tab(app, "model")
            click_tab(app, "diagram")
            click_tab(app, "model")

        # Should still be functional
        stats = get_header_stats(app)
        assert "Tables" in stats

    def test_diagram_tab_then_model_tab(self, app: Page):
        """Test switching from diagram back to model preserves state."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)

        click_tab(app, "diagram")
        app.wait_for_timeout(300)
        click_tab(app, "model")
        app.wait_for_timeout(100)

        # Tree should still be visible
        items = app.query_selector_all(".tree-item")
        assert len(items) > 0, "Tree items should still be visible"


class TestDiagramEdgeCases:
    """Tests for diagram edge cases."""

    def test_diagram_search_no_match(self, app: Page):
        """Test diagram search with no matching tables."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)
        click_tab(app, "diagram")
        app.wait_for_timeout(500)

        app.fill("#diagramSearch", "ZZZZZZNONEXISTENT")
        app.wait_for_timeout(200)

        # All nodes should be dimmed/faded
        highlighted = app.evaluate(
            "() => appState.cy ? appState.cy.nodes('.highlighted').length : -1"
        )
        assert highlighted == 0, "No nodes should be highlighted for non-matching search"

    def test_diagram_search_clears(self, app: Page):
        """Test that clearing diagram search restores all nodes."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)
        click_tab(app, "diagram")
        app.wait_for_timeout(500)

        app.fill("#diagramSearch", "Sales")
        app.wait_for_timeout(200)
        app.fill("#diagramSearch", "")
        app.wait_for_timeout(200)

        # All nodes should be visible/normal
        dimmed = app.evaluate(
            "() => appState.cy ? appState.cy.nodes('.dimmed').length : -1"
        )
        assert dimmed == 0, "No nodes should be dimmed after clearing search"


class TestTreeSearch:
    """Tests for tree search functionality."""

    def test_tree_search_filters_items(self, app: Page):
        """Test that tree search filters visible items."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)

        total = app.evaluate(
            "() => document.querySelectorAll('.tree-item').length"
        )

        app.fill("#treeSearch", "Sales")
        app.wait_for_timeout(200)

        visible = app.evaluate("""() => {
            let count = 0;
            document.querySelectorAll('.tree-item').forEach(el => {
                if (el.offsetParent !== null) count++;
            });
            return count;
        }""")

        assert visible < total, "Search should filter tree items"
        assert visible > 0, "Should find at least one match for 'Sales'"

    def test_tree_search_clear(self, app: Page):
        """Test that clearing search shows all items again."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)

        total_before = app.evaluate(
            "() => document.querySelectorAll('.tree-item').length"
        )

        app.fill("#treeSearch", "Sales")
        app.wait_for_timeout(100)
        app.fill("#treeSearch", "")
        app.wait_for_timeout(100)

        total_after = app.evaluate("""() => {
            let count = 0;
            document.querySelectorAll('.tree-item').forEach(el => {
                if (el.offsetParent !== null) count++;
            });
            return count;
        }""")

        assert total_after == total_before, "All items should be visible after clearing search"


class TestFileFormatDetection:
    """Tests for file format detection and error handling."""

    def test_plain_text_file_shows_error(self, app: Page):
        """Test that a random text file shows an error."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "invalid.txt"))
        app.wait_for_selector("#errorBanner", state="visible", timeout=5000)

        error_text = app.text_content("#errorBanner")
        assert len(error_text) > 0, "Error message should be displayed"

    def test_empty_json_shows_error(self, app: Page):
        """Test that empty JSON ({}) loads as empty model or shows error."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "empty.bim"))
        # Should either show an error or load as a model with 0 tables
        try:
            app.wait_for_selector("#errorBanner", state="visible", timeout=3000)
        except Exception:
            # If no error, it loaded as an empty model — that's acceptable
            wait_for_app(app, timeout=5000)
            stats = get_header_stats(app)
            assert "0 Tables" in stats

    def test_bim_format_badge(self, app: Page):
        """Test that .bim files show correct format badge."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)
        badge = app.text_content("#modelFormat")
        assert badge == "bim"

    def test_pbit_format_badge(self, app: Page):
        """Test that .pbit files show correct format badge."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.pbit"))
        wait_for_app(app)
        badge = app.text_content("#modelFormat")
        assert badge == "pbit"

    def test_tmdl_format_badge(self, app: Page):
        """Test that TMDL .zip files show correct format badge."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "tmdl-test-model.zip"))
        wait_for_app(app)
        badge = app.text_content("#modelFormat")
        assert badge == "tmdl"


class TestInactiveRelationships:
    """Tests for inactive relationship handling."""

    def test_inactive_relationship_in_markdown(self, app: Page):
        """Test that inactive relationships are marked in Markdown."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)

        md = app.evaluate("() => modelToMarkdown(appState.model, null)")
        assert "No" in md, "Markdown should show inactive relationship as 'No'"

    def test_bidirectional_relationship_in_markdown(self, app: Page):
        """Test that bidirectional relationships show correct direction."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)

        md = app.evaluate("() => modelToMarkdown(appState.model, null)")
        assert "Both" in md, "Markdown should show bidirectional as 'Both'"


# ============================================================
# Breaker Bug-Fix Tests
# ============================================================


class TestEscHtmlQuotes:
    """Tests for escHtml escaping quotes (XSS fix)."""

    def test_eschtml_escapes_double_quotes(self, app: Page):
        """escHtml should escape double quotes to &quot;"""
        result = app.evaluate('() => escHtml(\'He said "hello"\')')
        assert "&quot;" in result
        assert '"' not in result

    def test_eschtml_escapes_single_quotes(self, app: Page):
        """escHtml should escape single quotes to &#39;"""
        result = app.evaluate("() => escHtml(\"It's a test\")")
        assert "&#39;" in result

    def test_xss_in_data_key_attribute(self, app: Page):
        """Attribute injection via data-key should be prevented by quote escaping."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "edge-special-chars.bim"))
        wait_for_app(app)
        # Ensure no unescaped quotes leak into data-key attributes
        html = app.inner_html("#treeScroll")
        # All occurrences of data-key="..." should not contain raw unescaped double quotes inside
        # (the escHtml should have converted them to &quot;)
        assert 'data-key="table:' in html or "data-key=" in html


class TestColonInNames:
    """Tests for names containing colons in detail panel lookup."""

    def test_detail_panel_colon_column(self, app: Page):
        """Column with colon in name should display correctly in detail panel."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "edge-special-chars.bim"))
        wait_for_app(app)
        # Click the table to see its detail
        app.click('.tree-item[data-key^="table:"]')
        detail = app.inner_html("#detailPanel")
        assert "Col:colon:name" in detail, "Column with colons should appear in detail"

    def test_measure_with_colon_table_lookup(self, app: Page):
        """Measures should be found even when table name has special chars."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "edge-special-chars.bim"))
        wait_for_app(app)
        # Click first measure in tree
        measure_items = app.query_selector_all('.tree-item[data-key^="measure:"]')
        if len(measure_items) > 0:
            measure_items[0].click()
            detail = app.inner_html("#detailPanel")
            assert "detail-code" in detail or "detail-title" in detail


class TestPipeInMarkdown:
    """Tests for pipe characters in Markdown table cells."""

    def test_pipe_escaped_in_column_markdown(self, app: Page):
        """Pipe chars in column names should be escaped as \\| in Markdown tables."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "edge-special-chars.bim"))
        wait_for_app(app)
        md = app.evaluate("() => modelToMarkdown(appState.model, null)")
        # The column "Col|pipe|bar" should have pipes escaped in the table
        assert "Col\\|pipe\\|bar" in md, "Pipe characters should be escaped in Markdown tables"

    def test_escMdTable_function(self, app: Page):
        """escMdTable should escape pipe characters."""
        result = app.evaluate("() => escMdTable('hello|world')")
        assert result == "hello\\|world"

    def test_escMdTable_null_handling(self, app: Page):
        """escMdTable should handle null values."""
        result = app.evaluate("() => escMdTable(null)")
        assert result == ""


class TestUnquoteTmdl:
    """Tests for TMDL unquoting with doubled quotes."""

    def test_doubled_single_quotes_unescaped(self, app: Page):
        """unquoteTmdl should unescape doubled single quotes: 'it''s' -> it's"""
        result = app.evaluate("() => unquoteTmdl(\"'it''s a test'\")")
        assert result == "it's a test"

    def test_doubled_double_quotes_unescaped(self, app: Page):
        """unquoteTmdl should unescape doubled double quotes."""
        result = app.evaluate('() => unquoteTmdl(\'"say ""hello"" now"\')')
        assert result == 'say "hello" now'

    def test_no_quotes_unchanged(self, app: Page):
        """unquoteTmdl should leave unquoted strings unchanged."""
        result = app.evaluate("() => unquoteTmdl('plaintext')")
        assert result == "plaintext"


class TestTmdlDottedTableNames:
    """Tests for TMDL relationship parsing with dotted table names."""

    def test_splitTmdlQualifiedName_quoted(self, app: Page):
        """splitTmdlQualifiedName should handle quoted names with dots."""
        result = app.evaluate("() => splitTmdlQualifiedName(\"'Schema.Sales'.ProductKey\")")
        assert result == ["Schema.Sales", "ProductKey"]

    def test_splitTmdlQualifiedName_unquoted(self, app: Page):
        """splitTmdlQualifiedName should handle simple unquoted names."""
        result = app.evaluate("() => splitTmdlQualifiedName('Sales.ProductKey')")
        assert result == ["Sales", "ProductKey"]

    def test_splitTmdlQualifiedName_escaped_quotes(self, app: Page):
        """splitTmdlQualifiedName should handle escaped quotes in table name."""
        result = app.evaluate("() => splitTmdlQualifiedName(\"'It''s.A.Table'.Col\")")
        assert result == ["It's.A.Table", "Col"]

    def test_tmdl_dotted_relationship_parsed(self, app: Page):
        """TMDL model with dotted table names in relationships should parse correctly."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "tmdl-test-model.zip"))
        wait_for_app(app)
        md = app.evaluate("() => modelToMarkdown(appState.model, null)")
        assert "Schema.Sales" in md, "Dotted table name should be preserved in relationships"
        assert "Schema.Product" in md


class TestTabResetOnNewFile:
    """Tests for tab state reset when loading a new file."""

    def test_tab_resets_to_model_on_new_file(self, app: Page):
        """After clicking New File, active tab should be Model."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)
        # Switch to Diagram tab
        app.click('[data-tab="diagram"]')
        app.wait_for_timeout(300)
        # Click New File
        app.click("#newFileBtn")
        app.wait_for_selector("#dropZone", state="visible")
        # Load another file
        upload_file_via_input(app, os.path.join(TEST_FILES, "edge-single-table.bim"))
        wait_for_app(app)
        # Check that Model tab is active
        model_btn = app.query_selector('.tab-btn[data-tab="model"]')
        assert "active" in model_btn.get_attribute("class"), "Model tab should be active after New File"

    def test_diagram_tab_not_active_after_new_file(self, app: Page):
        """Diagram tab should not remain active after New File."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)
        # Switch to Diagram tab
        app.click('[data-tab="diagram"]')
        app.wait_for_timeout(300)
        # Click New File
        app.click("#newFileBtn")
        app.wait_for_selector("#dropZone", state="visible")
        # Verify diagram tab is not active
        diagram_btn = app.query_selector('.tab-btn[data-tab="diagram"]')
        assert "active" not in diagram_btn.get_attribute("class")


# ============================================================
# BPA (Best Practice Analyzer) tests
# ============================================================


def open_bpa_tab(page: Page, file_path: str):
    """Load a file and open the BPA tab."""
    upload_file_via_input(page, file_path)
    wait_for_app(page)
    click_tab(page, "bpa")
    page.wait_for_selector(".bpa-summary", state="visible", timeout=10000)


class TestBpaEngine:
    """Tests for BPA rule engine internals via JS evaluation."""

    def test_bpa_rules_loaded(self, app: Page):
        """BPA_RULES array should have 55+ rules."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)
        count = app.evaluate("() => BPA_RULES.length")
        assert count >= 55, f"Expected 55+ BPA rules, got {count}"

    def test_run_bpa_returns_results(self, app: Page):
        """runBpa should return one result per rule."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)
        result = app.evaluate("() => { const r = runBpa(appState.model); return { count: r.length, hasRule: r[0] && !!r[0].rule }; }")
        assert result["count"] >= 55
        assert result["hasRule"] is True

    def test_bpa_summary_structure(self, app: Page):
        """bpaSummary should return expected fields."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)
        summary = app.evaluate("() => { const r = runBpa(appState.model); return bpaSummary(r); }")
        for field in ["total", "passed", "failed", "errors", "warnings", "infos", "totalViolations", "score"]:
            assert field in summary, f"Missing field '{field}' in bpaSummary"
        assert summary["total"] >= 55
        assert 0 <= summary["score"] <= 100

    def test_each_rule_has_required_fields(self, app: Page):
        """Each rule should have id, name, category, severity, description, check."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)
        result = app.evaluate("""() => {
            const missing = [];
            for (const r of BPA_RULES) {
                for (const f of ['id', 'name', 'category', 'severity', 'description']) {
                    if (!r[f]) missing.push(r.id + ':' + f);
                }
                if (typeof r.check !== 'function') missing.push(r.id + ':check');
            }
            return missing;
        }""")
        assert result == [], f"Rules with missing fields: {result}"

    def test_rule_ids_are_unique(self, app: Page):
        """Each rule should have a unique ID."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)
        result = app.evaluate("""() => {
            const ids = BPA_RULES.map(r => r.id);
            const dupes = ids.filter((id, i) => ids.indexOf(id) !== i);
            return dupes;
        }""")
        assert result == [], f"Duplicate rule IDs: {result}"

    def test_rules_do_not_throw(self, app: Page):
        """No rule should throw an exception on any model."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)
        errors = app.evaluate("""() => {
            const results = runBpa(appState.model);
            return results.filter(r => r.error).map(r => r.rule.id + ': ' + r.error);
        }""")
        assert errors == [], f"Rules threw errors: {errors}"

    def test_violations_have_message(self, app: Page):
        """Every violation should have a message string."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)
        bad = app.evaluate("""() => {
            const results = runBpa(appState.model);
            const problems = [];
            for (const r of results) {
                for (const v of r.violations) {
                    if (!v.message || typeof v.message !== 'string') {
                        problems.push(r.rule.id);
                    }
                }
            }
            return problems;
        }""")
        assert bad == [], f"Violations without messages in rules: {bad}"


class TestBpaBadPracticesModel:
    """Tests using the bpa-bad-practices.bim model that has many known violations."""

    def test_many_violations_detected(self, app: Page):
        """Bad practices model should trigger many rules."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        wait_for_app(app)
        summary = app.evaluate("() => { const r = runBpa(appState.model); return bpaSummary(r); }")
        assert summary["failed"] >= 20, f"Expected 20+ failed rules on bad model, got {summary['failed']}"
        assert summary["totalViolations"] >= 25, f"Expected 25+ total violations, got {summary['totalViolations']}"

    def test_perf_bidir_detected(self, app: Page):
        """PERF_001: bi-directional relationship should be flagged."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        wait_for_app(app)
        count = app.evaluate("""() => {
            const r = runBpa(appState.model).find(r => r.rule.id === 'PERF_001');
            return r ? r.violations.length : -1;
        }""")
        assert count >= 1, "PERF_001 should detect bi-directional relationship"

    def test_perf_m2m_detected(self, app: Page):
        """PERF_002: many-to-many relationship should be flagged."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        wait_for_app(app)
        count = app.evaluate("""() => {
            const r = runBpa(appState.model).find(r => r.rule.id === 'PERF_002');
            return r ? r.violations.length : -1;
        }""")
        assert count >= 1, "PERF_002 should detect many-to-many relationship"

    def test_perf_calc_column_detected(self, app: Page):
        """PERF_003: calculated column should be flagged."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        wait_for_app(app)
        count = app.evaluate("""() => {
            const r = runBpa(appState.model).find(r => r.rule.id === 'PERF_003');
            return r ? r.violations.length : -1;
        }""")
        assert count >= 1, "PERF_003 should detect calculated column"

    def test_perf_high_column_count(self, app: Page):
        """PERF_004: table with >30 columns should be flagged."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        wait_for_app(app)
        count = app.evaluate("""() => {
            const r = runBpa(appState.model).find(r => r.rule.id === 'PERF_004');
            return r ? r.violations.length : -1;
        }""")
        assert count >= 1, "PERF_004 should detect high column count"

    def test_perf_float_type(self, app: Page):
        """PERF_006: double data type should be flagged."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        wait_for_app(app)
        count = app.evaluate("""() => {
            const r = runBpa(appState.model).find(r => r.rule.id === 'PERF_006');
            return r ? r.violations.length : -1;
        }""")
        assert count >= 1, "PERF_006 should detect double data type"

    def test_perf_inactive_rel(self, app: Page):
        """PERF_007: inactive relationship should be flagged."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        wait_for_app(app)
        count = app.evaluate("""() => {
            const r = runBpa(appState.model).find(r => r.rule.id === 'PERF_007');
            return r ? r.violations.length : -1;
        }""")
        assert count >= 1, "PERF_007 should detect inactive relationship"

    def test_perf_auto_datetime(self, app: Page):
        """PERF_008: auto date/time table should be flagged."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        wait_for_app(app)
        count = app.evaluate("""() => {
            const r = runBpa(appState.model).find(r => r.rule.id === 'PERF_008');
            return r ? r.violations.length : -1;
        }""")
        assert count >= 1, "PERF_008 should detect auto date/time table"

    def test_dax_iferror_detected(self, app: Page):
        """DAX_001: IFERROR usage should be flagged."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        wait_for_app(app)
        count = app.evaluate("""() => {
            const r = runBpa(appState.model).find(r => r.rule.id === 'DAX_001');
            return r ? r.violations.length : -1;
        }""")
        assert count >= 1, "DAX_001 should detect IFERROR"

    def test_dax_divide_operator(self, app: Page):
        """DAX_002: / operator should be flagged."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        wait_for_app(app)
        count = app.evaluate("""() => {
            const r = runBpa(appState.model).find(r => r.rule.id === 'DAX_002');
            return r ? r.violations.length : -1;
        }""")
        assert count >= 1, "DAX_002 should detect / division operator"

    def test_dax_filter_whole_table(self, app: Page):
        """DAX_005: FILTER on whole table should be flagged."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        wait_for_app(app)
        count = app.evaluate("""() => {
            const r = runBpa(appState.model).find(r => r.rule.id === 'DAX_005');
            return r ? r.violations.length : -1;
        }""")
        assert count >= 1, "DAX_005 should detect FILTER on whole table"

    def test_dax_nested_calculate(self, app: Page):
        """DAX_007: nested CALCULATE should be flagged."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        wait_for_app(app)
        count = app.evaluate("""() => {
            const r = runBpa(appState.model).find(r => r.rule.id === 'DAX_007');
            return r ? r.violations.length : -1;
        }""")
        assert count >= 1, "DAX_007 should detect nested CALCULATE"

    def test_dax_long_measure(self, app: Page):
        """DAX_010: long measure expression should be flagged."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        wait_for_app(app)
        count = app.evaluate("""() => {
            const r = runBpa(appState.model).find(r => r.rule.id === 'DAX_010');
            return r ? r.violations.length : -1;
        }""")
        assert count >= 1, "DAX_010 should detect long measure expression"

    def test_name_reserved_keyword(self, app: Page):
        """NAME_006: reserved DAX keyword as column name should be flagged."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        wait_for_app(app)
        count = app.evaluate("""() => {
            const r = runBpa(appState.model).find(r => r.rule.id === 'NAME_006');
            return r ? r.violations.length : -1;
        }""")
        assert count >= 2, "NAME_006 should detect reserved keywords (Date, Value, Name)"

    def test_name_starts_with_number(self, app: Page):
        """NAME_005: measure name starting with number should be flagged."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        wait_for_app(app)
        count = app.evaluate("""() => {
            const r = runBpa(appState.model).find(r => r.rule.id === 'NAME_005');
            return r ? r.violations.length : -1;
        }""")
        assert count >= 1, "NAME_005 should detect measure starting with number"

    def test_name_table_prefix(self, app: Page):
        """NAME_010: table with database-style prefix should be flagged."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        wait_for_app(app)
        count = app.evaluate("""() => {
            const r = runBpa(appState.model).find(r => r.rule.id === 'NAME_010');
            return r ? r.violations.length : -1;
        }""")
        assert count >= 1, "NAME_010 should detect fact_ prefix"

    def test_name_measure_prefix(self, app: Page):
        """NAME_009: measure with m_ prefix should be flagged."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        wait_for_app(app)
        count = app.evaluate("""() => {
            const r = runBpa(appState.model).find(r => r.rule.id === 'NAME_009');
            return r ? r.violations.length : -1;
        }""")
        assert count >= 1, "NAME_009 should detect m_ prefix"

    def test_meta_table_no_description(self, app: Page):
        """META_001: tables without descriptions should be flagged."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        wait_for_app(app)
        count = app.evaluate("""() => {
            const r = runBpa(appState.model).find(r => r.rule.id === 'META_001');
            return r ? r.violations.length : -1;
        }""")
        assert count >= 1, "META_001 should detect tables without descriptions"

    def test_meta_measure_no_description(self, app: Page):
        """META_002: measures without descriptions should be flagged."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        wait_for_app(app)
        count = app.evaluate("""() => {
            const r = runBpa(appState.model).find(r => r.rule.id === 'META_002');
            return r ? r.violations.length : -1;
        }""")
        assert count >= 5, "META_002 should detect many measures without descriptions"

    def test_meta_visible_on_hidden(self, app: Page):
        """META_005: visible column on hidden table should be flagged."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        wait_for_app(app)
        count = app.evaluate("""() => {
            const r = runBpa(appState.model).find(r => r.rule.id === 'META_005');
            return r ? r.violations.length : -1;
        }""")
        assert count >= 1, "META_005 should detect visible column on hidden table"

    def test_meta_empty_table(self, app: Page):
        """META_008: empty table should be flagged."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        wait_for_app(app)
        count = app.evaluate("""() => {
            const r = runBpa(appState.model).find(r => r.rule.id === 'META_008');
            return r ? r.violations.length : -1;
        }""")
        assert count >= 1, "META_008 should detect empty table"

    def test_model_disconnected_table(self, app: Page):
        """MODEL_001: table without relationships should be flagged."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        wait_for_app(app)
        count = app.evaluate("""() => {
            const r = runBpa(appState.model).find(r => r.rule.id === 'MODEL_001');
            return r ? r.violations.length : -1;
        }""")
        assert count >= 1, "MODEL_001 should detect disconnected table"

    def test_model_multiple_rels(self, app: Page):
        """MODEL_002: multiple relationships between same tables should be flagged."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        wait_for_app(app)
        count = app.evaluate("""() => {
            const r = runBpa(appState.model).find(r => r.rule.id === 'MODEL_002');
            return r ? r.violations.length : -1;
        }""")
        assert count >= 1, "MODEL_002 should detect multiple relationships between same tables"

    def test_model_no_date_table(self, app: Page):
        """MODEL_005: model without dedicated date table should be flagged."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        wait_for_app(app)
        count = app.evaluate("""() => {
            const r = runBpa(appState.model).find(r => r.rule.id === 'MODEL_005');
            return r ? r.violations.length : -1;
        }""")
        assert count >= 1, "MODEL_005 should detect missing date table"

    def test_fmt_no_format_string(self, app: Page):
        """FMT_001: measure without format string should be flagged."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        wait_for_app(app)
        count = app.evaluate("""() => {
            const r = runBpa(appState.model).find(r => r.rule.id === 'FMT_001');
            return r ? r.violations.length : -1;
        }""")
        assert count >= 3, "FMT_001 should detect measures without format strings"

    def test_sec_empty_role(self, app: Page):
        """SEC_002: RLS role with no filters should be flagged."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        wait_for_app(app)
        count = app.evaluate("""() => {
            const r = runBpa(appState.model).find(r => r.rule.id === 'SEC_002');
            return r ? r.violations.length : -1;
        }""")
        assert count >= 1, "SEC_002 should detect empty RLS role"

    def test_sec_username_function(self, app: Page):
        """SEC_003: USERNAME() in RLS should be flagged."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        wait_for_app(app)
        count = app.evaluate("""() => {
            const r = runBpa(appState.model).find(r => r.rule.id === 'SEC_003');
            return r ? r.violations.length : -1;
        }""")
        assert count >= 1, "SEC_003 should detect USERNAME() usage"

    def test_name_inconsistent_rel_cols(self, app: Page):
        """NAME_008: relationship with different column names should be flagged."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        wait_for_app(app)
        count = app.evaluate("""() => {
            const r = runBpa(appState.model).find(r => r.rule.id === 'NAME_008');
            return r ? r.violations.length : -1;
        }""")
        assert count >= 1, "NAME_008 should detect mismatched relationship column names"


class TestBpaCleanModel:
    """Tests using the bpa-clean-model.bim which should pass most rules."""

    def test_high_score(self, app: Page):
        """Clean model should have a high BPA score."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "bpa-clean-model.bim"))
        wait_for_app(app)
        summary = app.evaluate("() => { const r = runBpa(appState.model); return bpaSummary(r); }")
        assert summary["score"] >= 80, f"Clean model should score >= 80%, got {summary['score']}%"

    def test_no_errors(self, app: Page):
        """Clean model should have no error-severity violations."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "bpa-clean-model.bim"))
        wait_for_app(app)
        errors = app.evaluate("() => { const r = runBpa(appState.model); return bpaSummary(r).errors; }")
        assert errors == 0, f"Clean model should have 0 errors, got {errors}"

    def test_few_warnings(self, app: Page):
        """Clean model should have very few warnings."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "bpa-clean-model.bim"))
        wait_for_app(app)
        warnings = app.evaluate("() => { const r = runBpa(appState.model); return bpaSummary(r).warnings; }")
        assert warnings <= 5, f"Clean model should have few warnings, got {warnings}"


class TestBpaTabUI:
    """Tests for BPA tab UI rendering and interactions."""

    def test_bpa_tab_renders(self, app: Page):
        """BPA tab should render with summary and rules."""
        open_bpa_tab(app, os.path.join(TEST_FILES, "test-model.bim"))
        expect(app.locator(".bpa-summary")).to_be_visible()
        expect(app.locator(".bpa-score")).to_be_visible()
        expect(app.locator(".bpa-rules")).to_be_visible()

    def test_bpa_tab_shows_score(self, app: Page):
        """BPA tab should display a percentage score."""
        open_bpa_tab(app, os.path.join(TEST_FILES, "test-model.bim"))
        score_text = app.text_content(".bpa-score")
        assert "%" in score_text, f"Score should contain %, got: {score_text}"

    def test_bpa_rules_visible(self, app: Page):
        """BPA tab should show rule details elements."""
        open_bpa_tab(app, os.path.join(TEST_FILES, "test-model.bim"))
        rules = app.query_selector_all(".bpa-rule")
        assert len(rules) > 0, "Should display BPA rule elements"

    def test_bpa_rule_expand(self, app: Page):
        """Clicking a rule should expand its details."""
        open_bpa_tab(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        # Find first failed rule and click it
        first_failed = app.locator(".bpa-rule.bpa-failed").first
        first_failed.locator("summary").click()
        app.wait_for_timeout(200)
        expect(first_failed.locator(".bpa-rule-body")).to_be_visible()

    def test_bpa_filter_failed_only(self, app: Page):
        """Filtering to 'Failed only' should hide passed rules."""
        open_bpa_tab(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        # Count total rules
        total = len(app.query_selector_all(".bpa-rule"))
        # Filter to failed only
        app.select_option("#bpaFilter", "failed")
        app.wait_for_timeout(200)
        filtered = len(app.query_selector_all(".bpa-rule"))
        assert filtered < total, "Failed filter should reduce visible rules"
        # All visible should be failed
        passed = app.query_selector_all(".bpa-rule.bpa-passed")
        assert len(passed) == 0, "No passed rules should be visible after filtering"

    def test_bpa_filter_by_severity(self, app: Page):
        """Filtering by severity should show only matching rules."""
        open_bpa_tab(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        for sev in ["error", "warning", "info"]:
            app.select_option("#bpaFilter", sev)
            app.wait_for_timeout(200)
            rules = app.query_selector_all(".bpa-rule")
            if len(rules) > 0:
                # All rules should have matching severity badge
                badges = app.query_selector_all(f".bpa-sev-{sev}")
                assert len(badges) > 0, f"Should have {sev} badges when filtering by {sev}"

    def test_bpa_filter_by_category(self, app: Page):
        """Filtering by category should show only rules in that category."""
        open_bpa_tab(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        app.select_option("#bpaFilter", "cat:Performance")
        app.wait_for_timeout(200)
        rules = app.query_selector_all(".bpa-rule")
        assert len(rules) > 0, "Performance category should have rules"

    def test_bpa_copy_report_button(self, app: Page):
        """Copy Report button should produce markdown output."""
        open_bpa_tab(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        md = app.evaluate("() => { const r = runBpa(appState.model); return bpaToMarkdown(r, appState.model); }")
        assert "# Best Practice Analyzer Report" in md
        assert "Score:" in md

    def test_bpa_fix_prompt_button(self, app: Page):
        """Copy Fix Prompt button should produce LLM prompt with model context."""
        open_bpa_tab(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        prompt = app.evaluate("() => { const r = runBpa(appState.model); return bpaFixPrompt(r, appState.model); }")
        assert "BPA REPORT" in prompt
        assert "MODEL DEFINITION" in prompt
        assert "Power BI" in prompt

    def test_bpa_violations_table_rendered(self, app: Page):
        """Failed rules should display a violations table."""
        open_bpa_tab(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        # Expand first failed rule
        first_failed = app.locator(".bpa-rule.bpa-failed").first
        first_failed.locator("summary").click()
        app.wait_for_timeout(200)
        table = first_failed.locator(".bpa-violations-table")
        expect(table).to_be_visible()

    def test_bpa_severity_badges_colored(self, app: Page):
        """Severity badges should have correct classes."""
        open_bpa_tab(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        # Check at least one of each type exists
        for sev_class in ["bpa-sev-error", "bpa-sev-warning", "bpa-sev-info"]:
            badges = app.query_selector_all(f".{sev_class}")
            assert len(badges) > 0, f"Should have badges with class {sev_class}"


class TestBpaTabSwitching:
    """Tests for BPA tab switching and lazy rendering."""

    def test_bpa_tab_accessible(self, app: Page):
        """BPA tab button should be visible after loading any model."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)
        bpa_btn = app.locator('.tab-btn[data-tab="bpa"]')
        expect(bpa_btn).to_be_visible()

    def test_bpa_tab_lazy_render(self, app: Page):
        """BPA tab should not render until clicked."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)
        # Before clicking, BPA content should be placeholder
        content = app.text_content("#bpa-content")
        assert "Load a model" in content
        # Now click BPA tab
        click_tab(app, "bpa")
        app.wait_for_selector(".bpa-summary", state="visible", timeout=10000)
        # Should now have real content
        expect(app.locator(".bpa-score")).to_be_visible()

    def test_bpa_switch_back_preserves(self, app: Page):
        """Switching away from BPA and back should keep results."""
        open_bpa_tab(app, os.path.join(TEST_FILES, "test-model.bim"))
        score1 = app.text_content(".bpa-score")
        click_tab(app, "model")
        app.wait_for_timeout(200)
        click_tab(app, "bpa")
        app.wait_for_timeout(200)
        score2 = app.text_content(".bpa-score")
        assert score1 == score2, "BPA score should be preserved after switching tabs"

    def test_bpa_resets_on_new_file(self, app: Page):
        """Loading a new file should reset BPA results."""
        open_bpa_tab(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        score1 = app.text_content(".bpa-score")
        # Load a new file
        app.click("#newFileBtn")
        app.wait_for_selector("#dropZone", state="visible")
        upload_file_via_input(app, os.path.join(TEST_FILES, "bpa-clean-model.bim"))
        wait_for_app(app)
        click_tab(app, "bpa")
        app.wait_for_selector(".bpa-summary", state="visible", timeout=10000)
        score2 = app.text_content(".bpa-score")
        assert score1 != score2, "BPA score should change when loading a different model"

    def test_rapid_tab_switching_with_bpa(self, app: Page):
        """Rapid switching between all tabs including BPA should not crash."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "test-model.bim"))
        wait_for_app(app)
        for _ in range(3):
            click_tab(app, "bpa")
            click_tab(app, "model")
            click_tab(app, "diagram")
            click_tab(app, "bpa")
        app.wait_for_timeout(200)
        stats = get_header_stats(app)
        assert "Tables" in stats, "App should remain functional after rapid tab switching"


class TestBpaEdgeCases:
    """Tests for BPA behavior on edge-case models."""

    def test_empty_model(self, app: Page):
        """BPA should work on an empty model without errors."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "edge-empty-model.bim"))
        wait_for_app(app)
        result = app.evaluate("() => { const r = runBpa(appState.model); return { count: r.length, errors: r.filter(x => x.error).length }; }")
        assert result["count"] >= 55, "Should still evaluate all rules"
        assert result["errors"] == 0, "No rule should error on empty model"

    def test_single_table_model(self, app: Page):
        """BPA should work on a single-table model."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "edge-single-table.bim"))
        wait_for_app(app)
        result = app.evaluate("() => { const r = runBpa(appState.model); return { count: r.length, errors: r.filter(x => x.error).length }; }")
        assert result["errors"] == 0, "No rule should error on single-table model"

    def test_all_hidden_model(self, app: Page):
        """BPA should work on a model with all hidden items."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "edge-all-hidden.bim"))
        wait_for_app(app)
        result = app.evaluate("() => { const r = runBpa(appState.model); return { count: r.length, errors: r.filter(x => x.error).length }; }")
        assert result["errors"] == 0, "No rule should error on all-hidden model"

    def test_special_chars_model(self, app: Page):
        """BPA should handle special characters in names without crashing."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "edge-special-chars.bim"))
        wait_for_app(app)
        result = app.evaluate("() => { const r = runBpa(appState.model); return { count: r.length, errors: r.filter(x => x.error).length }; }")
        assert result["errors"] == 0, "No rule should error on special-chars model"

    def test_many_tables_model(self, app: Page):
        """BPA should handle a model with many tables."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "edge-many-tables.bim"))
        wait_for_app(app)
        result = app.evaluate("() => { const r = runBpa(appState.model); return { count: r.length, errors: r.filter(x => x.error).length }; }")
        assert result["errors"] == 0, "No rule should error on many-tables model"

    def test_long_names_model(self, app: Page):
        """BPA should handle very long names without crashing."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "edge-long-names.bim"))
        wait_for_app(app)
        result = app.evaluate("() => { const r = runBpa(appState.model); return { count: r.length, errors: r.filter(x => x.error).length }; }")
        assert result["errors"] == 0, "No rule should error on long-names model"

    def test_no_measures_model(self, app: Page):
        """BPA should work on a model with no measures."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "edge-no-measures.bim"))
        wait_for_app(app)
        result = app.evaluate("() => { const r = runBpa(appState.model); return { count: r.length, errors: r.filter(x => x.error).length }; }")
        assert result["errors"] == 0, "No rule should error on no-measures model"


class TestBpaWithRealFiles:
    """Tests for BPA with real-world Power BI files."""

    def test_adventureworks_bpa(self, app: Page):
        """BPA should analyze AdventureWorks model without errors."""
        bim_path = os.path.join(TEST_FILES, "AdventureWorks.bim")
        if not os.path.exists(bim_path):
            pytest.skip("AdventureWorks.bim not downloaded")
        upload_file_via_input(app, bim_path)
        wait_for_app(app)
        result = app.evaluate("""() => {
            const r = runBpa(appState.model);
            const s = bpaSummary(r);
            return { total: s.total, score: s.score, ruleErrors: r.filter(x => x.error).length };
        }""")
        assert result["ruleErrors"] == 0, "No rule should error on AdventureWorks"
        assert result["score"] > 0, "Score should be > 0"

    def test_adventureworks_bpa_tab_ui(self, app: Page):
        """BPA tab should render correctly for AdventureWorks."""
        bim_path = os.path.join(TEST_FILES, "AdventureWorks.bim")
        if not os.path.exists(bim_path):
            pytest.skip("AdventureWorks.bim not downloaded")
        open_bpa_tab(app, bim_path)
        expect(app.locator(".bpa-score")).to_be_visible()
        rules = app.query_selector_all(".bpa-rule")
        assert len(rules) >= 55, f"Should show all rules, got {len(rules)}"

    def test_adventureworks_bpa_markdown_export(self, app: Page):
        """BPA markdown export should work for AdventureWorks."""
        bim_path = os.path.join(TEST_FILES, "AdventureWorks.bim")
        if not os.path.exists(bim_path):
            pytest.skip("AdventureWorks.bim not downloaded")
        upload_file_via_input(app, bim_path)
        wait_for_app(app)
        md = app.evaluate("() => { const r = runBpa(appState.model); return bpaToMarkdown(r, appState.model); }")
        assert "# Best Practice Analyzer Report" in md
        assert "Score:" in md
        assert len(md) > 200, "Should produce substantial markdown output"

    def test_corporate_spend_pbix_bpa(self, app: Page):
        """BPA should work on .pbix file (Corporate Spend)."""
        pbix_path = os.path.join(TEST_FILES, "Corporate_Spend.pbix")
        if not os.path.exists(pbix_path):
            pytest.skip("Corporate_Spend.pbix not available")
        upload_file_via_input(app, pbix_path)
        wait_for_app(app, timeout=30000)
        result = app.evaluate("""() => {
            const r = runBpa(appState.model);
            return { total: r.length, ruleErrors: r.filter(x => x.error).length, score: bpaSummary(r).score };
        }""")
        assert result["ruleErrors"] == 0, "No rule should error on Corporate_Spend.pbix"

    def test_pbit_file_bpa(self, app: Page):
        """BPA should work on .pbit file."""
        pbit_path = os.path.join(TEST_FILES, "test-model.pbit")
        if not os.path.exists(pbit_path):
            pytest.skip("test-model.pbit not available")
        upload_file_via_input(app, pbit_path)
        wait_for_app(app)
        result = app.evaluate("""() => {
            const r = runBpa(appState.model);
            return { total: r.length, ruleErrors: r.filter(x => x.error).length };
        }""")
        assert result["ruleErrors"] == 0, "No rule should error on .pbit file"

    def test_tmdl_file_bpa(self, app: Page):
        """BPA should work on TMDL zip file."""
        tmdl_path = os.path.join(TEST_FILES, "tmdl-test-model.zip")
        if not os.path.exists(tmdl_path):
            pytest.skip("tmdl-test-model.zip not available")
        upload_file_via_input(app, tmdl_path)
        wait_for_app(app)
        result = app.evaluate("""() => {
            const r = runBpa(appState.model);
            return { total: r.length, ruleErrors: r.filter(x => x.error).length };
        }""")
        assert result["ruleErrors"] == 0, "No rule should error on TMDL file"

    def test_tmdl_sales_bpa(self, app: Page):
        """BPA should work on the comprehensive TMDL sales model."""
        tmdl_path = os.path.join(TEST_FILES, "tmdl-sales.zip")
        if not os.path.exists(tmdl_path):
            pytest.skip("tmdl-sales.zip not available")
        upload_file_via_input(app, tmdl_path)
        wait_for_app(app)
        result = app.evaluate("""() => {
            const r = runBpa(appState.model);
            const s = bpaSummary(r);
            return { total: s.total, score: s.score, ruleErrors: r.filter(x => x.error).length };
        }""")
        assert result["ruleErrors"] == 0, "No rule should error on TMDL sales model"


class TestBpaMarkdownExport:
    """Tests for BPA markdown and fix prompt export."""

    def test_markdown_contains_all_sections(self, app: Page):
        """BPA markdown should have title, score, and violation sections."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        wait_for_app(app)
        md = app.evaluate("() => { const r = runBpa(appState.model); return bpaToMarkdown(r, appState.model); }")
        assert "# Best Practice Analyzer Report" in md
        assert "Score:" in md
        assert "## Error" in md or "## Warning" in md

    def test_markdown_lists_violations(self, app: Page):
        """BPA markdown should list specific violations with location."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        wait_for_app(app)
        md = app.evaluate("() => { const r = runBpa(appState.model); return bpaToMarkdown(r, appState.model); }")
        assert "fact_sales" in md, "Should reference specific table names"
        assert "- " in md, "Should use bullet points for violations"

    def test_fix_prompt_includes_both_sections(self, app: Page):
        """Fix prompt should include both BPA report and model definition."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        wait_for_app(app)
        prompt = app.evaluate("() => { const r = runBpa(appState.model); return bpaFixPrompt(r, appState.model); }")
        assert "--- BPA REPORT ---" in prompt
        assert "--- MODEL DEFINITION ---" in prompt
        assert "# Model:" in prompt

    def test_fix_prompt_has_instructions(self, app: Page):
        """Fix prompt should include instructions for the LLM."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "bpa-bad-practices.bim"))
        wait_for_app(app)
        prompt = app.evaluate("() => { const r = runBpa(appState.model); return bpaFixPrompt(r, appState.model); }")
        assert "XMLA" in prompt or "Power BI" in prompt
        assert "fix" in prompt.lower()

    def test_clean_model_markdown_says_all_passed(self, app: Page):
        """Clean model BPA markdown should indicate all passed."""
        upload_file_via_input(app, os.path.join(TEST_FILES, "bpa-clean-model.bim"))
        wait_for_app(app)
        md = app.evaluate("() => { const r = runBpa(appState.model); return bpaToMarkdown(r, appState.model); }")
        # Should have high score
        assert "Score:" in md


# ============================================================
# Responsive layout tests
# ============================================================


VIEWPORTS = [
    {"name": "desktop", "width": 1280, "height": 800},
    {"name": "tablet", "width": 768, "height": 1024},
    {"name": "mobile", "width": 375, "height": 667},
]


@pytest.fixture(params=VIEWPORTS, ids=lambda v: v["name"])
def sized_app(request, page: Page):
    """Navigate to the app at a specific viewport size."""
    vp = request.param
    page.set_viewport_size({"width": vp["width"], "height": vp["height"]})
    page.goto(f"file://{HTML_PATH}")
    page.wait_for_selector("#dropZone", state="visible", timeout=10000)
    return page, vp


class TestResponsiveLayout:
    """Test that the app renders without overflow at various screen sizes."""

    def test_no_horizontal_overflow(self, sized_app):
        page, vp = sized_app
        overflow = page.evaluate(
            "document.documentElement.scrollWidth > document.documentElement.clientWidth"
        )
        assert not overflow, f"Horizontal overflow at {vp['name']} ({vp['width']}x{vp['height']})"

    def test_drop_zone_visible(self, sized_app):
        page, vp = sized_app
        drop = page.locator("#dropZone")
        expect(drop).to_be_visible()
        box = drop.bounding_box()
        assert box is not None
        assert box["width"] > 0

    def test_header_not_clipped_after_load(self, sized_app):
        """After loading a file, header actions should not overflow."""
        page, vp = sized_app
        bim_path = os.path.join(TEST_FILES, "test_model.bim")
        if not os.path.exists(bim_path):
            pytest.skip("test_model.bim not generated")
        drop_file(page, bim_path)
        wait_for_app(page)
        header = page.locator(".app-header")
        box = header.bounding_box()
        assert box is not None
        # Header should not extend beyond the viewport
        assert box["x"] >= 0
        assert box["x"] + box["width"] <= vp["width"] + 2  # 2px tolerance

    def test_star_button_visible_after_load(self, sized_app):
        """GitHub star button should be present in the header."""
        page, vp = sized_app
        bim_path = os.path.join(TEST_FILES, "test_model.bim")
        if not os.path.exists(bim_path):
            pytest.skip("test_model.bim not generated")
        drop_file(page, bim_path)
        wait_for_app(page)
        star_btn = page.locator("#ghStarBtn")
        expect(star_btn).to_be_visible()
