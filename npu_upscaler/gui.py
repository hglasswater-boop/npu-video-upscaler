"""Small Windows-first PySide6 GUI. All conversion work runs off the UI thread."""

from pathlib import Path
from threading import Event
import os
import subprocess

from PySide6.QtCore import QThread, Signal, QSettings, QTimer
from PySide6.QtWidgets import (QApplication, QFileDialog, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QMainWindow, QMessageBox,
                               QProgressBar, QPushButton, QVBoxLayout, QWidget, QCheckBox)

from .pipeline import JobCancelled, run_video
from .updates import choose_update, download_installer, fetch_releases
from . import __version__


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


class UpdateCheckWorker(QThread):
    found = Signal(object)
    error = Signal(str)

    def run(self):
        try:
            self.found.emit(choose_update(fetch_releases(), __version__))
        except Exception as exc:
            self.error.emit(str(exc))


class UpdateDownloadWorker(QThread):
    progress = Signal(int, int)
    completed = Signal(str)
    error = Signal(str)

    def __init__(self, update):
        super().__init__()
        self.update = update

    def run(self):
        try:
            base = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'NpuVideoUpscaler' / 'Updates'
            path = download_installer(self.update, base, progress=lambda done, total:
                                      self.progress.emit(done, total))
            self.completed.emit(str(path))
        except Exception as exc:
            self.error.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f'NPU Video Upscaler v{__version__} — experimental')
        self.resize(640, 260)
        self.worker = None
        self.update_check_worker = None
        self.update_download_worker = None
        self.pending_update = None
        self.settings = QSettings('NpuVideoUpscaler', 'NpuVideoUpscaler')
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
        update_actions = QHBoxLayout()
        self.update_btn = QPushButton('Check for updates')
        self.auto_update = QCheckBox('Check for updates on startup')
        self.auto_update.setChecked(self.settings.value('autoCheckUpdates', True, type=bool))
        self.auto_update.toggled.connect(
            lambda checked: self.settings.setValue('autoCheckUpdates', checked))
        update_actions.addWidget(self.update_btn)
        update_actions.addWidget(self.auto_update)
        layout.addLayout(update_actions)
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
        self.update_btn.clicked.connect(self.check_updates)
        if self.auto_update.isChecked():
            QTimer.singleShot(1500, self.check_updates)

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

    def _job_busy(self):
        return self.worker is not None and self.worker.isRunning()

    def check_updates(self):
        if self.update_check_worker and self.update_check_worker.isRunning():
            return
        self.update_check_worker = UpdateCheckWorker()
        self.update_check_worker.found.connect(self._update_found)
        self.update_check_worker.error.connect(
            lambda message: self.status.setText(f'Update check failed: {message}'))
        self.update_check_worker.start()

    def _update_found(self, update):
        if update is None:
            self.status.setText('No newer version available.')
            return
        if self._job_busy():
            self.pending_update = update
            self.status.setText(f'Update v{update.version} available after conversion.')
            return
        response = QMessageBox.question(
            self, 'Update available',
            f'Version {update.version} is available from GitHub Releases.\n'
            'Download the installer and verify SHA-256?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if response != QMessageBox.StandardButton.Yes:
            return
        self._download_update(update)

    def _download_update(self, update):
        if self._job_busy() or (self.update_download_worker and self.update_download_worker.isRunning()):
            self.pending_update = update
            return
        self.update_download_worker = UpdateDownloadWorker(update)
        self.update_download_worker.progress.connect(
            lambda done, total: self.status.setText(f'Update download: {done // 1024} / {total // 1024} KiB'))
        self.update_download_worker.error.connect(
            lambda message: QMessageBox.warning(self, 'Update failed', message))
        self.update_download_worker.completed.connect(self._install_update)
        self.update_download_worker.start()

    def _install_update(self, installer_path):
        if self._job_busy():
            self.status.setText('Update downloaded. Finish conversion before installing.')
            return
        response = QMessageBox.question(
            self, 'Install update',
            'The installer passed SHA-256 verification.\n'
            'Close this app and launch the interactive installer now?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if response != QMessageBox.StandardButton.Yes:
            self.status.setText(f'Verified update saved at: {installer_path}')
            return
        try:
            subprocess.Popen([installer_path], cwd=str(Path(installer_path).parent),
                             close_fds=True)
        except OSError as exc:
            QMessageBox.critical(self, 'Unable to start installer', str(exc))
            return
        QApplication.instance().quit()

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
        if self.pending_update:
            update, self.pending_update = self.pending_update, None
            QTimer.singleShot(100, lambda: self._update_found(update))

    def closeEvent(self, event):
        if self._job_busy():
            self.cancel_job()
            event.ignore()
        elif ((self.update_check_worker and self.update_check_worker.isRunning())
              or (self.update_download_worker and self.update_download_worker.isRunning())):
            self.status.setText('Waiting for update request to finish…')
            event.ignore()
        else:
            event.accept()


def main():
    app = QApplication([])
    window = MainWindow()
    window.show()
    if os.environ.get('NPU_UPSCALER_SMOKE_TEST') == '1':
        QTimer.singleShot(1000, app.quit)
    return app.exec()
