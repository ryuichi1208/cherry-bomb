"""Slack Bolt event handler"""

import contextlib

import structlog
from slack_bolt.async_app import AsyncApp
from slack_sdk.web.async_client import AsyncWebClient

from cherry_bomb.agent.orchestrator import AgentOrchestrator

logger = structlog.get_logger()


def register_handlers(app: AsyncApp, orchestrator: AgentOrchestrator) -> None:
    """Slack Bolt app にイベントハンドラを登録する"""

    @app.event("app_mention")
    async def handle_mention(event: dict, say: callable, client: AsyncWebClient) -> None:
        """メンション時にエージェントを起動する"""
        user = event.get("user", "unknown")
        text = event.get("text", "")
        channel = event.get("channel", "")
        thread_ts = event.get("thread_ts") or event.get("ts", "")

        logger.info("slack_mention_received", user=user, channel=channel)

        # 考え中の反応を追加
        with contextlib.suppress(Exception):
            await client.reactions_add(
                channel=channel,
                timestamp=event["ts"],
                name="hourglass_flowing_sand",
            )

        try:
            response = await orchestrator.run(
                user_message=text,
                additional_context=f"Slack channel: {channel}, User: <@{user}>",
            )

            # メインの応答を送信
            await say(text=response.text, thread_ts=thread_ts)

            # 承認待ちがあれば通知
            if response.has_pending_approvals:
                for approval in response.pending_approvals:
                    await say(
                        text=f"⏳ *承認待ち*: `{approval['tool_name']}` の実行には承認が必要です。",
                        thread_ts=thread_ts,
                    )

        except Exception as e:
            logger.error("agent_error", error=str(e))
            await say(
                text=f"エラーが発生しました: {e}",
                thread_ts=thread_ts,
            )
        finally:
            # 完了リアクションに変更
            with contextlib.suppress(Exception):
                await client.reactions_remove(
                    channel=channel,
                    timestamp=event["ts"],
                    name="hourglass_flowing_sand",
                )
                await client.reactions_add(
                    channel=channel,
                    timestamp=event["ts"],
                    name="white_check_mark",
                )

    @app.event("message")
    async def handle_message(event: dict) -> None:
        """一般メッセージは無視する（メンションのみ応答）"""
        pass
