#!/bin/bash
# B7 phase 2: launch the PRINCIPAL session under a bubblewrap floor that MASKS a
# configurable deny-list of never-legitimately-needed secret paths, while leaving the
# session otherwise NORMAL (writable home, full env, network) so it never breaks git
# push / MCP servers / ssh / .env-reads. NARROW BY DESIGN: this is not the untrusted-
# subprocess sandbox (bwrap_run.sh) — it is a light mask of a few crown-jewel paths on
# an otherwise-normal session.
#
# Deny-list: memory/state/principal_floor_denylist.txt (one path per line, # comments).
#
# HONEST STATUS (2026-07-23): on THIS box the effective deny-list is EMPTY, because the
# principal session legitimately uses every secret present (.ssh occasional-ssh, .env
# config, the broker vault broker for tools, ~/.git-credentials for HTTPS push) and no
# wallet/crypto-signing files exist. So this is a READY mechanism that is a NO-OP until
# a genuinely-never-needed secret path exists to mask (e.g. a wallet dir appears). The
# broader "the model's own Bash cannot read .env" is Option 2 (sandbox-the-Bash-tool),
# deliberately deferred because it conflicts with legitimate operator Bash work. See
# memory/Infra/b7-phase2-landlock-design.md.
#
# FAIL-OPEN (unlike bwrap_run.sh): if bwrap is missing, run the command UNSANDBOXED +
# warn — locking the operator out of their own session is worse than a missing narrow floor.
#
# Usage: principal_floor.sh -- <command...>   (e.g. the claude launch command)
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DENYLIST="${PRINCIPAL_FLOOR_DENYLIST:-$ROOT/memory/state/principal_floor_denylist.txt}"

# strip a leading "--"
[ "${1:-}" = "--" ] && shift
[ $# -ge 1 ] || { echo "principal_floor: no command (use -- CMD ...)" >&2; exit 2; }

if ! command -v bwrap >/dev/null 2>&1; then
    echo "principal_floor: bubblewrap absent; running UNSANDBOXED (fail-open, availability > narrow floor)." >&2
    exec "$@"
fi

# read the deny-list (existing paths only)
DIRS=(); FILES=()
if [ -f "$DENYLIST" ]; then
    while IFS= read -r line; do
        line="${line%%#*}"; line="$(echo -n "$line" | xargs 2>/dev/null || true)"
        [ -z "$line" ] && continue
        p="$(eval echo "$line")"   # expand ~ / vars
        if   [ -d "$p" ]; then DIRS+=("$p")
        elif [ -e "$p" ]; then FILES+=("$p")
        fi
    done < "$DENYLIST"
fi

# NORMAL session (writable /, full env, net) with ONLY the deny-list masked.
ARGS=( --bind / / --dev /dev --proc /proc --die-with-parent )
for d in "${DIRS[@]:-}";  do [ -n "$d" ] && ARGS+=( --tmpfs "$d" ); done
for f in "${FILES[@]:-}"; do [ -n "$f" ] && ARGS+=( --ro-bind /dev/null "$f" ); done

if [ ${#DIRS[@]} -eq 0 ] && [ ${#FILES[@]} -eq 0 ]; then
    # nothing to mask -> the floor is a no-op; skip bwrap overhead, run normally.
    exec "$@"
fi
exec bwrap "${ARGS[@]}" "$@"
