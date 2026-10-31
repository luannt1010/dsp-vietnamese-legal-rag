"""Configuration entry point; load once at application startup and inject."""

from core.config.loader import load_settings
from core.config.settings import Settings

__all__ = ["Settings", "load_settings"]
