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