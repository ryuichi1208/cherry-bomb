"""DatadogPluginのユニットテスト"""

import sys
from unittest.mock import MagicMock, patch

import pytest

from cherry_bomb.models.schemas import ToolDefinition
from cherry_bomb.plugins.builtin.datadog import DatadogPlugin


@pytest.fixture
def plugin():
    return DatadogPlugin(api_key="test-api-key", app_key="test-app-key", site="datadoghq.com")


class TestDatadogPluginProperties:
    def test_name(self, plugin):
        assert plugin.name == "datadog"

    def test_description(self, plugin):
        assert "Datadog" in plugin.description
        assert "メトリクス" in plugin.description

    def test_default_site(self):
        p = DatadogPlugin(api_key="k", app_key="a")
        assert p._site == "datadoghq.com"

    def test_custom_site(self):
        p = DatadogPlugin(api_key="k", app_key="a", site="us5.datadoghq.com")
        assert p._site == "us5.datadoghq.com"


class TestGetTools:
    def test_returns_list_of_tool_definitions(self, plugin):
        tools = plugin.get_tools()
        assert isinstance(tools, list)
        assert all(isinstance(t, ToolDefinition) for t in tools)

    def test_returns_four_tools(self, plugin):
        tools = plugin.get_tools()
        assert len(tools) == 4

    def test_tool_names(self, plugin):
        names = {t.name for t in plugin.get_tools()}
        assert names == {
            "datadog_query_metrics",
            "datadog_search_logs",
            "datadog_list_monitors",
            "datadog_get_monitor",
        }

    def test_query_metrics_has_required_params(self, plugin):
        tool = next(t for t in plugin.get_tools() if t.name == "datadog_query_metrics")
        assert set(tool.input_schema.required) == {"query", "from_ts", "to_ts"}

    def test_search_logs_has_required_params(self, plugin):
        tool = next(t for t in plugin.get_tools() if t.name == "datadog_search_logs")
        assert tool.input_schema.required == ["query"]

    def test_list_monitors_no_required_params(self, plugin):
        tool = next(t for t in plugin.get_tools() if t.name == "datadog_list_monitors")
        assert tool.input_schema.required == []

    def test_get_monitor_has_required_params(self, plugin):
        tool = next(t for t in plugin.get_tools() if t.name == "datadog_get_monitor")
        assert tool.input_schema.required == ["monitor_id"]

    def test_list_monitors_status_enum(self, plugin):
        tool = next(t for t in plugin.get_tools() if t.name == "datadog_list_monitors")
        status_prop = tool.input_schema.properties["status"]
        assert status_prop.enum == ["Alert", "Warn", "No Data", "OK"]


class TestReadOnlyTools:
    def test_all_four_tools_are_read_only(self, plugin):
        ro = plugin.read_only_tools()
        assert ro == {
            "datadog_query_metrics",
            "datadog_search_logs",
            "datadog_list_monitors",
            "datadog_get_monitor",
        }

    def test_requires_approval_false_for_all_tools(self, plugin):
        for tool in plugin.get_tools():
            assert plugin.requires_approval(tool.name) is False

    def test_requires_approval_true_for_unknown_tool(self, plugin):
        assert plugin.requires_approval("datadog_delete_monitor") is True


class TestExecute:
    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self, plugin):
        result = await plugin.execute("datadog_unknown", {})
        assert result.is_error is True
        assert "Unknown tool" in result.content

    @pytest.mark.asyncio
    async def test_dispatches_to_query_metrics(self, plugin):
        with patch.object(plugin, "_query_metrics", return_value=MagicMock()) as mock:
            params = {"query": "avg:system.cpu.user{*}", "from_ts": 1000, "to_ts": 2000}
            await plugin.execute("datadog_query_metrics", params)
            mock.assert_called_once_with(params)

    @pytest.mark.asyncio
    async def test_dispatches_to_search_logs(self, plugin):
        with patch.object(plugin, "_search_logs", return_value=MagicMock()) as mock:
            params = {"query": "service:api"}
            await plugin.execute("datadog_search_logs", params)
            mock.assert_called_once_with(params)

    @pytest.mark.asyncio
    async def test_dispatches_to_list_monitors(self, plugin):
        with patch.object(plugin, "_list_monitors", return_value=MagicMock()) as mock:
            params = {}
            await plugin.execute("datadog_list_monitors", params)
            mock.assert_called_once_with(params)

    @pytest.mark.asyncio
    async def test_dispatches_to_get_monitor(self, plugin):
        with patch.object(plugin, "_get_monitor", return_value=MagicMock()) as mock:
            params = {"monitor_id": 12345}
            await plugin.execute("datadog_get_monitor", params)
            mock.assert_called_once_with(params)

    @pytest.mark.asyncio
    async def test_execute_catches_exception(self, plugin):
        with patch.object(plugin, "_query_metrics", side_effect=RuntimeError("boom")):
            result = await plugin.execute("datadog_query_metrics", {"query": "x", "from_ts": 0, "to_ts": 1})
            assert result.is_error is True
            assert "Datadog API error" in result.content
            assert "boom" in result.content


class TestImportError:
    @pytest.mark.asyncio
    async def test_query_metrics_import_error(self, plugin):
        """datadog-api-clientがない場合にImportErrorを適切にハンドルする"""
        with patch.dict(sys.modules, {"datadog_api_client": None}):
            result = await plugin._query_metrics({"query": "avg:system.cpu.user{*}", "from_ts": 1000, "to_ts": 2000})
            assert result.is_error is True
            assert "datadog-api-client" in result.content

    @pytest.mark.asyncio
    async def test_search_logs_import_error(self, plugin):
        with patch.dict(sys.modules, {"datadog_api_client": None}):
            result = await plugin._search_logs({"query": "service:api"})
            assert result.is_error is True
            assert "datadog-api-client" in result.content

    @pytest.mark.asyncio
    async def test_list_monitors_import_error(self, plugin):
        with patch.dict(sys.modules, {"datadog_api_client": None}):
            result = await plugin._list_monitors({})
            assert result.is_error is True
            assert "datadog-api-client" in result.content

    @pytest.mark.asyncio
    async def test_get_monitor_import_error(self, plugin):
        with patch.dict(sys.modules, {"datadog_api_client": None}):
            result = await plugin._get_monitor({"monitor_id": 123})
            assert result.is_error is True
            assert "datadog-api-client" in result.content
