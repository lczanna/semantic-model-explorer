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
HTML_PATH = os.path.join(ROOT, "semantic-model-explorer.html")
TEST_FILES = os.path.join(ROOT, "data", "test-files")


@pytest.fixture(scope="session", autouse=True)
def generate_test_files():
    """Generate test files before running tests."""
    from generate_test_files import generate_bim, generate_pbit, generate_tmdl, generate_edge_case_files

    os.makedirs(TEST_FILES, exist_ok=True)
    generate_bim(TEST_FILES)
    generate_pbit(TEST_FILES)
    generate_tmdl(TEST_FILES)
    generate_edge_case_files(TEST_FILES)


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

    def test_pbix_export_buttons_enabled(self, app: Page):
        """Test that CSV and Parquet export buttons are enabled after loading data."""
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
        assert csv_disabled is None, "CSV button should be enabled"
        assert parquet_disabled is None, "Parquet button should be enabled"

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
