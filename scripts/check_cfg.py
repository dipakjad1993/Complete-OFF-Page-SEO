import json, re
cfg = json.load(open('data/brand_configs.json', encoding='utf-8', errors='replace'))
keys = set()
for bid, v in cfg.items():
    if isinstance(v, dict):
        keys.update(v.keys())
print('sub-keys:', keys)
for mod in ['bot_governance', 'prompt_tracking', 'ugc_depth', 'image_backlinks',
            'author_graph', 'pr_outreach', 'multi_brand']:
    src = open(f'backend/api/{mod}.py', encoding='utf-8', errors='replace').read()
    hits = sorted(set(re.findall(r'cfg.get\("([a-z_]+)"\)', src)))
    print(mod, hits)
