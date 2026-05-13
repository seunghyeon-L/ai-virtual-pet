# watcher.py — Step 4: 현재 활성 창의 제목을 반환하는 단일 함수.
# 자기 자신(=이 파이썬 프로세스)이 활성 창이면 빈 문자열을 반환해
# pet.py 가 그 사이클을 스킵할 수 있게 한다 (BRIEF.md §11.4 회피).

import os               # 자기 PID 조회 — 자기 창 회피 비교에 사용
import win32gui         # Windows GUI API 바인딩 — 활성 창 핸들/제목 조회
import win32process     # 창 ↔ 프로세스 매핑 — 핸들로 PID 알아내기
import win32con         # Windows 메시지 상수 모음 — WM_CLOSE 등


def get_active_window_title() -> str:
    """현재 포그라운드 창의 제목을 반환. 활성 창이 없거나 자기 자신이면 빈 문자열."""
    hwnd = win32gui.GetForegroundWindow()              # 포그라운드 창의 핸들(HWND, 정수). 없으면 0.
    if hwnd == 0:                                      # 활성 창이 아예 없는 드문 경우 → 스킵 신호
        return ""

    _, pid = win32process.GetWindowThreadProcessId(hwnd)  # (스레드ID, 프로세스ID) 튜플 반환 — pid만 사용
    if pid == os.getpid():                             # 자기 자신이 활성이면 → 자기 회피용 빈 문자열
        return ""

    return win32gui.GetWindowText(hwnd)                # 창 타이틀바의 텍스트 반환 (없으면 자동으로 빈 문자열)


def get_active_window_info() -> tuple[int, str]:
    """현재 포그라운드 창의 (핸들, 제목)을 반환. 활성 창이 없거나 자기 자신이면 (0, "")."""
    hwnd = win32gui.GetForegroundWindow()
    if hwnd == 0:
        return 0, ""

    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    if pid == os.getpid():
        return 0, ""

    return hwnd, win32gui.GetWindowText(hwnd)


def close_window(hwnd: int) -> bool:
    """지정한 창 핸들에 WM_CLOSE 전송. 자기 자신/없는 창이면 False."""
    if not hwnd or not win32gui.IsWindow(hwnd):
        return False

    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    if pid == os.getpid():
        return False

    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
    return True


def close_active_window() -> bool:
    """현재 활성 창에 WM_CLOSE 메시지 전송 (X 버튼 누른 것과 동일).
    자기 자신은 절대 안 닫음. 닫기 시도했으면 True, 스킵했으면 False 반환."""
    hwnd = win32gui.GetForegroundWindow()              # 현재 포그라운드 창의 핸들
    if hwnd == 0:                                      # 활성 창이 없는 경우 → 스킵
        return False

    _, pid = win32process.GetWindowThreadProcessId(hwnd)  # 창의 프로세스 ID 조회
    if pid == os.getpid():                             # 자기 자신이면 → 절대 닫지 말 것 (자기 펫 자살 방지)
        return False

    # WM_CLOSE 송신 — 비동기, 즉시 반환. 앱이 받아서 정중하게 처리 (저장 다이얼로그 등도 가능)
    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
    return True
