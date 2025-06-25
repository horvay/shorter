import os
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QProgressBar,
    QMessageBox,
)
from PySide6.QtCore import QThread, Signal
from shorter.core.video_utils import remove_silence

VIDEO_DIR = "videos"
CUTS_DIR = os.path.join(VIDEO_DIR, "cuts")

def create_remove_silence_tab() -> QWidget:
    tab = QWidget()
    layout = QVBoxLayout(tab)
    tab.refresh_targets = []

    def add_refresh_target(target_func):
        tab.refresh_targets.append(target_func)

    tab.add_refresh_target = add_refresh_target

    # Video selection
    video_selection_layout = QHBoxLayout()
    video_label = QLabel("Select Video:")
    video_combo = QComboBox()
    video_selection_layout.addWidget(video_label)
    video_selection_layout.addWidget(video_combo)
    layout.addLayout(video_selection_layout)

    # Process button
    process_button = QPushButton("Remove Silent Sections")
    layout.addWidget(process_button)

    # Progress and status
    progress_bar = QProgressBar()
    status_label = QLabel("Ready to process video.")
    layout.addWidget(progress_bar)
    layout.addWidget(status_label)
    layout.addStretch()

    def populate_videos():
        video_combo.clear()
        all_videos = []
        if os.path.exists(CUTS_DIR):
            videos = [os.path.join(CUTS_DIR, f) for f in os.listdir(CUTS_DIR) if f.endswith(('.mp4', '.mkv', '.avi', '.webm'))]
            all_videos.extend(videos)

        video_combo.addItems([os.path.basename(v) for v in all_videos])
        tab.video_map = {os.path.basename(v): v for v in all_videos}

    def start_processing():
        selected_video = video_combo.currentText()
        if not selected_video:
            QMessageBox.warning(tab, "Warning", "Please select a video.")
            return

        in_path = tab.video_map[selected_video]
        out_filename = f"autocut_{selected_video}"
        out_path = os.path.join(CUTS_DIR, out_filename)

        process_button.setEnabled(False)
        status_label.setText("Processing...")
        progress_bar.setRange(0, 0)

        tab.worker = SilenceRemoverWorker(in_path, out_path)
        tab.worker.finished.connect(on_processing_finished)
        tab.worker.start()

    def on_processing_finished(success: bool, message: str):
        process_button.setEnabled(True)
        status_label.setText(message)
        progress_bar.setRange(0, 100)
        progress_bar.setValue(0)
        if success:
            QMessageBox.information(tab, "Success", "Silence removal complete!")
            for target in tab.refresh_targets:
                target()
        else:
            QMessageBox.critical(tab, "Error", f"Failed to remove silence: {message}")

    process_button.clicked.connect(start_processing)
    populate_videos()

    tab.populate_videos = populate_videos


    return tab


class SilenceRemoverWorker(QThread):
    finished = Signal(bool, str)

    def __init__(self, input_path: str, output_path: str):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path

    def run(self):
        try:
            success = remove_silence(self.input_path, self.output_path)
            if success:
                self.finished.emit(True, "Processing finished.")
            else:
                self.finished.emit(False, "Processing failed.")
        except Exception as e:
            self.finished.emit(False, str(e))