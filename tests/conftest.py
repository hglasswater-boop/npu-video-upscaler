"""Maintain one Qt app during tests and shut it down before Python interpreter exit."""
import gc
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
    app = _QT_APP
    yield app
    for widget in list(app.topLevelWidgets()):
        widget.close()
        widget.deleteLater()
    app.processEvents()
    app.quit()
    _QT_APP = None
    app.deleteLater()
    app.processEvents()
    del app
    gc.collect()
