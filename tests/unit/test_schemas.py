from cherry_bomb.models.schemas import (
    ApprovalStatus,
    ToolDefinition,
    ToolParameterProperty,
    ToolParameters,
    ToolResult,
)


class TestToolParameterProperty:
    def test_basic_property(self) -> None:
        prop = ToolParameterProperty(type="string", description="A test param")
        assert prop.type == "string"
        assert prop.description == "A test param"
        assert prop.enum is None

    def test_property_with_enum(self) -> None:
        prop = ToolParameterProperty(
            type="string", description="Priority", enum=["high", "low"]
        )
        assert prop.enum == ["high", "low"]


class TestToolParameters:
    def test_defaults(self) -> None:
        params = ToolParameters(properties={})
        assert params.type == "object"
        assert params.required == []

    def test_with_properties(self) -> None:
        params = ToolParameters(
            properties={
                "query": ToolParameterProperty(type="string", description="Search query")
            },
            required=["query"],
        )
        assert "query" in params.properties
        assert params.required == ["query"]


class TestToolDefinition:
    def _make_tool(self) -> ToolDefinition:
        return ToolDefinition(
            name="datadog_get_metrics",
            description="Get metrics from Datadog",
            input_schema=ToolParameters(
                properties={
                    "query": ToolParameterProperty(type="string", description="Metric query"),
                    "period": ToolParameterProperty(
                        type="string",
                        description="Time period",
                        enum=["1h", "6h", "24h"],
                    ),
                },
                required=["query"],
            ),
        )

    def test_to_claude_format_structure(self) -> None:
        tool = self._make_tool()
        result = tool.to_claude_format()

        assert result["name"] == "datadog_get_metrics"
        assert result["description"] == "Get metrics from Datadog"
        assert "input_schema" in result

    def test_to_claude_format_input_schema(self) -> None:
        tool = self._make_tool()
        result = tool.to_claude_format()
        schema = result["input_schema"]

        assert schema["type"] == "object"
        assert "query" in schema["properties"]
        assert schema["properties"]["query"]["type"] == "string"
        assert schema["required"] == ["query"]

    def test_to_claude_format_enum(self) -> None:
        tool = self._make_tool()
        result = tool.to_claude_format()
        period = result["input_schema"]["properties"]["period"]

        assert period["enum"] == ["1h", "6h", "24h"]

    def test_to_claude_format_returns_dict(self) -> None:
        tool = self._make_tool()
        result = tool.to_claude_format()
        assert isinstance(result, dict)


class TestToolResult:
    def test_success_result(self) -> None:
        result = ToolResult(
            tool_use_id="toolu_123",
            content='{"status": "ok"}',
        )
        assert result.is_error is False

    def test_error_result(self) -> None:
        result = ToolResult(
            tool_use_id="toolu_456",
            content="Something went wrong",
            is_error=True,
        )
        assert result.is_error is True

    def test_to_claude_format(self) -> None:
        result = ToolResult(
            tool_use_id="toolu_123",
            content='{"metrics": [1, 2, 3]}',
        )
        formatted = result.to_claude_format()

        assert formatted["type"] == "tool_result"
        assert formatted["tool_use_id"] == "toolu_123"
        assert formatted["content"] == '{"metrics": [1, 2, 3]}'
        assert formatted["is_error"] is False

    def test_to_claude_format_error(self) -> None:
        result = ToolResult(
            tool_use_id="toolu_456",
            content="Error occurred",
            is_error=True,
        )
        formatted = result.to_claude_format()
        assert formatted["is_error"] is True


class TestApprovalStatus:
    def test_values(self) -> None:
        assert ApprovalStatus.PENDING == "pending"
        assert ApprovalStatus.APPROVED == "approved"
        assert ApprovalStatus.REJECTED == "rejected"
        assert ApprovalStatus.EXPIRED == "expired"

    def test_is_str(self) -> None:
        assert isinstance(ApprovalStatus.PENDING, str)
