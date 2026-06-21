import sys
import math
import random
import json
import time
from pathlib import Path
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, QRect, QEasingCurve, QPropertyAnimation, QEvent
from PySide6.QtGui import (
    QColor,
    QPainter,
    QPen,
    QBrush,
    QFont,
    QLinearGradient,
    QRadialGradient,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QPushButton,
    QLabel,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QScrollArea,
    QCheckBox,
    QProgressBar,
    QGraphicsOpacityEffect,
)

from ui_state import read_ui_state, close_widget, read_chat_history

try:
    import psutil
except Exception:
    psutil = None


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
TODO_PATH = DATA_DIR / "todo.json"


def load_todo_tasks():
    if not TODO_PATH.exists():
        return []

    try:
        with open(TODO_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return []

    if isinstance(payload, dict):
        tasks = payload.get("tasks", [])
    else:
        tasks = payload

    if not isinstance(tasks, list):
        return []

    return tasks


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()

        if widget:
            widget.setParent(None)
            widget.deleteLater()


def safe_percent(value):
    try:
        return max(0, min(100, int(round(float(value)))))
    except Exception:
        return 0


class HudWidgetPanel(QFrame):
    """
    Base floating HUD widget panel.
    Handles frame painting, drag movement, close action, and open/close animation.
    """

    WIDTH = 430
    HEIGHT = 360

    def __init__(self, widget_payload, parent=None):
        super().__init__(parent)

        self.widget_payload = widget_payload or {}
        self.widget_id = self.widget_payload.get("widget_id", "")
        self.widget_type = self.widget_payload.get("widget_type", "")
        self.title = self.widget_payload.get("title", self.widget_type).upper()
        self.user_moved = False
        self.drag_offset = None
        self._animations = []

        self.setObjectName("hudFloatingWidget")
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setAutoFillBackground(False)
        self.setMouseTracking(True)
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.setStyleSheet("#hudFloatingWidget { background: transparent; border: none; }")

        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self.opacity_effect)

        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(18, 12, 18, 16)
        self.root_layout.setSpacing(10)

        self.title_bar = QFrame(self)
        self.title_bar.setFixedHeight(34)
        self.title_bar.setCursor(Qt.SizeAllCursor)
        self.title_bar.installEventFilter(self)

        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(8)

        self.title_label = QLabel(self.title, self.title_bar)
        self.title_label.setStyleSheet(
            "color: rgba(150, 225, 238, 235);"
            "font-family: Consolas;"
            "font-size: 14px;"
            "font-weight: 800;"
            "letter-spacing: 3px;"
            "background: transparent;"
        )
        self.title_label.installEventFilter(self)

        self.close_btn = QPushButton("X", self.title_bar)
        self.close_btn.setFixedSize(28, 24)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(10, 28, 38, 210);
                color: rgba(150, 225, 238, 230);
                border: 1px solid rgba(82, 180, 200, 145);
                border-radius: 0px;
                font-size: 11px;
                font-weight: 800;
            }
            QPushButton:hover {
                background-color: rgba(42, 105, 125, 230);
                border: 1px solid rgba(165, 238, 248, 230);
            }
        """)
        self.close_btn.clicked.connect(self.request_close)

        title_layout.addWidget(self.title_label)
        title_layout.addStretch(1)
        title_layout.addWidget(self.close_btn)

        self.content_frame = QFrame(self)
        self.content_frame.setStyleSheet("background: transparent;")
        self.content_layout = QVBoxLayout(self.content_frame)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(8)

        self.root_layout.addWidget(self.title_bar)
        self.root_layout.addWidget(self.content_frame, 1)

        self.populate_content()

    def request_close(self):
        close_widget(self.widget_id)

    def set_payload(self, widget_payload):
        self.widget_payload = widget_payload or {}
        self.title = self.widget_payload.get("title", self.title).upper()
        self.title_label.setText(self.title)
        self.populate_content()

    def label(self, text, size=10, alpha=190, bold=False, align=Qt.AlignLeft):
        label = QLabel(str(text or ""), self)
        label.setWordWrap(True)
        label.setAlignment(align)
        label.setStyleSheet(
            f"color: rgba(132, 210, 224, {alpha});"
            "font-family: Consolas;"
            f"font-size: {size}px;"
            f"font-weight: {'800' if bold else '500'};"
            "background: transparent;"
        )
        return label

    def populate_content(self):
        clear_layout(self.content_layout)
        content = self.widget_payload.get("content", {})

        if isinstance(content, (dict, list)):
            text = json.dumps(content, indent=2)
        else:
            text = str(content or "No content.")

        self.content_layout.addWidget(self.label(text, size=10, alpha=175))
        self.content_layout.addStretch(1)

    def refresh_dynamic_content(self):
        return

    def animate_to_geometry(self, target_rect, duration=360):
        if self.user_moved:
            return

        animation = QPropertyAnimation(self, b"geometry", self)
        animation.setDuration(duration)
        animation.setStartValue(self.geometry())
        animation.setEndValue(target_rect)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.start()
        self._animations.append(animation)

    def animate_in(self, target_rect):
        start_rect = QRect(
            target_rect.x(),
            target_rect.y() + 28,
            target_rect.width(),
            target_rect.height(),
        )
        self.setGeometry(start_rect)
        self.show()

        geometry_animation = QPropertyAnimation(self, b"geometry", self)
        geometry_animation.setDuration(360)
        geometry_animation.setStartValue(start_rect)
        geometry_animation.setEndValue(target_rect)
        geometry_animation.setEasingCurve(QEasingCurve.OutCubic)

        opacity_animation = QPropertyAnimation(self.opacity_effect, b"opacity", self)
        opacity_animation.setDuration(320)
        opacity_animation.setStartValue(0.0)
        opacity_animation.setEndValue(1.0)
        opacity_animation.setEasingCurve(QEasingCurve.OutCubic)

        geometry_animation.start()
        opacity_animation.start()
        self._animations.extend([geometry_animation, opacity_animation])

    def animate_out(self):
        end_rect = QRect(
            self.x(),
            self.y() + 26,
            self.width(),
            self.height(),
        )

        geometry_animation = QPropertyAnimation(self, b"geometry", self)
        geometry_animation.setDuration(260)
        geometry_animation.setStartValue(self.geometry())
        geometry_animation.setEndValue(end_rect)
        geometry_animation.setEasingCurve(QEasingCurve.InCubic)

        opacity_animation = QPropertyAnimation(self.opacity_effect, b"opacity", self)
        opacity_animation.setDuration(240)
        opacity_animation.setStartValue(self.opacity_effect.opacity())
        opacity_animation.setEndValue(0.0)
        opacity_animation.setEasingCurve(QEasingCurve.InCubic)
        opacity_animation.finished.connect(self.deleteLater)

        geometry_animation.start()
        opacity_animation.start()
        self._animations.extend([geometry_animation, opacity_animation])

    def eventFilter(self, watched, event):
        if watched in {self.title_bar, self.title_label}:
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self.drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                self.user_moved = True
                return True

            if event.type() == QEvent.MouseMove and self.drag_offset:
                self.move(event.globalPosition().toPoint() - self.drag_offset)
                return True

            if event.type() == QEvent.MouseButtonRelease:
                self.drag_offset = None
                return True

        return super().eventFilter(watched, event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(1, 1, -2, -2)
        painter.setPen(QPen(QColor(80, 180, 200, 140), 1.4))
        painter.setBrush(QBrush(QColor(5, 13, 18, 225)))
        painter.drawRect(rect)

        painter.setPen(QPen(QColor(150, 230, 242, 180), 2))
        corner = 28
        painter.drawLine(rect.left(), rect.top(), rect.left() + corner, rect.top())
        painter.drawLine(rect.left(), rect.top(), rect.left(), rect.top() + corner)
        painter.drawLine(rect.right(), rect.top(), rect.right() - corner, rect.top())
        painter.drawLine(rect.right(), rect.top(), rect.right(), rect.top() + corner)
        painter.drawLine(rect.left(), rect.bottom(), rect.left() + corner, rect.bottom())
        painter.drawLine(rect.left(), rect.bottom(), rect.left(), rect.bottom() - corner)
        painter.drawLine(rect.right(), rect.bottom(), rect.right() - corner, rect.bottom())
        painter.drawLine(rect.right(), rect.bottom(), rect.right(), rect.bottom() - corner)

        painter.setPen(QPen(QColor(255, 255, 255, 10), 1))
        for y in range(8, self.height(), 7):
            painter.drawLine(2, y, self.width() - 2, y)


class TodoWidget(HudWidgetPanel):
    def populate_content(self):
        clear_layout(self.content_layout)
        tasks = load_todo_tasks()

        if not tasks:
            self.content_layout.addWidget(
                self.label("No tasks yet.", size=12, alpha=175, align=Qt.AlignCenter)
            )
            self.content_layout.addStretch(1)
            return

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        container = QWidget(scroll)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(8)

        for task in tasks:
            checkbox = QCheckBox(str(task.get("text", "Untitled task")), container)
            checkbox.setChecked(bool(task.get("done")))
            checkbox.setEnabled(False)
            checkbox.setStyleSheet("""
                QCheckBox {
                    color: rgba(145, 220, 232, 210);
                    font-family: Consolas;
                    font-size: 11px;
                    spacing: 9px;
                    background: transparent;
                }
                QCheckBox::indicator {
                    width: 15px;
                    height: 15px;
                    border: 1px solid rgba(100, 205, 225, 180);
                    background: rgba(3, 18, 25, 190);
                }
                QCheckBox::indicator:checked {
                    background: rgba(105, 225, 235, 210);
                }
            """)
            layout.addWidget(checkbox)

        layout.addStretch(1)
        scroll.setWidget(container)
        self.content_layout.addWidget(scroll)

    def refresh_dynamic_content(self):
        self.populate_content()


class ChatWidget(HudWidgetPanel):
    def populate_content(self):
        clear_layout(self.content_layout)
        content = self.widget_payload.get("content", {})

        if isinstance(content, dict):
            messages = content.get("messages") or read_chat_history(limit=10)
        else:
            messages = read_chat_history(limit=10)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        container = QWidget(scroll)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(9)

        if not messages:
            layout.addWidget(self.label("No conversation captured yet.", size=11, alpha=165))
        else:
            for message in messages[-10:]:
                role = str(message.get("role", "jarvis")).lower()
                text = str(message.get("text", "")).strip()
                timestamp = str(message.get("timestamp", ""))[11:19]
                align = Qt.AlignRight if role == "user" else Qt.AlignLeft
                prefix = "YOU" if role == "user" else "JARVIS"

                bubble = self.label(f"{prefix} // {timestamp}\n{text}", size=10, alpha=210, align=align)
                bubble.setStyleSheet(
                    bubble.styleSheet()
                    + (
                        "padding: 8px;"
                        "border: 1px solid rgba(70, 165, 185, 90);"
                        "background-color: rgba(7, 24, 32, 155);"
                    )
                )
                layout.addWidget(bubble)

        layout.addStretch(1)
        scroll.setWidget(container)
        self.content_layout.addWidget(scroll)

    def refresh_dynamic_content(self):
        self.widget_payload["content"] = {"messages": read_chat_history(limit=10)}
        self.populate_content()


class SystemWidget(HudWidgetPanel):
    def __init__(self, widget_payload, parent=None):
        super().__init__(widget_payload, parent)
        self.system_timer = QTimer(self)
        self.system_timer.timeout.connect(self.refresh_dynamic_content)
        self.system_timer.start(5000)

    def _bar(self, label, value):
        row = QWidget(self)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        name = self.label(label, size=10, alpha=190, bold=True)
        name.setFixedWidth(78)

        bar = QProgressBar(row)
        bar.setRange(0, 100)
        bar.setValue(safe_percent(value))
        bar.setTextVisible(True)
        bar.setFormat(f"{safe_percent(value)}%")
        bar.setStyleSheet("""
            QProgressBar {
                background-color: rgba(3, 18, 25, 190);
                border: 1px solid rgba(60, 150, 170, 130);
                color: rgba(165, 235, 245, 210);
                font-family: Consolas;
                font-size: 10px;
                text-align: center;
                height: 18px;
            }
            QProgressBar::chunk {
                background-color: rgba(85, 210, 228, 180);
            }
        """)

        layout.addWidget(name)
        layout.addWidget(bar, 1)
        return row

    def populate_content(self):
        clear_layout(self.content_layout)

        if not psutil:
            self.content_layout.addWidget(self.label("System telemetry unavailable.", size=11, alpha=175))
            self.content_layout.addStretch(1)
            return

        cpu = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory().percent
        disk = psutil.disk_usage(str(BASE_DIR.anchor or "C:\\")).percent
        battery = psutil.sensors_battery()
        battery_value = battery.percent if battery else None

        self.content_layout.addWidget(self._bar("CPU", cpu))
        self.content_layout.addWidget(self._bar("RAM", ram))
        self.content_layout.addWidget(self._bar("DISK", disk))

        if battery_value is not None:
            self.content_layout.addWidget(self._bar("BATTERY", battery_value))
        else:
            self.content_layout.addWidget(self.label("BATTERY // not detected", size=10, alpha=155))

        self.content_layout.addStretch(1)

    def refresh_dynamic_content(self):
        self.populate_content()


class SpotifyWidget(HudWidgetPanel):
    def populate_content(self):
        clear_layout(self.content_layout)
        content = self.widget_payload.get("content", {})
        content = content if isinstance(content, dict) else {}

        track = content.get("track") or "Spotify not detected"
        artist = content.get("artist") or "Open Spotify to show playback here"
        progress = safe_percent(content.get("progress", 0))

        album = QLabel("", self)
        album.setFixedSize(118, 118)
        album.setStyleSheet("""
            QLabel {
                background-color: rgba(7, 24, 32, 190);
                border: 1px solid rgba(90, 190, 210, 130);
            }
        """)
        album.setAlignment(Qt.AlignCenter)
        album.setText("ALBUM\nART")
        album.setStyleSheet(album.styleSheet() + "color: rgba(120, 205, 220, 150); font-family: Consolas;")

        info = QWidget(self)
        info_layout = QVBoxLayout(info)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(8)
        info_layout.addWidget(self.label(track, size=14, alpha=230, bold=True))
        info_layout.addWidget(self.label(artist, size=10, alpha=175))
        info_layout.addStretch(1)

        top = QWidget(self)
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(14)
        top_layout.addWidget(album)
        top_layout.addWidget(info, 1)

        progress_bar = QProgressBar(self)
        progress_bar.setRange(0, 100)
        progress_bar.setValue(progress)
        progress_bar.setTextVisible(False)
        progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: rgba(3, 18, 25, 190);
                border: 1px solid rgba(60, 150, 170, 130);
                height: 10px;
            }
            QProgressBar::chunk {
                background-color: rgba(90, 218, 232, 180);
            }
        """)

        controls = QWidget(self)
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(10)

        for text in ["PREV", "PLAY", "NEXT"]:
            button = QPushButton(text, controls)
            button.setEnabled(False)
            button.setFixedHeight(30)
            button.setStyleSheet("""
                QPushButton {
                    background-color: rgba(8, 28, 38, 170);
                    color: rgba(145, 220, 232, 160);
                    border: 1px solid rgba(70, 165, 185, 90);
                    border-radius: 0px;
                    font-family: Consolas;
                    font-weight: 800;
                }
            """)
            controls_layout.addWidget(button)

        self.content_layout.addWidget(top)
        self.content_layout.addWidget(progress_bar)
        self.content_layout.addWidget(controls)
        self.content_layout.addWidget(
            self.label("Playback controls are ready for a future Spotify integration.", size=9, alpha=130)
        )
        self.content_layout.addStretch(1)


