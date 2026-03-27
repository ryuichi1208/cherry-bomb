"""DecisionPlugin テスト"""

from datetime import UTC, datetime

import pytest

from cherry_bomb.decision.store import SQLiteDecisionStore
from cherry_bomb.models.schemas import DecisionRecord, TurnAction, TurnRecord
from cherry_bomb.plugins.builtin.decision import DecisionPlugin


@pytest.fixture
async def store() -> SQLiteDecisionStore:
    s = SQLiteDecisionStore(db_path=":memory:")
    await s.initialize()
    return s


@pytest.fixture
def plugin(store: SQLiteDecisionStore) -> DecisionPlugin:
    return DecisionPlugin(store=store)


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
            ),
            TurnRecord(
                turn_number=1,
                reasoning="CPU使用率は正常範囲内です",
                action=TurnAction.FINAL_ANSWER,
            ),
        ],
        final_answer="CPU使用率は正常範囲内です",
    )


class TestDecisionPlugin:
    def test_name(self, plugin: DecisionPlugin) -> None:
        assert plugin.name == "decision"

    def test_get_tools(self, plugin: DecisionPlugin) -> None:
        tools = plugin.get_tools()
        names = {t.name for t in tools}
        assert "decision_search" in names
        assert "decision_get" in names

    def test_all_tools_are_read_only(self, plugin: DecisionPlugin) -> None:
        tool_names = {t.name for t in plugin.get_tools()}
        read_only = plugin.read_only_tools()
        assert tool_names == read_only

    async def test_decision_search(self, plugin: DecisionPlugin, store: SQLiteDecisionStore) -> None:
        await store.save(_make_record(session_id="s1", user_message="CPUの状態を教えて"))
        await store.save(_make_record(session_id="s2", user_message="メモリ使用量は？"))

        result = await plugin.execute("decision_search", {"query": "CPU"})
        assert not result.is_error
        assert "s1" in result.content
        assert "CPU" in result.content

    async def test_decision_get(self, plugin: DecisionPlugin, store: SQLiteDecisionStore) -> None:
        await store.save(_make_record(session_id="sess-001"))

        result = await plugin.execute("decision_get", {"session_id": "sess-001"})
        assert not result.is_error
        assert "sess-001" in result.content
        assert "datadog_query_metrics" in result.content

    async def test_decision_get_not_found(self, plugin: DecisionPlugin) -> None:
        result = await plugin.execute("decision_get", {"session_id": "nonexistent"})
        assert not result.is_error
        assert "見つかりません" in result.content

    async def test_decision_search_no_results(self, plugin: DecisionPlugin) -> None:
        result = await plugin.execute("decision_search", {"query": "kubernetes"})
        assert not result.is_error
        assert "見つかりません" in result.content

    async def test_unknown_tool(self, plugin: DecisionPlugin) -> None:
        result = await plugin.execute("unknown_tool", {})
        assert result.is_error
