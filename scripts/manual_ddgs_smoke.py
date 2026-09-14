"""DDGS smoke test — requires ddgs in requirements.txt (pip install -r requirements.txt)."""
try:
    from ddgs import DDGS
except ImportError as e:
    print(f"SKIP: ddgs not installed ({e}). Run: pip install ddgs==9.0.0")
    raise SystemExit(0)

results = list(DDGS(timeout=12).text("CrowdStrike review", max_results=5) or [])
print(f"Results: {len(results)}")
for r in results:
    print(f"  Title: {r.get('title', '')[:60]}")
    print(f"  URL: {r.get('href', '')[:60]}")
    print(f"  Body: {r.get('body', '')[:100]}")
    print()
assert len(results) > 0, "ddgs returned 0 results — network may be blocked"
print("OK: ddgs live search working")
