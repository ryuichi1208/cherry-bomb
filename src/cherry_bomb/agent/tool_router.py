"""Claude API tool_useレスポンスのプラグインへのルーティング"""

from typing import TYPE_CHECKING, Any

import structlog

from cherry_bomb.models.schemas import ToolResult

if TYPE_CHECKING:
    from cherry_bomb.plugins.registry import PluginRegistry

logger = structlog.get_logger()


class ApprovalRequiredError(Exception):
    """承認が必要な操作の場合に発生する例外"""

    def __init__(self, tool_name: str, parameters: dict[str, Any]) -> None:
        self.tool_name = tool_name
        self.parameters = parameters
        super().__init__(f"Approval required for: {tool_name}")


class ToolRouter:
    """tool_useレスポンスをプラグインにルーティングする"""

    def __init__(self, registry: PluginRegistry) -> None:
        self._registry = registry

    async def route(self, tool_name: str, tool_use_id: str, parameters: dict[str, Any]) -> ToolResult:
        """ツール呼び出しをルーティングする。

        読み取り系: 直接実行して結果を返す
        変更系: ApprovalRequiredError例外を発生させる

        Args:
            tool_name: ツール名
            tool_use_id: Claude APIのtool_use_id
            parameters: ツールパラメータ

        Returns:
            ToolResult

        Raises:
            ApprovalRequiredError: 承認が必要な操作の場合
            ToolNotFoundError: ツールが見つからない場合
        """
        plugin, needs_approval = self._registry.resolve_tool(tool_name)

        if needs_approval:
            logger.info("approval_required", tool_name=tool_name, parameters=parameters)
            raise ApprovalRequiredError(tool_name=tool_name, parameters=parameters)

        logger.info("executing_tool", tool_name=tool_name, plugin=plugin.name)
        try:
            result = await plugin.execute(tool_name, parameters)
            result.tool_use_id = tool_use_id
            return result
        except Exception as e:
            logger.error("tool_execution_failed", tool_name=tool_name, error=str(e))
            return ToolResult(
                tool_use_id=tool_use_id,
                content=f"Error executing {tool_name}: {e}",
                is_error=True,
            )
