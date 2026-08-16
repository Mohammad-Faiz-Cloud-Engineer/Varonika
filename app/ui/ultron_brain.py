import math
import random
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QColor, QPen, QBrush
from PySide6.QtCore import QTimer, Qt, QPointF
from app.conversation.state import AppState

class UltronBrain(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(300, 400)
        self.state = AppState.LISTENING_FOR_WAKEWORD
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(30) # ~33fps
        self.time = 0.0

        # Generate some random nodes for the network
        self.nodes = [(random.random(), random.random()) for _ in range(30)]

    def set_state(self, new_state: AppState):
        self.state = new_state

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Background
        painter.fillRect(self.rect(), QColor(10, 10, 15))

        self.time += 0.05
        
        # Determine colors and activity based on state
        color = QColor(0, 150, 255) # Default blue
        pulse_speed = 1.0
        line_thickness = 1
        
        if self.state == AppState.LISTENING_FOR_WAKEWORD:
            color = QColor(0, 100, 200, 100)
            pulse_speed = 0.5
        elif self.state == AppState.WAKEWORD_DETECTED:
            color = QColor(0, 255, 255)
            pulse_speed = 3.0
            line_thickness = 3
        elif self.state == AppState.LISTENING:
            color = QColor(0, 255, 100)
            pulse_speed = 2.0
        elif self.state == AppState.TRANSCRIBING:
            color = QColor(255, 150, 0)
            pulse_speed = 3.0
        elif self.state == AppState.THINKING:
            color = QColor(255, 0, 255)
            pulse_speed = 4.0
        elif self.state == AppState.SPEAKING:
            color = QColor(0, 200, 255)
            pulse_speed = max(1, int(2.0 + math.sin(self.time * 2) * 1.5))
        elif self.state == AppState.ERROR:
            color = QColor(255, 0, 0)
            pulse_speed = 0.5
        
        w, h = self.width(), self.height()
        center_x, center_y = w / 2, h / 2

        # Draw connecting lines
        pen = QPen(color)
        pen.setWidth(line_thickness)
        painter.setPen(pen)
        
        # Dynamic node positions
        active_nodes = []
        for nx, ny in self.nodes:
            dx = math.sin(self.time * pulse_speed + nx * 10) * 20
            dy = math.cos(self.time * pulse_speed + ny * 10) * 20
            px = center_x + (nx - 0.5) * w * 0.8 + dx
            py = center_y + (ny - 0.5) * h * 0.8 + dy
            active_nodes.append((px, py))

        # Draw mesh
        for i in range(len(active_nodes)):
            for j in range(i + 1, len(active_nodes)):
                x1, y1 = active_nodes[i]
                x2, y2 = active_nodes[j]
                dist = math.hypot(x2 - x1, y2 - y1)
                if dist < 100:
                    alpha = int(255 * (1 - dist/100))
                    c = QColor(color)
                    c.setAlpha(alpha)
                    painter.setPen(QPen(c, line_thickness))
                    painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        
        # Draw central orb
        radius = 30 + math.sin(self.time * pulse_speed) * 10
        orb_color = QColor(color)
        orb_color.setAlpha(150)
        painter.setBrush(QBrush(orb_color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(center_x, center_y), radius, radius)

        painter.end()
