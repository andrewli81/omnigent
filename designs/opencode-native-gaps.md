# OpenCode-native: feature-gap closure plan

**Status:** implemented (single PR) · **Owner:** Dhruv Gupta · **Harness:** `opencode-native`

## Implementation status (this PR)

All gaps from the review are closed in one PR:

- ✅ **Compaction (P0)** — real `/compact` (v1 `/summarize`) + auto-compaction surfacing
- ✅ **MCP** — `spec.mcp_servers` → opencode.json + `permission:ask` (policies route through the engine)
- ✅ **Cost tracking (P1)** — `external_session_usage` from per-message cost/tokens
- ✅ **Resume** — text-prefix replay from the Omnigent transcript (no more silent cross-host amnesia)
- ✅ **Fork (P1)** — text-preamble fork (reuses resume rehydration)
- ✅ **In-harness session-cmd sync** — TUI model-switch mirror + (compact/fork/resume above)
- ✅ **Elicitation** — tool-approval round-trip verified + tested (the review's "double-check")
- ✅ **Policies** — confirmed wired to the TOOL_CALL engine; `permission:ask` closes the MCP coverage hole

Each was live-verified against `opencode serve` 1.17.7 where the wire was uncertain.

**Bonus (not in the original gap list) — `question.asked` interactive input:**
opencode's `question` tool (the model asking the *user* a multiple-choice
question, distinct from tool-approval) blocks the turn until answered. This was
characterized live against `opencode serve` 1.17.7 (built+run from source at
HEAD `b60c0a5`) so the integration is grounded in the real wire, not the schema
name:

- **Real event is `question.asked`** (not `question.v2.asked`, despite the
  `QuestionV2*` schema names). Payload:
  `{id, sessionID, questions:[{question, header, options:[{label, description}], multiple}], tool:{messageID, callID}}`.
- **Reply is GLOBAL, not session-scoped:** `POST /question/{id}/reply` with
  `{answers: [[label], …]}` (one inner list per question; single-choice → a
  one-element list). Live-verified: `{"answers": [["Tabs"]]}` → `200` →
  `question.replied` → `session.idle`. `POST /question/{id}/reject` unblocks
  without an answer. (The session-scoped path returns the web SPA, not an API
  route.)
- The web AskUserQuestion card already parses **exactly** this shape via
  `_parse_questions_with_options` (`{question, header, options:[{label,
  description}], multiSelect}`), so the forward leg is a near-direct mapping.

**Landed in this PR (foundation):** the live-verified client methods
`OpenCodeClient.reply_question(request_id, answers)` /
`reject_question(request_id)` (unit-tested), wrapping the two endpoints above.

**Deferred to a follow-up (the web round-trip):** wiring a forwarder
`_on_question_asked` handler + a server **form-elicitation hook** that publishes
the AskUserQuestion card and replies via the client methods. Two parts cannot be
closed from opencode source alone and need the live web UI:
1. **TUI coexistence (race safety).** Like the permission card, a TUI user can
   answer the same question directly; the handler must reuse the
   `_signal_terminal_resolved_harness_elicitation` race guard (first-answer-wins)
   or a naive web intercept breaks TUI interactivity.
2. **Answer mapping.** `ElicitationResult.content` is an MCP-shaped
   `{field: value}` map; opencode wants opencode's *ordered* `[[label]]`.
   Single-question single-select is a deterministic, safe map; multi-question
   ordering must be verified against a real web verdict before shipping.

The tool-approval elicitation path (`permission.asked`) is unaffected by this
gap. See the QA plan for the manual web round-trip needed to promote the
follow-up.

## Background

`opencode-native` (native-server harness: runner spawns `opencode serve`, an
SSE forwarder translates events, a typed HTTP client injects prompts) merged in
PR #576. A post-merge review of the harness feature matrix flagged gaps. This
doc records a **live recon** of opencode 1.17.7's actual API/event surface, then
gives a per-area gap analysis + plan grounded in that evidence. Reference
sibling throughout is **codex-native** (same native-server shape); the
authoritative capability list is the `harness-integration-guide` skill's
native-harness matrix.

