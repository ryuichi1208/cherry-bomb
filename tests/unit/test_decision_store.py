"""DecisionStore テスト"""

from datetime import UTC, datetime

import pytest

from cherry_bomb.decision.store import SQLiteDecisionStore
from cherry_bomb.models.schemas import DecisionRecord, TurnAction, TurnRecord


@pytest.fixture
async def store() -> SQLiteDecisionStore:
    s = SQLiteDecisionStore(db_path=":memory:")
    await s.initialize()
    return s


def _make_record(
    session_id: str = "sess-001",
    user_message: str = "CPUの状態を教えて",
    **kwargs: object,
) -> DecisionRecord:
    return DecisionRecord(
        session_id=session_id,
        timestamp=datetime(2026, 3, 27, 10, 0, 0, tzinfo=UTC),
        user_message=user_message,
        channel="C123",
        user_id="U456",
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
        **kwargs,  # type: ignore[arg-type]
    )


class TestSQLiteDecisionStore:
    async def test_save_and_get(self, store: SQLiteDecisionStore) -> None:
        record = _make_record()
        await store.save(record)

        result = await store.get("sess-001")
        assert result is not None
        assert result.session_id == "sess-001"
        assert result.user_message == "CPUの状態を教えて"
        assert len(result.turns) == 2
        assert result.turns[0].tool_name == "datadog_query_metrics"
        assert result.final_answer == "CPU使用率は正常範囲内です"

    async def test_get_nonexistent(self, store: SQLiteDecisionStore) -> None:
        result = await store.get("nonexistent")
        assert result is None

    async def test_search_by_user_message(self, store: SQLiteDecisionStore) -> None:
        await store.save(_make_record(session_id="s1", user_message="CPUの状態を教えて"))
        await store.save(
            DecisionRecord(
                session_id="s2",
                timestamp=datetime(2026, 3, 27, 11, 0, 0, tzinfo=UTC),
                user_message="メモリ使用量は？",
                turns=[
                    TurnRecord(
                        turn_number=0,
                        reasoning="メモリを確認します",
                        action=TurnAction.TOOL_CALL,
                        tool_name="datadog_query_metrics",
                        tool_parameters={"query": "avg:system.mem.used{*}"},
                        tool_result_summary="Memory: 70%",
                    ),
                ],
                final_answer="メモリ使用量は70%です",
            )
        )

        results = await store.search("CPU")
        assert len(results) == 1
        assert results[0].session_id == "s1"

    async def test_search_by_reasoning(self, store: SQLiteDecisionStore) -> None:
        await store.save(_make_record(session_id="s1"))

        results = await store.search("Datadog")
        assert len(results) == 1
        assert results[0].session_id == "s1"

    async def test_search_no_results(self, store: SQLiteDecisionStore) -> None:
        await store.save(_make_record())
        results = await store.search("kubernetes")
        assert len(results) == 0

    async def test_search_limit(self, store: SQLiteDecisionStore) -> None:
        for i in range(5):
            await store.save(_make_record(session_id=f"s{i}", user_message=f"CPU質問{i}"))

        results = await store.search("CPU", limit=3)
        assert len(results) == 3

    async def test_save_overwrites_existing(self, store: SQLiteDecisionStore) -> None:
        await store.save(_make_record(session_id="s1"))
        await store.save(
            _make_record(session_id="s1", user_message="更新されたメッセージ")
        )

        result = await store.get("s1")
        assert result is not None
        assert result.user_message == "更新されたメッセージ"
