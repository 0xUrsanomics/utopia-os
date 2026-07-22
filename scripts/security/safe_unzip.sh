#!/usr/bin/env bash
# safe_unzip.sh — unzip an archive, then neutralize any planted .git/hooks executables.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
#
# Defense against the zip-hook attack vector (as used in the "Contagious Interview"
# campaign): standard `unzip` preserves executable bits on .git/hooks/* files, which
# git auto-fires on the next `git checkout` or `git commit`. This wrapper:
#   1. Unzips to a target directory
#   2. Immediately strips the executable bit from ALL files under .git/hooks/
#   3. Runs audit_repo_hooks.py to confirm no leftover suspicious bits
#   4. Prints a summary
#
# Usage:
#   safe_unzip.sh <zip-file> [target-dir]
#
# If target-dir omitted, unzips to ./<zipname-without-ext>/
#
# Exit codes:
#   0 = unzipped + neutralized + audit clean
#   1 = unzipped but audit found post-neutralize findings (shouldn't happen, investigate)
#   2 = invocation error

set -eo pipefail

if [[ $# -lt 1 ]]; then
    echo "usage: $0 <zip-file> [target-dir]" >&2
    exit 2
fi

ZIP="$1"
TARGET="${2:-${ZIP%.zip}}"

if [[ ! -f "$ZIP" ]]; then
    echo "error: zip file not found: $ZIP" >&2
    exit 2
fi

if [[ -e "$TARGET" ]]; then
    echo "error: target already exists: $TARGET" >&2
    exit 2
fi

echo "📦 unzipping $ZIP → $TARGET ..."
mkdir -p "$TARGET"
unzip -q "$ZIP" -d "$TARGET"

# Neutralize ALL hook executables (find every .git/hooks dir within the target)
echo "🛡️  neutralizing .git/hooks/* executables ..."
NEUTRALIZED=0
while IFS= read -r -d '' hooks_dir; do
    while IFS= read -r -d '' hook_file; do
        chmod -x "$hook_file"
        NEUTRALIZED=$((NEUTRALIZED + 1))
    done < <(find "$hooks_dir" -maxdepth 1 -type f -not -name "*.sample" -print0 2>/dev/null)
done < <(find "$TARGET" -type d -name "hooks" -path "*/.git/hooks" -print0 2>/dev/null)

echo "   chmod -x applied to $NEUTRALIZED file(s)"

# Audit confirmation
echo "🔍 running audit_repo_hooks.py for confirmation ..."
SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
if python3 "$SCRIPT_DIR/audit_repo_hooks.py" "$TARGET" --quiet; then
    echo "✅ all clean — $TARGET is safe for git ops"
    exit 0
else
    echo "⚠️  audit STILL found suspicious files after neutralize. Investigate $TARGET manually."
    exit 1
fi