Gap-matrix verdicts for the opencode row (✓ = works, ✗ = missing, ? = unknown):

| Capability | Matrix | Resolved verdict |
|---|---|---|
| Connects to Omnigent MCP | ✗ | was missing → **built**: launches the shared `serve-mcp` relay → `sys_*`/`load_skill`/`web_fetch`/comment/policy tools |
| Model override | ✓ | works (per-prompt) |
| Streaming (forwarder) | complete-only | by design for native-server |
| Elicitation (web) | ✓ | **solid** (verified) + a separate `question.asked` surface — foundation landed, web round-trip is a follow-up |
| Policies | ? | **Partial** — TOOL_CALL-phase only (reactive via `permission.asked`). Name-agnostic policies (rate-limit, cost-budget, allow/deny-all) work; tool-name-targeted ones were silently bypassed until the parse fix (the action was read as the literal `"permission"`). REQUEST/PROMPT-phase + TOOL_RESULT-phase policies do **not** fire (opencode has no prompt-submit / post-tool hook). Per-policy name-set coverage still partial — see the policy-coverage note |
| Cost tracking (P1) | ? | was missing → **built** (`external_session_usage`) |
| Interrupt | ✓ | works (abort) |
| Bidirectional sync (TUI→Omni) | ✓ | works |
| In-harness session-cmd sync | ✗ | was missing → **built**: compact + fork + resume + model-switch (both ways) + clear |
| Resume/fork from Omnigent transcript | ✗ | was missing → **built** (text-prefix replay; fork reuses it) |
| Compaction | ? | was missing (web `/compact` faked success) → **built** (P0) |
| Reasoning (P1) | matrix said ✓ but was NOT wired | → **built**: reasoning parts → transient reasoning deltas |
| Images | matrix said ✓ but was NOT wired | → **built**: image parts → image content blocks; non-image files text-flattened |

## Recon: opencode 1.17.7 (live)

**Method:** ran `opencode serve` locally (the pinned 1.17.7 is installed on the
dev box), pulled its OpenAPI from `GET /doc` (390 KB), and drove one live
big-pickle turn capturing the `GET /event` SSE stream. Raw artifacts:
`scratchpad/oc-recon/{openapi-1.17.7.json, events.ndjson, RECON-FINDINGS.md}`.
This dispatched the "needs a live server to confirm" blocker on every item.

Key surfaces discovered (all confirmed present in 1.17.7):

