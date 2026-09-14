"""Fix star-export bug: `from .common import *` skips underscore names.

Appends an explicit __all__ to backend/modules/common.py covering every
module-level def/class/constant so analysis.py + domain modules keep working.
"""
import ast, pathlib

p = pathlib.Path("backend/modules/common.py")
src = p.read_text(encoding="utf-8", errors="replace")
tree = ast.parse(src)
names = []
for node in tree.body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        names.append(node.name)
    elif isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name):
                names.append(t.id)
    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        names.append(node.target.id)
# Re-exported imports that analysis.py + domain modules rely on via star import.
REEXPORTS = ["APIRouter", "HTTPException", "Depends", "BaseModel", "Session",
             "httpx", "json", "os", "re", "math", "asyncio", "datetime",
             "timezone", "Counter", "parse_qs", "urlparse", "BeautifulSoup",
             "get_db", "Brand", "BrandMention", "Backlink", "RAGCitation",
             "VectorDistance", "KnowledgeGraphTriple", "ConsensusScore",
             "Alert", "Competitor", "Executive", "PassageAttention",
             "VerifiedData", "UnavailableData", "is_verified", "is_unavailable",
             "verified", "unavailable", "ahrefs", "moz", "majestic", "serpapi",
             "openai", "anthropic", "perplexity", "newsapi", "google_kg",
             "search_web", "verify_url", "search_news", "free_apis", "settings"]
names = sorted(set(names) | set(REEXPORTS))
block = "\n\n__all__ = [\n" + "\n".join(f'    "{n}",' for n in names if n != "__all__") + "\n]\n"
import re as _re
src = _re.sub(r"\n\n__all__ = \[(?:[^\]]*)\]\n?", "", src)
p.write_text(src + block, encoding="utf-8")
print(f"exported {len(names)} names")
print([n for n in names if n.startswith("_")][:20])
