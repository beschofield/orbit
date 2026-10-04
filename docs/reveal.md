# Welcome to Orbit, Gabby ♇ ☾

Surprise! Becca built this for the two of you. Your machine, **pluto**, and hers,
**charon**, each get a little terminal companion: Pluto for you, Charon for her. The two
keep each other company over the tailnet. They greet you when you open a terminal, pass
notes between you, and show in your prompt whether the other one is around.

Becca's side is already set up, and **charon is already holding a note for you.**
It shows up the first time your new terminal opens.

Do these steps on pluto, with Becca nearby for the testing part.

## What you need

- pluto and charon both online and on the tailnet
- Python 3.11 or newer
- bash as your shell (Orbit doesn't support zsh yet)

Check the last two:
```bash
python3 --version   # 3.11 or newer
echo $SHELL         # should end in /bash
```

## 1. Get the code

```bash
git clone git@github.com:beschofield/orbit.git ~/orbit
```
(Use the HTTPS URL instead if you don't use SSH keys with GitHub. Any folder works, but
the rest of this guide assumes `~/orbit`.)

## 2. Install

```bash
loginctl enable-linger $USER   # keeps orbitd running while you're logged out
~/orbit/install.sh             # when it asks which machine this is, answer: pluto
```

The installer:
- writes `~/.orbit/config.json` for pluto
- links `orbit` into `~/.local/bin`
- starts the `orbitd` background service with systemd
- adds a small block to `~/.bashrc`, between `# >>> orbit >>>` and `# <<< orbit <<<`

It's safe to run again. Each run replaces what the last one did.

## 3. Let pluto and charon talk

They talk on **port 1978** (the year Charon was discovered). Check both directions.

From pluto:
```bash
curl -s http://charon:1978/health
```
Then ask Becca to run this on charon:
```bash
curl -s http://pluto:1978/health
```

Each should print a line of JSON with `"ok": true`. If one hangs, your tailnet access
rules (ACLs) are blocking it. Allow TCP port 1978 between charon and pluto in both
directions, then try again. A tailnet that still uses the default allow-everything
policy needs no change.

Only these two machines can use the sync API. Each request is checked with
`tailscale whois`, so other devices on your tailnet get turned away.

## 4. Check everything

```bash
orbit doctor
```

Every line should start with ✓, and each ✗ line says what to fix. If it says
`orbit: command not found`, open a new login shell first (see step 5) or run
`~/.local/bin/orbit doctor`.

## 5. Open a new terminal

Log out and back in, or open a fresh login shell, so `~/.local/bin` is on your PATH
and the new `~/.bashrc` block loads. Pluto should greet you, then hand over Becca's note
in Charon's bubble, something like:

```
✉ Note from Charon · 8:12 am
welcome to orbit ♥
```

Your prompt now starts with Becca's status, for example `☾ charon: active`.

## 6. Test it together

Do these with Becca at charon:

1. **Reply to her:** `orbit note "it works!! ♥"`. Pluto confirms it's sent.
2. **Becca checks charon.** Within a few seconds her prompt shows `✉ 1`. When she
   opens a new terminal, Charon's greeting shows your note.
3. **Get your read receipt:** open another new terminal on pluto. Pluto tells you
   `Charon read your note "it works!! ♥" ♥`.
4. **Try presence:** run `orbit away "making tea"`. At Becca's next prompt, it starts
   with `♇ pluto: away (making tea)`. Run `orbit back` to clear it. Ask her to do the
   same, and watch your prompt change.
5. **Look around:** `orbit notes` shows recent notes from both of you, `orbit hi` says
   hi, and `orbit help` lists everything.

## If something's off

| What you see | What to do |
|---|---|
| No greeting in a new terminal | Run `orbit greet` by hand. If that works, open a real *login* shell, since some terminals start non-login shells. |
| `orbit: command not found` | Log out and back in, or use `~/.local/bin/orbit`. |
| Your prompt shows `☾ charon: 💤` | charon can't be reached. Check it's on, re-run the `curl` from step 3, and run `systemctl --user status orbitd` on both machines. |
| A note didn't arrive | Wait about 30 s, since sync retries on its own. Then run `orbit doctor` on both machines. |
| Anything else | Read `~/.orbit/logs/orbitd.log`, or the log named after the capability in `~/.orbit/logs/`. |

## What's next

- **The go/orbit page** has how-tos and ideas. Becca has shared it with you.
- **Make it yours.** Open Claude Code in `~/orbit` and say
  *"Read CLAUDE.md, then use the new-capability skill to add …"*. `TODO.md` has a list
  of ideas and things to build next.
- **Getting each other's changes:** run `git pull` in `~/orbit`. New capabilities show
  up within about 30 seconds. If the core (`orbit/`) changed, also run
  `systemctl --user restart orbitd`. `orbit doctor` tells you if your machine and
  Becca's are out of sync.
