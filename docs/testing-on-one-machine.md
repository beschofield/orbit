# Testing a change on one machine

How to try a branch (for example `feat/toggle-status`) on charon alone, with a fake
pluto, without touching your real Orbit. Works the same on pluto with the names swapped.

## Why it's set up this way

- **Your real orbitd runs from `~/Claude/orbit`** (`orbit` in your PATH points at
  `~/Claude/orbit/bin/orbit`), and it picks up capability changes within 30 s. So
  don't switch that checkout to the branch. Test from a separate checkout and run
  its own `bin/orbit`, not plain `orbit`.
- **`ORBIT_DIR=~/.orbit-dev`** keeps test notes and statuses out of the real
  `~/.orbit`. The fake peer keeps its data in `~/.orbit-devpeer`.
- The test daemon listens on `127.0.0.1:1978` and the fake peer on `127.0.0.1:1979`.
  Your real orbitd listens on your tailnet address, so they don't clash.

## 1. Check out the branch somewhere else (once)

```bash
cd ~/Claude/orbit
git fetch origin
git worktree add --detach ~/orbit-test origin/feat/toggle-status   # a second checkout of the branch
cd ~/orbit-test
rm -rf ~/.orbit-dev ~/.orbit-devpeer               # start from clean test data
```

`--detach` works even if the branch is already checked out elsewhere. To pick up new
commits later: `git fetch origin && git checkout --detach origin/feat/toggle-status`.

## 2. Start the test daemon and the fake peer

Open three terminals, all in `~/orbit-test`. In **every** one, first run:

```bash
export ORBIT_DIR=~/.orbit-dev
```

| Terminal | Run | What it is |
|---|---|---|
| 1 | `bin/orbit init --dev --me charon --peer pluto` (first time only), then `bin/orbit daemon` | your test daemon |
| 2 | `bin/orbit dev peer` | the fake pluto |
| 3 | the commands below | where you try things |

## 3. Try it (terminal 3)

The presence segment is in `$ORBIT_DIR/prompt`. Your real shell prompt still shows
the real `~/.orbit/prompt`, so look at the file with `cat`:

```bash
cat $ORBIT_DIR/prompt                     # ♇ pluto: ✨  (fake pluto counts as active)

bin/orbit dev peer away "at the gym"      # run a command *as* fake pluto
cat $ORBIT_DIR/prompt                     # ♇ pluto: ⏳ (at the gym)

bin/orbit status style symbol; cat $ORBIT_DIR/prompt   # ♇ ⏳ (at the gym)
bin/orbit status style name;   cat $ORBIT_DIR/prompt   # pluto: ⏳ (at the gym)
bin/orbit status style both;   cat $ORBIT_DIR/prompt   # ♇ pluto: ⏳ (at the gym)

bin/orbit status toggle; cat $ORBIT_DIR/prompt         # (empty: hidden)
bin/orbit status toggle; cat $ORBIT_DIR/prompt         # back again
bin/orbit status                                       # prints usage, changes nothing

bin/orbit dev peer back
cat $ORBIT_DIR/prompt                     # ♇ pluto: ✨
```

Changes usually show up within a second. If not, wait a few seconds and `cat` again.

- **Asleep (💤):** stop the fake peer (Ctrl-C in terminal 2). After about 20 s the
  prompt shows `♇ pluto: 💤`. Start it again to bring it back.
- **Idle (💭):** the fake peer shares your terminals, so it only goes idle when you
  leave every terminal alone for 5+ minutes. The quick check is the test cases:
  `bin/orbit dev test presence`.
- **Seeing it in your real prompt:** the bashrc block reads `~/.orbit/prompt`. To see
  test data in place for one shell, run `PS1="\$(<$ORBIT_DIR/prompt) \$ "` in
  terminal 3.

## 4. Run the automated tests

```bash
bin/orbit dev test presence    # this capability's cases
python3 -m unittest            # everything, in under 30 s
```

## 5. Clean up

```bash
# Ctrl-C terminals 1 and 2, then:
unset ORBIT_DIR
rm -rf ~/.orbit-dev ~/.orbit-devpeer
cd ~/Claude/orbit && git worktree remove ~/orbit-test
```

Nothing in `~/.orbit` was touched. Once the branch is merged, pull it on **both**
machines: capability code doesn't sync, and `orbit doctor` flags a mismatch.
