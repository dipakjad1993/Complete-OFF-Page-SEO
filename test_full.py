import httpx, json, time

# Check brands
r = httpx.get('http://localhost:8000/api/v1/brands/', timeout=5)
brands = r.json()
print(f"Brands: {len(brands)}")
for b in brands:
    print(f"  ID:{b['id']} {b['name']} ({b['domain']})")

if brands:
    bid = brands[0]['id']
    print(f"\nRunning analysis for brand {bid}...")
    start = time.time()
    r2 = httpx.post('http://localhost:8000/api/v1/analysis/run', 
                     json={"brand_id": bid, "analysis_type": "full"}, 
                     timeout=300)
    elapsed = time.time() - start
    print(f"Status: {r2.status_code}, Time: {elapsed:.1f}s")
    
    if r2.status_code == 200:
        data = r2.json()
        sections = data.get("sections", {})
        print(f"Sections: {len(sections)}")
        non_zero = 0
        errors = 0
        for key, val in sorted(sections.items()):
            if isinstance(val, dict):
                if 'error' in val:
                    errors += 1
                    print(f"  ERROR {key}: {str(val.get('error',''))[:80]}")
                else:
                    nums = [v for k,v in val.items() if isinstance(v,(int,float)) and k != 'feature_name']
                    nz = sum(1 for v in nums if v != 0)
                    if nz > 0:
                        non_zero += 1
                    print(f"  {'OK' if nz > 0 else 'ZERO'} {key}")
        print(f"\nResult: {non_zero} OK, {errors} errors, {len(sections)-non_zero-errors} zeros")
        summary = data.get("summary", {})
        print(f"Score: {summary.get('overall_score', 'N/A')}")
    else:
        print(f"ERROR: {r2.text[:500]}")
else:
    # Create a brand first
    print("No brands found. Creating OpenAI...")
    r = httpx.post('http://localhost:8000/api/v1/brands/', json={
        "name": "OpenAI", "domain": "openai.com", 
        "description": "AI research company",
        "primary_categories": ["technology"],
        "seed_keywords": ["AI", "GPT", "ChatGPT"]
    }, timeout=10)
    brand = r.json()
    print(f"Created brand ID {brand['id']}")
    
    # Now run analysis
    start = time.time()
    r2 = httpx.post('http://localhost:8000/api/v1/analysis/run', 
                     json={"brand_id": brand['id'], "analysis_type": "full"}, 
                     timeout=300)
    elapsed = time.time() - start
    print(f"Analysis: status={r2.status_code}, time={elapsed:.1f}s")
    if r2.status_code == 200:
        data = r2.json()
        sections = data.get("sections", {})
        print(f"Sections: {len(sections)}")
        non_zero = 0
        for key, val in sorted(sections.items()):
            if isinstance(val, dict) and 'error' not in val:
                nums = [v for k,v in val.items() if isinstance(v,(int,float)) and k != 'feature_name']
                nz = sum(1 for v in nums if v != 0)
                if nz > 0:
                    non_zero += 1
                print(f"  {'OK' if nz > 0 else 'ZERO'} {key}")
            elif isinstance(val, dict) and 'error' in val:
                print(f"  ERROR {key}: {str(val['error'])[:80]}")
        print(f"\nResult: {non_zero}/{len(sections)} features with data")
        print(f"Score: {data.get('summary',{}).get('overall_score','N/A')}")
