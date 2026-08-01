from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import Callable
from uuid import uuid4

from app.analysis import AnalysisBundle


@dataclass
class AnalysisSession:
    bundle: AnalysisBundle
    currency: str
    expires_at: float


class AnalysisSessionCache:
    """Keep a small number of cleaned analyses for the current app session."""

    def __init__(
        self,
        *,
        ttl_seconds: int,
        max_sessions: int,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.ttl_seconds = max(1, ttl_seconds)
        self.max_sessions = max(1, max_sessions)
        self._clock = clock
        self._sessions: OrderedDict[str, AnalysisSession] = OrderedDict()
        self._lock = Lock()

    def create(self, bundle: AnalysisBundle, currency: str) -> str:
        with self._lock:
            now = self._clock()
            self._remove_expired(now)
            while len(self._sessions) >= self.max_sessions:
                self._sessions.popitem(last=False)

            analysis_id = uuid4().hex
            self._sessions[analysis_id] = AnalysisSession(
                bundle=bundle,
                currency=currency,
                expires_at=now + self.ttl_seconds,
            )
            return analysis_id

    def get(self, analysis_id: str) -> AnalysisSession | None:
        with self._lock:
            now = self._clock()
            self._remove_expired(now)
            session = self._sessions.get(analysis_id)
            if session is None:
                return None

            session.expires_at = now + self.ttl_seconds
            self._sessions.move_to_end(analysis_id)
            return session

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()

    def _remove_expired(self, now: float) -> None:
        expired = [
            analysis_id
            for analysis_id, session in self._sessions.items()
            if session.expires_at <= now
        ]
        for analysis_id in expired:
            del self._sessions[analysis_id]
