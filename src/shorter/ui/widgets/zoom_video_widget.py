from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsRectItem
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtGui import QPen, QBrush, QColor, QPainter
from PySide6.QtCore import Qt, QRectF, Signal, QPointF

class ZoomVideoWidget(QGraphicsView):
    region_selected = Signal(QRectF)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        self.video_item = QGraphicsVideoItem()
        self.scene.addItem(self.video_item)

        self.setRenderHint(QPainter.Antialiasing)
        self.setOptimizationFlags(QGraphicsView.DontAdjustForAntialiasing)

        self.selection_rect_item = QGraphicsRectItem()
        self.selection_rect_item.setPen(QPen(Qt.GlobalColor.red, 2, Qt.PenStyle.DashLine))
        self.selection_rect_item.setBrush(Qt.NoBrush)
        self.scene.addItem(self.selection_rect_item)
        self.selection_rect_item.setVisible(False)

        self.start_pos = QPointF()
        self.is_drawing = False
        self.active_rect_item = QGraphicsRectItem()
        self.active_rect_item.setPen(QPen(QColor(255, 0, 0, 200), 2, Qt.PenStyle.SolidLine))
        self.active_rect_item.setBrush(Qt.NoBrush)
        self.scene.addItem(self.active_rect_item)
        self.active_rect_item.setVisible(False)

    def video_sink(self):
        return self.video_item.videoSink()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.active_rect_item.setVisible(False)
            self.start_pos = self.mapToScene(event.pos())
            self.is_drawing = True
            self.selection_rect_item.setRect(QRectF(self.start_pos, self.start_pos))
            self.selection_rect_item.setVisible(True)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.is_drawing:
            end_pos = self.mapToScene(event.pos())
            self.selection_rect_item.setRect(QRectF(self.start_pos, end_pos).normalized())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.is_drawing:
            self.is_drawing = False
            self.region_selected.emit(self.selection_rect_item.rect())
            self.selection_rect_item.setVisible(False)
        super().mouseReleaseEvent(event)

    def set_active_rect(self, rect):
        if rect.isNull():
            self.active_rect_item.setVisible(False)
        else:
            self.active_rect_item.setRect(rect)
            self.active_rect_item.setVisible(True)

    def set_video_size(self, size):
        self.video_item.setSize(size)
        self.scene.setSceneRect(self.video_item.boundingRect())
        self.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)