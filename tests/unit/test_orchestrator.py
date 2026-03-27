import pytest
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

from cherry_bomb.agent.orchestrator import AgentOrchestrator, AgentResponse
from cherry_bomb.models.schemas import ToolDefinition, ToolParameters, ToolParameterProperty, ToolResult
from cherry_bomb.plugins.base import ToolPlugin
from cherry_bomb.plugins.registry import PluginRegistry


# --- Helpers ---


@dataclass
class FakeTextBlock:
    type: str = "text"
    text: str = ""


@dataclass
class FakeToolUseBlock:
    type: str = "tool_use"
    name: str = ""
    id: str = ""
    input: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.input is None:
            self.input = {}


@dataclass
class FakeResponse:
    content: list[Any] | None = None
    stop_reason: str = "end_turn"

    def __post_init__(self) -> None:
        if self.content is None:
            self.content = []


class FakePlugin(ToolPlugin):
    @property
    def name(self) -> str:
        return "fake"

    @property
    def description(self) -> str:
        return "Fake plugin"

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="fake_read",
                description="Read tool",
                input_schema=ToolParameters(
                    properties={"q": ToolParameterProperty(type="string", description="query")},
                ),
            ),
            ToolDefinition(
                name="fake_write",
                description="Write tool",
                input_schema=ToolParameters(
                    properties={"t": ToolParameterProperty(type="string", description="target")},
                ),
            ),
        ]

    async def execute(self, tool_name: str, parameters: dict[str, Any]) -> ToolResult:
        return ToolResult(tool_use_id="", content=f"result of {tool_name}")

    def read_only_tools(self) -> set[str]:
        return {"fake_read"}


def _make_settings() -> MagicMock:
    settings = MagicMock()
    settings.ANTHROPIC_API_KEY.get_secret_value.return_value = "sk-test-key"
    settings.CLAUDE_MODEL = "claude-sonnet-4-20250514"
    return settings


def _make_orchestrator(registry: PluginRegistry | None = None) -> AgentOrchestrator:
    settings = _make_settings()
    if registry is None:
        registry = PluginRegistry()
        registry.register(FakePlugin())
    return AgentOrchestrator(settings=settings, registry=registry)


# --- Tests ---


class TestAgentResponse:
    def test_has_pending_approvals_false(self) -> None:
        resp = AgentResponse(text="hello", pending_approvals=[], messages=[])
        assert resp.has_pending_approvals is False

    def test_has_pending_approvals_true(self) -> None:
        resp = AgentResponse(
            text="hello",
            pending_approvals=[{"tool_name": "restart", "parameters": {}, "tool_use_id": "t1"}],
            messages=[],
        )
        assert resp.has_pending_approvals is True


