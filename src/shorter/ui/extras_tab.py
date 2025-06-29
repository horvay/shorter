import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QMessageBox, QSlider, QProgressBar
)
from PySide6.QtCore import Qt, QThread, Signal
from shorter.core.video_utils import speed_up_video

VIDEO_DIR = "videos"
CUTS_DIR = os.path.join(VIDEO_DIR, "cuts")

class ExtrasWorker(QThread):
    finished = Signal(bool, str)

    def __init__(self, input_path, output_path, speed):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.speed = speed

    def run(self):
        try:
            success = speed_up_video(self.input_path, self.output_path, self.speed)
            if success:
                self.finished.emit(True, "Processing finished.")
            else:
                self.finished.emit(False, "Processing failed.")
        except Exception as e:
            self.finished.emit(False, str(e))

def create_extras_tab() -> QWidget:
    tab = QWidget()
    layout = QVBoxLayout(tab)
    tab.video_map = {}
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

    # Speed selection
    speed_layout = QHBoxLayout()
    speed_label = QLabel("Speed: 1.0x")
    speed_slider = QSlider(Qt.Horizontal)
    speed_slider.setRange(10, 30) # Represents 1.0 to 3.0
    speed_slider.setValue(10)
    speed_layout.addWidget(speed_label)
    speed_layout.addWidget(speed_slider)
    layout.addLayout(speed_layout)

    # Process button
    process_button = QPushButton("Process Video")
    layout.addWidget(process_button)

    # Progress and status
    progress_bar = QProgressBar()
    status_label = QLabel("Ready.")
    layout.addWidget(progress_bar)
    layout.addWidget(status_label)
    layout.addStretch()

    # --- Connections and Logic ---

    def update_speed_label(value):
        speed = value / 10.0
        speed_label.setText(f"Speed: {speed:.1f}x")

    speed_slider.valueChanged.connect(update_speed_label)

    def start_processing():
        selected_video = video_combo.currentText()
        if not selected_video:
            QMessageBox.warning(tab, "Warning", "Please select a video.")
            return

        in_path = tab.video_map[selected_video]
        speed = speed_slider.value() / 10.0

        base, ext = os.path.splitext(selected_video)
        out_filename = f"{base}_{speed:.1f}x{ext}"
        out_path = os.path.join(CUTS_DIR, out_filename)

        process_button.setEnabled(False)
        status_label.setText("Processing...")
        progress_bar.setRange(0, 0)

        tab.worker = ExtrasWorker(in_path, out_path, speed)
        tab.worker.finished.connect(on_processing_finished)
        tab.worker.start()

    def on_processing_finished(success, message):
        process_button.setEnabled(True)
        status_label.setText(message)
        progress_bar.setRange(0, 100)
        progress_bar.setValue(0)

        if success:
            QMessageBox.information(tab, "Success", "Video processing complete!")
            for target in tab.refresh_targets:
                target()
        else:
            QMessageBox.critical(tab, "Error", f"Failed to process video: {message}")

    process_button.clicked.connect(start_processing)

    def populate_videos():
        video_combo.blockSignals(True)
        video_combo.clear()

        all_videos = []
        # We'll populate from the 'cuts' directory for this tab
        if os.path.exists(CUTS_DIR):
            videos = [os.path.join(CUTS_DIR, f) for f in os.listdir(CUTS_DIR) if f.endswith(('.mp4', '.mkv', '.avi', '.webm'))]
            all_videos.extend(videos)

        video_combo.addItems([os.path.basename(v) for v in all_videos])
        tab.video_map = {os.path.basename(v): v for v in all_videos}
        video_combo.blockSignals(False)

    tab.populate_videos = populate_videos
    populate_videos()

    return tab