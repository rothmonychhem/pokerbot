"""FastAPI application factory."""

from fastapi import FastAPI

from pokerbot import __version__
from pokerbot.api.play import create_play_router


def create_app() -> FastAPI:
    """Build the API application."""
    application = FastAPI(title="Poker Bot Arena", version=__version__)

    @application.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    application.include_router(create_play_router())
    return application


app = create_app()
