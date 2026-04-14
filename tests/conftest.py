# tests/conftest.py
import os
import types
import pytest

# tests/conftest.py
import sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtWidgets
except Exception:
    QtWidgets = None

@pytest.fixture(scope="session")
def qapp():
    if QtWidgets is None:
        pytest.skip("PyQt6 nie jest zainstalowane w środowisku testowym")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    return app

@pytest.fixture
def _ns():
    return lambda **kw: types.SimpleNamespace(**kw)
