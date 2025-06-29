import os
import subprocess
import tempfile
import nemo.collections.asr as nemo_asr
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QComboBox,
    QTableWidget,
    QProgressBar,
    QTableWidgetItem,
    QHeaderView,
    QApplication,
)
from PySide6.QtCore import QThread, Signal, Qt
from matplotlib.font_manager import findSystemFonts
from matplotlib.textpath import TextPath
from matplotlib.font_manager import FontProperties
from PIL import ImageFont
import random
import re
import platform
import traceback


class TranscriptionThread(QThread):
    finished_signal = Signal(list)
    error_signal = Signal(str)

    def __init__(self, video_path, asr_model):
        super().__init__()
        self.video_path = video_path
        self.asr_model = asr_model

    def run(self):
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_audio:
                audio_filename = tmp_audio.name

            command = [
                "ffmpeg",
                "-i",
                self.video_path,
                "-vn",
                "-acodec",
                "pcm_s16le",
                "-ar",
                "16000",
                "-ac",
                "1",
                audio_filename,
                "-y",
            ]
            subprocess.run(
                command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )

            output = self.asr_model.transcribe([audio_filename], timestamps=True)
            word_timestamps = output[0].timestamp["word"]

            self.finished_signal.emit(word_timestamps)

        except Exception as e:
            self.error_signal.emit(str(e))
        finally:
            if os.path.exists(audio_filename):
                os.remove(audio_filename)


