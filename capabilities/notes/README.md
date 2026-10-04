# notes

Leave little notes for each other. They pop up at the next login.

- **Commands:**
  - `orbit note <text>` sends a note (up to 280 characters).
  - `orbit notes` shows the last 20 notes from both of you.
- **At login:** unread notes are said by the sender's character (up to 5, then a
  summary) and marked seen. Each starts with a header saying who it's from and when
  ("✉ Note from Pluto · 6:42 pm", or "Oct 2, 9:30 pm" if it's older than today). You
  also get a read receipt that quotes your note ('Pluto read your note "lunch at 1?" ♥')
  once it's been seen.
- **Prompt:** `✉ N` while you have N unread notes.
- **Event types:** all `keep: log`.
  - `notes.sent` `{text}`
  - `notes.seen` `{seqs}`: the peer's `notes.sent` seqs I've seen
  - `notes.receipts_shown` `{seqs}`: my notes whose receipt I've been shown
- **State:** none of its own. Unread and receipts are worked out from the events
  on every run.
