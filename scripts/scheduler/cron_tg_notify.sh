#!/usr/bin/env bash
# cron_tg_notify.sh: minimal Telegram notifier for shell crons (no model turn). Sends $1 to the
# operator chat. Part of Utopia OS, an open framework for personal-AI-operations. MIT.
#
# Credentials: TELEGRAM_BOT_TOKEN and OPERATOR_CHAT_ID from the environment, or from the
# KEY=value file named by $AGENT_NOTIFY_ENV (the same convention as cron_runcount_probe.py).
# The token goes to curl on stdin as a config line, so it never appears in argv or `ps`.
#
# Exit codes:
#   0  Telegram answered "ok":true, so the message was delivered
#   1  no token or chat id, curl failed, or Telegram rejected the message
# It used to exit 0 always, which turned every rejected alert into a silent success. Callers
# must check the exit code; scripts/security/tg_sender_lint.py lists callers that do not.
# On exit 1 a short reason goes to stderr: Telegram's "description" field, or the curl exit
# code. curl's own error text is never printed, because it can carry the request URL and the
# URL holds the bot token. Telegram's response body never contains the token.
TOKEN="${TELEGRAM_BOT_TOKEN:-}"
CHAT="${OPERATOR_CHAT_ID:-}"
if [ -n "${AGENT_NOTIFY_ENV:-}" ] && [ -r "$AGENT_NOTIFY_ENV" ]; then
  [ -z "$TOKEN" ] && TOKEN=$(grep -E '^TELEGRAM_BOT_TOKEN=' "$AGENT_NOTIFY_ENV" | head -1 | cut -d= -f2-)
  [ -z "$CHAT" ] && CHAT=$(grep -E '^OPERATOR_CHAT_ID=' "$AGENT_NOTIFY_ENV" | head -1 | cut -d= -f2-)
fi
if [ -z "$TOKEN" ] || [ -z "$CHAT" ]; then
  echo "cron_tg_notify: TELEGRAM_BOT_TOKEN or OPERATOR_CHAT_ID not set" >&2
  exit 1
fi
BODY=$(printf 'url = "https://api.telegram.org/bot%s/sendMessage"\n' "$TOKEN" \
  | curl -s --max-time 15 -K - --data-urlencode "chat_id=$CHAT" --data-urlencode "text=$1" 2>/dev/null)
RC=$?
unset TOKEN
if [ "$RC" -ne 0 ]; then
  echo "cron_tg_notify: curl failed (curl exit $RC)" >&2
  exit 1
fi
case "$BODY" in
  '{"ok":true'*) exit 0 ;;
esac
DESC=$(printf '%s' "$BODY" | python3 -c '
import json, sys
try:
    print(str(json.load(sys.stdin).get("description", "no description"))[:200])
except Exception:
    print("response was not Telegram JSON")
' 2>/dev/null)
echo "cron_tg_notify: rejected: ${DESC:-unknown}" >&2
exit 1
