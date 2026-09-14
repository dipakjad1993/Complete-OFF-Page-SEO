"""Fail if any backend/frontend-script file uses post-3.11 syntax.

CI runs Python 3.11 while dev may run 3.13 (PEP 701 multiline f-strings etc.).
Parses every .py with feature_version=(3, 11) grammar.
"""
import ast
import pathlib
import sys

bad = []
files = sorted(pathlib.Path(".").rglob("*.py"))
skip_dirs = {".git", "__pycache__", ".venv", "venv", "node_modules", ".pytest_cache"}
for f in files:
    if any(d in f.parts for d in skip_dirs):
        continue
    try:
        src = f.read_text(encoding="utf-8", errors="replace")
        ast.parse(src, filename=str(f), feature_version=(3, 11))
    except SyntaxError as e:
        bad.append(f"{f}:{e.lineno}: {e.msg}")
    except Exception as e:  # noqa: BLE001
        bad.append(f"{f}: ?? {e}")

if bad:
    print("PY311-INCOMPATIBLE FILES:")
    for b in bad:
        print(" ", b)
    sys.exit(1)
print(f"py311-compat OK: {len(files)} files parse under 3.11 grammar")
