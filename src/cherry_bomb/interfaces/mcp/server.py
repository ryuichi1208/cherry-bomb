"""cherry-bomb MCP サーバー: 意思決定ログを Claude Code から照会可能にする"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.server.fastmcp import FastMCP

if TYPE_CHECKING:
    from cherry_bomb.decision.store import DecisionStore


def create_mcp_server(store: DecisionStore) -> FastMCP:
    """DecisionStore を使って MCP サーバーを構築する"""
    mcp = FastMCP("cherry-bomb")

    @mcp.tool()
    async def decision_search(query: str) -> str:
        """過去のエージェント意思決定ログをキーワードで検索する。

        SREエージェントが過去に行った判断の理由や根拠を調べたいときに使います。
        例: 「CPU」「アラート」「再起動」などのキーワードで検索できます。

        Args:
            query: 検索キーワード
        """
        records = await store.search(query, limit=5)
        if not records:
            return f"「{query}」に一致する意思決定ログは見つかりませんでした。"

        lines: list[str] = [f"「{query}」の検索結果 ({len(records)}件):\n"]
        for r in records:
            lines.append(f"--- セッション: {r.session_id} ---")
            lines.append(f"日時: {r.timestamp.isoformat()}")
            lines.append(f"質問: {r.user_message}")
            lines.append(f"回答: {r.final_answer[:200]}")
            lines.append(f"ターン数: {len(r.turns)}")
            for t in r.turns:
                action_label = t.action.value
                tool_info = f" ({t.tool_name})" if t.tool_name else ""
                lines.append(f"  [{action_label}{tool_info}] {t.reasoning[:150]}")
            lines.append("")
        return "\n".join(lines)

    @mcp.tool()
    async def decision_get(session_id: str) -> str:
        """セッションIDで特定の意思決定ログの詳細を取得する。

        decision_search で見つけたセッションの詳細な推論過程を確認するときに使います。

        Args:
            session_id: セッションID
        """
        record = await store.get(session_id)
        if record is None:
            return f"セッション {session_id} の意思決定ログは見つかりませんでした。"

        lines: list[str] = [
            f"セッション: {record.session_id}",
            f"日時: {record.timestamp.isoformat()}",
            f"質問: {record.user_message}",
            f"最終回答: {record.final_answer}",
            f"\n意思決定プロセス ({len(record.turns)}ターン):",
        ]
        for t in record.turns:
            action_label = t.action.value
            tool_info = f" ({t.tool_name})" if t.tool_name else ""
            lines.append(f"\n  ターン {t.turn_number}: [{action_label}{tool_info}]")
            lines.append(f"  理由: {t.reasoning}")
            if t.tool_parameters:
                lines.append(f"  パラメータ: {t.tool_parameters}")
            if t.tool_result_summary:
                lines.append(f"  結果: {t.tool_result_summary[:300]}")
            if t.approval_required:
                lines.append("  ⚠️ 承認が必要")
        return "\n".join(lines)

    return mcp
