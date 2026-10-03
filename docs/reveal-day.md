# Reveal day checklist

Do these steps together with Gabby, after showing her the surprise. Use a fresh
terminal on each machine, so no `ORBIT_DIR` from testing is still set (`unset ORBIT_DIR`
if you're not sure).

1. **On charon, install for real.** If you tested in dev mode, you did it with
   `ORBIT_DIR=~/.orbit-dev`, so the real `~/.orbit` is clean and has none of the test
   notes or fake-pluto events. Run `loginctl enable-linger $USER` (before or after the
   install; it keeps orbitd running while you're logged out), then
   `~/Claude/orbit/install.sh` and answer `charon`.
2. **On pluto, check the basics and install.**
   - `python3 --version` must say 3.11 or newer.
   - `echo $SHELL` should be bash. (Orbit v1 supports bash; if she uses zsh, the
     greeting and prompt need a zsh version first.)
   - Copy the code over: `scp -r ~/Claude/orbit pluto:~/orbit` from charon (or push it
     to GitHub first as `beschofield/orbit`, private, and clone it there).
   - Run `loginctl enable-linger $USER`, then `~/orbit/install.sh` and answer `pluto`.
3. **Check that the tailnet lets them talk.** From charon run
   `curl -s http://pluto:1978/health`, and from pluto run
   `curl -s http://charon:1978/health`. Each should print a line of JSON with `"ok": true`.
   If one hangs, the tailnet access rules (ACLs) probably need to allow port 1978
   between charon and pluto.
4. **Run `orbit doctor` on both machines.** Everything should be ✓. Each ✗ line says
   what to fix.
5. **Log out and back in** (or open a new login shell) on both machines, so
   `~/.local/bin` is on PATH and the new `~/.bashrc` block is loaded.
6. **Send the first note** from charon, e.g. `orbit note "welcome to orbit ♥"`, and
   have Gabby open a new terminal.

Later: add a `go/orbit` link once there's a web page to point it at.
