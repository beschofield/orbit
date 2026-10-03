# Orbit — Design Spec

- **Date:** 2026-10-03
- **Status:** Approved design, pending spec review
- **Working name:** Orbit (may be renamed)

## 1. Purpose

Two Linux machines on the same tailnet, **charon** (Becca's) and **pluto**
(Gabby's, her partner), get a pair of terminal companions: ASCII Pluto and Charon.
Like Pluto and Charon in space, which are tidally locked and orbit a shared
point between them, the two machines are equal peers sharing one small world.

Orbit is a **surprise gift**. Becca builds v1 alone on charon; it is installed
on pluto on reveal day. After that, Gabby extends it by adding new
**capabilities**, mostly by working with Claude. So the code and docs are
designed for **agents first, humans second**.

### Success criteria

- At login, Becca and Gabby are each greeted by the characters. The greeting
  shows unread notes from the other person and a read receipt for notes they
  sent.
- `orbit note "lunch at 1?"` on one machine shows up on the other within a few
  seconds when both are online, and at the next sync when one was offline.
- The shell prompt shows the other person's presence (Gabby's on charon,
  Becca's on pluto), and it never adds noticeable
  latency, even if Orbit is broken.
- A Claude session told "read CLAUDE.md, then use the new-capability skill"
  can add a working, tested capability without changing the core.

### Non-goals (v1)

- No GUI and no web page (the go link page is future work).
- No exposure outside the tailnet; no more than two machines.
- No editing or deleting events once written.
- No dependencies outside the Python 3 standard library at runtime.
- No automatic syncing of capability code between machines.

## 2. Key decisions

| Decision | Choice | Why |
|---|---|---|
| Extensibility | Capabilities are folders holding an executable, a manifest and JSON on stdin/stdout | Works in any language, keeps failures isolated, and is easy for agents to copy |
| Language | Python 3, stdlib only | Becca reads Python; installing on pluto is a copy, not a package install |
| Prompt speed | The daemon writes a prompt file; the shell reads it with `$(<file)` | Python startup (~30 ms with imports) never runs on the prompt path |
| Topology | Two equal daemons, one per machine | Matches the theme; neither machine depends on the other being up |
| Sync | Each machine is the sole source of truth for its own events; the peer pulls them, nudged by a poke | No merging or conflicts, and missed events heal themselves |
| Transport/auth | HTTP over the tailnet; peer verified with `tailscale whois` | Encryption and identity come from Tailscale |
| Port | 1978 (the year Charon was discovered) | Cute; configurable |

## 3. Repository layout

```
orbit/
├── CLAUDE.md                     # agent entry point: map, rules, how to verify
├── README.md                     # human entry point: the story, setup
├── install.sh                    # installs on a machine (see §11)
├── bin/orbit                     # tiny launcher: python3 -m orbit.cli "$@"
├── docs/
│   ├── capability-contract.md    # SINGLE source of truth for the contract
│   ├── reveal-day.md             # install checklist for pluto
│   └── superpowers/specs/        # design specs (this file)
├── orbit/                        # core package (stdlib only)
│   ├── cli.py                    # `orbit <cmd>`: routing, dev tools, doctor
│   ├── daemon.py                 # orbitd: HTTP server, timers, prompt file
│   ├── store.py                  # SQLite event log + "latest" table
│   ├── sync.py                   # pull from peer, poke, backoff
│   ├── loader.py                 # discover, run, validate capabilities
│   ├── contract.py               # validation of manifests and outputs
│   ├── characters.py             # rendering: art + mood + speech bubble
│   ├── config.py                 # load/validate ~/.orbit/config.json
│   └── art/{pluto,charon}/<mood>.txt
├── capabilities/
│   ├── companions/
│   ├── notes/
│   ├── presence/
│   └── example/                  # heavily commented template
├── .claude/skills/new-capability/SKILL.md
├── systemd/orbitd.service        # user unit
└── tests/
```

Each module has one job. If a file grows past ~300 lines, split it.

## 4. Runtime layout and config

Data lives in `~/.orbit/`:

```
~/.orbit/
├── config.json
├── orbit.db          # SQLite, WAL mode, busy_timeout 2000 ms
├── prompt            # ready-to-print prompt segment (may be empty)
└── logs/
    ├── orbitd.log
    └── <capability>.log
```

`config.json`:

```json
{
  "me": "charon",
  "peer": "pluto",
  "peer_host": "pluto",
  "port": 1978,
  "capabilities_dir": "/home/becca/Claude/orbit/capabilities",
  "prompt_order": ["presence", "notes"]
}
```

- `me` and `peer` are character names, and also the `origin` values in events.
- `peer_host` is the MagicDNS name used for HTTP and checked against
  `tailscale whois`.
- Capabilities left out of `prompt_order` come after the listed ones,
  alphabetically.

## 5. Capability contract

The full contract lives in `docs/capability-contract.md`. This section
summarizes it, and that doc must agree with it. `orbit/contract.py` enforces it.

### 5.1 Folder

```
capabilities/<name>/
├── manifest.json
├── main.py          # or any executable named in manifest.run
├── README.md        # what it does, commands, event types
└── tests/
    └── <case>.json  # {"input": {...}, "expect": {...}}
```

`<name>` matches `^[a-z][a-z0-9_]{1,30}$` and equals `manifest.name`.

### 5.2 Manifest

```json
{
  "name": "notes",
  "description": "Leave little notes for each other.",
  "contract": 1,
  "run": "main.py",
  "commands": [
    {"name": "note", "usage": "note <text>", "help": "Send a note to your partner."},
    {"name": "notes", "usage": "notes", "help": "Show recent notes."}
  ],
  "triggers": ["login", "received"],
  "tick_seconds": null,
  "event_types": {
    "notes.sent": {"keep": "log"},
    "notes.seen": {"keep": "log"},
    "notes.receipts_shown": {"keep": "log"}
  },
  "receives": ["notes.sent", "notes.seen"]
}
```

- `run` is executed directly, so it must be executable and have a shebang.
- `triggers` can include: `login`, `tick` (requires `tick_seconds` ≥ 10), and
  `received`. `command` is implied when `commands` isn't empty.
- Every key in `event_types` must start with `<name>.`. `keep` is `log`
  (history is kept forever) or `latest` (only the newest event per origin and
  type is kept).
- `receives` lists the event types (from any capability) that cause a
  `received` trigger when they arrive from the peer.
- Command names are unique across all capabilities. The loader reports
  duplicates as errors, and neither capability gets the command.
- Reserved command names: `dev`, `doctor`, `greet`, `help`.

### 5.3 Input (stdin, one JSON object)

```json
{
  "contract": 1,
  "trigger": {"kind": "command", "name": "note", "args": ["lunch at 1?"]},
  "me":   {"name": "charon"},
  "peer": {"name": "pluto", "online": true, "last_seen": "2026-10-03T14:01:50Z"},
  "now":  "2026-10-03T14:02:11Z",
  "events": [ /* up to 200 most recent events of this capability's types, both origins, oldest first */ ],
  "latest": { "charon": {"presence.status": { /* event */ }}, "pluto": { } }
}
```

Trigger shapes:

- `{"kind": "command", "name": str, "args": [str]}`
- `{"kind": "login"}`
- `{"kind": "tick"}`
- `{"kind": "received", "events": [event, ...]}`

`latest` includes every `keep: latest` event from every capability, so for
example companions can read presence.

### 5.4 Output (stdout, one JSON object; every key optional)

```json
{
  "say":    [{"who": "pluto", "mood": "love", "text": "Pluto says: lunch at 1?"}],
  "emit":   [{"type": "notes.seen", "data": {"seqs": [41, 42]}, "v": 1}],
  "prompt": "✉ 1",
  "print":  "plain text for command output"
}
```

- `say[].who` is `"pluto"` or `"charon"`. `mood` is one of `neutral`,
  `happy`, `sleepy`, `love`, `thinking`, `worried`. `text` is at most 280
  characters.
- `emit[].type` must be declared in this capability's `event_types`. `v`
  defaults to 1. The core fills in `origin`, `seq` and `ts`.
- `prompt`: a string replaces this capability's prompt segment, `""` clears
  it, and leaving it out keeps it unchanged. Maximum 40 characters, no
  newlines.
- `print` is shown only for `command` triggers.
- Exit code 0 is required. Anything on stderr goes to the capability's log.

### 5.5 Where `say` is shown

- **command** and **login:** rendered straight to the terminal.
- **tick** and **received** (run by the daemon, which has no terminal):
  `say` is dropped, and the loader logs a warning. These triggers
  communicate only through `prompt` and `emit`.

### 5.6 Timeouts

- 10 s for `command`; 0.8 s for `login`; 2 s for `tick` and `received`.
- The whole `orbit greet` (login) is capped at 1 s in the shell snippet (see
  §9). If a single capability takes too long, it's skipped and the others
  still run.

## 6. Events and store

### 6.1 Event

```json
{"origin": "charon", "seq": 42, "type": "notes.sent",
 "ts": "2026-10-03T14:02:11Z", "v": 1, "data": {"text": "lunch at 1?"}}
```

- The pair `(origin, seq)` is the primary key. `seq` is a local counter per
  origin, starting at 1 and always going up.
- Ordering uses `seq` within an origin. `ts` is for display only; clocks are
  not trusted.
- `data` is a JSON object of at most 16 KB.

### 6.2 Tables

- `events(origin, seq, type, ts, v, data, PRIMARY KEY(origin, seq))`
- `latest(origin, type, seq, ts, v, data, PRIMARY KEY(origin, type))`
- `meta(key, value)`: holds `next_seq`, `peer_cursor` (the highest peer `seq`
  stored) and `core_version`.

`keep: latest` events take a seq like any other event but are written only to
`latest` (an upsert, kept only if the incoming seq is higher). That way the
sync cursor covers both tables.

Inserts use `INSERT OR IGNORE`, so storing the same event twice changes
nothing. The CLI writes to the DB directly; the daemon and the CLI share it
safely in WAL mode.

## 7. Sync

### 7.1 HTTP API (orbitd, bound to this machine's tailnet IP, port 1978)

| Method/Path | Purpose |
|---|---|
| `GET /events?after=<seq>&limit=500` | This machine's own events (both tables) with `seq > after`, in ascending order. Response: `{"events": [...], "has_more": bool, "core_version": str, "capabilities": [names]}` |
| `POST /poke` | "I have new events." Triggers a pull from the caller now. Returns 204. |
| `GET /health` | `{"ok": true, "me": str, "core_version": str}` |

Every request: the daemon runs `tailscale whois --json <remote_ip>` (results
cached for 5 minutes) and rejects with 403 unless the hostname equals
`peer_host`. In dev/test mode, a static allowlist replaces this check.

### 7.2 Pull loop

- Pulls `GET /events?after=<peer_cursor>` from the peer when:
  - the daemon starts,
  - a poke arrives,
  - 30 s pass with no pull, or
  - a backoff wait ends after a failed pull.
- Follows `has_more` until all events are fetched.
- Checks each incoming event: `origin == peer`, the type has a capability
  prefix, the shape is valid, and `data` is within the size limit. Invalid
  events are logged and skipped, and the cursor still moves past them.
- Stores valid events, then runs a `received` trigger for every capability
  whose `receives` matches, in batches per capability.
- Peer status:
  - success → `peer.online = true`, `last_seen = now`
  - failure → `online = false`, exponential backoff 5 s → 5 min
- Writes `peer` status to `meta` so the CLI can read it.

### 7.3 Poke

After the CLI writes events, it sends `POST /poke` to the **peer's** daemon
(timeout 1 s, errors ignored). If a poke is lost, the 30 s pull catches it.

In dev/test mode, the full API binds to loopback instead of the tailnet IP, and
the whois check is replaced by a static allowlist.

## 8. Characters

- Art lives in plain text files: `orbit/art/<who>/<mood>.txt`. Each is 6 lines
  or fewer and 16 columns or narrower. Every mood listed in §5.4 exists for
  both characters.
- `characters.render(who, mood, text)` returns the art next to a word-wrapped
  speech bubble, 60 columns wide in total.
- If several `say` entries come from the same trigger, they're shown in
  order. If both characters speak, they're shown facing each other: Pluto's
  art on the left, Charon's on the right.
- No color in v1 except one optional ANSI accent per character, turned off
  when `NO_COLOR` is set or the output isn't a terminal.

## 9. Surfaces (shell integration)

`install.sh` adds a marked block to `~/.bashrc`:

```bash
# >>> orbit >>>
[[ $- == *i* ]] && timeout 1 orbit greet 2>/dev/null
__orbit_prompt() { ORBIT_PS=$( [[ -r ~/.orbit/prompt ]] && echo "$(<~/.orbit/prompt)" ); }
PROMPT_COMMAND="__orbit_prompt${PROMPT_COMMAND:+;$PROMPT_COMMAND}"
PS1='${ORBIT_PS:+$ORBIT_PS }'"$PS1"
# <<< orbit <<<
```

- `orbit greet` runs the `login` trigger for every capability that lists it,
  in parallel, and renders their `say` output.
- Each capability's prompt segment is stored in `meta` as `prompt:<name>`.
  Whichever process ran the capability (the CLI or the daemon) updates the
  segment and rebuilds `~/.orbit/prompt`: the non-empty segments joined by
  `" · "` in `prompt_order`, written atomically (write to a temp file, then
  rename).
- Pluto's shell may not be bash. The reveal-day checklist checks this, and v1
  supports bash only.

## 10. v1 capabilities

### 10.1 companions
- **Triggers:** `login`. **Command:** `hi`.
- At login: a greeting from the user's own character that depends on the time
  of day. If the peer is offline, a line like "Pluto's asleep, I'll keep
  watch."
- `orbit hi`: a random line from a small, editable list in
  `capabilities/companions/lines.json`.
- Emits nothing.

### 10.2 notes
- **Commands:** `note <text>` (emits `notes.sent {text}`), `notes` (prints the
  last 20 notes from both people).
- **login:**
  - The partner's character says each unread peer `notes.sent`, then the
    capability emits one `notes.seen {seqs}`.
  - The user's own character reports read receipts not yet shown ("Pluto read
    your note ♥"), then the capability emits `notes.receipts_shown {seqs}`.
- **received** and **login:** set `prompt` to `✉ N` (N = unread notes), or
  `""` when N is 0. Login clears it after showing the notes.
- "Unread" and "unshown" are worked out entirely from `input.events`. There's
  no local state.

### 10.3 presence
- **Triggers:** `tick` (60 s), `received`. **Command:** `away [message]` /
  `back`.
- **tick:**
  - Works out its own state from how long the user's terminal sessions have
    been idle (`who -u`): `active` < 5 min, `idle` < 60 min, otherwise
    `away`. A manual `away` overrides this until `back`.
  - Emits `presence.status {state, message?}` (keep: latest) only when the
    state changes.
- **prompt:**
  - `♇ pluto: active` on charon, or `☾ charon: idle` on pluto. The symbol
    shows the partner.
  - `💤` when `peer.online` is false.

### 10.4 example
- **Command:** `hello [name]`. Prints and says a greeting. Every line is
  commented to explain the contract. It includes one test case. It's the
  template the `new-capability` skill copies.

## 11. Install and service

- `install.sh`:
  - checks for `python3` ≥ 3.11 and `tailscale`
  - creates `~/.orbit/` and asks for `me`/`peer` to write `config.json`
  - symlinks `bin/orbit` into `~/.local/bin`
  - installs and enables `systemd/orbitd.service` as a user unit
    (`Restart=on-failure`)
  - adds the bashrc block (safe to run again)
- The daemon needs to run even when nobody is logged in, which takes
  `loginctl enable-linger`. The installer prints this command rather than
  running it.

## 12. Agent-friendliness requirements

1. **`CLAUDE.md`** under 150 lines. It covers:
   - what Orbit is
   - a module map, one line each
   - the invariants: stdlib only; no Python on the prompt path; capabilities
     never touch the DB; events are never edited
   - how to verify: `python3 -m unittest`, `orbit dev test <cap>`,
     `orbit doctor`
   - a pointer to the contract doc and the skill
2. **`.claude/skills/new-capability/SKILL.md`** (mainly for Gabby's Claude
   sessions) walks through:
   1. copy `capabilities/example`
   2. write the test cases first
   3. fill in the manifest
   4. implement
   5. run `orbit dev test <name>`
   6. run `orbit dev run <name> <trigger>` against a dev peer
   7. update the capability README
   8. remind the user to install the capability on both machines
3. **A single source of truth** for the contract: `docs/capability-contract.md`
   (JSON shapes plus one full worked example). `contract.py` and the doc are
   kept in sync. A test checks that every example in the doc passes validation.
4. **Actionable errors:** every validation error names the file, the JSON path
   and the fix. Example:
   `capabilities/notes/manifest.json: event_types."sent": must start with "notes." — rename to "notes.sent"`.
5. **Dev tools:**
   - `orbit dev run <cap> <trigger> [args]` runs one capability with a
     synthesized input and pretty-prints the output plus any validation
     errors.
   - `orbit dev test [cap]` runs the capabilities' test cases.
   - `orbit dev peer` starts a fake peer daemon with its own temp data dir and
     port 1979, on loopback, with the test allowlist.
   - `orbit doctor` checks the config, the daemon, the peer, whois, every
     manifest, and differences in capabilities and core version between the
     two machines.
6. **Code style:**
   - type hints throughout and `dataclasses` for shapes
   - docstrings explain *why*
   - no metaprogramming or plugin magic beyond reading folders
   - files stay under ~300 lines

## 13. Error handling

| Failure | Behavior |
|---|---|
| A capability exits non-zero, times out, or prints invalid JSON or output that breaks the contract | Skipped; logged to `logs/<cap>.log` with an actionable message. After 5 failures in a row it's disabled (stored in `meta`) until `orbit doctor --reset <cap>` or a change to the capability's files (detected by mtime). |
| A command fails | The error is printed to stderr; exit code 1. |
| `orbit greet` is slow or broken | Killed at 1 s by `timeout`; prints nothing. |
| The prompt file is missing or unreadable | The segment is empty. |
| The daemon is down | The CLI still writes to the DB, and the pokes fail silently. systemd restarts the daemon, which pulls at startup. |
| The peer is unreachable | Backoff; `peer.online = false`. |
| An invalid peer event | Logged and skipped; the cursor moves past it. |
| An event type with no local capability | Stored anyway, with no trigger. It's handled once the capability is installed (its next input includes it). |
| The DB is locked | `busy_timeout` of 2 s, then the command fails with a clear message. |
| The two machines run different core versions | `orbit doctor` warns. Sync tolerates unknown fields. |

## 14. Testing

Uses only `unittest` from the standard library. `python3 -m unittest` runs
everything in under 30 s.

- **store:** idempotent inserts; `seq` only goes up; `latest` upserts keep the
  highest seq; the cursor covers both tables.
- **contract:** one passing fixture and one fixture for each rule a manifest
  or output can break; the examples in the contract doc pass validation.
- **loader:** timeout, non-zero exit, invalid JSON, auto-disable and
  re-enable on mtime change, duplicate command names.
- **characters:** saved reference output for every `who`×`mood`, plus
  wrapping of long text.
- **sync (integration):** two daemons on loopback (ports 19780/19781, temp data
  dirs, allowlist auth):
  - a note round trip: sent → received → `✉ 1` prompt → greet shows it →
    `notes.seen` → receipt shown on the sender's side
  - the peer is offline while 3 notes are sent, comes back, and catches up
  - a corrupted peer event is skipped and the cursor moves past it
  - the `whois` check rejects an unknown host (a stub)
- **capabilities:** each one's `tests/*.json` cases run through
  `orbit dev test`.
- **prompt path:** a test checks that the bashrc snippet runs no Python (it
  reads the file only).

## 15. Reveal day (`docs/reveal-day.md`)

1. Confirm pluto has Python 3.11 or newer, and check which shell it uses.
2. Confirm the tailnet access rules allow charon ↔ pluto on port 1978. Ask Gabby
   to adjust them if needed.
3. Copy the repo over (or clone it once it's on GitHub as `beschofield/orbit`)
   and run `install.sh` with `me=pluto`, `peer=charon`.
4. `loginctl enable-linger`; run `orbit doctor` on both machines.
5. Send the first note.
6. Optional, later: a `go/orbit` link once the web surface exists.

## 16. Future work (not v1)

- The go link web page: characters orbiting, recent notes, sending from a
  phone. It would be another place the characters show up, reading the store.
- Rituals: countdowns, a shared list, a "gratitude jar".
- Memory search: `orbit ask` over shared notes and data.
- A Home Assistant capability (for example, a lamp glows when a note arrives).
- zsh support; syncing capability code between machines.

## 17. Repository and publishing

- A local git repo at `~/Claude/orbit`, with commits authored as `beschofield`.
- **Nothing is pushed before the reveal.** Afterwards it gets published as
  `github.com/beschofield/orbit` (private recommended).
