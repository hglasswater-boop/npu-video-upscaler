"""Small Windows-first PySide6 GUI. All conversion work runs off the UI thread."""

from pathlib import Path
from threading import Event

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (QApplication, QFileDialog, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QMainWindow, QMessageBox,
                               QProgressBar, QPushButton, QVBoxLayout, QWidget)

from .pipeline import JobCancelled, run_video


class Worker(QThread):
    progress_changed = Signal(int, int)
    succeeded = Signal(int)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, source: Path, model: Path, destination: Path):
        super().__init__()
        self.source, self.model, self.destination = source, model, destination
        self.cancel_flag = Event()

    def run(self):
        try:
            frames = run_video(self.source, self.model, self.destination,
                               lambda done, total: self.progress_changed.emit(done, total or 0),
                               self.cancel_flag)
            self.succeeded.emit(frames)
        except JobCancelled:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('NPU Video Upscaler — experimental')
        self.resize(640, 260)
        self.worker = None
        layout = QVBoxLayout()
        form = QFormLayout()
        self.source = self._picker(form, 'Input MP4 / MKV', 'Video files (*.mp4 *.mkv)', False)
        self.model = self._picker(form, 'OpenVINO model XML', 'OpenVINO IR (*.xml)', False)
        self.destination = self._picker(form, 'Output MP4', 'MP4 (*.mp4)', True)
        layout.addLayout(form)
        actions = QHBoxLayout()
        self.start_btn = QPushButton('Start NPU conversion')
        self.cancel_btn = QPushButton('Cancel')
        self.cancel_btn.setEnabled(False)
        actions.addWidget(self.start_btn)
        actions.addWidget(self.cancel_btn)
        layout.addLayout(actions)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1)
        self.bar.setValue(0)
        self.status = QLabel('Ready. Requires preconverted NPU-compatible OpenVINO IR.')
        layout.addWidget(self.bar)
        layout.addWidget(self.status)
        wrapper = QWidget()
        wrapper.setLayout(layout)
        self.setCentralWidget(wrapper)
        self.start_btn.clicked.connect(self.start_job)
        self.cancel_btn.clicked.connect(self.cancel_job)

    def _picker(self, form, label, file_filter, save):
        edit = QLineEdit()
        browse = QPushButton('Browse…')
        row = QHBoxLayout()
        row.addWidget(edit)
        row.addWidget(browse)
        form.addRow(label, row)

        def select():
            if save:
                name, _ = QFileDialog.getSaveFileName(self, label, edit.text(), file_filter)
            else:
                name, _ = QFileDialog.getOpenFileName(self, label, edit.text(), file_filter)
            if name:
                edit.setText(name)
        browse.clicked.connect(select)
        return edit

    def start_job(self):
        if self.worker and self.worker.isRunning():
            return
        if not all((self.source.text(), self.model.text(), self.destination.text())):
            QMessageBox.warning(self, 'Missing paths', 'Select input, model and output files.')
            return
        self.worker = Worker(Path(self.source.text()), Path(self.model.text()), Path(self.destination.text()))
        self.worker.progress_changed.connect(self.update_progress)
        self.worker.succeeded.connect(lambda frames: self.finish(f'Completed: {frames} frames'))
        self.worker.failed.connect(lambda message: self.finish(f'Failed: {message}'))
        self.worker.cancelled.connect(lambda: self.finish('Cancelled'))
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.status.setText('Preparing NPU / converting…')
        self.bar.setRange(0, 0)
        self.worker.start()

    def update_progress(self, done, total):
        if total:
            self.bar.setRange(0, max(done, total))
            self.bar.setValue(done)
            self.status.setText(f'{done} / ~{total} frames')
        else:
            self.status.setText(f'{done} frames')

    def cancel_job(self):
        if self.worker:
            self.worker.cancel_flag.set()
            self.status.setText('Cancelling after current NPU tile…')

    def finish(self, message):
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.bar.setRange(0, 1)
        self.bar.setValue(1 if message.startswith('Completed') else 0)
        self.status.setText(message)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.cancel_job()
            event.ignore()
        else:
            event.accept()


def main():
    app = QApplication([])
    window = MainWindow()
    window.show()
    return app.exec()
