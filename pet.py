# pet.py — 사자 PNG 이미지 기반 버전.
# QWidget(투명 컨테이너) 안에 msg_label + lion_label + hint_label 을 쌓아서 표시.
# HTML img 태그 방식은 Qt 로컬 파일 로드 미지원으로 폐기 → setPixmap() 사용.

import sys
import os
import signal
import random
import math
import win32api
import win32con
from PyQt5.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect, QSize, QEvent,
)
from PyQt5.QtGui import QPixmap, QPainter, QColor, QPen, QFontDatabase, QFontMetrics
from PyQt5.QtWidgets import (
    QApplication, QLabel, QWidget,
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QListWidget, QListWidgetItem, QGraphicsOpacityEffect,
)

from watcher import get_active_window_title, get_active_window_info, close_window
from judge import is_on_task
from messages import PRAISE, ANGRY, SAD, CELEBRATE

# --- 사자 이미지 설정 ---
BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")  # PNG 파일 기준 폴더
CHARACTER_SIZE = 200            # 사자 이미지 표시 크기(px)
MESSAGE_FONT_SIZE = 28          # 메시지 텍스트 크기(px)
SPEECH_CHAR_MS = 45             # 타이핑 효과 — 글자당 출력 간격(ms)
MARGIN_FROM_EDGE = 50           # 화면 우하단 여백(px)

LION_IMAGES = {                 # 무드 → PNG 파일명
    "default":   "lion_default.png",
    "praise":    "lion_praise.png",
    "angry":     "lion_angry.png",
    "sad":       "lion_sad.png",
    "hidden":    "lion_hidden.png",
    "celebrate": "lion_celebration.png",
}


def _lion_pixmap(mood: str = "default", size: int = 80) -> QPixmap:
    """무드에 맞는 사자 QPixmap (정사각형 스케일). 파일 없으면 default 폴백."""
    name = LION_IMAGES.get(mood, "lion_default.png")
    path = os.path.join(BASE_DIR, name)
    if not os.path.exists(path):                        # celebrate 등 아직 없는 파일 폴백
        path = os.path.join(BASE_DIR, "lion_default.png")
    px = QPixmap(path)
    if px.isNull():
        return px                                        # 호출자가 isNull() 체크 후 폴백
    return px.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def _window_display_name(title: str) -> str:
    """긴 창 제목에서 사용자가 알아보기 쉬운 앱/사이트 이름만 추출."""
    title = (title or "").strip()
    if not title:
        return "현재"

    known_names = (
        "YouTube",
        "Visual Studio Code",
        "Visual Studio",
        "Google Chrome",
        "Microsoft Edge",
        "Discord",
        "Steam",
        "Notion",
    )
    title_lower = title.lower()
    for name in known_names:
        if name.lower() in title_lower:
            if name == "Google Chrome":
                return "Chrome"
            if name == "Microsoft Edge":
                return "Edge"
            return name

    for separator in (" - ", " — ", " – "):
        if separator in title:
            parts = [part.strip() for part in title.split(separator) if part.strip()]
            if parts:
                return parts[-1]

    return title[:24]


# --- 감시/에스컬레이션 타이밍 ---
WATCH_INTERVAL_MS = 5000
ESCALATION_SECONDS = 300
ESCALATION_WARNING = "5분이나 무시해? 창 닫는다!"
ESCALATION_CLOSE_DELAY_MS = 2200

# --- 무드별 메시지 박스 색상 ---
MOOD_STYLES = {
    "praise":    {"bg": "#fff4e0", "text": "#5d4037"},
    "angry":     {"bg": "#ffebee", "text": "#b71c1c"},
    "sad":       {"bg": "#e8eaf6", "text": "#283593"},
    "celebrate": {"bg": "#fff8d0", "text": "#bf6f00"},
    "default":   {"bg": "#ffffff", "text": "#333333"},
}

BUTTON_STYLE = """
    QPushButton {
        font-size: 16px; font-weight: bold; color: white;
        background-color: #ff9800; border: none; border-radius: 10px;
        padding: 14px; font-family: 'Hakgyoansim Nadeuri TTF B', 'Malgun Gothic', sans-serif;
    }
    QPushButton:hover { background-color: #ff7043; }
    QPushButton:pressed { background-color: #e65100; }
    QPushButton:disabled { background-color: #cccccc; }
"""

DIALOG_STYLE = """
    QDialog {
        background-color: #fff8e1;
        border: 2px solid #ff9800;
    }
"""


class OutlinedLabel(QLabel):
    """배경·테두리 없이 흰 글자만 — 검은 외곽선 + 그림자로 어떤 배경에서도 가독성 확보."""

    _OUTLINE = QColor(0, 0, 0, 210)
    _SHADOW = QColor(0, 0, 0, 120)
    _TEXT = QColor(255, 255, 255)

    def paintEvent(self, event):
        if not self.text():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setFont(self.font())
        rect = self.contentsRect()
        flags = self.alignment() | Qt.TextWordWrap

        # 그림자 (아래·오른쪽으로 살짝)
        painter.setPen(self._SHADOW)
        painter.drawText(rect.translated(2, 3), flags, self.text())

        # 외곽선 (8방향 1px)
        painter.setPen(self._OUTLINE)
        for dx, dy in ((-1, -1), (0, -1), (1, -1), (-1, 0),
                       (1, 0), (-1, 1), (0, 1), (1, 1)):
            painter.drawText(rect.translated(dx, dy), flags, self.text())

        # 흰 글자
        painter.setPen(self._TEXT)
        painter.drawText(rect, flags, self.text())


