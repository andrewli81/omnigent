"""E2E: the optimistic user-message bubble lifecycle in the chat surface.

These browser tests drive the real SPA against a spawned server and
exercise the path a queued/optimistic user message takes:

    send → optimistic bubble renders immediately → server consumes it
    (``session.input.consumed``) → bubble promotes into committed
    history (not dropped, not duplicated) → survives navigation.

They guard the store wiring this change refactored — the
``session.input.consumed`` promotion in ``chatStore.handleSessionEvent``
and the ``bindStream`` snapshot hydration of ``pendingUserMessages``. A
regression in the promote path (dropping the bubble, double-rendering
it, or popping the wrong pending entry) turns these red.

Scope caveat — read before assuming these cover everything:

The ``pending_inputs`` server-side replay this change adds is
**native-terminal only** (claude-native / codex-native): only those
sessions defer persistence to the transcript forwarder and need the
in-memory replay to survive a rebind. The e2e_ui harness runs an
``openai-agents`` agent (``conftest._TEST_AGENT_YAML``) — native claude
needs the ``claude`` CLI binary + tmux, which this harness doesn't
provide. So on this agent the user message persists at POST time and is
re-loaded from ``items`` on navigation; the native ``pending_inputs``
replay itself is covered by the unit tests
(``tests/runtime/test_pending_inputs.py`` and the ``chatStore``
``session.input.consumed`` / ``bindStream`` suites). What these e2e
tests faithfully verify is the **client** lifecycle (optimistic render,
promote-without-drop-or-dup, queue-while-streaming, navigation
hydration) end-to-end through the real SPA.

User-message bubbles are ``data-testid="message-bubble"`` +
``data-role="user"`` (see ``ChatPage.tsx``). The user's own message
text is deterministic regardless of the LLM's reply, so assertions key
off unique sentinel strings — no dependence on model output.

The last tests cover the **docked queue** (``data-testid="queued-message"``):
a follow-up sent while a turn is in flight is POSTed to the server IMMEDIATELY,
and the server queues it into the running task's inbox. The client flags it
``queued`` and shows it as a read-only row above the composer
(``data-queued-state="queued"``) — NOT a transcript bubble — until its
``session.input.consumed`` promotes it inline. The strip has no actions: the
message is already on the server. So the queued strip is exactly "posted, not
yet picked up," observable in the natural in-flight window without gating the
LLM.
"""

from __future__ import annotations

import re

from playwright.sync_api import Page, expect

# Unique sentinels per test so a user bubble is unambiguously locatable
# and can't collide with the assistant's reply text. Worded so the model
# has no reason to echo them verbatim into its own bubble.
_NAV_MSG = "sentinel-nav-7f3a remember this exact phrase"
_PROMOTE_MSG = "sentinel-promote-91b2 keep this bubble"
# Docked-queue test: A holds the turn open so B, sent while A streams, is
# observably queued (docked above the composer) until A finishes and the agent
# picks B up.
_DOCK_MSG_A = "sentinel-dock-a-2f7d hold the turn open"
_DOCK_MSG_B = "sentinel-dock-b-3e9a queued behind the first"

_COMPOSER_PLACEHOLDER = "Ask the agent anything…"


def _user_bubble(page: Page, text: str):
    """Locator for the user-message bubble carrying ``text``."""
    return page.locator('[data-testid="message-bubble"][data-role="user"]').filter(has_text=text)


def _queued_row(page: Page, text: str):
    """Locator for the docked queue row carrying ``text``.

    A queued (posted-but-unconsumed) follow-up renders in the strip above the
    composer (``data-testid="queued-message"``), NOT inline in the transcript;
    once the agent picks it up it leaves the strip and becomes an ordinary
    bubble.
    """
    return page.locator('[data-testid="queued-message"]').filter(has_text=text)


def _send(page: Page, text: str) -> None:
    """Type ``text`` into the composer and click Send.

    Clicks the button by its accessible name ``Send`` — which is present
    only when the composer has a draft (while a turn streams with no
    draft the same button is the ``Interrupt`` square), so a successful
    click also confirms the draft registered.
    """
    composer = page.get_by_label("Message the agent")
    expect(composer).to_be_visible()
    composer.fill(text)
    page.get_by_role("button", name="Send", exact=True).click()


def test_optimistic_user_bubble_renders_then_persists_through_consume(
    page: Page,
    seeded_session: tuple[str, str],
) -> None:
    """Send a message: it renders immediately and stays through the turn.

    Two claims, both about the optimistic-bubble lifecycle:

    1. The user bubble appears right after Send — before any assistant
       output — proving the optimistic render (``pendingUserMessages``)
       fires without waiting on the server.
    2. After the assistant's reply completes (so the message was
       consumed), there is still **exactly one** user bubble with that
       text. A count of 0 means the ``session.input.consumed`` promotion
       dropped the bubble; a count of 2 means it appended a committed
       block without clearing the optimistic one (double-render — the
       exact symptom this change targets).
    """
    base_url, session_id = seeded_session
    page.goto(f"{base_url}/c/{session_id}")

    _send(page, _PROMOTE_MSG)

    # (1) Optimistic render: visible well before the LLM replies.
    expect(_user_bubble(page, _PROMOTE_MSG)).to_be_visible(timeout=10_000)

    # Wait for the assistant turn to complete — a real assistant bubble
    # with non-whitespace text (not the "Working…" shimmer, which has a
    # different testid). This guarantees the consume + promote happened.
    assistant = page.locator('[data-testid="message-bubble"][data-role="assistant"]').first
    expect(assistant).to_have_text(re.compile(r"\S"), timeout=60_000)

    # (2) Exactly one user bubble survived the promote — not dropped, not
    # duplicated.
    expect(_user_bubble(page, _PROMOTE_MSG)).to_have_count(1)


