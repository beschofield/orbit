# >>> orbit >>>
# Added by orbit/install.sh; reinstalling replaces everything between these markers.
# The prompt hook only reads ~/.orbit/prompt (no Python runs), so it can't slow the shell down.
if [[ $- == *i* ]]; then
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
    return $s
  }
  if [[ ${PROMPT_COMMAND:-} != *__orbit_prompt* ]]; then
    PROMPT_COMMAND="__orbit_prompt${PROMPT_COMMAND:+;$PROMPT_COMMAND}"
  fi
  if [[ ${PS1:-} != *ORBIT_PS* ]]; then
    PS1='${ORBIT_PS:+$ORBIT_PS }'"${PS1:-\$ }"
  fi
fi
# <<< orbit <<<
