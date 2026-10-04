# Orbit — what to work on next

A shared list for Becca and Gabby (and their Claudes). Pick something, move it to
"In progress" with your name, and delete it when it's merged. Anything that adds a
feature should usually be a capability: see `CLAUDE.md` and the `new-capability` skill.

## Next up

### Login nudge when the other machine has newer code

`orbit update` and the doctor check are done; orbitd's `/health` now reports `commit`.
What's left: have the companions greeting say, for example, Pluto: "Charon has newer
code! Try `orbit update`". That needs the peer's commit in the capability input; one way
is to carry it in the peer status. `doctor.commit_mismatch` already works out who's behind.

## Known issues (small)

- **Reinstall: notes can look already read.** After pluto (or charon) is reinstalled,
  the other machine's own `notes.seen` events still list the *old* install's note
  numbers. The new install's first notes then look already read at login, though
  `orbit notes` still shows them. Fix: record the peer's instance id in `notes.seen`
  (`{"seqs": [...], "instance": "..."}`) and ignore seen events from a different
  instance. Reveal day isn't affected, since both machines start fresh.
- **Reinstall: order of writes in `orbit/sync.py` `new_installation`.** It stores the
  new `peer_instance` *before* `forget_origin` and the cursor reset. If the DB is locked
  between those steps, the next pull never forgets and skips the new install's early
  events. Fix: write `peer_instance` last, or do all three steps in one transaction.
- **Emoji joined with ZWJ** (👩‍❤️‍👩, 🏳️‍🌈) get split apart in bubbles, and emoji with
  VS16 are measured one column too narrow (`orbit/characters.py`). `isprintable()`
  also rejects them in `prompt`.
- **A locked database in the CLI** shows a Python traceback instead of a friendly
  "try again" message (spec §13).
- **Prompt refresh race:** the CLI and the daemon can both rebuild `~/.orbit/prompt`
  from different snapshots, so the prompt can be stale for up to 60 s.
- **`orbit doctor`:** add an explicit `tailscale whois` check of the peer's IP, and
  don't exit 1 just because the peer is switched off.

## Ideas (from the design doc)

- **New character art.** Becca wants another pass. See `orbit/art/README.md`.
- **A go link web page** (`go/orbit`): the two characters orbiting each other, recent
  notes, and a way to send one from a phone. It would be another place the characters
  show up, reading the store, not a capability.
- **Rituals:** countdowns ("12 days until the trip"), a shared grocery or todo list, and
  a gratitude jar that brings back an old note now and then.
- **Memory search:** `orbit ask "what was that ramen place?"` over shared notes.
- **Home Assistant:** a lamp glows when a note arrives. There's a `homeassistant` node
  on the tailnet.

## In progress

_Nothing yet._
