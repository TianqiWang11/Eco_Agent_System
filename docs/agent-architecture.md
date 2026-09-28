# Agent runtime — first implementation

## Scope and deployment

The App Server uses `src/agent` for both `/agent/*` and the synchronous
`/chat` transport. Old orchestration, parser, pipelines and composer have been removed.
Only the original Python business tools are inherited into `tools/local_tools/`.
Get_data owns import adapters but reads active analysis data from PostgreSQL. Knowledge
retrieval uses an independent LlamaIndex + Chroma persistent vector database. Predict owns its trained model and code-defined
workbook template, while platform data APIs live in `src/platform/data`.

This is a **modular, single-host/single-worker runtime**, not a production distributed
scheduler. Run one Uvicorn worker against a state directory. SQLite transactions,
revision checks, durable checkpoints and an in-process execution queue establish
boundaries that can later be replaced by a distributed store/worker system.
Do not run two App Servers against the same state directory: startup recovery assumes
exclusive ownership. No automatic multi-process failover or exactly-once side effects
are claimed.

```text
src/agent/
  contracts.py             five finite Agent Actions, ToolCall, ModelClient, ToolSpec
  harness/
    loop.py                seven-stage bounded Agent Action loop
    actions.py             strict Action validation, execution and loop control
    context.py             Context Manager, paired-message compaction, result refs
    prompts.py             stable System Prompt and finite Action policy
    model.py               provider response → finite Action contract adapter
    provider.py            model connection settings, no routing or answer generation
    dispatcher.py          schema validation, write-ahead execution ledger, approvals
    policy.py              explicit network endpoint allowlist
  session/store.py          Events + Task State + Checkpoints in SQLite
  tools/
    registry.py            explicit tool registry, JSON Schema validation
    local_tools/           original Python functions + new structured adapters/registration
    mcp.py                 MCP tools and resources through Streamable HTTP
  environment/             PostgreSQL business-data repository/bootstrap
  sandbox/
    interface.py           SandboxInterface
    local.py               LocalSandbox: trusted file operations only
    docker.py              DockerSandbox: opt-in generated Python execution
    workspace.py           session-isolated workspace paths
    manager.py             SandboxManager, no silent host fallback
  telemetry/events.py      safe event projection; OTLP Trace / Log / Metrics
  runtime.py               composition root and task scheduling
  api.py                   capability-protected task, HITL and SSE endpoints
```

## Harness and context engineering

`ToolCallingModel` uses the new `harness/provider.py` connection settings and
maintains an HTTP client with an allowlisted endpoint and redirects disabled.
The configured model is not replaced. Every model step is forced through structured
tool calling and must resolve to exactly one of five discriminated Agent Actions:
`Respond`, `Ask_User`, `Call_Tool`, `Wait`, or `Finish`. Plain model text, unknown
Action types, extra fields, a control Action mixed with business tool calls, unknown
tools, invalid parameters and duplicate call IDs all fail closed. `Call_Tool` contains
one to four typed calls. Execution is sequential; each turn has at most eight Actions.
Provider timeouts and bounded retries use existing configuration. There is no automatic
fallback to a different model/provider on error.

The Harness follows one explicit lifecycle:

```text
load/create Session + State
          ↓
Context Manager builds context
          ↓
model selects exactly one finite Action
          ↓
validate Action and all tool parameters
          ↓
execute Action
          ↓
persist Session + State + checkpoint
          ↓
loop control: continue / pause / stop
```

`Respond` and `Finish` both terminate the current turn; their separate types preserve
intent in the trace. `Ask_User` pauses in `awaiting_input`. `Wait` is non-blocking and
pauses in `waiting` until an explicit resume. `Call_Tool` is the only Action that may
invoke tools; successful or structured replay-safe error results can enter the next
Action step. The model cannot emit an unclassified executable instruction.

Context Manager owns the system instructions, task objective, conversation selection,
tool-result previews and compaction. It uses a conservative **24,000-character**
serialized input budget (including tool schemas), not an exact token-count claim.
Whole assistant/tool-response blocks are compacted together; current query and task
objective are preserved. Compaction is extractive and lossy, not an LLM-generated
semantic memory. Full earlier task states remain in checkpoints. Completed tool results
remain in the ledger; `session_result(call_id, offset)` provides bounded text paging.
Binary chart artifacts are kept out of model context. A schema/prompt that alone exceeds
the budget is rejected instead of silently truncating system instructions.

