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

    parser = argparse.ArgumentParser(description="Capture the legacy baseline or compare legacy/bounded agents with synthetic Gmail.")
    parser.add_argument("--manifest", type=Path, default=HERE / "manifest.json")
    parser.add_argument("--output", type=Path, help="New evidence directory; existing directories are never overwritten.")
    parser.add_argument("--sizes", type=int, nargs="+", choices=(0, 100, 1000, 10000))
    parser.add_argument("--mode", choices=("model-free", "live"), default="model-free")
    parser.add_argument("--compare", action="store_true", help="Compare both strategies; model-free decisions remain scripted.")
    parser.add_argument("--cases", nargs="+", help="Frozen routing case IDs for the comparison.")
    parser.add_argument("--context-window", type=int, help="Explicit model context allowance for bounded comparison requests.")
    parser.add_argument("--input-cap", type=int, default=32768)
    parser.add_argument("--max-calls", type=int, default=64, help="Total HTTP request cap across both comparison arms.")
    parser.add_argument("--case-timeout", type=int, default=180)
    parser.add_argument("--request-interval", type=float, help="Minimum seconds between HTTP requests; defaults to 3.1 live, 0 offline.")
    args = parser.parse_args(argv)
    output = None
    try:
        manifest = load_manifest(args.manifest)
        if "server" in sys.modules:
            raise EvaluationConfigError("Run the harness in a fresh standalone process")
        if args.mode == "live" and not args.compare:
            raise EvaluationConfigError("Live mode requires --compare; the frozen baseline remains model-free")
        key = "test-key"
        if args.compare:
            if args.context_window is None or args.context_window < args.input_cap + 1024 + manifest["runtime_settings"]["openrouter_max_tokens"] or args.input_cap < 4096:
                raise EvaluationConfigError("Comparison requires --context-window covering input cap, output, and 1024 headroom; input cap must be at least 4096")
            if not 1 <= args.max_calls <= 128 or not 10 <= args.case_timeout <= 300:
                raise EvaluationConfigError("Comparison supports 1–128 total requests and 10–300 seconds per case")
            if args.request_interval is not None and not 0 <= args.request_interval <= 10:
                raise EvaluationConfigError("Request interval must be between 0 and 10 seconds")
            if args.mode == "live":
                # Read only this credential, before app imports or disposable env setup.
                from dotenv import dotenv_values
                key = os.environ.get("OPENROUTER_API_KEY")
                if key is None:
                    key = dotenv_values(ROOT / ".env").get("OPENROUTER_API_KEY")
                if not key or key == "test-key":
                    raise EvaluationConfigError("Live comparison requires a configured OpenRouter API key")
        elif args.cases or args.context_window:
            raise EvaluationConfigError("Comparison controls require --compare")
        sizes = args.sizes if args.sizes is not None else ([100] if args.compare else manifest["catalog_sizes"])
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
                    "OPENPOKE_MODEL_CONTEXT_WINDOWS": json.dumps({manifest["runtime_settings"]["interaction_agent_model"]: args.context_window}) if args.compare else "{}",
                    "OPENPOKE_CONTEXT_INPUT_TOKENS": str(args.input_cap) if args.compare else "32768",
                    "OPENPOKE_CONTEXT_HEADROOM_TOKENS": "1024",
                    "OPENROUTER_API_KEY": key,
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
                    from contextlib import ExitStack
                    with ExitStack() as guards:
                        if args.mode == "model-free":
                            guards.enter_context(patch.object(socket.socket, "connect", side_effect=reject_network))
                            guards.enter_context(patch.object(socket.socket, "connect_ex", side_effect=reject_network))
                        # This import initializes stores, so keep it after env setup.
                        if args.compare:
                            from evals.agent_overload.comparison import run_comparison
                            summary = loop.run_until_complete(run_comparison(manifest, sizes, output, Path(directory),
                                mode=args.mode, cases=args.cases, max_calls=args.max_calls, timeout=args.case_timeout,
                                request_interval=args.request_interval if args.request_interval is not None else 3.1 if args.mode == "live" else 0))
                        else:
                            from evals.agent_overload.engine import run_evaluation
                            summary = run_evaluation(manifest, sizes, output, Path(directory), loop)
                finally:
                    loop.run_until_complete(loop.shutdown_asyncgens())
                    loop.run_until_complete(loop.shutdown_default_executor())
                    loop.close()
                    asyncio.set_event_loop(None)
        print(json.dumps({"status": "passed" if summary["checks_passed"] else "failed",
                          "mode": args.mode, "case_contexts": summary["case_context_count"],
                          "routing_quality": summary["routing_quality"] if args.compare else "unavailable", "output": str(output)}))
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
