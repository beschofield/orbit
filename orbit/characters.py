"""ASCII Pluto and Charon with speech bubbles.

Pluto sits on the left facing right and Charon on the right facing left, so a
conversation looks like the two facing each other. Text is cleaned of control
characters first: notes come from the other machine, and an escape code in a note
must not be able to clear the screen or change colors.
"""
from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import Sequence

from orbit.contract import Say

ART_DIR = Path(__file__).parent / "art"
ART_WIDTH = 16
BUBBLE_TEXT_WIDTH = 36  # 16 art + 1 gap + 36 text + 6 border = 59 ≤ 60 columns
ACCENT = {"pluto": "\033[38;5;216m", "charon": "\033[38;5;110m"}  # peach, blue-grey
RESET = "\033[0m"


def display_width(s: str) -> int:
    """Terminal columns: wide characters (most emoji, CJK) take 2, combining marks 0."""
    width = 0
    for ch in s:
        if unicodedata.category(ch) in ("Mn", "Me", "Cf"):
            continue
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return width


def clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\t", "    ")
    return "".join(ch for ch in text if ch == "\n" or unicodedata.category(ch)[0] != "C")


def _fit(word: str, width: int) -> int:
    """How many leading characters of `word` fit in `width` columns (at least 1)."""
    used = count = 0
    for ch in word:
        w = display_width(ch)
        if used + w > width:
            break
        used += w
        count += 1
    return max(count, 1)


def wrap(text: str, width: int) -> list[str]:
    out: list[str] = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split(" "):
            while display_width(word) > width:
                if line:
                    out.append(line)
                    line = ""
                cut = _fit(word, width)
                out.append(word[:cut])
                word = word[cut:]
            candidate = f"{line} {word}" if line else word
            if display_width(candidate) <= width:
                line = candidate
            else:
                out.append(line)
                line = word
        out.append(line)
    return out or [""]


def _pad(s: str, width: int) -> str:
    return s + " " * max(0, width - display_width(s))


def load_art(who: str, mood: str) -> list[str]:
    for m in (mood, "neutral"):
        path = ART_DIR / who / f"{m}.txt"
        if path.is_file():
            return [line.rstrip() for line in path.read_text(encoding="utf-8").rstrip("\n").split("\n")]
    return [f"({who})"]


def render(who: str, mood: str, text: str, color: bool = False) -> str:
    art = load_art(who, mood) + [who.capitalize().center(ART_WIDTH).rstrip()]
    lines = wrap(clean(text), BUBBLE_TEXT_WIDTH)
    inner = max(display_width(line) for line in lines)
    art_left = who == "pluto"
    tail_left, tail_right = ("<", " ") if art_left else (" ", ">")
    bubble = [" ." + "-" * (inner + 2) + ". "]
    for i, line in enumerate(lines):
        bubble.append((tail_left if i == 0 else " ") + "| " + _pad(line, inner) + " |"
                      + (tail_right if i == 0 else " "))
    bubble.append(" '" + "-" * (inner + 2) + "' ")
    height = max(len(art), len(bubble))
    art += [""] * (height - len(art))
    bubble += [""] * (height - len(bubble))
    rows = []
    for a, b in zip(art, bubble):
        cell = _pad(a, ART_WIDTH)
        if color:
            cell = ACCENT[who] + cell + RESET
        row = f"{cell} {b}" if art_left else f"{_pad(b, inner + 6)} {cell}"
        rows.append(row.rstrip())
    return "\n".join(rows)


def render_says(says: Sequence[Say], color: bool = False) -> str:
    return "\n\n".join(render(s.who, s.mood, s.text, color) for s in says)
