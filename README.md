# cherry-bomb

SRE AI Agent powered by Claude API. Slackからメンションすると、Datadogのメトリクス取得やログ検索などのSRE業務を支援します。

## Architecture

```
[Slack] <-> [FastAPI + Slack Bolt]
                ├── Claude API (Tool Use loop)
                ├── Plugin System (Datadog, PagerDuty, K8s, AWS...)
                ├── Decision Log (SQLite) ← 意思決定の記録・照会
                ├── Approval Flow (SQS + DynamoDB)
                └── MCP Server (stdio) ← Claude Code 連携

[Claude Code] <-> [MCP Server] <-> [Decision Log]
```

## Quick Start

```bash
# 依存インストール
uv sync --extra dev

# 環境変数を設定
cp .env.example .env
# .env を編集して API キーを設定

# 起動
make dev

# テスト
make test

# lint
make lint
```

## Plugin System

`ToolPlugin` ABC を実装することで独自のツールを追加できます。

```python
from cherry_bomb.plugins.base import ToolPlugin

class MyPlugin(ToolPlugin):
    @property
    def name(self) -> str:
        return "my-plugin"

    # ...
```

読み取り系ツールは即座に実行され、変更系ツールはSlackで承認を得てから実行されます。

## Decision Log

エージェントが各ターンで「なぜその判断をしたか」を構造化して SQLite に記録します。後から Slack や Claude Code 経由で照会できます。

**記録される情報:**
- 各ターンの Claude の推論テキスト（reasoning）
- 使用したツールとパラメータ
- ツール実行結果のサマリ
- 承認待ちの有無

**照会方法:**
- Slack: `@cherry-bomb さっきのアラート対応でなぜCPUメトリクスを先に見た？` → `decision_search` ツール経由で自動検索
- Claude Code: MCP サーバー経由（下記参照）

## MCP Server (Claude Code 連携)

意思決定ログを Claude Code から照会できる MCP サーバーを提供しています。

### セットアップ

```bash
# MCP 依存をインストール
uv sync --extra mcp

# .claude/settings.json に追加
```

```json
{
  "mcpServers": {
    "cherry-bomb": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/cherry-bomb", "python", "-m", "cherry_bomb.interfaces.mcp.run"],
      "env": {}
    }
  }
}
```

### 利用可能なツール

| ツール | 説明 |
|--------|------|
| `decision_search` | キーワードで過去の意思決定ログを検索 |
| `decision_get` | セッションIDで特定の意思決定ログの詳細を取得 |

### 使用例（Claude Code から）

```
「cherry-bomb が昨日のアラート対応でなぜ Datadog メトリクスを先に確認したのか調べて」
→ decision_search("アラート Datadog") が呼ばれ、過去の推論過程を返す
```

## Tech Stack

- Python 3.14+ / uv
- Claude API (Tool Use)
- FastAPI + Slack Bolt
- Pydantic v2 / structlog
- SQLite (aiosqlite) — 意思決定ログ
- MCP SDK — Claude Code 連携
- AWS (ECS, DynamoDB, SQS, Lambda)
