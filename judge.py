# judge.py — Step 5: 사용자 목표와 활성 창 제목을 비교해 "현재 on-task 인가?" 판정.
# 가장 단순한 룰 기반 — 목표를 공백으로 쪼갠 단어 중 하나라도 창 제목에
# case-insensitive substring 으로 포함되면 True (PLAN.md/BRIEF.md D1).


def is_on_task(goal: str, title: str) -> bool:
    """목표 단어 중 하나라도 창 제목에 포함되면 True."""
    if not goal or not title:                       # 둘 중 하나라도 비어있으면 판정 불가 → 안전하게 False
        return False                                #   (호출자는 보통 빈 title 시 사이클을 스킵하지만, 방어적으로 처리)

    title_lower = title.lower()                     # 비교 위해 창 제목을 소문자로 정규화 (영문 대소문자 차이 무시)
    return any(                                     # 어느 단어라도 매칭되면 True
        word.lower() in title_lower                 #   - 각 단어도 소문자로 변환 후 substring 검사
        for word in goal.split()                    #   - 목표 문자열을 공백으로 split → 단어 토큰들
    )
