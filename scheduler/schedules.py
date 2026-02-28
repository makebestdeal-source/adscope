"""페르소나별/요일별 수집 스케줄 — 미디어 이용 패턴 기반 자동 생성.

Phase 3B: 14명 페르소나 × 하루 3회 = 42슬롯 (평일/주말 각각).
Phase 5: 봇 탐지 회피를 위해 랜덤 3-8분 간격 오프셋 적용.
"""

import random
from dataclasses import dataclass

from crawler.config import crawler_settings
from crawler.personas.media_patterns import MEDIA_PATTERNS
from crawler.personas.profiles import PERSONAS


@dataclass(frozen=True)
class ScheduleSlot:
    persona_code: str
    time: str  # HH:MM
    device: str  # "pc" | "mobile"
    label: str


def _offset_time(base_time: str, offset_minutes: int) -> str:
    """HH:MM 시간에 오프셋(분) 적용."""
    h, m = map(int, base_time.split(":"))
    total = h * 60 + m + offset_minutes
    total = total % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def generate_schedules(day_type: str = "weekday") -> list[ScheduleSlot]:
    """미디어 이용 패턴 기반 스케줄 자동 생성.

    Args:
        day_type: "weekday" 또는 "weekend"

    Returns:
        ScheduleSlot 리스트 (14명 × 3회 = 42슬롯)
    """
    slots: list[ScheduleSlot] = []
    offset_minutes = 0

    for code, persona in PERSONAS.items():
        if persona.age_group and persona.gender:
            pattern = MEDIA_PATTERNS.get((persona.age_group, persona.gender))
            if pattern:
                peak_hours = (
                    pattern.peak_hours_weekday
                    if day_type == "weekday"
                    else pattern.peak_hours_weekend
                )
            else:
                peak_hours = ("09:00", "14:00", "20:00")
        else:
            # 제어 그룹: 표준 3회 시간
            peak_hours = ("09:00", "14:00", "20:00")

        device = persona.primary_device or "mobile_galaxy"
        device_short = "mobile" if "mobile" in device else "pc"

        labels = ["피크1", "피크2", "피크3"]
        for i, peak_time in enumerate(peak_hours[:3]):
            adjusted = _offset_time(peak_time, offset_minutes)
            age_label = persona.age_group or "CTRL"
            gender_label = persona.gender or ""

            slots.append(
                ScheduleSlot(
                    persona_code=code,
                    time=adjusted,
                    device=device_short,
                    label=f"{age_label} {gender_label} {labels[i]}".strip(),
                )
            )
            offset_minutes += random.randint(
                crawler_settings.schedule_offset_min_minutes,
                crawler_settings.schedule_offset_max_minutes,
            )

    return slots


# 모듈 로드 시 스케줄 자동 생성
WEEKDAY_SCHEDULE: list[ScheduleSlot] = generate_schedules("weekday")
WEEKEND_SCHEDULE: list[ScheduleSlot] = generate_schedules("weekend")
