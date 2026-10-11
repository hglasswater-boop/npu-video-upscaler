"""Small Windows-first PySide6 GUI. All conversion work runs off the UI thread."""

from pathlib import Path
from threading import Event
import os
import subprocess
import time

from PySide6.QtCore import QThread, Signal, QSettings, QTimer, QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication, QFileDialog, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QMainWindow, QMessageBox as QtMessageBox,
                               QProgressBar, QPushButton, QVBoxLayout, QWidget, QCheckBox)

from .pipeline import JobCancelled, run_video
from .media_tools import (find_installed_media_tools, install_vendor_media_tools,
                          resolve_media_tools, MediaToolsError)
from .model_packages import find_prepared_model, install_model_zip
from .model_download import choose_model_release
from .updates import choose_update, download_installer, fetch_releases
from . import __version__


def _duration(seconds):
    hours, rest = divmod(max(0, round(seconds)), 3600)
    minutes, seconds = divmod(rest, 60)
    return (f'{hours}時間' if hours else '') + (f'{minutes}分' if minutes else '') + f'{seconds}秒'


class QMessageBox(QtMessageBox):
    """Japanese actions even when the Qt Japanese translation pack is absent."""

    @staticmethod
    def question(parent, title, message, *args):
        dialog = QtMessageBox(parent)
        dialog.setWindowTitle(title)
        dialog.setText(message)
        dialog.setIcon(QtMessageBox.Icon.Question)
        yes = dialog.addButton("はい", QtMessageBox.ButtonRole.YesRole)
        dialog.addButton("いいえ", QtMessageBox.ButtonRole.NoRole)
        dialog.setDefaultButton(yes)
        dialog.exec()
        return (QtMessageBox.StandardButton.Yes if dialog.clickedButton() == yes
                else QtMessageBox.StandardButton.No)

    @staticmethod
    def _notice(parent, title, message, severity):
        dialog = QtMessageBox(parent)
        dialog.setWindowTitle(title)
        if len(message) > 160:
            dialog.setText("処理を完了できませんでした。詳しい原因は「詳細を表示」で確認できます。")
            dialog.setDetailedText(message)
        else:
            dialog.setText(message)
        dialog.setIcon(severity)
        dialog.setMaximumWidth(600)
        dialog.setStyleSheet("QLabel#qt_msgbox_label { max-width: 490px; }")
        dialog.addButton("閉じる", QtMessageBox.ButtonRole.AcceptRole)
        for button in dialog.findChildren(QPushButton):
            if button.text() == "Show Details...":
                button.setText("詳細を表示")
            elif button.text() == "Hide Details...":
                button.setText("詳細を隠す")
        dialog.exec()

    @staticmethod
    def warning(parent, title, message):
        QMessageBox._notice(parent, title, message, QtMessageBox.Icon.Warning)

    @staticmethod
    def critical(parent, title, message):
        QMessageBox._notice(parent, title, message, QtMessageBox.Icon.Critical)


class Worker(QThread):
    progress_changed = Signal(int, int)
    detail_progress_changed = Signal(int, int, int, int)
    stage_changed = Signal(str)
    succeeded = Signal(int)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, source: Path, model: Path, destination: Path,
                 preview_seconds: int | None = None, optimize_tiles: bool = True):
        super().__init__()
        self.source, self.model, self.destination = source, model, destination
        self.preview_seconds = preview_seconds
        self.optimize_tiles = optimize_tiles
        self.cancel_flag = Event()

    def run(self):
        last_detail_at = float('-inf')
        def report_detail(done, total, tile_done, tile_total):
            nonlocal last_detail_at
            now = time.monotonic()
            if tile_done in (0, tile_total) or now - last_detail_at >= 0.25:
                last_detail_at = now
                self.detail_progress_changed.emit(done, total or 0, tile_done, tile_total)
        try:
            frames = run_video(self.source, self.model, self.destination,
                               lambda done, total: self.progress_changed.emit(done, total or 0),
                               self.cancel_flag, preview_seconds=self.preview_seconds,
                               stage_changed=self.stage_changed.emit,
                               detail_progress=report_detail, optimize_tiles=self.optimize_tiles)
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


