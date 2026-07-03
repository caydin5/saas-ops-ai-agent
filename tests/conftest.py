"""
Test configuration.

This file ensures pytest can import the local app package when tests are run
from the project root.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))