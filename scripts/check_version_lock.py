"""Version-lock CI gate: README v2026.4.0 == config/settings.py APP_VERSION == frontend/package.json version.

Fails CI if enterprise version drifts — the #1 trust killer in vendor vetting.
"""
import json, re, pathlib, sys

root = pathlib.Path(__file__).resolve().parents[1]
readme = (root / "README.md").read_text(encoding="utf-8", errors="ignore")
settings_text = (root / "config/settings.py").read_text(encoding="utf-8", errors="ignore")
frontend_pkg = json.loads((root / "frontend/package.json").read_text(encoding="utf-8"))

m_ver = re.search(r'APP_VERSION\s*:\s*str\s*=\s*"([^"]+)"', settings_text)
settings_ver = m_ver.group(1).strip() if m_ver else ""

# README first header line with v2026.x.x
m_readme = re.search(r'v2026\.(\d+)\.(\d+)', readme)
readme_ver = f"2026.{m_readme.group(1)}.{m_readme.group(2)}" if m_readme else ""

# Also check explicit v2026.4.0 string in header badges
has_badge = "v2026.4.0" in readme

frontend_ver = str(frontend_pkg.get("version", "")).strip()

print(f"[version-lock] settings APP_VERSION={settings_ver}")
print(f"[version-lock] README v badge has v2026.4.0={has_badge} readme_ver={readme_ver}")
print(f"[version-lock] frontend/package.json version={frontend_ver}")

ok = True
if settings_ver != "2026.4.0":
    print(f"FAIL: config/settings.py APP_VERSION expected 2026.4.0 got {settings_ver}")
    ok = False
if not has_badge:
    print("FAIL: README must contain v2026.4.0 badge/header")
    ok = False
if frontend_ver != "2026.4.0":
    print(f"FAIL: frontend/package.json expected 2026.4.0 got {frontend_ver}")
    ok = False
if not ok:
    # dump hints
    print("\n--- README header snippet ---")
    for line in readme.splitlines()[:12]:
        print(line[:200])
    sys.exit(1)

print("version-lock OK: all three versions = 2026.4.0")
