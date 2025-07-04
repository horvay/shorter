import os
import subprocess
import tempfile
import json
from typing import List, Dict, Tuple, Any

import nemo.collections.asr as nemo_asr
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    QProgressBar,
    QMessageBox,
    QHeaderView,
)
from PIL import ImageFont

# Directory that holds cuts to be captioned
CLIPS_DIR = os.path.join("videos", "cuts")
# Directory that holds bundled fonts
FONTS_DIR = "fonts"
# Output directory for captioned videos
OUTPUT_DIR = os.path.join(CLIPS_DIR, "captioned")

# Words that should not start a new, enlarged caption line
AVOID_LIST = {
    # articles / determiners
    "a", "an", "the", "this", "that", "these", "those",

    # pronouns
    "i", "me", "you", "your", "he", "him", "his", "she", "her", "it", "its", "we", "us", "our", "they", "them", "their",

    # auxiliary / modal verbs
    "am", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do", "does", "did",
    "will", "would", "shall", "should", "can", "could", "may", "might", "must",

    # conjunctions / prepositions / misc fillers
    "and", "or", "but", "so", "for", "nor", "yet", "if", "than", "as", "at", "by", "from", "in", "into", "of", "on", "off",
    "out", "over", "to", "up", "down", "with", "about", "above", "after", "before", "between", "during", "until", "within",

    # other very common words
    "not", "no", "yes", "more", "most", "some", "any", "each", "every", "one", "all", "how", "when", "where", "what",
    "which", "who", "whom", "why", "been", "there", "here", "then", "too", "very",

    # common contractions
    "i'm", "you're", "we're", "they're", "it's", "that's", "there's", "who's",
    "i've", "you've", "we've", "they've", "could've", "would've", "should've",
    "i'll", "you'll", "he'll", "she'll", "we'll", "they'll",
    "isn't", "aren't", "wasn't", "weren't",
    "don't", "doesn't", "didn't",
    "can't", "couldn't", "won't", "wouldn't", "shouldn't",
    "haven't", "hasn't", "hadn't",
}

# -------------------------------------------------
# Helper functions
# -------------------------------------------------

def _ensure_directories() -> None:
    """Make sure expected folders exist."""
    for d in (CLIPS_DIR, OUTPUT_DIR):
        if not os.path.exists(d):
            os.makedirs(d, exist_ok=True)


