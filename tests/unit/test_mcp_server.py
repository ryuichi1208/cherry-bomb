"""MCP サーバーテスト"""

from datetime import UTC, datetime

import pytest

pytest.importorskip("mcp", reason="mcp package not installed")

from mcp.server.fastmcp import FastMCP  # noqa: E402

from cherry_bomb.decision.store import SQLiteDecisionStore  # noqa: E402
from cherry_bomb.interfaces.mcp.server import create_mcp_server  # noqa: E402
from cherry_bomb.models.schemas import DecisionRecord, TurnAction, TurnRecord  # noqa: E402


@pytest.fixture
async def store() -> SQLiteDecisionStore:
    s = SQLiteDecisionStore(db_path=":memory:")
    await s.initialize()
    return s


@pytest.fixture
async def mcp_server(store: SQLiteDecisionStore) -> FastMCP:
    return create_mcp_server(store)


def _make_record(session_id: str = "sess-001", user_message: str = "CPUの状態を教えて") -> DecisionRecord:
    return DecisionRecord(
        session_id=session_id,
        timestamp=datetime(2026, 3, 27, 10, 0, 0, tzinfo=UTC),
        user_message=user_message,
        turns=[
            TurnRecord(
                turn_number=0,
                reasoning="CPU使用率を確認するためDatadogメトリクスを取得します",
                action=TurnAction.TOOL_CALL,
                tool_name="datadog_query_metrics",
                tool_parameters={"query": "avg:system.cpu.user{*}"},
                tool_result_summary="CPU usage: 45%",
            ),
            TurnRecord(
                turn_number=1,
                reasoning="CPU使用率は正常範囲内です",
                action=TurnAction.FINAL_ANSWER,
            ),
        ],
        final_answer="CPU使用率は正常範囲内です",
    )


def _extract_text(result: object) -> str:
    """call_tool の戻り値からテキストを抽出する"""
    # FastMCP.call_tool は (list[TextContent], dict) のタプルを返す
    contents = result[0]  # type: ignore[index]
    return contents[0].text  # type: ignore[union-attr]


class TestCreateMcpServer:
    def test_returns_fastmcp_instance(self, mcp_server: FastMCP) -> None:
        assert isinstance(mcp_server, FastMCP)

    def test_server_name(self, mcp_server: FastMCP) -> None:
        assert mcp_server.name == "cherry-bomb"


class TestMcpTools:
    """FastMCP の直接 API を使ったツールテスト"""

    async def test_tools_are_listed(self, mcp_server: FastMCP) -> None:
        tools = await mcp_server.list_tools()
        names = {t.name for t in tools}
        assert "decision_search" in names
        assert "decision_get" in names

    async def test_decision_search_with_results(self, mcp_server: FastMCP, store: SQLiteDecisionStore) -> None:
        await store.save(_make_record(session_id="s1", user_message="CPUの状態を教えて"))

        result = await mcp_server.call_tool("decision_search", {"query": "CPU"})
        text = _extract_text(result)
        assert "s1" in text
        assert "CPU" in text

    async def test_decision_search_no_results(self, mcp_server: FastMCP, store: SQLiteDecisionStore) -> None:
        result = await mcp_server.call_tool("decision_search", {"query": "nonexistent"})
        text = _extract_text(result)
        assert "見つかりません" in text

    async def test_decision_get_with_result(self, mcp_server: FastMCP, store: SQLiteDecisionStore) -> None:
        await store.save(_make_record(session_id="sess-001"))

        result = await mcp_server.call_tool("decision_get", {"session_id": "sess-001"})
        text = _extract_text(result)
        assert "sess-001" in text
        assert "datadog_query_metrics" in text

    async def test_decision_get_not_found(self, mcp_server: FastMCP, store: SQLiteDecisionStore) -> None:
        result = await mcp_server.call_tool("decision_get", {"session_id": "nonexistent"})
        text = _extract_text(result)
        assert "見つかりません" in text
