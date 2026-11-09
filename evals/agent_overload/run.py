"""Standalone bootstrap: configure disposable state before any server import."""

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import traceback
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]


def main(argv=None):
    sys.path.insert(0, str(ROOT))
    from evals.agent_overload.contracts import EvaluationConfigError, HERE, load_manifest

    parser = argparse.ArgumentParser(description="Capture a model-free legacy baseline; no live provider/email calls.")
    parser.add_argument("--manifest", type=Path, default=HERE / "manifest.json")
    parser.add_argument("--output", type=Path, help="New evidence directory; existing directories are never overwritten.")
    parser.add_argument("--sizes", type=int, nargs="+", choices=(0, 100, 1000, 10000))
    parser.add_argument("--mode", choices=("model-free",), default="model-free")
    args = parser.parse_args(argv)
    output = None
    try:
        manifest = load_manifest(args.manifest)
        if "server" in sys.modules:
            raise EvaluationConfigError("Run the harness in a fresh standalone process")
        sizes = args.sizes if args.sizes is not None else manifest["catalog_sizes"]
        if len(set(sizes)) != len(sizes):
            raise EvaluationConfigError("Catalog sizes must not be repeated")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        output = (args.output or HERE / "runs" / stamp).resolve()
        output.mkdir(parents=True, exist_ok=False)

        def reject_network(*unused_args, **unused_kwargs):
            raise RuntimeError("Network access is disabled in model-free evaluations")

        with tempfile.TemporaryDirectory(prefix="openpoke-eval-") as directory:
            with patch.dict(os.environ, {
                    "OPENPOKE_DATA_DIR": directory,
                    "OPENPOKE_WORKER_DISCOVERY": "legacy",
                    "OPENPOKE_CONTEXT_STRATEGY": "legacy",
                    "OPENPOKE_MODEL_CONTEXT_WINDOWS": "{}",
                    "OPENPOKE_CONTEXT_INPUT_TOKENS": "32768",
                    "OPENPOKE_CONTEXT_HEADROOM_TOKENS": "1024",
                    "OPENROUTER_API_KEY": "test-key",
                    "COMPOSIO_API_KEY": "test-key",
                    "COMPOSIO_GMAIL_AUTH_CONFIG_ID": "test-auth-config",
                    "OPENROUTER_MODEL": manifest["runtime_settings"]["interaction_agent_model"],
                    "OPENROUTER_MAX_TOKENS": str(manifest["runtime_settings"]["openrouter_max_tokens"]),
            }):
                # Windows may connect a local self-pipe while creating the loop.
                # Construct it before blocking all subsequent socket connects.
                loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(loop)
                    with (
                        patch.object(socket.socket, "connect", side_effect=reject_network),
                        patch.object(socket.socket, "connect_ex", side_effect=reject_network),
                    ):
                        # This import initializes stores, so keep it after env setup.
                        from evals.agent_overload.engine import run_evaluation
                        summary = run_evaluation(manifest, sizes, output, Path(directory), loop)
                finally:
                    loop.run_until_complete(loop.shutdown_asyncgens())
                    loop.run_until_complete(loop.shutdown_default_executor())
                    loop.close()
                    asyncio.set_event_loop(None)
        print(json.dumps({"status": "passed" if summary["checks_passed"] else "failed",
                          "mode": "model-free", "case_contexts": summary["case_context_count"],
                          "routing_quality": "unavailable", "output": str(output)}))
        return 0 if summary["checks_passed"] else 1
    except FileExistsError:
        print("Evidence directory already exists; choose a new --output directory.", file=sys.stderr)
        return 2
    except EvaluationConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        # Do not dump exception messages, settings, headers, or the environment.
        if output is not None and output.is_dir():
            frames = [frame for frame in traceback.extract_tb(exc.__traceback__) if Path(frame.filename).is_relative_to(ROOT)]
            location = {"file": str(Path(frames[-1].filename).relative_to(ROOT)), "line": frames[-1].lineno} if frames else None
            (output / "failure.json").write_text(json.dumps({"status": "failed", "exception_type": type(exc).__name__, "location": location}), encoding="utf-8")
        print(f"Evaluation failed ({type(exc).__name__}); inspect the saved evidence.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
