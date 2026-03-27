from typing import Any

import pytest

from cherry_bomb.models.schemas import (
    ToolDefinition,
    ToolParameterProperty,
    ToolParameters,
    ToolResult,
)
from cherry_bomb.plugins.base import ToolPlugin
from cherry_bomb.plugins.registry import PluginRegistry, ToolNotFoundError


class FakePlugin(ToolPlugin):
    """テスト用プラグイン"""

    def __init__(self, plugin_name: str = "fake", tools: list[ToolDefinition] | None = None) -> None:
        self._name = plugin_name
        self._tools = tools or []

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"Fake plugin: {self._name}"

    def get_tools(self) -> list[ToolDefinition]:
        return self._tools

    async def execute(self, tool_name: str, parameters: dict[str, Any]) -> ToolResult:
        return ToolResult(tool_use_id="", content="ok")

    def read_only_tools(self) -> set[str]:
        return {"fake_read"}


def _make_tool(name: str) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=f"Tool {name}",
        input_schema=ToolParameters(
            properties={"input": ToolParameterProperty(type="string", description="Input")},
        ),
    )


class TestPluginRegistry:
    def test_register_and_get(self) -> None:
        registry = PluginRegistry()
        plugin = FakePlugin("test")
        registry.register(plugin)

        assert registry.get_plugin("test") is plugin

    def test_get_nonexistent_plugin(self) -> None:
        registry = PluginRegistry()
        assert registry.get_plugin("nonexistent") is None

    def test_unregister(self) -> None:
        registry = PluginRegistry()
        plugin = FakePlugin("test")
        registry.register(plugin)
        registry.unregister("test")

        assert registry.get_plugin("test") is None

    def test_unregister_nonexistent(self) -> None:
        registry = PluginRegistry()
        # 存在しないプラグインのunregisterはエラーにならない
        registry.unregister("nonexistent")

    def test_plugins_property(self) -> None:
        registry = PluginRegistry()
        p1 = FakePlugin("alpha")
        p2 = FakePlugin("beta")
        registry.register(p1)
        registry.register(p2)

        plugins = registry.plugins
        assert len(plugins) == 2
        assert "alpha" in plugins
        assert "beta" in plugins

    def test_plugins_property_returns_copy(self) -> None:
        registry = PluginRegistry()
        registry.register(FakePlugin("test"))
        plugins = registry.plugins
        plugins["injected"] = FakePlugin("injected")  # type: ignore[assignment]
        # 内部状態は変わらない
        assert "injected" not in registry.plugins

    def test_register_overwrites(self) -> None:
        registry = PluginRegistry()
        p1 = FakePlugin("test", tools=[_make_tool("tool_a")])
        p2 = FakePlugin("test", tools=[_make_tool("tool_b")])
        registry.register(p1)
        registry.register(p2)

        assert registry.get_plugin("test") is p2
        assert len(registry.plugins) == 1


class TestGetClaudeTools:
    def test_empty_registry(self) -> None:
        registry = PluginRegistry()
        assert registry.get_claude_tools() == []

    def test_single_plugin(self) -> None:
        registry = PluginRegistry()
        plugin = FakePlugin("dd", tools=[_make_tool("dd_metrics")])
        registry.register(plugin)

        tools = registry.get_claude_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "dd_metrics"

    def test_multiple_plugins(self) -> None:
        registry = PluginRegistry()
        registry.register(FakePlugin("dd", tools=[_make_tool("dd_metrics"), _make_tool("dd_events")]))
        registry.register(FakePlugin("pg", tools=[_make_tool("pg_incidents")]))

        tools = registry.get_claude_tools()
        assert len(tools) == 3
        names = {t["name"] for t in tools}
        assert names == {"dd_metrics", "dd_events", "pg_incidents"}

    def test_tools_have_correct_structure(self) -> None:
        registry = PluginRegistry()
        registry.register(FakePlugin("dd", tools=[_make_tool("dd_metrics")]))

        tools = registry.get_claude_tools()
        tool = tools[0]
        assert "name" in tool
        assert "description" in tool
        assert "input_schema" in tool


class TestResolveTool:
    def test_resolve_existing_tool(self) -> None:
        registry = PluginRegistry()
        plugin = FakePlugin("fake", tools=[_make_tool("fake_read"), _make_tool("fake_write")])
        registry.register(plugin)

        resolved_plugin, needs_approval = registry.resolve_tool("fake_read")
        assert resolved_plugin is plugin
        assert needs_approval is False  # fake_readはread_only_toolsに含まれる

    def test_resolve_write_tool(self) -> None:
        registry = PluginRegistry()
        plugin = FakePlugin("fake", tools=[_make_tool("fake_write")])
        registry.register(plugin)

        resolved_plugin, needs_approval = registry.resolve_tool("fake_write")
        assert resolved_plugin is plugin
        assert needs_approval is True

    def test_resolve_nonexistent_tool(self) -> None:
        registry = PluginRegistry()
        registry.register(FakePlugin("fake", tools=[_make_tool("fake_read")]))

        with pytest.raises(ToolNotFoundError) as exc_info:
            registry.resolve_tool("nonexistent_tool")
        assert exc_info.value.tool_name == "nonexistent_tool"
        assert "nonexistent_tool" in str(exc_info.value)

    def test_resolve_from_multiple_plugins(self) -> None:
        registry = PluginRegistry()
        p1 = FakePlugin("dd", tools=[_make_tool("dd_metrics")])
        p2 = FakePlugin("pg", tools=[_make_tool("pg_incidents")])
        registry.register(p1)
        registry.register(p2)

        plugin, _ = registry.resolve_tool("pg_incidents")
        assert plugin is p2


class TestToolNotFoundError:
    def test_error_message(self) -> None:
        err = ToolNotFoundError("my_tool")
        assert err.tool_name == "my_tool"
        assert str(err) == "Tool not found: my_tool"

    def test_is_exception(self) -> None:
        assert issubclass(ToolNotFoundError, Exception)
