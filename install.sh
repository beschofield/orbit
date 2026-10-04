#!/usr/bin/env bash
# Installs Orbit for the current user. Safe to run again: each step replaces its previous result.
set -euo pipefail
REPO="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
DATA="${ORBIT_DIR:-$HOME/.orbit}"

python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null || {
  echo "Orbit needs Python 3.11 or newer (found: $(python3 --version 2>&1))" >&2; exit 1; }
command -v tailscale >/dev/null || { echo "Orbit needs Tailscale, but 'tailscale' isn't on PATH" >&2; exit 1; }
# zsh gets its block too when it's in use: the login shell, or a ~/.zshrc already exists.
RCS=(.bashrc)
[[ -f $HOME/.zshrc || ${SHELL:-} == */zsh ]] && RCS+=(.zshrc)
for rc in "${RCS[@]}"; do
  if grep -q '^# >>> orbit >>>$' "$HOME/$rc" 2>/dev/null && ! grep -q '^# <<< orbit <<<$' "$HOME/$rc"; then
    echo "~/$rc has '# >>> orbit >>>' but no '# <<< orbit <<<' line, so Orbit won't guess what to remove." >&2
    echo "Fix ~/$rc by hand (delete the old orbit block, or add the end marker), then run install.sh again." >&2
    exit 1
  fi
done

if [[ ! -f $DATA/config.json ]]; then
  read -rp "Which machine is this? (pluto/charon): " ME
  case $ME in
    pluto) PEER=charon ;;
    charon) PEER=pluto ;;
    *) echo "Please answer pluto or charon" >&2; exit 1 ;;
  esac
  "$REPO/bin/orbit" init --me "$ME" --peer "$PEER"
fi

mkdir -p "$HOME/.local/bin"
ln -sfn "$REPO/bin/orbit" "$HOME/.local/bin/orbit"

mkdir -p "$HOME/.config/systemd/user"
cp "$REPO/systemd/orbitd.service" "$HOME/.config/systemd/user/orbitd.service"
if systemctl --user daemon-reload && systemctl --user enable --now orbitd.service; then
  echo "orbitd is running (systemctl --user status orbitd)"
else
  echo "warning: couldn't start orbitd with systemd; run 'orbit daemon' by hand to see why" >&2
fi

for rc in "${RCS[@]}"; do
  touch "$HOME/$rc"
  if grep -q '^# >>> orbit >>>$' "$HOME/$rc"; then
    # --follow-symlinks: edit a dotfiles-managed rc file in place instead of replacing the link
    sed -i --follow-symlinks '/^# >>> orbit >>>$/,/^# <<< orbit <<<$/d' "$HOME/$rc"
  fi
  cat "$REPO/shell/orbit${rc%rc}" >> "$HOME/$rc"  # .bashrc gets orbit.bash, .zshrc gets orbit.zsh
done

case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) echo "note: ~/.local/bin isn't on your PATH yet; open a new login shell or add it in ~/.profile" ;;
esac
echo "To keep orbitd running while you're logged out, run:  loginctl enable-linger ${USER:-$(id -un)}"
echo "Done! Open a new terminal, then try: orbit help"
