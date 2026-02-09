#!/usr/bin/env python3
"""Quick test for VertiPaq data extraction from .pbix files."""

import os
import sys

# Add project root for imports
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from playwright.sync_api import sync_playwright

HTML_PATH = os.path.join(ROOT, 'semantic-model-explorer.html')
PBIX_PATH = os.path.join(ROOT, 'data', 'test-files', 'Revenue_Opportunities.pbix')

BROWSER_ARGS = [
    "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage", "--single-process",
]


def test_pbix_load():
    """Test that a .pbix file with DataModel loads correctly."""
    with sync_playwright() as p:
        browser = p.chromium.launch(args=BROWSER_ARGS)
        page = browser.new_page()

        errors = []
        page.on('console', lambda msg: print(f'  CONSOLE [{msg.type}]: {msg.text}'))
        page.on('pageerror', lambda err: errors.append(str(err)))

        page.goto(f'file://{HTML_PATH}')
        page.wait_for_load_state('domcontentloaded')

        # Upload the .pbix file
        page.set_input_files('#fileInput', PBIX_PATH)

        # Wait for the app to render (may take time for XPress9 decompression)
        try:
            page.wait_for_selector('.app-wrap', state='visible', timeout=30000)
        except Exception as e:
            # Check for errors
            if errors:
                print(f'Page errors: {errors}')
            # Check error banner
            err_banner = page.query_selector('#errorBanner')
            if err_banner:
                err_text = page.text_content('#errorBanner')
                print(f'Error banner: {err_text}')
            raise

        # Check model loaded
        format_badge = page.text_content('#modelFormat')
        print(f'Format badge: {format_badge}')
        assert 'pbix' in format_badge.lower(), f'Expected pbix format, got: {format_badge}'

        stats = page.text_content('#modelStats')
        print(f'Model stats: {stats}')
        assert 'Tables' in stats, f'Expected tables in stats: {stats}'

        # Check Data tab is visible
        data_tab_btn = page.query_selector('#dataTabBtn')
        assert data_tab_btn is not None, 'Data tab button not found'
        display = page.evaluate('document.getElementById("dataTabBtn").style.display')
        print(f'Data tab display: "{display}"')
        assert display != 'none', 'Data tab should be visible for .pbix'

        # Click Data tab
        data_tab_btn.click()
        page.wait_for_selector('#dataTableList .data-table-item', timeout=5000)

        # Get table list
        table_items = page.query_selector_all('#dataTableList .data-table-item')
        table_names = [item.text_content() for item in table_items]
        print(f'Tables found: {table_names}')
        assert len(table_names) > 0, 'No tables found in Data tab'

        # Click on first table
        table_items[0].click()

        # Wait for data preview to load
        page.wait_for_selector('.data-table th', timeout=30000)

        # Check we got actual data
        headers = page.query_selector_all('.data-table th')
        header_names = [h.text_content() for h in headers]
        print(f'Columns: {header_names}')
        assert len(header_names) > 0, 'No columns in data preview'

        rows = page.query_selector_all('.data-table tbody tr')
        print(f'Preview rows: {len(rows)}')
        assert len(rows) > 0, 'No data rows in preview'

        # Check row count display
        row_count = page.text_content('#dataRowCount')
        print(f'Row count: {row_count}')

        # Check export buttons are enabled
        csv_disabled = page.get_attribute('#exportCsvBtn', 'disabled')
        parquet_disabled = page.get_attribute('#exportParquetBtn', 'disabled')
        print(f'CSV btn disabled: {csv_disabled}, Parquet btn disabled: {parquet_disabled}')

        print('\n=== ALL CHECKS PASSED ===')

        browser.close()


if __name__ == '__main__':
    test_pbix_load()
