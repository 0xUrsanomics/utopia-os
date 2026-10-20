#!/usr/bin/env bash
# install_setup_auth.sh: install a `claude setup-token` credential so shells stop re-prompting for login.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
#
# WHY THIS EXISTS. A recurring "please log in again" every few days, while the refresh credential
# still has weeks of validity left, means a credential is being DROPPED (clobbered by another
# same-account writer), not expiring. `claude setup-token` mints a long-lived credential that has
# no refresh cycle to lose, which sidesteps the failing subsystem instead of patching it.
#
# THE VALUE IS READ FROM STDIN, NEVER FROM argv. Anything passed as an argument shows up in
# `ps auxww` for every user on the box and in shell history. That is why there is no --value flag.
#
# Usage (run in a real terminal, the OAuth step needs a TTY):
#   claude setup-token                       # prints the credential, copy it
#   ./install_setup_auth.sh                  # paste at the silent prompt
#   ./install_setup_auth.sh --status         # show whether one is installed (no secret printed)
#   ./install_setup_auth.sh --uninstall      # remove it and fall back to normal OAuth
#
# SCOPE. The axis is NOT project or directory (a credential is account-wide, every `claude` in every
# folder is the same account). The axis is whether the process's shell sources ~/.bashrc:
#   COVERED     interactive shells you open yourself.
#   COVERED     anything spawned `bash -lc` (login shell -> ~/.profile -> ~/.bashrc on most distros).
#   NOT COVERED systemd units and cron. They keep using .credentials.json unless their launcher
#               sources scripts/lib/lib_claude_setup_auth.sh (or uses lib_claude_child_env.py).
#   NOT COVERED tmux panes started from a raw command string, because tmux runs it under /bin/sh,
#               which never reads ~/.bashrc. Fleet tenants get it from tenant_run.sh instead.
# Verify with --status, and do not restate the scope from memory.
set -euo pipefail

AUTH_FILE="$HOME/.claude/oauth-token.env"
BASHRC="$HOME/.bashrc"
MARKER_BEGIN="# >>> agent claude setup credential >>>"
MARKER_END="# <<< agent claude setup credential <<<"

die() { printf '%s\n' "ERROR: $*" >&2; exit 1; }

fingerprint() {  # print a stable id for a secret WITHOUT revealing it
  sha256sum | cut -c1-12
}

cmd_status() {
  echo "=== claude setup credential status ==="
  if [[ -f "$AUTH_FILE" ]]; then
    local perms; perms=$(stat -c '%a' "$AUTH_FILE")
    echo "file       : $AUTH_FILE (mode $perms)"
    [[ "$perms" == "600" ]] || echo "  WARNING: mode is $perms, expected 600"
    echo "fingerprint: $(sed -n 's/^export CLAUDE_CODE_OAUTH_TOKEN=//p' "$AUTH_FILE" | tr -d "'\"" | fingerprint)"
  else
    echo "file       : (none installed)"
  fi
  grep -qF "$MARKER_BEGIN" "$BASHRC" 2>/dev/null \
    && echo "bashrc     : wired" || echo "bashrc     : not wired"
  if [[ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]]; then
    echo "this shell : credential IS set"
  else
    echo "this shell : credential not set (open a new shell, or source $AUTH_FILE)"
  fi
  echo
  echo "NOT project-scoped: a credential is account-wide. Every 'claude' in every folder is you."
  echo "covered    : shells that source ~/.bashrc. terminals you open, AND 'bash -lc' spawns."
  echo "NOT covered: systemd + cron, and tmux panes launched from a raw command string (tmux runs"
  echo "             those under /bin/sh, which skips ~/.bashrc). Have those launchers source"
  echo "             scripts/lib/lib_claude_setup_auth.sh."
}

cmd_uninstall() {
  if [[ -f "$AUTH_FILE" ]]; then rm -f "$AUTH_FILE"; echo "removed $AUTH_FILE"; fi
  if grep -qF "$MARKER_BEGIN" "$BASHRC" 2>/dev/null; then
    # keep a copy before editing a file we did not write
    cp -a "$BASHRC" "$BASHRC.bak-$(date +%Y%m%d-%H%M%S)"
    sed -i "/${MARKER_BEGIN//\//\\/}/,/${MARKER_END//\//\\/}/d" "$BASHRC"
    echo "unwired $BASHRC (backup kept alongside)"
  fi
  echo "Done. New shells fall back to normal OAuth via ~/.claude/.credentials.json"
}

cmd_install() {
  [[ -t 0 ]] || die "run this in a terminal, the credential is read from an interactive prompt"

  echo "Paste the value from 'claude setup-token' (input hidden), then press Enter:"
  local value=""
  read -rs value
  echo

  [[ -n "$value" ]] || die "empty input, nothing written"
  [[ "$value" != *[[:space:]]* ]] || die "value contains whitespace, looks like a paste error"
  [[ ${#value} -ge 20 ]] || die "value is only ${#value} chars, that is too short to be real"

  umask 077
  mkdir -p "$(dirname "$AUTH_FILE")"
  printf 'export CLAUDE_CODE_OAUTH_TOKEN=%q\n' "$value" > "$AUTH_FILE"
  chmod 600 "$AUTH_FILE"

  if ! grep -qF "$MARKER_BEGIN" "$BASHRC" 2>/dev/null; then
    [[ -f "$BASHRC" ]] && cp -a "$BASHRC" "$BASHRC.bak-$(date +%Y%m%d-%H%M%S)"
    {
      echo ""
      echo "$MARKER_BEGIN"
      echo "[ -f \"$AUTH_FILE\" ] && . \"$AUTH_FILE\""
      echo "$MARKER_END"
    } >> "$BASHRC"
    echo "wired into $BASHRC (backup kept alongside)"
  else
    echo "$BASHRC already wired, left alone"
  fi

  unset value
  echo
  cmd_status
  echo
  # NOTE: `claude --version` is NOT a valid check, it never touches auth and passes on a junk
  # credential. The check has to make a real call.
  echo "Next: open a NEW terminal and run:  claude -p 'say ok'"
  echo "An answer means it took. A login prompt means it did not."
  echo "Rollback at any time: $0 --uninstall"
}

case "${1:-install}" in
  --status|status)       cmd_status ;;
  --uninstall|uninstall) cmd_uninstall ;;
  install)               cmd_install ;;
  -h|--help)             sed -n '2,27p' "$0" ;;
  *) die "unknown option '$1'. use: (no args) | --status | --uninstall | --help" ;;
esac
