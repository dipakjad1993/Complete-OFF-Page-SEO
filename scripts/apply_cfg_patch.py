"""Apply brand_config_for() resolver across P1 routers + engine extended block."""
import pathlib

OLD_A = "    from backend.api.analysis import load_configs\n    cfgs = load_configs()\n    cfg = cfgs.get(str(brand_id), {}) if isinstance(cfgs, dict) else {}"
OLD_B = "    from backend.api.analysis import load_configs\n    cfgs = load_configs()\n    cfg = cfgs.get(str(brand_id), cfgs.get(int(brand_id), {})) if isinstance(cfgs, dict) else {}"
NEW = "    from backend.services.brand_config import brand_config_for\n    cfg = brand_config_for(brand_id)"

for f in ["backend/api/kg_ops.py", "backend/api/bot_governance.py",
          "backend/api/prompt_tracking.py", "backend/api/ugc_depth.py",
          "backend/api/image_backlinks.py", "backend/api/author_graph.py"]:
    p = pathlib.Path(f)
    src = p.read_text(encoding="utf-8", errors="replace")
    n0 = src.count(OLD_A) + src.count(OLD_B)
    src = src.replace(OLD_A, NEW).replace(OLD_B, NEW)
    # fix shadowed name: some funcs use `cfgs`/`cfg` later for the flat dict — rename trailing uses
    p.write_text(src, encoding="utf-8")
    print(f, "patched lookups:", n0)

# engine extended block: _bcfg2 raw nested -> resolved flat
pe = pathlib.Path("backend/api/analysis.py")
src = pe.read_text(encoding="utf-8", errors="replace")
old_e = "        _bcfg2 = _cfgs.get(str(brand_id), _cfgs.get(int(brand_id), {})) if isinstance(_cfgs, dict) else {}"
new_e = "        from backend.services.brand_config import brand_config_for as _bcf\n        _bcfg2 = _bcf(brand_id)"
assert old_e in src, "engine extended block not found"
pe.write_text(src.replace(old_e, new_e), encoding="utf-8")
print("analysis.py extended block patched")
