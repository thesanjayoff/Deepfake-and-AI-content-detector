import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from tests.fixtures.make_fixtures import FIXTURES_DIR, make_all  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def fixtures():
    required = ["plain_photo.jpg", "spliced_photo.jpg", "sample_human_text.txt"]
    if not all((FIXTURES_DIR / f).exists() for f in required):
        make_all()
    return FIXTURES_DIR
