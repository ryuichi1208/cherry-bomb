"""Tests for FastAPI application entry point"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from cherry_bomb.config import Settings
from cherry_bomb.main import create_app, create_slack_app


@pytest.fixture
def mock_settings():
    """テスト用の Settings を作成する"""
    return Settings(
        ANTHROPIC_API_KEY=SecretStr("test-api-key"),
        SLACK_BOT_TOKEN=SecretStr("xoxb-test-token"),
        SLACK_SIGNING_SECRET=SecretStr("test-signing-secret"),
    )


class TestCreateSlackApp:
    def test_creates_slack_app(self, mock_settings):
        """Slack Bolt AsyncApp が作成されること"""
        app = create_slack_app(mock_settings)
        # AsyncApp のインスタンスであること（型チェックは import の都合上シンプルに）
        assert app is not None


class TestCreateApp:
    @patch("cherry_bomb.main.create_slack_app")
    @patch("cherry_bomb.main.AsyncSlackRequestHandler")
    @patch("cherry_bomb.main.AgentOrchestrator")
    def test_creates_fastapi_app(self, mock_orch_cls, mock_handler_cls, mock_create_slack, mock_settings):
        """FastAPI app が正常に作成されること"""
        mock_create_slack.return_value = MagicMock()
        mock_handler_cls.return_value = MagicMock()

        app = create_app(settings=mock_settings)

        assert app.title == "cherry-bomb"
        assert app.version == "0.1.0"

    @patch("cherry_bomb.main.create_slack_app")
    @patch("cherry_bomb.main.AsyncSlackRequestHandler")
    @patch("cherry_bomb.main.AgentOrchestrator")
    def test_health_endpoint(self, mock_orch_cls, mock_handler_cls, mock_create_slack, mock_settings):
        """/health エンドポイントが正しく動作すること"""
        mock_create_slack.return_value = MagicMock()
        mock_handler_cls.return_value = MagicMock()

        app = create_app(settings=mock_settings)
        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    @patch("cherry_bomb.main.create_slack_app")
    @patch("cherry_bomb.main.AsyncSlackRequestHandler")
    @patch("cherry_bomb.main.AgentOrchestrator")
    def test_slack_events_endpoint_exists(self, mock_orch_cls, mock_handler_cls, mock_create_slack, mock_settings):
        """/slack/events エンドポイントが登録されていること"""
        mock_create_slack.return_value = MagicMock()
        mock_handler_cls.return_value = MagicMock()

        app = create_app(settings=mock_settings)
        routes = [route.path for route in app.routes]
        assert "/slack/events" in routes

    @patch("cherry_bomb.main.create_slack_app")
    @patch("cherry_bomb.main.AsyncSlackRequestHandler")
    @patch("cherry_bomb.main.AgentOrchestrator")
    def test_registers_slack_handlers(self, mock_orch_cls, mock_handler_cls, mock_create_slack, mock_settings):
        """Slack ハンドラが register_handlers 経由で登録されること"""
        mock_slack_app = MagicMock()
        mock_create_slack.return_value = mock_slack_app
        mock_handler_cls.return_value = MagicMock()

        with patch("cherry_bomb.main.register_handlers") as mock_register:
            app = create_app(settings=mock_settings)
            mock_register.assert_called_once_with(mock_slack_app, mock_orch_cls.return_value)

    @patch("cherry_bomb.main.create_slack_app")
    @patch("cherry_bomb.main.AsyncSlackRequestHandler")
    @patch("cherry_bomb.main.AgentOrchestrator")
    def test_creates_orchestrator_with_settings(self, mock_orch_cls, mock_handler_cls, mock_create_slack, mock_settings):
        """AgentOrchestrator が正しい引数で作成されること"""
        mock_create_slack.return_value = MagicMock()
        mock_handler_cls.return_value = MagicMock()

        app = create_app(settings=mock_settings)

        mock_orch_cls.assert_called_once()
        call_kwargs = mock_orch_cls.call_args
        assert call_kwargs.kwargs["settings"] is mock_settings