class ModelInstallWorker(QThread):
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, package: Path):
        super().__init__()
        self.package = package

    def run(self):
        try:
            self.completed.emit(str(install_model_zip(self.package)))
        except Exception as exc:
            self.failed.emit(str(exc))


class ModelDownloadWorker(QThread):
    completed = Signal(str)
    failed = Signal(str)

    def run(self):
        try:
            release = choose_model_release(fetch_releases())
            if release is None:
                raise RuntimeError('No verified model ZIP published in project Releases yet')
            directory = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'NpuVideoUpscaler' / 'Downloads'
            archive = download_installer(release, directory)
            self.completed.emit(str(install_model_zip(archive)))
        except Exception as exc:
            self.failed.emit(str(exc))


class MediaDownloadWorker(QThread):
    progress_changed = Signal(int, int)
    completed = Signal()
    failed = Signal(str)

    def run(self):
        try:
            install_vendor_media_tools(
                progress=lambda done, total: self.progress_changed.emit(done, total)
            )
            self.completed.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f'NPU Video Upscaler v{__version__} — 開発版')
        self.setAcceptDrops(True)
        self.worker = None
        self.update_check_worker = None
        self.update_download_worker = None
        self.model_setup_worker = None
        self.model_download_worker = None
        self.media_download_worker = None
        self.pending_update = None
        self._media_ready_known = find_installed_media_tools() is not None
        self.settings = QSettings('NpuVideoUpscaler', 'NpuVideoUpscaler')
        from .gui_layout import build_ui
        prepared_model = find_prepared_model()
        build_ui(self, prepared_model)
        self.start_btn.clicked.connect(self.start_job)
        self.cancel_btn.clicked.connect(self.cancel_job)
        self.update_btn.clicked.connect(self.check_updates)
        self.model_setup_btn.clicked.connect(self.install_model_package_dialog)
        self.model_download_btn.clicked.connect(self.download_model_prompt)
        self.media_setup_btn.clicked.connect(self.download_ffmpeg_prompt)
        self.driver_help_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(
            'https://www.intel.com/content/www/us/en/download/794734/intel-npu-driver-windows.html'
        )))
        if os.environ.get('NPU_UPSCALER_SMOKE_TEST') != '1':
            if find_installed_media_tools() is None:
                QTimer.singleShot(600, self.download_ffmpeg_prompt)
            elif not prepared_model and self.settings.value('promptModelSetup', True, type=bool):
                QTimer.singleShot(2600, self.download_model_prompt)
        if self.auto_update.isChecked():
            QTimer.singleShot(1500, self.check_updates)

    def _refresh_guidance(self, *_ignored):
        self.media_state.setText(
            "FFmpeg：設定済み" if self._media_ready_known
            else "FFmpeg：未設定（下のボタンでダウンロード）")
        self.model_state.setText(
            "AIモデル：設定済み" if self.model.text()
            else "AIモデル：未設定（下のボタンでダウンロード）")
        if not self.source.text():
            self.guidance.setText("次にすること：① 動画をドロップするか「参照…」で選んでください。")
        elif not self._media_ready_known:
            self.guidance.setText("次にすること：② FFmpegをダウンロードしてください。")
        elif not self.model.text():
            self.guidance.setText("次にすること：② AIモデルをダウンロードしてください。")
        else:
            self.guidance.setText(
                "準備完了：③ 先頭60秒だけ試し、確認してから全編を変換できます。")

    def _picker(self, form, label, file_filter, save):
        edit = QLineEdit()
        edit.setAcceptDrops(False)
        edit.setMinimumWidth(0)
        browse = QPushButton('参照…')
        row = QHBoxLayout()
        row.addWidget(edit, 1)
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

    def _dropped_video(self, event):
        if self._job_busy() or not (event.possibleActions() & Qt.DropAction.CopyAction):
            return None
        urls = event.mimeData().urls()
        if len(urls) != 1 or not urls[0].isLocalFile():
            return None
        path = Path(urls[0].toLocalFile())
        if path.suffix.lower() not in {'.mp4', '.mkv'} or not path.is_file():
            return None
        return path

    def dragEnterEvent(self, event):
        if self._dropped_video(event) is not None:
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        path = self._dropped_video(event)
        if path is None:
            event.ignore()
            return
        self.source.setText(str(path))
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()

    def _suggest_output(self, *_ignored):
        """Change the suggested name only when the user has not edited it."""
        if hasattr(self, 'start_btn'):
            self.start_btn.setText('先頭60秒を試す' if self.preview.isChecked()
                                   else 'NPUで変換を開始')
        current = self.destination.text()
        if not self.source.text():
            return
        if current and current != self._suggested_output:
            return
        source = Path(self.source.text())
        suffix = '_upscaled_preview60' if self.preview.isChecked() else '_upscaled'
        suggestion = str(source.with_name(f'{source.stem}{suffix}.mp4'))
        self._suggested_output = suggestion
        self.destination.setText(suggestion)

    def _media_busy(self):
        return self.media_download_worker is not None and self.media_download_worker.isRunning()

    def download_ffmpeg_prompt(self):
        if self._job_busy() or self._media_busy() or self._model_busy():
            return
        if find_installed_media_tools():
            self._media_ready_known = True
            self._refresh_guidance()
            self.status.setText('FFmpegとffprobeは設定済みです。')
            return
        answer = QMessageBox.question(
            self, 'FFmpegとffprobeのセットアップ',
            'GitHubの配布元（GyanD）からFFmpeg 9.0.2（約115MB）をダウンロードしますか？\n'
            '配布元のビルドはGPLv3ライセンスです： https://ffmpeg.org/legal.html\n'
            'SHA-256を検証し、アプリ専用のユーザーフォルダーに保存します。 '
            '管理者権限やPATH設定の変更は不要です。',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.status.setText('FFmpegが未設定です。変換前に「FFmpegをダウンロード」を押してください。')
            return
        self.media_download_worker = MediaDownloadWorker()
        self.media_download_worker.progress_changed.connect(
            lambda done, total: self.status.setText(
                f'FFmpegダウンロード： {done // (1024 * 1024)} / '
                f'{total // (1024 * 1024)} MiB'
            )
        )
        self.media_download_worker.completed.connect(self._media_ready)
        self.media_download_worker.failed.connect(self._media_failed)
        self.media_setup_btn.setEnabled(False)
        self.start_btn.setEnabled(False)
        self.status.setText('FFmpegを配布元からダウンロードしています…')
        self.media_download_worker.start()

    def _media_ready(self):
        self.media_setup_btn.setEnabled(True)
        self.start_btn.setEnabled(True)
        self._media_ready_known = True
        self._refresh_guidance()
        self.status.setText('FFmpegの設定が完了しました。PATH変更は不要です。')
        if not self.model.text() and self.settings.value('promptModelSetup', True, type=bool):
            QTimer.singleShot(300, self.download_model_prompt)

    def _media_failed(self, message):
        self.media_setup_btn.setEnabled(True)
        self.start_btn.setEnabled(True)
        self.status.setText('FFmpegの設定に失敗しました。詳細はエラー通知で確認できます。')
        QMessageBox.warning(self, 'FFmpegの設定に失敗', message)

    def _model_busy(self):
        return ((self.model_setup_worker and self.model_setup_worker.isRunning())
                or (self.model_download_worker and self.model_download_worker.isRunning()))

    def download_model_prompt(self):
        if self._job_busy() or self._model_busy() or self._media_busy():
            return
        answer = QMessageBox.question(
            self, 'AI超解像モデルのセットアップ',
            'GitHub Releasesから試験用BSRGANx2モデルをダウンロードしますか？\\n'
            'SHA-256を検証し、モデルがNPUでコンパイルできた場合のみ\\n'
            'インストールします。CPU/GPUへの自動切替は行いません。',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            self.settings.setValue('promptModelSetup', False)
            return
        self.model_download_worker = ModelDownloadWorker()
        self.model_download_worker.completed.connect(self._model_ready)
        self.model_download_worker.failed.connect(self._model_setup_failed)
        self.start_btn.setEnabled(False)
        self.model_download_btn.setEnabled(False)
        self.model_setup_btn.setEnabled(False)
        self.status.setText('公式モデルをダウンロードしてNPU上で検証しています…')
        self.model_download_worker.start()

    def install_model_package_dialog(self):
        if self._job_busy() or (self.model_setup_worker and self.model_setup_worker.isRunning()):
            QMessageBox.warning(self, 'モデルのセットアップ中', '先に実行中の処理を完了してください。')
            return
        archive, _ = QFileDialog.getOpenFileName(
            self, '信頼できるNPUモデルZIPを選択', '', 'モデルZIP (*.zip)')
        if not archive:
            return
        answer = QMessageBox.question(
            self, 'モデルZIPの確認',
            'NPU Video Upscaler公式配布物のZIPだけを使用してください。\\n'
            '内蔵チェックサムは破損検出用で、配布元の真正性は保証しません。\\n'
            'Intel NPUで検証してインストールしますか？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.model_setup_worker = ModelInstallWorker(Path(archive))
        self.model_setup_worker.completed.connect(self._model_ready)
        self.model_setup_worker.failed.connect(self._model_setup_failed)
        self.model_setup_btn.setEnabled(False)
        self.start_btn.setEnabled(False)
        self.status.setText('モデルを検証しNPUでコンパイルしています…')
        self.model_setup_worker.start()

    def _model_ready(self, model_path):
        self.model.setText(model_path)
        self._refresh_guidance()
        self.start_btn.setEnabled(True)
        self.model_setup_btn.setEnabled(True)
        self.model_download_btn.setEnabled(True)
        self.status.setText('NPUモデルの設定が完了しました。変換する動画を選択してください。')

    def _model_setup_failed(self, message):
        self.start_btn.setEnabled(True)
        self.model_setup_btn.setEnabled(True)
        self.model_download_btn.setEnabled(True)
        self.status.setText('AIモデルの設定に失敗しました。詳細はエラー通知で確認できます。')
        QMessageBox.warning(self, 'NPUモデルの設定に失敗', message)

    def _job_busy(self):
        return self.worker is not None and self.worker.isRunning()

    def check_updates(self):
        if self.update_check_worker and self.update_check_worker.isRunning():
            return
        self.update_check_worker = UpdateCheckWorker()
        self.update_check_worker.found.connect(self._update_found)
        self.update_check_worker.error.connect(
            lambda message: self.status.setText(f'更新確認に失敗: {message}'))
        self.update_check_worker.start()

    def _update_found(self, update):
        if update is None:
            self.status.setText('新しいバージョンはありません。')
            return
        if self._job_busy():
            self.pending_update = update
            self.status.setText(f'バージョン {update.version} の更新があります。変換後に適用できます。')
            return
        response = QMessageBox.question(
            self, '更新があります',
            f'GitHub Releasesにバージョン {update.version} があります。\n'
            'インストーラをダウンロードしてSHA-256を検証しますか？',
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
            lambda done, total: self.status.setText(f'更新ファイルのダウンロード： {done // 1024} / {total // 1024} KiB'))
        self.update_download_worker.error.connect(
            lambda message: QMessageBox.warning(self, '更新に失敗', message))
        self.update_download_worker.completed.connect(self._install_update)
        self.update_download_worker.start()

    def _install_update(self, installer_path):
        if self._job_busy():
            self.status.setText('更新ファイルを取得しました。変換完了後にインストールしてください。')
            return
        response = QMessageBox.question(
            self, '更新をインストール',
            'インストーラのSHA-256検証に成功しました。\n'
            'アプリを終了して更新インストーラを起動しますか？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if response != QMessageBox.StandardButton.Yes:
            self.status.setText(f'検証済みの更新ファイル： {installer_path}')
            return
        try:
            subprocess.Popen([installer_path], cwd=str(Path(installer_path).parent),
                             close_fds=True)
        except OSError as exc:
            QMessageBox.critical(self, 'インストーラを起動できません', str(exc))
            return
        QApplication.instance().quit()

    def start_job(self):
        if self._media_busy():
            QMessageBox.warning(self, 'FFmpegのセットアップ中', 'FFmpegの設定が完了するまでお待ちください。')
            return
        try:
            resolve_media_tools()
        except MediaToolsError as exc:
            QMessageBox.warning(self, 'FFmpegが必要です', str(exc))
            return
        if self._model_busy():
            QMessageBox.warning(self, 'モデルのセットアップ中', 'NPUの検証が完了するまでお待ちください。')
            return
        if self.worker and self.worker.isRunning():
            return
        if not all((self.source.text(), self.model.text(), self.destination.text())):
            QMessageBox.warning(self, 'ファイルが未選択です', '入力動画・AIモデル・出力先を指定してください。')
            return
        self.worker = Worker(Path(self.source.text()), Path(self.model.text()),
                             Path(self.destination.text()),
                             preview_seconds=60 if self.preview.isChecked() else None,
                             optimize_tiles=self.optimize_tiles.isChecked())
        self._started_at = time.monotonic()
        self._progress_started_at = None
        self._progress_done = 0
        self.worker.progress_changed.connect(self.update_progress)
        self.worker.detail_progress_changed.connect(self.update_detailed_progress)
        self.worker.succeeded.connect(lambda frames: self.finish(f'完了：{frames} フレーム'))
        self.worker.failed.connect(lambda message: self.finish(f'失敗：{message}'))
        self.worker.stage_changed.connect(lambda stage: self.status.setText(f'{stage}中…'))
        self.worker.cancelled.connect(lambda: self.finish('キャンセルしました'))
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.status.setText('NPUを準備して変換しています…')
        self.bar.setRange(0, 0)
        self.bar.setFormat('%p%')
        self.progress_label.setText('進捗：準備中｜経過：0秒｜残り：計算中')
        self.worker.start()

    def update_progress(self, done, total):
        self.update_detailed_progress(done, total, 0, 0)

    def update_detailed_progress(self, done, total, tile_done, tile_total):
        now = time.monotonic()
        self._progress_done = done
        if tile_total and getattr(self, '_progress_started_at', None) is None:
            self._progress_started_at = now
        completed = done + (tile_done / tile_total if tile_total else 0)
        frames = f'{done} / 約{total} フレーム' if total else f'{done} フレーム（総数不明）'
        parts = []
        if total:
            percentage = min(99.999, max(0, completed / max(total, completed) * 100))
            parts.append(f'{percentage:.3f}%')
            self.bar.setRange(0, 100000)
            self.bar.setValue(int(percentage * 1000))
            self.bar.setFormat(f'{percentage:.3f}%')
        else:
            self.bar.setRange(0, 0)
        parts.append(frames)
        if tile_total:
            parts.append(f'現在のフレーム：{tile_done} / {tile_total} タイル')
        parts.append(f'経過：{_duration(now - getattr(self, "_started_at", now))}')
        started = getattr(self, '_progress_started_at', None)
        if total and done >= 1 and started is not None and now > started:
            remaining = max(0, total - completed) * (now - started) / completed
            parts.append(f'残り目安：{_duration(remaining)}')
        else:
            parts.append('残り：計算中')
        self.progress_label.setText('｜'.join(parts))

    def cancel_job(self):
        if self.worker:
            self.worker.cancel_flag.set()
            self.status.setText('現在のNPU処理が終わり次第キャンセルします…')

    def finish(self, message):
        if message.startswith('失敗：') and len(message) > 160:
            QMessageBox.warning(self, '動画変換に失敗', message)
            message = '動画変換に失敗しました。詳細はエラー通知で確認できます。'
        if message.startswith('完了：') and hasattr(self, '_started_at'):
            message += f'（処理時間：{time.monotonic() - self._started_at:.1f}秒）'
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        if message.startswith('完了：'):
            self.bar.setRange(0, 100000)
            self.bar.setValue(100000)
            self.bar.setFormat('100.000%')
            self.progress_label.setText(
                f'100.000%｜{getattr(self, "_progress_done", 0)} フレーム｜'
                f'経過：{_duration(time.monotonic() - getattr(self, "_started_at", time.monotonic()))}')
        elif self.bar.maximum() == 0:
            self.bar.setRange(0, 1)
            self.bar.setValue(0)
            self.bar.setFormat('中断')
        self.status.setText(message)
        if self.pending_update:
            update, self.pending_update = self.pending_update, None
            QTimer.singleShot(100, lambda: self._update_found(update))

    def closeEvent(self, event):
        if self._job_busy():
            self.cancel_job()
            event.ignore()
        elif ((self.update_check_worker and self.update_check_worker.isRunning())
              or (self.update_download_worker and self.update_download_worker.isRunning())
              or self._model_busy() or self._media_busy()):
            self.status.setText('更新処理の完了を待っています…')
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
