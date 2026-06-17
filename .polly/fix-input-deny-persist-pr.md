## Summary

- Persist synchronous INPUT-policy DENY sentinels as assistant `message` conversation items while preserving the existing live SSE `response.output_text.delta` deny surfacing.
- Unsuppress `test_policy_gate_deny_persists_to_history` and make it deterministic by asserting the items API immediately after the server-side deny.
- Add focused route/unit coverage that proves `POST /v1/sessions/{id}/events` INPUT DENY is readable from `GET /v1/sessions/{id}/items`.

ELI5: before, the app showed “Denied by policy” on the live stream but forgot to write that message into the conversation notebook. Now it still shows the message immediately and also writes it into history, so later reads and follow-up turns see the same deny marker.

```text
User message
  |
  v
REQUEST policy evaluates input
  |
  +-- ALLOW --> normal persist/forward path unchanged
  |
  +-- DENY --> publish live stream delta (existing)
          \
           +--> persist assistant deny sentinel to conversation_items (new)
                    |
                    v
              GET /v1/sessions/{id}/items returns [Denied by policy: ...]
```

Blast-radius reasoning:
- INPUT DENY still returns the same `{queued: false, denied: true, reason}` body and does not forward to the runner.
- OUTPUT DENY is unchanged; it already rewrites the assistant body and falls through to the normal persist path.
- Non-deny input messages are unchanged because the new helper is only called inside the synchronous INPUT-deny branches.
- The persisted item uses the normal assistant message shape (`role=assistant`, `content=[output_text]`, `model=<agent name>`) so history readers and replay see a legitimate assistant deny item.

## Type of change

- [x] Bug fix
- [ ] Feature
- [ ] Refactor / chore
- [ ] Docs
- [ ] Test / CI
- [ ] Breaking change

## Test coverage

- [x] Unit tests added / updated
- [x] Integration tests added / updated
- [x] E2E tests added / updated
- [x] Manual verification completed
- [ ] Existing tests cover this change
- [ ] Not applicable

## Coverage rationale

Commands run:
- `uv run ruff format omnigent/server/routes/sessions.py tests/server/routes/test_sessions_policy.py tests/server/routes/test_sessions_input_policy_deny.py tests/e2e/test_policies_e2e.py`
- `uv run ruff check omnigent/server/routes/sessions.py tests/server/routes/test_sessions_policy.py tests/server/routes/test_sessions_input_policy_deny.py tests/e2e/test_policies_e2e.py`
- `uv run pytest tests/server/routes/test_sessions_input_policy_deny.py tests/server/routes/test_sessions_policy.py::test_input_policy_deny_sentinel_persists_as_assistant_history -q`
- `uv run pytest tests/server/routes/test_sessions_policy.py -q`
- `uv run pytest tests/e2e/test_policies_e2e.py::test_policy_gate_deny_persists_to_history -q`

Coverage added/updated:
- New route-level regression test posts an INPUT-denied user message, verifies the live deny stream publish still happens, and verifies `GET /items` returns exactly one assistant deny sentinel item.
- Existing policy unit test suite now includes a helper-level test for the persisted assistant item shape.
- The previously suppressed e2e is unsuppressed and now checks the deterministic server-side deny/history behavior directly without relying on a second live model turn.