All MCP/resource/tool content and historical excerpts are treated as untrusted data.
Model-generated reasoning is neither persisted deliberately nor streamed to the UI.
Prompts and tool results remain in the private durable task state; protect its filesystem
permissions and backup/retention policy. These are not encrypted at rest by this runtime.

There is only one model-driven loop. Local tools take typed parameters (dataset, year,
metric, operation, filters), not an old planner's free-text query or parsed state.
Knowledge retrieval returns evidence; response generation belongs to Harness.
Existing credential environment names are accepted only as connection configuration.
The original plotting library has more functions than the new registered tool surface:
specialized comparison/composite charts are retained as functions, not yet exposed tools.
A trained species-aware DBH growth model is exposed only through the typed `predict`
tool. `plot_id` is a validation grouping key, not a model feature. Tree shape fields
are experimental extrapolations from 2025 allometric relationships. Prediction calls
return an in-memory `.xlsx` artifact; the canonical workbook layout is defined in
`tools/local_tools/predict/tool.py`, not an external template file.

## Durable Session and recovery

Default state: `storage/agent/sessions.sqlite3`, ignored by Git.
The Session contains objective, current prompt, short memory, conversation blocks,
current Action, bounded Action history, pending calls, execution ledger, results,
approval/input/wait state, step budget and final response.
SQLite stores session snapshots, revisions, checkpoint history and safe ordered events.

New sessions use contract version 4. Earlier snapshots remain readable, but resume and
follow-up are rejected for earlier contracts to avoid executing stale tool parameters.
Create a new task after updating; historical task data is not deleted.

```text
queued → running → completed
             ├→ awaiting_approval → queued → running
             ├→ awaiting_input → queued → running
             ├→ waiting → queued → running
             └→ failed
process restart: queued/running → interrupted
explicit resume: interrupted/failed/waiting → queued (only when safe)
```

Before invoking a tool, its call ID and argument fingerprint are saved as `started`.
After completion, the JSON result is saved before proceeding. Resuming a pending group
reuses completed results, never repeating them. A non-replay-safe call left `started`
may have produced an external effect: automatic resume is refused until an operator
reconciles the external state. There is currently no UI to manually rewrite that ledger;
create a new task only after checking the external outcome. Completed UE instructions
mean generated delivery requests, not proof of UE execution.

Approvals bind to the exact call and arguments via a digest. Stale/repeated approvals
are refused. A denial is returned to the model as a tool result. Model calls cannot
approve their own tools or change policy. Scene changes and generic MCP operations
require approval. Existing trusted ecological
calculations and local reads run without an extra prompt.

Long-running work continues after the browser disconnects. A refresh can replay safe
events using the event cursor. Runtime has one execution worker (some scientific
libraries may use global state) and a 16-task in-flight queue. No arbitrary host process
cancellation is implemented; failure/resume and paused approvals are supported.

## MCP Tools and Resources

The repository-level `config/mcp.json` enables Exa's hosted Streamable HTTP MCP
endpoint for keyless, rate-limited web search. Set `AGENT_MCP_CONFIG` only when an
operator needs to override that configuration. Current configuration:

```json
{
  "servers": {
    "exa": {
      "url": "https://mcp.exa.ai/mcp",
      "capabilities": {
        "web_search": {
          "tool": "web_search_exa"
        }
      }
    }
  }
}
```

`token_env` is optional and names a server-side environment variable; do not put secrets
in the JSON file or URLs. For production Exa usage, store `EXA_API_KEY` only in `.env`
and add `"token_env": "EXA_API_KEY"` to the server configuration. The model sees configured
server aliases, not credentials. Tools exposed are `web_search`, `mcp_list_tools`,
`mcp_call_tool`, `mcp_list_resources`, and `mcp_read_resource`. Discovery supports pagination. Calls validate
against the server-advertised schema; external JSON Schema references are forbidden.
Resource URIs are passed to the configured MCP server, never fetched as arbitrary URLs
by our host. MCP errors remain structured results and emit failed-tool events.
The stable, read-only `web_search` capability is pre-approved. Generic MCP calls and
resource operations remain approval-gated.

SDK 1.x Streamable HTTP is supported. Stdio execution, automatic OAuth, server sampling,
elicitation and dynamic arbitrary server registration are intentionally not enabled.
Requests have timeouts, HTTP redirects are disabled, and URLs are checked against the
operator list. A configured server is a trust boundary: its own outbound access and
side effects are not controlled by our Docker sandbox. Network policy here is an
application allowlist, **not a host firewall**, and does not cover arbitrary local tool
network calls. Production must add gateway/egress controls and response size limits.

## Sandbox (deferred)

