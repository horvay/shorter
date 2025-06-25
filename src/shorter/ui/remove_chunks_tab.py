import os
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QListWidget,
    QMessageBox,
    QStyle,
    QSlider,
    QProgressBar,
)
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtCore import Qt, QUrl, QThread, Signal
from superqt import QRangeSlider
from shorter.core.video_utils import remove_chunks
import time


VIDEO_DIR = "videos"
CUTS_DIR = os.path.join(VIDEO_DIR, "cuts")

def format_time(ms: int) -> str:
    s = ms / 1000
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{int(h):02}:{int(m):02}:{int(s):02}"

class RemoveChunksWorker(QThread):
    finished = Signal(bool, str)

    def __init__(self, input_path, output_path, chunks):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.chunks = chunks

    def run(self):
        try:
            success = remove_chunks(self.input_path, self.output_path, self.chunks)
            if success:
                self.finished.emit(True, "Processing finished.")
            else:
                self.finished.emit(False, "Processing failed.")
        except Exception as e:
            self.finished.emit(False, str(e))


def create_remove_chunks_tab() -> QWidget:
    tab = QWidget()
    layout = QVBoxLayout(tab)
    tab.chunks_to_remove = []
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

    # Video player
    video_widget = QVideoWidget()
    layout.addWidget(video_widget, 1)

    # Playback controls
    controls_layout = QHBoxLayout()
    play_button = QPushButton()
    play_button.setIcon(tab.style().standardIcon(QStyle.SP_MediaPlay))
    position_slider = QSlider(Qt.Horizontal)
    controls_layout.addWidget(play_button)
    controls_layout.addWidget(position_slider)
    layout.addLayout(controls_layout)

    # Range slider for chunk selection
    time_range_layout = QHBoxLayout()
    start_time_label = QLabel("00:00:00")
    end_time_label = QLabel("00:00:00")
    range_slider = QRangeSlider(Qt.Horizontal)
    time_range_layout.addWidget(start_time_label)
    time_range_layout.addWidget(range_slider)
    time_range_layout.addWidget(end_time_label)
    layout.addLayout(time_range_layout)

    # Chunk list and controls
    chunks_layout = QHBoxLayout()
    chunk_list = QListWidget()
    add_chunk_button = QPushButton("Add Chunk to Remove")
    chunks_layout.addWidget(chunk_list)
    chunks_layout.addWidget(add_chunk_button)
    layout.addLayout(chunks_layout)

    # Progress and status
    progress_bar = QProgressBar()
    status_label = QLabel("Ready.")
    layout.addWidget(progress_bar)
    layout.addWidget(status_label)

    # Process button
    process_button = QPushButton("Remove Selected Chunks")
    layout.addWidget(process_button)

    # Media Player Setup
    tab.media_player = QMediaPlayer()
    tab.audio_output = QAudioOutput()
    tab.media_player.setAudioOutput(tab.audio_output)
    tab.media_player.setVideoOutput(video_widget)
    tab.previous_range_values = (0, 0)

    def load_video(video_name):
        if video_name and video_name in tab.video_map:
            video_path = tab.video_map[video_name]
            tab.media_player.setSource(QUrl.fromLocalFile(video_path))

    def update_duration(duration):
        range_slider.setRange(0, duration)
        position_slider.setRange(0, duration)
        range_slider.setValue((0, duration))

    def update_position(position):
        position_slider.setValue(position)

    def update_time_labels(values):
        start, end = int(values[0]), int(values[1])
        start_time_label.setText(format_time(start))
        end_time_label.setText(format_time(end))

    def seek_on_drag(values):
        lower, upper = int(values[0]), int(values[1])
        prev_lower, prev_upper = tab.previous_range_values
        if lower != prev_lower:
            tab.media_player.setPosition(lower)
        elif upper != prev_upper:
            tab.media_player.setPosition(upper)
        tab.previous_range_values = (lower, upper)

    def play_pause():
        if tab.media_player.playbackState() == QMediaPlayer.PlayingState:
            tab.media_player.pause()
            play_button.setIcon(tab.style().standardIcon(QStyle.SP_MediaPlay))
        else:
            tab.media_player.play()
            play_button.setIcon(tab.style().standardIcon(QStyle.SP_MediaPause))

    video_combo.currentTextChanged.connect(load_video)
    tab.media_player.durationChanged.connect(update_duration)
    tab.media_player.positionChanged.connect(update_position)
    position_slider.sliderMoved.connect(tab.media_player.setPosition)
    range_slider.valueChanged.connect(update_time_labels)
    range_slider.sliderMoved.connect(seek_on_drag)
    play_button.clicked.connect(play_pause)

    # Chunk Logic
    def add_chunk():
        start, end = range_slider.value()
        if start >= end:
            return

        chunk_text = f"{format_time(start)} -> {format_time(end)}"
        chunk_list.addItem(chunk_text)
        tab.chunks_to_remove.append((start / 1000.0, end / 1000.0))

    def remove_chunk_item(item):
        row = chunk_list.row(item)
        chunk_list.takeItem(row)
        del tab.chunks_to_remove[row]

    add_chunk_button.clicked.connect(add_chunk)
    chunk_list.itemDoubleClicked.connect(remove_chunk_item)

    # Processing Logic
    def start_processing():
        selected_video = video_combo.currentText()
        if not selected_video:
            QMessageBox.warning(tab, "Warning", "Please select a video.")
            return

        in_path = tab.video_map[selected_video]
        out_filename = f"manualcut_{selected_video}"
        out_path = os.path.join(CUTS_DIR, out_filename)

        process_button.setEnabled(False)
        status_label.setText("Processing...")
        progress_bar.setRange(0, 0)

        tab.worker = RemoveChunksWorker(in_path, out_path, tab.chunks_to_remove)
        tab.worker.finished.connect(on_processing_finished)
        tab.worker.start()

    def on_processing_finished(success, message):
        process_button.setEnabled(True)
        status_label.setText(message)
        progress_bar.setRange(0, 100)
        progress_bar.setValue(0)
        if success:
            QMessageBox.information(tab, "Success", "Chunks removed successfully!")
            chunk_list.clear()
            tab.chunks_to_remove.clear()
            for target in tab.refresh_targets:
                target()
        else:
            QMessageBox.critical(tab, "Error", f"Failed to remove chunks: {message}")

    process_button.clicked.connect(start_processing)

    def populate_videos():
        video_combo.blockSignals(True)
        video_combo.clear()
        chunk_list.clear()
        tab.chunks_to_remove.clear()
        all_videos = []
        if os.path.exists(CUTS_DIR):
            videos = [os.path.join(CUTS_DIR, f) for f in os.listdir(CUTS_DIR) if f.endswith(('.mp4', '.mkv', '.avi', '.webm'))]
            all_videos.extend(videos)

        video_combo.addItems([os.path.basename(v) for v in all_videos])
        tab.video_map = {os.path.basename(v): v for v in all_videos}
        video_combo.blockSignals(False)
        if video_combo.count() > 0:
            load_video(video_combo.currentText())

    tab.populate_videos = populate_videos
    populate_videos()

    return tab