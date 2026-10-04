# Orbit ♇ ☾

Pluto and Charon are tidally locked: they always show each other the same face, and
they circle a point in the space *between* them. These two machines, **pluto**
(Gabby's) and **charon** (Becca's), now do something similar. Each one has a little
terminal companion, and the two keep each other company over the tailnet.

```
   .-~~~~-.       .----------------------.
  /  ♥  ♥  \     <| lunch at 1?          |
 |   \__/   |     '----------------------'
  \   ♥    /
   '-....-'
     Pluto
```

## What it does

- **A greeting** from your character whenever you open a terminal.
- **Notes:** `orbit note "lunch at 1?"` pops up on the other machine at the next
  login. You get a read receipt when it's been seen.
- **Presence:** your prompt shows your girlfriend's state, `♇ pluto: active`, or `💤`
  when her machine is asleep. Use `orbit away gym` and `orbit back` to set it by hand.
- `orbit hi` for a friendly line, and `orbit help` for everything else.

## Install (on each machine)

Setting up pluto for the first time? Follow `docs/reveal.md`, which walks through
installing and testing it together.

```bash
git clone <this repo> ~/orbit   # or copy the folder over
~/orbit/install.sh              # asks which machine this is
loginctl enable-linger $USER    # keeps orbitd running when you're logged out
orbit doctor                    # check that everything works
```

You need Python 3.11+, Tailscale, and both machines on the same tailnet, able to
reach each other on port 1978.

## Making it yours

Orbit is built to grow. Each feature is a small **capability** in `capabilities/`,
and you can add your own, for example countdowns, a shared grocery list, or a lamp
that glows when a note arrives. The easiest way is to ask Claude:

> Read CLAUDE.md, then use the new-capability skill to add a capability that ...

Or do it by hand: copy `capabilities/example/` and follow
`docs/capability-contract.md`.

## When something's off

`orbit doctor` explains what's wrong and how to fix it. The logs are in `~/.orbit/logs/`.
