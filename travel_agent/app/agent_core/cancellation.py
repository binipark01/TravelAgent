"""실행 중인 run의 협조적 중지(취소) 신호.

백그라운드 실행 태스크와 '중지' 요청은 같은 프로세스(단일 uvicorn 워커)에서 도므로,
메모리 집합으로 취소 플래그를 공유한다. 슈퍼바이저가 각 단계 경계에서 이 플래그를 확인해
RunCancelled를 던지면 파이프라인이 멈춘다(진행 중이던 단계는 끝나고 다음 경계에서 중단).

다중 워커로 확장한다면 이 플래그를 공유 저장소(DB·Redis)로 옮겨야 한다.
"""

from __future__ import annotations

import threading

_lock = threading.Lock()
_cancelled: set[str] = set()


class RunCancelled(Exception):
    """사용자가 실행 중지를 요청했을 때 계획 파이프라인을 빠져나오는 신호."""


def request_cancel(run_id: str) -> None:
    if not run_id:
        return
    with _lock:
        _cancelled.add(run_id)


def is_cancelled(run_id: str | None) -> bool:
    if not run_id:
        return False
    with _lock:
        return run_id in _cancelled


def clear(run_id: str | None) -> None:
    """취소 처리가 끝났거나 run이 종료되면 플래그를 비운다(메모리 누수 방지)."""
    if not run_id:
        return
    with _lock:
        _cancelled.discard(run_id)
