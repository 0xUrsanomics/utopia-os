#!/bin/bash
# Run a command in a bubblewrap sandbox that CANNOT read credential paths (.ssh,
# cloud/gh creds, gpg, agent env, workspace .env) and starts from a CLEAN
# environment. For the highest-risk subprocesses that chew on UNTRUSTED external
# content (web research, remote fetch, document parse), i.e. the prompt-injection
# entry points. This is the OS enforcement of the prose "no secret access" rule:
# even a fully-hijacked child physically cannot read the secrets.
#
# Usage: bwrap_run.sh [--no-net] [--workdir DIR] [--setenv K V]... -- CMD [ARGS...]
#   --no-net    isolate the network too (for pure processing that needs no net)
#   --workdir   a writable bind for output (default: only /tmp is writable)
#   --setenv    pass an explicit env var into the clean sandbox env
# Extra secret paths (colon-separated) via env:
#   BWRAP_SECRET_DIRS   extra directories to mask
#   BWRAP_SECRET_FILES  extra files to mask
#   BWRAP_ENV_ROOT      root to sweep for .env files (default: $WORKSPACE or ~/projects)
#
# FAILS CLOSED: if bwrap is missing it REFUSES to run (does not fall back to an
# unsandboxed run) — the guarantee is the whole point.
set -uo pipefail

command -v bwrap >/dev/null 2>&1 || {
    echo "bwrap_run: bubblewrap not installed; refusing to run UNSANDBOXED (fail-closed)." >&2
    exit 90
}

NET="--share-net"
WORKDIR=""
SETENVS=()
SECRET_ENVS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --no-net)     NET="--unshare-net"; shift;;
        --workdir)    WORKDIR="${2:-}"; shift 2;;
        --setenv)     SETENVS+=(--setenv "${2:-}" "${3:-}"); shift 3;;
        --secret-env) SECRET_ENVS+=("${2:-}"); shift 2;;
        --)           shift; break;;
        *)            echo "bwrap_run: unknown arg $1" >&2; exit 91;;
    esac
done
[ $# -ge 1 ] || { echo "bwrap_run: no command given (use -- CMD ...)" >&2; exit 92; }

SECRET_DIRS=( "$HOME/.ssh" "$HOME/.aws" "$HOME/.config/gcloud" "$HOME/.config/gh"
              "$HOME/.gnupg" "$HOME/.config/agent" )
SECRET_FILES=( "$HOME/.claude/.credentials.json" )
IFS=':' read -ra _XD <<< "${BWRAP_SECRET_DIRS:-}";  for d in "${_XD[@]}";  do [ -n "$d" ] && SECRET_DIRS+=("$d"); done
IFS=':' read -ra _XF <<< "${BWRAP_SECRET_FILES:-}"; for f in "${_XF[@]}"; do [ -n "$f" ] && SECRET_FILES+=("$f"); done
# every workspace .env is secret-bearing -> mask them all (found at runtime)
ENV_ROOT="${BWRAP_ENV_ROOT:-${WORKSPACE:-$HOME/projects}}"
while IFS= read -r f; do SECRET_FILES+=("$f"); done < <(find "$ENV_ROOT" -maxdepth 4 -name ".env" 2>/dev/null | grep -v '/venv/' | head -50)

ARGS=( --ro-bind / / --dev /dev --proc /proc --tmpfs /tmp )
if [ -n "$WORKDIR" ]; then mkdir -p "$WORKDIR" 2>/dev/null || true; ARGS+=( --bind "$WORKDIR" "$WORKDIR" ); fi
for d in "${SECRET_DIRS[@]}";  do [ -d "$d" ] && ARGS+=( --tmpfs "$d" ); done
for f in "${SECRET_FILES[@]}"; do [ -e "$f" ] && ARGS+=( --ro-bind /dev/null "$f" ); done
ARGS+=( --unshare-all "$NET" --die-with-parent --new-session --clearenv
        --setenv PATH "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$HOME/.local/bin"
        --setenv HOME "$HOME" --setenv USER "${USER:-agent}"
        --setenv LANG "${LANG:-C.UTF-8}" --setenv TERM "${TERM:-xterm}" )
ARGS+=( "${SETENVS[@]}" )

# Secrets passed by ENV-VAR NAME (never on any argv): the value is read from this
# script's own environment, streamed in through an fd via --ro-bind-data (so it
# never appears in a process command line), and exposed inside as the file
# /tmp/.secret_<NAME> with <NAME>_FILE pointing at it. Avoids secret-in-argv.
for _n in "${SECRET_ENVS[@]:-}"; do
    [ -z "$_n" ] && continue
    _v="${!_n:-}"
    [ -z "$_v" ] && continue
    exec {_sfd}< <(printf '%s' "$_v")
    ARGS+=( --ro-bind-data "$_sfd" "/tmp/.secret_$_n" --setenv "${_n}_FILE" "/tmp/.secret_$_n" )
done

exec bwrap "${ARGS[@]}" "$@"
