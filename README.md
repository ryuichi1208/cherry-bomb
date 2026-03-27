# cherry-bomb

SRE AI Agent powered by Claude API. Slackからメンションすると、Datadogのメトリクス取得やログ検索などのSRE業務を支援します。

## Architecture

```
[Slack] <-> [FastAPI + Slack Bolt]
                ├── Claude API (Tool Use loop)
                ├── Plugin System (Datadog, PagerDuty, K8s, AWS...)
                └── Approval Flow (SQS + DynamoDB)
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

## Tech Stack

- Python 3.14+ / uv
- Claude API (Tool Use)
- FastAPI + Slack Bolt
- Pydantic v2 / structlog
- AWS (ECS, DynamoDB, SQS, Lambda)
