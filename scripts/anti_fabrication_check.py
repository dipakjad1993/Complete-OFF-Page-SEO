"""Anti-fabrication static audit — fails CI if output paths fake data.

Forbids random/faker/mock/synthetic value generation inside
backend/api/analysis.py output path and backend/modules/.
Allows `random` only for UA rotation in services/search.py.
"""
import pathlib
import re
import sys

FORBIDDEN = [r"\brandom\.(randint|random|uniform|choice)\b.*metric",
             r"\bfaker\b", r"\bFaker\b", r"synthetic_value",
             r"mock_results\s*=", r"demo_data\s*="]
ROOTS = [pathlib.Path("backend/api/analysis.py"),
         pathlib.Path("backend/modules")]

bad = []
for root in ROOTS:
    files = [root] if root.is_file() else list(root.rglob("*.py"))
    for p in files:
        text = p.read_text(encoding="utf-8", errors="ignore")
        for pat in FORBIDDEN:
            if re.search(pat, text):
                bad.append(f"{p}:{pat}")
if bad:
    print("ANTI-FABRICATION FAIL:")
    print("\n".join(bad))
    sys.exit(1)
print("anti-fabrication OK: no fabricated output paths found.")
