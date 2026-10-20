# shellcheck shell=sh
# lib_claude_setup_auth.sh: load the long-lived Claude setup credential into the environment.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
#
# SOURCE it, do not execute it. Pass the agent via an ENV VAR, never a positional:
#   CLAUDE_TOKEN_AGENT=worker
#   . scripts/lib/lib_claude_setup_auth.sh
#
# NOT `. lib_claude_setup_auth.sh worker`. Passing args to the `.` builtin is a bash extension that
# dash SILENTLY IGNORES, and a launcher started by tmux from a raw command string runs under
# /bin/sh (dash on many distros). The positional form appears to pass in testing because it falls
# through to the shared file, which is indistinguishable from success when only one credential
# exists. An env var behaves identically in bash and dash.
#
# WHY. Same-account tenants used to seed a COPY of ~/.claude/.credentials.json and then refresh it
# independently. Same-account refreshes invalidate each other: random 401s on the tenants and a
# re-login prompt for the operator every few days.
#
# A `claude setup-token` credential has NO refresh cycle, so there is nothing to rotate and
# nothing to race. Three properties to verify against your own CLI build:
#   1. credential in env + EMPTY config dir            -> authenticates
#   2. credential in env + BROKEN .credentials.json    -> authenticates, env WINS
#   3. after either run, no .credentials.json is written -> no rotation, so no race
# (3) is the one that matters. It is why this is a fix and not a bandaid.
#
# RESOLUTION ORDER, per-agent first so a single-credential setup can become per-agent later by
# dropping ONE file, with no code change:
#   ~/.claude/oauth-token.<agent>.env     (per-agent override, optional)
#   ~/.claude/oauth-token.env             (fleet-wide shared)
#
# FAIL-OPEN BY DESIGN. If neither file exists this exports nothing and returns success, so the
# caller still launches on whatever .credentials.json it already has. A missing credential must
# never take a bot down; that would trade a slow auth bug for a hard outage.
#
# Never echoes the value. Callers that want to confirm a load should test CLAUDE_TOKEN_SRC,
# which holds the PATH it came from, never the value.
#
# HOW TO CHECK IF IT IS SET, without printing it:
#     RIGHT:  [ -n "$CLAUDE_CODE_OAUTH_TOKEN" ] && echo SET || echo UNSET
#     RIGHT:  echo "${CLAUDE_CODE_OAUTH_TOKEN:+SET}"
#     WRONG:  echo "${CLAUDE_CODE_OAUTH_TOKEN:+SET}${CLAUDE_CODE_OAUTH_TOKEN:-UNSET}"
# The wrong form leaks the value into a log. `${VAR:-default}` returns the VALUE whenever VAR is
# set, so concatenating the two forms prints "SET<the actual secret>". It reads like a presence
# check and behaves like one in every test where the variable is EMPTY, which is exactly when you
# are writing the check. It only betrays you once the value is real.

_uct_agent="${CLAUDE_TOKEN_AGENT:-}"
_uct_base="${HOME:-}/.claude"

for _uct_f in "$_uct_base/oauth-token.$_uct_agent.env" "$_uct_base/oauth-token.env"; do
    # skip the per-agent slot when no agent name was passed
    case "$_uct_f" in
        *"oauth-token..env") continue ;;
    esac
    if [ -f "$_uct_f" ] && [ -r "$_uct_f" ]; then
        # shellcheck disable=SC1090
        . "$_uct_f"
        if [ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
            export CLAUDE_CODE_OAUTH_TOKEN
            CLAUDE_TOKEN_SRC="$_uct_f"
            export CLAUDE_TOKEN_SRC
            break
        fi
    fi
done

unset _uct_agent _uct_base _uct_f
return 0 2>/dev/null || :
