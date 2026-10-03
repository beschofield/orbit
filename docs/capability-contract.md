# Capability contract (v1)

This is the single source of truth for how a capability talks to the Orbit core.
`orbit/contract.py` enforces it, and `tests/test_contract_doc.py` checks every example
below against that code. If you change one, change the other.

## The idea

A capability is a folder in `capabilities/` holding a program. The core runs the program
when something happens (a command, a login, a timer, or events arriving from the other
machine). It writes **one JSON object to stdin** and reads **one JSON object from stdout**.

A capability never touches the database, the network or `~/.orbit`. Everything it needs
is in the input, and everything it wants to change goes in the output. Capabilities are
stateless: their memory is the event log, which syncs between charon and pluto.

## Folder

```
capabilities/<name>/
├── manifest.json     # what it is and when it runs
├── main.py           # the program named by "run" (executable, with a shebang)
├── README.md         # what it does, its commands and event types
└── tests/<case>.json # test cases (see "Tests")
```

`<name>`: 2–31 lowercase letters, digits or `_`, starting with a letter. It must equal
the manifest's `name`.

## manifest.json

```json manifest
{
  "name": "notes",
  "description": "Leave little notes for each other; they pop up at the next login.",
  "contract": 1,
  "run": "main.py",
  "commands": [
    {"name": "note", "usage": "note <text>", "help": "Send a note to your girlfriend."},
    {"name": "notes", "usage": "notes", "help": "Show the last 20 notes."}
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

| Key | Rules |
|---|---|
| `name` | Same as the folder name. |
| `description` | One line. `orbit doctor` and `orbit help` show it. |
| `contract` | Always `1`. |
| `run` | A file name inside the folder. It must be executable (`chmod +x`) and start with a shebang such as `#!/usr/bin/env python3`. |
| `commands` | The `orbit <name> ...` commands this capability answers. Each has a `name` (lowercase letters, digits and `-`), a `usage` and a `help`. Names must be unique across all capabilities; if two clash, neither gets the command until one is renamed. Reserved by the core: `daemon`, `dev`, `doctor`, `greet`, `help`, `init`. |
| `triggers` | Any of `login`, `tick`, `received`. Commands are implied by `commands`, so don't list `command`. |
| `tick_seconds` | Required (a whole number ≥ 10) when `triggers` includes `tick`; otherwise `null`. |
| `event_types` | Every event type this capability may emit. Each must start with `<name>.` and maps to `{"keep": "log"}` (the full history is kept) or `{"keep": "latest"}` (only the newest per machine is kept). |
| `receives` | Event types, from any capability, that fire the `received` trigger when they arrive from the other machine. Required exactly when `triggers` includes `received`. |

## Triggers

| Trigger | When | Run by | Timeout | Is `say` shown? |
|---|---|---|---|---|
| `command` | `orbit <command> args...` | the CLI | 10 s | yes |
| `login` | a new interactive shell (`orbit greet`) | the CLI | 0.8 s | yes |
| `tick` | every `tick_seconds` | orbitd | 2 s | no; it's ignored and logged |
| `received` | the other machine's events of a `receives` type arrive | orbitd | 2 s | no; it's ignored and logged |

`tick` and `received` run in the background with no terminal, so they can only use
`prompt` and `emit`.

## Input (stdin)

```json input
{
  "contract": 1,
  "trigger": {"kind": "command", "name": "note", "args": ["lunch at 1?"]},
  "me": {"name": "charon"},
  "peer": {"name": "pluto", "online": true, "last_seen": "2026-10-03T14:01:50Z"},
  "now": "2026-10-03T14:02:11Z",
  "events": [
    {"origin": "pluto", "seq": 41, "type": "notes.sent", "ts": "2026-10-03T13:00:00Z", "v": 1, "data": {"text": "good luck today!"}}
  ],
  "latest": {
    "charon": {},
    "pluto": {"presence.status": {"origin": "pluto", "seq": 40, "type": "presence.status", "ts": "2026-10-03T13:59:00Z", "v": 1, "data": {"state": "active", "manual": false}}}
  }
}
```

