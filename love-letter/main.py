"""A tiny customizable love-letter app.

Edit the values in the "Make it yours" section, then run:

    python3 love-letter/main.py

To package on Windows:

    python love-letter/build_exe.py
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable

try:
    import tkinter as tk
except ModuleNotFoundError:  # pragma: no cover - depends on the local Python install.
    tk = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Make it yours
# ---------------------------------------------------------------------------

RECIPIENT_NAME = "you"
SENDER_NAME = "someone who smiles thinking about you"

LETTER_LINES = [
    "Hey, {name}.",
    "",
    "I made you a tiny little program because regular texts felt too ordinary.",
    "So here it is: a pocket-sized reminder that you are deeply appreciated.",
    "",
    "Your laugh, your kindness, the way you make simple moments feel special...",
    "I notice it all. And I like it more than I know how to say.",
    "",
    "If this made you smile even a little, then it worked.",
    "",
    "From,",
    "{sender}",
]

FINAL_PROMPT = "P.S. will you let me take you on a cute little date?"
YES_REPLY = "Perfect. I was hoping you would say that."
NO_REPLY = "That's okay. I still hope this made your day softer."


# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------

WINDOW_TITLE = "a little love letter.exe"
BG = "#1f1025"
PANEL = "#fff1f7"
PANEL_DARK = "#ffd7e8"
TEXT = "#3b1f2f"
ACCENT = "#ff5f9e"
ACCENT_DARK = "#d83a78"
HEARTS = ["#ff5f9e", "#ff8ebd", "#ffc2d8", "#f43f7f", "#ffd1dc"]


@dataclass
class Heart:
    item: int
    x_speed: float
    y_speed: float
    wobble: float


class LoveLetterApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title(WINDOW_TITLE)
        self.root.geometry("820x620")
        self.root.minsize(640, 520)
        self.root.configure(bg=BG)

        self.canvas = tk.Canvas(self.root, bg=BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self._draw_background)

        self.hearts: list[Heart] = []
        self.typewriter_job: str | None = None
        self.current_text = ""
        self.target_text = ""
        self.not_yet_clicks = 0

        self.title_font = ("Georgia", 30, "bold")
        self.body_font = ("Georgia", 15)
        self.small_font = ("Helvetica", 11)
        self.button_font = ("Helvetica", 12, "bold")

        self.card = tk.Frame(self.root, bg=PANEL, bd=0, highlightthickness=0)
        self.card_window = self.canvas.create_window(410, 310, window=self.card, width=560, height=360)

        self._show_envelope()
        self._seed_hearts()
        self._animate_hearts()

    def run(self) -> None:
        self.root.mainloop()

    def _draw_background(self, _event: tk.Event | None = None) -> None:
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        self.canvas.coords(self.card_window, width / 2, height / 2)

        self.canvas.delete("sparkle")
        for _ in range(34):
            x = random.randint(0, max(width, 1))
            y = random.randint(0, max(height, 1))
            radius = random.choice([1, 1, 2])
            self.canvas.create_oval(
                x,
                y,
                x + radius,
                y + radius,
                fill="#fff4fb",
                outline="",
                tags="sparkle",
            )

    def _seed_hearts(self) -> None:
        width = max(self.canvas.winfo_width(), 820)
        height = max(self.canvas.winfo_height(), 620)
        for _ in range(24):
            self._add_heart(
                x=random.randint(20, width - 20),
                y=random.randint(20, height - 20),
                size=random.randint(16, 32),
            )

    def _add_heart(self, x: int, y: int, size: int) -> None:
        item = self.canvas.create_text(
            x,
            y,
            text="♥",
            fill=random.choice(HEARTS),
            font=("Arial", size, "bold"),
            tags="heart",
        )
        self.hearts.append(
            Heart(
                item=item,
                x_speed=random.uniform(-0.35, 0.35),
                y_speed=random.uniform(0.35, 1.15),
                wobble=random.uniform(-0.25, 0.25),
            )
        )

    def _animate_hearts(self) -> None:
        width = max(self.canvas.winfo_width(), 820)
        height = max(self.canvas.winfo_height(), 620)

        for heart in self.hearts:
            self.canvas.move(heart.item, heart.x_speed + heart.wobble, -heart.y_speed)
            x, y = self.canvas.coords(heart.item)
            if y < -30:
                self.canvas.coords(heart.item, random.randint(0, width), height + 30)

        self.root.after(35, self._animate_hearts)

    def _clear_card(self) -> None:
        if self.typewriter_job:
            self.root.after_cancel(self.typewriter_job)
            self.typewriter_job = None
        for child in self.card.winfo_children():
            child.destroy()

    def _show_envelope(self) -> None:
        self._clear_card()
        self.card.configure(bg=PANEL)

        tk.Label(
            self.card,
            text="✉",
            font=("Georgia", 58),
            fg=ACCENT,
            bg=PANEL,
        ).pack(pady=(28, 0))

        tk.Label(
            self.card,
            text="You received a tiny love letter",
            font=self.title_font,
            fg=TEXT,
            bg=PANEL,
        ).pack(pady=(2, 8))

        tk.Label(
            self.card,
            text="Only open if you are ready for something very soft.",
            font=self.body_font,
            fg=TEXT,
            bg=PANEL,
        ).pack(pady=(0, 24))

        button_row = tk.Frame(self.card, bg=PANEL)
        button_row.pack()

        self.open_button = self._button(button_row, "Open it", self._show_letter)
        self.open_button.grid(row=0, column=0, padx=8)

        self.not_yet_button = self._button(button_row, "Not yet", self._tease_not_yet, secondary=True)
        self.not_yet_button.grid(row=0, column=1, padx=8)

        tk.Label(
            self.card,
            text="made with Python",
            font=self.small_font,
            fg="#8e5b75",
            bg=PANEL,
        ).pack(side="bottom", pady=16)

    def _button(
        self,
        parent: tk.Misc,
        text: str,
        command: Callable[[], None],
        *,
        secondary: bool = False,
    ) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            font=self.button_font,
            fg="white" if not secondary else TEXT,
            bg=ACCENT if not secondary else PANEL_DARK,
            activeforeground="white" if not secondary else TEXT,
            activebackground=ACCENT_DARK if not secondary else "#ffc8df",
            bd=0,
            padx=20,
            pady=10,
            cursor="hand2",
        )

    def _tease_not_yet(self) -> None:
        self.not_yet_clicks += 1
        messages = [
            "Are you sure?",
            "It is pretty cute...",
            "Okay but now I am nervous.",
            "Fine, but the letter misses you.",
            "Last chance before the hearts unionize.",
        ]
        self.not_yet_button.configure(text=messages[min(self.not_yet_clicks - 1, len(messages) - 1)])
        self._burst_hearts(8)

    def _show_letter(self) -> None:
        self._clear_card()
        self.card.configure(bg=PANEL)

        tk.Label(
            self.card,
            text="For {name}".format(name=RECIPIENT_NAME),
            font=self.title_font,
            fg=ACCENT_DARK,
            bg=PANEL,
        ).pack(pady=(24, 8))

        self.letter_label = tk.Label(
            self.card,
            text="",
            font=self.body_font,
            fg=TEXT,
            bg=PANEL,
            justify="left",
            wraplength=485,
        )
        self.letter_label.pack(padx=36, pady=10, fill="both", expand=True)

        self.prompt_frame = tk.Frame(self.card, bg=PANEL)
        self.prompt_frame.pack(pady=(4, 22))

        formatted_lines = [
            line.format(name=RECIPIENT_NAME, sender=SENDER_NAME) for line in LETTER_LINES
        ]
        self.target_text = "\n".join(formatted_lines)
        self.current_text = ""
        self._type_next_character(0)

    def _type_next_character(self, index: int) -> None:
        if index >= len(self.target_text):
            self.typewriter_job = None
            self._show_final_prompt()
            return

        self.current_text += self.target_text[index]
        self.letter_label.configure(text=self.current_text + "▌")
        delay = 28 if self.target_text[index] != "\n" else 140
        self.typewriter_job = self.root.after(delay, self._type_next_character, index + 1)

    def _show_final_prompt(self) -> None:
        self.letter_label.configure(text=self.target_text)

        tk.Label(
            self.prompt_frame,
            text=FINAL_PROMPT,
            font=("Georgia", 14, "italic"),
            fg=TEXT,
            bg=PANEL,
            wraplength=460,
        ).grid(row=0, column=0, columnspan=2, pady=(0, 12))

        self._button(self.prompt_frame, "Yes", lambda: self._answer(YES_REPLY)).grid(
            row=1, column=0, padx=8
        )
        self._button(
            self.prompt_frame,
            "No, but this was sweet",
            lambda: self._answer(NO_REPLY),
            secondary=True,
        ).grid(row=1, column=1, padx=8)

    def _answer(self, message: str) -> None:
        for child in self.prompt_frame.winfo_children():
            child.destroy()

        tk.Label(
            self.prompt_frame,
            text=message,
            font=("Georgia", 15, "bold"),
            fg=ACCENT_DARK,
            bg=PANEL,
            wraplength=460,
        ).pack()
        self._burst_hearts(18)

    def _burst_hearts(self, amount: int) -> None:
        width = max(self.canvas.winfo_width(), 820)
        height = max(self.canvas.winfo_height(), 620)
        for _ in range(amount):
            self._add_heart(
                x=random.randint(width // 3, width * 2 // 3),
                y=random.randint(height // 3, height * 2 // 3),
                size=random.randint(16, 36),
            )


def main() -> None:
    if tk is None:
        print(
            "This app needs tkinter.\n"
            "On Ubuntu/Debian, install it with: sudo apt install python3-tk\n"
            "On Windows, install Python from python.org with the default options."
        )
        raise SystemExit(1)

    app = LoveLetterApp()
    app.run()


if __name__ == "__main__":
    main()
