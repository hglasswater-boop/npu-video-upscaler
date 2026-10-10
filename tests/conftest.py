"""One Qt app for all GUI tests: avoid destroying/recreating QApplication on Windows."""
import os
import pytest

_QT_APP = None


@pytest.fixture(scope="session")
def qt_app():
    global _QT_APP
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    if _QT_APP is None:
        _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP
