"""SSE Event Bus — 크롤링/프로세서 이벤트를 프론트엔드로 실시간 푸시.

사용법:
  from api.event_bus import event_bus
  await event_bus.publish("crawl_complete", {"channel": "youtube_ads", "new_ads": 42})
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import AsyncGenerator

logger = logging.getLogger("adscope.event_bus")

# 이벤트 타입 상수
EVT_CRAWL_COMPLETE = "crawl_complete"
EVT_CRAWL_START = "crawl_start"
EVT_DATA_UPDATED = "data_updated"
EVT_AI_ENRICH_DONE = "ai_enrich_done"
EVT_CAMPAIGN_REBUILT = "campaign_rebuilt"
EVT_HEARTBEAT = "heartbeat"


@dataclass
class SSEEvent:
    event: str
    data: dict
    timestamp: float = field(default_factory=time.time)

    def format_sse(self) -> str:
        """SSE 프로토콜 형식으로 직렬화."""
        payload = json.dumps({**self.data, "_ts": self.timestamp}, ensure_ascii=False)
        return f"event: {self.event}\ndata: {payload}\n\n"


class EventBus:
    """비동기 pub/sub 이벤트 버스 (인메모리).

    여러 SSE 클라이언트가 subscribe하면 각자의 큐에 이벤트가 복제됩니다.
    """

    def __init__(self, max_history: int = 50):
        self._subscribers: list[asyncio.Queue] = []
        self._history: list[SSEEvent] = []
        self._max_history = max_history
        self._lock = asyncio.Lock()

    async def publish(self, event_type: str, data: dict | None = None):
        """이벤트 발행 — 모든 구독자 큐에 전달."""
        evt = SSEEvent(event=event_type, data=data or {})

        async with self._lock:
            # 히스토리 유지
            self._history.append(evt)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

            # 각 구독자 큐에 넣기
            dead: list[asyncio.Queue] = []
            for q in self._subscribers:
                try:
                    q.put_nowait(evt)
                except asyncio.QueueFull:
                    dead.append(q)
            # 꽉 찬 큐 제거
            for q in dead:
                self._subscribers.remove(q)

        logger.debug("Event published: %s (%d subscribers)", event_type, len(self._subscribers))

    async def subscribe(self, since_ts: float = 0) -> AsyncGenerator[SSEEvent, None]:
        """SSE 스트림 구독.

        since_ts > 0 이면 해당 시각 이후 히스토리를 먼저 재생합니다.
        """
        q: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=100)

        async with self._lock:
            self._subscribers.append(q)

            # 히스토리 재생 (재연결 시 놓친 이벤트 복구)
            if since_ts > 0:
                for evt in self._history:
                    if evt.timestamp > since_ts:
                        try:
                            q.put_nowait(evt)
                        except asyncio.QueueFull:
                            break

        try:
            while True:
                evt = await q.get()
                yield evt
        finally:
            async with self._lock:
                if q in self._subscribers:
                    self._subscribers.remove(q)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


# 싱글톤 인스턴스
event_bus = EventBus()
