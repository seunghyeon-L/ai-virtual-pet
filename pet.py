# pet.py — 사자 PNG 이미지 기반 버전.
# QWidget(투명 컨테이너) 안에 msg_label + lion_label + hint_label 을 쌓아서 표시.
# HTML img 태그 방식은 Qt 로컬 파일 로드 미지원으로 폐기 → setPixmap() 사용.

import sys
import os
import signal
import random
import math
from PyQt5.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect,
)
from PyQt5.QtGui import QPixmap, QPainter, QColor
from PyQt5.QtWidgets import (
    QApplication, QLabel, QWidget,
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QListWidget, QListWidgetItem, QGraphicsOpacityEffect,
)

from watcher import get_active_window_title, close_active_window
from judge import is_on_task
from messages import PRAISE, ANGRY, SAD, CELEBRATE

# --- 사자 이미지 설정 ---
BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")  # PNG 파일 기준 폴더
CHARACTER_SIZE = 200            # 사자 이미지 표시 크기(px)
MESSAGE_FONT_SIZE = 22          # 메시지 텍스트 크기(px)
MARGIN_FROM_EDGE = 50           # 화면 우하단 여백(px)

LION_IMAGES = {                 # 무드 → PNG 파일명
    "default":   "lion_default.png",
    "praise":    "lion_praise.png",
    "angry":     "lion_angry.png",
    "sad":       "lion_sad.png",
    "celebrate": "lion_celebrate.png",
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


# --- 감시/에스컬레이션 타이밍 ---
WATCH_INTERVAL_MS = 5000
ESCALATION_SECONDS = 300
ESCALATION_WARNING = "5분이나 무시해? 창 닫는다!"

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
        padding: 14px; font-family: 'Malgun Gothic', sans-serif;
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
    """첫 진입 — 여러 목표 추가/삭제 frameless 모달."""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setFixedSize(440, 560)
        self.setStyleSheet(DIALOG_STYLE)
        self.goals: list[str] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 24, 36, 24)
        layout.setSpacing(10)

        header = QLabel("AI 스터디카페  ⠿⠿  (드래그로 이동)")
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet(
            "font-size: 11px; color: #ff9800; font-weight: bold;"
            "letter-spacing: 2px; font-family: 'Malgun Gothic', sans-serif;"
        )
        layout.addWidget(header)

        lion_label = QLabel()
        lion_label.setAlignment(Qt.AlignCenter)
        px = _lion_pixmap("default", 80)
        if not px.isNull():
            lion_label.setPixmap(px)
        else:
            lion_label.setText("🦁")
            lion_label.setStyleSheet("font-size: 56px;")
        layout.addWidget(lion_label)

        prompt = QLabel("오늘 목표 다 적어내냥")
        prompt.setAlignment(Qt.AlignCenter)
        prompt.setStyleSheet(
            "font-size: 20px; font-weight: bold; color: #333333;"
            "font-family: 'Malgun Gothic', sans-serif;"
        )
        layout.addWidget(prompt)

        hint = QLabel("입력 후 Enter 또는 [+ 추가] 로 여러 개 추가")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet(
            "font-size: 12px; color: #888888; font-family: 'Malgun Gothic', sans-serif;"
        )
        layout.addWidget(hint)

        input_row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("예: Python 공부")
        self.input.setStyleSheet("""
            QLineEdit {
                font-size: 15px; padding: 10px;
                border: 2px solid #e0e0e0; border-radius: 8px;
                background-color: white; color: #333333;
                font-family: 'Malgun Gothic', sans-serif;
            }
            QLineEdit:focus { border: 2px solid #ff9800; }
        """)
        self.input.returnPressed.connect(self._add_goal)
        add_btn = QPushButton("+ 추가")
        add_btn.setStyleSheet("""
            QPushButton {
                font-size: 14px; font-weight: bold; color: white;
                background-color: #ffa726; border: none; border-radius: 8px;
                padding: 10px 16px; font-family: 'Malgun Gothic', sans-serif;
            }
            QPushButton:hover { background-color: #ff7043; }
        """)
        add_btn.clicked.connect(self._add_goal)
        input_row.addWidget(self.input, 1)
        input_row.addWidget(add_btn)
        layout.addLayout(input_row)

        self.goals_list = QListWidget()
        self.goals_list.setStyleSheet("""
            QListWidget {
                font-size: 14px; border: 2px solid #e0e0e0;
                border-radius: 8px; background-color: white;
                font-family: 'Malgun Gothic', sans-serif;
            }
            QListWidget::item { border-bottom: 1px solid #f0f0f0; }
            QListWidget::item:selected { background-color: #fff4e0; color: #333; }
        """)
        layout.addWidget(self.goals_list, 1)

        self.start_btn = QPushButton("시작하기")
        self.start_btn.setStyleSheet(BUTTON_STYLE)
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self._on_start)
        layout.addWidget(self.start_btn)

        esc_hint = QLabel("ESC 키로 취소")
        esc_hint.setAlignment(Qt.AlignCenter)
        esc_hint.setStyleSheet(
            "font-size: 11px; color: #aaaaaa; font-family: 'Malgun Gothic', sans-serif;"
        )
        layout.addWidget(esc_hint)

    def _add_goal(self):
        text = self.input.text().strip()
        if not text:
            return
        item = QListWidgetItem()
        item.setData(Qt.UserRole, text)
        widget = QWidget()
        h = QHBoxLayout(widget)
        h.setContentsMargins(10, 4, 6, 4)
        h.setSpacing(8)
        label = QLabel(text)
        label.setStyleSheet("font-size: 14px; color: #333; font-family: 'Malgun Gothic', sans-serif;")
        delete_btn = QPushButton("✕")
        delete_btn.setFixedSize(26, 26)
        delete_btn.setStyleSheet("""
            QPushButton { color: #aaa; background: transparent; border: none;
                          font-size: 14px; font-weight: bold; }
            QPushButton:hover { color: #b71c1c; }
        """)
        delete_btn.clicked.connect(lambda: self._remove_item(item))
        h.addWidget(label, 1)
        h.addWidget(delete_btn)
        item.setSizeHint(widget.sizeHint())
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
        if event.key() == Qt.Key_Escape:
            self.reject()
        elif event.key() == Qt.Key_Delete:
            for it in self.goals_list.selectedItems():
                self._remove_item(it)
        else:
            super().keyPressEvent(event)


