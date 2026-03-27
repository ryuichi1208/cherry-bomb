"""意思決定ログのデータモデルテスト"""

from datetime import UTC, datetime
from typing import Any

from cherry_bomb.models.schemas import (
    DecisionRecord,
    TurnAction,
    TurnRecord,
)


class TestTurnAction:
    def test_values(self) -> None:
        assert TurnAction.TOOL_CALL == "tool_call"
        assert TurnAction.FINAL_ANSWER == "final_answer"
        assert TurnAction.APPROVAL_WAIT == "approval_wait"
        assert TurnAction.MAX_TURNS == "max_turns"


class TestTurnRecord:
    def test_minimal_creation(self) -> None:
        record = TurnRecord(
            turn_number=0,
            reasoning="CPUメトリクスを確認します",
            action=TurnAction.TOOL_CALL,
        )
        assert record.turn_number == 0
        assert record.reasoning == "CPUメトリクスを確認します"
        assert record.action == TurnAction.TOOL_CALL
        assert record.tool_name is None
        assert record.tool_parameters == {}
        assert record.tool_result_summary == ""
        assert record.approval_required is False

    def test_full_creation(self) -> None:
        record = TurnRecord(
            turn_number=1,
            reasoning="アラートの原因を調査するためログを検索します",
            action=TurnAction.TOOL_CALL,
            tool_name="datadog_search_logs",
            tool_parameters={"query": "error", "limit": 10},
            tool_result_summary="Found 3 error logs...",
            approval_required=False,
        )
        assert record.tool_name == "datadog_search_logs"
        assert record.tool_parameters == {"query": "error", "limit": 10}
        assert record.tool_result_summary == "Found 3 error logs..."

    def test_approval_wait(self) -> None:
        record = TurnRecord(
            turn_number=2,
            reasoning="サービスを再起動する必要があります",
            action=TurnAction.APPROVAL_WAIT,
            tool_name="restart_service",
            tool_parameters={"service": "web-app"},
            approval_required=True,
        )
        assert record.action == TurnAction.APPROVAL_WAIT
        assert record.approval_required is True

    def test_serialization_roundtrip(self) -> None:
        record = TurnRecord(
            turn_number=0,
            reasoning="test",
            action=TurnAction.FINAL_ANSWER,
            tool_name="some_tool",
            tool_parameters={"key": "value"},
        )
        data: dict[str, Any] = record.model_dump()
        restored = TurnRecord.model_validate(data)
        assert restored == record


class TestDecisionRecord:
    def test_minimal_creation(self) -> None:
        record = DecisionRecord(
            session_id="abc-123",
            timestamp=datetime(2026, 3, 27, 10, 0, 0, tzinfo=UTC),
            user_message="CPUの状態を教えて",
        )
        assert record.session_id == "abc-123"
        assert record.user_message == "CPUの状態を教えて"
        assert record.channel == ""
        assert record.user_id == ""
        assert record.turns == []
        assert record.final_answer == ""

    def test_with_turns(self) -> None:
        turn1 = TurnRecord(
            turn_number=0,
            reasoning="メトリクスを確認します",
            action=TurnAction.TOOL_CALL,
            tool_name="datadog_query_metrics",
        )
        turn2 = TurnRecord(
            turn_number=1,
            reasoning="CPU使用率は正常範囲です",
            action=TurnAction.FINAL_ANSWER,
        )
        record = DecisionRecord(
            session_id="abc-123",
            timestamp=datetime(2026, 3, 27, 10, 0, 0, tzinfo=UTC),
            user_message="CPUの状態を教えて",
            channel="C123",
            user_id="U456",
            turns=[turn1, turn2],
            final_answer="CPU使用率は正常範囲です",
        )
        assert len(record.turns) == 2
        assert record.turns[0].tool_name == "datadog_query_metrics"
        assert record.final_answer == "CPU使用率は正常範囲です"

    def test_json_serialization_roundtrip(self) -> None:
        record = DecisionRecord(
            session_id="abc-123",
            timestamp=datetime(2026, 3, 27, 10, 0, 0, tzinfo=UTC),
            user_message="test",
            turns=[
                TurnRecord(
                    turn_number=0,
                    reasoning="reasoning text",
                    action=TurnAction.TOOL_CALL,
                    tool_name="some_tool",
                    tool_parameters={"key": "value"},
                    tool_result_summary="result",
                ),
            ],
            final_answer="answer",
        )
        json_str = record.model_dump_json()
        restored = DecisionRecord.model_validate_json(json_str)
        assert restored == record
