from typing import Any

import pytest

from cherry_bomb.models.schemas import (
    ToolDefinition,
    ToolParameterProperty,
    ToolParameters,
    ToolResult,
)
from cherry_bomb.plugins.base import ToolPlugin


class DummyPlugin(ToolPlugin):
    """テスト用の具象プラグイン"""

    @property
    def name(self) -> str:
        return "dummy"

    @property
    def description(self) -> str:
        return "A dummy plugin for testing"

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="dummy_read",
                description="Read something",
                input_schema=ToolParameters(
                    properties={"id": ToolParameterProperty(type="string", description="ID")},
                    required=["id"],
                ),
            ),
            ToolDefinition(
                name="dummy_write",
                description="Write something",
                input_schema=ToolParameters(
                    properties={
                        "id": ToolParameterProperty(type="string", description="ID"),
                        "value": ToolParameterProperty(type="string", description="Value"),
                    },
                    required=["id", "value"],
                ),
            ),
        ]

    async def execute(self, tool_name: str, parameters: dict[str, Any]) -> ToolResult:
        return ToolResult(
            tool_use_id="",
            content=f"Executed {tool_name}",
        )

    def read_only_tools(self) -> set[str]:
        return {"dummy_read"}


class TestToolPluginABC:
    def test_cannot_instantiate_abc(self) -> None:
        with pytest.raises(TypeError):
            ToolPlugin()  # type: ignore[abstract]

    def test_concrete_plugin_properties(self) -> None:
        plugin = DummyPlugin()
        assert plugin.name == "dummy"
        assert plugin.description == "A dummy plugin for testing"

    def test_get_tools(self) -> None:
        plugin = DummyPlugin()
        tools = plugin.get_tools()
        assert len(tools) == 2
        assert tools[0].name == "dummy_read"
        assert tools[1].name == "dummy_write"

    def test_execute(self) -> None:
        import asyncio

        plugin = DummyPlugin()
        result = asyncio.run(plugin.execute("dummy_read", {"id": "123"}))
        assert result.content == "Executed dummy_read"
        assert result.is_error is False

    def test_requires_approval_read_only(self) -> None:
        plugin = DummyPlugin()
        assert plugin.requires_approval("dummy_read") is False

    def test_requires_approval_write(self) -> None:
        plugin = DummyPlugin()
        assert plugin.requires_approval("dummy_write") is True

    def test_requires_approval_unknown_tool(self) -> None:
        plugin = DummyPlugin()
        # 未知のツールは安全側に倒してTrueを返す
        assert plugin.requires_approval("unknown_tool") is True

    def test_default_read_only_tools(self) -> None:
        """read_only_toolsをオーバーライドしないプラグインはデフォルト空セット"""

        class MinimalPlugin(ToolPlugin):
            @property
            def name(self) -> str:
                return "minimal"

            @property
            def description(self) -> str:
                return "Minimal"

            def get_tools(self) -> list[ToolDefinition]:
                return []

            async def execute(self, tool_name: str, parameters: dict[str, Any]) -> ToolResult:
                return ToolResult(tool_use_id="", content="")

        plugin = MinimalPlugin()
        assert plugin.read_only_tools() == set()
        # デフォルトではすべて承認が必要
        assert plugin.requires_approval("any_tool") is True