class DraggableDialog(QDialog):
    """Frameless 다이얼로그 베이스 — 빈 영역 드래그로 창 이동."""

    def __init__(self):
        super().__init__()
        self._drag_pos = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPos() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None


class GoalDialog(DraggableDialog):
    """첫 진입 — 여러 목표 추가/삭제, 노트 스타일 frameless 모달."""

    _MX = 67             # 빨간 여백선 x
    _LT = 197            # 첫 가로줄 y
    _LG = 50             # 줄 간격 (아이템 높이와 동일)
    _ITEM_FONT_SIZE = 19 # 목표 목록 글자 크기

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(528, 696)
        self.goals: list[str] = []
        self.manual_mode = False
        self._shift_press_count = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(self._MX + 19, 29, 31, 26)
        layout.setSpacing(7)

        top_row = QHBoxLayout()
        drag_hint = QLabel("✎  드래그로 이동")
        drag_hint.setStyleSheet(
            "font-size: 12px; color: #C8C8C8; background: transparent;"
            "font-family: 'Hakgyoansim Nadeuri TTF B', 'Malgun Gothic';"
        )
        top_row.addWidget(drag_hint, 1)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(31, 31)
        close_btn.setStyleSheet("""
            QPushButton {
                color: #BBBBBB; background: transparent; border: none;
                font-size: 18px; font-weight: bold;
            }
            QPushButton:hover { color: #E53935; background: #FFE8E8; border-radius: 15px; }
        """)
        close_btn.clicked.connect(self.reject)
        top_row.addWidget(close_btn)
        layout.addLayout(top_row)

        lion_label = QLabel()
        lion_label.setAlignment(Qt.AlignCenter)
        lion_label.setStyleSheet("background: transparent;")
        px = _lion_pixmap("default", 96)
        if not px.isNull():
            lion_label.setPixmap(px)
        else:
            lion_label.setText("🦁")
            lion_label.setStyleSheet("font-size: 67px; background: transparent;")
        layout.addWidget(lion_label)

        prompt = QLabel("오늘 목표 다 적어내냥")
        prompt.setAlignment(Qt.AlignCenter)
        prompt.setStyleSheet(
            "font-size: 26px; font-weight: bold; color: #4A4A4A;"
            "font-family: 'Hakgyoansim Nadeuri TTF B', 'Malgun Gothic';"
            "background: transparent;"
        )
        layout.addWidget(prompt)

        input_row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("예: Python 공부")
        self.input.setStyleSheet("""
            QLineEdit {
                font-size: 18px; padding: 5px 5px 8px 5px;
                border: none; border-bottom: 2px solid #C8C8C8;
                background: transparent; color: #333333;
                font-family: 'Hakgyoansim Nadeuri TTF B', 'Malgun Gothic';
            }
            QLineEdit:focus { border-bottom: 2px solid #FF9800; }
        """)
        self.input.returnPressed.connect(self._add_goal)

        add_btn = QPushButton("+ 추가")
        add_btn.setFixedWidth(84)
        add_btn.setStyleSheet("""
            QPushButton {
                font-size: 16px; font-weight: bold; color: white;
                background-color: #FFAA44; border: none; border-radius: 17px;
                padding: 10px 0px; font-family: 'Hakgyoansim Nadeuri TTF B', 'Malgun Gothic';
            }
            QPushButton:hover { background-color: #FF8C00; }
        """)
        add_btn.clicked.connect(self._add_goal)
        input_row.addWidget(self.input, 1)
        input_row.addSpacing(10)
        input_row.addWidget(add_btn)
        layout.addLayout(input_row)

        self.goals_list = QListWidget()
        self.goals_list.setStyleSheet("""
            QListWidget {
                border: none; background: transparent;
                padding: 0px; margin: 0px;
            }
            QListWidget::item {
                padding: 12px 2px 6px 2px;
                color: #444444;
            }
            QListWidget::item:selected { background: rgba(255, 168, 68, 0.12); }
        """)
        layout.addWidget(self.goals_list, 1)

        self.start_btn = QPushButton("시작하기  ✓")
        self.start_btn.setFixedHeight(55)
        self.start_btn.setStyleSheet("""
            QPushButton {
                font-size: 18px; font-weight: bold; color: white;
                background-color: #FF9800; border: none; border-radius: 27px;
                font-family: 'Hakgyoansim Nadeuri TTF B', 'Malgun Gothic';
            }
            QPushButton:hover { background-color: #FF7043; }
            QPushButton:pressed { background-color: #E65100; }
            QPushButton:disabled { background-color: #DDDDDD; color: #AAAAAA; }
        """)
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self._on_start)
        layout.addWidget(self.start_btn)

        esc_hint = QLabel("ESC 키로 취소")
        esc_hint.setAlignment(Qt.AlignCenter)
        esc_hint.setStyleSheet(
            "font-size: 12px; color: #CCCCCC; background: transparent;"
            "font-family: 'Hakgyoansim Nadeuri TTF B', 'Malgun Gothic';"
        )
        layout.addWidget(esc_hint)

        for widget in (self, self.input, self.goals_list, self.start_btn, add_btn):
            widget.installEventFilter(self)

    def _record_shift_press(self, event):
        if event.key() != Qt.Key_Shift or event.isAutoRepeat():
            return False
        self._shift_press_count += 1
        if self._shift_press_count >= 3 and not self.manual_mode:
            self.manual_mode = True
            self.start_btn.setText("수동 모드 시작하기  ✓")
            print("[수동 모드] 목표 설정 창에서 Shift 3회 입력됨")
        return True

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            if self._record_shift_press(event):
                return True
            self._shift_press_count = 0
        return super().eventFilter(obj, event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        r = 22

        # 드롭 섀도 (7겹 반투명 오프셋)
        painter.setPen(Qt.NoPen)
        for i in range(7, 0, -1):
            painter.setBrush(QColor(0, 0, 0, 9))
            painter.drawRoundedRect(i, i, w - i, h - i, r, r)

        # 종이 배경
        painter.setBrush(QColor("#FFFDF0"))
        painter.drawRoundedRect(0, 0, w - 7, h - 7, r, r)

        # 가로 줄선
        painter.setPen(QPen(QColor("#D6E8F7"), 1))
        for y in range(self._LT, h - 58, self._LG):
            painter.drawLine(self._MX, y, w - 24, y)

        # 빨간 여백선
        painter.setPen(QPen(QColor("#FFAAAA"), 1.5))
        painter.drawLine(self._MX, 22, self._MX, h - 58)

        # 스파이럴 구멍 (왼쪽 세로 열, 7개)
        hole_r = 10
        hole_x = 24
        n_holes = 7
        painter.setBrush(QColor("#EDE7CE"))
        painter.setPen(QPen(QColor("#C8BFA0"), 1))
        for i in range(n_holes):
            hy = int(36 + i * (h - 72) / (n_holes - 1))
            painter.drawEllipse(hole_x - hole_r, hy - hole_r, hole_r * 2, hole_r * 2)

    def _add_goal(self):
        text = self.input.text().strip()
        if not text:
            return
        item = QListWidgetItem()
        item.setData(Qt.UserRole, text)
        widget = QWidget()
        widget.setStyleSheet("background: transparent;")
        h = QHBoxLayout(widget)
        h.setContentsMargins(5, 0, 5, 0)
        h.setSpacing(10)
        label = QLabel("• " + text)
        label.setStyleSheet(
            f"font-size: {self._ITEM_FONT_SIZE}px; color: #444444; background: transparent;"
            "font-family: 'Hakgyoansim Nadeuri TTF B', 'Malgun Gothic';"
        )
        delete_btn = QPushButton("✕")
        delete_btn.setFixedSize(29, 29)
        delete_btn.setStyleSheet("""
            QPushButton { color: #C8C8C8; background: transparent; border: none;
                          font-size: 14px; }
            QPushButton:hover { color: #E53935; }
        """)
        delete_btn.clicked.connect(lambda: self._remove_item(item))
        h.addWidget(label, 1)
        h.addWidget(delete_btn)
        item.setSizeHint(QSize(0, self._LG))
        self.goals_list.addItem(item)
        self.goals_list.setItemWidget(item, widget)
        self.input.clear()
        self._update_button_state()

    def _remove_item(self, item: QListWidgetItem):
        row = self.goals_list.row(item)
        self.goals_list.takeItem(row)
        self._update_button_state()

    def _update_button_state(self):
        self.start_btn.setEnabled(self.goals_list.count() > 0)

    def _on_start(self):
        self.goals = [
            self.goals_list.item(i).data(Qt.UserRole)
            for i in range(self.goals_list.count())
        ]
        if not self.goals:
            return
        self.accept()

    def keyPressEvent(self, event):
        if self._record_shift_press(event):
            event.accept()
        elif event.key() == Qt.Key_Escape:
            self.reject()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            pass  # QDialog가 Enter로 default 버튼 트리거하는 것 방지
        elif event.key() == Qt.Key_Delete:
            self._shift_press_count = 0
            for it in self.goals_list.selectedItems():
                self._remove_item(it)
        else:
            self._shift_press_count = 0
            super().keyPressEvent(event)


class CelebrateDialog(DraggableDialog):
    """완료 클릭 시 축하 모달 — 노트 스타일, 목표는 빗금 처리. 별 폭발은 CelebrationOverlay 담당."""

    _MX = 67             # 빨간 여백선 x
    _LT = 255            # 첫 가로줄 y (목표 리스트 시작 위치에 맞춤)
    _LG = 50             # 줄 간격 (아이템 높이와 동일)
    _ITEM_FONT_SIZE = 19 # 목표 글자 크기

    def __init__(self, goals: list[str], message: str):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(528, 696)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(self._MX + 19, 29, 31, 26)
        layout.setSpacing(7)

        top_row = QHBoxLayout()
        top_row.addStretch(1)
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(31, 31)
        close_btn.setStyleSheet("""
            QPushButton {
                color: #BBBBBB; background: transparent; border: none;
                font-size: 18px; font-weight: bold;
            }
            QPushButton:hover { color: #E53935; background: #FFE8E8; border-radius: 15px; }
        """)
        close_btn.clicked.connect(self.accept)
        top_row.addWidget(close_btn)
        layout.addLayout(top_row)

        lion_label = QLabel()
        lion_label.setAlignment(Qt.AlignCenter)
        lion_label.setStyleSheet("background: transparent;")
        px = _lion_pixmap("celebrate", 96)
        if not px.isNull():
            lion_label.setPixmap(px)
        else:
            lion_label.setText("🥳")
            lion_label.setStyleSheet("font-size: 67px; background: transparent;")
        layout.addWidget(lion_label)

        title = QLabel("오늘 목표 클리어!")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size: 28px; font-weight: bold; color: #FF9800;"
            "font-family: 'Hakgyoansim Nadeuri TTF B', 'Malgun Gothic';"
            "background: transparent;"
        )
        layout.addWidget(title)

        # 완료된 목표 — 주황 체크 + 회색 빗금, 노트 줄 위에 배치
        goals_list = QListWidget()
        goals_list.setFocusPolicy(Qt.NoFocus)
        goals_list.setSelectionMode(QListWidget.NoSelection)
        goals_list.setStyleSheet("""
            QListWidget { border: none; background: transparent; padding: 0px; margin: 0px; }
            QListWidget::item { padding: 12px 2px 6px 2px; }
        """)
        for g in goals:
            item = QListWidgetItem()
            lbl = QLabel(
                f'<span style="color:#FF9800;">✓</span> '
                f'<span style="color:#AAAAAA;"><s>{g}</s></span>'
            )
            lbl.setTextFormat(Qt.RichText)
            lbl.setStyleSheet(
                f"font-size: {self._ITEM_FONT_SIZE}px; background: transparent;"
                "font-family: 'Hakgyoansim Nadeuri TTF B', 'Malgun Gothic';"
            )
            item.setSizeHint(QSize(0, self._LG))
            goals_list.addItem(item)
            goals_list.setItemWidget(item, lbl)
        layout.addWidget(goals_list, 1)

        sajaa_msg = QLabel(message)
        sajaa_msg.setAlignment(Qt.AlignCenter)
        sajaa_msg.setWordWrap(True)
        sajaa_msg.setStyleSheet(
            "font-size: 18px; color: #5D4037; font-weight: bold;"
            "padding: 12px; background-color: rgba(255, 200, 80, 0.25); border-radius: 10px;"
            "font-family: 'Hakgyoansim Nadeuri TTF B', 'Malgun Gothic';"
        )
        layout.addWidget(sajaa_msg)

        button = QPushButton("좋다, 마무리하자")
        button.setFixedHeight(55)
        button.setStyleSheet("""
            QPushButton {
                font-size: 18px; font-weight: bold; color: white;
                background-color: #FF9800; border: none; border-radius: 27px;
                font-family: 'Hakgyoansim Nadeuri TTF B', 'Malgun Gothic';
            }
            QPushButton:hover { background-color: #FF7043; }
            QPushButton:pressed { background-color: #E65100; }
        """)
        button.clicked.connect(self.accept)
        layout.addWidget(button)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        r = 22

        painter.setPen(Qt.NoPen)
        for i in range(7, 0, -1):
            painter.setBrush(QColor(0, 0, 0, 9))
            painter.drawRoundedRect(i, i, w - i, h - i, r, r)

        painter.setBrush(QColor("#FFFDF0"))
        painter.drawRoundedRect(0, 0, w - 7, h - 7, r, r)

        painter.setPen(QPen(QColor("#D6E8F7"), 1))
        for y in range(self._LT, h - 58, self._LG):
            painter.drawLine(self._MX, y, w - 24, y)

        painter.setPen(QPen(QColor("#FFAAAA"), 1.5))
        painter.drawLine(self._MX, 22, self._MX, h - 58)

        hole_r = 10
        hole_x = 24
        n_holes = 7
        painter.setBrush(QColor("#EDE7CE"))
        painter.setPen(QPen(QColor("#C8BFA0"), 1))
        for i in range(n_holes):
            hy = int(36 + i * (h - 72) / (n_holes - 1))
            painter.drawEllipse(hole_x - hole_r, hy - hole_r, hole_r * 2, hole_r * 2)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Escape, Qt.Key_Return, Qt.Key_Enter):
            self.accept()
        else:
            super().keyPressEvent(event)