- **Compaction events:** auto-compaction emits `session.next.compaction.started` `{sessionID, messageID, reason: auto|manual}` + `…ended` `{…, text, recent}`; an explicit compaction emits `session.compacted` `{sessionID}` (completion only). **Trigger:** the v2 `POST /api/session/{id}/compact` returns **503 "Session compact is not available yet" in 1.17.x** (verified live) — so use the v1 `POST /session/{id}/summarize`, which **requires `{providerID, modelID}`** (read from the session's `model`) and emits `session.compacted`.
- **Cost/context (live-confirmed shape):** `message.updated` assistant `info` carries `cost` (USD) + `tokens:{input,output,reasoning,cache:{read,write}}`; `Session` carries cumulative `cost`+`tokens`; context window = `Model.limit.context`. Event `session.next.context.updated`.
- **MCP:** `opencode.json` `mcp` block — `McpLocalConfig {type:"local", command:[…], cwd?, environment?, enabled?, timeout?}` / `McpRemoteConfig {type:"remote", url, headers?, oauth?, enabled?}`. Runtime API also: `GET/POST /mcp`, `/mcp/{name}/connect`, `/mcp/{name}/auth`.
- **Permission config:** `opencode.json` `permission` — either a scalar `"ask"|"allow"|"deny"` (applies to all tools) or a per-tool map. We synthesize `opencode.json`, so we control it.
- **Resume/history:** `POST /sync/history`, `/sync/replay`, `/sync/start`; `POST /session/{id}/message`; `GET /session/{id}/message`; `POST /session/{id}/fork` (branch at `messageID`).
- **Session commands:** `POST /session/{id}/command`, `GET /command`, event `command.executed`; `/session/{id}/revert` + `/unrevert` (= undo/redo).
- **Questions (elicitation gap):** a surface *separate* from permissions — `question.v2.asked {questions[], tool}` + `/session/{id}/question/{rid}/reply|reject`. The forwarder ignores it today. "Always" decisions persist server-side via `/api/permission/saved`.

## Two clarifications (raised in review)

**1. "The compact button" = the `/compact` slash command.** There is no separate
button. `/compact` is a built-in slash command in both the web composer
(`ap-web` `BUILTIN_SLASH_COMMANDS["/compact"]`) and the REPL
(`omnigent/repl/_repl.py` `@_cmd("/compact")`). The web sends it as
`postEvent({type:"compact"})` (`ap-web/src/store/chatStore.ts:1253`) →
server `_COMPACT_TYPE` (`sessions.py`) → runner control dispatch
(`runner/app.py` ~11523). The runner dispatch only branches on
claude-native/codex-native; **opencode falls to a 204 no-op, so the server then
runs its own AP-side compaction on the Omnigent conversation store** — which is
NOT what opencode sends to the model. Net: `/compact` on an opencode session
emits a `response.compaction.completed` marker while opencode's real context is
untouched (a correctness lie). opencode has a real `POST .../compact`, so we can
make `/compact` genuinely compact opencode. **Recommendation: make it real.**

**2. "Will policies just WORK either way?" — yes, with native config + force-ask.**
- *Precedent:* codex/claude-native expose Omnigent tools via a **relay** — one
  `omnigent` MCP server (`serve-mcp`) that proxies the active toolset; every
  call (incl. MCP) hits the central proxy + policy engine. Guaranteed, but it
  means porting the whole `bridge.json`/`tool_relay.json` relay to opencode (L).
- *Native config path:* we synthesize `opencode.json`, so we write **both** the
  `mcp` block **and** `permission: "ask"`. opencode then emits `permission.asked`
  for tool calls (incl. MCP tools), which the forwarder already routes through
  Omnigent's `TOOL_CALL` policy engine (`opencode_native_permissions.py` +
  `runner/app.py` `_build_opencode_policy_evaluator`) — the same path that
  already gates opencode's built-in tools (confirmed wired + tested). So
  **policies work under native config**, provided we force opencode to ask.
  *Caveat:* a tool opencode is configured to auto-allow would bypass the gate —
  but we own that config, so we don't auto-allow.
- **Recommendation: native `opencode.json` MCP + `permission: ask`.** Far smaller
  than the relay, and policies still "just work." Revisit the relay only if a
  future requirement needs central TOOL_RESULT gating or proxy-side redaction
  (opencode's reactive model can't pre-gate tools opencode never asks about).

## Per-area plan

Each area: **current state → gap → recon evidence → approach → effort/risk.**
All land in `opencode_native_forwarder.py` / `opencode_native_provider.py` /
`runner/app.py` unless noted; server-side contracts are reused as-is.

### 1. Compaction — **P0**
- **Current:** nothing. Auto-compaction is invisible to Omnigent; explicit `/compact` fakes success (see clarification 1).
- **Approach (two parts):**
  - *Surface auto-compaction (additive, no server change):* handle `session.next.compaction.started` → post `external_compaction_status` `in_progress`; `…ended` → `completed`. Reuses claude-native's existing inbound wire contract (`response.compaction.*`). Also drives the web "compacting" marker.
  - *Make `/compact` real:* add `_handle_opencode_native_compact` to the runner control dispatch (mirror `_handle_codex_native_compact`, but HTTP not tmux) that resolves the session's model and calls `POST /session/{id}/summarize` via the client, returning 200 so the server stops running the AP-side fake (204 when no live server → graceful fallback; 503 on failure). Completion flows back through the `session.compacted` / `…ended` handler.
