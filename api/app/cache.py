"""Cache of answers to the fixed demo questions (keeps free-tier quotas and the live demo safe)."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .demo_questions import DEMO_QUESTIONS
from .models import ChatResponse

if TYPE_CHECKING:
    from .agent import Identity
    from .providers import LLMProvider


def normalise(question: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", question.lower()).strip()


class ResponseCache:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._store: dict[str, Any] = {}
        self._fixed = {normalise(q) for q in DEMO_QUESTIONS}
        if path and path.exists():
            self._store = json.loads(path.read_text(encoding="utf-8"))

    def _key(self, provider: LLMProvider, who: Identity, question: str) -> str | None:
        q = normalise(question)
        if q not in self._fixed:
            return None
        return hashlib.sha256(f"{provider.name}|{provider.model}|{who.role}|{who.branch_id}|{q}".encode()).hexdigest()

    def get(self, provider: LLMProvider, who: Identity, question: str) -> ChatResponse | None:
        key = self._key(provider, who, question)
        if key and key in self._store:
            resp = ChatResponse.model_validate(self._store[key])
            resp.guardrail.cached = True
            return resp
        return None

    def put(self, provider: LLMProvider, who: Identity, question: str, response: ChatResponse) -> None:
        key = self._key(provider, who, question)
        if not key:
            return
        self._store[key] = response.model_dump(mode="json")
        if self._path:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(self._store), encoding="utf-8")

    def clear(self) -> None:
        self._store.clear()
        if self._path and self._path.exists():
            self._path.unlink()
