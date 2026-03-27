"""Tests for Slack Bolt event handler"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from cherry_bomb.agent.orchestrator import AgentResponse
from cherry_bomb.interfaces.slack.handler import register_handlers


@pytest.fixture
def mock_orchestrator():
    orch = AsyncMock()
    return orch


@pytest.fixture
def mock_app():
    """AsyncApp のモック。event デコレータで登録されたハンドラを取得できるようにする"""
    app = MagicMock()
    handlers = {}

    def event_decorator(event_type):
        def decorator(func):
            handlers[event_type] = func
            return func

        return decorator

    app.event = event_decorator
    app._handlers = handlers
    return app


@pytest.fixture
def mention_event():
    return {
        "user": "U12345",
        "text": "<@BOTID> help me",
        "channel": "C12345",
        "ts": "1234567890.123456",
    }


class TestHandleMention:
    async def test_successful_response(self, mock_app, mock_orchestrator, mention_event):
        """メンション時に orchestrator を呼び出し、応答を返す"""
        response = AgentResponse(
            text="Here is your answer",
            pending_approvals=[],
            messages=[],
        )
        mock_orchestrator.run.return_value = response

        register_handlers(mock_app, mock_orchestrator)
        handler = mock_app._handlers["app_mention"]

        say = AsyncMock()
        client = AsyncMock()

        await handler(event=mention_event, say=say, client=client)

        mock_orchestrator.run.assert_awaited_once_with(
            user_message="<@BOTID> help me",
            additional_context="Slack channel: C12345, User: <@U12345>",
        )
        say.assert_any_call(text="Here is your answer", thread_ts="1234567890.123456")

    async def test_sends_hourglass_reaction(self, mock_app, mock_orchestrator, mention_event):
        """処理中に砂時計リアクションを追加する"""
        mock_orchestrator.run.return_value = AgentResponse(text="ok", pending_approvals=[], messages=[])

        register_handlers(mock_app, mock_orchestrator)
        handler = mock_app._handlers["app_mention"]

        say = AsyncMock()
        client = AsyncMock()

        await handler(event=mention_event, say=say, client=client)

        client.reactions_add.assert_any_call(
            channel="C12345",
            timestamp="1234567890.123456",
            name="hourglass_flowing_sand",
        )

    async def test_replaces_reaction_on_completion(self, mock_app, mock_orchestrator, mention_event):
        """完了時に砂時計を削除してチェックマークを追加する"""
        mock_orchestrator.run.return_value = AgentResponse(text="done", pending_approvals=[], messages=[])

        register_handlers(mock_app, mock_orchestrator)
        handler = mock_app._handlers["app_mention"]

        say = AsyncMock()
        client = AsyncMock()

        await handler(event=mention_event, say=say, client=client)

        client.reactions_remove.assert_any_call(
            channel="C12345",
            timestamp="1234567890.123456",
            name="hourglass_flowing_sand",
        )
        client.reactions_add.assert_any_call(
            channel="C12345",
            timestamp="1234567890.123456",
            name="white_check_mark",
        )

    async def test_pending_approvals_notification(self, mock_app, mock_orchestrator, mention_event):
        """承認待ちがある場合に通知メッセージを送信する"""
        response = AgentResponse(
            text="Processing",
            pending_approvals=[{"tool_name": "restart_service", "parameters": {}, "tool_use_id": "abc"}],
            messages=[],
        )
        mock_orchestrator.run.return_value = response

        register_handlers(mock_app, mock_orchestrator)
        handler = mock_app._handlers["app_mention"]

        say = AsyncMock()
        client = AsyncMock()

        await handler(event=mention_event, say=say, client=client)

        # メイン応答 + 承認待ち通知 = 2回 say が呼ばれる
        assert say.call_count == 2
        approval_call = say.call_args_list[1]
        assert "restart_service" in approval_call.kwargs["text"]

    async def test_error_handling(self, mock_app, mock_orchestrator, mention_event):
        """orchestrator がエラーを投げた場合にエラーメッセージを返す"""
        mock_orchestrator.run.side_effect = RuntimeError("API error")

        register_handlers(mock_app, mock_orchestrator)
        handler = mock_app._handlers["app_mention"]

        say = AsyncMock()
        client = AsyncMock()

        await handler(event=mention_event, say=say, client=client)

        say.assert_any_call(
            text="エラーが発生しました: API error",
            thread_ts="1234567890.123456",
        )

    async def test_thread_ts_from_thread(self, mock_app, mock_orchestrator):
        """スレッド内メンションの場合は thread_ts を使う"""
        event = {
            "user": "U12345",
            "text": "<@BOTID> help",
            "channel": "C12345",
            "ts": "1111.2222",
            "thread_ts": "9999.0000",
        }
        mock_orchestrator.run.return_value = AgentResponse(text="reply", pending_approvals=[], messages=[])

        register_handlers(mock_app, mock_orchestrator)
        handler = mock_app._handlers["app_mention"]

        say = AsyncMock()
        client = AsyncMock()

        await handler(event=event, say=say, client=client)

        say.assert_any_call(text="reply", thread_ts="9999.0000")

    async def test_reaction_failure_ignored(self, mock_app, mock_orchestrator, mention_event):
        """リアクション追加が失敗しても処理を続行する"""
        mock_orchestrator.run.return_value = AgentResponse(text="ok", pending_approvals=[], messages=[])

        register_handlers(mock_app, mock_orchestrator)
        handler = mock_app._handlers["app_mention"]

        say = AsyncMock()
        client = AsyncMock()
        client.reactions_add.side_effect = Exception("rate limited")

        await handler(event=mention_event, say=say, client=client)

        # say は正常に呼ばれること
        say.assert_any_call(text="ok", thread_ts="1234567890.123456")


class TestHandleMessage:
    async def test_message_handler_registered(self, mock_app, mock_orchestrator):
        """message イベントハンドラが登録される"""
        register_handlers(mock_app, mock_orchestrator)
        assert "message" in mock_app._handlers

    async def test_message_handler_does_nothing(self, mock_app, mock_orchestrator):
        """message ハンドラは何もしない"""
        register_handlers(mock_app, mock_orchestrator)
        handler = mock_app._handlers["message"]
        # 例外を投げないことを確認
        await handler(event={"text": "hello"})
