# Look direction: planets face you, or each other

Date: 2026-10-04 · Branch: `feat/look-direction` (built on `feat/tidally-locked-art`)
Status: design approved in chat; waiting for review of this spec.

## 1. Goal

Each speech bubble can choose which way its planet looks:

- **forward**: at the person at the terminal (the art on `main` before
  `feat/tidally-locked-art`).
- **side**: toward the other planet (the tidally-locked art from
  `feat/tidally-locked-art`: Pluto looks right, Charon looks left, and each has a
  tiny version of the other in that corner).

Rule of thumb for capability authors: **look forward when talking to the person
at the terminal; look to the side when carrying the other person's words or
reaching toward them.**

Every capability makes this choice the same way, through one optional key in the
capability contract. No capability needs code of its own for it.

## 2. Decisions (from Becca)

| # | Capability · when | Who speaks | Look |
|---|---|---|---|
| 1 | companions · login greeting (time of day) | own planet | forward |
| 2 | companions · login, peer offline line | own planet | forward |
| 3 | companions · `orbit hi` | own planet | forward |
| 4 | notes · `orbit note` "Sent!" confirmation | own planet | **side** |
| 5 | notes · login read receipt | own planet | forward |
| 6 | notes · login, each unread note | peer's planet | **side** |
| 7 | notes · login, "…and N more" | peer's planet | **side** |
| 8 | example · `orbit hello` | own planet | forward |

- **`look` is left out when it's forward**, in capability code and in capability
  test cases. Write `"look": "side"` only where it applies.
- **The little moon** (`o` next to Pluto, `♥` next to Charon) only appears in the side art.

## 3. Contract

`say` entries gain an optional key:

```json
{"who": "pluto", "mood": "love", "look": "side", "text": "lunch at 1?"}
```

- `look` is `"forward"` or `"side"`. Leaving it out means `"forward"`.
- Any other value is an output error, reported like the other `say` errors:
  `say[0].look: must be "forward" or "side" (leave it out for "forward")`.
- The contract stays at **v1**. The key is optional, and an older core ignores
  keys it doesn't know, so a capability that sends `look` to a core that hasn't
  been updated still shows its bubble, facing forward.

`orbit/contract.py`:

- `LOOKS = ("forward", "side")` next to `MOODS`. This is the one shared definition.
- `Say` gains `look: str = "forward"` (after `text`, so existing
  `Say(who, mood, text)` calls keep working).
- `_says` validates `look` as described above.
- `output_to_dict` writes `look` only when it isn't `"forward"`. This keeps the
  comparable form the same as what authors write, so `orbit dev run` output and
  test cases match without `"look": "forward"` everywhere.

## 4. Art

Art moves into one folder per direction:

```
orbit/art/<who>/forward/<mood>.txt   # the art from main (e5c45b4)
orbit/art/<who>/side/<mood>.txt      # the art from feat/tidally-locked-art (7e4e6f0)
```

- Every mood exists in both directions for both planets: 2 × 2 × 6 = 24 files, each
  at most 6 lines and 16 columns, as before.
- `load_art(who, mood, look="forward")` tries these in order, so a new mood or
  direction drawn only partly still shows something sensible:
  1. `<look>/<mood>`
  2. `<look>/neutral`
  3. `forward/<mood>`
  4. `forward/neutral`
  5. `(<who>)`
- An unknown `look` passed straight to `load_art` (not through the contract)
  is treated like a missing file and falls back the same way.

## 5. Rendering

- `characters.render(who, mood, text, color=False, look="forward")`.
- `render_says` passes each `Say.look` through.
- Layout doesn't change: Pluto on the left, Charon on the right, same bubble widths.

## 6. Capabilities

- **notes**: three bubbles add `"look": "side"`: the "Sent!" confirmation in
  `send()`, each unread note in `login()`, and the "…and N more" line.
- **companions**: no change, since everything is forward.
- **example**: no change to its output, plus a comment next to `say` explaining `look`
  and the rule of thumb, since this is the folder new capabilities are copied from.

## 7. Tests

- **Capability test cases** (`capabilities/*/tests/*.json`):
  - An expected `say` entry without `look` means forward, because
    `output_to_dict` leaves out `"forward"`.
  - Only the notes cases that cover rows 4, 6 and 7 change: `note_command.json`,
    `login_unread.json`, and any other case expecting those bubbles.
- **`tests/test_contract.py`**:
  - `look` left out → `Say.look == "forward"`.
  - `"side"` is accepted.
  - A bad value gives the error in §3.
  - `output_to_dict` writes only `side`.
- **`tests/test_characters.py`**:
  - **Art limits:** loop over who × look × mood.
  - **Facing:** forward Pluto's eyes are centered (`^  ^`); side Pluto's eyes sit
    on the right (`^ ^`), and the reverse for Charon.
  - **Fallback:** cover the chain in §4 using a temporary `ART_DIR`.
  - **Saved reference renders:** grow to 24 files,
    `tests/golden/<who>_<look>_<mood>.txt`, replacing the 12 current ones.
    Regenerate them with `ORBIT_UPDATE_GOLDEN=1`.
- **`tests/test_contract_doc.py`** already checks every JSON example in the contract
  doc, so the new example there is checked automatically.
- `python3 -W error::ResourceWarning -m unittest` stays clean.

## 8. Docs

- `docs/capability-contract.md`:
  - the `say` row: add `look`, its default, and the rule of thumb;
  - one output example with `"look": "side"`.
- `docs/superpowers/specs/2026-10-03-orbit-design.md`: §5.4 (`say` fields), §8 (art
  path, both directions), and the tree in §3 (`art/{pluto,charon}/{forward,side}/<mood>.txt`).
- `CLAUDE.md`: the `orbit/characters.py` row in the map mentions the
  `forward`/`side` art folders.
- `.claude/skills/new-capability/SKILL.md`: one line on `look` and the rule of thumb.
- `README.md`: no art change. Its example is Pluto delivering the note "lunch
  at 1?", which already looks to the side on `feat/tidally-locked-art`.
- `docs/go-orbit/index.html`: the greeting (Pluto) looks forward; the note from Charon looks to the side.

## 9. Rollout

- Merge `feat/tidally-locked-art` and `feat/look-direction` together. The first
  branch alone would make every bubble look to the side.
- Install on **both** charon and pluto. `orbit/` (art included) and the notes
  capability change. Until a machine is updated, everything there faces forward,
  because its core ignores `look`.
- After merging, republish Gabby's go/orbit page from `docs/go-orbit/index.html`.

## 10. Out of scope

- More directions (up, away, etc.). Adding one later means one more value in
  `LOOKS` plus one more art folder; the fallback chain covers missing drawings.
- The core choosing direction on its own (for example, from `who`). Capabilities choose.
- Changing bubble layout or which side each planet sits on.