class EscalationWarningDialog(QDialog):
    """창을 닫기 전 중앙에 잠깐 띄우는 경고 다이얼로그."""

    def __init__(self, window_name: str):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(500, 230)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(10)

        lion_label = QLabel()
        lion_label.setAlignment(Qt.AlignCenter)
        lion_label.setStyleSheet("background: transparent;")
        px = _lion_pixmap("angry", 82)
        if not px.isNull():
            lion_label.setPixmap(px)
        else:
            lion_label.setText("🦁")
            lion_label.setStyleSheet("font-size: 64px; background: transparent;")
        layout.addWidget(lion_label)

        title = QLabel("경고")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size: 28px; font-weight: bold; color: #D32F2F;"
            "font-family: 'Hakgyoansim Nadeuri TTF B', 'Malgun Gothic';"
            "background: transparent;"
        )
        layout.addWidget(title)

        message = QLabel(f"{window_name} 창을 곧 닫습니다")
        message.setAlignment(Qt.AlignCenter)
        message.setWordWrap(True)
        message.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #4A2A2A;"
            "font-family: 'Hakgyoansim Nadeuri TTF B', 'Malgun Gothic';"
            "background: transparent;"
        )
        layout.addWidget(message)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        for i in range(7, 0, -1):
            painter.setBrush(QColor(0, 0, 0, 11))
            painter.drawRoundedRect(i, i, self.width() - i, self.height() - i, 22, 22)
        painter.setBrush(QColor("#FFF3F3"))
        painter.drawRoundedRect(0, 0, self.width() - 7, self.height() - 7, 22, 22)
        painter.setPen(QPen(QColor("#EF5350"), 2))
        painter.drawRoundedRect(1, 1, self.width() - 9, self.height() - 9, 20, 20)


