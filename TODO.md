# Orbit — what to work on next

A shared list for Becca and Gabby (and their Claudes). Pick something, move it to
"In progress" with your name, and delete it when it's merged. Anything that adds a
feature should usually be a capability: see `CLAUDE.md` and the `new-capability` skill.

## Next up

### `orbit update`: one command to get the latest code

**Why:** code doesn't sync between the machines (only events do). After one of you
pushes, the other has to `git pull` and sometimes restart orbitd. `orbit doctor`
flags the mismatch, but nothing fixes it. This command should make updating one step.

**What it does, in order:**
1. **Refuse if the checkout isn't clean.** Run `git -C <repo> status --porcelain`, and
   if it's non-empty, say "you have local changes in <repo> — commit or stash them
   first". Never discard work.
2. **Remember the current commit** (`git rev-parse HEAD`), then
   `git -C <repo> pull --ff-only`. If the fast-forward fails, explain that the branches
   diverged and point to `git pull --rebase` (don't do it automatically).
3. **Work out what changed:** `git diff --name-only OLD NEW`.
   - Nothing changed: print "already up to date" and stop.
   - Only `capabilities/**` changed: no restart is needed, because orbitd rescans
     capabilities every 30 s. Say so.
   - Anything under `orbit/`, `bin/` or `shell/` changed: run
     `systemctl --user restart orbitd`. If systemd isn't available, print the command.
   - `shell/orbit.bash` or `install.sh` changed: suggest re-running `install.sh`. It's
     safe to run again; it replaces the bashrc block.
4. **Show a short summary:** `git log --oneline OLD..NEW`, then run the doctor checks
   (or a subset) so a broken update shows up right away.
5. A character says something cute, for example Charon: "Fresh code, same orbit ♥".

**Where it goes:** this is a **core command**, not a capability, because it touches
the repo and systemd, which capabilities must never do (invariant 3). Steps:
- Add `update` to `RESERVED_COMMANDS` in `orbit/contract.py`, to the reserved list
  in `docs/capability-contract.md`, and to `CORE_COMMANDS` in `orbit/cli.py`.
- Put the logic in a new `orbit/update.py`. One job, as with `doctor.py`.
- Find the repo with `config.REPO_ROOT`.

**Nice extra: tell the other machine when it's behind.**
- Add the current git commit (`git rev-parse --short HEAD`, or `null` if it isn't a
  git checkout) to `/health` alongside `core_version`.
- Have `orbit doctor` print "pluto is on <sha>, charon is on <sha> — run `orbit update`
  on the older one".
- Optionally, the companions login greeting could mention it, for example Pluto:
  "Charon has newer code! Try `orbit update`". That needs the peer's commit in the
  capability input; one way is to carry it in the peer status.

**Tests:**
- Create a temp bare repo as `origin` and clone it.
- Commit a capability-only change upstream, then check: no restart.
- Commit a core change upstream, then check that a fake `systemctl` on `PATH` received
  `--user restart orbitd`.
- A dirty working tree is refused and nothing changes.
- A diverged branch is refused with the hint.
- Never touch the real repo, `~/.orbit` or systemd in tests.

**Convention to adopt alongside it:** bump `CORE_VERSION` in `orbit/__init__.py`
whenever `orbit/` changes in a way the other machine must match.

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
- **zsh support** for the greeting and prompt block, if either of you switches shells.

## In progress

_Nothing yet._
