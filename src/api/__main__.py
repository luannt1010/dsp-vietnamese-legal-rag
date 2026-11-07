"""Run with python -m src.api using the existing host/port/logging settings."""

import logging

import uvicorn

from src.api.main import app


def main() -> None:
    settings = app.state.settings
    logging.basicConfig(level=settings.logging.level)
    uvicorn.run(app, host=settings.api.host, port=settings.api.port,
                log_level=settings.logging.level.lower(), access_log=False)


if __name__ == "__main__":
    main()
