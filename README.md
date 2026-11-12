# OpenPoke 🌴

OpenPoke is a simplified, open-source take on [Interaction Company’s](https://interaction.co/about) [Poke](https://poke.com/) assistant—built to show how a multi-agent orchestration stack can feel genuinely useful. It keeps the handful of things Poke is great at (email triage, reminders, and persistent agents) while staying easy to spin up locally.

- Multi-agent FastAPI backend that mirrors Poke's interaction/execution split, powered by [OpenRouter](https://openrouter.ai/).
- Gmail tooling via [Composio](https://composio.dev/) for drafting/replying/forwarding without leaving chat.
- Trigger scheduler and background watchers for reminders and "important email" alerts.
- Next.js web UI that proxies everything through the shared `.env`, so plugging in API keys is the only setup.

## Requirements
- Python 3.10+
- Node.js 18+
- npm 9+

## Quickstart
1. **Clone and enter the repo.**
   ```bash
   git clone https://github.com/shlokkhemani/OpenPoke
   cd OpenPoke
   ```
2. **Create a shared env file.** Copy the template and open it in your editor:
   ```bash
   cp .env.example .env
   ```
3. **Get your API keys and add them to `.env`:**
   
   **OpenRouter (Required)**
   - Create an account at [openrouter.ai](https://openrouter.ai/)
   - Generate an API key
   - Replace `your_openrouter_api_key_here` with your actual key in `.env`
   - The default model is `anthropic/claude-sonnet-4.6`. Bounded discovery/context are enabled by default with a 65,536 planning allowance for that bundled model. This is an application policy, not a provider-capacity claim.
   - To use another tool-capable model, set `OPENROUTER_MODEL` and provide `OPENPOKE_MODEL_CONTEXT_WINDOWS` entries for every selected model, then restart. Custom models without explicit allowances fail startup; see [context configuration](docs/context-budgets.md).
   - LLM requests allow up to 2,048 output tokens by default to avoid reserving the model's full output limit against your credits. Set `OPENROUTER_MAX_TOKENS` in `.env` to adjust this limit, then restart the backend.
   
   **Composio (Required for Gmail)**
   - Sign in at [composio.dev](https://composio.dev/)
   - Create an API key
   - Set up Gmail integration and get your auth config ID
   - Replace `your_composio_api_key_here` and `your_gmail_auth_config_id_here` in `.env`
4. **(Required) Create and activate a Python 3.10+ virtualenv:**
   ```bash
   # Ensure you're using Python 3.10+
   python3.10 -m venv .venv
   source .venv/bin/activate
   
   # Verify Python version (should show 3.10+)
   python --version
   ```
   On Windows (PowerShell):
   ```powershell
   # Use Python 3.10+ (adjust path as needed)
   python3.10 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   
   # Verify Python version
   python --version
   ```

5. **Install backend dependencies:**
   ```bash
   pip install -r server/requirements.txt
   ```
6. **Install frontend dependencies:**
   ```bash
   npm install --prefix web
   ```
7. **Start the FastAPI server:**
   ```bash
   python -m server.server --reload
   ```
8. **Start the Next.js app (new terminal):**
   ```bash
   npm run dev --prefix web
   ```
9. **Connect Gmail for email workflows.** With both services running, open [http://localhost:3000](http://localhost:3000), head to *Settings → Gmail*, and complete the Composio OAuth flow. This step is required for email drafting, replies, and the important-email monitor.

The web app proxies API calls to the Python server using the values in `.env`, so keeping both processes running is required for end-to-end flows.

## Runtime data and backend tests

Persistent state defaults to `server/data/`. Set `OPENPOKE_DATA_DIR` in the
environment or `.env` before starting the backend to use another directory.
Relative paths resolve from the process working directory; `~` is expanded.
Restart the backend after changing this setting. Existing files are not moved.

Run the backend tests from the repository root with:

```bash
python server/tests/run_tests.py
```

The runner sets a temporary data directory before importing the application and
replaces integration credentials with test values. Use this runner instead of
bare unittest discovery, which imports stores using your runtime configuration.
Tests use mocked providers and do not require live Gmail or model calls.

Runtime logs also include `telemetry` JSON events for model usage/timing and
request, worker, and callback correlation. See [Runtime telemetry](docs/observability.md)
for fields, examples, and content boundaries.

Frozen workflow catalogs and the local Gmail test backend are documented in
[Agent overload fixtures](server/tests/fixtures/README.md).

Capture the model-free full-roster baseline with:

```bash
python evals/agent_overload/run.py
```

See the [evaluation harness](evals/agent_overload/README.md) and the
[saved baseline report](evals/agent_overload/baseline/report.md). The runner uses
disposable storage and mocked providers; live model quality/cost remain unmeasured.

The [paired comparison command](evals/agent_overload/README.md#phase-3-paired-comparison)
now supports both scripted checks and live model decisions with fake Gmail.
The [live report](docs/agent-overload-comparison.md) preserves the initial bounded
draft-send failure and a passing focused recheck after clarifying draft IDs versus
saved references.

The [application release checks](docs/agent-overload-release-checks.md) now pass,
including full review through HTTP/proxy/rendering, stored triggers, callbacks,
startup/shutdown, and clearing. They also fix a frontend escape-decoding issue
and close trigger-store connections promptly. The checked bounded strategies are
now the defaults; the [release findings and opt-out guide](docs/agent-overload-release-checks.md)
describe the remaining limits and data-preserving rollback.

The [reduced-scope implementation plan](docs/execution-agent-overload-implementation-plan.md)
keeps name-based dispatch and local JSON/log storage.
[Bounded worker discovery](docs/worker-discovery.md) defaults to
`OPENPOKE_WORKER_DISCOVERY=bounded`: at most five recent entries plus `find_worker`
over all workers, using a small metadata sidecar. Set the flag to `legacy` to opt
out; restart the backend after changing settings. Explicit existing choices are
preserved. Lookup scoring is selectable with `OPENPOKE_WORKER_RANKER`:
`heuristic_v1` (unchanged default), `idf_v1`, or `bm25_v1`. The
[ranking implementation plan and comparison guide](docs/worker-ranking-implementation-plan.md)
records the interfaces, isolated local/agent comparisons, results and promotion
criteria. Ranking methods add no model calls or new service dependencies.
The unused workflow,
migration, and event-storage work is preserved in a
[verified deferred checkpoint](deferred/execution-agent-overload-storage-2026-11-08/README.md)
and removed from the active code and test suite. See the
[progress log](docs/execution-agent-overload-progress.md) for the scope change.

[Shared context preflight](docs/context-budgets.md) defaults to
`OPENPOKE_CONTEXT_STRATEGY=bounded`, with a shipped allowance for the bundled
model and explicit configuration for custom models. It accounts
for complete text requests and rejects over-budget input before HTTP.
[Full-content capture](docs/content-capture.md) now preserves oversized live
messages/results under owner-qualified references in the same bounded mode.
[Bounded source recovery](docs/context-recovery.md) exposes paged `read_result`
and selected-history `recall_history` tools to both agents.
[Bounded outer-agent context](docs/bounded-context.md) now keeps recent episodes
and saves large tool results before previewing them. Required content that cannot
fit fails explicitly. [Exact draft/body references](docs/draft-references.md)
now carry large bodies through Gmail creation, full user review, and confirmation
without repeating them in model arguments. [Inner model context](docs/inner-context.md)
now bounds email search, classification, and streamed summarization, including
cumulative source/result/recovery work. The reduced-scope implementation plan is
complete: comparison, draft-ID follow-up, application checks and default promotion
are recorded. To restore the original strategies without deleting data, set both
`OPENPOKE_WORKER_DISCOVERY=legacy` and `OPENPOKE_CONTEXT_STRATEGY=legacy`, then restart.

## Project Layout

See the [runtime architecture map](docs/architecture-map.md) for the complete query-to-storage flow, labeled API/function calls, worker discovery, callbacks, model context, Gmail drafts, background jobs, and storage layout.

The [known system limitations register](docs/known-limitations.md) tracks current gaps, intentional bounds, deferred capabilities, evidence limits, and resolved findings with stable IDs and source links. Update it when repository work identifies, changes, or resolves a limitation.

- `server/` – FastAPI application and agents
- `web/` – Next.js app
- `server/data/` – runtime data (ignored by git)

## License
MIT — see [LICENSE](LICENSE).
