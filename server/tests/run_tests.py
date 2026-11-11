"""Run backend tests with disposable storage configured before app imports.

Usage from the repository root: python server/tests/run_tests.py
"""

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo_root))
    with tempfile.TemporaryDirectory(prefix="openpoke-tests-") as directory:
        with patch.dict(os.environ, {
            "OPENPOKE_DATA_DIR": directory,
            "OPENPOKE_WORKER_DISCOVERY": "legacy",
            "OPENPOKE_WORKER_RANKER": "heuristic_v1",
            "OPENPOKE_CONTEXT_STRATEGY": "legacy",
            "OPENPOKE_MODEL_CONTEXT_WINDOWS": "{}",
            "OPENPOKE_CONTEXT_INPUT_TOKENS": "32768",
            "OPENPOKE_CONTEXT_HEADROOM_TOKENS": "1024",
            "OPENROUTER_API_KEY": "test-key",
            "COMPOSIO_API_KEY": "test-key",
            "COMPOSIO_GMAIL_AUTH_CONFIG_ID": "test-auth-config",
        }):
            # Importing server initializes stores, so discover only after setting
            # the environment. Always override a caller's real data directory.
            suite = unittest.defaultTestLoader.discover(str(repo_root / "server" / "tests"))
            result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
