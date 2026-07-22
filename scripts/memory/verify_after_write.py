#!/usr/bin/env python3
"""PostToolUse-hook stub (Utopia OS). Run a lightweight check after a write-class tool fires, e.g.
re-lint the touched skill, confirm no secret was written, refresh an index. This generic version reads
the hook payload and passes; wire your own verification. Never block the tool on a routine write.
See docs/security-gates.md."""
import sys, json
def main() -> int:
    try:
        json.loads(sys.stdin.read() or "{}")
    except Exception:
        pass
    # add your post-write verification here
    return 0
if __name__ == "__main__":
    sys.exit(main())
