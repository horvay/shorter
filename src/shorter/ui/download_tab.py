from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QMessageBox,
)
from PySide6.QtCore import QThread, Signal
from shorter.core.downloader import download_video
from typing import Any, Optional
import os


OUTPUT_PATH = "videos"


def create_download_tab() -> QWidget:
    tab = QWidget()
    layout = QVBoxLayout(tab)
    tab.refresh_targets = []

    def add_refresh_target(target_func):
        tab.refresh_targets.append(target_func)

    tab.add_refresh_target = add_refresh_target


    url_label = QLabel("YouTube URL:")
    url_input = QLineEdit()
    filename_label = QLabel("Optional Filename (no extension):")
    filename_input = QLineEdit()
    download_button = QPushButton("Download")
    progress_bar = QProgressBar()
    progress_bar.setRange(0, 100)
    progress_bar.setValue(0)
    status_label = QLabel("Enter a URL and click Download.")

    layout.addWidget(url_label)
    layout.addWidget(url_input)
    layout.addWidget(filename_label)
    layout.addWidget(filename_input)
    layout.addWidget(download_button)
    layout.addWidget(progress_bar)
    layout.addWidget(status_label)
    layout.addStretch()

    def start_download():
        url = url_input.text()
        if not url:
            QMessageBox.warning(tab, "Warning", "Please enter a URL.")
            return

        filename = filename_input.text() or None

        download_button.setEnabled(False)
        status_label.setText("Starting download...")

        # Keep a reference to the worker
        tab.thread = DownloadWorker(url, OUTPUT_PATH, filename)
        tab.thread.progress.connect(progress_bar.setValue)
        tab.thread.finished.connect(on_download_finished)
        tab.thread.start()

    def on_download_finished(success: bool, message: str):
        download_button.setEnabled(True)
        status_label.setText(message)
        if success:
            progress_bar.setValue(100)
            QMessageBox.information(tab, "Success", "Download completed successfully!")
            for target in tab.refresh_targets:
                target()
        else:
            QMessageBox.critical(tab, "Error", f"Download failed: {message}")
        progress_bar.setValue(0)

    download_button.clicked.connect(start_download)

    return tab

class DownloadWorker(QThread):
    progress = Signal(int)
    finished = Signal(bool, str)  # success, message

    def __init__(self, url: str, output_path: str, filename: Optional[str] = None):
        super().__init__()
        self.url = url
        self.output_path = output_path
        self.filename = filename
        self._is_running = True

    def run(self):
        try:
            download_video(self.url, self.output_path, self.progress_hook, self.filename)
            self.finished.emit(True, "Download finished!")
        except Exception as e:
            self.finished.emit(False, str(e))

    def progress_hook(self, d: dict[str, Any]) -> None:
        if d["status"] == "downloading":
            total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate")
            if total_bytes:
                downloaded_bytes = d.get("downloaded_bytes")
                if downloaded_bytes:
                    progress = int((downloaded_bytes / total_bytes) * 100)
                    self.progress.emit(progress)
        elif d["status"] == "finished":
            self.progress.emit(100)

    def stop(self):
        self._is_running = False