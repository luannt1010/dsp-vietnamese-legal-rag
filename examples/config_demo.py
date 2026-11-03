"""Inspect configuration offline with python -m examples.config_demo."""

import sys

from core.config import load_settings
from core.exceptions import ConfigurationError


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    settings = load_settings()
    print("Retrieval defaults:")
    print(settings.retrieval.default_strategy().model_dump_json(indent=2))
    print("Raw data directory:", settings.data_pipeline.raw_dir)
    try:
        settings.validate_runtime()
    except ConfigurationError as exc:
        print("Mock development is available. Real adapters need configuration:")
        print(exc)
    else:
        print("Runtime selections complete; service/model connectivity is not checked.")


if __name__ == "__main__":
    main()
