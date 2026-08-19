from ddgs import DDGS

results = DDGS().text("CrowdStrike review", max_results=5)
print(f"Results: {len(results)}")
for r in results:
    print(f"  Title: {r.get('title', '')[:60]}")
    print(f"  URL: {r.get('href', '')[:60]}")
    print(f"  Body: {r.get('body', '')[:100]}")
    print()
