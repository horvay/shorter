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
from shorter.ui.zoom_tab import create_zoom_tab
from shorter.ui.extras_tab import create_extras_tab
from shorter.ui.caption_tab import create_caption_tab


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
        self.zoom_tab = create_zoom_tab()
        self.extras_tab = create_extras_tab()
        self.caption_tab = create_caption_tab()

        self.tabs.addTab(self.download_tab, "1. Download")
        self.tabs.addTab(self.select_section_tab, "2. Select Section")
        self.tabs.addTab(self.remove_silence_tab, "3. Remove Silence")
        self.tabs.addTab(self.remove_chunks_tab, "4. Remove Chunks")
        self.tabs.addTab(self.zoom_tab, "5. Zoom & Pan")
        self.tabs.addTab(self.caption_tab, "6. Caption")
        self.tabs.addTab(self.extras_tab, "Extras")

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

        # Setup cross-tab refresh
        all_tabs = [
            self.download_tab, self.select_section_tab, self.remove_silence_tab,
            self.remove_chunks_tab, self.zoom_tab, self.extras_tab, self.caption_tab
        ]

        for source_tab in all_tabs:
            for target_tab in all_tabs:
                if source_tab != target_tab and hasattr(target_tab, 'populate_videos'):
                    if hasattr(source_tab, 'add_refresh_target'):
                        source_tab.add_refresh_target(target_tab.populate_videos)

        def on_tab_changed(index):
            widget = self.tabs.widget(index)
            if hasattr(widget, 'populate_videos'):
                widget.populate_videos()

        self.tabs.currentChanged.connect(on_tab_changed)