- `trigger` is one of:
  - `{"kind": "command", "name": "note", "args": [...]}`: `args` are the shell words after the command name.
  - `{"kind": "login"}`
  - `{"kind": "tick"}`
  - `{"kind": "received", "events": [...]}`: the events that just arrived.
- `me.name` and `peer.name` are `"charon"` or `"pluto"`. `peer.online` says whether
  the last sync with the other machine worked, and `peer.last_seen` is when it last
  did (or `null`).
- `now` is the current UTC time in ISO 8601 with a `Z`.
- `events` holds up to 200 of the most recent events **of this capability's own
  `event_types`**, from both machines, oldest first **by arrival on this machine**.
  Never sort by `ts`, because the two machines' clocks can disagree.
- `latest` holds every `keep: latest` event from every capability, as
  `latest[<machine>][<type>]`. Both machine keys are always present.

An event:

| Field | Meaning |
|---|---|
| `origin` | the machine that created it |
| `seq` | that machine's counter; `(origin, seq)` is unique |
| `type` | `<capability>.<name>` |
| `ts` | creation time on the origin machine (for display only) |
| `v` | version of the `data` shape, starting at 1 |
| `data` | a JSON object of at most 16 KB |

## Output (stdout)

```json output
{
  "say": [{"who": "pluto", "mood": "love", "text": "lunch at 1?"}],
  "emit": [{"type": "notes.seen", "data": {"seqs": [41, 42]}, "v": 1}],
  "prompt": ""
}
```

Every key is optional. Print `{}` (or nothing at all) to do nothing.

| Key | Rules |
|---|---|
| `say` | A list of `{"who", "mood", "text"}`. `who` is `"pluto"` or `"charon"`. `mood` is one of `neutral`, `happy`, `sleepy`, `love`, `thinking`, `worried`. `text` is 1–280 characters, and newlines are fine. |
| `emit` | A list of `{"type", "data", "v"}`. `type` must be in your `event_types`. `data` is an object of at most 16 KB. `v` defaults to 1. The core adds `origin`, `seq` and `ts`, stores the event and syncs it. |
| `prompt` | Your segment of the shell prompt: at most 40 printable characters, with no newlines or control codes. `""` clears it; leaving the key out keeps the current one. |
| `print` | Plain text shown to the person; only used for command triggers. Good for messages like "usage: ...". |

The exit code must be 0, and stdout must be exactly one JSON object. **Send debug
output to stderr**, which goes to `~/.orbit/logs/<name>.log`.

## Failures

If the program exits non-zero, times out, or prints output that breaks these rules, the
core skips it, logs the reason and the fix to `~/.orbit/logs/<name>.log`, and moves on.
After 5 failures in a row the capability is disabled until a file in its folder changes
or someone runs `orbit doctor --reset <name>`.

## Tests

Each file in `tests/` is one case:

```json case
{
  "description": "orbit note sends a note and Charon confirms",
  "input": {"trigger": {"kind": "command", "name": "note", "args": ["lunch", "at", "1?"]}},
  "expect": {
    "emit": [{"type": "notes.sent", "data": {"text": "lunch at 1?"}, "v": 1}],
    "say": [{"who": "charon", "mood": "happy", "text": "Sent! I'll make sure Pluto gets it."}]
  }
}
```

- `input` is merged over defaults, so a case only needs `trigger` plus whatever it's
  testing. The defaults are:
  - `contract`: 1
  - `me`: charon
  - `peer`: pluto, online, with `last_seen` null
  - `now`: `2026-10-03T14:00:00Z`
  - `events`: `[]`
  - `latest`: both machines empty
- `expect` lists the output keys to check, and each is compared exactly. Keys you leave
  out aren't checked. In the comparison, `emit[].v` is always filled in, and an absent
  `prompt` or `print` is `null`.
- Cases run with `TZ=UTC`.
- Run them with `orbit dev test <name>`. They also run as part of `python3 -m unittest`.

## Checking your work

- `orbit dev test <name>` runs the cases.
- `orbit dev run <name> <trigger> [command] [args...]` runs the capability once against
  this machine's real data. It prints the input, the output, any problems and the
  rendered bubbles, and **writes nothing**.
- `orbit doctor` checks the config, the daemon, the peer and every manifest.
