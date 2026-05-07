"""Interactive CLI for the diary chatbot."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import asdict
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()
except Exception:
    pass

from . import personalities
from .chat import ChatClient, ChatConfig
from .storage import ChatMessage, DiaryStore, Todo, now_iso, today_str


HELP_TEXT = """
[bold]Commands[/bold]
  [cyan]/todo <text>[/cyan]      add a todo
  [cyan]/done <id>[/cyan]        mark a todo done
  [cyan]/undone <id>[/cyan]      mark a todo not done
  [cyan]/rm <id>[/cyan]          delete a todo
  [cyan]/todos[/cyan]            show today's todos
  [cyan]/log[/cyan]              show today's log file path
  [cyan]/mood <key>[/cyan]       switch personality (cheerleader / coach / friend / roast)
  [cyan]/quiet[/cyan]            toggle bot replies on/off
  [cyan]/help[/cyan]             show this help
  [cyan]/exit[/cyan]             save and quit

Anything else you type is logged as a journal entry and the bot replies.
""".strip()


class DiaryApp:
    def __init__(
        self,
        entries_dir: Path,
        personality_key: str,
        no_chat: bool = False,
    ):
        self.console = Console()
        self.store = DiaryStore(entries_dir)
        self.day = today_str()
        self.todos: list[Todo] = self.store.carry_forward_todos(self.day)
        self.chat_history: list[ChatMessage] = self.store.load_chat(self.day)
        self.personality = personalities.get(personality_key)
        self.quiet = no_chat
        self.client: ChatClient | None = None
        if not self.quiet:
            try:
                self.client = ChatClient()
            except RuntimeError as e:
                self.console.print(
                    Panel.fit(
                        Text(str(e), style="yellow"),
                        title="No LLM configured",
                        border_style="yellow",
                    )
                )
                self.console.print(
                    "[dim]Continuing in quiet mode. Use /help to see commands.[/dim]\n"
                )
                self.quiet = True

    # --------------------------------------------------------------- helpers

    def _next_todo_id(self) -> int:
        return (max((t.id for t in self.todos), default=0)) + 1

    def _todo_context(self) -> str:
        if not self.todos:
            return f"Today is {self.day}. The user has no todos yet today."
        lines = [f"Today is {self.day}. Current todos:"]
        for t in self.todos:
            mark = "[x]" if t.done else "[ ]"
            lines.append(f"  {mark} #{t.id} {t.text}")
        return "\n".join(lines)

    def _save_state(self) -> None:
        self.store.save_todos(self.day, self.todos)
        self.store.save_chat(self.day, self.chat_history)

    def _print_todos(self) -> None:
        if not self.todos:
            self.console.print("[dim]No todos yet today. Add one with /todo <text>.[/dim]")
            return
        table = Table(show_header=True, header_style="bold cyan", box=None)
        table.add_column("#", justify="right", style="dim")
        table.add_column("status", justify="center")
        table.add_column("todo")
        for t in self.todos:
            status = "[green]done[/green]" if t.done else "[yellow]open[/yellow]"
            text = f"[strike]{t.text}[/strike]" if t.done else t.text
            table.add_row(str(t.id), status, text)
        self.console.print(table)

    def _bot_reply(self, user_message: str, system_event: str | None = None) -> None:
        """Get an LLM reply to the user's message and log it.

        `system_event` is an optional internal note (e.g. "the user just
        completed todo #2: foo") appended as system context so the bot can
        react to structural events, not just free text.
        """
        if self.quiet or self.client is None:
            return
        history_dicts = [
            {"role": m.role, "content": m.content} for m in self.chat_history
        ]
        context = self._todo_context()
        if system_event:
            context += f"\n\nEvent: {system_event}"
        try:
            with self.console.status("[dim]thinking...[/dim]", spinner="dots"):
                reply = self.client.reply(
                    system_prompt=self.personality.system_prompt,
                    history=history_dicts,
                    user_message=user_message,
                    context=context,
                )
        except Exception as e:
            self.console.print(f"[red]LLM error:[/red] {e}")
            return
        if not reply:
            return
        self.chat_history.append(ChatMessage(role="user", content=user_message, ts=now_iso()))
        self.chat_history.append(ChatMessage(role="assistant", content=reply, ts=now_iso()))
        self.store.append_log(self.day, f"{self.personality.label}", reply)
        self.console.print()
        self.console.print(
            Panel(
                Markdown(reply),
                title=f"[bold magenta]{self.personality.label}[/bold magenta]",
                border_style="magenta",
            )
        )

    # ---------------------------------------------------------------- actions

    def add_todo(self, text: str) -> None:
        text = text.strip()
        if not text:
            self.console.print("[red]Empty todo.[/red]")
            return
        todo = Todo(id=self._next_todo_id(), text=text, created=now_iso())
        self.todos.append(todo)
        self.store.append_log(self.day, "todo added", f"- [ ] #{todo.id} {todo.text}")
        self.console.print(f"[green]+[/green] added [bold]#{todo.id}[/bold] {todo.text}")
        self._bot_reply(
            user_message=f"(added a todo) {text}",
            system_event=f"the user just added todo #{todo.id}: {text!r}",
        )

    def mark_done(self, todo_id: int, done: bool = True) -> None:
        for t in self.todos:
            if t.id == todo_id:
                t.done = done
                t.completed = now_iso() if done else None
                verb = "completed" if done else "reopened"
                self.store.append_log(
                    self.day, f"todo {verb}", f"- [{'x' if done else ' '}] #{t.id} {t.text}"
                )
                self.console.print(
                    f"[green]{'done' if done else 'reopened'}:[/green] #{t.id} {t.text}"
                )
                self._bot_reply(
                    user_message=f"(marked todo #{t.id} as {'done' if done else 'not done'}) {t.text}",
                    system_event=f"the user just {verb} todo #{t.id}: {t.text!r}",
                )
                return
        self.console.print(f"[red]No todo with id #{todo_id}.[/red]")

    def remove_todo(self, todo_id: int) -> None:
        for i, t in enumerate(self.todos):
            if t.id == todo_id:
                self.todos.pop(i)
                self.store.append_log(self.day, "todo deleted", f"- ~~#{t.id} {t.text}~~")
                self.console.print(f"[red]-[/red] removed #{t.id} {t.text}")
                return
        self.console.print(f"[red]No todo with id #{todo_id}.[/red]")

    def journal(self, text: str) -> None:
        self.store.append_log(self.day, "entry", text)
        self._bot_reply(user_message=text)

    # ------------------------------------------------------------------- run

    def banner(self) -> None:
        title = Text("daily diary", style="bold")
        sub = Text(
            f"  {self.day}  -  mood: {self.personality.label.lower()}  -  "
            f"{'quiet mode' if self.quiet else 'chat on'}",
            style="dim",
        )
        self.console.print(Panel(Text.assemble(title, "\n", sub), border_style="cyan"))
        if self.todos:
            self.console.print("[dim]Carried-over todos:[/dim]")
            self._print_todos()
        self.console.print("[dim]Type /help for commands. Just type to journal.[/dim]\n")

    def handle_command(self, line: str) -> bool:
        """Return True to keep looping, False to exit."""
        parts = line.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd in ("/exit", "/quit", "/q"):
            return False
        if cmd == "/help":
            self.console.print(Panel(HELP_TEXT, border_style="cyan"))
        elif cmd == "/todo":
            self.add_todo(arg)
        elif cmd == "/todos":
            self._print_todos()
        elif cmd == "/done":
            try:
                self.mark_done(int(arg), True)
            except ValueError:
                self.console.print("[red]Usage: /done <id>[/red]")
        elif cmd == "/undone":
            try:
                self.mark_done(int(arg), False)
            except ValueError:
                self.console.print("[red]Usage: /undone <id>[/red]")
        elif cmd == "/rm":
            try:
                self.remove_todo(int(arg))
            except ValueError:
                self.console.print("[red]Usage: /rm <id>[/red]")
        elif cmd == "/log":
            self.console.print(str(self.store.log_path(self.day)))
        elif cmd == "/mood":
            new = personalities.get(arg)
            self.personality = new
            self.console.print(f"[green]mood ->[/green] {new.label} ({new.description})")
        elif cmd == "/quiet":
            self.quiet = not self.quiet
            self.console.print(
                f"[yellow]chat {'off' if self.quiet else 'on'}[/yellow]"
            )
        else:
            self.console.print(f"[red]unknown command:[/red] {cmd}  (try /help)")
        return True

    def run(self) -> None:
        self.banner()
        try:
            while True:
                try:
                    line = self.console.input("[bold cyan]>[/bold cyan] ").rstrip()
                except EOFError:
                    break
                if not line:
                    continue
                if line.startswith("/"):
                    if not self.handle_command(line):
                        break
                else:
                    self.journal(line)
                self._save_state()
        except KeyboardInterrupt:
            self.console.print()
        finally:
            self._save_state()
            self.console.print(
                f"[dim]saved to {self.store.log_path(self.day)}[/dim]"
            )


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="diary",
        description="A daily diary + todo logger with an LLM friend attached.",
    )
    p.add_argument(
        "--dir",
        default=os.environ.get("DIARY_DIR", "./entries"),
        help="Directory to store diary entries (default: ./entries)",
    )
    p.add_argument(
        "--mood",
        "-m",
        default=os.environ.get("DIARY_MOOD", personalities.DEFAULT_PERSONALITY),
        choices=personalities.list_keys(),
        help="Bot personality.",
    )
    p.add_argument(
        "--no-chat",
        action="store_true",
        help="Disable LLM replies (logging-only mode).",
    )
    p.add_argument(
        "--list-moods",
        action="store_true",
        help="Show available personalities and exit.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    if args.list_moods:
        console = Console()
        for key in personalities.list_keys():
            p = personalities.get(key)
            console.print(f"  [bold cyan]{p.key:12s}[/bold cyan] {p.description}")
        return 0

    app = DiaryApp(
        entries_dir=Path(args.dir),
        personality_key=args.mood,
        no_chat=args.no_chat,
    )
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
