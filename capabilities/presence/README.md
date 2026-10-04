# presence

Shows your girlfriend's state in your shell prompt as an emoji: `♇ pluto: ✨` on charon,
or `☾ charon: 💭` on pluto. ✨ is active, 💭 idle, ⏳ away (with any away message in
parentheses), and 💤 means the other machine can't be reached. Unknown states show as words.

- **Commands:**
  - `orbit away [message]` marks you away, with an optional message of up to 30
    characters. It sticks until you run `orbit back`.
  - `orbit back` returns you to automatic presence.
  - `orbit status toggle` hides your girlfriend's status from your prompt, or shows it
    again if it's hidden. `orbit status on` and `orbit status off` set it either
    way. It only changes your own prompt: she still sees yours.
  - `orbit status style both|symbol|name` picks how she's labelled: `♇ pluto: ✨`
    (both, the default), `♇ ✨` (symbol) or `pluto: ✨` (name).
- **Every 60 s (tick):** works out your state from terminal idle time (how long since
  any of your terminals, including tmux panes, was last used):
  active (under 5 minutes), idle (under 60 minutes), otherwise away. It emits a new
  status only when the state changes.
- **Event types:** `presence.status` `{state, manual, message?}`, `keep: latest`;
  `presence.display` `{shown, style}`, `keep: latest` (this machine's prompt settings;
  no event means shown, style both). Events store the state as a word; the emoji
  are only for the prompt.
