# Milky Plugin Test Protocol

This protocol covers behavioral tests for Hoshino plugins when the active
adapter is Milky. A test is valid only when it exercises the same dispatch and
send boundaries used by the running bot.

## Required Path

Every message matcher case must follow this path:

1. Build a `message_receive` payload with `MilkyAdapter.json_to_event()`.
   Use a unique `message_seq`, the real message segments, sender data, and
   group/member data when the matcher needs group permissions.
2. Construct a `MilkyBot` from the registered Milky adapter.
3. Call `await bot.handle_event(event)`.
   This is required because it runs Milky's reply, mention, nickname, and
   `to_me` preprocessing before NoneBot dispatch.
4. Stub the Milky HTTP boundary and assert the request. A passing test must
   verify the action name, target ID, and meaningful message payload. Do not
   stop at `matcher.rule()`, `command.parse()`, a direct handler call, or an
   import assertion.

For outgoing messages, the preferred stub is an adapter-level `call_http`
capture (or an equivalent NoneBug API context) that records the Milky action
and JSON data. Patching `send_group_message()` is acceptable only for a focused
message-conversion test, and must be paired with an HTTP/API assertion in the
same representative workflow where the plugin performs a platform call.

## Shared Fixtures

The shared event factory should expose these parameters:

- `scene`: `group`, `friend`, or `temp`
- `text` and concrete Milky message segments
- unique `message_seq`
- `self_id`, `sender_id`, `peer_id`
- optional `group`, `group_member`, and `to_me` inputs

Use a deterministic fake HTTP response for every API the handler reaches.
Never use live QQNT credentials, network calls, or a production endpoint in
the test suite. Keep API payload assertions free of tokens and other secrets.

## Case Selection

Create representative behavioral cases for the changed plugin entries. Select
the entry that best represents each changed behavior:

| Entry type | Required assertion |
| --- | --- |
| native `on_command` / `on_message` | `handle_event()` invokes the handler and the expected outbound API call is emitted |
| Alconna command | command text is accepted through the real event path and the response/API payload is checked |
| regex / startswith / fullmatch | matching and a non-matching boundary case, with outbound behavior for the match |
| notice / request / lifecycle | construct the actual Milky event type, dispatch it, and assert the resulting API call or state change |
| rule-only or import-only plugin | document why no message response exists, then test its actual event/lifecycle entry instead |

At minimum, include cases for:

- private and group message scenes where the plugin supports both;
- `to_me` behavior for commands that require a mention;
- service enable/disable scope for Hoshino services;
- text plus media output, including the Milky segment types and target IDs;
- expected negative input where a matcher must not respond.

## Test Shape

Use this structure for a message case (names are illustrative):

```python
event = make_milky_message(
    text="今天吃什么",
    message_seq=1001,
    group_id=915530476,
    sender_id=34839204,
)
bot = make_milky_bot()
api = capture_milky_http(monkeypatch)

await bot.handle_event(event)

assert api.calls == [
    {
        "action": "send_group_message",
        "data": {
            "group_id": 915530476,
            "message": expected_segments,
        },
    }
]
```

If a handler performs more than one API call, assert the ordered sequence and
stub each response explicitly. Use unique message IDs in each case so
Alconna's message cache cannot make one test reuse another test's input.

## Acceptance Gates

Before a batch is ready for review:

1. Every changed matcher-bearing plugin has representative real entry tests.
2. Each test uses `MilkyBot.handle_event()` and reaches a stubbed Milky API or
   documents a deliberate no-response boundary.
3. No test imports production `.env.prod`, uses real access tokens, or sends
   to a live QQNT endpoint.
4. `uv run pytest nb-tests -q` is green, and focused Milky tests are reported
   separately.
5. Ruff import/format checks and `git diff --check` pass for changed files.
6. The final report names uncovered lifecycle boundaries or plugin-specific
   external dependencies instead of treating import success as coverage.
