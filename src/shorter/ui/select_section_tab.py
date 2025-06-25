import os
import time
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QSlider,
    QStyle,
    QMessageBox,
    QCheckBox,
)
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtCore import Qt, QUrl
from shorter.core.video_utils import cut_video
from superqt import QRangeSlider

VIDEO_DIR = "videos"

def create_select_section_tab() -> QWidget:
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

    # Video player
    video_widget = QVideoWidget()
    layout.addWidget(video_widget, 1)  # Allow video widget to expand

    # Playback controls
    controls_layout = QHBoxLayout()
    play_button = QPushButton()
    play_button.setIcon(tab.style().standardIcon(QStyle.SP_MediaPlay))

    position_slider = QSlider(Qt.Horizontal)

    controls_layout.addWidget(play_button)
    controls_layout.addWidget(position_slider)
    layout.addLayout(controls_layout)

    # Sliders for start and end
    time_range_layout = QHBoxLayout()
    start_time_label = QLabel("00:00")
    end_time_label = QLabel("00:00")
    range_slider = QRangeSlider(Qt.Horizontal)

    time_range_layout.addWidget(start_time_label)
    time_range_layout.addWidget(range_slider)
    time_range_layout.addWidget(end_time_label)

    layout.addWidget(QLabel("Time Range:"))
    layout.addLayout(time_range_layout)

    # Cut button
    cut_button = QPushButton("Cut Video")
    vertical_checkbox = QCheckBox("Create Vertical Short")
    layout.addWidget(vertical_checkbox)
    layout.addWidget(cut_button)

    # Store media player and audio output on the tab to prevent garbage collection
    tab.media_player = QMediaPlayer()
    tab.audio_output = QAudioOutput()
    tab.media_player.setAudioOutput(tab.audio_output)
    tab.audio_output.setVolume(1.0)
    tab.media_player.setVideoOutput(video_widget)

    tab.previous_range_values = (0, 0)

    def format_time(ms: int) -> str:
        s = ms / 1000
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        return f"{int(h):02}:{int(m):02}:{int(s):02}"

    def update_duration(duration: int):
        position_slider.setRange(0, duration)
        range_slider.setRange(0, duration)
        range_slider.setValue((0, duration))
        start_time_label.setText(format_time(0))
        end_time_label.setText(format_time(duration))
        tab.previous_range_values = (0, duration)

    def update_position(position: int):
        position_slider.setValue(position)

    def update_time_labels(values: tuple[float, float]):
        start, end = values
        start_time_label.setText(format_time(int(start)))
        end_time_label.setText(format_time(int(end)))

    def seek_on_drag(values: tuple[float, float]):
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

    tab.media_player.durationChanged.connect(update_duration)
    tab.media_player.positionChanged.connect(update_position)
    position_slider.sliderMoved.connect(tab.media_player.setPosition)
    range_slider.valueChanged.connect(update_time_labels)
    range_slider.sliderMoved.connect(seek_on_drag)
    play_button.clicked.connect(play_pause)

    def do_cut():
        in_path = os.path.join(VIDEO_DIR, video_combo.currentText())
        out_filename = f"cut_{os.path.basename(in_path)}"
        out_path = os.path.join(VIDEO_DIR, "cuts", out_filename)

        start_time, end_time = range_slider.value()

        if start_time >= end_time:
            QMessageBox.warning(tab, "Warning", "Start time must be before end time.")
            return

        success = cut_video(
            in_path,
            out_path,
            format_time(int(start_time)),
            format_time(int(end_time)),
            vertical_checkbox.isChecked()
        )

        if success:
            QMessageBox.information(tab, "Success", f"Video cut and saved to {out_path}")
            for target in tab.refresh_targets:
                target()
        else:
            QMessageBox.critical(tab, "Error", "Failed to cut video.")

    cut_button.clicked.connect(do_cut)

    def populate_videos():
        video_combo.clear()
        if not os.path.exists(VIDEO_DIR):
            return
        videos = [f for f in os.listdir(VIDEO_DIR) if f.endswith(('.mp4', '.mkv', '.avi', '.webm'))]
        video_combo.addItems(videos)

    def load_selected_video(video_name: str):
        if video_name:
            video_path = os.path.join(VIDEO_DIR, video_name)
            tab.media_player.setSource(QUrl.fromLocalFile(video_path))

    video_combo.currentTextChanged.connect(load_selected_video)

    populate_videos()

    if video_combo.count() > 0:
        load_selected_video(video_combo.currentText())

    tab.populate_videos = populate_videos
    return tab