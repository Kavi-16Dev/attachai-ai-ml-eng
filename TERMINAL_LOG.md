## Setup

$ pip install -r requirements.txt
[...]

$ python -m scripts.seed
Tokens (use as the X-Member-Token header):
  riverside admin: riverside-admin
  oakhurst admin:  oakhurst-admin
  Riverside Member 1: riverside-member-1
  Riverside Member 2: riverside-member-2
  Riverside Member 3: riverside-member-3
  Riverside Member 4: riverside-member-4
  Riverside Member 5: riverside-member-5
  Riverside Member 6: riverside-member-6
  Oakhurst Member 1: oakhurst-member-1
  Oakhurst Member 2: oakhurst-member-2
  Oakhurst Member 3: oakhurst-member-3
  Oakhurst Member 4: oakhurst-member-4
  Oakhurst Member 5: oakhurst-member-5
  Oakhurst Member 6: oakhurst-member-6

## Initial test run (before fixing conftest.py driver mismatch)

$ pytest -v
ImportError while loading conftest 'C:\Users\KishorRamesh\Documents\assessment\attachai-ai-ml-eng\tests\conftest.py'.
tests\conftest.py:9: in <module>
    from app.db import SessionLocal
app\db.py:6: in <module>
    engine = create_engine(settings.database_url, future=True)
..\assess_venv\Lib\site-packages\sqlalchemy\util\deprecations.py:281: in warned
    return fn(*args, **kwargs)  # type: ignore[no-any-return]
..\assess_venv\Lib\site-packages\sqlalchemy\engine\create.py:617: in create_engine
    dbapi = dbapi_meth(**dbapi_args)
..\assess_venv\Lib\site-packages\sqlalchemy\dialects\postgresql\psycopg2.py:697: in import_dbapi
    import psycopg2
E   ModuleNotFoundError: No module named 'psycopg2'

## Fix applied: tests/conftest.py — postgresql+psycopg2:// → postgresql+psycopg://

## Test run after fix

$ pytest -v
platform win32 -- Python 3.14.0, pytest-8.3.3, pluggy-1.6.0 -- C:\Users\KishorRamesh\Documents\assessment\assess_venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\KishorRamesh\Documents\assessment\attachai-ai-ml-eng
configfile: pytest.ini
plugins: anyio-4.15.1
collected 7 items

tests/test_bookings.py::test_confirm_payment_succeeds PASSED                                                                                         [ 14%]
tests/test_introductions.py::test_generate_reason_includes_attributes PASSED                                                                         [ 28%]
tests/test_knowledge.py::test_query_own_club_returns_results PASSED                                                                                  [ 42%]
tests/test_knowledge.py::test_query_rejects_non_member PASSED                                                                                        [ 57%]
tests/test_matching.py::test_rank_candidates_returns_sorted_list PASSED                                                                              [ 71%]
tests/test_sessions.py::test_session_books_end_to_end PASSED                                                                                         [ 85%]
tests/test_sessions.py::test_refund_dispute_escalates PASSED                                                                                         [100%]

## Issue 2 — Introductions endpoint: trace before the fix

A Riverside member asks about Riverside member 3 (who has a restricted attribute) and an Oakhurst member.

PS> curl.exe -s "http://localhost:8000/introductions/5/9?reason=business" -H "X-Member-Token: riverside-member-1"

{"reason_text":"Because manages anxiety, prefers quiet low-key venues and former hospitality business owner, now a consultant — a good business match."}

The response contains a restricted health-related attribute, plus data from an Oakhurst member, in reply to a Riverside caller.

## Issue 2 — Introductions endpoint: trace after the fix

PS> curl.exe -s "http://localhost:8000/introductions/5/9?reason=business" -H "X-Member-Token: riverside-member-1"

{"detail":"member not found"}

## Git state after the fix

(assess_venv) PS> git status
On branch main
Your branch is up to date with 'origin/main'.
nothing to commit, working tree clean

(assess_venv) PS> git log --oneline
d4e013f (HEAD -> main, origin/main, origin/HEAD) fix: authorize introductions, exclude restricted attributes, scope to caller's club
aa9a48f fix: scope knowledge-chunk similarity search to caller's club Add club_id filter to the knowledge query and regression test for cross-tenant isolation
4f4eefb Kindred Concierge — Round 3 assessment starter

## Part 3 - Authorization traces (extraction endpoint)

A member token cannot trigger extraction:

PS> curl.exe -s -X POST "http://localhost:8000/clubs/riverside/extract-attributes" -H "X-Member-Token: riverside-member-1" -H "Content-Type: application/json" -d '{\"message_ids\": [1]}'
{"detail":"admin role required"}

An admin of a different club cannot trigger extraction:

PS> curl.exe -s -X POST "http://localhost:8000/clubs/riverside/extract-attributes" -H "X-Member-Token: oakhurst-admin" -H "Content-Type: application/json" -d '{\"message_ids\": [1]}'
{"detail":"admin of a different club"}

