"""
Smoke tests for Krishora Insight — Agriculture Data Analytics Platform.
These basic tests verify the project structure and core dependencies are healthy.
"""
import os

import fastapi
import pydantic


def test_project_importable():
    """Verify the app/main.py file exists in the project."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    app_main_path = os.path.abspath(os.path.join(script_dir, "..", "app", "main.py"))
    assert os.path.exists(app_main_path), "app/main.py must exist"


def test_fastapi_available():
    """Verify FastAPI is installed and importable."""
    assert fastapi.__version__, "FastAPI must be importable"


def test_pydantic_available():
    """Verify Pydantic is installed and importable."""
    assert pydantic.__version__, "Pydantic must be importable"
