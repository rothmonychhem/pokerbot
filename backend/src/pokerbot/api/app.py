"""FastAPI application factory."""

from fastapi import FastAPI

from pokerbot import __version__


def create_app() -> FastAPI:
    """Build the API application."""
    application = FastAPI(title="Poker Bot Arena", version=__version__)

    @application.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
