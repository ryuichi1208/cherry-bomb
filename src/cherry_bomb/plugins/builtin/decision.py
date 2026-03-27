"""過去の意思決定ログを照会するプラグイン"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from cherry_bomb.models.schemas import (
    ToolDefinition,
    ToolParameterProperty,
    ToolParameters,
    ToolResult,
)
from cherry_bomb.plugins.base import ToolPlugin

if TYPE_CHECKING:
    from cherry_bomb.decision.store import DecisionStore


class DecisionPlugin(ToolPlugin):
    """過去の意思決定ログを検索・取得するプラグイン"""

    def __init__(self, store: DecisionStore) -> None:
        self._store = store

    @property
    def name(self) -> str:
        return "decision"

    @property
    def description(self) -> str:
        return "過去の意思決定ログを検索・取得する"

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="decision_search",
                description="過去のエージェント意思決定ログをキーワードで検索する",
                input_schema=ToolParameters(
                    properties={
                        "query": ToolParameterProperty(
                            type="string",
                            description="検索キーワード",
                        ),
                    },
                    required=["query"],
                ),
            ),
            ToolDefinition(
                name="decision_get",
                description="セッションIDで特定の意思決定ログを取得する",
                input_schema=ToolParameters(
                    properties={
                        "session_id": ToolParameterProperty(
                            type="string",
                            description="セッションID",
                        ),
                    },
                    required=["session_id"],
                ),
            ),
        ]

    def read_only_tools(self) -> set[str]:
        return {"decision_search", "decision_get"}

    async def execute(self, tool_name: str, parameters: dict[str, Any]) -> ToolResult:
        if tool_name == "decision_search":
            return await self._search(parameters.get("query", ""))
        if tool_name == "decision_get":
            return await self._get(parameters.get("session_id", ""))
        return ToolResult(tool_use_id="", content=f"Unknown tool: {tool_name}", is_error=True)

    async def _search(self, query: str) -> ToolResult:
        records = await self._store.search(query, limit=5)
        if not records:
            return ToolResult(tool_use_id="", content=f"「{query}」に一致する意思決定ログは見つかりませんでした。")

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
        return ToolResult(tool_use_id="", content="\n".join(lines))

    async def _get(self, session_id: str) -> ToolResult:
        record = await self._store.get(session_id)
        if record is None:
            return ToolResult(
                tool_use_id="",
                content=f"セッション {session_id} の意思決定ログは見つかりませんでした。",
            )

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
        return ToolResult(tool_use_id="", content="\n".join(lines))
