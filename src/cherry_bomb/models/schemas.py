from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ToolParameterProperty(BaseModel):
    """ツールパラメータの個別プロパティ定義"""

    type: str
    description: str
    enum: list[str] | None = None


class ToolParameters(BaseModel):
    """Claude Tool Use形式のパラメータスキーマ"""

    type: str = "object"
    properties: dict[str, ToolParameterProperty]
    required: list[str] = Field(default_factory=list)


class ToolDefinition(BaseModel):
    """Claude API Tool Use形式のツール定義"""

    name: str
    description: str
    input_schema: ToolParameters

    def to_claude_format(self) -> dict[str, Any]:
        """Claude API messages.create() の tools 引数に渡せる形式に変換"""
        return self.model_dump()


class ToolResult(BaseModel):
    """ツール実行結果"""

    tool_use_id: str
    content: str
    is_error: bool = False

    def to_claude_format(self) -> dict[str, Any]:
        """Claude APIのtool_result形式に変換"""
        return {
            "type": "tool_result",
            "tool_use_id": self.tool_use_id,
            "content": self.content,
            "is_error": self.is_error,
        }


class ApprovalStatus(str, Enum):
    """承認ステータス"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