Sandbox code is retained as a future boundary, but it is not constructed and its tools
are not registered in the current Runtime because no active platform capability needs
model-generated code execution.

`LocalSandbox` only reads/creates UTF-8 files in a session workspace (64 KiB limit),
rejects path escape/absolute paths/Windows alternate streams and refuses overwrite.
It never runs generated Python or shell commands. This trusted adapter is not an OS
isolation mechanism and assumes no hostile same-user process changing filesystem paths.

`DockerSandbox` requires an installed, running Linux-container Docker engine, a
pre-provisioned image, and `AGENT_DOCKER_ENABLED=true`. Runtime will **not pull images**.
For reproducible deployments, set `AGENT_DOCKER_IMAGE` to an approved immutable digest.
It uses no network, a read-only root and workspace mount, non-root UID, dropped
capabilities, no-new-privileges, memory/CPU/PID/time/output limits and a temporary `/tmp`.
Output is returned as bounded text. Durable generated files can subsequently be created
through the approved workspace tool. Host code execution is never a fallback.

Docker is defense-in-depth, not a hardened boundary for mutually hostile tenants.
This development machine has no Docker command installed; command construction and
disabled-mode behavior are tested, actual container execution has not been verified.

## Telemetry and frontend

Each module emits detailed developer events to the private checkpoint database and
OpenTelemetry. The user SSE is a separate projection containing only a stable stage and
generic message such as “正在理解你的需求” or “正在调用工具处理任务”. It never contains
tool names, parameters, Session state, prompts, result bodies, exception text, reasoning
or secrets. The user task endpoint exposes only a coarse phase and required interaction.

With `AGENT_OTLP_ENDPOINT=http://127.0.0.1:4318`, traces, logs and metrics are exported
to `/v1/traces`, `/v1/logs`, `/v1/metrics`. Run/model/tool spans and session IDs correlate
execution; resumed runs can have new traces. Without a collector, UI events still work.
Exporter failures do not decide task success or affect approvals.

The frontend consumes a curated **SSE execution-event projection**, not the collector.
It never receives operational Logs/Metrics. The task panel supports task selection,
event replay, exact-call approve/deny and safe resume without growing the UE panel.
Rendering uses textContent, not server-supplied HTML. History selection never replays
old UE actions automatically.

## API and access

| Endpoint | Purpose |
| --- | --- |
| POST `/agent/sessions` | Create task; returns session ID and a random capability token |
| GET `/agent/sessions/{id}` | Public task state, final result, pending approval |
| POST `/agent/sessions/{id}/turns` | Follow-up within a completed session |
| GET `/agent/sessions/{id}/events?after=N` | SSE replay/live events |
| POST `/agent/sessions/{id}/approval` | `{digest, allow}`; approved or denied once |
| POST `/agent/sessions/{id}/resume` | Explicit safe recovery |
| POST `/chat` | Synchronous transport over the same runtime; returns task references |

Except creation, task endpoints require `Authorization: Bearer <session-token>`.
Tokens are hashed in SQLite; never put them in query strings. The browser keeps up to
20 task references in sessionStorage (refresh survives; closing the tab can lose them).
This is capability-based demo access, not account-level identity, task ownership or
production RBAC. The current app still has unauthenticated development endpoints and
CORS. **Bind to localhost or a trusted network; do not expose publicly** before adding
login, per-user ownership, rate limits, retention, TLS and durable authenticated task lists.

## Run and validate

From the repository root, install `requirements.txt` into the project venv. This environment
does not bundle pip; a system pip can target it with:

```powershell
py -3.14 -m pip --python .venv/Scripts/python.exe install -r requirements-agent.txt
.venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider
.venv/Scripts/python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000 --workers 1
```

Tests use fake models plus the real HTTP/MCP clients against local protocol fixtures,
and an actual local OTLP HTTP receiver. They do not call a paid model, external MCP
or Docker. `tests/agent-ui-smoke.cjs` uses a mock API and headless Chrome to test SSE,
approval, reload/replay and stable visualization size; supply Node's `ws` via installed
dependencies or `AGENT_WS_MODULE`. Use `AGENT_CHROME` for a non-default Chrome path.

Live provider acceptance, real external server credentials, production collector
deployment and actual Docker isolation still require environment-specific acceptance.
The Session SQLite database is infrastructure state, not the future ecology database.

## Official references consulted

- Kimi API platform: https://platform.moonshot.ai/docs
- MCP Python SDK 1.x: https://github.com/modelcontextprotocol/python-sdk/tree/v1.x
- OpenTelemetry Python: https://opentelemetry.io/docs/languages/python/instrumentation/
