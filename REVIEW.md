# Code Review — Kindred Concierge

Prioritized by business impact. Kindred's core promise to clubs is data isolation
("each club's members, knowledge, and data are isolated from every other club's"),
so cross-tenant leaks rank above performance issues even where the leak looks small
in the diff.

---

## 1. Cross-tenant knowledge leak — CRITICAL — Security / Data Isolation

**File:** `app/routers/knowledge.py`, lines 19–33

**Description:** `query_knowledge` checks that the caller belongs to the `club_id`
in the URL (line 19), then embeds the query and runs a nearest-neighbour search
over `KnowledgeChunk` with no `club_id` filter (lines 28–33). The authorization
check validates the *request*; it is never applied to the *query*. Any authenticated
member of any club can retrieve another club's knowledge base simply by asking a
question — no need to know the other club's ID or guess anything.

**Why the nearby check doesn't catch it:** the `if club_id != member.club_id`
check on line 19 only proves the caller is allowed to *ask about* their own club.
It says nothing about what the database query below is scoped to. There's no
`.filter(KnowledgeChunk.club_id == club_id)` anywhere in the query, so the
`ORDER BY cosine_distance / LIMIT 5` runs across every club's chunks.

**Trace (own club, own valid token, ordinary question):**

```
$ curl.exe -s "http://localhost:8000/clubs/riverside/knowledge/query?q=dress%20code" \
  -H "X-Member-Token: riverside-member-1"

[{"chunk_id":1,"club_id":"riverside","title":"Guest fees","body":"Riverside guest fees are $50 per visit, waived for members' immediate family."},{"chunk_id":2,"club_id":"riverside","title":"Dress code","body":"Riverside's dress code is smart casual after 6pm, resort wear during the day."},{"chunk_id":8,"club_id":"oakhurst","title":"Cancellation policy","body":"Oakhurst bookings are non-refundable within 48 hours of the reservation."},{"chunk_id":7,"club_id":"oakhurst","title":"Opening hours","body":"Oakhurst is open 6am to midnight, the pool closes at 9pm."},{"chunk_id":6,"club_id":"oakhurst","title":"Dress code","body":"Oakhurst requires collared shirts in all dining areas, no exceptions."}]
```

3 of the 5 results returned belong to `oakhurst`, not `riverside` — confirmed with a valid Riverside member token against Riverside's own endpoint.

**Recommended fix:** add `.filter(KnowledgeChunk.club_id == club_id)` to the query.
More generally, any query against a table with a `club_id` column should be scoped
by a single shared helper/mixin rather than relying on each router remembering to
add the filter — that's the "actual cause" fix per Part 2's instructions, not a
one-line patch to this one endpoint.

```
**After fix** (added `.filter(KnowledgeChunk.club_id == club_id)`):

$ curl.exe -s "http://localhost:8000/clubs/riverside/knowledge/query?q=dress%20code" \
  -H "X-Member-Token: riverside-member-1"

[{"chunk_id":1,"club_id":"riverside","title":"Guest fees","body":"Riverside guest fees are $50 per visit, waived for members' immediate family."},{"chunk_id":2,"club_id":"riverside","title":"Dress code","body":"Riverside's dress code is smart casual after 6pm, resort wear during the day."},{"chunk_id":3,"club_id":"riverside","title":"Opening hours","body":"Riverside is open 7am to 11pm daily, kitchen closes at 10pm."},{"chunk_id":4,"club_id":"riverside","title":"Cancellation policy","body":"Riverside bookings can be cancelled up to 24 hours ahead for a full refund."}]

All 4 results now belong to riverside. Confirms the fix closes the leak.
```
---

## 2. No authorization on introductions; leaks restricted attributes — CRITICAL — Security / Data Isolation

**File:** `app/routers/introductions.py`, lines 11–25

**Description:** `generate_reason` takes `member_a_id`/`member_b_id` from the URL
and never checks that the requesting member belongs to the same club as either of
them, or that the requester is one of the two parties. It also concatenates every
`MemberAttribute` for both members with no filter on `restricted` — so a caller
who can enumerate member IDs gets other clubs' members' health/therapy attributes
verbatim in the response text.

**Recommended fix:** require `member.club_id` to match both members' `club_id`,
and exclude `restricted=True` attributes from `a_text`/`b_text`.

---

## 3. Restricted attributes feed the matching embedding — HIGH — Data Isolation / Privacy

**File:** `app/services/matching_service.py`, `build_member_profile_text`, lines 9–11

**Description:** The function joins every attribute for a member with no filter
on `restricted`, and this text is what gets embedded for both the candidate-ranking
endpoint and the stored `profile_embedding`. A member's therapy/health context can
measurably shift who they're matched with, even though it's flagged restricted
specifically so it wouldn't be used this way.

**Recommended fix:** filter `.filter(MemberAttribute.restricted == False)` here.
This function is shared by `embedding_pipeline.py` and `matching_service.py`, so
one fix covers both call sites — see DESIGN_NOTES.md for how this same function
needs to double as the Part 3 enforcement point.

---

## 4. Payment charged before persistence, no idempotency — HIGH — Data Integrity

**File:** `app/services/session_flow.py`, `advance_turn`, lines 30–33 (the `affirm` branch)

**Description:** On `affirm`, the code calls `payment_mock_client.charge(...)`
before anything is written to the database, and there's no check for a prior
successful charge on this session. If the process crashes after the charge
succeeds but before the `Booking`/`PaymentAttempt` rows are written (reproducible
via `simulate_crash: true`), or if a client simply retries after a timeout, the
member can be charged twice for one booking with no server-side way to detect it.

**Recommended fix:** see DESIGN_NOTES.md — Part 2 session-flow section.

---

## 5. Client-supplied `amount_cents` — MEDIUM-HIGH — Security

**Files:** `app/routers/bookings.py` (`ConfirmPaymentIn.amount_cents`),
`app/services/session_flow.py` (`payload.get("amount_cents", 0)`)

**Description:** Both the booking-confirmation endpoint and the session `affirm`
turn take the charge amount directly from the request body rather than deriving
it from the `Booking`/session state server-side. A member can set `amount_cents`
to anything, including `0` (forces a "failed" charge but the code path still
continues) or a small positive number well below the real price.

**Recommended fix:** compute the amount from server-side state (the booking's
stored price, or a priced-in-session field) and ignore/validate against any
client-supplied amount.

---

## 6. Redundant embedding recompute in ranking loop — LOW-MEDIUM — Performance

**File:** `app/services/matching_service.py`, `rank_candidates`, line 28

**Description:** `embedding_client.embed(build_member_profile_text(member, db))`
runs inside the `for candidate in candidates` loop, recomputing the *same*
requesting member's embedding on every iteration instead of once before the loop.
With a real embeddings API (vs. the free local fake one) this turns one API call
into N, adding latency and cost that scales with club size for no benefit.

**Recommended fix:** hoist the `query_vec` computation above the loop.
