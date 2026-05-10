# Troubleshooting

이 프로젝트에서 만난 이슈와 해결 방법을 기록한다. 새 이슈가 생기면 가장 위에 추가.

---

## 1. PyQt5 말풍선 좌표·사이즈·`isVisible=True` 인데 화면에 안 보임

**날짜**: 2026-05-09
**관련 파일**: [speech_bubble.py](speech_bubble.py)

### 증상

- `SpeechBubble` 인스턴스 생성 후 진단 출력이 모두 정상:
  - 좌표가 화면 안에 있음 (예: pos=(2350,1132) size=(153x39))
  - `isVisible=True`
- 그런데 실제 화면엔 아무것도 안 그려짐 (사자 위에 빈 공간)

### 원인

Qt 5.15 (Windows) 에서 `QLabel` 에 다음 둘을 동시에 적용하면 페인팅 quirk 발생:
1. `setAttribute(Qt.WA_TranslucentBackground)` — 위젯 배경 전체 투명화
2. 스타일시트의 `background-color: rgba(...)` — 둥근 흰 배경 그리기

Qt가 라벨의 배경 페인팅을 건너뛰고 완전 투명한 사각형만 그려버림. 텍스트도 같이 사라져 빈 공간으로 보임. `isVisible` 은 True 라 디버깅이 까다로움.

### 시도한 해결책들

#### v2 (실패) — 컨테이너 패턴

`QWidget` 컨테이너 + 자식 `QLabel` 에만 스타일 적용. 책임 분리하면 자식 라벨이 평범하게 그려질 거라 기대했음.

```python
class SpeechBubble(QWidget):
    def __init__(self, ...):
        self.setAttribute(Qt.WA_TranslucentBackground)
        label = QLabel(text)
        label.setStyleSheet("QLabel { background-color: rgba(...); border-radius: 12px; ... }")
        layout = QVBoxLayout(self)
        layout.addWidget(label)
```

**왜 실패**: 부모 위젯의 `WA_TranslucentBackground` 가 자식의 페인팅에까지 영향을 주는 듯. 자식 라벨도 동일하게 빈 투명창으로 그려짐. 환경 의존(고DPI/멀티모니터?) 으로 추정되지만 정확한 원인 미확인.

#### v3 (실패) — `QPainter` 로 직접 그리기

`paintEvent` 를 오버라이드해 스타일시트를 거치지 않고 둥근 사각형 + 텍스트를 직접 그림.

```python
class SpeechBubble(QWidget):
    def __init__(self, text, anchor, lifetime_ms=3000):
        super().__init__()
        self._text = text
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._font = QFont("Malgun Gothic", 11)
        # 텍스트 크기 측정 후 위젯 크기 확정
        metrics = QFontMetrics(self._font)
        text_rect = metrics.boundingRect(text)
        self.resize(text_rect.width() + 28, text_rect.height() + 20)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(255, 255, 255, 240))
        painter.setPen(QPen(QColor(51, 51, 51), 2))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 12, 12)
        painter.setPen(QColor(34, 34, 34))
        painter.setFont(self._font)
        painter.drawText(self.rect(), Qt.AlignCenter, self._text)
```

**왜 실패**: `[bubble v3] visible=True` 인데 화면엔 여전히 안 보임. 추정 원인: 사용자 환경(4K 고DPI 모니터) 에서 `WA_TranslucentBackground` + 프레임 없는 top-level 창의 합성이 Windows DWM 단계에서 누락되는 듯. 사자는 보이는데 말풍선은 안 보이는 차이는 — 사자는 `QLabel` 의 텍스트 페인팅이 별도 코드 경로라 영향을 안 받았기 때문으로 보임. 즉 `WA_TranslucentBackground` 자체가 이 환경에서 우리 paintEvent 결과물에 적용 안 되는 게 진짜 원인.

#### v4 (실패) — `WA_TranslucentBackground` 포기, 평범한 사각형

