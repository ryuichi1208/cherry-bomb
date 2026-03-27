"""Claude API Tool Useオーケストレーション"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import anthropic
import structlog

from cherry_bomb.agent.prompts import build_system_prompt
from cherry_bomb.agent.tool_router import ApprovalRequiredError, ToolRouter
from cherry_bomb.models.schemas import DecisionRecord, TurnAction, TurnRecord

if TYPE_CHECKING:
    from cherry_bomb.config import Settings
    from cherry_bomb.decision.store import DecisionStore
    from cherry_bomb.plugins.registry import PluginRegistry

logger = structlog.get_logger()


class AgentOrchestrator:
    """Claude API Tool Useループを管理するオーケストレーター"""

    def __init__(
        self,
        settings: Settings,
        registry: PluginRegistry,
        decision_store: DecisionStore | None = None,
    ) -> None:
        self._settings = settings
        self._registry = registry
        self._tool_router = ToolRouter(registry)
        self._decision_store = decision_store
        self._client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY.get_secret_value())

    async def run(
        self,
        user_message: str,
        conversation_history: list[dict[str, Any]] | None = None,
        additional_context: str | None = None,
        max_turns: int = 10,
    ) -> AgentResponse:
        """エージェントループを実行する。

        Args:
            user_message: ユーザーからのメッセージ
            conversation_history: 過去の会話履歴
            additional_context: 追加コンテキスト
            max_turns: 最大ターン数（無限ループ防止）

        Returns:
            AgentResponse
        """
        messages: list[dict[str, Any]] = list(conversation_history or [])
        messages.append({"role": "user", "content": user_message})

        system_prompt = build_system_prompt(additional_context)
        tools = self._registry.get_claude_tools()
        pending_approvals: list[dict[str, Any]] = []

        decision = DecisionRecord(
            session_id=str(uuid4()),
            timestamp=datetime.now(UTC),
            user_message=user_message,
        )

        for turn in range(max_turns):
            logger.info("agent_turn", turn=turn, message_count=len(messages))

            response = await self._client.messages.create(
                model=self._settings.CLAUDE_MODEL,
                system=system_prompt,
                messages=messages,  # type: ignore[arg-type]
                tools=tools if tools else anthropic.NOT_GIVEN,  # type: ignore[arg-type]
                max_tokens=4096,
            )

            if response.stop_reason == "end_turn":
                text = self._extract_text(response)
                decision.final_answer = text
                decision.turns.append(
                    TurnRecord(
                        turn_number=turn,
                        reasoning=text,
                        action=TurnAction.FINAL_ANSWER,
                    )
                )
                await self._save_decision(decision)
                return AgentResponse(
                    text=text,
                    pending_approvals=pending_approvals,
                    messages=messages + [{"role": "assistant", "content": response.content}],
                )

            if response.stop_reason == "tool_use":
                tool_results: list[dict[str, Any]] = []
                assistant_content = response.content
                reasoning = self._extract_text(response)

                for block in response.content:
                    if block.type == "tool_use":
                        try:
                            result = await self._tool_router.route(
                                tool_name=block.name,
                                tool_use_id=block.id,
                                parameters=block.input,
                            )
                            tool_results.append(result.to_claude_format())
                            decision.turns.append(
                                TurnRecord(
                                    turn_number=turn,
                                    reasoning=reasoning,
                                    action=TurnAction.TOOL_CALL,
                                    tool_name=block.name,
                                    tool_parameters=block.input or {},
                                    tool_result_summary=result.content[:500],
                                )
                            )
                        except ApprovalRequiredError as e:
                            pending_approvals.append(
                                {
                                    "tool_name": e.tool_name,
                                    "parameters": e.parameters,
                                    "tool_use_id": block.id,
                                }
                            )
                            tool_results.append(
                                {
                                    "type": "tool_result",
                                    "tool_use_id": block.id,
                                    "content": f"\u23f3 {e.tool_name} は承認待ちです。承認されるまでお待ちください。",
                                }
                            )
                            decision.turns.append(
                                TurnRecord(
                                    turn_number=turn,
                                    reasoning=reasoning,
                                    action=TurnAction.APPROVAL_WAIT,
                                    tool_name=e.tool_name,
                                    tool_parameters=e.parameters,
                                    approval_required=True,
                                )
                            )

                messages.append({"role": "assistant", "content": assistant_content})
                messages.append({"role": "user", "content": tool_results})
            else:
                # Unknown stop reason
                text = self._extract_text(response)
                await self._save_decision(decision)
                return AgentResponse(
                    text=text,
                    pending_approvals=pending_approvals,
                    messages=messages,
                )

        logger.warning("max_turns_reached", max_turns=max_turns)
        decision.turns.append(
            TurnRecord(
                turn_number=max_turns - 1,
                reasoning="最大ターン数に達しました。",
                action=TurnAction.MAX_TURNS,
            )
        )
        await self._save_decision(decision)
        return AgentResponse(
            text="最大ターン数に達しました。",
            pending_approvals=pending_approvals,
            messages=messages,
        )

    async def _save_decision(self, record: DecisionRecord) -> None:
        if self._decision_store is not None:
            try:
                await self._decision_store.save(record)
            except Exception:
                logger.exception("decision_save_failed", session_id=record.session_id)

    @staticmethod
    def _extract_text(response: Any) -> str:
        """レスポンスからテキストブロックを抽出する"""
        texts: list[str] = []
        for block in response.content:
            if hasattr(block, "text"):
                texts.append(block.text)
        return "\n".join(texts)


class AgentResponse:
    """エージェントの応答"""

    def __init__(
        self,
        text: str,
        pending_approvals: list[dict[str, Any]],
        messages: list[dict[str, Any]],
    ) -> None:
        self.text = text
        self.pending_approvals = pending_approvals
        self.messages = messages

    @property
    def has_pending_approvals(self) -> bool:
        return len(self.pending_approvals) > 0
