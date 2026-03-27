from cherry_bomb.models.schemas import ToolDefinition
from cherry_bomb.plugins.base import ToolPlugin


class ToolNotFoundError(Exception):
    """指定されたツールが見つからない場合のエラー"""

    def __init__(self, tool_name: str) -> None:
        self.tool_name = tool_name
        super().__init__(f"Tool not found: {tool_name}")


class PluginRegistry:
    """プラグインの登録と検索を管理する"""

    def __init__(self) -> None:
        self._plugins: dict[str, ToolPlugin] = {}

    def register(self, plugin: ToolPlugin) -> None:
        """プラグインを登録する"""
        self._plugins[plugin.name] = plugin

    def unregister(self, name: str) -> None:
        """プラグインを登録解除する"""
        self._plugins.pop(name, None)

    def get_plugin(self, name: str) -> ToolPlugin | None:
        """名前でプラグインを取得する"""
        return self._plugins.get(name)

    @property
    def plugins(self) -> dict[str, ToolPlugin]:
        """登録済みプラグイン一覧"""
        return dict(self._plugins)

    def get_claude_tools(self) -> list[dict]:  # type: ignore[type-arg]
        """全プラグインのツール定義をClaude API形式で返す"""
        tools: list[dict] = []  # type: ignore[type-arg]
        for plugin in self._plugins.values():
            for tool_def in plugin.get_tools():
                tools.append(tool_def.to_claude_format())
        return tools

    def resolve_tool(self, tool_name: str) -> tuple[ToolPlugin, bool]:
        """tool_nameからプラグインと承認要否を解決する。
        Returns: (plugin, needs_approval)
        Raises: ToolNotFoundError
        """
        for plugin in self._plugins.values():
            for tool_def in plugin.get_tools():
                if tool_def.name == tool_name:
                    needs_approval = plugin.requires_approval(tool_name)
                    return plugin, needs_approval
        raise ToolNotFoundError(tool_name)
