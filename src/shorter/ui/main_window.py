import sys
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QTabWidget,
    QWidget,
)

from shorter.ui.download_tab import create_download_tab
from shorter.ui.select_section_tab import create_select_section_tab
from shorter.ui.remove_silence_tab import create_remove_silence_tab
from shorter.ui.remove_chunks_tab import create_remove_chunks_tab


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Shorter")
        self.setGeometry(100, 100, 800, 600)
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self._create_tabs()

    def _create_tabs(self):
        # Download Tab
        self.download_tab = create_download_tab()
        self.select_section_tab = create_select_section_tab()
        self.remove_silence_tab = create_remove_silence_tab()
        self.remove_chunks_tab = create_remove_chunks_tab()

        self.tabs.addTab(self.download_tab, "Download")
        self.tabs.addTab(self.select_section_tab, "Select Section")
        self.tabs.addTab(self.remove_silence_tab, "Remove Silence")
        self.tabs.addTab(self.remove_chunks_tab, "Remove Chunks")

        # Pass refresh functions
        self.download_tab.add_refresh_target(self.select_section_tab.populate_videos)
        self.download_tab.add_refresh_target(self.remove_silence_tab.populate_videos)
        self.download_tab.add_refresh_target(self.remove_chunks_tab.populate_videos)

        self.select_section_tab.add_refresh_target(self.remove_silence_tab.populate_videos)
        self.select_section_tab.add_refresh_target(self.remove_chunks_tab.populate_videos)

        self.remove_silence_tab.add_refresh_target(self.select_section_tab.populate_videos)
        self.remove_silence_tab.add_refresh_target(self.remove_chunks_tab.populate_videos)

        self.remove_chunks_tab.add_refresh_target(self.select_section_tab.populate_videos)
        self.remove_chunks_tab.add_refresh_target(self.remove_silence_tab.populate_videos)

        def on_tab_changed(index):
            widget = self.tabs.widget(index)
            if hasattr(widget, 'populate_videos'):
                widget.populate_videos()

        self.tabs.currentChanged.connect(on_tab_changed)