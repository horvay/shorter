import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QListWidget, QMessageBox, QStyle, QSlider, QProgressBar
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtCore import Qt, QUrl, QThread, Signal, QRect, QRectF, QSizeF
from shorter.ui.widgets.zoom_video_widget import ZoomVideoWidget
from shorter.core.video_utils import process_zoom_pan, get_video_resolution
import time

VIDEO_DIR = "videos"
CUTS_DIR = os.path.join(VIDEO_DIR, "cuts")

def format_time(ms: int) -> str:
    s = ms / 1000
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{int(h):02}:{int(m):02}:{int(s):02}"

class ZoomWorker(QThread):
    finished = Signal(bool, str)

    def __init__(self, input_path, output_path, regions):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.regions = regions

    def run(self):
        try:
            success = process_zoom_pan(self.input_path, self.output_path, self.regions)
            if success:
                self.finished.emit(True, "Processing finished.")
            else:
                self.finished.emit(False, "Processing failed.")
        except Exception as e:
            self.finished.emit(False, str(e))

def create_zoom_tab() -> QWidget:
    tab = QWidget()
    layout = QVBoxLayout(tab)
    tab.zoom_regions = []
    tab.video_map = {}
    tab.refresh_targets = []
    tab.current_video_resolution = None
    tab.initial_frame_loaded = False

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

    # Custom Video player
    video_widget = ZoomVideoWidget()
    layout.addWidget(video_widget, 1)

    # Playback controls
    controls_layout = QHBoxLayout()
    play_button = QPushButton()
    play_button.setIcon(tab.style().standardIcon(QStyle.SP_MediaPlay))
    position_slider = QSlider(Qt.Horizontal)
    controls_layout.addWidget(play_button)
    controls_layout.addWidget(position_slider)
    layout.addLayout(controls_layout)

    # Zoom region list and controls
    zoom_layout = QHBoxLayout()
    region_list = QListWidget()
    remove_region_button = QPushButton("Remove Selected Region")
    zoom_layout.addWidget(region_list)
    zoom_layout.addWidget(remove_region_button)
    layout.addLayout(zoom_layout)

    # Process button
    process_button = QPushButton("Process Zoomed Video")
    layout.addWidget(process_button)

    # Progress and status
    progress_bar = QProgressBar()
    status_label = QLabel("Ready.")
    layout.addWidget(progress_bar)
    layout.addWidget(status_label)

    # Media Player Setup
    tab.media_player = QMediaPlayer()
    tab.audio_output = QAudioOutput()
    tab.media_player.setAudioOutput(tab.audio_output)
    tab.media_player.setVideoOutput(video_widget.video_sink())

    # Connect signals and slots
    def load_video(video_name):
        if video_name and video_name in tab.video_map:
            video_path = tab.video_map[video_name]
            tab.initial_frame_loaded = False  # Reset flag for new video
            tab.media_player.setSource(QUrl.fromLocalFile(video_path))
            tab.current_video_resolution = get_video_resolution(video_path)
            if tab.current_video_resolution:
                w, h = tab.current_video_resolution
                video_widget.set_video_size(QSizeF(w, h))

    def update_duration(duration):
        position_slider.setRange(0, duration)
        if not tab.initial_frame_loaded:
            tab.media_player.setPosition(0)
            tab.initial_frame_loaded = True

    def update_position(position):
        position_slider.setValue(position)

        current_time_sec = position / 1000.0
        active_rect = QRectF()

        # Find the last region with a start time before the current playback time
        found_region = None
        for region in tab.zoom_regions:
            if region['time'] <= current_time_sec:
                found_region = region
            else:
                break # List is sorted, so we can stop

        if found_region:
            active_rect = found_region['rect']
        else:
            active_rect = QRectF()

        video_widget.set_active_rect(active_rect)

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
    play_button.clicked.connect(play_pause)

    # Zoom Logic
    def add_zoom_region(rect_f: QRectF):
        if not tab.current_video_resolution:
            QMessageBox.warning(tab, "Error", "Could not determine video resolution.")
            return

        # rect_f is already in video coordinates from the scene
        scaled_rect = rect_f.toRect()

        timestamp = tab.media_player.position()
        region_text = f"{format_time(timestamp)} -> Rect({scaled_rect.x()}, {scaled_rect.y()}, {scaled_rect.width()}, {scaled_rect.height()})"

        tab.zoom_regions.append({
            'time': timestamp / 1000.0,
            'rect': scaled_rect,
        })
        # Sort regions by time after adding
        tab.zoom_regions.sort(key=lambda x: x['time'])
        # Regenerate list to reflect sorted order
        region_list.clear()
        for region in tab.zoom_regions:
            scaled_rect = region['rect']
            region_text = f"{format_time(region['time'] * 1000)} -> Rect({scaled_rect.x()}, {scaled_rect.y()}, {scaled_rect.width()}, {scaled_rect.height()})"
            region_list.addItem(region_text)

    def remove_selected_region():
        selected_items = region_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(tab, "Warning", "Please select a region to remove.")
            return

        row = region_list.row(selected_items[0])
        region_list.takeItem(row)
        tab.zoom_regions.pop(row)

    video_widget.region_selected.connect(add_zoom_region)
    remove_region_button.clicked.connect(remove_selected_region)

    def start_processing():
        selected_video = video_combo.currentText()
        if not selected_video:
            QMessageBox.warning(tab, "Warning", "Please select a video.")
            return

        in_path = tab.video_map[selected_video]
        out_filename = f"zoomed_{selected_video}"
        out_path = os.path.join(CUTS_DIR, out_filename)

        process_button.setEnabled(False)
        status_label.setText("Processing...")
        progress_bar.setRange(0, 0)

        tab.worker = ZoomWorker(in_path, out_path, tab.zoom_regions)
        tab.worker.finished.connect(on_processing_finished)
        tab.worker.start()

    def on_processing_finished(success, message):
        process_button.setEnabled(True)
        status_label.setText(message)
        progress_bar.setRange(0, 100)
        progress_bar.setValue(0)

        if success:
            QMessageBox.information(tab, "Success", "Zoom processing complete!")
            for target in tab.refresh_targets:
                target()
        else:
            QMessageBox.critical(tab, "Error", f"Failed to process zoom: {message}")

    process_button.clicked.connect(start_processing)

    # Populate videos
    def populate_videos():
        video_combo.blockSignals(True)
        video_combo.clear()
        region_list.clear()
        tab.zoom_regions.clear()
        video_widget.set_active_rect(QRectF())
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