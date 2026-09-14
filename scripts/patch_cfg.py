"""Patch P1 routers + engine to use brand_config_for() flat resolver."""
import pathlib, re

PATCHES = {
    "backend/api/kg_ops.py": [
        ("    from backend.api.analysis import load_configs\n    cfgs = load_configs()\n    cfg = cfgs.get(str(brand_id), {}) if isinstance(cfgs, dict) else {}",
         "    from backend.services.brand_config import brand_config_for\n    cfg = brand_config_for(brand_id)"),
    ],
    "backend/api/bot_governance.py": [],
    "backend/api/prompt_tracking.py": [],
    "backend/api/ugc_depth.py": [],
    "backend/api/image_backlinks.py": [],
    "backend/api/author_graph.py": [],
}

# discover lookup patterns in each router first
for f in PATCHES:
    src = pathlib.Path(f).read_text(encoding="utf-8", errors="replace")
    for i, l in enumerate(src.splitlines(), 1):
        if "load_configs" in l or "cfgs.get" in l or "brand_configs" in l:
            print(f"{f}:{i}: {l.strip()[:120]}")
