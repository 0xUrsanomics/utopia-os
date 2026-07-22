# lib_path_guard.py — path-traversal confinement guard for anything that touches dynamic paths.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""
lib_path_guard.py — path-traversal confinement guard for scripts touching user paths.

Pattern from VectifyAI/OpenKB (Apache-2.0): every read/write tool checks
`path.is_relative_to(allowed_root)` before operating. Prevents path-traversal attacks
(../../../etc/passwd) and accidental cross-scope writes.

Usage:
    from lib_path_guard import confined_path, PathGuardError

    ROOT = Path.home() / "projects" / "my-workspace"

    def write_user_doc(rel_path: str, content: str) -> None:
        target = confined_path(ROOT / "outputs" / rel_path, allowed_root=ROOT)
        target.write_text(content)

    # If rel_path is "../../etc/passwd", confined_path raises PathGuardError.
    # If rel_path is "raw/doc.md", confined_path returns the resolved path.

When to use:
- Any function that takes a user/external/dynamic path string
- Any cron-dispatched script writing to scoped output dirs
- Any harvester script handling untrusted feed metadata
- Any subagent dispatcher passing paths to children

When NOT to use:
- Hardcoded paths inside scripts (no traversal vector)
- Paths from trusted internal sources when the source is verified
- Read-only inspection where blast radius is bounded

Caveats:
- `Path.is_relative_to` was added in Python 3.9. Fallback for older versions included.
- Symlink resolution: we use `.resolve()` to follow symlinks. If allowed_root contains symlinks
  pointing OUTSIDE the intended scope, this can be bypassed. Don't put symlink shortcuts in scoped roots.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union


class PathGuardError(ValueError):
    """Raised when a path would escape its allowed root."""
    pass


def is_relative_to_safe(path: Path, root: Path) -> bool:
    """Compatibility shim. Path.is_relative_to() is Python 3.9+, this works on 3.8 too."""
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def confined_path(
    candidate: Union[str, Path],
    allowed_root: Union[str, Path],
    *,
    must_exist: bool = False,
    create_parents: bool = False,
) -> Path:
    """Validate a candidate path is within allowed_root. Return resolved Path.

    Args:
        candidate: the path to validate (string or Path).
        allowed_root: the directory the candidate MUST be inside (after resolution).
        must_exist: if True, raise PathGuardError when the resolved path doesn't exist.
        create_parents: if True, mkdir -p the parent directory after validation.

    Returns:
        Resolved Path inside allowed_root.

    Raises:
        PathGuardError: if candidate resolves outside allowed_root, or must_exist + missing.
    """
    cand = Path(candidate).expanduser()
    root = Path(allowed_root).expanduser().resolve()

    # Resolve the candidate; for non-existent paths, resolve() still expands ../ correctly
    try:
        resolved = cand.resolve()
    except (OSError, RuntimeError) as e:
        raise PathGuardError(f"unable to resolve candidate path: {cand} ({e})")

    if not is_relative_to_safe(resolved, root):
        raise PathGuardError(
            f"path escapes allowed root: candidate={cand!r} resolved={resolved!r} root={root!r}"
        )

    if must_exist and not resolved.exists():
        raise PathGuardError(f"path does not exist: {resolved!r}")

    if create_parents:
        resolved.parent.mkdir(parents=True, exist_ok=True)

    return resolved


def assert_confined(candidate: Union[str, Path], allowed_root: Union[str, Path]) -> None:
    """Assert-only variant. Raises PathGuardError, returns None on success."""
    confined_path(candidate, allowed_root)


# ── Self-test ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "subdir").mkdir()

        # Pass cases
        ok = confined_path(root / "file.txt", root)
        assert ok == (root / "file.txt").resolve()

        ok = confined_path(root / "subdir" / "x.md", root)
        assert ok == (root / "subdir" / "x.md").resolve()

        # Fail cases
        try:
            confined_path("/etc/passwd", root)
            print("FAIL: /etc/passwd should have raised", file=sys.stderr)
            sys.exit(1)
        except PathGuardError:
            pass

        try:
            confined_path(root / ".." / "outside.txt", root)
            print("FAIL: ../outside should have raised", file=sys.stderr)
            sys.exit(1)
        except PathGuardError:
            pass

        # must_exist
        try:
            confined_path(root / "missing.txt", root, must_exist=True)
            print("FAIL: missing path should have raised", file=sys.stderr)
            sys.exit(1)
        except PathGuardError:
            pass

        # create_parents
        nested = confined_path(root / "a" / "b" / "c.md", root, create_parents=True)
        assert nested.parent.exists()

        print("self-test PASSED")
