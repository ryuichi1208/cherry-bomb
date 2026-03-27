# cherry-bomb: SRE AI Agent 設計書

## Context

SREチームの運用負荷を軽減するため、Slackを主要インターフェースとしたAIエージェントを構築する。インシデント対応支援、運用タスク自動化、監視・分析・可観測性の3領域をカバーする複合型エージェントとして設計し、Claude APIのTool Use機能を活用してプラグイン式の外部ツール連携を実現する。

変更系操作には人間の承認を必須とし、安全性を確保する。

## 要件

- **AIバックエンド**: Claude API (Tool Use)
- **インターフェース**: Slack (メイン) + CLI
- **ツール連携**: プラグイン式（Datadog, PagerDuty, Kubernetes, AWS等を柔軟に追加）
- **自律性**: 承認付き実行（提案 → Slack承認 → 実行）
- **デプロイ**: AWS ECS (メイン) + Lambda (承認後実行)
- **言語**: Python 3.14+

## アーキテクチャ

### 全体構成: ハイブリッド型（モノリシック + イベント駆動の部分採用）

Claude APIのTool Useループは同期的であるため、コア処理はECS上の単一プロセスで同期実行する。一方、承認フローは本質的に非同期（人間の応答待ち）であるため、SQS + DynamoDB + Lambdaによるイベント駆動を採用する。

```
[Slack] ←→ [ECS: FastAPI + Slack Bolt]
                ├── agent/orchestrator (Claude API Tool Useループ: 同期)
                ├── plugins/ (読み取り系ツール: 同期実行)
                └── approval/ → [SQS] → [Lambda: 変更系アクション実行]
                                        → [DynamoDB: 承認状態管理]

[CLI] → [agent/orchestrator] → 同上のプラグイン・承認フロー
```

### データフロー

#### 読み取り系操作（承認不要）

```
Slackメッセージ受信
  → Slack Bolt handler
  → agent/orchestrator (Claude API呼び出し)
  → Claude が tool_use を返す
  → plugin/registry でツール特定
  → プラグインが直接実行（例: Datadogメトリクス取得）
  → 結果をClaudeに返す → Claudeが自然言語で回答
  → Slackに返信
```

#### 変更系操作（承認必要）

```
Slackメッセージ受信
  → Slack Bolt handler
  → agent/orchestrator (Claude API呼び出し)
  → Claude が tool_use を返す
  → plugin の requires_approval() == True
  → approval/manager が承認リクエスト生成
  → DynamoDB に保存 + Slackに Block Kit 承認メッセージ送信
  → 人間が Approve ボタンクリック
  → Slack interactions handler → approval/manager がステータス更新
  → SQS にメッセージ送信
  → Lambda (executor) がプラグイン経由でアクション実行
  → 結果をSlackに返信
```

## コンポーネント詳細

### 1. agent/orchestrator - AIエージェントコア

Claude APIのTool Useループを管理する心臓部。

```python
async def run_agent_loop(user_message: str, context: ConversationContext) -> str:
    messages = context.get_history() + [{"role": "user", "content": user_message}]
    tools = plugin_registry.get_claude_tools()

    while True:
        response = await claude_client.messages.create(
            model="claude-sonnet-4-20250514",
            system=build_system_prompt(context),
            messages=messages,
            tools=tools,
            max_tokens=4096,
        )

        if response.stop_reason == "end_turn":
            return extract_text(response)

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = await handle_tool_call(block)
                    tool_results.append(result)

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
```

### 2. plugins/base - ToolPlugin プロトコル

すべてのプラグインが実装するインターフェース。

```python
from abc import ABC, abstractmethod
from typing import Any
from cherry_bomb.models.schemas import ToolDefinition, ToolResult

class ToolPlugin(ABC):
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
        """ツールを実行する"""
        ...

    def requires_approval(self, tool_name: str) -> bool:
        """変更系操作はTrue、読み取り系はFalse（デフォルト: True）"""
        return True

    def read_only_tools(self) -> set[str]:
        """承認不要の読み取り系ツール名のセットを返す"""
        return set()
```

### 3. plugins/registry - プラグイン登録

```python
class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, ToolPlugin] = {}

    def register(self, plugin: ToolPlugin) -> None:
        self._plugins[plugin.name] = plugin

    def get_claude_tools(self) -> list[dict]:
        """全プラグインのツール定義をClaude API形式で返す"""
        tools = []
        for plugin in self._plugins.values():
            for tool_def in plugin.get_tools():
                tools.append(tool_def.to_claude_format())
        return tools

    def resolve_tool(self, tool_name: str) -> tuple[ToolPlugin, bool]:
        """tool_nameからプラグインと承認要否を解決"""
        for plugin in self._plugins.values():
            for tool_def in plugin.get_tools():
                if tool_def.name == tool_name:
                    needs_approval = plugin.requires_approval(tool_name)
                    return plugin, needs_approval
        raise ToolNotFoundError(tool_name)
```

### 4. approval/manager - 承認フロー管理

```python
@dataclass
class ApprovalRequest:
    request_id: str              # UUID
    tool_name: str
    parameters: dict[str, Any]
    requester: str               # Slack user ID
    channel: str                 # Slack channel ID
    status: ApprovalStatus       # pending / approved / rejected / expired
    created_at: datetime
    expires_at: datetime         # デフォルト30分
    approved_by: str | None = None
    execution_result: str | None = None

class ApprovalManager:
    async def create_request(self, ...) -> ApprovalRequest:
        """承認リクエストを作成しDynamoDBに保存"""
        ...

    async def approve(self, request_id: str, approver: str) -> ApprovalRequest:
        """承認を記録し、SQSに実行メッセージを送信"""
        ...

    async def reject(self, request_id: str, rejector: str) -> ApprovalRequest:
        """拒否を記録"""
        ...
```

