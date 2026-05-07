"""Filesystem storage for diary entries, todos, and chat history.

Layout (under the entries dir, default ./entries):

    entries/
      2026-05-07/
        log.md         human-readable daily log (entries + bot replies)
        todos.json     today's todo list (carried over from yesterday)
        chat.json      raw chat history for LLM context

Todos roll forward: when you start a new day, any unfinished todos from the
most recent prior day get copied into today's todos.json so they don't get
lost. Completed ones stay archived in their original day's file.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Iterable


@dataclass
class Todo:
    id: int
    text: str
    done: bool = False
    created: str = ""
    completed: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "Todo":
        return cls(
            id=int(d["id"]),
            text=str(d["text"]),
            done=bool(d.get("done", False)),
            created=str(d.get("created", "")),
            completed=d.get("completed"),
        )


@dataclass
class ChatMessage:
    role: str  # "user" | "assistant" | "system"
    content: str
    ts: str = ""


@dataclass
class DayState:
    day: str  # ISO date string YYYY-MM-DD
    todos: list[Todo] = field(default_factory=list)
    chat: list[ChatMessage] = field(default_factory=list)


class DiaryStore:
    def __init__(self, root: Path):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ paths

    def _day_dir(self, day: str) -> Path:
        d = self.root / day
        d.mkdir(parents=True, exist_ok=True)
        return d

    def log_path(self, day: str) -> Path:
        return self._day_dir(day) / "log.md"

    def todos_path(self, day: str) -> Path:
        return self._day_dir(day) / "todos.json"

    def chat_path(self, day: str) -> Path:
        return self._day_dir(day) / "chat.json"

    # ----------------------------------------------------------------- todos

    def load_todos(self, day: str) -> list[Todo]:
        p = self.todos_path(day)
        if not p.exists():
            return []
        try:
            data = json.loads(p.read_text())
        except json.JSONDecodeError:
            return []
        return [Todo.from_dict(t) for t in data]

    def save_todos(self, day: str, todos: Iterable[Todo]) -> None:
        p = self.todos_path(day)
        p.write_text(json.dumps([asdict(t) for t in todos], indent=2))

    def carry_forward_todos(self, day: str) -> list[Todo]:
        """If today has no todos file yet, seed it from the most recent prior
        day's unfinished todos. Returns today's current todos."""
        today_path = self.todos_path(day)
        if today_path.exists():
            return self.load_todos(day)

        prior_days = sorted(
            (p.name for p in self.root.iterdir() if p.is_dir() and p.name < day),
            reverse=True,
        )
        carried: list[Todo] = []
        for prev in prior_days:
            prev_todos = self.load_todos(prev)
            if prev_todos:
                carried = [t for t in prev_todos if not t.done]
                break

        for i, t in enumerate(carried, start=1):
            t.id = i

        self.save_todos(day, carried)
        return carried

    # ------------------------------------------------------------------ chat

    def load_chat(self, day: str) -> list[ChatMessage]:
        p = self.chat_path(day)
        if not p.exists():
            return []
        try:
            data = json.loads(p.read_text())
        except json.JSONDecodeError:
            return []
        return [ChatMessage(**m) for m in data]

    def save_chat(self, day: str, chat: Iterable[ChatMessage]) -> None:
        self.chat_path(day).write_text(
            json.dumps([asdict(m) for m in chat], indent=2)
        )

    # ------------------------------------------------------------------- log

    def append_log(self, day: str, header: str, body: str) -> None:
        """Append a markdown block to today's human-readable log file."""
        p = self.log_path(day)
        is_new = not p.exists()
        with p.open("a", encoding="utf-8") as f:
            if is_new:
                f.write(f"# Diary - {day}\n\n")
            ts = datetime.now().strftime("%H:%M")
            f.write(f"## {ts} - {header}\n\n{body.rstrip()}\n\n")


def today_str() -> str:
    return date.today().isoformat()


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
