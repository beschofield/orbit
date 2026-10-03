# notes

Leave little notes for each other. They pop up at the next login.

- **Commands:**
  - `orbit note <text>` sends a note (up to 280 characters).
  - `orbit notes` shows the last 20 notes from both of you.
- **At login:** unread notes are said by the sender's character (up to 5, then a
  summary) and marked seen. You also get a read receipt ("Pluto read your note ♥")
  once your notes have been seen.
- **Prompt:** `✉ N` while you have N unread notes.
- **Event types:** all `keep: log`.
  - `notes.sent` `{text}`
  - `notes.seen` `{seqs}`: the peer's `notes.sent` seqs I've seen
  - `notes.receipts_shown` `{seqs}`: my notes whose receipt I've been shown
- **State:** none of its own. Unread and receipts are worked out from the events
  on every run.
