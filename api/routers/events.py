"""SSE (Server-Sent Events) 엔드포인트 — 실시간 데이터 업데이트 스트림."""

import asyncio
import logging

from fastapi import APIRouter, Request, Query
from fastapi.responses import StreamingResponse

from api.event_bus import event_bus, EVT_HEARTBEAT

logger = logging.getLogger("adscope.events")

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("/stream")
async def sse_stream(
    request: Request,
    last_event_ts: float = Query(default=0, description="마지막으로 수신한 이벤트 타임스탬프"),
):
    """SSE 스트림 엔드포인트.

    프론트엔드에서 EventSource로 연결하면 크롤링 완료, 데이터 갱신 등
    이벤트를 실시간으로 수신합니다.

    재연결 시 last_event_ts 파라미터로 놓친 이벤트를 복구할 수 있습니다.
    """

    async def generate():
        try:
            # 30초마다 heartbeat 전송 (연결 유지)
            heartbeat_task = asyncio.create_task(_heartbeat_loop())

            async for evt in event_bus.subscribe(since_ts=last_event_ts):
                # 클라이언트 연결 끊김 감지
                if await request.is_disconnected():
                    break
                yield evt.format_sse()
        except asyncio.CancelledError:
            pass
        finally:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # nginx SSE 버퍼링 방지
        },
    )


@router.get("/status")
async def event_status():
    """현재 SSE 연결 상태."""
    return {
        "active_subscribers": event_bus.subscriber_count,
        "status": "ok",
    }


async def _heartbeat_loop():
    """30초 간격 heartbeat 이벤트 전송."""
    try:
        while True:
            await asyncio.sleep(30)
            await event_bus.publish(EVT_HEARTBEAT, {"type": "ping"})
    except asyncio.CancelledError:
        pass
