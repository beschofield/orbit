# >>> orbit >>>
# Added by orbit/install.sh; reinstalling replaces everything between these markers.
# The prompt hook only reads ~/.orbit/prompt (no Python runs), so it can't slow the shell down.
if [[ $- == *i* ]]; then
  # Greet only when someone can see it (not in scp, pipes or scripts): showing a note marks it read.
  [[ -t 1 ]] && command -v orbit >/dev/null 2>&1 && timeout 1 orbit greet 2>/dev/null
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
