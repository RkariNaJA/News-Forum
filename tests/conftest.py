import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES = Path(__file__).resolve().parent / "fixtures"


# Tests marked "live" need internet and a browser (TradingView's widgets), so a plain run skips them.
def pytest_addoption(parser):
    parser.addoption("--live", action="store_true", help="also run tests that need internet and a browser")


def pytest_configure(config):
    config.addinivalue_line("markers", "live: needs internet and a browser; run with --live")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--live"):
        return
    skip = pytest.mark.skip(reason="needs internet and a browser: run with --live")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)
