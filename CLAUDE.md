# Orbit — notes for Claude

Orbit gives two Linux machines on one tailnet, **charon** (Becca's) and **pluto**
(Gabby's; Gabby is Becca's girlfriend), a pair of terminal companions: ASCII Pluto
and Charon. It was a gift. Its owners grow it by adding **capabilities**.

- Design: `docs/superpowers/specs/2026-10-03-orbit-design.md` (read §18 too)
- **Capability contract: `docs/capability-contract.md`.** This is the one source of
  truth for capability input and output.

## Adding or changing a capability

Use the **new-capability** skill (`.claude/skills/new-capability/SKILL.md`). In short:
copy `capabilities/example/`, write `tests/*.json` cases first, implement, then run
`orbit dev test <name>`. You should almost never need to change `orbit/` (the core)
to add a feature.

## Map

| Path | Job |
|---|---|
| `orbit/cli.py` | `orbit <command>`: greet, help, init, and routing to capability commands |
| `orbit/loader.py` | finds capabilities, builds their input, runs them, applies their output, disables failing ones |
| `orbit/contract.py` | validation of manifests and output (enforces the contract doc) |
| `orbit/store.py` | SQLite event log (`events`, `latest`, `meta`) |
| `orbit/sync.py` | pulls the peer's events over HTTP; poke; backoff |
| `orbit/daemon.py` | orbitd: HTTP API, `tailscale whois` auth, pull and tick loop |
| `orbit/characters.py` | ASCII art (`orbit/art/<who>/<mood>.txt`) and speech bubbles |
| `orbit/prompt.py` | builds `~/.orbit/prompt` from each capability's segment |
| `orbit/devtools.py` | `orbit dev run`, `orbit dev test`, `orbit dev peer` |
| `orbit/doctor.py` | `orbit doctor` health checks |
| `orbit/config.py` | `~/.orbit/config.json` (`$ORBIT_DIR` overrides the folder) |
| `orbit/log.py` | append-only logs in `~/.orbit/logs/` |
| `capabilities/` | one folder per capability: example, notes, presence, companions |
| `shell/orbit.bash` | the `~/.bashrc` block; `install.sh` installs it |
| `tests/` | `unittest` suites; `tests/fixtures/capabilities/ping` is a test-only capability |

## Invariants (don't break these)

1. **Python stdlib only**, Python ≥ 3.11. No pip installs, ever: pluto gets a plain copy.
2. **Nothing on the shell-prompt path runs Python.** The shell only reads `~/.orbit/prompt`.
3. **Capabilities never touch the DB, the network or `~/.orbit`.** Input comes on stdin and output goes to stdout.
4. **Events are never edited or deleted.** To undo something, emit a new event.
   (Sole exception: `Store.forget_origin`, when the peer turns out to be a new installation.)
5. **Order by `seq` or arrival, never `ts`.** The two machines' clocks can differ.
6. **Every error message says where, what, and how to fix it.**
7. **Small files with one job each** (under about 300 lines), type hints, and docstrings that say *why*.
8. **Capability code doesn't sync.** After changing a capability, remind the person
   to install it on both machines. `orbit doctor` flags any mismatch.
9. **Wording:** the people are Becca and Gabby. Say "girlfriend", never a generic stand-in for her.
10. **Close what you open.** Tests close every `Store`/runtime they open (`rt.store.close()`), and per-request threads call `store.release()`; `python3 -W error::ResourceWarning -m unittest` must stay clean.

## Verify your work

```bash
python3 -m unittest                                  # everything, in under 30 s
bin/orbit dev test <name>                            # one capability's cases
bin/orbit dev run <name> <trigger> [command] [args]  # one dry run with real local data; writes nothing
bin/orbit doctor                                     # config, daemon, peer, manifests
```

## Testing with two machines on one computer

Use a separate data folder, so test notes, cursors and fake-pluto events never land in
the real `~/.orbit` (they would confuse the real pluto on reveal day). Set it in every
terminal you use for testing:

```bash
export ORBIT_DIR=~/.orbit-dev                          # keeps test data out of the real ~/.orbit
bin/orbit init --dev --me charon --peer pluto          # point this test folder at the fake peer
bin/orbit daemon &                                     # this machine's daemon (not systemd: it would use the real ~/.orbit)
bin/orbit dev peer                                     # fake pluto on 127.0.0.1:1979 (its own terminal)
bin/orbit dev peer note "hi from fake pluto"           # run any command *as* the fake peer
bin/orbit greet                                        # see it arrive
```

The fake peer keeps its data in `~/.orbit-devpeer`. To go back to the real setup,
`unset ORBIT_DIR`; `~/.orbit` was never touched.

## Data on disk

`~/.orbit/` contains `config.json`, `orbit.db`, `prompt` and `logs/<name>.log`.
When something misbehaves, read the logs first.