- **Effort:** S–M · **Risk:** low for surfacing; medium for the dispatch (touches the shared runner control path + the server's compact-fallback semantics — scope carefully so codex/claude are unaffected).

### 2. MCP
- **Current:** none; agent MCP tools absent in opencode.
- **Approach:** in `opencode_native_provider.py`, add `build_opencode_mcp_block(spec.mcp_servers)`: stdio → `{type:"local", command:[cmd,*args], environment:env}`; http → `{type:"remote", url, headers}` (+ resolve `databricks_profile` → `Authorization: Bearer` header, reusing `resolve_databricks_gateway`'s pattern). Merge into the synthesized `opencode.json` alongside `provider`/`model` in the `runner/app.py` spawn flow. Set `permission: "ask"` so MCP tool calls route through the policy engine (clarification 2). Secrets ride the existing atomic-0600 writer.
- **Effort:** S–M · **Risk:** low (gated on `spec.mcp_servers`; reuses the 0600 writer + spawn chokepoint).

### 3. Resume — **high**
- **Current:** resumes only by the persisted opencode `external_session_id`. Same-host relaunch works (per-session `XDG_DATA_HOME` persists opencode's store). **Cross-host / wiped-store resume silently starts an empty session — the web transcript shows history but the agent has amnesia, no error.**
- **Approach:** when `get_session(external_session_id)` returns `None` on a resume that *had* an id, (C) at minimum surface the failure instead of silent amnesia, then (A) rehydrate from the Omnigent transcript: `GET /v1/sessions/{id}/items` (mirror codex's paginated fetch) → seed a fresh opencode session via `POST /session/{id}/message` and/or the `/sync/history`/`/sync/replay` primitives. Confirm the `/sync/history` body shape against the live server before committing to it.
- **Effort:** M · **Risk:** medium — hinges on how opencode accepts back-dated/non-executing history (token cost, tool-call representation). Ship (C) first.

### 4. Cost tracking — **P1**
- **Current:** none; `message.updated` cost/tokens dropped. Context ring, cost badge, and cost-budget policy all dead for opencode.
- **Approach:** in the forwarder, accumulate `info.cost` + `info.tokens` per assistant `message.updated`; post `external_session_usage {context_tokens, context_window, cumulative_cost_usd, cumulative_*_tokens, model}` (context_window from `Model.limit.context`) on message.updated + `session.idle`. Reuses codex's `external_session_usage` contract verbatim; server prices via `cumulative_cost_usd` directly. Live-confirmed token/cost shape.
- **Effort:** M · **Risk:** low (additive; cosmetic worst case).

### 5. Fork — **P1**
- **Current:** `transport.fork()` + `POST /session/{id}/fork` exist but are wired to nothing; opencode is absent from `_FORK_HISTORY_NATIVE_HARNESSES`.
- **Approach:** add `opencode-native` to `_FORK_HISTORY_NATIVE_HARNESSES` (`sessions.py`); add `fork_source_*` fields to the opencode launch config + a fork branch in `_auto_create_opencode_terminal` that calls `client.fork(source, {messageID})` for same-harness sources, falling back to the resume-rehydration path (#3) for cross-family sources. Simpler than codex (opencode has a first-class fork endpoint). Build on #3.
- **Effort:** M · **Risk:** low–medium.

### 6. In-harness session-cmd sync
- **Current:** neither direction. Omnigent `/compact` (and clear/fork/resume) don't reach opencode; TUI-typed `/model`, `/compact`, `/undo` don't mirror back.
- **Approach:** Omnigent→opencode via `POST /session/{id}/command` (the matrix's "clear/fork/resume/switch"); the `/compact` half is covered by #1. opencode→Omnigent: handle `command.executed` (+ mirror `/model` to `model_override`, surface `/compact`/`/undo` as `slash_command` items). Overlaps #1/#3/#5; do last.
- **Effort:** M–L · **Risk:** low–medium.

### 7. Elicitation (verify) + Policies (verify/harden)
- **Elicitation:** ✓ solid (full permission.v2 round-trip, fail-closed, tested). Harden: (C1) the typed `transport.reply_permission` is dead code parallel to the live forwarder path — unify or delete to prevent drift; (C2) a failed `POST .../reply` is swallowed → opencode-side hang — retry/reconcile via `GET /session/{id}/permission`. **New (C3):** handle the separate `question.asked` input-request surface (currently ignored) as a form elicitation — **foundation landed** (`reply_question`/`reject_question`, live-verified + tested); the forwarder handler + server form-hook + TUI race guard remain (see the bonus section). Effort S (C1) / M (C2, C3).
- **Policies:** wired to the TOOL_CALL engine (allow/deny/ask honored), reactive via `permission.asked`. Honest coverage limits (audited after the file/shell-approval bug):
  - **Phase (current integration):** only TOOL_CALL (pre-execution) fires, because the integration is reactive over the SSE `permission.asked` stream. So today REQUEST/PROMPT-phase policies (prompt-injection, PII-in-prompt, per-prompt cost) and TOOL_RESULT-phase policies (gate/redact tool output) do **not** enforce. **This is an integration gap, NOT an opencode limit** — opencode exposes a first-class **plugin hook** API (`packages/plugin`) covering every stage: `chat.message`/`chat.params` (REQUEST), `tool.execute.before` + `permission.ask` (TOOL_CALL; `permission.ask` sets `output.status` to allow/ask/deny), and `tool.execute.after` (TOOL_RESULT). An Omnigent opencode plugin that bridges these to `/policies/evaluate` (like claude's `UserPromptSubmit`/`PreToolUse`/`PostToolUse` hooks) would close the REQUEST + TOOL_RESULT gaps and supersede the reactive permission path. Loadable via the synthesized `opencode.json` `plugin:[...]` field (or a file in the per-session config plugin dir). Tracked as the proper full-phase follow-up.
  - **Tool name:** opencode's `permission.asked` carries the action in `permission` (v1) as a CATEGORY (`bash`/`edit`/`read`/`grep`/`glob`/`skill`/`webfetch`/…). The parser read only `action`/`type`, so the policy tool name was the literal `"permission"` and **no tool-name-targeted policy matched** (file/shell approval, skill block, github/google gating all silently ALLOWed). Fixed: parser reads `permission`/`patterns`; `ask_on_os_tools` gained the opencode categories.
  - **Per-policy name-set gaps still open:** `block_skills` doesn't recognize opencode's `skill` category (and the skill name rides in `patterns`, not the forwarded args — Omnigent `load_skill` via the relay IS covered); the github/google policies gate shell commands via a default `sys_os_shell`-only set (misses every native harness's shell tool — broad/config-dependent, not opencode-specific); `risk_score`'s risk table is keyed by canonical names, so opencode categories score as default.
  - Name-agnostic policies (rate-limit, cost-budget, allow/deny-all) were unaffected throughout.

## Recommended sequence

1. **P0 compaction** (surface auto-compaction + make `/compact` real)
2. **MCP** (native config + `permission: ask`)
3. **Resume** (surface failure → rehydrate from transcript)
4. **Cost tracking** (P1)
5. **Fork** (P1; builds on resume)
6. **Session-cmd sync** (builds on 1/3/5)
7. **Elicitation/policy hardening** (C1–C3 + force-ask)

Each is an independent, reviewable PR. 1–5 reuse existing server contracts (no
server changes except the compact-dispatch arm in #1).

## Open questions

1. `/sync/history` request-body shape — verify against the live server before choosing it for resume rehydration (vs. re-injecting via `POST /session/{id}/message`).
2. opencode's behavior for back-dated/non-executing history messages (cost, ordering, tool-call representation) — gates resume Option A.
3. Whether to ever build the MCP relay (central TOOL_RESULT gating) — deferred; native config + force-ask is the plan.
4. ~~`question.v2` payload — capture a real fixture to shape the form-elicitation mapping (C3).~~ **Resolved:** real event is `question.asked` with `{questions:[{question, header, options:[{label,description}], multiple}], tool}`; reply via GLOBAL `POST /question/{id}/reply {answers:[[label]]}` (live-verified). Foundation client methods landed; the web round-trip + TUI race guard remain the follow-up (see the bonus section above).
