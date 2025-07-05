import os
import json
import glob
from typing import Optional, List, Dict

# Suppress linter warnings for PySide6 imports
# type: ignore[import-untyped]
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QComboBox,
                            QLineEdit, QTextEdit, QLabel, QProgressBar,
                            QMessageBox)
# type: ignore[import-untyped]
from PySide6.QtCore import Qt, QThread, Signal
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request

# Suppress linter warnings for googleapiclient dynamic attributes
# type: ignore[import]
# type: ignore[attr-defined]

class UploadThread(QThread):
    progress = Signal(int)
    status = Signal(str)
    finished = Signal(bool)

    def __init__(self, youtube, video_file: str, title: str, description: str, privacy: str, playlist_id: Optional[str] = None):
        super().__init__()
        self.youtube = youtube
        self.video_file = video_file
        self.title = title
        self.description = description
        self.privacy = privacy
        self.playlist_id = playlist_id

    def run(self):
        try:
            self.status.emit("Starting upload...")
            body = {
                'snippet': {
                    'title': self.title,
                    'description': self.description,
                    'tags': ['youtube', 'video'],
                    'categoryId': '22'  # Category ID for People & Blogs
                },
                'status': {
                    'privacyStatus': self.privacy
                }
            }

            media = MediaFileUpload(self.video_file, chunksize=-1, resumable=True)
            request = self.youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media
            )

            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    self.progress.emit(int(status.progress() * 100))
                    self.status.emit(f"Uploading: {int(status.progress() * 100)}%")

            video_id = response['id']
            self.status.emit("Video uploaded successfully!")

            if self.playlist_id:
                self.status.emit("Adding video to playlist...")
                playlist_item_body = {
                    'snippet': {
                        'playlistId': self.playlist_id,
                        'resourceId': {
                            'kind': 'youtube#video',
                            'videoId': video_id
                        }
                    }
                }
                self.youtube.playlistItems().insert(
                    part="snippet",
                    body=playlist_item_body
                ).execute()
                self.status.emit("Video added to playlist!")

            self.finished.emit(True)
        except Exception as e:
            self.status.emit(f"Upload failed: {str(e)}")
            self.finished.emit(False)

class PublishTab(QWidget):
    def __init__(self):
        super().__init__()
        self.v_layout = QVBoxLayout(self)
        self.youtube = None
        self.playlists: List[Dict] = []
        self.setup_ui()

    def setup_ui(self):
        self.auth_button = QPushButton("Authenticate with YouTube")
        self.auth_button.clicked.connect(self.authenticate)
        self.v_layout.addWidget(self.auth_button)

        self.video_label = QLabel("Select Video to Upload:")
        self.v_layout.addWidget(self.video_label)

        self.video_combo = QComboBox()
        self.v_layout.addWidget(self.video_combo)

        self.title_label = QLabel("Video Title:")
        self.v_layout.addWidget(self.title_label)

        self.title_input = QLineEdit()
        self.v_layout.addWidget(self.title_input)

        self.description_label = QLabel("Video Description:")
        self.v_layout.addWidget(self.description_label)

        self.description_input = QTextEdit()
        self.v_layout.addWidget(self.description_input)

        self.privacy_label = QLabel("Privacy Setting:")
        self.v_layout.addWidget(self.privacy_label)

        self.privacy_combo = QComboBox()
        self.privacy_combo.addItems(["public", "private", "unlisted"])
        self.v_layout.addWidget(self.privacy_combo)

        self.playlist_label = QLabel("Add to Playlist (optional):")
        self.v_layout.addWidget(self.playlist_label)

        self.playlist_combo = QComboBox()
        self.playlist_combo.addItem("None", None)
        self.v_layout.addWidget(self.playlist_combo)

        self.upload_button = QPushButton("Upload Video")
        self.upload_button.clicked.connect(self.start_upload)
        self.upload_button.setEnabled(False)
        self.v_layout.addWidget(self.upload_button)

        self.progress_bar = QProgressBar()
        self.progress_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.v_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Status: Not authenticated")
        self.v_layout.addWidget(self.status_label)

    def refresh(self):
        self.load_videos()
        if self.youtube:
            self.load_playlists()

    def populate_videos(self):
        """Alias used by MainWindow for cross-tab refresh system."""
        self.load_videos()

    def load_videos(self):
        self.video_combo.clear()
        captioned_folder = os.path.join("videos", "cuts", "captioned")
        if not os.path.exists(captioned_folder):
            os.makedirs(captioned_folder, exist_ok=True)
        videos = glob.glob(os.path.join(captioned_folder, "*.mp4"))
        for video in videos:
            self.video_combo.addItem(os.path.basename(video), video)

    def load_playlists(self):
        if not self.youtube:
            return
        try:
            self.playlist_combo.clear()
            self.playlist_combo.addItem("None", None)
            response = self.youtube.playlists().list(
                part="snippet",
                mine=True,
                maxResults=50
            ).execute()
            self.playlists = response.get('items', [])
            for playlist in self.playlists:
                self.playlist_combo.addItem(playlist['snippet']['title'], playlist['id'])
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load playlists: {str(e)}")

    def authenticate(self):
        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json',
                scopes=['https://www.googleapis.com/auth/youtube.upload', 'https://www.googleapis.com/auth/youtube']
            )
            credentials = flow.run_local_server(port=0)
            self.youtube = build('youtube', 'v3', credentials=credentials)
            self.auth_button.setEnabled(False)
            self.upload_button.setEnabled(True)
            self.status_label.setText("Status: Authenticated")
            self.load_playlists()
            QMessageBox.information(self, "Success", "Authentication successful!")
        except FileNotFoundError:
            QMessageBox.critical(self, "Error", "credentials.json file not found. Please ensure it is in the correct directory.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Authentication failed: {str(e)}")

    def start_upload(self):
        if self.video_combo.currentData() is None:
            QMessageBox.warning(self, "Warning", "Please select a video to upload.")
            return
        if not self.title_input.text():
            QMessageBox.warning(self, "Warning", "Please enter a title for the video.")
            return

        video_file = self.video_combo.currentData()
        title = self.title_input.text()
        description = self.description_input.toPlainText()
        privacy = self.privacy_combo.currentText()
        playlist_id = self.playlist_combo.currentData()

        self.upload_thread = UploadThread(self.youtube, video_file, title, description, privacy, playlist_id)
        self.upload_thread.progress.connect(self.progress_bar.setValue)
        self.upload_thread.status.connect(self.status_label.setText)
        self.upload_thread.finished.connect(self.upload_finished)
        self.upload_thread.start()
        self.upload_button.setEnabled(False)

    def upload_finished(self, success: bool):
        self.upload_button.setEnabled(True)
        if success:
            QMessageBox.information(self, "Success", "Video uploaded successfully!")
        else:
            QMessageBox.critical(self, "Error", "Video upload failed. Check the status for details.")

def create_publish_tab() -> QWidget:
    """Factory function to maintain compatibility with main_window import."""
    tab = PublishTab()
    tab.refresh()
    return tab