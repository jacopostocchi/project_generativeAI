"""The memory store, and the handle. TODO 1 to 3.

Two things live here and they are easy to confuse.

**Memory** is what the agent remembers about a resident across runs: facts,
written once and searched later. It is a store.

**A handle** is a name for a piece of state that the agent carries in its own
messages. It is not memory, it is an address. `open_case` mints one, and
every later call passes it back as an ordinary argument.

The distinction is the whole week. Block 2 shows why: when the protocol stops
carrying state for you, the state does not vanish, it becomes an argument
with a name the model can see.
"""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_PATH = Path("artifacts/memory_store.json") 
import calendar

RETENTION_SECONDS = 90 * 24 * 3600
_TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _now_iso() -> str:
    return time.strftime(_TS_FORMAT, time.gmtime())

import re

def _tokens(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) > 2}


def _epoch(ts: str) -> float:
    return calendar.timegm(time.strptime(ts, _TS_FORMAT))


@dataclass
class Fact:
    subject: str
    kind: str
    text: str
    handle: str
    written_at: str


@dataclass
class MemoryStore:
    """A file-backed store. Deliberately not a database and not a vector store.

    Week 7 replaces `search` with real retrieval over embeddings. Keep the
    keyword version behind this one method and next week costs you ten lines
    instead of a refactor.
    """

    path: Path = DEFAULT_PATH
    facts: list[Fact] = field(default_factory=list)
    cases: dict[str, str] = field(default_factory=dict)

    # ----------------------------------------------------------------
    # TODO 1. Writing, and the handle it returns.
    # ----------------------------------------------------------------

    def write(self, subject: str, kind: str, text: str) -> str:
        """TODO 1. Append one fact and return a handle for it.

        Three decisions here, and all three go in DECISIONS.md with a reason.

        What does a handle look like? A sequential `fact-0007` tells anyone
        who sees it how many facts exist and lets them guess `fact-0006`,
        which is a read of somebody else's data. Week 12 attacks exactly
        this.

        What happens when a new fact contradicts an older one? Keeping both
        means `recall` can return two contradictory facts and something has
        to cope. Overwriting means losing what changed and when. Pick one.

        How long does a record live? Nothing here expires, which is a choice
        and the wrong one for a real service holding residents' data. If you
        keep it, say so rather than leaving it unsaid.
        """
        self._purge_expired()

        existing = {f.handle for f in self.facts}
        handle = f"fact-{secrets.token_hex(8)}"
        while handle in existing:
            handle = f"fact-{secrets.token_hex(8)}"

        self.facts = [
            f for f in self.facts
            if not (f.subject == subject and f.kind == kind)
        ]
        self.facts.append(Fact(
            subject=subject,
            kind=kind,
            text=text,
            handle=handle,
            written_at=_now_iso(),
        ))
        self.save()
        return handle
    
    
    def _purge_expired(self) -> int:
        """Hard-delete facts past retention. Returns how many were removed."""
        cutoff = time.time() - RETENTION_SECONDS
        before = len(self.facts)
        self.facts = [f for f in self.facts if _epoch(f.written_at) >= cutoff]
        removed = before - len(self.facts)
        if removed:
            self.save()
        return removed
    # ----------------------------------------------------------------
    # TODO 2. Searching, and what k costs.
    # ----------------------------------------------------------------

    def search(self, subject: str, query: str, k: int = 3) -> list[str]:
        """TODO 2. Return at most k remembered facts about ONE subject.

        Scope to the subject BEFORE you score anything. That is not an
        optimization, it is the boundary that stops one resident's memory
        leaking into another's conversation, and it belongs here rather than
        in a sentence asking the model not to do it.

        Keyword overlap is fine. Week 7 replaces the body of this method
        with embeddings and the signature does not change, so keep the
        matching inside this one method.

        Then answer, at the checkpoint: what does k cost you in tokens per
        call, and what happens when the store holds four hundred facts?
        """
        self._purge_expired()
        if k <= 0:
            return []

        scoped = [f for f in self.facts if f.subject == subject]
        if not scoped:
            return []

        terms = _tokens(query)
        scored = []
        for f in scoped:
            score = len(terms & _tokens(f.text + " " + f.kind))
            if score > 0:
                scored.append((score, f.written_at, f))

        scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
        return [f"[{f.kind}] {f.text}" for _, _, f in scored[:k]]

    # ----------------------------------------------------------------
    # TODO 3. Forgetting, which is not optional.
    # ----------------------------------------------------------------

    def forget(self, handle: str) -> bool:
        """TODO 3. Hard delete by handle. Return whether it existed.

        Not optional. A store that can only be written to is not a store you
        can operate, and "we keep everything forever" is an answer with a
        legal department attached to it.

        One line in DECISIONS.md about what this does NOT reach: anything
        already copied into a running conversation's messages. Deleting the
        fact does not un-say it.
        """
        before = len(self.facts)
        self.facts = [f for f in self.facts if f.handle != handle]
        existed = len(self.facts) < before
        if existed:
            self.save()
        return existed

    # ----------------------------------------------------------------
    # The handle, which is block 2's subject
    # ----------------------------------------------------------------

    def open_case(self, subject: str) -> str:
        """Mint an explicit handle for a piece of ongoing state."""
        handle = f"case-{secrets.token_hex(6)}"
        self.cases[handle] = subject
        self.save()
        return handle

    def subject_of(self, handle: str) -> str | None:
        return self.cases.get(handle)

    # ----------------------------------------------------------------
    # Persistence
    # ----------------------------------------------------------------

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({
            "facts": [vars(f) for f in self.facts],
            "cases": self.cases,
        }, indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: Path = DEFAULT_PATH) -> "MemoryStore":
        store = cls(path=path)
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            store.facts = [Fact(**f) for f in data.get("facts", [])]
            store.cases = data.get("cases", {})
        return store