투명 배경 자체를 빼고 단순한 흰 직사각형으로 후퇴. 둥근 모서리 / 투명 외곽선 포기.

```python
class SpeechBubble(QLabel):
    def __init__(self, text, anchor, lifetime_ms=3000):
        super().__init__(text)
        self.setWindowFlags(Qt.FramelessWindowHint
                            | Qt.WindowStaysOnTopHint
                            | Qt.Tool)
        # WA_TranslucentBackground 안 씀
        self.setStyleSheet("""
            QLabel {
                background-color: #ffffff;
                color: #222222;
                border: 2px solid #333333;
                padding: 10px 14px;
                font-size: 14px;
                font-family: 'Malgun Gothic', sans-serif;
            }
        """)
        self.adjustSize()
        # ... place above, timer, show, raise
```

**왜 실패**: v4 도 안 보임. `[bubble v4] visible=True` 인데 화면엔 사각형 없음. 투명 배경이 아닌데도 안 보인다는 건 **두 번째 frameless top-level 창 자체가 이 환경에서 합성되지 않음**을 의미.

#### v5 (실패) — 거대 노란 사각, 화면 정중앙

위치/크기/색을 극단으로 키워서 어디에든 보이는지 확인. 400x200 노란 배경 + 빨간 5px 테두리 + 화면 정중앙. `Qt.Tool` 도 제거(혹시 Tool 이 hidden 되는 환경인지 검증).

**결과**: 콘솔 `pos=(1080,596) size=(400x200) visible=True` 정상. 화면엔 여전히 안 보임. **결정적 — 사자 외 추가 frameless top-level 창은 어떤 옵션 조합이든 이 환경에서 안 그려짐.**

#### v6 (성공) — 사자의 QLabel 텍스트를 동적으로 변경 (별도 창 X)

별도 윈도우 패턴 자체를 포기. 사자 라벨에 `setText()` 로 HTML 을 넣어 메시지를 사자 위에 인라인 표시.

```python
def show_speech(message: str, duration_ms: int = 3000):
    html = (
        f"<div style='font-size: 22px; font-weight: bold; color: #000;"
        f"background-color: rgba(255,255,255,255); padding: 6px 10px;'>{message}</div>"
        f"<div style='font-size: 120px;'>🦁</div>"
    )
    pet.setText(html)
    pet.adjustSize()
    reposition()                              # 사자가 우하단에 유지되도록
    QTimer.singleShot(duration_ms, revert_speech)

def revert_speech():
    pet.setText("🦁")
    pet.adjustSize()
    reposition()
```

**왜 작동하는가**: 사자 라벨은 첫 (그리고 유일한) top-level 창이라 정상 렌더됨. 메시지를 새 창 만드는 대신 같은 라벨의 텍스트를 HTML 로 바꿔치기. 합성 quirk 가 발생할 윈도우가 추가로 생기지 않음.

### 시각적 trade-off (v6)

- ❌ 둥근 풍선 모양 / 사자와 분리된 떠 있는 느낌
- ✅ 메시지가 보임 (이게 우선)
- 메시지 박스: 흰 배경 + 검정 굵은 글씨, 어떤 데스크탑 색에서도 가독성 OK

### 검증

- 사자 등장 직후 사자 위에 흰 사각 안 텍스트 `안녕! 잘하고 있냥?` 보임 → 3초 후 사자만 남음
- 사자가 늘 우하단 같은 위치에 유지 (메시지 표시/해제 시 매번 reposition)

### 학습한 것

- **PyQt5 의 두 번째 frameless top-level 창은 환경 의존성이 매우 큼** — 고DPI / Windows DWM / 그래픽 드라이버 조합에서 합성 실패 가능
- "단일 창 안에서 모든 시각 변화를 처리" 가 가장 robust 한 패턴
- 이후 완료 버튼 등 추가 UI 도 가급적 같은 사자 라벨 안에 통합하거나, 정 별도 위젯이 필요하면 사자 라벨의 자식(child) 위젯으로 둘 것 — top-level 창은 추가하지 말 것

---
