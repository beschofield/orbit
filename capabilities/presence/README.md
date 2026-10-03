# presence

Shows your girlfriend's state in your shell prompt: `♇ pluto: active` on charon,
or `☾ charon: idle` on pluto. When the other machine can't be reached, it shows `💤`.

- **Commands:**
  - `orbit away [message]` marks you away, with an optional message of up to 30
    characters. It sticks until you run `orbit back`.
  - `orbit back` returns you to automatic presence.
- **Every 60 s (tick):** works out your state from terminal idle time (`who -u`):
  active (under 5 minutes), idle (under 60 minutes), otherwise away. It emits a new
  status only when the state changes.
- **Event types:** `presence.status` `{state, manual, message?}`, `keep: latest`.
- **Note:** idle time comes from login sessions (SSH, consoles). Panes inside tmux
  may not count.
