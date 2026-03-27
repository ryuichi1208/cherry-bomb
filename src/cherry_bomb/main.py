"""FastAPI application + Slack Bolt integration"""

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import structlog
from fastapi import FastAPI, Request, Response
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from slack_bolt.async_app import AsyncApp

from cherry_bomb.agent.orchestrator import AgentOrchestrator
from cherry_bomb.config import Settings
from cherry_bomb.interfaces.slack.handler import register_handlers
from cherry_bomb.plugins.registry import PluginRegistry

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = structlog.get_logger()


def create_slack_app(settings: Settings) -> AsyncApp:
    """Slack Bolt app を作成する"""
    return AsyncApp(
        token=settings.SLACK_BOT_TOKEN.get_secret_value(),
        signing_secret=settings.SLACK_SIGNING_SECRET.get_secret_value(),
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """FastAPI application を作成する"""
    if settings is None:
        settings = Settings()

    registry = PluginRegistry()
    orchestrator = AgentOrchestrator(settings=settings, registry=registry)

    slack_app = create_slack_app(settings)
    register_handlers(slack_app, orchestrator)
    slack_handler = AsyncSlackRequestHandler(slack_app)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        logger.info("cherry_bomb_starting", model=settings.CLAUDE_MODEL)
        yield
        logger.info("cherry_bomb_stopping")

    fastapi_app = FastAPI(
        title="cherry-bomb",
        description="SRE AI Agent",
        version="0.1.0",
        lifespan=lifespan,
    )

    @fastapi_app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @fastapi_app.post("/slack/events")
    async def slack_events(request: Request) -> Response:
        return await slack_handler.handle(request)

    return fastapi_app
