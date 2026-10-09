#!/usr/bin/env python3
"""test_mcp_server.py — uji handshake MCP: initialize, daftar tool, panggil tool gratis."""
import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PY = "/home/ubuntu/prpo_ai/venv/bin/python"
SRV = "/home/ubuntu/prpo_ai/dist/xh_agent/mcp_server.py"


async def main() -> None:
    params = StdioServerParameters(command=PY, args=[SRV])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            init = await s.initialize()
            print("server:", init.serverInfo.name if init.serverInfo else "?")
            tools = await s.list_tools()
            names = [t.name for t in tools.tools]
            print("tools terdaftar:", names)
            r = await s.call_tool("xh_quote", {"url": "https://xhagents.xyz/api/x402-trust"})
            txt = "".join(c.text for c in r.content if hasattr(c, "text"))
            print("xh_quote ->", txt[:320].replace("\n", " "))
            r2 = await s.call_tool("xh_provenance", {})
            t2 = "".join(c.text for c in r2.content if hasattr(c, "text"))
            print("xh_provenance ->", t2[:200].replace("\n", " "))
            r3 = await s.call_tool("xh_trust_score", {"url": "https://example.com"})
            t3 = "".join(c.text for c in r3.content if hasattr(c, "text"))
            print("xh_trust_score (tanpa kunci) ->", t3[:160].replace("\n", " "))


if __name__ == "__main__":
    try:
        asyncio.run(asyncio.wait_for(main(), timeout=120))
    except Exception as e:  # noqa: BLE001
        print("GAGAL:", type(e).__name__, e)
        sys.exit(1)
