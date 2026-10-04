# >>> orbit >>>
# Added by orbit/install.sh; reinstalling replaces everything between these markers.
# The prompt hook only reads ~/.orbit/prompt (no Python runs), so it can't slow the shell down.
if [[ -o interactive ]]; then
  # Greet only when someone can see it (not in scp, pipes or scripts): showing a note marks it read.
  # Prefer the installed link, so a PATH without ~/.local/bin (first login) still greets.
  __orbit_bin="$HOME/.local/bin/orbit"
  [[ -x $__orbit_bin ]] || __orbit_bin=$(command -v orbit 2>/dev/null)
  [[ -t 1 && -n $__orbit_bin ]] && timeout 1 "$__orbit_bin" greet 2>/dev/null
  unset __orbit_bin
  __orbit_prompt() {
    local s=$? f="${ORBIT_DIR:-$HOME/.orbit}/prompt"  # keep $? for prompts that show it
    ORBIT_PS=""
    [[ -r $f ]] && ORBIT_PS=$(<"$f")
    ORBIT_PS=${ORBIT_PS//\%/%%}  # zsh reads % as a prompt escape; "100%" in an away reason must stay text
    # Checked on every prompt, not once: themes like starship set PROMPT in ~/.zshrc, sometimes after this block.
    [[ $PROMPT == *ORBIT_PS* ]] || PROMPT='${ORBIT_PS:+$ORBIT_PS }'"$PROMPT"
    return $s
  }
  setopt prompt_subst
  autoload -Uz add-zsh-hook
  add-zsh-hook precmd __orbit_prompt  # add-zsh-hook skips a hook that's already there
fi
# <<< orbit <<<
