# Code Review - Kindred Concierge

Issues are ranked by business impact. Kindred's promise to clubs is that each
club's members, knowledge and data are isolated from every other club's, so
cross-tenant leaks rank above everything else. Payment integrity comes next
because it is money and customer trust; performance and validation come last.
Line numbers refer to the code as cloned (before any fix).

| # | Issue | Category | Severity | Status |
|---|-------|----------|----------|--------|
| 1 | Knowledge search returns other clubs' data | Data Isolation | Critical | Fixed (commit aa9a48f) |
| 2 | Introductions: no authorization, leaks restricted and cross-club attributes | Security / Data Isolation | Critical | Fixed (commit d4e013f) |
| 3 | Payment amount is client-controlled; a failed charge is reported as "confirmed" | Data Integrity | High | Open (design in DESIGN_NOTES.md) |
| 4 | Double charge on retry, crash or timeout | Data Integrity | High | Open (design in DESIGN_NOTES.md) |
| 5 | Restricted attributes feed the matching embedding | Data Isolation | High | Fixed (needed for Part 3) |
| 6 | Requester's embedding recomputed inside the ranking loop | Performance | Low-Medium | Open |
| 7 | Unvalidated `dict` body on the session turn endpoint | Data Integrity | Low | Open |

---

## 1. Knowledge search returns other clubs' data - CRITICAL - Data Isolation

**File:** `app/routers/knowledge.py`, authorization check at line 19, unscoped query at lines 28-33

**Description.** `query_knowledge` checks that the URL's `club_id` equals the
caller's own club (line 19), then runs a nearest-neighbour search over
`KnowledgeChunk` with no `club_id` filter (lines 28-33). Any authenticated member
gets other clubs' knowledge base mixed into their results simply by asking an
ordinary question, using their own club's URL and their own token.

**Why the nearby check does not catch it.** Line 19 authorizes the *request*: it
proves the caller may ask about their own club. It is never attached to the
*query*. The `ORDER BY cosine_distance ... LIMIT 5` on lines 28-33 has no
`WHERE club_id = ...`, so it ranges over every club's rows regardless of who is
asking. Passing the check says nothing about what the query is allowed to touch.

**Trace - before the fix** (own club, own valid token, ordinary question):

```
PS> curl.exe -s "http://localhost:8000/clubs/riverside/knowledge/query?q=dress%20code" -H "X-Member-Token: riverside-member-1"

[{"chunk_id":1,"club_id":"riverside","title":"Guest fees","body":"Riverside guest fees are $50 per visit, waived for members' immediate family."},{"chunk_id":2,"club_id":"riverside","title":"Dress code","body":"Riverside's dress code is smart casual after 6pm, resort wear during the day."},{"chunk_id":8,"club_id":"oakhurst","title":"Cancellation policy","body":"Oakhurst bookings are non-refundable within 48 hours of the reservation."},{"chunk_id":7,"club_id":"oakhurst","title":"Opening hours","body":"Oakhurst is open 6am to midnight, the pool closes at 9pm."},{"chunk_id":6,"club_id":"oakhurst","title":"Dress code","body":"Oakhurst requires collared shirts in all dining areas, no exceptions."}]
```

Three of the five results belong to `oakhurst`.

**Trace - after the fix** (`.filter(KnowledgeChunk.club_id == club_id)` added):

```
PS> curl.exe -s "http://localhost:8000/clubs/riverside/knowledge/query?q=dress%20code" -H "X-Member-Token: riverside-member-1"

[{"chunk_id":1,"club_id":"riverside","title":"Guest fees","body":"Riverside guest fees are $50 per visit, waived for members' immediate family."},{"chunk_id":2,"club_id":"riverside","title":"Dress code","body":"Riverside's dress code is smart casual after 6pm, resort wear during the day."},{"chunk_id":3,"club_id":"riverside","title":"Opening hours","body":"Riverside is open 7am to 11pm daily, kitchen closes at 10pm."},{"chunk_id":4,"club_id":"riverside","title":"Cancellation policy","body":"Riverside bookings can be cancelled up to 24 hours ahead for a full refund."}]
```

