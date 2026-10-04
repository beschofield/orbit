# notes

Leave little notes for each other. They pop up at the next login.

- **Commands:**
  - `orbit note <text>` sends a note (up to 280 characters).
  - `orbit notes` shows the last 20 notes from both of you, numbered (1 is the oldest
    note this machine still has). Each of your own notes ends with `✓ read` once the
    other person has seen it, or `· not read yet` until then.
  - `orbit read` shows the newest note from the other person again, in their
    character's bubble, the same as at login. `orbit read <n>` shows note #n from
    `orbit notes` (yours or theirs). Reading an unread note marks it seen.
  - `orbit unread` shows every unread note from the other person, oldest first, each
    in their character's bubble as at login (no limit of 5), and marks them all seen.
- **At login:**
  1. Read receipts for your notes that were seen since last time, quoting the note
     ('Pluto read your note "lunch at 1?" ♥', or "Pluto read your 2 notes ♥").
  2. Unread notes, said by the sender's character and then marked seen. Up to 5 are
     said; any more get a summary ("…and 2 more. Read them with: orbit unread") and
     stay unread, so the prompt keeps counting them. Each starts with who it's from and when ("✉ Note from Pluto · 6:42 pm",
     or "Oct 2, 9:30 pm" if it's older than today).
- **Prompt:** `✉  N` while you have N unread notes.
- **Event types:** all `keep: log`.
  - `notes.sent` `{text}`
  - `notes.seen` `{seqs}`: the peer's `notes.sent` seqs I've seen
  - `notes.receipts_shown` `{seqs}`: my notes whose receipt I've been shown
- **State:** none of its own. Unread and receipts are worked out from the events
  on every run.
