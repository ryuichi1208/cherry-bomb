from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cherry_bomb.models.schemas import ToolDefinition, ToolResult


class ToolPlugin(ABC):
    """SREツールプラグインの基底クラス"""

    @property
    @abstractmethod
    def name(self) -> str:
        """プラグイン名（例: "datadog"）"""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """プラグインの説明"""
        ...

    @abstractmethod
    def get_tools(self) -> list[ToolDefinition]:
        """Claude Tool Use形式のツール定義を返す"""
        ...

    @abstractmethod
    async def execute(self, tool_name: str, parameters: dict[str, Any]) -> ToolResult:
        """ツールを実行する。tool_use_idはorchestrator側で設定するため、ここでは空文字で返して良い"""
        ...

    def requires_approval(self, tool_name: str) -> bool:
        """変更系操作はTrue、読み取り系はFalse。デフォルトはTrue（安全側に倒す）"""
        return tool_name not in self.read_only_tools()

    def read_only_tools(self) -> set[str]:
        """承認不要の読み取り系ツール名のセット。サブクラスでオーバーライドする"""
        return set()
