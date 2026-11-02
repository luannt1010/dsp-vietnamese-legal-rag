# conftest.py
"""Test configuration to ensure the repository root is on PYTHONPATH.
This allows imports like `import src.xxx` and `import core.xxx` in the test suite.
"""
import sys
import pathlib

# Add the project root (directory containing this file) to sys.path
project_root = pathlib.Path(__file__).resolve().parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
