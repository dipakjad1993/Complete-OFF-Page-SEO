"""Move 4 stranded constants into backend/modules/common.py."""
import ast, pathlib

NAMES = ["FORUM_DOMAINS", "PODCAST_VIDEO_DOMAINS", "STALE_INDICATORS", "TOXIC_TLD_KEYWORDS"]
MODS = ["llm", "pr", "kg", "technical", "risk"]

# extract exact source from .bak
bak_lines = pathlib.Path("backend/api/analysis.py.bak").read_text(encoding="utf-8", errors="replace").splitlines()
bak_tree = ast.parse("\n".join(bak_lines))
blocks = {}
for node in bak_tree.body:
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id in NAMES:
                seg = ast.get_source_segment("\n".join(bak_lines), node)
                blocks[t.id] = seg
assert set(blocks) == set(NAMES), set(NAMES) - set(blocks)
print("extracted:", list(blocks))

# remove from domain modules (whole top-level statement)
for m in MODS:
    p = pathlib.Path(f"backend/modules/{m}.py")
    tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
    kill = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in NAMES:
                    kill.update(range(node.lineno - 1, (node.end_lineno or node.lineno)))
    if kill:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        p.write_text("".join(l for i, l in enumerate(lines) if i not in kill), encoding="utf-8")
        print(m, "removed lines", sorted(kill)[:4])

# append to common.py (+ extend __all__)
c = pathlib.Path("backend/modules/common.py")
src = c.read_text(encoding="utf-8", errors="replace")
add = "\n\n# Shared signal lexicons (moved here in monolith split; used across domain modules).\n" + "\n".join(blocks[n] for n in NAMES) + "\n"
import re as _re
src = _re.sub(r"\n\n__all__ = \[(?:[^\]]*)\]\n?", "", src)
tree = ast.parse(src)
names = set()
for node in tree.body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        names.add(node.name)
    elif isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name):
                names.add(t.id)
names |= set(NAMES)
names.discard("__all__")
# keep re-exports
for n in ["APIRouter", "HTTPException", "Depends", "BaseModel", "Session", "httpx", "json",
          "os", "re", "math", "asyncio", "datetime", "timezone", "Counter", "parse_qs",
          "urlparse", "BeautifulSoup", "get_db", "Brand", "BrandMention", "Backlink",
          "RAGCitation", "VectorDistance", "KnowledgeGraphTriple", "ConsensusScore",
          "Alert", "Competitor", "Executive", "PassageAttention", "VerifiedData",
          "UnavailableData", "is_verified", "is_unavailable", "verified", "unavailable",
          "ahrefs", "moz", "majestic", "serpapi", "openai", "anthropic", "perplexity",
          "newsapi", "google_kg", "search_web", "verify_url", "search_news", "free_apis", "settings"]:
    names.add(n)
block = "\n\n__all__ = [\n" + "\n".join(f'    "{n}",' for n in sorted(names)) + "\n]\n"
c.write_text(src + add + block, encoding="utf-8")
print("common.py updated")