**Fix.** Scope the query itself to the club. The regression test
`test_query_never_returns_other_clubs_chunks` stores an identical chunk under both
clubs, so an unscoped query would return both, and asserts only the caller's club
comes back. The same root cause (a `club_id` that is validated but not applied to
the query) is what issue 2 shows in a different endpoint; a shared tenant-scoped
query helper would make it impossible to forget.

---

## 2. Introductions: no authorization, leaks restricted and cross-club attributes - CRITICAL - Security / Data Isolation

**File:** `app/routers/introductions.py`, authentication only at line 17, unscoped queries at lines 19-20, all attributes concatenated at lines 23-25

**Description.** `generate_reason` takes two member ids from the URL and reads
every `MemberAttribute` for both, with no check that either member is in the
caller's club or that the caller is a party to the introduction. It also joins
attributes without looking at `restricted`. Any logged-in member can therefore
read any member's attributes, in any club, including health-related ones
(e.g. "manages anxiety"), by guessing sequential integer ids. Nothing in the
code comments points at this; the only comment concerns confidence.

**Why the existing dependency does not catch it.** `get_current_member` (line 17)
only authenticates the token. It never relates the caller to the two ids in the
path. The sibling endpoint `app/routers/matching.py` lines 19-20 shows the intended
pattern ("can only rank your own candidates"); this endpoint has no equivalent.

**Trace - before the fix** (a Riverside member asks about Riverside member 3, who has a restricted attribute, and an Oakhurst member):

```
PS> curl.exe -s "http://localhost:8000/introductions/5/9?reason=business" -H "X-Member-Token: riverside-member-1"

{"reason_text":"Because manages anxiety, prefers quiet low-key venues and former hospitality business owner, now a consultant — a good business match."}
```

The response contains a restricted health-related attribute, plus data from an Oakhurst member, in reply to a Riverside caller.

**Trace - after the fix:**

```
PS> curl.exe -s "http://localhost:8000/introductions/5/9?reason=business" -H "X-Member-Token: riverside-member-1"

{"detail":"member not found"}
```

**Fix.** Both members must be in the caller's club (a missing member and a
member from another club return the same 404, so the endpoint cannot be used to
probe which ids exist elsewhere); the caller must be one of the two members or
an admin; restricted attributes are excluded and `club_id` is re-applied on the
attribute query. If a member has nothing left to draw on the endpoint says
"insufficient basis for an introduction" instead of emitting a sentence with a
blank side. Tests cover restricted exclusion, cross-club rejection, non-party
rejection, admin access and the insufficient-basis case, and each guard was
confirmed load-bearing by removing it and watching a test fail. Not addressed
here: low-confidence attributes are still stated as fact (the code comment at
line 22); that is the confidence-threshold work in Part 4a.

---

## 3. Payment amount is client-controlled; a failed charge is reported as "confirmed" - HIGH - Data Integrity

**Files:** `app/services/session_flow.py` lines 32, 36, 46, 52, 55; `app/routers/bookings.py` line 29; `app/schemas.py` line 5

**Description.** The charge amount comes straight from the request body
(`payload.get("amount_cents", 0)` on line 32, `payload.amount_cents` in
`bookings.py`), so a caller chooses what to pay, and an `affirm` turn with no
amount charges `0`. The mock provider returns `failed` for that, but line 52 sets
`session.status = "confirmed"` and line 55 returns `"confirmed"` regardless of
`result.status`; only the booking is left `pending` (line 46). The member is told
their booking is confirmed when nothing was paid.

**Reproduce:**

```
curl.exe -s -X POST http://localhost:8000/sessions -H "X-Member-Token: riverside-member-1"
curl.exe -s -X POST http://localhost:8000/sessions/<id>/turn -H "X-Member-Token: riverside-member-1" -H "Content-Type: application/json" -d "{\"intent\":\"book\",\"party_size\":4}"
curl.exe -s -X POST http://localhost:8000/sessions/<id>/turn -H "X-Member-Token: riverside-member-1" -H "Content-Type: application/json" -d "{\"intent\":\"affirm\"}"
```

The last call returns `{"status":"confirmed","booking_id":...}` while the
charge log (`GET /sessions/debug/payment-charge-log` as admin) shows a charge of `0`.

