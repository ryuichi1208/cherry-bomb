"""cherry-bomb MCP サーバーのエントリポイント

Claude Code から利用する場合:
  uv run python -m cherry_bomb.interfaces.mcp.run
"""

from __future__ import annotations

import asyncio
import sys

from cherry_bomb.decision.store import SQLiteDecisionStore
from cherry_bomb.interfaces.mcp.server import create_mcp_server


async def _init_store(db_path: str) -> SQLiteDecisionStore:
    store = SQLiteDecisionStore(db_path=db_path)
    await store.initialize()
    return store


def main() -> None:
    db_path = sys.argv[1] if len(sys.argv) > 1 else "data/decisions.db"
    store = asyncio.run(_init_store(db_path))
    mcp = create_mcp_server(store)
    mcp.run()


if __name__ == "__main__":
    main()
