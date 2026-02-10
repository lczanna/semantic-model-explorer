"""Playwright configuration for Semantic Model Explorer tests."""

import pytest
from playwright.sync_api import BrowserType, Browser, BrowserContext, Page


BROWSER_ARGS = [
    "--no-sandbox",
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--single-process",
]


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    """Add required browser launch args for this environment."""
    return {
        **browser_type_launch_args,
        "args": BROWSER_ARGS,
    }


@pytest.fixture
def context(browser_type: BrowserType, browser_type_launch_args):
    """Create a fresh browser + context per test (needed for --single-process)."""
    browser = browser_type.launch(**browser_type_launch_args)
    ctx = browser.new_context()
    yield ctx
    ctx.close()
    browser.close()


@pytest.fixture
def page(context: BrowserContext) -> Page:
    """Create a page from the per-test context."""
    return context.new_page()
