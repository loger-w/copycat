#!/usr/bin/env python3
"""PostToolUse hook: auto-format the file Claude just wrote/edited (hardened).

Dispatch by extension:
  *.py                              → ruff format ONLY (no check --fix; TDD-safe)
  *.ts / *.tsx / *.js / *.jsx ...   → nearest node_modules/.bin/eslint --fix

Skips silently when:
  - formatter is not available
  - file is under a vendor / generated tree (node_modules, .venv, dist, ...)
  - file is a minified / generated artifact (*.min.js, *.d.ts, *.pyc, ...)
  - PostToolUse payload is malformed

Never blocks (always exits 0).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

WINDOWS = os.name == "nt"

PY_EXTENSIONS = {".py"}
JS_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}

ESLINT_TIMEOUT_SEC = 10
RUFF_TIMEOUT_SEC = 5

# Skip files under any of these directories (vendor / build / cache).
_SKIP_DIR_PARTS = {
    "node_modules",
    ".venv",
    "venv",
    "site-packages",
    "dist",
    "build",
    "__pycache__",
    ".next",
    ".nuxt",
    ".turbo",
    "coverage",
    ".tox",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    ".cache",
}
_SKIP_SUFFIXES = (".min.js", ".min.css", ".bundle.js", ".pyc", ".pyi", ".d.ts")
_ROOT_MARKERS = (
    ".git",
    "pyproject.toml",
    "ruff.toml",
    ".ruff.toml",
    "setup.cfg",
    "package.json",
)

# On Windows node_modules/.bin/ has both POSIX shell scripts (bare name) and
# .cmd shims. CreateProcess can only execute .cmd/.exe/.bat; the bare shell
# script fails with WinError 193. Prefer the executable variant.
_BIN_EXT_PREFERENCE = (".cmd", ".CMD", ".bat", ".BAT", ".exe", "") if WINDOWS else ("",)


def find_repo_root(start: Path) -> Path:
    """Return the closest ancestor containing any root marker."""
    for parent in [start, *start.parents]:
        if any((parent / m).exists() for m in _ROOT_MARKERS):
            return parent
    return start.parent


def find_ancestor(start: Path, target_rel: str) -> Path | None:
    """Walk up parents looking for target_rel. Bounded by first .git. For
    node_modules/.bin/* paths, requires a sibling package.json to avoid
    matching stray installs in unrelated parents.
    """
    requires_pkg_json = target_rel.startswith("node_modules")
    seen: set[Path] = set()
    chains = [start.parents, start.resolve().parents]
    for chain in chains:
        for parent in chain:
            if parent in seen:
                continue
            seen.add(parent)
            for ext in _BIN_EXT_PREFERENCE:
                cand = parent / (target_rel + ext)
                if cand.exists():
                    if requires_pkg_json and not (parent / "package.json").exists():
                        continue
                    return cand
            if (parent / ".git").exists():
                break
    return None


def find_python_tool(name: str, start: Path) -> str | None:
    """Prefer venv-pinned tool, fall back to PATH."""
    for parent in [start, *start.parents]:
        for cand in (
            parent / ".venv" / "Scripts" / f"{name}.exe",
            parent / ".venv" / "bin" / name,
            parent / "venv" / "Scripts" / f"{name}.exe",
            parent / "venv" / "bin" / name,
        ):
            if cand.exists():
                return str(cand)
        if (parent / ".git").exists():
            break
    return shutil.which(name)


def run(cmd: list[str], cwd: Path, timeout: float) -> tuple[int, str]:
    """Subprocess wrapper that kills the entire child tree on timeout (Windows-safe)."""
    try:
        if WINDOWS:
            proc = subprocess.Popen(
                cmd,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
            try:
                out, err = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                # Default Popen.kill on Windows only kills the cmd.exe shim;
                # node.exe / python.exe children survive and hold file locks.
                # taskkill /T walks the process tree.
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True,
                )
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
                return 124, f"timeout after {timeout}s (tree killed): {cmd[0]}"
            msg = (err or "") + (out or "")
            return proc.returncode or 0, msg.strip()

        result = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        out = (result.stderr or "") + (result.stdout or "")
        return result.returncode, out.strip()
    except FileNotFoundError:
        return 127, f"executable not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, f"timeout: {' '.join(cmd[:3])}"


def format_python(file_path: Path, cwd: Path) -> list[str]:
    # Intentionally `ruff format` only — NOT `ruff check --fix`. Auto-fixing
    # F401 (unused-import) during TDD red→green cycles is hostile: the test
    # file imports symbols that don't exist yet, and the fixer deletes the
    # import the moment you save. ruff format is pure whitespace/syntax
    # rewrite and never removes code. Lint findings still surface via
    # `python -m pytest` / `ruff check` at commit-time gate.
    ruff = find_python_tool("ruff", cwd)
    if ruff is None:
        return []
    rc, msg = run([ruff, "format", str(file_path)], cwd=cwd, timeout=RUFF_TIMEOUT_SEC)
    if rc != 0 and msg:
        return [f"ruff format failed (rc={rc}): {msg.splitlines()[0][:200]}"]
    return []


def format_js_ts(file_path: Path, cwd: Path) -> list[str]:
    eslint = find_ancestor(
        file_path.parent, "node_modules/.bin/eslint"
    ) or find_ancestor(cwd, "node_modules/.bin/eslint")
    if eslint is None:
        return []
    eslint_root = eslint.parent.parent.parent  # .bin → node_modules → repo
    rc, msg = run(
        [str(eslint), "--fix", "--no-error-on-unmatched-pattern", str(file_path)],
        cwd=eslint_root,
        timeout=ESLINT_TIMEOUT_SEC,
    )
    # eslint exits 1 on remaining warnings — only treat rc>=2 as real failure.
    if rc >= 2 and msg:
        return [f"eslint --fix failed (rc={rc}): {msg.splitlines()[0][:200]}"]
    return []


def select_formatter(ext: str):
    if ext in PY_EXTENSIONS:
        return format_python
    if ext in JS_EXTENSIONS:
        return format_js_ts
    return None


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            return 0

        tool_name = payload.get("tool_name") or payload.get("toolName") or ""
        if tool_name not in {"Write", "Edit", "MultiEdit"}:
            return 0

        tool_input = payload.get("tool_input") or payload.get("toolInput") or {}
        if not isinstance(tool_input, dict):
            return 0

        raw_path = tool_input.get("file_path") or tool_input.get("filePath") or ""
        if not isinstance(raw_path, str) or not raw_path:
            return 0

        file_path = Path(raw_path)
        if not file_path.is_absolute():
            file_path = Path.cwd() / file_path
        if not file_path.exists() or not file_path.is_file():
            return 0

        # Skip vendor / generated dirs and minified artifacts.
        if set(file_path.resolve().parts) & _SKIP_DIR_PARTS:
            return 0
        if file_path.name.endswith(_SKIP_SUFFIXES):
            return 0

        formatter = select_formatter(file_path.suffix.lower())
        if formatter is None:
            return 0

        cwd = find_repo_root(file_path)
        errs = formatter(file_path, cwd)
        for e in errs:
            print(f"format-on-edit({file_path.name}): {e}", file=sys.stderr)
    except Exception as e:  # noqa: BLE001 — hook must never crash the host
        print(
            f"format-on-edit: unexpected error (silenced): {type(e).__name__}: {e}",
            file=sys.stderr,
        )
    return 0  # Never block on format failure


if __name__ == "__main__":
    sys.exit(main())
