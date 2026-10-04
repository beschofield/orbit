import os
import unittest

from orbit import characters
from orbit.characters import display_width
from orbit.contract import MOODS, WHO, Say
from tests.helpers import REPO

GOLDEN = REPO / "tests" / "golden"
SAMPLE = "Hello from Orbit! This line is long enough to wrap onto a second line."


class ArtTest(unittest.TestCase):
    def test_every_who_and_mood_has_art_within_limits(self):
        for who in WHO:
            for mood in MOODS:
                path = characters.ART_DIR / who / f"{mood}.txt"
                with self.subTest(path=str(path)):
                    self.assertTrue(path.is_file())
                    lines = path.read_text(encoding="utf-8").rstrip("\n").split("\n")
                    self.assertLessEqual(len(lines), 6)
                    self.assertLessEqual(max(display_width(line) for line in lines), characters.ART_WIDTH)


class RenderTest(unittest.TestCase):
    def test_pluto_faces_right_and_charon_faces_left(self):
        p = characters.render("pluto", "happy", "hi").split("\n")[1]
        self.assertLess(p.index("^ ^"), p.index("| hi"))
        c = characters.render("charon", "happy", "hi").split("\n")[1]
        self.assertLess(c.index("| hi"), c.index("^ ^"))

    def test_name_label_under_art(self):
        self.assertIn("Charon", characters.render("charon", "neutral", "hi"))

    def test_rows_fit_in_60_columns(self):
        for who in WHO:
            for row in characters.render(who, "neutral", SAMPLE * 3).split("\n"):
                self.assertLessEqual(display_width(row), 60, row)

    def test_bubble_edges_line_up_with_wide_characters(self):  # Review Focus #1
        text = "sleepy 💤💤 time ♥ ok, and a few more words to wrap the line"
        lines = characters.wrap(characters.clean(text), characters.BUBBLE_TEXT_WIDTH)
        rows = characters.render("pluto", "sleepy", text).split("\n")[: len(lines) + 2]
        self.assertEqual(len({display_width(r) for r in rows}), 1, rows)

    def test_newlines_start_new_lines(self):  # Review Focus #1
        out = characters.render("charon", "neutral", "line one\nline two")
        self.assertIn("| line one", out)
        self.assertIn("| line two", out)

    def test_escape_codes_are_stripped(self):  # Review Focus #1
        out = characters.render("pluto", "neutral", "evil \x1b[2J text\x07")
        self.assertNotIn("\x1b", out)
        self.assertNotIn("\x07", out)
        self.assertIn("evil [2J text", out)

    def test_color_only_when_asked(self):
        self.assertNotIn("\033", characters.render("pluto", "happy", "hi"))
        self.assertIn("\033[", characters.render("pluto", "happy", "hi", color=True))

    def test_wrap_breaks_long_words(self):
        self.assertEqual(characters.wrap("x" * 50, 20), ["x" * 20, "x" * 20, "x" * 10])

    def test_unknown_mood_falls_back_to_neutral(self):
        self.assertEqual(characters.load_art("pluto", "nope"), characters.load_art("pluto", "neutral"))

    def test_render_says_joins_bubbles(self):
        out = characters.render_says([Say("pluto", "love", "first"), Say("charon", "happy", "second")])
        self.assertIn("first", out)
        self.assertIn("second", out)
        self.assertEqual(characters.render_says([]), "")

    def test_golden_renders(self):
        for who in WHO:
            for mood in MOODS:
                with self.subTest(who=who, mood=mood):
                    got = characters.render(who, mood, SAMPLE) + "\n"
                    path = GOLDEN / f"{who}_{mood}.txt"
                    if os.environ.get("ORBIT_UPDATE_GOLDEN"):
                        path.parent.mkdir(exist_ok=True)
                        path.write_text(got, encoding="utf-8")
                    self.assertEqual(got, path.read_text(encoding="utf-8"))
