import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Emitter import scheduler  # noqa: E402


@pytest.fixture(autouse=True)
def clean_scheduler():
    scheduler.reset()
    yield
    scheduler.reset()
