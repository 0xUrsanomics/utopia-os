#!/usr/bin/env python3
# emdash_send_guard.py — PreToolUse guard: blocks em/en-dashes in outbound messages (style rule).
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Fail-open em/en-dash send guard (PreToolUse).

Blocks an outbound message send whose text contains U+2014 (em-dash) or U+2013
(en-dash), which are banned as separators in operator-facing text (a style rule).
The block returns exit 2 + a stderr reason, so the agent rewrites (comma / colon /
period) and resends. This is a structural boundary gate: a per-turn text reminder to
"avoid em-dashes" failed repeatedly, so the rule is enforced at the tool boundary
instead of relying on the model to remember.

Fail-open by design: ANY error (unreadable stdin, unexpected shape, exception)
exits 0 (allow). A guard bug must never be able to block the operator channel.
Compound hyphens (U+002D) are never matched. This covers the interactive send/reply
tools; a deterministic auto-scrub on the send path can cover automated sends.
"""
import sys
import json

GUARDED_TOOLS = {
    "mcp__plugin_telegram_telegram__reply",
    "mcp__plugin_telegram_telegram__edit_message",
    "mcp__plugin_telegram_telegram__send_message",
}
TEXT_FIELDS = ("text", "message", "caption")
DASHES = {"—": "em-dash (U+2014)", "–": "en-dash (U+2013)"}


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # fail-open: unreadable payload never blocks
    try:
        tool = data.get("tool_name", "")
        if tool not in GUARDED_TOOLS:
            sys.exit(0)
        ti = data.get("tool_input", {}) or {}
        blob = " ".join(str(ti.get(k, "")) for k in TEXT_FIELDS)
        found = [name for ch, name in DASHES.items() if ch in blob]
        if found:
            sys.stderr.write(
                "BLOCKED (emdash_send_guard): outbound text contains "
                + ", ".join(found)
                + ", banned as a separator. Rewrite with a comma, colon, or period "
                "(compound hyphens are fine), then resend.\n"
            )
            sys.exit(2)
        sys.exit(0)
    except Exception:
        sys.exit(0)  # fail-open on any guard error


if __name__ == "__main__":
    main()
