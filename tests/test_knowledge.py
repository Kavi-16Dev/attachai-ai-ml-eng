from fastapi.testclient import TestClient

from app.embeddings import embedding_client
from app.main import app
from app.models import Club, KnowledgeChunk, Member

client = TestClient(app)


def test_query_own_club_returns_results(db):
    db.add(Club(id="riverside", name="Riverside"))
    db.add(Member(club_id="riverside", name="A", email="a@example.com", token="tok-a", role="member"))
    db.add(
        KnowledgeChunk(
            club_id="riverside",
            title="Fees",
            body="Guest fees are $50.",
            embedding=embedding_client.embed("Guest fees are $50."),
        )
    )
    db.commit()

    resp = client.get(
        "/clubs/riverside/knowledge/query",
        params={"q": "guest fees"},
        headers={"X-Member-Token": "tok-a"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_query_never_returns_other_clubs_chunks(db):
    """Regression test for the cross-tenant leak: even when another club's
    chunk is a closer embedding match, it must never appear in the results
    for a caller scoped to a different club."""
    db.add(Club(id="riverside", name="Riverside"))
    db.add(Club(id="oakhurst", name="Oakhurst"))
    db.add(Member(club_id="riverside", name="A", email="a@example.com", token="tok-a", role="member"))

    shared_body = "Guest fees are $50 per visit."
    db.add(
        KnowledgeChunk(
            club_id="riverside",
            title="Fees",
            body=shared_body,
            embedding=embedding_client.embed(shared_body),
        )
    )
    db.add(
        KnowledgeChunk(
            club_id="oakhurst",
            title="Fees",
            body=shared_body,
            embedding=embedding_client.embed(shared_body),
        )
    )
    db.commit()

    resp = client.get(
        "/clubs/riverside/knowledge/query",
        params={"q": "guest fees"},
        headers={"X-Member-Token": "tok-a"},
    )
    assert resp.status_code == 200
    club_ids = {row["club_id"] for row in resp.json()}
    assert club_ids == {"riverside"}


def test_query_rejects_non_member(db):
    db.add(Club(id="riverside", name="Riverside"))
    db.add(Club(id="oakhurst", name="Oakhurst"))
    db.add(Member(club_id="riverside", name="A", email="a@example.com", token="tok-a", role="member"))
    db.commit()

    resp = client.get(
        "/clubs/oakhurst/knowledge/query",
        params={"q": "guest fees"},
        headers={"X-Member-Token": "tok-a"},
    )
    assert resp.status_code == 403


