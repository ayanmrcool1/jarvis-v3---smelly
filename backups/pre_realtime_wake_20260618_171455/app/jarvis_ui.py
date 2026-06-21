import sys
import math
import random
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import (
    QColor,
    QPainter,
    QPen,
    QBrush,
    QFont,
    QLinearGradient,
    QRadialGradient,
)
from PySide6.QtWidgets import QApplication, QWidget, QPushButton, QLabel

from ui_state import read_ui_state


class JarvisHUD(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("J.A.R.V.I.S")
        self.setMinimumSize(1200, 760)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        self.t = 0.0
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

    def tick(self):
        self.t += 0.016

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

        self.update()

    def refresh_external_state(self):
        state = read_ui_state()

        self.status = state.get("status", "STANDBY")
        self.sub_status = state.get("sub_status", "Awaiting wake phrase")
        self.detail = state.get("detail", "")

        self.status_label.setText(self.status)
        self.sub_status_label.setText(self.sub_status)
        self.detail_label.setText(self.detail)

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
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.is_dragging_window = True

            if self.paint_timer.isActive():
                self.paint_timer.stop()

    def mouseMoveEvent(self, event):
        if self.drag_position and not self.isFullScreen():
            self.move(event.globalPosition().toPoint() - self.drag_position)

    def mouseReleaseEvent(self, event):
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

        cx = w / 2
        cy = h / 2 + 8
        base_r = min(w, h) * 0.14
        pulse = 1 + 0.012 * math.sin(self.t * 3.0)

        # Outer mist
        halo = QRadialGradient(QPointF(cx, cy), base_r * 3.0)
        halo.setColorAt(0.0, QColor(42, 110, 128, 28))
        halo.setColorAt(0.42, QColor(20, 58, 72, 14))
        halo.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(halo))
        painter.drawEllipse(QPointF(cx, cy), base_r * 3.0, base_r * 3.0)

        # Rotating outer arcs
        ring_scales = [2.1, 1.72, 1.4]
        ring_colors = [
            QColor(92, 178, 194, 80),
            QColor(76, 150, 168, 72),
            QColor(62, 128, 146, 60),
        ]

        for i, scale in enumerate(ring_scales):
            radius = base_r * scale * pulse
            rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)
            painter.setPen(QPen(ring_colors[i], 2))
            painter.setBrush(Qt.NoBrush)

            start = int((self.t * (44 + i * 8) * (1 if i % 2 == 0 else -1) + i * 72) * 16)
            span = int((180 - i * 20) * 16)
            painter.drawArc(rect, start, span)

            start2 = int((self.t * (-36 - i * 7) + 180 + i * 38) * 16)
            span2 = int((44 + i * 10) * 16)
            painter.drawArc(rect, start2, span2)

        # Glass core shell
        core_r = base_r * 0.84 * pulse
        shell_grad = QRadialGradient(QPointF(cx - core_r * 0.24, cy - core_r * 0.28), core_r * 1.3)
        shell_grad.setColorAt(0.0, QColor(205, 235, 240, 225))
        shell_grad.setColorAt(0.16, QColor(112, 190, 205, 180))
        shell_grad.setColorAt(0.42, QColor(45, 100, 128, 200))
        shell_grad.setColorAt(0.76, QColor(15, 36, 54, 230))
        shell_grad.setColorAt(1.0, QColor(5, 14, 24, 245))

        painter.setPen(QPen(QColor(130, 205, 218, 150), 1.6))
        painter.setBrush(QBrush(shell_grad))
        painter.drawEllipse(QPointF(cx, cy), core_r, core_r)

        # Inner glass center
        inner_r = core_r * 0.48
        inner_grad = QRadialGradient(QPointF(cx - inner_r * 0.2, cy - inner_r * 0.22), inner_r * 1.15)
        inner_grad.setColorAt(0.0, QColor(225, 245, 248, 160))
        inner_grad.setColorAt(0.3, QColor(135, 205, 216, 110))
        inner_grad.setColorAt(1.0, QColor(20, 56, 76, 60))

        painter.setPen(QPen(QColor(170, 225, 235, 55), 1))
        painter.setBrush(QBrush(inner_grad))
        painter.drawEllipse(QPointF(cx, cy), inner_r, inner_r)

        # Highlight streak
        painter.setPen(QPen(QColor(235, 250, 255, 95), 2))
        painter.drawArc(
            QRectF(cx - core_r * 0.78, cy - core_r * 0.78, core_r * 1.56, core_r * 1.56),
            32 * 16,
            70 * 16
        )

        # Orbiting node
        orbit_r = core_r * 0.95
        theta = self.t * 1.35
        node_x = cx + math.cos(theta) * orbit_r
        node_y = cy + math.sin(theta) * orbit_r
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(185, 230, 238, 165)))
        painter.drawEllipse(QPointF(node_x, node_y), 4.2, 4.2)

        # Rotating labels
        labels = ["VOICE", "MEMORY", "VISION", "TOOLS"]
        label_radius = base_r * 1.62
        painter.setFont(QFont("Consolas", 8, QFont.Bold))
        painter.setPen(QPen(QColor(110, 180, 192, 125), 1))

        for i, label in enumerate(labels):
            angle = self.t * 0.35 + i * (math.pi * 2 / len(labels))
            lx = cx + math.cos(angle) * label_radius
            ly = cy + math.sin(angle) * label_radius
            painter.drawText(QRectF(lx - 34, ly - 10, 68, 20), Qt.AlignCenter, label)

        # Label beneath orb
        painter.setFont(QFont("Consolas", 10, QFont.Bold))
        painter.setPen(QPen(QColor(118, 190, 204, 170), 1))
        painter.drawText(QRectF(cx - 120, cy + base_r * 2.05, 240, 22), Qt.AlignCenter, "GLASS AI CORE")

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
        QWidget {
            background-color: #010408;
        }
    """)

    window = JarvisHUD()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()