class CelebrateDialog(DraggableDialog):
    """완료 클릭 시 축하 모달. 별 폭발 애니메이션은 CelebrationOverlay 가 담당."""

    def __init__(self, goals: list[str], message: str):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setFixedSize(420, 500)
        self.setStyleSheet(DIALOG_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(14)

        header = QLabel("AI 스터디카페")
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet(
            "font-size: 12px; color: #ff9800; font-weight: bold;"
            "letter-spacing: 2px; font-family: 'Malgun Gothic', sans-serif;"
        )
        layout.addWidget(header)

        lion_label = QLabel()
        lion_label.setAlignment(Qt.AlignCenter)
        px = _lion_pixmap("celebrate", 120)
        if not px.isNull():
            lion_label.setPixmap(px)
        else:
            lion_label.setText("🥳")
            lion_label.setStyleSheet("font-size: 100px;")
        layout.addWidget(lion_label)

        title = QLabel("오늘 목표 클리어!")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size: 26px; font-weight: bold; color: #ff9800;"
            "font-family: 'Malgun Gothic', sans-serif;"
        )
        layout.addWidget(title)

        goals_text = "\n".join(f"• {g}" for g in goals)
        recap = QLabel(goals_text)
        recap.setAlignment(Qt.AlignCenter)
        recap.setWordWrap(True)
        recap.setStyleSheet(
            "font-size: 14px; color: #666666; font-style: italic;"
            "font-family: 'Malgun Gothic', sans-serif;"
        )
        layout.addWidget(recap)

        sajaa_msg = QLabel(message)
        sajaa_msg.setAlignment(Qt.AlignCenter)
        sajaa_msg.setWordWrap(True)
        sajaa_msg.setStyleSheet(
            "font-size: 16px; color: #5d4037; font-weight: bold;"
            "padding: 12px; background-color: #fff8d0;"
            "font-family: 'Malgun Gothic', sans-serif;"
        )
        layout.addWidget(sajaa_msg)

        button = QPushButton("좋다, 마무리하자")
        button.setStyleSheet(BUTTON_STYLE)
        button.clicked.connect(self.accept)
        layout.addWidget(button)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Escape, Qt.Key_Return, Qt.Key_Enter):
            self.accept()
        else:
            super().keyPressEvent(event)


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

    signal.signal(signal.SIGINT, signal.SIG_DFL)
    sigint_timer = QTimer()
    sigint_timer.start(500)
    sigint_timer.timeout.connect(lambda: None)

    dialog = GoalDialog()
    if dialog.exec_() != QDialog.Accepted:
        sys.exit(0)
    goals = dialog.goals
    print(f"[목표 {len(goals)}개] {goals}")

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

    msg_label = QLabel()                                # 메시지 박스 — 평소엔 숨김
    msg_label.setAlignment(Qt.AlignCenter)
    msg_label.setWordWrap(True)
    msg_label.hide()
    pet_layout.addWidget(msg_label)

    lion_label = QLabel()                               # 사자 PNG — 무드별 교체
    lion_label.setAlignment(Qt.AlignCenter)
    lion_label.setStyleSheet("background: transparent;")
    pet_layout.addWidget(lion_label)

    hint_label = QLabel("✓ 완료시 사자 클릭")
    hint_label.setAlignment(Qt.AlignCenter)
    hint_label.setStyleSheet(
        "font-size: 14px; color: #888; background: transparent;"
        "font-family: 'Malgun Gothic', sans-serif;"
    )
    pet_layout.addWidget(hint_label)

    screen = app.primaryScreen().availableGeometry()

    # 사용자가 드래그하면 위젯 하단-좌측을 앵커로 저장. None 이면 기본 우하단.
    # 하단 기준이라야 메시지가 위로 펼쳐질 때 사자 본체가 제자리에 머무른다.
    _user_anchor = None

    def reposition():
        if _user_anchor is None:
            pet.move(
                screen.right() - pet.width() - MARGIN_FROM_EDGE,
                screen.bottom() - pet.height() - MARGIN_FROM_EDGE,
            )
        else:
            x_left, y_bottom = _user_anchor
            pet.move(x_left, y_bottom - pet.height())

    def render_lion(message=None, mood="default"):
        # 메시지 유무에 따라 msg_label 표시/숨김
        if message:
            style = MOOD_STYLES.get(mood, MOOD_STYLES["default"])
            msg_label.setText(message)
            msg_label.setStyleSheet(
                f"font-size: {MESSAGE_FONT_SIZE}px; font-weight: bold;"
                f"color: {style['text']}; background-color: {style['bg']};"
                f"padding: 8px 14px; font-family: 'Malgun Gothic', sans-serif;"
            )
            msg_label.show()
        else:
            msg_label.hide()

        # 무드별 사자 PNG 교체
        px = _lion_pixmap(mood, CHARACTER_SIZE)
        if not px.isNull():
            lion_label.setPixmap(px)
        else:
            lion_label.setText("🦁")                   # PNG 없으면 이모지 폴백
            lion_label.setStyleSheet("font-size: 120px; background: transparent;")

        pet.adjustSize()
        reposition()

    def show_speech(message: str, duration_ms: int = 3000, mood: str = "default"):
        render_lion(message, mood)
        QTimer.singleShot(duration_ms, revert_speech)

    def revert_speech():
        render_lion(None, "default")

    render_lion(None)
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

        consecutive_off_task += WATCH_INTERVAL_MS // 1000

        if consecutive_off_task >= ESCALATION_SECONDS:
            print(f"[에스컬레이션] {consecutive_off_task}s 연속 off-task → 창 닫기 시도")
            show_speech(ESCALATION_WARNING, duration_ms=2500, mood="angry")
            QTimer.singleShot(2000, close_active_window)
            consecutive_off_task = 0
            return

        if random.random() < 0.5:
            show_speech(random.choice(ANGRY), mood="angry")
        else:
            show_speech(random.choice(SAD), mood="sad")

    watch_timer = QTimer()
    watch_timer.start(WATCH_INTERVAL_MS)
    watch_timer.timeout.connect(on_watch_tick)

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
                _user_anchor = (pet.x(), pet.y() + pet.height())
            _drag_start = None
            _is_dragging = False
            event.accept()

    pet.mousePressEvent = pet_mouse_press
    pet.mouseMoveEvent = pet_mouse_move
    pet.mouseReleaseEvent = pet_mouse_release

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
