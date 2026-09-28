# Design Notes

## Part 2 - Session flow: double charge and false confirmation

In `advance_turn`'s `affirm` branch (`app/services/session_flow.py`, lines
31-55) the card is charged on line 36 before anything is persisted (booking,
attempt and session are only written on lines 41-54), and nothing checks for a
prior charge, so the `simulate_crash` path on lines 38-39, or a plain client retry,
charges the member twice; I reproduced `[5000, 5000]` in the provider ledger.
I would create the `Booking` (status `pending`) first, flush it, and write a
`PaymentAttempt` with `idempotency_key=f"session-{session.id}"` and status
`pending` *before* calling `charge()` (the attempt needs the booking's id because
`PaymentAttempt.booking_id` is non-nullable, `models.py` line 95), commit, then
charge and update both rows. At the top of the branch, an existing attempt for that
key means "do not charge again": return the confirmed result if it succeeded, or
reconcile with the provider by the same key if it is still `pending`, which is the
crash case. The same branch also takes `amount_cents` from the request (line 32,
default `0`) and marks the session `confirmed` on line 52 even when
`result.status` is `failed`; the fix is to derive the amount server-side and only
confirm when the charge succeeded. That needs a price source the current schema
does not have, which I would raise with the schema owner rather than add myself.

## Part 3 - Extraction pipeline

**Provider and prompt.** OpenAI Chat Completions with a strict JSON-schema
response format (`kind` is an enum), so malformed shapes are rare; the client
still validates every attribute and treats bad output as a permanent error. The
prompt's few-shot examples come from the *seeded* conversation messages, not from
`eval/golden_set.json`, so the eval isn't scoring examples the prompt has already
seen. The message text is passed as untrusted data and the prompt says so.

**Idempotency key.** A message counts as already processed if a `MemberAttribute`
row exists with `source_message_id == message.id` (`app/routers/extraction.py`,
the `already_processed` query in `_process_message`). No new column was needed;
`source_message_id` already exists for this. The check runs before any API call, so
re-running extraction is one indexed lookup, not a wasted call. This idempotency
also holds under concurrency: `_process_message` first takes a row lock
(`.with_for_update()`) on the `ConversationMessage`, so a second simultaneous
request for the same message blocks until the first commits, then sees its rows
and skips. I did not add a unique constraint because the brief forbids schema
changes. (The lock is a design choice; the tests do not exercise concurrent
requests.)

*Known gap:* a message that legitimately yields zero attributes (small talk)
leaves no row, so it is examined again on every run. That costs an extra LLM call
but never creates duplicate rows. Closing it needs a "processed" marker the schema
doesn't have; I would raise a nullable `processed_at` on `conversation_messages`
with the schema owner.

**Restricted-attribute enforcement.** Extraction and matching share
`member_attributes`, so the boundary is a read-side filter:
`build_member_profile_text` in `app/services/matching_service.py` applies
`MemberAttribute.restricted == False`. `rank_candidates` (the live ranking query)
and `refresh_member_embedding` (which writes `profile_embedding`) both build their
text through that one function, and so does `scripts/seed.py`. A restricted row
can therefore be stored and flagged, and still never reach an embedding or a
similarity score. `test_restricted_attribute_is_stored_but_never_reaches_matching`
proves it, and I confirmed the test fails when the filter is removed. One
operational consequence: embeddings stored before the filter existed still contain
restricted text, so they must be rebuilt (I reset and re-seeded). Extraction itself
does not refresh embeddings; whenever they are built, the filter applies.

**Retry strategy.** `OpenAILLMClient.extract_attributes`
(`app/llm_providers/openai_client.py`) makes up to 4 attempts with exponential
backoff and jitter (about 0.5s, 1s, 2s, each scaled by a random 0.5-1.0). Only
transient failures are retried: timeouts, connection errors, 429 rate limits and
5xx. Everything else fails fast as `PermanentLLMError` with no retry: other 4xx,
refusals, truncated or invalid output, and a 429 whose code is `insufficient_quota`
(retrying an empty billing balance can never succeed). A transient error that
outlives the budget is also surfaced as permanent. The SDK's own hidden retries are
turned off (`max_retries=0`) so this is the only retry strategy in play; the tests
inject the sleep function, so the strategy is verified without waiting or
calling the API.

