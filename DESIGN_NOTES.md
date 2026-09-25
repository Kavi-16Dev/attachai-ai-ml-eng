# Design Notes

## Part 2 — Session flow double-charge

`advance_turn`'s `affirm` branch (`app/services/session_flow.py`, lines 31–45)
calls `payment_mock_client.charge(amount_cents)` on line ~36 before any row is
written, and never checks whether this session already has a successful charge
on it. I'd fix this by writing a `PaymentAttempt` row with
`idempotency_key=f"session:{session.id}"` and `status="pending"` *before*
calling `charge()`, then querying for an existing attempt with that key and
`status="succeeded"` at the top of the branch — if one exists, return the
already-confirmed result instead of charging again. That covers both failure
modes the code currently reproduces: a client retry after a timeout, and the
`simulate_crash` path where the process dies after `charge()` succeeds
(line ~39) but before `db.add(booking)` / `db.commit()` (lines ~41–45) run —
on restart or retry, the pre-written "pending" attempt is what lets the retry
recognize the charge may already have happened rather than blindly charging
again.

## Part 3 — Extraction pipeline

**Idempotency key.** A message is considered already processed if a
`MemberAttribute` row exists with `source_message_id == message.id`
(`app/routers/extraction.py`, the `already_processed` query). No new column
was added — `source_message_id` already existed on `MemberAttribute` for
exactly this purpose. This is checked, and the LLM is skipped entirely, before
any API call is made, so re-running extraction on a processed message is a
single indexed lookup, not a wasted API call plus a discarded write. This is
the idempotency guarantee the spec requires: re-running extraction never
creates duplicate rows.

**Restricted-attribute enforcement.** Extraction and matching share
`member_attributes` — there's no separate table to firewall them. The actual
check is a `.filter(MemberAttribute.restricted == False)` clause inside
`build_member_profile_text` in `app/services/matching_service.py`, which is
the single function both `rank_candidates` (the live `/members/{id}/candidates`
endpoint) and `refresh_member_embedding` (which writes `profile_embedding`)
call to turn a member's attributes into text before embedding. Because
extraction writes rows with `restricted=True` but never bypasses this
function on the read side, a restricted row can exist in the table and still
never reach an embedding or a ranking score. The enforcement point is the
read-side filter, not a write-side restriction, because the same rows need to
exist for legitimate uses (e.g. an admin viewing a member's full profile).

**Retry strategy.** `AnthropicLLMClient.extract_attributes`
(`app/llm_providers/anthropic_client.py`) retries up to 3 times with
exponential backoff (0.5s, 1s, 2s) for transient errors — rate limits,
timeouts, and 5xx responses, classified in `_call_once` by exception type and
status code. A non-transient failure (4xx other than rate limiting, or a
response that doesn't parse as the expected JSON shape) raises
`PermanentLLMError` immediately, with no retry, since retrying a malformed
prompt response wastes calls without changing the outcome. The extraction
router catches only `PermanentLLMError` per message — a message whose retries
are exhausted, or which failed permanently, is recorded as `"status": "failed"`
in that message's own result and the loop continues to the next message_id,
so one bad message never fails the whole batch.

**Eval threshold.** `eval/run_eval.py` uses 0.75. The golden set is only 4
records, so a single ambiguous label shouldn't fail the eval, but getting 2 or
more of 4 wrong is a real regression at this sample size and should.

## Closing question

<!-- Fill this in yourself once you've actually run the assignment end to
end — this needs to be your genuine judgment about what you skipped and why,
not a template. Things worth being honest about, if true: whether you fully
handled the ambiguous-outcome payment retry (I only sketched the fix, didn't
implement + test it end to end), whether 4a/4b got attempted, whether the
eval threshold or prompt could use another iteration with more real API
runs, whether the extraction prompt needs few-shot examples from the seeded
ConversationMessage data instead of zero-shot. -->