class TestAgentOrchestrator:
    @pytest.mark.asyncio()
    async def test_end_turn_response(self) -> None:
        """stop_reason=end_turnの場合、テキストを返して終了する"""
        orchestrator = _make_orchestrator()

        fake_response = FakeResponse(
            content=[FakeTextBlock(text="CPUは正常です。")],
            stop_reason="end_turn",
        )

        with patch.object(orchestrator._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = fake_response
            result = await orchestrator.run("CPUの状態を教えて")

        assert result.text == "CPUは正常です。"
        assert result.has_pending_approvals is False
        assert len(result.messages) >= 2  # user message + assistant content

    @pytest.mark.asyncio()
    async def test_tool_use_read_only(self) -> None:
        """読み取り系ツール呼び出し→結果→end_turnのフロー"""
        orchestrator = _make_orchestrator()

        tool_use_response = FakeResponse(
            content=[
                FakeToolUseBlock(name="fake_read", id="toolu_100", input={"q": "cpu"}),
            ],
            stop_reason="tool_use",
        )
        final_response = FakeResponse(
            content=[FakeTextBlock(text="CPU使用率は30%です。")],
            stop_reason="end_turn",
        )

        with patch.object(orchestrator._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = [tool_use_response, final_response]
            result = await orchestrator.run("CPUのメトリクスを取得して")

        assert result.text == "CPU使用率は30%です。"
        assert result.has_pending_approvals is False
        assert mock_create.call_count == 2

    @pytest.mark.asyncio()
    async def test_tool_use_approval_required(self) -> None:
        """変更系ツール呼び出しでpending_approvalsに追加される"""
        orchestrator = _make_orchestrator()

        tool_use_response = FakeResponse(
            content=[
                FakeToolUseBlock(name="fake_write", id="toolu_200", input={"t": "server-1"}),
            ],
            stop_reason="tool_use",
        )
        final_response = FakeResponse(
            content=[FakeTextBlock(text="承認をお待ちしています。")],
            stop_reason="end_turn",
        )

        with patch.object(orchestrator._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = [tool_use_response, final_response]
            result = await orchestrator.run("サーバーを再起動して")

        assert result.has_pending_approvals is True
        assert len(result.pending_approvals) == 1
        assert result.pending_approvals[0]["tool_name"] == "fake_write"
        assert result.pending_approvals[0]["tool_use_id"] == "toolu_200"

    @pytest.mark.asyncio()
    async def test_max_turns_reached(self) -> None:
        """最大ターン数に達した場合のハンドリング"""
        orchestrator = _make_orchestrator()

        # 常にtool_useを返し続けるレスポンス
        tool_use_response = FakeResponse(
            content=[
                FakeToolUseBlock(name="fake_read", id="toolu_loop", input={"q": "x"}),
            ],
            stop_reason="tool_use",
        )

        with patch.object(orchestrator._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = tool_use_response
            result = await orchestrator.run("無限ループ", max_turns=3)

        assert result.text == "最大ターン数に達しました。"
        assert mock_create.call_count == 3

    @pytest.mark.asyncio()
    async def test_unknown_stop_reason(self) -> None:
        """未知のstop_reasonでも正常に返す"""
        orchestrator = _make_orchestrator()

        fake_response = FakeResponse(
            content=[FakeTextBlock(text="something happened")],
            stop_reason="max_tokens",
        )

        with patch.object(orchestrator._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = fake_response
            result = await orchestrator.run("test")

        assert result.text == "something happened"

    @pytest.mark.asyncio()
    async def test_conversation_history_preserved(self) -> None:
        """会話履歴が正しく引き継がれる"""
        orchestrator = _make_orchestrator()
        history = [
            {"role": "user", "content": "こんにちは"},
            {"role": "assistant", "content": "こんにちは！"},
        ]

        fake_response = FakeResponse(
            content=[FakeTextBlock(text="お手伝いします。")],
            stop_reason="end_turn",
        )

        with patch.object(orchestrator._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = fake_response
            result = await orchestrator.run(
                "サーバーの状態を教えて",
                conversation_history=history,
            )

        # messages には history + user message + assistant content が含まれる
        assert len(result.messages) == 4  # 2 history + 1 new user + 1 assistant
        assert result.messages[0] == {"role": "user", "content": "こんにちは"}
        assert result.messages[1] == {"role": "assistant", "content": "こんにちは！"}
        assert result.messages[2] == {"role": "user", "content": "サーバーの状態を教えて"}

    @pytest.mark.asyncio()
    async def test_no_tools_registered(self) -> None:
        """ツール未登録でも正常にend_turnで返す"""
        empty_registry = PluginRegistry()
        orchestrator = _make_orchestrator(registry=empty_registry)

        fake_response = FakeResponse(
            content=[FakeTextBlock(text="ツールなしで回答します。")],
            stop_reason="end_turn",
        )

        with patch.object(orchestrator._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = fake_response
            result = await orchestrator.run("こんにちは")

        assert result.text == "ツールなしで回答します。"


class TestExtractText:
    def test_single_text_block(self) -> None:
        response = FakeResponse(content=[FakeTextBlock(text="hello")])
        assert AgentOrchestrator._extract_text(response) == "hello"

    def test_multiple_text_blocks(self) -> None:
        response = FakeResponse(
            content=[FakeTextBlock(text="line1"), FakeTextBlock(text="line2")]
        )
        assert AgentOrchestrator._extract_text(response) == "line1\nline2"

    def test_mixed_blocks(self) -> None:
        response = FakeResponse(
            content=[
                FakeTextBlock(text="before tool"),
                FakeToolUseBlock(name="test", id="t1"),
                FakeTextBlock(text="after tool"),
            ]
        )
        assert AgentOrchestrator._extract_text(response) == "before tool\nafter tool"

    def test_no_text_blocks(self) -> None:
        response = FakeResponse(
            content=[FakeToolUseBlock(name="test", id="t1")]
        )
        assert AgentOrchestrator._extract_text(response) == ""