## Part 3 - Batch run on seeded messages (idempotency)

Messages 1-5 already have attributes from the seed script, so the pipeline skips them and makes no API call.

PS> curl.exe -s -X POST "http://localhost:8000/clubs/riverside/extract-attributes" -H "X-Member-Token: riverside-admin" -H "Content-Type: application/json" -d '{\"message_ids\": [1,2,3,4,5]}'
{"results":[{"message_id":1,"status":"already_processed","attributes_created":0},{"message_id":2,"status":"already_processed","attributes_created":0},{"message_id":3,"status":"already_processed","attributes_created":0},{"message_id":4,"status":"already_processed","attributes_created":0},{"message_id":5,"status":"already_processed","attributes_created":0}]}

## Part 3 - Real API run: NOT COMPLETED (OpenAI quota exhausted)

The OpenAI account had no credit remaining, so no real extraction succeeded. Output is shown unedited.

PS> python -m eval.run_eval; echo "exit code: $LASTEXITCODE"
[1] FAIL  error: gave up after 4 attempts: Error code: 429 - {'error': {'message': 'You have no credits remaining. Add credits to continue using the API at https://platform.openai.com/settings/organization/billing/.', 'type': 'insufficient_quota', 'param': None, 'code': 'credit_balance_exhausted'}}
      message: "I'm trying to raise a Series A in the next few months, would love intros to VCs."
[2] FAIL  error: gave up after 4 attempts: Error code: 429 - {'error': {'message': 'You have no credits remaining. Add credits to continue using the API at https://platform.openai.com/settings/organization/billing/.', 'type': 'insufficient_quota', 'param': None, 'code': 'credit_balance_exhausted'}}
      message: "I've led fundraising for three Series A rounds as an operator, happy to help others through it."
[3] FAIL  error: gave up after 4 attempts: Error code: 429 - {'error': {'message': 'You have no credits remaining. Add credits to continue using the API at https://platform.openai.com/settings/organization/billing/.', 'type': 'insufficient_quota', 'param': None, 'code': 'credit_balance_exhausted'}}
      message: "I've been in therapy for the last year and it's helped a lot, just so you understand where I'm at."
[4] FAIL  error: gave up after 4 attempts: Error code: 429 - {'error': {'message': 'You have no credits remaining. Add credits to continue using the API at https://platform.openai.com/settings/organization/billing/.', 'type': 'insufficient_quota', 'param': None, 'code': 'credit_balance_exhausted'}}
      message: 'Does anyone want to join a weekly running club on Tuesday mornings?'

Overall: 0/4 = 0.00  (threshold 0.75)
BELOW THRESHOLD
exit code: 1

Note: this is an account billing failure, not a pipeline defect. The client retried the 429 insufficient_quota error 4 times before giving up, which is wasted effort because a zero balance does not recover on retry. Non-retrying insufficient_quota is a follow-up improvement.

## Final test run

PS> pytest -v
collected 28 items

tests/test_bookings.py::test_confirm_payment_succeeds PASSED
tests/test_extraction.py::test_extraction_happy_path PASSED
tests/test_extraction.py::test_extraction_is_idempotent PASSED
tests/test_extraction.py::test_extraction_requires_admin PASSED
tests/test_extraction.py::test_extraction_rejects_cross_club_admin PASSED
tests/test_extraction.py::test_extraction_isolates_per_message_failure PASSED
tests/test_extraction.py::test_restricted_attribute_is_stored_but_never_reaches_matching PASSED
tests/test_introductions.py::test_generate_reason_includes_attributes PASSED
tests/test_introductions.py::test_introduction_never_includes_restricted_attributes PASSED
tests/test_introductions.py::test_introduction_rejects_member_from_another_club PASSED
tests/test_introductions.py::test_introduction_rejects_member_who_is_not_a_party PASSED
tests/test_introductions.py::test_admin_can_request_introduction_within_own_club PASSED
tests/test_introductions.py::test_introduction_with_only_restricted_attributes_has_insufficient_basis PASSED
tests/test_knowledge.py::test_query_own_club_returns_results PASSED
tests/test_knowledge.py::test_query_never_returns_other_clubs_chunks PASSED
tests/test_knowledge.py::test_query_rejects_non_member PASSED
tests/test_matching.py::test_rank_candidates_returns_sorted_list PASSED
tests/test_openai_client.py::test_retries_transient_errors_then_succeeds PASSED
tests/test_openai_client.py::test_gives_up_after_budget_as_permanent PASSED
tests/test_openai_client.py::test_permanent_error_is_not_retried PASSED
tests/test_openai_client.py::test_parse_normalizes_and_clamps PASSED
tests/test_openai_client.py::test_parse_rejects_invalid_output[...] (5 parametrized cases) PASSED
tests/test_sessions.py::test_session_books_end_to_end PASSED
tests/test_sessions.py::test_refund_dispute_escalates PASSED

28 passed, 60 warnings in 3.64s