from typing import Any
from unittest.mock import AsyncMock

import pytest

from cherry_bomb.agent.tool_router import ApprovalRequiredError, ToolRouter
from cherry_bomb.models.schemas import ToolDefinition, ToolParameterProperty, ToolParameters, ToolResult
from cherry_bomb.plugins.base import ToolPlugin
from cherry_bomb.plugins.registry import PluginRegistry, ToolNotFoundError


class FakePlugin(ToolPlugin):
    """テスト用のフェイクプラグイン"""

    @property
    def name(self) -> str:
        return "fake"

    @property
    def description(self) -> str:
        return "Fake plugin for testing"

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="fake_read",
                description="Read-only tool",
                input_schema=ToolParameters(
                    properties={"query": ToolParameterProperty(type="string", description="query")},
                    required=["query"],
                ),
            ),
            ToolDefinition(
                name="fake_write",
                description="Write tool (needs approval)",
                input_schema=ToolParameters(
                    properties={"target": ToolParameterProperty(type="string", description="target")},
                    required=["target"],
                ),
            ),
        ]

    async def execute(self, tool_name: str, parameters: dict[str, Any]) -> ToolResult:
        return ToolResult(
            tool_use_id="",
            content=f"executed {tool_name} with {parameters}",
        )

    def read_only_tools(self) -> set[str]:
        return {"fake_read"}


@pytest.fixture()
def registry() -> PluginRegistry:
    reg = PluginRegistry()
    reg.register(FakePlugin())
    return reg


@pytest.fixture()
def router(registry: PluginRegistry) -> ToolRouter:
    return ToolRouter(registry)


class TestToolRouter:
    @pytest.mark.asyncio()
    async def test_route_read_only_tool(self, router: ToolRouter) -> None:
        """読み取り系ツールは直接実行される"""
        result = await router.route("fake_read", "toolu_001", {"query": "test"})
        assert result.tool_use_id == "toolu_001"
        assert "executed fake_read" in result.content
        assert result.is_error is False

    @pytest.mark.asyncio()
    async def test_route_write_tool_raises_approval_required(self, router: ToolRouter) -> None:
        """変更系ツールはApprovalRequiredError例外を発生させる"""
        with pytest.raises(ApprovalRequiredError) as exc_info:
            await router.route("fake_write", "toolu_002", {"target": "server-1"})
        assert exc_info.value.tool_name == "fake_write"
        assert exc_info.value.parameters == {"target": "server-1"}

    @pytest.mark.asyncio()
    async def test_route_unknown_tool_raises_not_found(self, router: ToolRouter) -> None:
        """存在しないツール名はToolNotFoundErrorを発生させる"""
        with pytest.raises(ToolNotFoundError):
            await router.route("nonexistent", "toolu_003", {})

    @pytest.mark.asyncio()
    async def test_route_execution_error_returns_error_result(self, registry: PluginRegistry) -> None:
        """ツール実行中のエラーはis_error=TrueのToolResultを返す"""
        plugin = registry.get_plugin("fake")
        assert plugin is not None
        # execute メソッドをモックしてエラーを発生させる
        original_execute = plugin.execute
        plugin.execute = AsyncMock(side_effect=RuntimeError("connection refused"))  # type: ignore[method-assign]

        router = ToolRouter(registry)
        result = await router.route("fake_read", "toolu_004", {"query": "fail"})

        assert result.is_error is True
        assert "Error executing fake_read" in result.content
        assert "connection refused" in result.content
        assert result.tool_use_id == "toolu_004"

        # 元に戻す
        plugin.execute = original_execute  # type: ignore[method-assign]


class TestApprovalRequiredError:
    def test_exception_attributes(self) -> None:
        exc = ApprovalRequiredError("restart_service", {"service": "web"})
        assert exc.tool_name == "restart_service"
        assert exc.parameters == {"service": "web"}
        assert "restart_service" in str(exc)
