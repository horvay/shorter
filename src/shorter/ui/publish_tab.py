import os
import pickle
from typing import Optional

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit,
    QTextEdit, QPushButton, QProgressBar, QMessageBox
)

from googleapiclient.discovery import build  # type: ignore
from googleapiclient.http import MediaFileUpload  # type: ignore
from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore
from google.auth.transport.requests import Request  # type: ignore

VIDEO_DIR = "videos"
CUTS_DIR = os.path.join(VIDEO_DIR, "cuts")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CREDENTIALS_FILE = "credentials.json"  # user provides Google OAuth client here
TOKEN_FILE = "token.pickle"


def _get_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError("Google OAuth credentials.json not found.")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


class UploadWorker(QThread):
    progress = Signal(int)
    finished = Signal(bool, str)

    def __init__(self, video_path: str, title: str, description: str, privacy: str):
        super().__init__()
        self.video_path = video_path
        self.title = title
        self.description = description
        self.privacy = privacy

    def run(self):
        try:
            service = _get_service()
            request_body = {
                "snippet": {
                    "title": self.title,
                    "description": self.description,
                    "categoryId": "22",  # People & Blogs
                },
                "status": {"privacyStatus": self.privacy},
            }
            media = MediaFileUpload(self.video_path, chunksize=1024 * 1024, resumable=True)
            request = service.videos().insert(part="snippet,status", body=request_body, media_body=media)
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    self.progress.emit(int(status.progress() * 100))
            video_id = response.get("id")
            self.progress.emit(100)
            self.finished.emit(True, f"Upload complete! Video ID: {video_id}")
        except Exception as e:
            self.finished.emit(False, str(e))


def create_publish_tab() -> QWidget:
    tab = QWidget()
    layout = QVBoxLayout(tab)
    tab.video_map = {}  # type: ignore[attr-defined]

    # Video selection
    vid_layout = QHBoxLayout()
    vid_layout.addWidget(QLabel("Select Video:"))
    video_combo = QComboBox()
    vid_layout.addWidget(video_combo)
    layout.addLayout(vid_layout)

    # Title / Description
    title_edit = QLineEdit()
    title_edit.setPlaceholderText("Title")
    desc_edit = QTextEdit()
    desc_edit.setPlaceholderText("Description")
    layout.addWidget(title_edit)
    layout.addWidget(desc_edit)

    # Privacy
    priv_layout = QHBoxLayout()
    priv_layout.addWidget(QLabel("Privacy:"))
    privacy_combo = QComboBox()
    privacy_combo.addItems(["public", "unlisted", "private"])
    priv_layout.addWidget(privacy_combo)
    layout.addLayout(priv_layout)

    # Buttons
    auth_button = QPushButton("Authenticate")
    upload_button = QPushButton("Upload")
    layout.addWidget(auth_button)
    layout.addWidget(upload_button)

    # Progress
    progress = QProgressBar()
    progress.setRange(0, 100)
    layout.addWidget(progress)
    layout.addStretch()

    def authenticate():
        try:
            _get_service()
            QMessageBox.information(tab, "Success", "Authentication successful.")
        except Exception as e:
            QMessageBox.critical(tab, "Error", str(e))

    auth_button.clicked.connect(authenticate)

    def start_upload():
        vid_name = video_combo.currentText()
        if not vid_name:
            QMessageBox.warning(tab, "Warning", "Please select a video.")
            return
        full_path = tab.video_map[vid_name]  # type: ignore[attr-defined]
        title = title_edit.text() or os.path.splitext(vid_name)[0]
        description = desc_edit.toPlainText()
        privacy = privacy_combo.currentText()

        upload_button.setEnabled(False)
        progress.setRange(0, 0)

        tab.worker = UploadWorker(full_path, title, description, privacy)  # type: ignore[attr-defined]
        tab.worker.progress.connect(progress.setValue)  # type: ignore[attr-defined]
        tab.worker.finished.connect(on_finished)  # type: ignore[attr-defined]
        tab.worker.start()  # type: ignore[attr-defined]

    def on_finished(success: bool, message: str):
        progress.setRange(0, 100)
        progress.setValue(0)
        upload_button.setEnabled(True)
        if success:
            QMessageBox.information(tab, "Success", message)
        else:
            QMessageBox.critical(tab, "Error", message)

    upload_button.clicked.connect(start_upload)

    def populate_videos():
        video_combo.blockSignals(True)
        video_combo.clear()
        vids = []
        if os.path.exists(CUTS_DIR):
            vids = [os.path.join(CUTS_DIR, f) for f in os.listdir(CUTS_DIR) if f.lower().endswith((".mp4", ".mkv", ".avi", ".webm"))]
        video_combo.addItems([os.path.basename(v) for v in vids])
        tab.video_map = {os.path.basename(v): v for v in vids}  # type: ignore[attr-defined]
        video_combo.blockSignals(False)

    tab.populate_videos = populate_videos  # type: ignore[attr-defined]
    populate_videos()

    return tab