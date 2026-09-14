"""Find module-level constants lost in the monolith split."""
import ast, pathlib

bak = pathlib.Path("backend/api/analysis.py.bak").read_text(encoding="utf-8", errors="replace")
tree = ast.parse(bak)
orig = {}
for node in tree.body:
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name):
                orig[t.id] = node.lineno
    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        orig[node.target.id] = node.lineno

new_names = set()
for f in ["backend/modules/common.py", "backend/modules/llm.py", "backend/modules/pr.py",
          "backend/modules/kg.py", "backend/modules/technical.py", "backend/modules/risk.py",
          "backend/api/analysis.py"]:
    t = ast.parse(pathlib.Path(f).read_text(encoding="utf-8", errors="replace"))
    for node in ast.walk(t):
        if isinstance(node, ast.Assign):
            for x in node.targets:
                if isinstance(x, ast.Name):
                    new_names.add(x.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            new_names.add(node.target.id)

lost = {k: v for k, v in orig.items() if k not in new_names and not k.startswith("__")}
print(f"orig consts: {len(orig)} | lost: {len(lost)}")
for k, ln in sorted(lost.items(), key=lambda x: x[1]):
    print(f"  bak:{ln}  {k}")