**Batch failure isolation (message 3 of 5 fails permanently, message 4 succeeds).**
`extract_attributes` loops over `message_ids`, calling `_process_message` for each.
For message 3 the client exhausts its retry strategy and raises `PermanentLLMError`;
`_process_message` catches it, rolls back (releasing the row lock) and returns
`{"status": "failed"}` for that message only. An outer `except Exception` treats
non-LLM errors, such as a database error, the same way. The loop moves on, and
message 4 is processed and committed. Each message commits on its own, so a failure
never rolls back messages 1 and 2, which already succeeded. The response reports a
status per message. `test_extraction_isolates_per_message_failure` covers this.

**Authorization.** `require_club_admin` (`app/auth.py`) requires the admin role
*and* that the admin's `club_id` equals the path `club_id`, so an admin of one club
cannot extract another club's messages. It is the first dependency on the endpoint
so it runs before the LLM client is built. My first version did the club check
inside the handler, and a test showed a cross-club admin reached the client
construction (and failed on the missing API key) instead of getting a 403, because
FastAPI resolves dependencies before the handler body runs.

**Eval and threshold.** `eval/run_eval.py` runs the real client over the golden
set. A record passes only if a single extracted attribute is right on kind, exact
`restricted`, and keywords together. The threshold is 0.75 (3 of 4). With four
hand-labelled records one borderline label (for example context versus interest) is
tolerable noise, while two misses is a real regression. It is a tripwire, not a
quality measure: four records cannot measure quality. The run's output is in
`TERMINAL_LOG.md`.

**Seeded messages and the demo.** Every seeded message already has an attribute
row, so under this idempotency rule all of them count as processed. For the
real-API demo, `scripts/add_demo_messages.py` adds new messages without touching
the seed data.

## Other decisions with a non-obvious alternative

- **404, not 403, for cross-club members in introductions.** A missing member and
  a member in another club return the same 404, so the endpoint cannot be used to
  discover which ids exist in other clubs. A same-club caller who is not a party
  gets 403, since revealing that the members exist there costs nothing.
- **Read-side filter for restricted data, not "don't store it".** The brief
  requires restricted attributes to be stored and flagged (an admin view or audit
  may legitimately need them), so the enforcement has to sit where text is built
  for matching and generated for introductions.
- **One commit per message in extraction.** It keeps a later failure from undoing
  earlier successes, at the cost of more transactions per batch.
- **Retry inside the client, not the router.** Retry policy belongs with the
  provider's error semantics; the router only needs to know "permanent or not".
- **Part 4a is not attempted.** The introductions fix incidentally excludes
  restricted attributes and returns "insufficient basis for an introduction", but
  it has no confidence threshold or audit trail of the attributes used, so I am not
  claiming 4a.
- **Noticed and left alone:** the Node.js and Airtable prerequisites in the brief
  are not used by this repo; `scripts/seed.py` omits `conversation_sessions` from
  its wipe list.

## Closing question

I deliberately did not implement the session-flow payment fix. Part 2 asked for a
design and the brief made the extraction pipeline the required deliverable, and I
judged a rushed change to a payment path, without a proper crash-recovery test, to
be worse than a written design plus a reproduced bug. That leaves a High-severity
money issue open, which I would want to be clear about. I also did not attempt Part
4, did not grow the four-record eval set, did not write a concurrency test for the
row lock, and left the low-severity items (redundant embedding in the ranking loop,
unvalidated turn body) alone.

With one more day I would: (1) fix the payment path as designed above, using a
pending booking and attempt written before the charge, server-side pricing, and
tests driven by `simulate_crash` and the timeout path, after agreeing a price
source with the schema owner; (2) build a labelled eval of around fifty messages
covering hedged statements, multi-attribute messages, small talk and sensitive
cases, and report restricted recall and per-kind precision rather than one
number, since a missed restricted flag is the expensive error; and (3) add one
tenant-scoped query helper so `club_id` cannot be validated but forgotten, which
is the shared cause behind the knowledge and introductions leaks.
