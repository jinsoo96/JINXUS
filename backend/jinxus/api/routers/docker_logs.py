"""Docker 컨테이너 로그 실시간 스트리밍 API

Docker Engine API (Unix 소켓)를 통해 컨테이너 목록 조회 및 로그 SSE 스트리밍.
"""
import asyncio
import json
import logging
import struct
from datetime import datetime

import httpx
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/docker", tags=["docker"])

DOCKER_SOCKET = "/var/run/docker.sock"


def _docker_transport() -> httpx.AsyncHTTPTransport:
    return httpx.AsyncHTTPTransport(uds=DOCKER_SOCKET)


@router.get("/containers")
async def list_containers():
    """Docker 컨테이너 목록 조회"""
    try:
        async with httpx.AsyncClient(
            transport=_docker_transport(), base_url="http://localhost"
        ) as client:
            resp = await client.get("/containers/json", params={"all": "true"})
            resp.raise_for_status()
            raw = resp.json()

        containers = []
        for c in raw:
            name = (c.get("Names") or ["/unknown"])[0].lstrip("/")
            # jinxus 관련 컨테이너만 표시
            if "jinxus" not in name.lower():
                continue
            containers.append({
                "id": c["Id"][:12],
                "name": name,
                "image": c.get("Image", ""),
                "status": c.get("Status", ""),
                "state": c.get("State", "unknown"),
                "created": datetime.fromtimestamp(c.get("Created", 0)).isoformat(),
            })

        return {"containers": containers}
    except Exception as e:
        logger.error(f"Docker 컨테이너 목록 조회 실패: {e}")
        return {"containers": [], "error": str(e)}


async def _stream_docker_logs(container_id: str, tail: int = 100):
    """Docker 로그를 SSE 형식으로 스트리밍.

    Docker 로그 스트림은 8바이트 헤더 멀티플렉싱을 사용한다:
    [stream_type(1)][padding(3)][size(4, big-endian)][payload]
    stream_type: 0=stdin, 1=stdout, 2=stderr
    """
    try:
        async with httpx.AsyncClient(
            transport=_docker_transport(),
            base_url="http://localhost",
            timeout=None,
        ) as client:
            async with client.stream(
                "GET",
                f"/containers/{container_id}/logs",
                params={
                    "stdout": "true",
                    "stderr": "true",
                    "follow": "true",
                    "tail": str(tail),
                    "timestamps": "true",
                },
            ) as resp:
                buf = b""
                async for chunk in resp.aiter_bytes():
                    buf += chunk

                    # 8바이트 헤더 프로토콜 파싱
                    while len(buf) >= 8:
                        stream_type = buf[0]  # 1=stdout, 2=stderr
                        size = struct.unpack(">I", buf[4:8])[0]

                        if len(buf) < 8 + size:
                            break  # 아직 데이터 부족

                        payload = buf[8 : 8 + size].decode("utf-8", errors="replace").rstrip("\n")
                        buf = buf[8 + size :]

                        stream_name = "stderr" if stream_type == 2 else "stdout"

                        # timestamp 분리 (Docker timestamps=true → RFC3339 prefix)
                        timestamp = ""
                        line = payload
                        if len(payload) > 30 and payload[4] == "-":
                            # 2026-03-16T10:23:45.123456789Z 형식
                            space_idx = payload.find(" ")
                            if space_idx > 20:
                                timestamp = payload[:space_idx]
                                line = payload[space_idx + 1 :]

                        data = json.dumps(
                            {"line": line, "stream": stream_name, "timestamp": timestamp},
                            ensure_ascii=False,
                        )
                        yield f"event: log\ndata: {data}\n\n"

    except httpx.RemoteProtocolError:
        # 컨테이너 중지 시 정상 종료
        pass
    except asyncio.CancelledError:
        pass
    except Exception as e:
        error_data = json.dumps({"error": str(e)}, ensure_ascii=False)
        yield f"event: error\ndata: {error_data}\n\n"


@router.get("/containers/{container_id}/logs")
async def stream_container_logs(
    container_id: str,
    tail: int = Query(default=100, ge=1, le=5000),
):
    """컨테이너 로그 SSE 스트리밍"""
    return StreamingResponse(
        _stream_docker_logs(container_id, tail),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