### 5. interfaces/slack - Slack連携

Slack Boltを使用してイベント駆動でメッセージを処理する。

- `handler.py`: `@app.message()` でメッセージ受信、orchestratorに渡す
- `blocks.py`: Block Kit UIビルダー（承認ボタン、結果表示等）
- `interactions.py`: `@app.action()` でボタンクリックを処理

### 6. interfaces/cli - CLIインターフェース

Typerベースで、ローカルからエージェントを利用可能にする。

```
cherry-bomb ask "production のCPU使用率を教えて"
cherry-bomb incident analyze --id INC-1234
cherry-bomb runbook execute --name restart-service --service api
```

## プロジェクト構造

```
cherry-bomb/
├── pyproject.toml
├── uv.lock
├── src/
│   └── cherry_bomb/
│       ├── __init__.py
│       ├── __main__.py
│       ├── main.py                 # FastAPI + Slack Bolt
│       ├── config.py               # pydantic-settings
│       ├── agent/
│       │   ├── __init__.py
│       │   ├── orchestrator.py     # Claude API Tool Useループ
│       │   ├── prompts.py          # システムプロンプト管理
│       │   ├── memory.py           # 会話履歴管理
│       │   └── tool_router.py      # tool_use → プラグインルーティング
│       ├── interfaces/
│       │   ├── __init__.py
│       │   ├── slack/
│       │   │   ├── __init__.py
│       │   │   ├── handler.py
│       │   │   ├── blocks.py
│       │   │   └── interactions.py
│       │   └── cli/
│       │       ├── __init__.py
│       │       └── app.py
│       ├── approval/
│       │   ├── __init__.py
│       │   ├── manager.py
│       │   ├── models.py
│       │   └── store.py            # DynamoDB永続化
│       ├── plugins/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── registry.py
│       │   ├── builtin/
│       │   │   ├── __init__.py
│       │   │   ├── datadog.py
│       │   │   ├── pagerduty.py
│       │   │   ├── kubernetes.py
│       │   │   └── aws.py
│       │   └── contrib/
│       │       └── __init__.py
│       ├── executor/
│       │   ├── __init__.py
│       │   ├── runner.py
│       │   ├── lambda_handler.py
│       │   └── audit.py
│       └── models/
│           ├── __init__.py
│           └── schemas.py
├── tests/
│   ├── conftest.py
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── docs/
├── infra/
│   ├── cdk/
│   └── docker/
│       ├── Dockerfile
│       └── docker-compose.yml
├── Makefile
├── .github/workflows/
├── .env.example
└── README.md
```

## 技術選定

| カテゴリ | 選定 | 理由 |
|---|---|---|
| パッケージ管理 | uv | 高速、lockファイル対応 |
| Web FW | FastAPI | 非同期対応、型安全 |
| Slack SDK | slack-bolt | 公式推奨、イベント/インタラクション対応 |
| AI SDK | anthropic | 公式Claude API SDK、Tool Use対応 |
| CLI | Typer | 型安全、自動ヘルプ生成 |
| 設定管理 | pydantic-settings | 環境変数の型安全な読み込み |
| ログ | structlog | 構造化ログ、JSON出力 |
| 型チェック | mypy (strict) | SREツールとして信頼性重視 |
| Linter | ruff | 高速、包括的 |
| テスト | pytest + moto + respx | AWSモック + HTTPモック |
| インフラ | AWS CDK (Python) | Pythonで統一 |

## 承認フローの安全性設計

- **デフォルト承認必須**: `requires_approval()` のデフォルトは `True`。明示的にオプトアウトした読み取り系のみ承認スキップ
- **TTL**: 承認リクエストは30分でexpire（DynamoDB TTL）
- **承認者制限**: 将来的にSlackのユーザーグループで承認可能者を制限
- **監査ログ**: すべての承認/拒否/実行をDynamoDBに記録
- **冪等性**: executor は実行IDで冪等性を保証

## フェーズ

### Phase 1: MVP

Slack → Claude → Datadog読み取りの基本フローを動かす。

実装対象: `config.py`, `main.py`, `agent/orchestrator.py`, `plugins/base.py`, `plugins/registry.py`, `plugins/builtin/datadog.py`, `interfaces/slack/handler.py`, `Dockerfile`, `docker-compose.yml`

### Phase 2: 承認フロー

変更系操作の承認→実行フローを追加。

実装対象: `approval/*`, `executor/*`, `interfaces/slack/blocks.py`, `interfaces/slack/interactions.py`

### Phase 3: プラグイン拡充 + CLI

PagerDuty, Kubernetes, AWSプラグインとCLIインターフェース。

実装対象: `plugins/builtin/pagerduty.py`, `plugins/builtin/kubernetes.py`, `plugins/builtin/aws.py`, `interfaces/cli/app.py`

### Phase 4: 本番運用品質

CDKインフラ、CI/CD、OpenTelemetry計装、会話コンテキスト管理。

### Phase 5: 高度な機能

自動インシデント検知、RAGによる過去インシデント学習、マルチチャンネル対応。

## 検証方法

1. **ローカル開発**: `docker-compose up` でFastAPI + ngrok → Slackイベント受信テスト
2. **ユニットテスト**: Claude APIレスポンスのモックでorc hestratorのロジックテスト
3. **統合テスト**: motoでDynamoDB/SQSをモック、Slack APIをrespxでモック
4. **E2Eテスト**: 実際のSlackワークスペース + Claude APIでエンドツーエンド確認