**Recommended fix.** Derive the amount server-side (the schema has no price
source; see DESIGN_NOTES.md), reject a missing or non-positive amount, and only
mark the session and booking confirmed when `result.status == "succeeded"`.

---

## 4. Double charge on retry, crash or timeout - HIGH - Data Integrity

**Files:** `app/services/session_flow.py` lines 31-55 (charge at 36, crash at 38-39, persistence at 41-54); `app/routers/bookings.py` lines 20-31; `app/models.py` line 96

**Description.** In the session flow the card is charged (line 36) before any row
is written (lines 41-54) and there is no check for a prior charge, so a crash or a
client retry after a timeout charges again. In `confirm_payment` there is no check
that the booking is already confirmed (lines 20-29), so calling it twice charges
twice, and a provider timeout returns 504 without recording anything (lines
30-31), leaving no way to tell whether the member was charged. The
`PaymentAttempt.idempotency_key` column (`models.py` line 96) exists for exactly
this and is never used.

**Reproduce** (crash after the charge, then a retry; then read the provider ledger):

```
curl.exe -s -X POST http://localhost:8000/sessions/<id>/turn -H "X-Member-Token: riverside-member-4" -H "Content-Type: application/json" -d "{\"intent\":\"affirm\",\"amount_cents\":5000,\"simulate_crash\":true}"
curl.exe -s -X POST http://localhost:8000/sessions/<id>/turn -H "X-Member-Token: riverside-member-4" -H "Content-Type: application/json" -d "{\"intent\":\"affirm\",\"amount_cents\":5000}"
curl.exe -s http://localhost:8000/sessions/debug/payment-charge-log -H "X-Member-Token: riverside-admin"
```

The ledger ends with `5000, 5000`: two real charges for one booking. Calling
`POST /bookings/<id>/confirm-payment` twice on a paid booking likewise logs two
charges.

**Recommended fix.** See DESIGN_NOTES.md, "Part 2 - session flow".

---

## 5. Restricted attributes feed the matching embedding - HIGH - Data Isolation

**File:** `app/services/matching_service.py`, `build_member_profile_text`, lines 9-12 (the query on line 10 has no `restricted` filter); consumed by `rank_candidates` line 35 and `scripts/seed.py` line 194

**Description.** The function joins every attribute regardless of `restricted`, and
its output is what gets embedded for both the live ranking query and each member's
stored `profile_embedding`. A member's health or therapy context therefore shifts
who they are matched with, which is exactly what the flag exists to prevent.

**Fix.** Filter `restricted == False` in this one function; every embedding path
goes through it, so one change covers all of them. Embeddings already stored
before the fix still contain the restricted text and must be rebuilt (re-seed, or
`refresh_member_embedding`). This is also the enforcement point for Part 3, see
DESIGN_NOTES.md.

---

## 6. Requester's embedding recomputed inside the ranking loop - LOW-MEDIUM - Performance

**File:** `app/services/matching_service.py`, `rank_candidates`, line 35

**Description.** `embedding_client.embed(build_member_profile_text(member, db))`
runs once per candidate although it does not depend on the candidate. With a real
embeddings API that turns one call into N, plus N database reads, with cost that
grows with club size.

**Recommended fix.** Compute `query_vec` once before the loop.

---

## 7. Unvalidated `dict` body on the session turn endpoint - LOW - Data Integrity

**Files:** `app/routers/sessions.py` line 51 (`payload: dict`); `app/services/session_flow.py` lines 20-22

**Description.** The turn endpoint accepts an arbitrary dict and `party_size` is
stored as given. A negative size is accepted (`party_size: -3` returned 200
`awaiting_confirmation`), a non-integer such as `"abc"` produces a 500 from the
database layer, and an unknown or missing `intent` returns 200 without doing
anything.

**Recommended fix.** A Pydantic model with a constrained `intent` and
`party_size: int = Field(gt=0)`.

---

## Other observations (not ranked)

- `tests/conftest.py` used the `postgresql+psycopg2` driver while `requirements.txt`
  installs psycopg v3, so the initial test run failed at import; fixed.
- `scripts/seed.py` clears its tables but omits `conversation_sessions`, so
  re-seeding fails with a foreign-key error once any session exists.
- Member tokens are static, stored in plaintext and never expire (`models.py` line 28).