class CelebrationOverlay(QWidget):
    """전체 화면을 덮는 반투명 어둠 + 중앙 캐릭터 페이드인/아웃 + 별 폭발 → CelebrateDialog."""

    STAR_COUNT = 14                 # 사방으로 튀는 별 개수
    STAR_DISTANCE = (220, 380)      # 사자 중심으로부터 날아가는 거리 범위(px)
    STAR_DURATION_MS = 900          # 별 비행 시간 (= BURST_HOLD_MS)
    STAR_FONT_SIZE = 44
    STAR_BOX = 64
    DIM_ALPHA = 150                 # 어둠 알파 (0~255)
    FADE_IN_MS = 280                # 어둠+사자 동시 페이드인
    BURST_HOLD_MS = 900             # 별 폭발 + 사자 유지 시간
    FADE_OUT_MS = 350               # 어둠+사자 동시 페이드아웃
    LION_SIZE = 220                 # 중앙 사자 크기

    def __init__(self, goals: list[str], message: str, on_done):
        super().__init__()
        self.goals = goals
        self.message = message
        self.on_done = on_done
        self._anims = []
        self._started = False

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)

        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)
        self.setWindowOpacity(0.0)

        # 중앙 사자 — 별 발사 기준점이자 페이드 대상
        self.lion_label = QLabel(self)
        self.lion_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.lion_label.setAlignment(Qt.AlignCenter)
        self.lion_label.setStyleSheet("background: transparent;")
        self.lion_label.resize(self.LION_SIZE, self.LION_SIZE)
        px = _lion_pixmap("celebrate", self.LION_SIZE)
        if not px.isNull():
            self.lion_label.setPixmap(px)
        else:
            self.lion_label.setText("🥳")
            self.lion_label.setStyleSheet(
                f"font-size: {self.LION_SIZE - 40}px; background: transparent;"
            )
        center = self.rect().center()
        self.lion_label.move(
            center.x() - self.LION_SIZE // 2,
            center.y() - self.LION_SIZE // 2,
        )

        self.lion_effect = QGraphicsOpacityEffect(self.lion_label)
        self.lion_effect.setOpacity(0.0)
        self.lion_label.setGraphicsEffect(self.lion_effect)

    def paintEvent(self, event):
        # 위젯 자체는 투명 — 여기서 반투명 어둠을 직접 칠한다.
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, self.DIM_ALPHA))

    def showEvent(self, event):
        super().showEvent(event)
        if self._started:
            return
        self._started = True

        # Phase A — 어둠 + 사자 동시 페이드인
        self._animate_opacity(self, 0.0, 1.0, self.FADE_IN_MS)
        self._animate_opacity(self.lion_effect, 0.0, 1.0, self.FADE_IN_MS)

        # Phase B — 페이드인 끝나면 별 폭발 (사자는 표시 유지)
        QTimer.singleShot(self.FADE_IN_MS, self._burst_stars)

        # Phase C — 별 폭발 끝나면 어둠 + 사자 동시 페이드아웃
        QTimer.singleShot(
            self.FADE_IN_MS + self.BURST_HOLD_MS,
            self._fade_out,
        )

        # Phase D — 페이드아웃 끝나면 알람 다이얼로그
        QTimer.singleShot(
            self.FADE_IN_MS + self.BURST_HOLD_MS + self.FADE_OUT_MS,
            self._show_alert,
        )

    def _animate_opacity(self, target, start, end, duration_ms, easing=None):
        prop = b"windowOpacity" if target is self else b"opacity"
        anim = QPropertyAnimation(target, prop)
        anim.setDuration(duration_ms)
        anim.setStartValue(start)
        anim.setEndValue(end)
        if easing is not None:
            anim.setEasingCurve(easing)
        anim.start()
        self._anims.append(anim)
        return anim

    def _fade_out(self):
        self._animate_opacity(self, 1.0, 0.0, self.FADE_OUT_MS)
        self._animate_opacity(self.lion_effect, 1.0, 0.0, self.FADE_OUT_MS)

    def _burst_stars(self):
        center = self.rect().center()
        for i in range(self.STAR_COUNT):
            angle = (2 * math.pi * i) / self.STAR_COUNT + random.uniform(-0.15, 0.15)
            distance = random.randint(*self.STAR_DISTANCE)

            star = QLabel("⭐", self)
            star.setStyleSheet(
                f"font-size: {self.STAR_FONT_SIZE}px; background: transparent;"
            )
            star.setAttribute(Qt.WA_TransparentForMouseEvents)
            star.setAlignment(Qt.AlignCenter)

            start_rect = QRect(
                center.x() - self.STAR_BOX // 2,
                center.y() - self.STAR_BOX // 2,
                self.STAR_BOX, self.STAR_BOX,
            )
            end_rect = QRect(
                int(center.x() + math.cos(angle) * distance) - self.STAR_BOX // 2,
                int(center.y() + math.sin(angle) * distance) - self.STAR_BOX // 2,
                self.STAR_BOX, self.STAR_BOX,
            )
            star.setGeometry(start_rect)
            star.show()
            star.raise_()

            pos_anim = QPropertyAnimation(star, b"geometry")
            pos_anim.setDuration(self.STAR_DURATION_MS)
            pos_anim.setStartValue(start_rect)
            pos_anim.setEndValue(end_rect)
            pos_anim.setEasingCurve(QEasingCurve.OutQuad)

            effect = QGraphicsOpacityEffect(star)
            effect.setOpacity(1.0)
            star.setGraphicsEffect(effect)
            fade = QPropertyAnimation(effect, b"opacity")
            fade.setDuration(self.STAR_DURATION_MS)
            fade.setStartValue(1.0)
            fade.setKeyValueAt(0.5, 1.0)
            fade.setEndValue(0.0)
            fade.finished.connect(star.deleteLater)

            pos_anim.start()
            fade.start()
            self._anims.extend([pos_anim, fade])

    def _show_alert(self):
        # 어둠은 이미 0이지만 명시적으로 숨겨서 클릭 차단도 제거
        self.hide()

        dialog = CelebrateDialog(self.goals, self.message)
        screen = QApplication.primaryScreen().geometry()
        dialog.move(
            screen.center().x() - dialog.width() // 2,
            screen.center().y() - dialog.height() // 2,
        )
        dialog.exec_()
        self.close()
        if self.on_done:
            self.on_done()