class CaptioningThread(QThread):
    finished_signal = Signal(str)
    error_signal = Signal(str)

    def __init__(self, video_path, font_path, transcription):
        super().__init__()
        self.video_path = video_path
        self.font_path = font_path
        self.transcription = transcription

    def get_text_dimensions(self, text, font_path, font_size):
        try:
            # Use PIL for more reliable text measurement
            font = ImageFont.truetype(font_path, font_size)
            bbox = font.getbbox(text)
            width = bbox[2] - bbox[0]  # right - left
            height = bbox[3] - bbox[1]  # bottom - top
            return width, height
        except Exception as e:
            print(f"[Debug] get_text_dimensions failed: {e}")
            # Fallback to approximate measurement
            return len(text) * font_size * 0.6, font_size

    def run(self):
        try:
            print("[Debug] CaptioningThread: Starting run method.")
            # 1. Get video info
            print("[Debug] CaptioningThread: Getting video info...")
            video_info = self.get_video_info()
            video_duration = self.get_video_duration()
            video_width = video_info["width"]
            video_height = video_info["height"]
            print(f"[Debug] CaptioningThread: Video info: {video_width}x{video_height}, duration: {video_duration}s")

            # 2. Prepare layout
            print("[Debug] CaptioningThread: Building filter complex...")
            filter_complex = self.build_filter_complex(
                video_width, video_height, video_duration
            )
            print(f"[Debug] CaptioningThread: Filter complex built (length: {len(filter_complex)}).")

            # 3. Run ffmpeg
            print("[Debug] CaptioningThread: Running ffmpeg...")
            output_filename = self.run_ffmpeg(filter_complex)
            print("[Debug] CaptioningThread: ffmpeg finished.")

            self.finished_signal.emit(output_filename)
            print("[Debug] CaptioningThread: Finished signal emitted.")

        except Exception as e:
            print("[Debug] CaptioningThread: EXCEPTION OCCURRED!")
            traceback.print_exc() # Print the full traceback
            error_message = str(e)
            if isinstance(e, subprocess.CalledProcessError):
                stderr_output = e.stderr.decode('utf-8', errors='ignore') if e.stderr else "No stderr output."
                error_message += f"\n--- FFMPEG ERROR ---\n{stderr_output}"
            self.error_signal.emit(error_message)

    def get_video_info(self):
        command = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=s=x:p=0",
            self.video_path,
        ]
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        width, height = map(int, result.stdout.strip().split("x"))
        return {"width": width, "height": height}

    def get_video_duration(self):
        command = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            self.video_path,
        ]
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        return float(result.stdout.strip())

    def build_filter_complex(self, video_width, video_height, video_duration):
        print("[Debug] build_filter_complex: Starting.")
        is_vertical = video_height > video_width

        if is_vertical:
            # Bottom half for shorts
            box_width = int(video_width * 0.9)
            box_height = int(video_height * 0.4)
            x_pos = (video_width - box_width) // 2
            y_pos = int(video_height * 0.55)
        else:
            # Left side for normal videos
            box_width = int(video_width * 0.4)
            box_height = int(video_height * 0.8)
            x_pos = int(video_width * 0.05)
            y_pos = (video_height - box_height) // 2

        font_size = 60 # Base font size
        space_width, _ = self.get_text_dimensions(" ", self.font_path, font_size)
        drawtext_filters = []
        line_buffer = []
        x, y = 0, 0

        # Helper to generate filters for a finished line
        def flush_line_buffer(buffer, end_time):
            if not buffer:
                return []

            filters = []

            # ffmpeg's drawtext needs an escaped path for windows
            escaped_font_path = self.font_path.replace('\\', '\\\\')
            if platform.system() == "Windows":
                escaped_font_path = escaped_font_path.replace(':', '\\:')

            for word_info in buffer:
                 # The comma in 'between' must be escaped!
                 # Each word now appears at its own start time but disappears with the line
                filters.append(
                    f"drawtext=fontfile='{escaped_font_path}':text='{word_info['text']}':"
                    f"fontsize={font_size}:fontcolor=white:"
                    f"x={word_info['x']}:y={word_info['y']}:"
                    f"enable='between(t,{word_info['start']}\\,{end_time})'"
                )
            return filters

        print(f"[Debug] build_filter_complex: Starting loop over {len(self.transcription)} words.")
        for i, word_data in enumerate(self.transcription):
            word_text = word_data["word"].strip().replace("'", "’")
            # This needs to be done carefully
            word_text_escaped = re.sub(r"([\\:%',\.\[\];=])", r"\\\1", word_text)

            start_time = word_data["start"]

            w, h = self.get_text_dimensions(word_text, self.font_path, font_size)

            # --- Logic to decide when to break a line ---
            break_condition = False

            # If word overflows current line
            if x > 0 and x + w > box_width:
                y += h + 10
                x = 0

            # If line overflows the caption box, flush and reset
            if y + h > box_height:
                break_condition = True

            # If there's a long pause, flush and reset
            if i > 0 and start_time - self.transcription[i-1]['end'] > 2.0:
                break_condition = True

            if break_condition and line_buffer:
                print(f"[Debug] build_filter_complex: Flushing line buffer at word index {i}")
                line_end_time = line_buffer[-1]['end'] if line_buffer else start_time
                drawtext_filters.extend(flush_line_buffer(line_buffer, line_end_time))

                # Reset for the new screen of text
                line_buffer = []
                x, y = 0, 0

            line_buffer.append({
                "text": word_text_escaped,
                "start": start_time,
                "end": word_data["end"],
                "x": x_pos + x,
                "y": y_pos + y
            })
            x += w + space_width

        # Flush any remaining words in the buffer at the end
        if line_buffer:
            print("[Debug] build_filter_complex: Flushing final line buffer.")
            last_word_end = line_buffer[-1]['end']
            line_end_time = min(last_word_end + 2.0, video_duration)
            drawtext_filters.extend(flush_line_buffer(line_buffer, line_end_time))


        if not drawtext_filters:
            print("[Debug] build_filter_complex: No filters created.")
            return "null"

        joined_filters = ",".join(drawtext_filters)
        print(f"[Debug] build_filter_complex: Finished, returning filter string of length {len(joined_filters)}.")
        return joined_filters

    def run_ffmpeg(self, filter_complex):
        base, _ = os.path.splitext(os.path.basename(self.video_path))
        output_dir = os.path.join("videos", "cuts")
        output_filename = os.path.join(output_dir, f"{base}_captioned.mp4")

        # The -filter_complex option must come before the -i input file.
        # Note for Master: If this still fails with "Option not found",
        # it's likely because your ffmpeg version (6.1+) was compiled
        # without libharfbuzz, which is now required for drawtext.
        command = [
            "ffmpeg",
            "-i", self.video_path,
            "-vf", filter_complex, # Using -vf for video filter
            "-c:a", "copy",
            output_filename,
            "-y"
        ]

        print("--- FFMPEG COMMAND ---")
        # We join the command list into a single string for printing
        print(" ".join(command))
        print("----------------------")

        try:
            # Using shell=False is safer and handles arguments correctly.
            subprocess.run(command, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            # Re-raise with more context
            stderr = e.stderr.decode('utf-8', errors='ignore') if e.stderr else "No stderr."
            raise Exception(f"FFMPEG Error:\n{stderr}") from e

        return output_filename


class CaptionTab(QWidget):
    def __init__(self):
        super().__init__()
        self.asr_model = None
        self.layout = QVBoxLayout(self)

        self.video_selector = QComboBox()
        self.layout.addWidget(self.video_selector)

        self.transcribe_button = QPushButton("Transcribe Video")
        self.layout.addWidget(self.transcribe_button)

        self.transcription_progress_bar = QProgressBar()
        self.transcription_progress_bar.setRange(0, 0)  # Indeterminate
        self.transcription_progress_bar.setVisible(False)
        self.layout.addWidget(self.transcription_progress_bar)

        self.transcription_table = QTableWidget()
        self.transcription_table.setColumnCount(3)
        self.transcription_table.setHorizontalHeaderLabels(
            ["Word", "Start (s)", "End (s)"]
        )
        self.transcription_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.layout.addWidget(self.transcription_table)

        captioning_layout = QHBoxLayout()
        self.font_selector = QComboBox()
        captioning_layout.addWidget(self.font_selector)

        self.caption_button = QPushButton("Generate Captioned Video")
        captioning_layout.addWidget(self.caption_button)
        self.layout.addLayout(captioning_layout)

        self.captioning_progress_bar = QProgressBar()
        self.captioning_progress_bar.setRange(0, 0)
        self.captioning_progress_bar.setVisible(False)
        self.layout.addWidget(self.captioning_progress_bar)

        self.populate_videos()
        self.populate_fonts()

        self.transcribe_button.clicked.connect(self.start_transcription)
        self.caption_button.clicked.connect(self.start_captioning)

    def populate_fonts(self):
        self.font_selector.clear()
        fonts_dir = "fonts"
        if not os.path.exists(fonts_dir):
            os.makedirs(fonts_dir)

        font_paths = [
            os.path.join(fonts_dir, f)
            for f in os.listdir(fonts_dir)
            if f.lower().endswith((".ttf", ".otf"))
        ]
        self.font_selector.addItems(font_paths)
        if not font_paths:
            self.font_selector.addItem("No fonts found in 'fonts' folder")

    def populate_videos(self):
        self.video_selector.clear()
        cuts_dir = os.path.join("videos", "cuts")
        if not os.path.exists(cuts_dir):
            os.makedirs(cuts_dir, exist_ok=True)
            return

        videos = [
            f
            for f in os.listdir(cuts_dir)
            if os.path.isfile(os.path.join(cuts_dir, f))
        ]
        self.video_selector.addItems(videos)

    def set_transcription(self, words):
        self.transcription_table.setRowCount(len(words))
        for i, word_data in enumerate(words):
            word = QTableWidgetItem(word_data["word"])
            start = QTableWidgetItem(f"{word_data['start']:.2f}")
            end = QTableWidgetItem(f"{word_data['end']:.2f}")

            self.transcription_table.setItem(i, 0, word)
            self.transcription_table.setItem(i, 1, start)
            self.transcription_table.setItem(i, 2, end)

    def add_refresh_target(self, target):
        pass

    def start_transcription(self):
        if not self.asr_model:
            # Show a message to the user that the model is loading
            self.transcribe_button.setText("Loading Model...")
            self.transcribe_button.setEnabled(False)
            QApplication.processEvents()  # Update the UI

            try:
                self.asr_model = nemo_asr.models.ASRModel.from_pretrained(
                    model_name="nvidia/parakeet-tdt-0.6b-v2"
                )
            except Exception as e:
                self.on_transcription_error(f"Failed to load model: {e}")
                self.transcribe_button.setText("Transcribe Video")
                return
            finally:
                self.transcribe_button.setText("Transcribe Video")
                self.transcribe_button.setEnabled(True)

        video_name = self.video_selector.currentText()
        if not video_name:
            return

        cuts_dir = os.path.join("videos", "cuts")
        video_path = os.path.join(cuts_dir, video_name)

        self.transcribe_button.setEnabled(False)
        self.transcription_progress_bar.setVisible(True)

        self.thread = TranscriptionThread(video_path, self.asr_model)
        self.thread.finished_signal.connect(self.on_transcription_finished)
        self.thread.error_signal.connect(self.on_transcription_error)
        self.thread.start()

    def on_transcription_finished(self, words):
        self.set_transcription(words)
        self.transcription_progress_bar.setVisible(False)
        self.transcribe_button.setEnabled(True)

    def on_transcription_error(self, error_message):
        print(f"Error: {error_message}") # Should show a dialog later
        self.transcription_progress_bar.setVisible(False)
        self.transcribe_button.setEnabled(True)

    def start_captioning(self):
        video_name = self.video_selector.currentText()
        font_path = self.font_selector.currentText()
        if not video_name or not font_path:
            return

        # Get transcription data from the table
        transcription = []
        for row in range(self.transcription_table.rowCount()):
            transcription.append({
                "word": self.transcription_table.item(row, 0).text(),
                "start": float(self.transcription_table.item(row, 1).text()),
                "end": float(self.transcription_table.item(row, 2).text()),
            })

        if not transcription:
            return # Don't run if there's no transcription

        cuts_dir = os.path.join("videos", "cuts")
        video_path = os.path.join(cuts_dir, video_name)

        self.caption_button.setEnabled(False)
        self.captioning_progress_bar.setVisible(True)

        self.captioning_thread = CaptioningThread(video_path, font_path, transcription)
        self.captioning_thread.finished_signal.connect(self.on_captioning_finished)
        self.captioning_thread.error_signal.connect(self.on_captioning_error)
        self.captioning_thread.start()

    def on_captioning_finished(self, output_filename):
        print(f"Video saved to {output_filename}")
        self.captioning_progress_bar.setVisible(False)
        self.caption_button.setEnabled(True)
        self.populate_videos() # Refresh list

    def on_captioning_error(self, error_message):
        print(f"Captioning Error: {error_message}")
        self.captioning_progress_bar.setVisible(False)
        self.caption_button.setEnabled(True)


def create_caption_tab():
    return CaptionTab()