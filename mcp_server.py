"""MCP server — pipe engine data to LLMs (Claude / Cursor).

Exposes offpage_audit, kg_check, pr_hooks as MCP tools.
Run:  py mcp_server.py   (uses fastmcp when installed, else stdio JSON fallback)

Real-data-only: tools call the live engine; unkeyed paths return honest
unavailable states identical to the REST API.
"""

from __future__ import annotations

import asyncio
import json
import sys

TOOLS = ["offpage_audit", "kg_check", "pr_hooks", "bot_governance", "prompt_tracking"]


async def offpage_audit(brand_id: int) -> dict:
    from backend.api.analysis import get_analysis_results  # noqa
    import os
    path = f"data/analysis_results/{brand_id}_latest.json"
    if not os.path.exists(path):
        return {"status": "no_results", "hint": "POST /api/v1/analysis/run first."}
    return json.load(open(path, encoding="utf-8", errors="replace"))


async def kg_check(brand_id: int) -> dict:
    from backend.api.kg_ops import kg_chain
    return await kg_chain(brand_id)


async def pr_hooks(brand_id: int) -> dict:
    import os
    path = f"data/analysis_results/{brand_id}_latest.json"
    if not os.path.exists(path):
        return {"status": "no_results"}
    data = json.load(open(path, encoding="utf-8", errors="replace"))
    mods = data.get("modules", {})
    return mods.get("pr_hooks", {"status": "missing"})


async def bot_governance(brand_id: int) -> dict:
    from backend.api.bot_governance import bot_audit
    return await bot_audit(brand_id)


async def prompt_tracking(brand_id: int) -> dict:
    from backend.api.prompt_tracking import history
    return await history(brand_id)


_HANDLERS = {"offpage_audit": offpage_audit, "kg_check": kg_check,
             "pr_hooks": pr_hooks, "bot_governance": bot_governance,
             "prompt_tracking": prompt_tracking}


def _try_fastmcp():
    try:
        from fastmcp import FastMCP  # type: ignore
        mcp = FastMCP("offpage-seo")

        @mcp.tool()
        async def offpage_audit_tool(brand_id: int) -> dict:
            return await offpage_audit(brand_id)

        @mcp.tool()
        async def kg_check_tool(brand_id: int) -> dict:
            return await kg_check(brand_id)

        @mcp.tool()
        async def pr_hooks_tool(brand_id: int) -> dict:
            return await pr_hooks(brand_id)

        return mcp
    except Exception:
        return None


async def _stdio_loop():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            name = req.get("tool")
            args = req.get("args", {})
            fn = _HANDLERS.get(name)
            if not fn:
                print(json.dumps({"error": f"unknown tool {name}", "tools": TOOLS}), flush=True)
                continue
            print(json.dumps(await fn(**args), default=str)[:20000], flush=True)
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"error": str(e)[:300]}), flush=True)


if __name__ == "__main__":
    mcp = _try_fastmcp()
    if mcp is not None:
        mcp.run()
    else:
        print(json.dumps({"mcp": "stdio-fallback", "tools": TOOLS}), flush=True)
        asyncio.run(_stdio_loop())
