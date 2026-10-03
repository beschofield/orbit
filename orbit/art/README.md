# Character art

Each character has one plain-text file per mood:

```
pluto/   neutral.txt  happy.txt  sleepy.txt  love.txt  thinking.txt  worried.txt
charon/  neutral.txt  happy.txt  sleepy.txt  love.txt  thinking.txt  worried.txt
```

Edit those files. No code changes are needed.

## Rules (a test checks them)

- At most **6 lines** and **16 columns** per file. The name label goes under the art automatically.
- All six moods must exist for both characters. A missing mood falls back to `neutral.txt`.
- Wide characters such as emoji count as 2 columns. `♥` counts as 1.

## Preview

From the repo root:

```bash
python3 -c "from orbit import characters; print(characters.render('pluto','happy','testing my new art!'))"
```

## When you like it

Refresh the reference renders the tests compare against, then commit:

```bash
ORBIT_UPDATE_GOLDEN=1 python3 -m unittest tests.test_characters
python3 -m unittest tests.test_characters
git add orbit/art tests/golden && git commit -m "New character art"
```