def test_user_message_survives_navigation_away_and_back(
    page: Page,
    seeded_session: tuple[str, str],
) -> None:
    """Send a message, navigate away and back: the bubble re-renders.

    Mirrors the reported symptom ("navigate away and back, the message
    doesn't render until history loads"). After the turn completes we
    leave the conversation (``/`` landing) and return to ``/c/<id>``,
    forcing a cold re-hydration from the snapshot. The user bubble must
    re-render from server state — if it only existed in client-only
    optimistic state it would be gone after the round trip.

    On this (non-native) agent the message is re-loaded from ``items``;
    the native ``pending_inputs`` replay that hydrates an *un-consumed*
    message is unit-tested (see module docstring). This still guards the
    ``bindStream`` hydration path against a regression that drops
    re-rendered user bubbles.
    """
    base_url, session_id = seeded_session
    page.goto(f"{base_url}/c/{session_id}")

    _send(page, _NAV_MSG)
    expect(_user_bubble(page, _NAV_MSG)).to_be_visible(timeout=10_000)

    # Let the turn finish so the message is committed server-side before
    # we navigate (the durable state we expect to re-hydrate).
    assistant = page.locator('[data-testid="message-bubble"][data-role="assistant"]').first
    expect(assistant).to_have_text(re.compile(r"\S"), timeout=60_000)

    # Navigate away to the landing route, then back into the chat.
    page.goto(f"{base_url}/")
    expect(page.get_by_placeholder(_COMPOSER_PLACEHOLDER)).to_have_count(0)
    page.goto(f"{base_url}/c/{session_id}")

    # Re-hydrated from the snapshot — exactly one bubble, no duplicate.
    expect(_user_bubble(page, _NAV_MSG)).to_have_count(1, timeout=30_000)
    expect(_user_bubble(page, _NAV_MSG)).to_be_visible()


def test_message_sent_while_busy_queues_then_promotes_on_pickup(
    page: Page,
    seeded_session: tuple[str, str],
) -> None:
    """A follow-up sent mid-turn queues above the composer, then promotes inline.

    The queued lifecycle end-to-end:

    1. Send A → its turn goes to work. Send B while A is in flight: B is POSTed
       immediately, but the server queues it into the running task's inbox, so
       the client flags it ``queued`` and shows it as a read-only docked row
       (``data-queued-state="queued"``) — NOT a transcript bubble.
    2. The row is read-only — no client-side edit/delete/steer actions, since
       the message is already on the server.
    3. Let A's turn finish → the agent picks B up (``session.input.consumed``);
       B leaves the strip and renders inline as exactly one transcript bubble,
       without any user action, and A is unaffected.

    Steps 1–2 ride the natural in-flight window (client send-time state), so no
    LLM gating is needed; step 3 waits the turn out.
    """
    base_url, session_id = seeded_session
    page.goto(f"{base_url}/c/{session_id}")

    # Send A; as soon as its bubble is up the turn is (about to be) working.
    _send(page, _DOCK_MSG_A)
    expect(_user_bubble(page, _DOCK_MSG_A)).to_be_visible(timeout=10_000)

    # Send B while A is in flight → queued docked row, not a transcript bubble.
    _send(page, _DOCK_MSG_B)
    row = _queued_row(page, _DOCK_MSG_B)
    expect(row).to_be_visible(timeout=10_000)
    expect(row).to_have_attribute("data-queued-state", "queued")
    expect(_user_bubble(page, _DOCK_MSG_B)).to_have_count(0)
    # Read-only: no client-side actions on a posted message.
    expect(row.get_by_test_id("queued-edit")).to_have_count(0)
    expect(row.get_by_test_id("queued-delete")).to_have_count(0)
    expect(row.get_by_test_id("queued-steer")).to_have_count(0)

    # Drain the turn → the agent picks B up. It leaves the strip and renders
    # inline as exactly one transcript bubble; A is unaffected.
    assistant = page.locator('[data-testid="message-bubble"][data-role="assistant"]').first
    expect(assistant).to_have_text(re.compile(r"\S"), timeout=60_000)
    expect(_queued_row(page, _DOCK_MSG_B)).to_have_count(0, timeout=60_000)
    expect(_user_bubble(page, _DOCK_MSG_B)).to_have_count(1, timeout=60_000)
    expect(_user_bubble(page, _DOCK_MSG_A)).to_have_count(1, timeout=60_000)
