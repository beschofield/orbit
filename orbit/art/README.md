# Character art

Each character has two looks, with one plain-text file per mood in each:

```
pluto/forward/   neutral.txt  happy.txt  sleepy.txt  love.txt  thinking.txt  worried.txt
pluto/side/      neutral.txt  happy.txt  sleepy.txt  love.txt  thinking.txt  worried.txt
charon/forward/  neutral.txt  happy.txt  sleepy.txt  love.txt  thinking.txt  worried.txt
charon/side/     neutral.txt  happy.txt  sleepy.txt  love.txt  thinking.txt  worried.txt
```

- `forward/` looks at the person at the terminal. Most bubbles use it.
- `side/` looks toward the other planet: Pluto (on the left) looks right, Charon (on the
  right) looks left, and each carries a tiny version of the other in that corner. Bubbles
  that pass a note between the two use it.

A capability picks the look per bubble with `"look": "side"` (see
`docs/capability-contract.md`). Edit these files. No code changes are needed.

## Rules (a test checks them)

- At most **6 lines** and **16 columns** per file. The name label goes under the art automatically.
- All six moods must exist in both looks for both characters.
- Art files go in a look folder. A file directly in `pluto/` or `charon/` is never shown.
- Missing art falls back in this order: `<look>/<mood>`, `<look>/neutral`, `forward/<mood>`, `forward/neutral`.
- Wide characters such as emoji count as 2 columns. `♥` counts as 1.

## Preview

From the repo root:

```bash
python3 -c "from orbit import characters; print(characters.render('pluto','happy','testing my new art!'))"
python3 -c "from orbit import characters; print(characters.render('pluto','happy','testing my new art!', look='side'))"
```

## When you like it

Refresh the reference renders the tests compare against, then commit:

```bash
ORBIT_UPDATE_GOLDEN=1 python3 -m unittest tests.test_characters
python3 -m unittest tests.test_characters
git add orbit/art tests/golden && git commit -m "New character art"
```