WIDGET_CLASSES = {
    "todo": TodoWidget,
    "chat": ChatWidget,
    "system": SystemWidget,
    "spotify": SpotifyWidget,
}


class JarvisHUD(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("J.A.R.V.I.S")
        self.setObjectName("jarvisRoot")
        self.setMinimumSize(1200, 760)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)

        self.t = 0.0
        self.frame_delta = 0.02
        self.last_tick_time = time.perf_counter()
        self.status = "STANDBY"
        self.sub_status = "Awaiting wake phrase"
        self.detail = ""

        self.wave_values = [random.random() for _ in range(72)]
        self.particles = [
            {
                "x": random.random(),
                "y": random.random(),
                "speed": random.uniform(0.0005, 0.0018),
                "size": random.uniform(0.8, 2.4),
                "alpha": random.randint(20, 90),
            }
            for _ in range(70)
        ]

        self.orb_position = "center"
        self.orb_x = None
        self.orb_y = None
        self.orb_r = None
        self.painted_widgets = {}
        self.widget_order = []
        self.widget_payload_signatures = {}
        self.widget_rects = {}
        self.widget_target_rects = {}
        self.widget_opacity = {}
        self.widget_closing = set()
        self.widget_manual_positions = set()
        self.drag_widget_id = None
        self.drag_widget_offset = QPointF(0, 0)
        self.system_cache = {}
        self.system_cache_updated_at = 0.0

        self.drag_position = None
        self.is_dragging_window = False

        self.setup_controls()

        self.paint_timer = QTimer(self)
        self.paint_timer.timeout.connect(self.tick)
        self.paint_timer.start(20)

        self.state_timer = QTimer(self)
        self.state_timer.timeout.connect(self.refresh_external_state)
        self.state_timer.start(250)

        self.refresh_external_state()

        self.showFullScreen()

    def setup_controls(self):
        self.title_label = QLabel("J.A.R.V.I.S", self)
        self.title_label.setStyleSheet("""
            QLabel {
                color: rgba(118, 195, 210, 235);
                font-size: 40px;
                font-weight: 800;
                letter-spacing: 11px;
                background: transparent;
            }
        """)
        self.title_label.setAlignment(Qt.AlignCenter)

        self.status_label = QLabel(self.status, self)
        self.status_label.setStyleSheet("""
            QLabel {
                color: rgba(150, 220, 230, 230);
                font-size: 20px;
                font-weight: 700;
                letter-spacing: 4px;
                background: transparent;
            }
        """)
        self.status_label.setAlignment(Qt.AlignCenter)

        self.sub_status_label = QLabel(self.sub_status, self)
        self.sub_status_label.setStyleSheet("""
            QLabel {
                color: rgba(105, 165, 180, 185);
                font-size: 13px;
                background: transparent;
            }
        """)
        self.sub_status_label.setAlignment(Qt.AlignCenter)

        self.detail_label = QLabel("", self)
        self.detail_label.setStyleSheet("""
            QLabel {
                color: rgba(88, 150, 165, 150);
                font-size: 11px;
                background: transparent;
            }
        """)
        self.detail_label.setAlignment(Qt.AlignCenter)

        button_style = """
            QPushButton {
                background-color: rgba(7, 18, 25, 205);
                color: rgba(135, 220, 235, 235);
                border: 1px solid rgba(60, 120, 140, 145);
                border-radius: 8px;
                font-size: 14px;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: rgba(22, 48, 63, 220);
                border: 1px solid rgba(125, 215, 230, 220);
            }
            QPushButton:pressed {
                background-color: rgba(80, 150, 170, 210);
                color: rgba(3, 10, 15, 255);
            }
        """

        self.min_btn = QPushButton("—", self)
        self.max_btn = QPushButton("□", self)
        self.close_btn = QPushButton("×", self)

        for btn in [self.min_btn, self.max_btn, self.close_btn]:
            btn.setFixedSize(42, 34)
            btn.setStyleSheet(button_style)
            btn.setCursor(Qt.PointingHandCursor)

        self.min_btn.clicked.connect(self.showMinimized)
        self.max_btn.clicked.connect(self.toggle_fullscreen)
        self.close_btn.clicked.connect(self.close)

    def resizeEvent(self, event):
        w = self.width()
        h = self.height()

        self.title_label.setGeometry(0, 50, w, 52)
        self.status_label.setGeometry(0, h - 145, w, 34)
        self.sub_status_label.setGeometry(0, h - 113, w, 24)
        self.detail_label.setGeometry(0, h - 88, w, 22)

        margin = 22
        y = 20
        self.close_btn.move(w - margin - 42, y)
        self.max_btn.move(w - margin - 42 * 2 - 10, y)
        self.min_btn.move(w - margin - 42 * 3 - 20, y)

        self.layout_widgets(animated=False)

    def tick(self):
        now = time.perf_counter()
        self.frame_delta = max(0.008, min(0.05, now - self.last_tick_time))
        self.last_tick_time = now
        self.t += self.frame_delta

        for i in range(len(self.wave_values)):
            base = 0.16 + 0.26 * abs(math.sin(self.t * 2.0 + i * 0.18))
            spike = 0.18 * abs(math.sin(self.t * 3.4 + i * 0.37))
            target = base + spike + random.uniform(-0.03, 0.03)
            self.wave_values[i] = self.wave_values[i] * 0.9 + target * 0.1

        for p in self.particles:
            p["y"] -= p["speed"]
            if p["y"] < -0.03:
                p["x"] = random.random()
                p["y"] = 1.03

        self.update_orb_motion()
        self.update_widget_motion()

        self.update()

    def refresh_external_state(self):
        state = read_ui_state()

        self.status = state.get("status", "STANDBY")
        self.sub_status = state.get("sub_status", "Awaiting wake phrase")
        self.detail = state.get("detail", "")
        active_widgets = state.get("active_widgets", [])
        requested_orb_position = state.get("orb_position", "center")

        self.orb_position = "corner" if active_widgets else requested_orb_position

        self.status_label.setText(self.status)
        self.sub_status_label.setText(self.sub_status)
        self.detail_label.setText(self.detail)

        self.sync_widgets(active_widgets)

    def target_orb_geometry(self):
        w = self.width()
        h = self.height()

        if self.orb_position == "corner":
            radius = max(42, min(w, h) * 0.048)
            return w - radius * 1.9, h - radius * 1.85, radius

        return w / 2, h / 2 + 8, min(w, h) * 0.14

    def update_orb_motion(self):
        target_x, target_y, target_r = self.target_orb_geometry()

        if self.orb_x is None:
            self.orb_x = target_x
            self.orb_y = target_y
            self.orb_r = target_r
            return

        # Eased interpolation gives the orb a smooth 300-400ms travel time
        # without introducing a separate animation object into the paint loop.
        ease = max(0.08, min(0.24, self.frame_delta * 7.0))
        self.orb_x += (target_x - self.orb_x) * ease
        self.orb_y += (target_y - self.orb_y) * ease
        self.orb_r += (target_r - self.orb_r) * ease

    def sync_widgets(self, widget_payloads):
        widget_payloads = widget_payloads if isinstance(widget_payloads, list) else []
        incoming_ids = {
            payload.get("widget_id")
            for payload in widget_payloads
            if isinstance(payload, dict) and payload.get("widget_id")
        }

        for widget_id in list(self.painted_widgets.keys()):
            if widget_id not in incoming_ids:
                self.widget_closing.add(widget_id)
                self.widget_payload_signatures.pop(widget_id, None)

        ordered_payloads = []

        for payload in widget_payloads:
            if not isinstance(payload, dict):
                continue

            widget_id = payload.get("widget_id")
            widget_type = payload.get("widget_type")

            if not widget_id:
                continue

            ordered_payloads.append(payload)
            signature = self.payload_signature(payload)

            if widget_id in self.painted_widgets:
                self.painted_widgets[widget_id] = payload
                self.widget_payload_signatures[widget_id] = signature
                self.widget_closing.discard(widget_id)
                continue

            self.painted_widgets[widget_id] = payload
            self.widget_payload_signatures[widget_id] = signature
            self.widget_opacity[widget_id] = 0.0
            self.widget_closing.discard(widget_id)

        self.widget_order = [
            payload.get("widget_id")
            for payload in ordered_payloads
            if payload.get("widget_id")
        ]

        self.layout_widgets(animated=True)

    def payload_signature(self, payload):
        try:
            return json.dumps(payload, sort_keys=True, default=str)
        except Exception:
            return str(payload)

    def layout_widgets(self, animated=True, new_widgets=None):
        active_widget_ids = [
            widget_id for widget_id in self.widget_order
            if widget_id in self.painted_widgets and widget_id not in self.widget_closing
        ]

        if not active_widget_ids:
            return

        rects = self.default_widget_rects(len(active_widget_ids))

        for index, widget_id in enumerate(active_widget_ids):
            if widget_id in self.widget_manual_positions:
                continue

            target_rect = rects[min(index, len(rects) - 1)]
            target = QRectF(target_rect)
            self.widget_target_rects[widget_id] = target

            if widget_id not in self.widget_rects or not animated:
                start = QRectF(target)
                start.translate(0, 28 if animated else 0)
                self.widget_rects[widget_id] = start

    def update_widget_motion(self):
        for widget_id in list(self.painted_widgets.keys()):
            closing = widget_id in self.widget_closing
            current_opacity = self.widget_opacity.get(widget_id, 0.0)
            target_opacity = 0.0 if closing else 1.0
            opacity_ease = max(0.10, min(0.28, self.frame_delta * 8.0))
            self.widget_opacity[widget_id] = current_opacity + (target_opacity - current_opacity) * opacity_ease

            current_rect = self.widget_rects.get(widget_id)
            target_rect = self.widget_target_rects.get(widget_id, current_rect)

            if current_rect and target_rect and widget_id not in self.widget_manual_positions:
                ease = max(0.10, min(0.26, self.frame_delta * 7.5))
                self.widget_rects[widget_id] = QRectF(
                    current_rect.x() + (target_rect.x() - current_rect.x()) * ease,
                    current_rect.y() + (target_rect.y() - current_rect.y()) * ease,
                    current_rect.width() + (target_rect.width() - current_rect.width()) * ease,
                    current_rect.height() + (target_rect.height() - current_rect.height()) * ease,
                )

            if closing and self.widget_opacity.get(widget_id, 0.0) < 0.03:
                self.painted_widgets.pop(widget_id, None)
                self.widget_rects.pop(widget_id, None)
                self.widget_target_rects.pop(widget_id, None)
                self.widget_opacity.pop(widget_id, None)
                self.widget_closing.discard(widget_id)
                self.widget_manual_positions.discard(widget_id)

    def default_widget_rects(self, count):
        w = self.width()
        h = self.height()
        panel_w = HudWidgetPanel.WIDTH
        panel_h = HudWidgetPanel.HEIGHT
        center_x = w // 2
        center_y = h // 2
        gap = 28

        if count <= 1:
            return [QRect(center_x - panel_w // 2, center_y - panel_h // 2, panel_w, panel_h)]

        if count == 2:
            return [
                QRect(center_x - panel_w - gap // 2, center_y - panel_h // 2, panel_w, panel_h),
                QRect(center_x + gap // 2, center_y - panel_h // 2, panel_w, panel_h),
            ]

        if count == 3:
            return [
                QRect(center_x - panel_w // 2, center_y - panel_h - gap // 2, panel_w, panel_h),
                QRect(center_x - panel_w - gap // 2, center_y + gap // 2, panel_w, panel_h),
                QRect(center_x + gap // 2, center_y + gap // 2, panel_w, panel_h),
            ]

        cols = 2 if count <= 4 else 3
        rows = math.ceil(count / cols)
        total_w = cols * panel_w + (cols - 1) * gap
        total_h = rows * panel_h + (rows - 1) * gap
        start_x = center_x - total_w // 2
        start_y = center_y - total_h // 2
        rects = []

        for index in range(count):
            col = index % cols
            row = index // cols
            rects.append(
                QRect(
                    start_x + col * (panel_w + gap),
                    start_y + row * (panel_h + gap),
                    panel_w,
                    panel_h,
                )
            )

        return rects

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F11:
            self.toggle_fullscreen()
        elif event.key() == Qt.Key_Escape:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.close()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            point = event.position()

            for widget_id in reversed(self.active_painted_widget_ids()):
                rect = self.widget_rects.get(widget_id)

                if not rect:
                    continue

                if self.widget_close_rect(rect).contains(point):
                    close_widget(widget_id)
                    return

                if self.widget_title_rect(rect).contains(point):
                    self.drag_widget_id = widget_id
                    self.drag_widget_offset = QPointF(point.x() - rect.x(), point.y() - rect.y())
                    self.widget_manual_positions.add(widget_id)
                    return

            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.is_dragging_window = True

            if self.paint_timer.isActive():
                self.paint_timer.stop()

    def mouseMoveEvent(self, event):
        if self.drag_widget_id:
            point = event.position()
            rect = self.widget_rects.get(self.drag_widget_id)

            if rect:
                new_rect = QRectF(
                    point.x() - self.drag_widget_offset.x(),
                    point.y() - self.drag_widget_offset.y(),
                    rect.width(),
                    rect.height(),
                )
                self.widget_rects[self.drag_widget_id] = new_rect
                self.widget_target_rects[self.drag_widget_id] = QRectF(new_rect)
                self.update()
            return

        if self.drag_position and not self.isFullScreen():
            self.move(event.globalPosition().toPoint() - self.drag_position)

    def mouseReleaseEvent(self, event):
        self.drag_widget_id = None
        self.drag_position = None
        self.is_dragging_window = False

        if not self.paint_timer.isActive():
            self.paint_timer.start(20)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        self.draw_background(painter, w, h)
        self.draw_grid(painter, w, h)
        self.draw_particles(painter, w, h)
        self.draw_top_bar(painter, w, h)
        self.draw_corner_hud(painter, w, h)
        self.draw_side_panels(painter, w, h)
        self.draw_orb_core(painter, w, h)
        self.draw_waveform(painter, w, h)
        self.draw_widget_panels(painter, w, h)
        self.draw_bottom_strip(painter, w, h)
        self.draw_scanlines(painter, w, h)

    def draw_background(self, painter, w, h):
        grad = QLinearGradient(0, 0, w, h)
        grad.setColorAt(0.0, QColor(1, 4, 8))
        grad.setColorAt(0.35, QColor(2, 9, 14))
        grad.setColorAt(0.7, QColor(3, 14, 20))
        grad.setColorAt(1.0, QColor(1, 3, 6))
        painter.fillRect(0, 0, w, h, grad)

        radial = QRadialGradient(QPointF(w / 2, h / 2), min(w, h) * 0.64)
        radial.setColorAt(0.0, QColor(35, 95, 115, 20))
        radial.setColorAt(0.4, QColor(14, 45, 60, 12))
        radial.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(0, 0, w, h, radial)

    def draw_grid(self, painter, w, h):
        painter.save()
        pen = QPen(QColor(42, 95, 115, 20), 1)
        painter.setPen(pen)

        spacing = 58
        offset = int((self.t * 14) % spacing)

        for x in range(-spacing, w + spacing, spacing):
            painter.drawLine(x + offset, 0, x + offset, h)

        for y in range(-spacing, h + spacing, spacing):
            painter.drawLine(0, y + offset, w, y + offset)

        painter.restore()

    def draw_particles(self, painter, w, h):
        painter.save()
        for p in self.particles:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(92, 168, 182, p["alpha"])))
            painter.drawEllipse(QPointF(p["x"] * w, p["y"] * h), p["size"], p["size"])
        painter.restore()

    def draw_top_bar(self, painter, w, h):
        painter.save()

        rect = QRectF(45, 42, w - 90, 52)
        painter.setPen(QPen(QColor(55, 120, 138, 85), 1.2))
        painter.setBrush(QBrush(QColor(4, 16, 24, 105)))
        painter.drawRoundedRect(rect, 14, 14)

        painter.setFont(QFont("Consolas", 10, QFont.Bold))
        painter.setPen(QPen(QColor(120, 196, 210, 180), 1))
        painter.drawText(QRectF(65, 57, 240, 22), Qt.AlignLeft, "J.A.R.V.I.S // LOCAL CORE")

        painter.setFont(QFont("Consolas", 9))
        painter.setPen(QPen(QColor(92, 155, 170, 145), 1))
        painter.drawText(QRectF(w - 350, 57, 260, 22), Qt.AlignRight, datetime.now().strftime("%A  %d %b %Y  //  %I:%M:%S %p"))

        painter.restore()

    def draw_corner_hud(self, painter, w, h):
        painter.save()

        pen = QPen(QColor(70, 155, 175, 110), 2)
        painter.setPen(pen)

        gap = 22
        length = 105

        painter.drawLine(gap, gap, gap + length, gap)
        painter.drawLine(gap, gap, gap, gap + length)

        painter.drawLine(w - gap, gap, w - gap - length, gap)
        painter.drawLine(w - gap, gap, w - gap, gap + length)

        painter.drawLine(gap, h - gap, gap + length, h - gap)
        painter.drawLine(gap, h - gap, gap, h - gap - length)

        painter.drawLine(w - gap, h - gap, w - gap - length, h - gap)
        painter.drawLine(w - gap, h - gap, w - gap, h - gap - length)

        painter.setPen(QPen(QColor(52, 110, 128, 52), 1))
        painter.drawRect(36, 36, w - 72, h - 72)
        painter.drawRect(50, 50, w - 100, h - 100)

        painter.restore()

    def draw_side_panels(self, painter, w, h):
        painter.save()

        panel_w = 265
        panel_h = 285
        top = h / 2 - panel_h / 2

        left_rows = [
            "VOICE LINK       ONLINE",
            "MEMORY STACK     READY",
            "VISION LAYER     READY",
            "ROUTER MODE      HYBRID",
            "LOCAL TOOLS      STABLE",
        ]

        right_rows = [
            f"TIME             {datetime.now().strftime('%I:%M:%S %p')}",
            f"STATE            {self.status}",
            "WAKE WORD        HEY JARVIS",
            "TTS ENGINE       KOKORO",
            "MODEL            GPT-4O-MINI",
        ]

        self.draw_panel(painter, 58, top, panel_w, panel_h, "CORE SYSTEMS", left_rows)
        self.draw_panel(painter, w - 58 - panel_w, top, panel_w, panel_h, "LIVE TELEMETRY", right_rows)

        painter.restore()

    def draw_panel(self, painter, x, y, width, height, title, rows):
        rect = QRectF(x, y, width, height)

        painter.setPen(QPen(QColor(52, 120, 138, 105), 1.4))
        painter.setBrush(QBrush(QColor(4, 18, 27, 115)))
        painter.drawRoundedRect(rect, 18, 18)

        painter.setPen(QPen(QColor(115, 196, 210, 195), 1))
        painter.setFont(QFont("Consolas", 11, QFont.Bold))
        painter.drawText(QRectF(x + 18, y + 16, width - 36, 25), Qt.AlignLeft, title)

        painter.setPen(QPen(QColor(52, 120, 138, 70), 1))
        painter.drawLine(x + 18, y + 48, x + width - 18, y + 48)

        painter.setFont(QFont("Consolas", 9))
        start_y = y + 72

        for i, row in enumerate(rows):
            alpha = 125 + int(35 * abs(math.sin(self.t * 1.5 + i)))
            painter.setPen(QPen(QColor(108, 180, 194, alpha), 1))
            painter.drawText(QRectF(x + 18, start_y + i * 34, width - 36, 22), Qt.AlignLeft, row)

            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(74, 170, 185, 70)))
            painter.drawEllipse(QPointF(x + width - 28, start_y + i * 34 + 9), 3, 3)

    def draw_orb_core(self, painter, w, h):
        painter.save()

        if self.orb_x is None:
            self.update_orb_motion()

        cx = self.orb_x or w / 2
        cy = self.orb_y or h / 2
        base_r = self.orb_r or min(w, h) * 0.14
        status = self.status.upper()
        compact = base_r < 58

        wave_energy = sum(self.wave_values) / max(1, len(self.wave_values))
        speed_map = {
            "STANDBY": 0.55,
            "LISTENING": 1.65,
            "THINKING": 2.35,
            "SPEAKING": 1.4,
        }
        speed = speed_map.get(status, 0.9)
        pulse = 1.0 + 0.018 * math.sin(self.t * 2.4 * speed)

        if status == "LISTENING":
            pulse += 0.055 * max(0, math.sin(self.t * 9.5))
        elif status == "SPEAKING":
            pulse += 0.04 * wave_energy
        elif status == "THINKING":
            pulse += 0.026 * abs(math.sin(self.t * 5.5))

        def ring_rect(radius):
            return QRectF(cx - radius, cy - radius, radius * 2, radius * 2)

        def polygon_points(radius, sides, rotation=0.0):
            points = []
            for i in range(sides):
                angle = rotation + (math.pi * 2 * i / sides)
                points.append(QPointF(cx + math.cos(angle) * radius, cy + math.sin(angle) * radius))
            return QPolygonF(points)

        # Hard-edged reactor glow, kept precise rather than cloudy.
        halo = QRadialGradient(QPointF(cx, cy), base_r * 2.55)
        halo.setColorAt(0.0, QColor(80, 210, 235, 44))
        halo.setColorAt(0.26, QColor(34, 112, 138, 24))
        halo.setColorAt(0.58, QColor(8, 42, 58, 9))
        halo.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(halo))
        painter.drawEllipse(QPointF(cx, cy), base_r * 2.55, base_r * 2.55)

        ray_count = 14 if compact else 24
        for i in range(ray_count):
            angle = (math.pi * 2 * i / ray_count) + self.t * 0.16 * speed
            flicker = 0.5 + 0.5 * math.sin(self.t * 3.0 + i * 0.71)
            alpha = 24 + int(45 * flicker)

            if status == "LISTENING" and i % 4 == 0:
                alpha += 70
            if status == "SPEAKING":
                alpha += int(45 * wave_energy)

            inner = base_r * 0.88
            outer = base_r * (1.8 + 0.18 * flicker)
            painter.setPen(QPen(QColor(100, 225, 245, min(190, alpha)), 1))
            painter.drawLine(
                QPointF(cx + math.cos(angle) * inner, cy + math.sin(angle) * inner),
                QPointF(cx + math.cos(angle) * outer, cy + math.sin(angle) * outer),
            )

        # Outer targeting ticks.
        tick_count = 40 if compact else 64
        tick_radius = base_r * 1.58 * pulse
        for i in range(tick_count):
            angle = math.pi * 2 * i / tick_count
            is_major = i % 7 == 0
            tick_len = base_r * (0.12 if is_major else 0.065)
            alpha = 130 if is_major else 62

            if status == "THINKING" and i % 5 == 0:
                alpha += 55

            painter.setPen(QPen(QColor(112, 222, 238, alpha), 2 if is_major else 1))
            painter.drawLine(
                QPointF(cx + math.cos(angle) * (tick_radius - tick_len), cy + math.sin(angle) * (tick_radius - tick_len)),
                QPointF(cx + math.cos(angle) * tick_radius, cy + math.sin(angle) * tick_radius),
            )

        # Counter-rotating precision rings.
        ring_data = [
            (1.46, 220, 54, 2.2, 1),
            (1.22, 92, 38, 1.7, -1),
            (0.98, 150, 42, 1.4, 1),
            (0.76, 58, 26, 1.1, -1),
        ]

        for index, (scale, span, gap_span, width, direction) in enumerate(ring_data):
            radius = base_r * scale * pulse
            rect = ring_rect(radius)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(110, 226, 242, 92 + index * 18), width))
            start = int((self.t * speed * direction * (32 + index * 11) + index * 44) * 16)
            painter.drawArc(rect, start, int(span * 16))
            painter.setPen(QPen(QColor(170, 242, 250, 120), max(1, width - 0.6)))
            painter.drawArc(rect, start + int((span + gap_span) * 16), int((42 + index * 8) * 16))

        # Hexagonal reactor housing.
        outer_hex_r = base_r * 0.72 * pulse
        mid_hex_r = base_r * 0.49 * pulse
        inner_hex_r = base_r * 0.27 * pulse
        rotation = self.t * 0.45 * speed

        painter.setBrush(QBrush(QColor(4, 20, 28, 210)))
        painter.setPen(QPen(QColor(122, 230, 244, 165), 2))
        painter.drawPolygon(polygon_points(outer_hex_r, 6, rotation + math.pi / 6))

        painter.setBrush(QBrush(QColor(8, 38, 50, 185)))
        painter.setPen(QPen(QColor(80, 190, 212, 130), 1.4))
        painter.drawPolygon(polygon_points(mid_hex_r, 6, -rotation * 0.8))

        # Mechanical spokes and inner cells.
        spoke_count = 6
        for i in range(spoke_count):
            angle = rotation + math.pi * 2 * i / spoke_count
            painter.setPen(QPen(QColor(145, 235, 248, 150), 2))
            painter.drawLine(
                QPointF(cx + math.cos(angle) * inner_hex_r, cy + math.sin(angle) * inner_hex_r),
                QPointF(cx + math.cos(angle) * outer_hex_r * 0.92, cy + math.sin(angle) * outer_hex_r * 0.92),
            )

            side_angle = angle + math.pi / spoke_count
            painter.setPen(QPen(QColor(65, 155, 180, 90), 1))
            painter.drawLine(
                QPointF(cx + math.cos(side_angle) * mid_hex_r * 0.72, cy + math.sin(side_angle) * mid_hex_r * 0.72),
                QPointF(cx + math.cos(side_angle) * outer_hex_r * 0.78, cy + math.sin(side_angle) * outer_hex_r * 0.78),
            )

        core_flash = 75
        if status == "LISTENING":
            core_flash += int(80 * abs(math.sin(self.t * 10.0)))
        elif status == "SPEAKING":
            core_flash += int(70 * wave_energy)
        elif status == "THINKING":
            core_flash += int(45 * abs(math.sin(self.t * 6.0)))

        core_grad = QRadialGradient(QPointF(cx, cy), inner_hex_r * 1.4)
        core_grad.setColorAt(0.0, QColor(230, 252, 255, min(245, 160 + core_flash)))
        core_grad.setColorAt(0.35, QColor(95, 220, 240, min(230, 115 + core_flash)))
        core_grad.setColorAt(1.0, QColor(5, 28, 38, 210))
        painter.setBrush(QBrush(core_grad))
        painter.setPen(QPen(QColor(190, 248, 255, 185), 1.5))
        painter.drawPolygon(polygon_points(inner_hex_r, 6, rotation * 1.3 + math.pi / 6))

        painter.setPen(QPen(QColor(230, 252, 255, 180), 1.2))
        painter.drawEllipse(QPointF(cx, cy), base_r * 0.09, base_r * 0.09)

        if not compact:
            painter.setFont(QFont("Consolas", 8, QFont.Bold))
            painter.setPen(QPen(QColor(124, 214, 228, 130), 1))
            painter.drawText(QRectF(cx - 120, cy + base_r * 1.78, 240, 22), Qt.AlignCenter, "LOCAL AI CORE")

        painter.restore()

    def draw_waveform(self, painter, w, h):
        painter.save()

        center_x = w / 2
        y = h / 2 + min(w, h) * 0.305
        total_w = min(w * 0.55, 760)
        gap = 5
        bar_count = len(self.wave_values)
        bar_w = max(4, (total_w - gap * (bar_count - 1)) / bar_count)
        x0 = center_x - total_w / 2

        color_map = {
            "STANDBY": QColor(78, 145, 160),
            "LISTENING": QColor(88, 185, 210),
            "THINKING": QColor(140, 185, 205),
            "SPEAKING": QColor(112, 205, 220),
        }
        wave_color = color_map.get(self.status.upper(), QColor(82, 165, 182))

        for i, value in enumerate(self.wave_values):
            height = 14 + value * 62
            x = x0 + i * (bar_w + gap)

            alpha = 60 + int(115 * value)
            color = QColor(wave_color.red(), wave_color.green(), wave_color.blue(), alpha)

            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(color))
            painter.drawRoundedRect(QRectF(x, y - height / 2, bar_w, height), 3, 3)

        painter.setPen(QPen(QColor(54, 112, 130, 54), 1))
        painter.drawLine(center_x - total_w / 2 - 24, y, center_x + total_w / 2 + 24, y)

        painter.restore()

    def active_painted_widget_ids(self):
        return [
            widget_id for widget_id in self.widget_order
            if widget_id in self.painted_widgets
        ] + [
            widget_id for widget_id in self.widget_closing
            if widget_id in self.painted_widgets and widget_id not in self.widget_order
        ]

    def widget_title_rect(self, rect):
        return QRectF(rect.x() + 14, rect.y() + 10, rect.width() - 28, 36)

    def widget_close_rect(self, rect):
        return QRectF(rect.right() - 44, rect.y() + 13, 26, 22)

    def draw_widget_panels(self, painter, w, h):
        for widget_id in self.active_painted_widget_ids():
            payload = self.painted_widgets.get(widget_id)
            rect = self.widget_rects.get(widget_id)

            if not payload or not rect:
                continue

            opacity = max(0.0, min(1.0, self.widget_opacity.get(widget_id, 1.0)))

            if opacity <= 0.03:
                continue

            slide = (1.0 - opacity) * 20
            draw_rect = QRectF(rect)
            draw_rect.translate(0, slide)
            self.draw_single_widget_panel(painter, payload, draw_rect, opacity)

    def draw_single_widget_panel(self, painter, payload, rect, opacity):
        painter.save()
        painter.setOpacity(opacity)
        painter.setRenderHint(QPainter.Antialiasing, False)

        widget_type = payload.get("widget_type", "")
        title = str(payload.get("title", widget_type)).upper()

        panel_rect = rect.adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(QColor(84, 190, 212, 175), 1.4))
        painter.setBrush(QBrush(QColor(5, 13, 18, 232)))
        painter.drawRect(panel_rect)

        painter.setBrush(QBrush(QColor(8, 28, 38, 205)))
        painter.setPen(QPen(QColor(70, 165, 188, 120), 1))
        painter.drawRect(QRectF(rect.x() + 1, rect.y() + 1, rect.width() - 2, 44))

        corner = 32
        painter.setPen(QPen(QColor(160, 238, 248, 205), 2))
        painter.drawLine(rect.left(), rect.top(), rect.left() + corner, rect.top())
        painter.drawLine(rect.left(), rect.top(), rect.left(), rect.top() + corner)
        painter.drawLine(rect.right(), rect.top(), rect.right() - corner, rect.top())
        painter.drawLine(rect.right(), rect.top(), rect.right(), rect.top() + corner)
        painter.drawLine(rect.left(), rect.bottom(), rect.left() + corner, rect.bottom())
        painter.drawLine(rect.left(), rect.bottom(), rect.left(), rect.bottom() - corner)
        painter.drawLine(rect.right(), rect.bottom(), rect.right() - corner, rect.bottom())
        painter.drawLine(rect.right(), rect.bottom(), rect.right(), rect.bottom() - corner)

        painter.setFont(QFont("Consolas", 14, QFont.Bold))
        painter.setPen(QPen(QColor(154, 230, 242, 235), 1))
        painter.drawText(QRectF(rect.x() + 18, rect.y() + 13, rect.width() - 72, 24), Qt.AlignLeft, title)

        close_rect = self.widget_close_rect(rect)
        painter.setPen(QPen(QColor(120, 220, 238, 155), 1))
        painter.setBrush(QBrush(QColor(8, 28, 38, 220)))
        painter.drawRect(close_rect)
        painter.setFont(QFont("Consolas", 10, QFont.Bold))
        painter.setPen(QPen(QColor(175, 245, 252, 220), 1))
        painter.drawText(close_rect, Qt.AlignCenter, "X")

        painter.setPen(QPen(QColor(255, 255, 255, 12), 1))
        for y in range(int(rect.y()) + 52, int(rect.bottom()) - 8, 7):
            painter.drawLine(QPointF(rect.x() + 2, y), QPointF(rect.right() - 2, y))

        content_rect = rect.adjusted(20, 58, -20, -18)
        painter.setRenderHint(QPainter.Antialiasing, True)

        if widget_type == "todo":
            self.draw_todo_widget_content(painter, payload, content_rect)
        elif widget_type == "chat":
            self.draw_chat_widget_content(painter, payload, content_rect)
        elif widget_type == "system":
            self.draw_system_widget_content(painter, content_rect)
        elif widget_type == "spotify":
            self.draw_spotify_widget_content(painter, content_rect)
        else:
            self.draw_generic_widget_content(painter, payload, content_rect)

        painter.restore()

    def draw_todo_widget_content(self, painter, payload, rect):
        content = payload.get("content", {})
        tasks = []

        if isinstance(content, dict):
            tasks = content.get("tasks") or []

        if not tasks:
            tasks = load_todo_tasks()

        painter.setFont(QFont("Consolas", 11))

        if not tasks:
            painter.setPen(QPen(QColor(128, 210, 224, 165), 1))
            painter.drawText(rect, Qt.AlignCenter | Qt.TextWordWrap, "No tasks yet.")
            return

        y = rect.y() + 4
        row_h = 34

        for index, task in enumerate(tasks[:8]):
            done = bool(task.get("done"))
            text = str(task.get("text", "Untitled task"))
            check_rect = QRectF(rect.x(), y + 6, 17, 17)

            painter.setPen(QPen(QColor(100, 215, 235, 180), 1.2))
            painter.setBrush(QBrush(QColor(4, 20, 28, 190)))
            painter.drawRect(check_rect)

            if done:
                painter.setPen(QPen(QColor(165, 245, 252, 220), 2))
                painter.drawLine(check_rect.left() + 3, check_rect.center().y(), check_rect.center().x() - 1, check_rect.bottom() - 4)
                painter.drawLine(check_rect.center().x() - 1, check_rect.bottom() - 4, check_rect.right() - 3, check_rect.top() + 4)

            painter.setFont(QFont("Consolas", 10))
            painter.setPen(QPen(QColor(145, 224, 236, 140 if done else 220), 1))
            text_rect = QRectF(rect.x() + 28, y, rect.width() - 30, row_h)
            painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self.elide_text(painter, text, text_rect.width()))

            if done:
                painter.setPen(QPen(QColor(145, 224, 236, 95), 1))
                painter.drawLine(text_rect.left(), text_rect.center().y(), text_rect.right() - 10, text_rect.center().y())

            y += row_h

        if len(tasks) > 8:
            painter.setFont(QFont("Consolas", 9))
            painter.setPen(QPen(QColor(112, 190, 205, 145), 1))
            painter.drawText(QRectF(rect.x(), rect.bottom() - 20, rect.width(), 18), Qt.AlignRight, f"+{len(tasks) - 8} more")

    def draw_chat_widget_content(self, painter, payload, rect):
        content = payload.get("content", {})
        messages = []

        if isinstance(content, dict):
            messages = content.get("messages") or []

        if not messages:
            messages = read_chat_history(limit=10)

        if not messages:
            painter.setFont(QFont("Consolas", 10))
            painter.setPen(QPen(QColor(128, 210, 224, 165), 1))
            painter.drawText(rect, Qt.AlignCenter | Qt.TextWordWrap, "No conversation captured yet.")
            return

        y = rect.y()

        for message in messages[-6:]:
            role = str(message.get("role", "jarvis")).lower()
            text = str(message.get("text", "")).strip()
            timestamp = str(message.get("timestamp", ""))[11:19]
            bubble_w = rect.width() * 0.76
            bubble_h = min(58, max(34, 22 + len(text) // 4))
            x = rect.right() - bubble_w if role == "user" else rect.x()
            bubble = QRectF(x, y, bubble_w, bubble_h)

            painter.setPen(QPen(QColor(82, 180, 202, 120), 1))
            painter.setBrush(QBrush(QColor(7, 24, 32, 175)))
            painter.drawRect(bubble)

            prefix = "YOU" if role == "user" else "JARVIS"
            painter.setFont(QFont("Consolas", 8, QFont.Bold))
            painter.setPen(QPen(QColor(112, 205, 220, 160), 1))
            painter.drawText(QRectF(bubble.x() + 8, bubble.y() + 5, bubble.width() - 16, 14), Qt.AlignLeft, f"{prefix} // {timestamp}")

            painter.setFont(QFont("Consolas", 9))
            painter.setPen(QPen(QColor(150, 226, 238, 220), 1))
            painter.drawText(QRectF(bubble.x() + 8, bubble.y() + 21, bubble.width() - 16, bubble.height() - 24), Qt.AlignLeft | Qt.TextWordWrap, text)
            y += bubble_h + 8

            if y > rect.bottom() - 30:
                break

    def get_system_cache(self):
        now = time.time()

        if self.system_cache and now - self.system_cache_updated_at < 5:
            return self.system_cache

        if not psutil:
            self.system_cache = {"available": False}
        else:
            battery = psutil.sensors_battery()
            self.system_cache = {
                "available": True,
                "CPU": psutil.cpu_percent(interval=None),
                "RAM": psutil.virtual_memory().percent,
                "DISK": psutil.disk_usage(str(BASE_DIR.anchor or "C:\\")).percent,
                "BATTERY": battery.percent if battery else None,
            }

        self.system_cache_updated_at = now
        return self.system_cache

    def draw_system_widget_content(self, painter, rect):
        stats = self.get_system_cache()

        if not stats.get("available"):
            painter.setFont(QFont("Consolas", 10))
            painter.setPen(QPen(QColor(128, 210, 224, 165), 1))
            painter.drawText(rect, Qt.AlignCenter, "System telemetry unavailable.")
            return

        y = rect.y() + 8

        for label in ["CPU", "RAM", "DISK", "BATTERY"]:
            value = stats.get(label)

            if value is None:
                continue

            self.draw_status_bar(painter, QRectF(rect.x(), y, rect.width(), 28), label, safe_percent(value))
            y += 42

    def draw_status_bar(self, painter, rect, label, value):
        painter.setFont(QFont("Consolas", 10, QFont.Bold))
        painter.setPen(QPen(QColor(135, 220, 234, 210), 1))
        painter.drawText(QRectF(rect.x(), rect.y(), 78, rect.height()), Qt.AlignVCenter | Qt.AlignLeft, label)

        bar = QRectF(rect.x() + 88, rect.y() + 5, rect.width() - 92, 18)
        painter.setPen(QPen(QColor(68, 165, 188, 135), 1))
        painter.setBrush(QBrush(QColor(4, 20, 28, 195)))
        painter.drawRect(bar)

        fill = QRectF(bar.x() + 1, bar.y() + 1, max(2, (bar.width() - 2) * value / 100), bar.height() - 2)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(85, 218, 235, 180)))
        painter.drawRect(fill)

        painter.setFont(QFont("Consolas", 9))
        painter.setPen(QPen(QColor(175, 245, 252, 220), 1))
        painter.drawText(bar, Qt.AlignCenter, f"{value}%")

    def draw_spotify_widget_content(self, painter, rect):
        album = QRectF(rect.x(), rect.y() + 4, 118, 118)
        painter.setPen(QPen(QColor(90, 190, 210, 135), 1))
        painter.setBrush(QBrush(QColor(7, 24, 32, 190)))
        painter.drawRect(album)

        painter.setFont(QFont("Consolas", 10, QFont.Bold))
        painter.setPen(QPen(QColor(120, 205, 220, 155), 1))
        painter.drawText(album, Qt.AlignCenter, "ALBUM\nART")

        painter.setFont(QFont("Consolas", 13, QFont.Bold))
        painter.setPen(QPen(QColor(155, 232, 242, 230), 1))
        painter.drawText(QRectF(rect.x() + 136, rect.y() + 12, rect.width() - 136, 30), Qt.AlignLeft, "Spotify not detected")

        painter.setFont(QFont("Consolas", 10))
        painter.setPen(QPen(QColor(118, 200, 215, 170), 1))
        painter.drawText(QRectF(rect.x() + 136, rect.y() + 48, rect.width() - 136, 42), Qt.AlignLeft | Qt.TextWordWrap, "Open Spotify to show playback here.")

        self.draw_status_bar(painter, QRectF(rect.x(), rect.y() + 142, rect.width(), 28), "TRACK", 0)

        painter.setFont(QFont("Consolas", 9, QFont.Bold))
        painter.setPen(QPen(QColor(110, 196, 212, 145), 1))
        controls = ["PREV", "PLAY", "NEXT"]
        button_w = (rect.width() - 20) / 3

        for i, label in enumerate(controls):
            button = QRectF(rect.x() + i * (button_w + 10), rect.y() + 190, button_w, 30)
            painter.setPen(QPen(QColor(70, 165, 185, 105), 1))
            painter.setBrush(QBrush(QColor(8, 28, 38, 145)))
            painter.drawRect(button)
            painter.setPen(QPen(QColor(145, 220, 232, 150), 1))
            painter.drawText(button, Qt.AlignCenter, label)

    def draw_generic_widget_content(self, painter, payload, rect):
        content = payload.get("content", {})
        text = json.dumps(content, indent=2) if isinstance(content, (dict, list)) else str(content or "No content.")
        painter.setFont(QFont("Consolas", 10))
        painter.setPen(QPen(QColor(145, 220, 232, 200), 1))
        painter.drawText(rect, Qt.AlignLeft | Qt.TextWordWrap, text)

    def elide_text(self, painter, text, width):
        return painter.fontMetrics().elidedText(str(text or ""), Qt.ElideRight, int(width))

    def draw_bottom_strip(self, painter, w, h):
        painter.save()

        rect = QRectF(46, h - 62, w - 92, 34)
        painter.setPen(QPen(QColor(55, 118, 134, 72), 1.2))
        painter.setBrush(QBrush(QColor(4, 16, 22, 96)))
        painter.drawRoundedRect(rect, 12, 12)

        left_text = "J.A.R.V.I.S // LOCAL WINDOWS ASSISTANT // VOICE + MEMORY + TOOLS"
        right_text = "F11 FULLSCREEN  |  ESC EXIT FULLSCREEN"

        painter.setFont(QFont("Consolas", 9))
        painter.setPen(QPen(QColor(92, 165, 182, 138), 1))
        painter.drawText(QRectF(62, h - 54, w / 2, 18), Qt.AlignLeft, left_text)
        painter.drawText(QRectF(w / 2, h - 54, w / 2 - 62, 18), Qt.AlignRight, right_text)

        painter.restore()

    def draw_scanlines(self, painter, w, h):
        painter.save()
        painter.setPen(QPen(QColor(255, 255, 255, 5), 1))
        for y in range(0, h, 8):
            painter.drawLine(0, y, w, y)
        painter.restore()


def main():
    app = QApplication(sys.argv)

    app.setStyleSheet("""
        QWidget#jarvisRoot {
            background-color: #010408;
        }
    """)

    window = JarvisHUD()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
