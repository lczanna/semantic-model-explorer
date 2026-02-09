"""Take screenshots of Semantic Model Explorer for README documentation."""

import os
import time
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML_PATH = os.path.join(ROOT, "semantic-model-explorer.html")
TEST_FILES = os.path.join(ROOT, "data", "test-files")
SCREENSHOTS = os.path.join(ROOT, "docs", "screenshots")

os.makedirs(SCREENSHOTS, exist_ok=True)


def take_screenshots():
    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage", "--single-process"],
    )

    # Use a larger viewport for nice screenshots
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()

    # ── 1. Drop Zone / Landing Page ──
    page.goto(f"file://{HTML_PATH}", wait_until="load")
    time.sleep(1)
    page.screenshot(path=os.path.join(SCREENSHOTS, "01-drop-zone.png"))
    print("1/6 Drop zone screenshot taken")
    ctx.close()
    browser.close()

    # ── 2. Model Tab with AdventureWorks ──
    browser = pw.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage", "--single-process"],
    )
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.goto(f"file://{HTML_PATH}", wait_until="load")
    time.sleep(1)
    page.set_input_files("#fileInput", os.path.join(TEST_FILES, "AdventureWorks.bim"))
    page.wait_for_selector("#appWrap", state="visible", timeout=15000)
    time.sleep(0.5)

    # Expand some sections and click a measure to show detail panel
    # Click "Select All" to show token count
    page.check("#selectAll")
    time.sleep(0.3)

    page.screenshot(path=os.path.join(SCREENSHOTS, "02-model-tab-overview.png"))
    print("2/6 Model tab overview screenshot taken")

    # ── 3. Detail panel showing a measure with DAX ──
    # Find and click a measure item in the tree
    page.evaluate("""() => {
        const items = document.querySelectorAll('.tree-item');
        for (const item of items) {
            if (item.dataset.key && item.dataset.key.includes('.measure.')) {
                item.click();
                return true;
            }
        }
        return false;
    }""")
    time.sleep(0.5)
    page.screenshot(path=os.path.join(SCREENSHOTS, "03-measure-detail.png"))
    print("3/6 Measure detail screenshot taken")
    ctx.close()
    browser.close()

    # ── 4. Diagram tab with AdventureWorks ──
    browser = pw.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage", "--single-process"],
    )
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.goto(f"file://{HTML_PATH}", wait_until="load")
    time.sleep(1)
    page.set_input_files("#fileInput", os.path.join(TEST_FILES, "AdventureWorks.bim"))
    page.wait_for_selector("#appWrap", state="visible", timeout=15000)
    time.sleep(0.5)

    page.click('.tab-btn[data-tab="diagram"]')
    time.sleep(1.5)  # Wait for Cytoscape layout

    page.screenshot(path=os.path.join(SCREENSHOTS, "04-diagram-tab.png"))
    print("4/6 Diagram tab screenshot taken")
    ctx.close()
    browser.close()

    # ── 5. MDATP PBIT model tab ──
    browser = pw.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage", "--single-process"],
    )
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.goto(f"file://{HTML_PATH}", wait_until="load")
    time.sleep(1)
    page.set_input_files("#fileInput", os.path.join(TEST_FILES, "MDATP_Status_Board.pbit"))
    page.wait_for_selector("#appWrap", state="visible", timeout=15000)
    time.sleep(0.5)

    page.check("#selectAll")
    time.sleep(0.3)

    page.screenshot(path=os.path.join(SCREENSHOTS, "05-pbit-model.png"))
    print("5/6 PBIT model screenshot taken")
    ctx.close()
    browser.close()

    # ── 6. Diagram with MDATP showing relationships ──
    browser = pw.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage", "--single-process"],
    )
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.goto(f"file://{HTML_PATH}", wait_until="load")
    time.sleep(1)
    page.set_input_files("#fileInput", os.path.join(TEST_FILES, "MDATP_Status_Board.pbit"))
    page.wait_for_selector("#appWrap", state="visible", timeout=15000)
    time.sleep(0.5)

    page.click('.tab-btn[data-tab="diagram"]')
    time.sleep(1.5)

    page.screenshot(path=os.path.join(SCREENSHOTS, "06-pbit-diagram.png"))
    print("6/6 PBIT diagram screenshot taken")
    ctx.close()
    browser.close()

    pw.stop()
    print(f"\nAll screenshots saved to {SCREENSHOTS}/")


if __name__ == "__main__":
    take_screenshots()
