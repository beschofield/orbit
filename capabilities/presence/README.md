# presence

Shows your girlfriend's state in your shell prompt: `♇ pluto: active` on charon,
or `☾ charon: idle` on pluto. When the other machine can't be reached, it shows `💤`.

- **Commands:**
  - `orbit away [message]` marks you away, with an optional message of up to 30
    characters. It sticks until you run `orbit back`.
  - `orbit back` returns you to automatic presence.
  - `orbit status` hides your girlfriend's status from your prompt, or shows it
    again if it's hidden. `orbit status on` and `orbit status off` set it either
    way. It only changes your own prompt: she still sees yours.
- **Every 60 s (tick):** works out your state from terminal idle time (how long since
  any of your terminals, including tmux panes, was last used):
  active (under 5 minutes), idle (under 60 minutes), otherwise away. It emits a new
  status only when the state changes.
- **Event types:** `presence.status` `{state, manual, message?}`, `keep: latest`;
  `presence.display` `{shown}`, `keep: latest` (whether this machine's prompt shows
  the segment; no event means shown).
