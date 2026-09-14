"""Find top-level constants stranded in the wrong domain module."""
import ast, pathlib
from collections import defaultdict

MODS = ["llm", "pr", "kg", "technical", "risk"]
defined = {}   # name -> module
used = defaultdict(set)  # name -> set(modules using it)
for m in MODS:
    tree = ast.parse(pathlib.Path(f"backend/modules/{m}.py").read_text(encoding="utf-8", errors="replace"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id.isupper():
                    defined[t.id] = m
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used[node.id].add(m)

print("STRANDED (defined in one module, used in another):")
for name, mod in sorted(defined.items()):
    users = used[name] - {mod}
    if users:
        print(f"  {name}: defined in {mod}, used in {sorted(users)}")
print("ALL-CAPS consts per module:")
for m in MODS:
    consts = [n for n, mm in defined.items() if mm == m]
    print(f"  {m}: {consts}")
