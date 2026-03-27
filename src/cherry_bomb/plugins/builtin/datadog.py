"""Datadog読み取りプラグイン"""

from typing import Any

import structlog

from cherry_bomb.models.schemas import ToolDefinition, ToolParameterProperty, ToolParameters, ToolResult
from cherry_bomb.plugins.base import ToolPlugin

logger = structlog.get_logger()


class DatadogPlugin(ToolPlugin):
    """Datadogからメトリクス・ログ・モニター情報を取得するプラグイン"""

    def __init__(self, api_key: str, app_key: str, site: str = "datadoghq.com") -> None:
        self._api_key = api_key
        self._app_key = app_key
        self._site = site

    @property
    def name(self) -> str:
        return "datadog"

    @property
    def description(self) -> str:
        return "Datadogからメトリクス、ログ、モニター情報を取得します"

    def read_only_tools(self) -> set[str]:
        return {
            "datadog_query_metrics",
            "datadog_search_logs",
            "datadog_list_monitors",
            "datadog_get_monitor",
        }

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="datadog_query_metrics",
                description="Datadogからメトリクスをクエリして取得する。時系列データを返す。",
                input_schema=ToolParameters(
                    properties={
                        "query": ToolParameterProperty(
                            type="string",
                            description="Datadogメトリクスクエリ（例: 'avg:system.cpu.user{host:web-1}'）",
                        ),
                        "from_ts": ToolParameterProperty(
                            type="integer",
                            description="開始時刻のUnixタイムスタンプ（秒）",
                        ),
                        "to_ts": ToolParameterProperty(
                            type="integer",
                            description="終了時刻のUnixタイムスタンプ（秒）",
                        ),
                    },
                    required=["query", "from_ts", "to_ts"],
                ),
            ),
            ToolDefinition(
                name="datadog_search_logs",
                description="Datadogのログを検索する。",
                input_schema=ToolParameters(
                    properties={
                        "query": ToolParameterProperty(
                            type="string",
                            description="ログ検索クエリ（例: 'service:api status:error'）",
                        ),
                        "from_ts": ToolParameterProperty(
                            type="string",
                            description="開始時刻（ISO 8601形式、例: '2024-01-01T00:00:00Z'）",
                        ),
                        "to_ts": ToolParameterProperty(
                            type="string",
                            description="終了時刻（ISO 8601形式）",
                        ),
                        "limit": ToolParameterProperty(
                            type="integer",
                            description="取得件数の上限（デフォルト: 10, 最大: 100）",
                        ),
                    },
                    required=["query"],
                ),
            ),
            ToolDefinition(
                name="datadog_list_monitors",
                description="Datadogのモニター一覧を取得する。ステータスでフィルタ可能。",
                input_schema=ToolParameters(
                    properties={
                        "name": ToolParameterProperty(
                            type="string",
                            description="モニター名でフィルタ（部分一致）",
                        ),
                        "status": ToolParameterProperty(
                            type="string",
                            description="ステータスでフィルタ",
                            enum=["Alert", "Warn", "No Data", "OK"],
                        ),
                    },
                    required=[],
                ),
            ),
            ToolDefinition(
                name="datadog_get_monitor",
                description="特定のDatadogモニターの詳細情報を取得する。",
                input_schema=ToolParameters(
                    properties={
                        "monitor_id": ToolParameterProperty(
                            type="integer",
                            description="モニターID",
                        ),
                    },
                    required=["monitor_id"],
                ),
            ),
        ]

    async def execute(self, tool_name: str, parameters: dict[str, Any]) -> ToolResult:
        """ツールを実行する"""
        logger.info("datadog_execute", tool=tool_name, parameters=parameters)

        try:
            if tool_name == "datadog_query_metrics":
                return await self._query_metrics(parameters)
            elif tool_name == "datadog_search_logs":
                return await self._search_logs(parameters)
            elif tool_name == "datadog_list_monitors":
                return await self._list_monitors(parameters)
            elif tool_name == "datadog_get_monitor":
                return await self._get_monitor(parameters)
            else:
                return ToolResult(
                    tool_use_id="",
                    content=f"Unknown tool: {tool_name}",
                    is_error=True,
                )
        except Exception as e:
            logger.error("datadog_error", tool=tool_name, error=str(e))
            return ToolResult(
                tool_use_id="",
                content=f"Datadog API error: {e}",
                is_error=True,
            )

    async def _query_metrics(self, params: dict[str, Any]) -> ToolResult:
        """メトリクスクエリを実行する（datadog-api-clientを使用）"""
        try:
            from datadog_api_client import ApiClient, Configuration
            from datadog_api_client.v1.api.metrics_api import MetricsApi

            config = Configuration()
            config.api_key["apiKeyAuth"] = self._api_key
            config.api_key["appKeyAuth"] = self._app_key
            config.server_variables["site"] = self._site

            async with ApiClient(config) as api_client:
                api = MetricsApi(api_client)
                response = api.query_metrics(
                    _from=params["from_ts"],
                    to=params["to_ts"],
                    query=params["query"],
                )

            # レスポンスを要約
            series = response.get("series", [])
            if not series:
                return ToolResult(tool_use_id="", content="メトリクスデータが見つかりませんでした。")

            summaries = []
            for s in series:
                pointlist = s.get("pointlist", [])
                if pointlist:
                    values = [p[1] for p in pointlist if p[1] is not None]
                    if values:
                        summaries.append(
                            f"- {s.get('scope', 'unknown')}: "
                            f"avg={sum(values)/len(values):.2f}, "
                            f"min={min(values):.2f}, max={max(values):.2f}, "
                            f"points={len(values)}"
                        )

            return ToolResult(
                tool_use_id="",
                content=f"クエリ: {params['query']}\n" + "\n".join(summaries) if summaries else "データポイントなし",
            )
        except ImportError:
            return ToolResult(
                tool_use_id="",
                content="datadog-api-client がインストールされていません。`pip install cherry-bomb[plugins-datadog]` を実行してください。",
                is_error=True,
            )

    async def _search_logs(self, params: dict[str, Any]) -> ToolResult:
        """ログ検索を実行する"""
        try:
            from datadog_api_client import ApiClient, Configuration
            from datadog_api_client.v2.api.logs_api import LogsApi
            from datadog_api_client.v2.model.logs_list_request import LogsListRequest
            from datadog_api_client.v2.model.logs_list_request_page import LogsListRequestPage
            from datadog_api_client.v2.model.logs_query_filter import LogsQueryFilter
            from datadog_api_client.v2.model.logs_sort import LogsSort

            config = Configuration()
            config.api_key["apiKeyAuth"] = self._api_key
            config.api_key["appKeyAuth"] = self._app_key
            config.server_variables["site"] = self._site

            limit = min(params.get("limit", 10), 100)

            filter_params = {"query": params["query"]}
            if "from_ts" in params:
                filter_params["from"] = params["from_ts"]
            if "to_ts" in params:
                filter_params["to"] = params["to_ts"]

            body = LogsListRequest(
                filter=LogsQueryFilter(**filter_params),
                sort=LogsSort.TIMESTAMP_DESCENDING,
                page=LogsListRequestPage(limit=limit),
            )

            async with ApiClient(config) as api_client:
                api = LogsApi(api_client)
                response = api.list_logs(body=body)

            logs = response.get("data", [])
            if not logs:
                return ToolResult(tool_use_id="", content="ログが見つかりませんでした。")

            log_entries = []
            for log in logs[:limit]:
                attrs = log.get("attributes", {})
                log_entries.append(
                    f"- [{attrs.get('timestamp', '?')}] {attrs.get('service', '?')}: "
                    f"{attrs.get('message', '(no message)')[:200]}"
                )

            return ToolResult(
                tool_use_id="",
                content=f"ログ検索結果 ({len(log_entries)}件):\n" + "\n".join(log_entries),
            )
        except ImportError:
            return ToolResult(
                tool_use_id="",
                content="datadog-api-client がインストールされていません。",
                is_error=True,
            )

    async def _list_monitors(self, params: dict[str, Any]) -> ToolResult:
        """モニター一覧を取得する"""
        try:
            from datadog_api_client import ApiClient, Configuration
            from datadog_api_client.v1.api.monitors_api import MonitorsApi

            config = Configuration()
            config.api_key["apiKeyAuth"] = self._api_key
            config.api_key["appKeyAuth"] = self._app_key
            config.server_variables["site"] = self._site

            async with ApiClient(config) as api_client:
                api = MonitorsApi(api_client)
                kwargs = {}
                if "name" in params:
                    kwargs["name"] = params["name"]
                monitors = api.list_monitors(**kwargs)

            # ステータスフィルタ
            if "status" in params:
                monitors = [m for m in monitors if m.get("overall_state") == params["status"]]

            if not monitors:
                return ToolResult(tool_use_id="", content="該当するモニターが見つかりませんでした。")

            entries = []
            for m in monitors[:20]:
                entries.append(
                    f"- [{m.get('overall_state', '?')}] {m.get('name', '?')} (ID: {m.get('id', '?')})"
                )

            return ToolResult(
                tool_use_id="",
                content=f"モニター一覧 ({len(entries)}件):\n" + "\n".join(entries),
            )
        except ImportError:
            return ToolResult(
                tool_use_id="",
                content="datadog-api-client がインストールされていません。",
                is_error=True,
            )

    async def _get_monitor(self, params: dict[str, Any]) -> ToolResult:
        """特定のモニター詳細を取得する"""
        try:
            from datadog_api_client import ApiClient, Configuration
            from datadog_api_client.v1.api.monitors_api import MonitorsApi

            config = Configuration()
            config.api_key["apiKeyAuth"] = self._api_key
            config.api_key["appKeyAuth"] = self._app_key
            config.server_variables["site"] = self._site

            async with ApiClient(config) as api_client:
                api = MonitorsApi(api_client)
                monitor = api.get_monitor(monitor_id=params["monitor_id"])

            return ToolResult(
                tool_use_id="",
                content=(
                    f"モニター詳細:\n"
                    f"- 名前: {monitor.get('name', '?')}\n"
                    f"- ステータス: {monitor.get('overall_state', '?')}\n"
                    f"- タイプ: {monitor.get('type', '?')}\n"
                    f"- クエリ: {monitor.get('query', '?')}\n"
                    f"- メッセージ: {monitor.get('message', '(なし)')[:200]}\n"
                    f"- タグ: {', '.join(monitor.get('tags', []))}"
                ),
            )
        except ImportError:
            return ToolResult(
                tool_use_id="",
                content="datadog-api-client がインストールされていません。",
                is_error=True,
            )