def _get_video_info(path: str) -> Dict[str, float]:
    """Return width, height and duration (seconds) for the given video."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,duration",
        "-of", "json",
        path,
    ]
    res = subprocess.run(cmd, check=True, text=True, capture_output=True)
    info = json.loads(res.stdout)["streams"][0]
    return {
        "width": int(info["width"]),
        "height": int(info["height"]),
        "duration": float(info.get("duration", 0)),
    }


def _font_candidates() -> List[str]:
    """Return paths to *.ttf / *.otf fonts from FONTS_DIR. Fall back to system fonts if none found."""
    fonts = []
    if os.path.isdir(FONTS_DIR):
        fonts = [os.path.join(FONTS_DIR, f) for f in os.listdir(FONTS_DIR) if f.lower().endswith((".ttf", ".otf"))]
    if not fonts:
        # fallback: try to find any system fonts via matplotlib (which is already a dependency elsewhere)
        from matplotlib.font_manager import findSystemFonts
        fonts = findSystemFonts(fontpaths=None, fontext='ttf')
    return fonts


def _choose_font(size_key: str, video_height: int) -> int:
    """Return pixel size for the given key ('small', 'medium', 'large')."""
    # Sizes are proportional to the video height
    sizes = {
        "small": 0.035,   # smaller for less emphasis
        "medium": 0.055,
        "large": 0.100,   # even larger for stronger emphasis
    }
    return int(video_height * sizes[size_key])


# -------------------------------------------------
# Worker threads
# -------------------------------------------------

class TranscriptionThread(QThread):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, video_path: str):
        super().__init__()
        self.video_path = video_path
        # Lazy-load ASR model so we do it only once for the whole application
        global _NEMO_MODEL
        if "_NEMO_MODEL" not in globals():
            _NEMO_MODEL = None  # type: ignore
        self._model: Any = _NEMO_MODEL

    def run(self):
        try:
            if self._model is None:
                # This model is relatively small (~120 MB) compared to others and decent quality
                self._model = nemo_asr.models.EncDecCTCModel.from_pretrained(model_name="nvidia/parakeet-tdt-0.6b-v2")
                globals()["_NEMO_MODEL"] = self._model  # cache for next time

            # Extract mono 16 kHz wav to a temporary file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                wav_path = tmp.name
            ff_cmd = [
                "ffmpeg", "-y", "-i", self.video_path, "-vn",
                "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", wav_path,
            ]
            subprocess.run(ff_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            asr_out = self._model.transcribe([wav_path], timestamps=True)  # type: ignore[attr-defined]
            word_ts = asr_out[0].timestamp["word"]  # list of Dict(word,start_time/offset,...)

            # Normalize timestamps to seconds – newer NeMo returns offsets (frames)
            win_stride = float(getattr(self._model.cfg.preprocessor, "window_stride", 0.02))  # seconds
            sec_per_frame = 8 * win_stride  # 8x subsampling for conformer-like models

            for w in word_ts:
                if "start_time" not in w and "start_offset" in w:
                    w["start_time"] = float(w["start_offset"]) * sec_per_frame
                if "end_time" not in w and "end_offset" in w:
                    w["end_time"]   = float(w["end_offset"])   * sec_per_frame

            self.finished.emit(word_ts)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            try:
                if os.path.exists(wav_path):
                    os.remove(wav_path)
            except Exception:
                pass


class CaptioningThread(QThread):
    finished = Signal(bool, str)  # success, message

    def __init__(self, video_path: str, words: List[Dict], font_path: str, output_path: str):
        super().__init__()
        self.video_path = video_path
        self.words = words
        self.font_path = font_path
        self.output_path = output_path

    # ---------------- Private helpers ----------------
    @staticmethod
    def _word_fontsize(word: str, video_height: int) -> Tuple[int, str]:
        """Return fontsize and size-key for a word based on rules."""
        # Decide size category: if the word is common, go smaller, else bigger.
        if word.lower() in AVOID_LIST:
            key = "small"
        elif len(word) > 6:
            key = "large"
        else:
            key = "medium"
        return _choose_font(key, video_height), key

    # --------------------------------------------------
    def run(self):
        try:
            _ensure_directories()
            info = _get_video_info(self.video_path)
            width, height = int(info["width"]), int(info["height"])

            draw_filters = []
            y_base = int(height * 0.66)  # bottom third start
            for idx, w in enumerate(self.words):
                word = w["word"].replace("'", "\u2019")  # avoid ffmpeg quote issues
                start = float(w.get("start_time", w.get("start_offset", 0)))
                end = float(w.get("end_time", w.get("end_offset", 0))) + 0.12  # hold word a bit longer
                fontsize, size_key = self._word_fontsize(word, height)

                # Shrink font if the word would exceed video width
                try:
                    max_width_px = width * 0.95  # small margin
                    while True:
                        font_obj = ImageFont.truetype(self.font_path, fontsize)
                        bbox = font_obj.getbbox(word)
                        text_width = bbox[2] - bbox[0]
                        if text_width <= max_width_px or fontsize <= 10:
                            break
                        fontsize -= 1
                except Exception:
                    # If PIL can't load the font, continue with chosen size
                    pass

                # y position – single line at bottom third (could be extended to multi-line)
                y_pos = y_base

                fade = 0.15
                alpha_expr = (
                    f"if(lt(t,{start}),0,"  # before start => invisible
                    f"if(lt(t,{start+fade}),(t-{start})/{fade},"  # fade-in
                    f"if(lt(t,{end-fade}),1,"  # fully visible
                    f"if(lt(t,{end}),({end}-t)/{fade},0))))"  # fade-out then invisible
                )

                draw = (
                    f"drawtext=fontfile='{self.font_path}':"
                    f"text='{word}':"
                    f"fontcolor=white:alpha='{alpha_expr}':"
                    f"fontsize={fontsize}:"
                    f"x=(w-text_w)/2:y={y_pos}:"
                    f"enable='between(t,{start},{end})'"
                )
                draw_filters.append(draw)

            vf = ",".join(draw_filters)
            cmd = [
                "ffmpeg", "-y", "-i", self.video_path,
                "-vf", vf,
                "-codec:a", "copy",
                self.output_path,
            ]
            subprocess.run(cmd, check=True)
            self.finished.emit(True, "Captioning complete.")
        except subprocess.CalledProcessError as e:
            self.finished.emit(False, e.stderr or "ffmpeg error")
        except Exception as exc:
            self.finished.emit(False, str(exc))


# -------------------------------------------------
# UI – Caption Tab
# -------------------------------------------------

class CaptionTab(QWidget):
    def __init__(self):
        super().__init__()
        _ensure_directories()

        self.video_map: Dict[str, str] = {}
        self.words: List[Dict] = []

        main_layout = QVBoxLayout(self)

        # Video selection
        video_layout = QHBoxLayout()
        video_layout.addWidget(QLabel("Select Clip:"))
        self.video_combo = QComboBox()
        video_layout.addWidget(self.video_combo)
        main_layout.addLayout(video_layout)

        # Font selection
        font_layout = QHBoxLayout()
        font_layout.addWidget(QLabel("Select Font:"))
        self.font_combo = QComboBox()
        font_layout.addWidget(self.font_combo)
        main_layout.addLayout(font_layout)

        # Transcript table (shows word + timings)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Word", "Start", "End"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # type: ignore[attr-defined]
        for col in (1, 2):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)  # type: ignore[attr-defined]
        main_layout.addWidget(self.table)

        # Buttons and progress
        actions = QHBoxLayout()
        self.transcribe_btn = QPushButton("Transcribe")
        self.caption_btn = QPushButton("Create Captions")
        self.caption_btn.setEnabled(False)
        actions.addWidget(self.transcribe_btn)
        actions.addWidget(self.caption_btn)
        main_layout.addLayout(actions)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        main_layout.addWidget(self.progress)

        # Connections
        self.transcribe_btn.clicked.connect(self._start_transcription)
        self.caption_btn.clicked.connect(self._start_captioning)

        # Populate combos
        self._populate_fonts()
        self._populate_videos()

    # --------------------------------------------------
    # Populate helpers
    # --------------------------------------------------
    def _populate_videos(self):
        self.video_combo.blockSignals(True)
        self.video_combo.clear()
        if os.path.isdir(CLIPS_DIR):
            videos = [os.path.join(CLIPS_DIR, f) for f in os.listdir(CLIPS_DIR) if f.lower().endswith((".mp4", ".mkv", ".avi", ".webm"))]
            self.video_combo.addItems([os.path.basename(v) for v in videos])
            self.video_map = {os.path.basename(v): v for v in videos}
        self.video_combo.blockSignals(False)

    def _populate_fonts(self):
        self.font_combo.clear()
        fonts = _font_candidates()
        for fpath in fonts:
            self.font_combo.addItem(os.path.basename(fpath), userData=fpath)

    # --------------------------------------------------
    # Transcription logic
    # --------------------------------------------------
    def _start_transcription(self):
        name = self.video_combo.currentText()
        if not name:
            QMessageBox.warning(self, "Warning", "Please select a clip.")
            return
        path = self.video_map[name]
        self.progress.setRange(0, 0)  # indefinite
        self.transcribe_btn.setEnabled(False)
        self.transcription_worker = TranscriptionThread(path)
        self.transcription_worker.finished.connect(self._on_transcription_finished)
        self.transcription_worker.error.connect(self._on_transcription_error)
        self.transcription_worker.start()

    def _on_transcription_error(self, msg: str):
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.transcribe_btn.setEnabled(True)
        QMessageBox.critical(self, "Error", f"Transcription failed: {msg}")

    def _on_transcription_finished(self, words: List[Dict]):
        self.words = words
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.transcribe_btn.setEnabled(True)
        self.caption_btn.setEnabled(True)

        # Populate table
        self.table.setRowCount(len(words))
        for row, w in enumerate(words):
            self.table.setItem(row, 0, QTableWidgetItem(w.get("word", "")))

            # NeMo 1.x uses 'start_time'/'end_time'; newer versions switched to 'start_offset'/'end_offset'.
            s = w.get("start_time", w.get("start_offset", 0))
            e = w.get("end_time", w.get("end_offset", 0))

            self.table.setItem(row, 1, QTableWidgetItem(f"{float(s):.2f}"))
            self.table.setItem(row, 2, QTableWidgetItem(f"{float(e):.2f}"))

    # --------------------------------------------------
    # Captioning logic
    # --------------------------------------------------
    def _start_captioning(self):
        if not self.words:
            QMessageBox.warning(self, "Warning", "No transcription available.")
            return
        name = self.video_combo.currentText()
        video_path = self.video_map[name]
        font_path = self.font_combo.currentData()
        base, ext = os.path.splitext(name)
        out_name = f"{base}_captioned{ext}"
        out_path = os.path.join(OUTPUT_DIR, out_name)

        self.caption_btn.setEnabled(False)
        self.progress.setRange(0, 0)

        self.caption_worker = CaptioningThread(video_path, self.words, font_path, out_path)
        self.caption_worker.finished.connect(self._on_captioning_finished)
        self.caption_worker.start()

    def _on_captioning_finished(self, success: bool, message: str):
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.caption_btn.setEnabled(True)
        if success:
            QMessageBox.information(self, "Success", message)
        else:
            QMessageBox.critical(self, "Error", message)


# Factory function for consistency with other tabs

def create_caption_tab() -> QWidget:
    return CaptionTab()