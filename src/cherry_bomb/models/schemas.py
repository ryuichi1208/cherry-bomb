from datetime import datetime
from enum import StrEnum
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


class ApprovalStatus(StrEnum):
    """承認ステータス"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class TurnAction(StrEnum):
    """エージェントのターンアクション種別"""

    TOOL_CALL = "tool_call"
    FINAL_ANSWER = "final_answer"
    APPROVAL_WAIT = "approval_wait"
    MAX_TURNS = "max_turns"


class TurnRecord(BaseModel):
    """1ターン内の意思決定記録"""

    turn_number: int
    reasoning: str
    action: TurnAction
    tool_name: str | None = None
    tool_parameters: dict[str, Any] = Field(default_factory=dict)
    tool_result_summary: str = ""
    approval_required: bool = False


class DecisionRecord(BaseModel):
    """エージェントの1セッション内の意思決定記録"""

    session_id: str
    timestamp: datetime
    user_message: str
    channel: str = ""
    user_id: str = ""
    turns: list[TurnRecord] = Field(default_factory=list)
    final_answer: str = ""
