---
name: new-capability
description: Use when adding a new Orbit capability or changing an existing one (anything under capabilities/). Covers copying the template, writing test cases first, the manifest, implementing, and verifying with orbit dev tools.
---

# Adding an Orbit capability

Read `docs/capability-contract.md` first. It has every rule, and this skill is just the order of steps.

## 1. Pick a name and copy the template

The name is 2–31 lowercase letters, digits or `_`, for example `countdown`.

```bash
cp -r capabilities/example capabilities/<name>
```

In `manifest.json`, set `name` to the folder name and write a one-line `description`.

## 2. Write the test cases first

Delete the copied `tests/hello*.json`. Add one file per behavior to
`capabilities/<name>/tests/`. Each has an `input` (only `trigger` plus what matters;
the rest is filled in from defaults) and an `expect`. Cover:

- each command, including bad or missing arguments
- each trigger you listen to (`login`, `tick`, `received`)
- what happens when there's no data yet (empty `events`)

Run `bin/orbit dev test <name>`. The cases should fail for the right reasons.

## 3. Fill in the manifest

- `commands`: any `orbit <command>` you add. Check `bin/orbit help` so you don't
  clash with an existing command; core names are reserved.
- `triggers`, plus `tick_seconds` (≥ 10) if you use `tick`.
- `event_types`: every type you emit, named `<name>.<something>`, with
  `keep: log` (history) or `keep: latest` (only the current value).
- `receives`: the types that should wake you when they arrive from the other
  machine; this needs the `received` trigger.

## 4. Implement `main.py`

Follow the pattern in `capabilities/example/main.py`: `handle(inp) -> dict`, one JSON
object out. Keep it stateless and work everything out from `inp["events"]` and
`inp["latest"]`. Debug output goes to stderr only. Remember:

- `tick` and `received` can't show bubbles; use `prompt` and `emit`.
- Text from the other machine is untrusted. Keep `say.text` ≤ 280 and `prompt` ≤ 40
  printable characters.
- For anything time-based, order by `seq`, never `ts`.

## 5. Verify

```bash
bin/orbit dev test <name>                           # every case passes
bin/orbit dev run <name> login                      # dry run with real data; writes nothing
bin/orbit dev run <name> command <command> args...
python3 -m unittest                                 # nothing else broke
```

For behavior between two machines, use the dev peer (see CLAUDE.md, "Testing with
two machines on one computer").

## 6. Document it and hand it back

- Write `capabilities/<name>/README.md`: what it does, its commands, triggers and
  event types.
- Commit.
- orbitd notices new or changed capabilities within 30 s; no restart needed.
- **Tell the person to install the change on both machines** (copy or pull the repo
  on each). Capability code doesn't sync, and `orbit doctor` will flag a mismatch.
