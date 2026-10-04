# Look Direction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let every speech bubble choose whether its planet looks forward (at the person at the terminal) or to the side (toward the other planet), through one optional `look` key in the capability contract.

**Architecture:** `orbit/contract.py` defines `LOOKS` and gives `Say` a `look` field that defaults to `"forward"`. `orbit/characters.py` loads art from `orbit/art/<who>/<look>/<mood>.txt`, falling back so a half-drawn set still shows something. Capabilities write `"look": "side"` only where it applies: the notes capability does it for its three side bubbles, and everything else gets forward by leaving it out.

**Tech Stack:** Python ≥ 3.11, stdlib only, `unittest`, JSON capability test cases run by `bin/orbit dev test`.

**Spec:** `docs/superpowers/specs/2026-10-04-look-direction-design.md`

**Branch:** `feat/look-direction` in the main checkout `/home/becca/Claude/orbit`. Use a plain branch here, not a worktree (Becca's `~/.claude/CLAUDE.md`). Commit after each task. Never force-push; push with plain `git push`.

## Global Constraints

- Python stdlib only, Python ≥ 3.11. No pip installs.
- Art files: at most 6 lines and 16 columns each (`characters.ART_WIDTH`); a rendered row is at most 60 columns.
- `look` is `"forward"` or `"side"`. Leaving it out means `"forward"`. Never write `"look": "forward"`, in capability code or in capability test cases.
- Bad `look` error text, exactly: `must be "forward" or "side" (leave it out for "forward")`, at `say[<i>].look`.
- The contract stays at v1 (`"contract": 1`).
- Every error message says where, what, and how to fix it (CLAUDE.md invariant 6).
- Small files with one job, type hints, docstrings that say *why* (invariant 7).
- Wording: the people are Becca and Gabby; say "girlfriend", never "partner" (invariant 9).
- `python3 -W error::ResourceWarning -m unittest` must stay clean (invariant 10).

## Review Focus

1. **A mistyped `look`** (`"Side"`, `"left"`) must give the contract error, not silently face forward. Pinned in Task 1, `test_bad_look_says_how_to_fix`.
2. **An explicit `"look": null`, a list, or an object** must give the same error, not crash validation. Pinned in Task 1, same test.
3. **A greeting that mixes forward and side bubbles** (`render_says` with Charon forward, Pluto side) must draw each bubble with its own art. Pinned in Task 2, `test_render_says_uses_each_bubbles_look`.
4. **A mood drawn for only one direction, or an unknown look** must fall back along the spec §4 chain and never raise. Pinned in Task 2, `FallbackTest`.
5. **Long text next to side art** (the widest art, 16 columns) for every who × look × mood must keep every row within 60 columns. Pinned in Task 2, `test_rows_fit_in_60_columns`.

---

### Task 1: Contract — the `look` key

**Files:**
- Modify: `orbit/contract.py` (constants near `MOODS` at line 21, `Say` at ~line 61, `_says` at ~line 265, `output_to_dict` at ~line 323)
- Modify: `docs/capability-contract.md` (`## Output` example, the `say` row of the output table, the `## Tests` case example)
- Modify: `docs/superpowers/specs/2026-10-03-orbit-design.md` (§5.4)
- Test: `tests/test_contract.py` (class `OutputTest`)

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `contract.LOOKS: tuple[str, ...] == ("forward", "side")`
  - `contract.Say(who: str, mood: str, text: str, look: str = "forward")`, a frozen dataclass. Positional and keyword calls with three arguments keep working.
  - `contract.output_to_dict(out)["say"]` items: `{"who", "mood", "text"}`, plus `"look"` only when it isn't `"forward"`.

- [ ] **Step 1: Write the failing tests**

Add these methods to `class OutputTest` in `tests/test_contract.py` (it already has `self.m` from `setUp` and a `self.problems(obj)` helper that returns the list of problems):

```python
    def test_look_defaults_to_forward(self):
        out = contract.parse_output('{"say": [{"who": "pluto", "mood": "happy", "text": "hi"}]}', self.m)
        self.assertEqual(out.say[0].look, "forward")

    def test_look_side_is_accepted(self):
        out = contract.parse_output(json.dumps(
            {"say": [{"who": "pluto", "mood": "love", "look": "side", "text": "hi"}]}), self.m)
        self.assertEqual(out.say[0].look, "side")

    def test_bad_look_says_how_to_fix(self):  # Review Focus #1, #2
        for look in ("Side", "left", None, ["side"], {"look": "side"}):
            with self.subTest(look=look):
                probs = self.problems({"say": [{"who": "pluto", "mood": "happy", "look": look, "text": "hi"}]})
                self.assertEqual(len(probs), 1, probs)
                self.assertIn('say[0].look', probs[0])
                self.assertIn('must be "forward" or "side" (leave it out for "forward")', probs[0])

    def test_output_to_dict_leaves_out_forward_look(self):
        out = contract.parse_output(json.dumps({"say": [
            {"who": "charon", "mood": "happy", "text": "a"},
            {"who": "pluto", "mood": "love", "look": "side", "text": "b"}]}), self.m)
        self.assertEqual(contract.output_to_dict(out)["say"], [
            {"who": "charon", "mood": "happy", "text": "a"},
            {"who": "pluto", "mood": "love", "look": "side", "text": "b"}])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest tests.test_contract.OutputTest -v`
Expected: the four new tests FAIL or ERROR. `test_look_defaults_to_forward` should raise `AttributeError: 'Say' object has no attribute 'look'`. The other existing tests still pass.

- [ ] **Step 3: Implement**

In `orbit/contract.py`, add this below `MOODS = (...)`:

```python
LOOKS = ("forward", "side")  # forward: at the person at the terminal; side: toward the other planet
```

Replace `class Say`:

```python
@dataclass(frozen=True)
class Say:
    who: str
    mood: str
    text: str
    # Which way the planet looks. Last, with a default, so Say(who, mood, text) still works
    # and a capability that leaves "look" out gets forward.
    look: str = "forward"
```

In `_says`, add this right after the `mood` check (before `text = s.get("text")`):

```python
        look = s.get("look", "forward")
        if look not in LOOKS:
            bad(f"{where}.look", 'must be "forward" or "side" (leave it out for "forward")')
            ok = False
```

In the same function, change `out.append(Say(s["who"], s["mood"], text))` to:

```python
            out.append(Say(s["who"], s["mood"], text, look))
```

(`look not in LOOKS` compares by equality, so `None`, lists and dicts are simply "not in" and don't raise.)

Replace the `"say"` line of `output_to_dict`, and add a helper above it:

```python
def _say_to_dict(s: Say) -> dict:
    """Leaves out look when it's forward, the same way capability authors write it, so test
    cases and `orbit dev run` output don't need "look": "forward" everywhere."""
    d = {"who": s.who, "mood": s.mood, "text": s.text}
    if s.look != "forward":
        d["look"] = s.look
    return d
```

```python
        "say": [_say_to_dict(s) for s in out.say],
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m unittest tests.test_contract -v`
Expected: all PASS.

- [ ] **Step 5: Update the contract doc**

In `docs/capability-contract.md`:

1. In the `## Output` example (the ` ```json output ` block), change the say line to:
   ```json
     "say": [{"who": "pluto", "mood": "love", "look": "side", "text": "lunch at 1?"}],
   ```
2. Replace the `say` row of the output table with:
   ```markdown
   | `say` | A list of `{"who", "mood", "text"}`, each with an optional `"look"`. `who` is `"pluto"` or `"charon"`. `mood` is one of `neutral`, `happy`, `sleepy`, `love`, `thinking`, `worried`. `text` is 1–280 characters, and newlines are fine. `look` is which way the planet looks: `"forward"`, at the person at the terminal (the default, so leave it out), or `"side"`, toward the other planet. Use `"side"` when the bubble carries the other person's words or reaches toward them, like a note being sent or delivered. |
   ```
3. In the `## Tests` example (the ` ```json case ` block), change the expected say line to:
   ```json
       "say": [{"who": "charon", "mood": "happy", "look": "side", "text": "Sent! I'll make sure Pluto gets it."}]
   ```

- [ ] **Step 6: Update the design spec §5.4**

In `docs/superpowers/specs/2026-10-03-orbit-design.md` §5.4:

1. In the JSON example, change the `say` line to:
   ```json
     "say":    [{"who": "pluto", "mood": "love", "look": "side", "text": "Pluto says: lunch at 1?"}],
   ```
2. Replace the `say[].who` bullet with:
   ```markdown
   - `say[].who` is `"pluto"` or `"charon"`. `mood` is one of `neutral`,
     `happy`, `sleepy`, `love`, `thinking`, `worried`. `text` is at most 280
     characters. `look` is optional: `"forward"` (the default, at the person at
     the terminal) or `"side"` (toward the other planet). See
     `docs/superpowers/specs/2026-10-04-look-direction-design.md`.
   ```

- [ ] **Step 7: Run the doc check and the full suite**

Run: `python3 -m unittest tests.test_contract_doc -v && python3 -W error::ResourceWarning -m unittest`
Expected: all PASS. `test_contract_doc` validates the two edited JSON examples against the new contract.

- [ ] **Step 8: Commit**

```bash
git add orbit/contract.py tests/test_contract.py docs/capability-contract.md docs/superpowers/specs/2026-10-03-orbit-design.md
git commit -m "contract: optional say look, forward (default) or side

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Art folders and rendering

**Files:**
- Move: `orbit/art/{pluto,charon}/<mood>.txt` → `orbit/art/{pluto,charon}/side/<mood>.txt` (12 files)
- Create: `orbit/art/{pluto,charon}/forward/<mood>.txt` (12 files, from commit `e5c45b4`)
- Modify: `orbit/characters.py` (`load_art`, `render`, `render_says`, module docstring)
- Test: `tests/test_characters.py`
- Replace: `tests/golden/<who>_<mood>.txt` (12) → `tests/golden/<who>_<look>_<mood>.txt` (24)
- Modify: `CLAUDE.md` (map row for `orbit/characters.py`)
- Modify: `docs/superpowers/specs/2026-10-03-orbit-design.md` (§3 tree, §8, test plan line "**characters:**")

**Interfaces:**
- Consumes: `contract.LOOKS`, and `Say.look` from Task 1.
- Produces:
  - `characters.load_art(who: str, mood: str, look: str = "forward") -> list[str]`
  - `characters.render(who: str, mood: str, text: str, color: bool = False, look: str = "forward") -> str`
  - `render_says(says, color=False)` uses each `Say.look`.

- [ ] **Step 1: Move the side art and restore the forward art**

The current art (merged to main in PR #3) is the side art. The forward art is the art from before it, at commit `e5c45b4`.

```bash
cd /home/becca/Claude/orbit
for who in pluto charon; do
  mkdir -p orbit/art/$who/side orbit/art/$who/forward
  git mv orbit/art/$who/*.txt orbit/art/$who/side/
  for m in neutral happy love sleepy thinking worried; do
    git show e5c45b4:orbit/art/$who/$m.txt > orbit/art/$who/forward/$m.txt
  done
done
git add orbit/art
cat orbit/art/pluto/forward/happy.txt orbit/art/pluto/side/happy.txt orbit/art/charon/forward/happy.txt orbit/art/charon/side/happy.txt
```

Expected output (forward Pluto, side Pluto, forward Charon, side Charon):

```
   .-~~~~-.
  /  ^  ^  \
 |   \__/   |
  \   ♥    /
   '-....-'
    .-~~~~-.   o
   /    ^ ^ \
  |     \_/  |
   \   ♥     /
    '-....-'
    .^^^^.
   / ^  ^ \
  |  \__/  |
   '.____.'
♥   .^^^^.
   /^ ^   \
  | \_/    |
   '.____.'
```

- [ ] **Step 2: Write the failing tests**

In `tests/test_characters.py`:

1. Change the imports at the top to:
   ```python
   import os
   import tempfile
   import unittest
   from pathlib import Path
   from unittest import mock

   from orbit import characters
   from orbit.characters import display_width
   from orbit.contract import LOOKS, MOODS, WHO, Say
   from tests.helpers import REPO
   ```

2. Replace `ArtTest.test_every_who_and_mood_has_art_within_limits` with:
   ```python
       def test_every_who_look_and_mood_has_art_within_limits(self):
           for who in WHO:
               for look in LOOKS:
                   for mood in MOODS:
                       path = characters.ART_DIR / who / look / f"{mood}.txt"
                       with self.subTest(path=str(path)):
                           self.assertTrue(path.is_file())
                           lines = path.read_text(encoding="utf-8").rstrip("\n").split("\n")
                           self.assertLessEqual(len(lines), 6)
                           self.assertLessEqual(max(display_width(line) for line in lines), characters.ART_WIDTH)
   ```

3. Replace `RenderTest.test_pluto_faces_right_and_charon_faces_left` with these two tests:
   ```python
       def test_forward_faces_the_person_at_the_terminal(self):
           p = characters.render("pluto", "happy", "hi").split("\n")[1]
           self.assertIn("/  ^  ^  \\", p)                 # eyes centered
           self.assertLess(p.index("^"), p.index("| hi"))  # Pluto on the left
           c = characters.render("charon", "happy", "hi").split("\n")[1]
           self.assertIn("/ ^  ^ \\", c)
           self.assertLess(c.index("| hi"), c.index("^"))  # Charon on the right

       def test_side_looks_toward_the_other_planet(self):
           p = characters.render("pluto", "happy", "hi", look="side").split("\n")[1]
           self.assertIn("/    ^ ^ \\", p)  # eyes on the right, toward Charon
           c = characters.render("charon", "happy", "hi", look="side").split("\n")[1]
           self.assertIn("/^ ^   \\", c)    # eyes on the left, toward Pluto
   ```

4. Replace `RenderTest.test_rows_fit_in_60_columns` with:
   ```python
       def test_rows_fit_in_60_columns(self):  # Review Focus #5
           for who in WHO:
               for look in LOOKS:
                   for mood in MOODS:
                       for row in characters.render(who, mood, SAMPLE * 3, look=look).split("\n"):
                           with self.subTest(who=who, look=look, mood=mood):
                               self.assertLessEqual(display_width(row), 60, row)
   ```

5. Add to `RenderTest`:
   ```python
       def test_render_says_uses_each_bubbles_look(self):  # Review Focus #3
           out = characters.render_says([Say("charon", "happy", "morning!"),
                                         Say("pluto", "love", "her note", "side")])
           self.assertIn("/ ^  ^ \\", out)    # Charon faces you
           self.assertIn("/    ♥ ♥ \\", out)  # Pluto looks toward Charon
   ```

6. Replace `RenderTest.test_golden_renders` with:
   ```python
       def test_golden_renders(self):
           for who in WHO:
               for look in LOOKS:
                   for mood in MOODS:
                       with self.subTest(who=who, look=look, mood=mood):
                           got = characters.render(who, mood, SAMPLE, look=look) + "\n"
                           path = GOLDEN / f"{who}_{look}_{mood}.txt"
                           if os.environ.get("ORBIT_UPDATE_GOLDEN"):
                               path.parent.mkdir(exist_ok=True)
                               path.write_text(got, encoding="utf-8")
                           self.assertEqual(got, path.read_text(encoding="utf-8"))
   ```

7. Add a new class at the end of the file:
   ```python
   class FallbackTest(unittest.TestCase):  # Review Focus #4
       """load_art falls back <look>/<mood> → <look>/neutral → forward/<mood> → forward/neutral → (who)."""

       def setUp(self):
           tmp = tempfile.TemporaryDirectory()
           self.addCleanup(tmp.cleanup)
           root = Path(tmp.name)
           for rel, art in {"pluto/forward/neutral.txt": "FN", "pluto/forward/happy.txt": "FH",
                            "pluto/side/neutral.txt": "SN", "pluto/side/love.txt": "SL"}.items():
               (root / rel).parent.mkdir(parents=True, exist_ok=True)
               (root / rel).write_text(art + "\n", encoding="utf-8")
           patcher = mock.patch.object(characters, "ART_DIR", root)
           patcher.start()
           self.addCleanup(patcher.stop)

       def test_chain(self):
           cases = [("side", "love", ["SL"]),       # exact
                    ("side", "happy", ["SN"]),      # same look, neutral, before forward/happy
                    ("forward", "happy", ["FH"]),   # exact
                    ("forward", "sleepy", ["FN"]),  # forward neutral
                    ("up", "happy", ["FH"]),        # unknown look: forward/<mood>
                    ("up", "sleepy", ["FN"])]       # unknown look and mood: forward/neutral
           for look, mood, want in cases:
               with self.subTest(look=look, mood=mood):
                   self.assertEqual(characters.load_art("pluto", mood, look), want)

       def test_no_art_at_all_shows_the_name(self):
           self.assertEqual(characters.load_art("charon", "happy", "side"), ["(charon)"])
   ```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python3 -m unittest tests.test_characters -v`
Expected: FAIL or ERROR. `render() got an unexpected keyword argument 'look'`, `load_art() takes 2 positional arguments`, and the forward test fails because `load_art` still reads `orbit/art/<who>/<mood>.txt`, which is now gone, so it renders `(pluto)`.

- [ ] **Step 4: Implement**

In `orbit/characters.py`, replace `load_art`:

```python
def load_art(who: str, mood: str, look: str = "forward") -> list[str]:
    """The art for one bubble, from orbit/art/<who>/<look>/<mood>.txt.

    Falls back <look>/<mood> → <look>/neutral → forward/<mood> → forward/neutral, so a
    new mood or look that's only partly drawn still shows something sensible.
    """
    for lk, m in ((look, mood), (look, "neutral"), ("forward", mood), ("forward", "neutral")):
        path = ART_DIR / who / lk / f"{m}.txt"
        if path.is_file():
            return [line.rstrip() for line in path.read_text(encoding="utf-8").rstrip("\n").split("\n")]
    return [f"({who})"]
```

Change the first two lines of `render`:

```python
def render(who: str, mood: str, text: str, color: bool = False, look: str = "forward") -> str:
    art = load_art(who, mood, look) + [who.capitalize().center(ART_WIDTH).rstrip()]
```

Change `render_says`:

```python
def render_says(says: Sequence[Say], color: bool = False) -> str:
    return "\n\n".join(render(s.who, s.mood, s.text, color, s.look) for s in says)
```

Replace the module docstring's first paragraph:

```python
"""ASCII Pluto and Charon with speech bubbles.

Pluto sits on the left and Charon on the right. Each bubble's `look` picks the art:
"forward" looks at the person at the terminal, and "side" looks toward the other planet
(Pluto right, Charon left), so a note being passed reads as the two facing each other.
Text is cleaned of control characters first: notes come from the other machine, and
an escape code in a note must not be able to clear the screen or change colors.
"""
```

- [ ] **Step 5: Replace the saved reference renders**

```bash
git rm -q tests/golden/pluto_*.txt tests/golden/charon_*.txt
ORBIT_UPDATE_GOLDEN=1 python3 -m unittest tests.test_characters
ls tests/golden | wc -l
cat tests/golden/pluto_forward_happy.txt tests/golden/charon_side_love.txt
```

Expected: `24`. Pluto forward happy has its eyes centered (`/  ^  ^  \`), and Charon side love has its eyes on the left (`/♥ ♥   \`) with the `♥` moon at the top left.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python3 -m unittest tests.test_characters -v && python3 -W error::ResourceWarning -m unittest`
Expected: all PASS.

- [ ] **Step 7: Update the docs that describe the art**

1. `CLAUDE.md`, map row: replace
   ```markdown
   | `orbit/characters.py` | ASCII art (`orbit/art/<who>/<mood>.txt`) and speech bubbles |
   ```
   with
   ```markdown
   | `orbit/characters.py` | ASCII art (`orbit/art/<who>/<look>/<mood>.txt`; look is `forward` or `side`) and speech bubbles |
   ```
2. `docs/superpowers/specs/2026-10-03-orbit-design.md`, §3 tree: replace
   `│   └── art/{pluto,charon}/<mood>.txt` with `│   └── art/{pluto,charon}/{forward,side}/<mood>.txt`.
3. Same file, §8: replace the first two bullets with:
   ```markdown
   - Art lives in plain text files: `orbit/art/<who>/<look>/<mood>.txt`, where
     look is `forward` (at the person at the terminal) or `side` (toward the
     other planet). Each is 6 lines or fewer and 16 columns or narrower. Every
     mood listed in §5.4 exists in both looks for both characters. Missing art
     falls back <look>/<mood> → <look>/neutral → forward/<mood> → forward/neutral.
   - `characters.render(who, mood, text, look=...)` returns the art next to a
     word-wrapped speech bubble, 60 columns wide in total.
   ```
4. Same file, test plan: replace
   `- **characters:** saved reference output for every \`who\`×\`mood\`, plus`
   with
   `- **characters:** saved reference output for every \`who\`×\`look\`×\`mood\`, plus`.

- [ ] **Step 8: Commit**

```bash
git add orbit/art orbit/characters.py tests/test_characters.py tests/golden CLAUDE.md docs/superpowers/specs/2026-10-03-orbit-design.md
git commit -m "characters: forward and side art, chosen per bubble

Forward (at the person at the terminal) is the art from before the
tidally-locked change; side is the tidally-locked art. load_art falls
back so a partly drawn mood or look still renders.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Notes looks to the side; template and skill explain `look`

**Files:**
- Modify: `capabilities/notes/main.py` (`send`, `login`, module docstring)
- Modify: `capabilities/notes/tests/note_command.json`, `capabilities/notes/tests/login_unread.json`
- Create: `capabilities/notes/tests/login_overflow.json`
- Modify: `capabilities/example/main.py` (comment only)
- Modify: `.claude/skills/new-capability/SKILL.md` (one bullet)

**Interfaces:**
- Consumes: the contract accepts `"look": "side"` (Task 1), and `output_to_dict` leaves out forward, so capability cases that don't mention `look` mean forward (Task 1).
- Produces: nothing new for later tasks.

- [ ] **Step 1: Update and add the failing test cases**

In `capabilities/notes/tests/note_command.json`, change the `say` line to:

```json
    "say": [{"who": "charon", "mood": "happy", "look": "side", "text": "Sent! I'll make sure Pluto gets it."}]
```

In `capabilities/notes/tests/login_unread.json`, change the `say` line to:

```json
    "say": [{"who": "pluto", "mood": "love", "look": "side", "text": "✉ Note from Pluto · 1:00 pm\ngood luck today!"}],
```

Create `capabilities/notes/tests/login_overflow.json`. Six unread notes: five are said, and the sixth is summarized. The default `now` in case input is `2026-10-03T14:00:00Z` and tests run with `TZ=UTC`, so same-day times show without a date.

```json
{
  "description": "more than five unread notes: five are said, the rest summarized; all look to the side",
  "input": {
    "trigger": {"kind": "login"},
    "events": [
      {"origin": "pluto", "seq": 1, "type": "notes.sent", "ts": "2026-10-03T13:00:00Z", "v": 1, "data": {"text": "one"}},
      {"origin": "pluto", "seq": 2, "type": "notes.sent", "ts": "2026-10-03T13:01:00Z", "v": 1, "data": {"text": "two"}},
      {"origin": "pluto", "seq": 3, "type": "notes.sent", "ts": "2026-10-03T13:02:00Z", "v": 1, "data": {"text": "three"}},
      {"origin": "pluto", "seq": 4, "type": "notes.sent", "ts": "2026-10-03T13:03:00Z", "v": 1, "data": {"text": "four"}},
      {"origin": "pluto", "seq": 5, "type": "notes.sent", "ts": "2026-10-03T13:04:00Z", "v": 1, "data": {"text": "five"}},
      {"origin": "pluto", "seq": 6, "type": "notes.sent", "ts": "2026-10-03T13:05:00Z", "v": 1, "data": {"text": "six"}}
    ]
  },
  "expect": {
    "say": [
      {"who": "pluto", "mood": "love", "look": "side", "text": "✉ Note from Pluto · 1:00 pm\none"},
      {"who": "pluto", "mood": "love", "look": "side", "text": "✉ Note from Pluto · 1:01 pm\ntwo"},
      {"who": "pluto", "mood": "love", "look": "side", "text": "✉ Note from Pluto · 1:02 pm\nthree"},
      {"who": "pluto", "mood": "love", "look": "side", "text": "✉ Note from Pluto · 1:03 pm\nfour"},
      {"who": "pluto", "mood": "love", "look": "side", "text": "✉ Note from Pluto · 1:04 pm\nfive"},
      {"who": "pluto", "mood": "happy", "look": "side", "text": "…and 1 more. See them all with: orbit notes"}
    ],
    "emit": [{"type": "notes.seen", "data": {"seqs": [1, 2, 3, 4, 5, 6]}, "v": 1}],
    "prompt": ""
  }
}
```

Leave `login_receipt.json` alone: the read receipt faces you (forward), so it has no `look`.

- [ ] **Step 2: Run the cases to verify they fail**

Run: `bin/orbit dev test notes`
Expected: `note_command.json`, `login_unread.json` and `login_overflow.json` FAIL. Their expected `say` has `"look": "side"` and the actual output doesn't. Every other notes case passes.

- [ ] **Step 3: Implement**

In `capabilities/notes/main.py`, change the `say` in `send()` to:

```python
            "say": [{"who": inp["me"]["name"], "mood": "happy", "look": "side",
                     "text": f"Sent! I'll make sure {NAMES[inp['peer']['name']]} gets it."}]}
```

In `login()`, change the two `say.append` calls inside the notes part (leave the receipt one alone):

```python
    for e in notes[:MAX_SHOWN]:
        say.append({"who": peer, "mood": "love", "look": "side", "text": incoming(e, inp)})
    if len(notes) > MAX_SHOWN:
        say.append({"who": peer, "mood": "happy", "look": "side",
                    "text": f"…and {len(notes) - MAX_SHOWN} more. See them all with: orbit notes"})
```

Add this line to the module docstring, after the "The sender then gets a read receipt…" line:

```
Bubbles that pass a note between the planets (sent, and each delivered note) look to the side,
toward the other planet; the read receipt is news for you, so it faces forward (no "look").
```

- [ ] **Step 4: Run the cases to verify they pass**

Run: `bin/orbit dev test notes && bin/orbit dev test companions && bin/orbit dev test example`
Expected: all PASS. Companions and example cases are unchanged and still pass, because forward is left out on both sides.

- [ ] **Step 5: Explain `look` in the template and the skill**

In `capabilities/example/main.py`, replace the two comment lines above `"say"`:

```python
            # "say": speech bubbles. Use your own machine's character (inp["me"]["name"])
            # unless the words come from the other person.
```

with:

```python
            # "say": speech bubbles. Use your own machine's character (inp["me"]["name"])
            # unless the words come from the other person. Bubbles look forward, at the
            # person at the terminal. Add "look": "side" to make the planet look toward the
            # other one instead: do that when the bubble carries the other person's words
            # or reaches toward them (notes does it for sent and delivered notes).
```

In `.claude/skills/new-capability/SKILL.md`, section `## 4. Implement main.py`, add this bullet after the `say.text ≤ 280` bullet:

```markdown
- `say` bubbles look forward, at the person at the terminal. Add `"look": "side"` only when
  the bubble carries the other person's words or reaches toward them (notes does this for
  sent and delivered notes); otherwise leave `look` out.
```

- [ ] **Step 6: Run the full suite**

Run: `python3 -W error::ResourceWarning -m unittest`
Expected: all PASS. `tests/test_capabilities.py` runs every capability's cases, including `login_overflow.json`.

- [ ] **Step 7: Commit**

```bash
git add capabilities/notes capabilities/example/main.py .claude/skills/new-capability/SKILL.md
git commit -m "notes: sent and delivered notes look to the side

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Examples, end-to-end check, push

**Files:**
- Modify: `docs/go-orbit/index.html` (the example greeting, ~lines 128–133)
- Check (no change expected): `README.md`

**Interfaces:**
- Consumes: forward and side art (Task 2), notes looks (Task 3).
- Produces: nothing.

- [ ] **Step 1: Make the go/orbit greeting face forward**

In `docs/go-orbit/index.html`, the Pluto greeting is a login greeting, so it looks forward. Replace the six Pluto lines:

```html
<pre><span class="pl">    .-~~~~-.   o</span>  .-----------------.
<span class="pl">   /    ^ ^ \   </span> &lt;| Good morning! ☀ |
<span class="pl">  |     \_/  |  </span>  '-----------------'
<span class="pl">   \   ♥     /</span>
<span class="pl">    '-....-'</span>
<span class="pl">     Pluto</span>
```

with:

```html
<pre><span class="pl">   .-~~~~-.     </span>  .-----------------.
<span class="pl">  /  ^  ^  \    </span> &lt;| Good morning! ☀ |
<span class="pl"> |   \__/   |   </span>  '-----------------'
<span class="pl">  \   ♥    /</span>
<span class="pl">   '-....-'</span>
<span class="pl">     Pluto</span>
```

Leave the Charon note below it unchanged: a delivered note looks to the side, which is what it already shows.

- [ ] **Step 2: Check the README example**

Run: `sed -n 8,15p README.md`
Expected: Pluto saying "lunch at 1?" with side art (`/    ♥ ♥ \` and the `o` moon). That's a delivered note, so it stays as it is. If it shows forward art instead, replace it with the output of:
`python3 -c "from orbit import characters as c; print(c.render('pluto','love','lunch at 1?', look='side'))"`

- [ ] **Step 3: Look at a real greeting**

Run:

```bash
python3 -c "
from orbit import characters as c
from orbit.contract import Say
print(c.render_says([Say('charon','happy','Good morning! ☀'),
                     Say('charon','happy','Pluto read your note \"lunch at 1?\" ♥'),
                     Say('pluto','love','✉ Note from Pluto · 11:58 pm\nsleep well ♥','side')]))"
```

Expected: Charon facing forward twice (eyes centered, no `♥` moon), then Pluto with its eyes to the right and the `o` moon.

- [ ] **Step 4: Run everything**

Run: `python3 -W error::ResourceWarning -m unittest && for c in notes companions example presence; do bin/orbit dev test $c || exit 1; done`
Expected: all PASS.

- [ ] **Step 5: Commit and push**

```bash
git add docs/go-orbit/index.html
git commit -m "go/orbit page: greeting faces forward, note looks to the side

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push
```

- [ ] **Step 6: Report rollout steps to Becca**

Tell Becca that, after the branch is merged to main:
- Run `orbit update` on charon, and on pluto (Gabby). Core and notes both changed. Until a machine is updated, its bubbles all show the side art that's on main now.
- Republish Gabby's go/orbit page (artifact `https://claude.ai/artifact/Lree7siUwTuD9tJEdsaqL7`) from `docs/go-orbit/index.html`.
