# Reveal day checklist

Do these steps together with Gabby, after showing her the surprise.

1. **On pluto, check the basics.** Run `python3 --version` (it must be 3.11 or newer)
   and `echo $SHELL` (Orbit v1 supports bash; if she uses zsh, the greeting and prompt
   need a zsh version first).
2. **Check that the tailnet allows it.** From charon, run
   `curl -s http://pluto:1978/health` once orbitd is running on pluto. If it hangs,
   Gabby may need to allow port 1978 between charon and pluto in the tailnet access
   rules (ACLs).
3. **Put the code on pluto.** Either copy the folder (`scp -r ~/Claude/orbit pluto:~/orbit`),
   or push it to GitHub first as `beschofield/orbit` (private) and clone it there.
4. **Install on pluto:** run `~/orbit/install.sh` and answer `pluto`, then run
   `loginctl enable-linger $USER`.
5. **Switch charon from dev mode to the real thing:** `unset ORBIT_DIR` (dev testing
   used `ORBIT_DIR=~/.orbit-dev`, which keeps test data out of the real `~/.orbit`), then
   `orbit init --force --me charon --peer pluto` and `systemctl --user restart orbitd`.
6. **Check both machines.** `orbit doctor` should be all ✓ on each.
7. **Send the first note** from charon, e.g. `orbit note "welcome to orbit ♥"`, and
   have Gabby open a new terminal.
8. **Later:** add a `go/orbit` link once there's a web page to point it at.