def main():
    app = QApplication(sys.argv)

    _font_path = os.path.join(os.path.dirname(__file__), "fonts", "Hakgyoansim Nadeuri TTF B.ttf")
    _fid = QFontDatabase.addApplicationFont(_font_path)
    _font_families = QFontDatabase.applicationFontFamilies(_fid)
    print(f"[폰트] {_font_families}")   # 실제 패밀리 이름 확인용

    signal.signal(signal.SIGINT, signal.SIG_DFL)
    sigint_timer = QTimer()
    sigint_timer.start(500)
    sigint_timer.timeout.connect(lambda: None)

    dialog = GoalDialog()
    if dialog.exec_() != QDialog.Accepted:
        sys.exit(0)
    goals = dialog.goals
    manual_mode = dialog.manual_mode
    print(f"[목표 {len(goals)}개] {goals}")
    if manual_mode:
        print("[수동 모드] Shift+1=숨김, Shift+2=숨은 사자, Shift+3=슬픈 사자 중앙, Shift+4=완료, Shift+5=칭찬 사자 오른쪽 중앙, Ctrl+1=분노/무시")

    # --- 사자 위젯: QWidget(투명 컨테이너) + 자식 QLabel 3개 ---
    # HTML img 태그가 Qt 로컬파일 로드 미지원으로 setPixmap() 방식으로 전환.
    # 별도 top-level 창이 아닌 자식 위젯이므로 DWM 합성 quirk 없음.
    pet = QWidget()
    pet.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
    pet.setAttribute(Qt.WA_TranslucentBackground)       # 컨테이너 배경 투명
    # 너비를 사자 크기에 고정 — 메시지 길이에 따라 위젯이 가로로 늘어나면
    # 가운데 정렬된 사자가 옆으로 흔들리는 현상이 생긴다. 메시지는 wordWrap 으로 줄바꿈.
    pet.setFixedWidth(CHARACTER_SIZE)

    pet_layout = QVBoxLayout(pet)
    pet_layout.setContentsMargins(0, 0, 0, 0)
    pet_layout.setSpacing(4)

    msg_label = OutlinedLabel()                         # 메시지 — 박스 없이 흰 글자만, 평소엔 숨김
    msg_label.setAlignment(Qt.AlignCenter)
    msg_label.setWordWrap(True)
    msg_label.setContentsMargins(4, 2, 4, 4)            # 외곽선·그림자가 잘리지 않도록 여백
    msg_label.hide()
    pet_layout.addWidget(msg_label)

    lion_label = QLabel()                               # 사자 PNG — 무드별 교체
    lion_label.setAlignment(Qt.AlignCenter)
    lion_label.setStyleSheet("background: transparent;")
    lion_label.setFixedSize(CHARACTER_SIZE, CHARACTER_SIZE)
    pet_layout.addWidget(lion_label)

    hint_label = QLabel("✓ 완료시 사자 클릭")
    hint_label.setAlignment(Qt.AlignCenter)
    hint_label.setStyleSheet(
        "font-size: 14px; color: #888; background: transparent;"
        "font-family: 'Hakgyoansim Nadeuri TTF B', 'Malgun Gothic', sans-serif;"
    )
    pet_layout.addWidget(hint_label)

    screen = app.primaryScreen().availableGeometry()

    # 사용자가 드래그하면 사자 본체의 하단을 앵커로 저장. None 이면 기본 우하단.
    # 메시지 높이가 늘어나도 pet 창만 위로 커지고, 사자 본체는 같은 화면 좌표에 머문다.
    _user_anchor = None
    _pet_state = {"mood": "default", "placement": "normal"}

    def update_message_height():
        if not msg_label.isVisible():
            msg_label.setFixedHeight(0)
            return

        content_width = max(1, CHARACTER_SIZE - 8)
        metrics = QFontMetrics(msg_label.font())
        text_rect = metrics.boundingRect(
            0, 0, content_width, 10000,
            msg_label.alignment() | Qt.TextWordWrap,
            msg_label.text(),
        )
        msg_label.setFixedHeight(text_rect.height() + 8)

    def reposition():
        if _pet_state["placement"] == "center":
            pet.move(
                screen.center().x() - pet.width() // 2,
                screen.center().y() - pet.height() // 2,
            )
            return
        if _pet_state["placement"] == "right_center":
            pet.move(
                screen.left() + (screen.width() * 3) // 4 - pet.width() // 2,
                screen.center().y() - pet.height() // 2,
            )
            return

        message_block_height = (
            msg_label.height() + pet_layout.spacing()
            if msg_label.isVisible()
            else 0
        )
        lion_bottom_in_pet = message_block_height + CHARACTER_SIZE
        x_left = (
            screen.right() - pet.width() + 1
            if _pet_state["placement"] == "edge"
            else screen.right() - pet.width() - MARGIN_FROM_EDGE
        )
        if _user_anchor is None:
            default_lion_bottom = (
                screen.bottom()
                - MARGIN_FROM_EDGE
                - hint_label.height()
                - pet_layout.spacing()
            )
            pet.move(x_left, default_lion_bottom - lion_bottom_in_pet)
        else:
            anchor_x_left, lion_bottom = _user_anchor
            if _pet_state["placement"] != "edge":
                x_left = anchor_x_left
            pet.move(x_left, lion_bottom - lion_bottom_in_pet)

    def render_lion(message=None, mood="default"):
        _pet_state["mood"] = mood
        # message=None → 메시지 숨김 / 빈 문자열 포함 그 외 → 표시. 색·배경은 OutlinedLabel 이 그림.
        if message is None:
            msg_label.setText("")
            msg_label.hide()
            update_message_height()
        else:
            msg_label.setText(message)
            msg_label.setStyleSheet(
                f"font-size: {MESSAGE_FONT_SIZE}px; font-weight: bold; background: transparent;"
                f"font-family: 'Hakgyoansim Nadeuri TTF B', 'Malgun Gothic', sans-serif;"
            )
            msg_label.show()
            update_message_height()

        # 무드별 사자 PNG 교체
        px = _lion_pixmap(mood, CHARACTER_SIZE)
        if not px.isNull():
            lion_label.setPixmap(px)
        else:
            lion_label.setText("🦁")                   # PNG 없으면 이모지 폴백
            lion_label.setStyleSheet("font-size: 120px; background: transparent;")

        pet.adjustSize()
        reposition()

    # --- 타이핑 효과: 한 글자씩 출력 → 다 출력되면 일정 시간 후 자동 숨김 ---
    _type_timer = QTimer()
    _type_timer.setInterval(SPEECH_CHAR_MS)
    _revert_timer = QTimer()
    _revert_timer.setSingleShot(True)
    _speech = {"msg": "", "i": 0, "after_ms": 3000}

    def _type_tick():
        _speech["i"] += 1
        i = _speech["i"]
        msg_label.setText(_speech["msg"][:i])
        update_message_height()
        pet.adjustSize()
        reposition()
        if i >= len(_speech["msg"]):
            _type_timer.stop()
            _revert_timer.start(_speech["after_ms"])

    def show_speech(message: str, duration_ms: int = 3000, mood: str = "default"):
        _type_timer.stop()
        _revert_timer.stop()
        _pet_state["placement"] = "normal"
        _speech["msg"] = message
        _speech["i"] = 0
        _speech["after_ms"] = duration_ms
        render_lion("", mood)        # 라벨 표시(빈 상태) + 무드 갱신
        _type_timer.start()

    def show_hidden_check():
        _type_timer.stop()
        _revert_timer.stop()
        _pet_state["placement"] = "edge"
        render_lion(None, "hidden")

    def show_escalation_warning(window_name: str):
        dialog = EscalationWarningDialog(window_name)
        dialog.move(
            screen.center().x() - dialog.width() // 2,
            screen.center().y() - dialog.height() // 2,
        )
        QTimer.singleShot(ESCALATION_CLOSE_DELAY_MS, dialog.accept)
        dialog.exec_()

    def revert_speech():
        _type_timer.stop()
        _revert_timer.stop()
        _pet_state["placement"] = "normal"
        render_lion(None, "default")

    _type_timer.timeout.connect(_type_tick)
    _revert_timer.timeout.connect(revert_speech)

    render_lion(None)
    if manual_mode:
        hint_label.hide()
        pet.hide()
    else:
        pet.show()
        show_speech("안녕! 잘하고 있냥?", mood="praise")

    consecutive_off_task = 0

    def on_watch_tick():
        nonlocal consecutive_off_task

        title = get_active_window_title()
        if not title:
            print("[감시] (스킵 — 자기 자신/활성 창 없음)")
            return

        on_task = any(is_on_task(g, title) for g in goals)
        print(f"[활성창] {title!r}  →  on_task={on_task}  (off_task 누적 {consecutive_off_task}s)")

        if on_task:
            consecutive_off_task = 0
            show_speech(random.choice(PRAISE), mood="praise")
            return

        was_on_task_until_now = consecutive_off_task == 0
        consecutive_off_task += WATCH_INTERVAL_MS // 1000

        if consecutive_off_task >= ESCALATION_SECONDS:
            print(f"[에스컬레이션] {consecutive_off_task}s 연속 off-task → 창 닫기 시도")
            target_hwnd, target_title = get_active_window_info()
            target_name = _window_display_name(target_title or title)
            show_speech(ESCALATION_WARNING, duration_ms=2500, mood="angry")
            show_escalation_warning(target_name)
            if close_window(target_hwnd):
                show_speech(f"({target_name})창 꺼버린다냥!", duration_ms=3500, mood="angry")
            consecutive_off_task = 0
            return

        if was_on_task_until_now:
            show_hidden_check()
        elif consecutive_off_task <= WATCH_INTERVAL_MS // 1000 * 5:
            show_speech(random.choice(SAD), mood="sad")
        else:
            show_speech(random.choice(ANGRY), mood="angry")

    watch_timer = QTimer()
    watch_timer.timeout.connect(on_watch_tick)
    if not manual_mode:
        watch_timer.start(WATCH_INTERVAL_MS)

    _manual_hotkey_down = {"1": False, "2": False, "3": False, "4": False, "5": False, "ctrl+1": False}
    _manual_ignore_count = 0

    def _is_key_down(vk: int) -> bool:
        return bool(win32api.GetAsyncKeyState(vk) & 0x8000)

    def _show_manual_blank():
        _type_timer.stop()
        _revert_timer.stop()
        pet.hide()

    def _show_manual_hidden():
        _type_timer.stop()
        _revert_timer.stop()
        hint_label.hide()
        _pet_state["placement"] = "edge"
        render_lion(None, "hidden")
        pet.show()
        pet.raise_()

    def _show_manual_sad_center():
        _type_timer.stop()
        _revert_timer.stop()
        hint_label.hide()
        show_speech(random.choice(SAD), mood="sad")
        _pet_state["placement"] = "center"
        reposition()
        pet.show()
        pet.raise_()

    def _show_manual_praise_right_center():
        nonlocal _manual_ignore_count
        _manual_ignore_count = 0
        _type_timer.stop()
        _revert_timer.stop()
        hint_label.hide()
        show_speech(random.choice(PRAISE), mood="praise")
        _pet_state["placement"] = "right_center"
        reposition()
        pet.show()
        pet.raise_()

    def _show_manual_angry_ignore():
        nonlocal _manual_ignore_count
        _type_timer.stop()
        _revert_timer.stop()
        hint_label.hide()
        _manual_ignore_count += 1
        show_speech(random.choice(ANGRY), mood="angry")
        pet.show()
        pet.raise_()

        if _manual_ignore_count >= 5:
            print("[수동 에스컬레이션] Shift+6 5회 입력 → 창 닫기 시도")
            target_hwnd, target_title = get_active_window_info()
            target_name = _window_display_name(target_title)
            show_speech(ESCALATION_WARNING, duration_ms=2500, mood="angry")
            show_escalation_warning(target_name)
            if close_window(target_hwnd):
                show_speech(f"({target_name})창 꺼버린다냥!", duration_ms=3500, mood="angry")
            _manual_ignore_count = 0

    def _show_manual_complete():
        on_complete()

    def on_manual_hotkey_tick():
        shift_down = _is_key_down(win32con.VK_SHIFT)
        for key, action in (
            ("1", _show_manual_blank),
            ("2", _show_manual_hidden),
            ("3", _show_manual_sad_center),
            ("4", _show_manual_complete),
            ("5", _show_manual_praise_right_center),
        ):
            pressed = shift_down and _is_key_down(ord(key))
            if pressed and not _manual_hotkey_down[key]:
                action()
            _manual_hotkey_down[key] = pressed

        ctrl1_pressed = _is_key_down(win32con.VK_CONTROL) and _is_key_down(ord("1"))
        if ctrl1_pressed and not _manual_hotkey_down["ctrl+1"]:
            _show_manual_angry_ignore()
        _manual_hotkey_down["ctrl+1"] = ctrl1_pressed

    manual_hotkey_timer = QTimer()
    if manual_mode:
        manual_hotkey_timer.setInterval(50)
        manual_hotkey_timer.timeout.connect(on_manual_hotkey_tick)
        manual_hotkey_timer.start()

    # 자식 위젯 마우스 이벤트를 부모(pet)로 통과 — 핸들러는 pet 하나만 관리
    for w in (lion_label, msg_label, hint_label):
        w.setAttribute(Qt.WA_TransparentForMouseEvents)

    _drag_origin = None   # 드래그 시작 시 pet 좌상단 기준점
    _drag_start = None    # 드래그 시작 커서 위치 (5px 임계 판정용)
    _is_dragging = False  # True 면 드래그 중, False 면 클릭 가능성
    _overlay_ref = []     # CelebrationOverlay GC 방지용 보관

    def on_complete():
        """완료 처리 — 감시 중단 → 전체화면 별 폭발 오버레이 → 축하 모달 → 앱 종료."""
        watch_timer.stop()
        pet.mousePressEvent = lambda e: None
        pet.mouseMoveEvent = lambda e: None
        pet.mouseReleaseEvent = lambda e: None
        pet.hide()

        msg = random.choice(CELEBRATE)
        overlay = CelebrationOverlay(goals, msg, on_done=app.quit)
        _overlay_ref.append(overlay)   # 지역변수만으로는 GC 가능성 있음
        overlay.show()

    def pet_mouse_press(event):
        nonlocal _drag_origin, _drag_start, _is_dragging
        if event.button() == Qt.LeftButton:
            _drag_start = event.globalPos()
            _drag_origin = event.globalPos() - pet.frameGeometry().topLeft()
            _is_dragging = False
            event.accept()

    def pet_mouse_move(event):
        nonlocal _is_dragging
        if event.buttons() & Qt.LeftButton and _drag_start is not None:
            # 5px 초과 이동 시 드래그로 확정
            if not _is_dragging and (event.globalPos() - _drag_start).manhattanLength() > 5:
                _is_dragging = True
            if _is_dragging:
                pet.move(event.globalPos() - _drag_origin)
                event.accept()

    def pet_mouse_release(event):
        nonlocal _drag_start, _is_dragging, _user_anchor
        if event.button() == Qt.LeftButton:
            if not _is_dragging:
                on_complete()   # 드래그 없이 뗐으면 클릭 → 완료
            else:
                _user_anchor = (pet.x(), pet.y() + lion_label.y() + lion_label.height())
            _drag_start = None
            _is_dragging = False
            event.accept()

    pet.mousePressEvent = pet_mouse_press
    pet.mouseMoveEvent = pet_mouse_move
    pet.mouseReleaseEvent = pet_mouse_release

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
