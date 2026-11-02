from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from briefledger.app import create_app


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(
        create_app(tmp_path, cookie_secure=True), base_url="https://testserver"
    ) as browser:
        yield browser


def session(client):
    response = client.get("/api/session")
    assert response.status_code == 200
    return response.json()


def write_headers(data):
    return {
        "origin": "https://testserver",
        "x-csrf-token": data["csrfToken"],
        "content-type": "application/json",
    }


def test_new_session_gets_private_cookie_and_usable_sample_collection(client):
    response = client.get("/api/session")
    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    for attribute in ["HttpOnly", "Secure", "SameSite=lax", "Path=/"]:
        assert attribute in cookie
    assert "Domain=" not in cookie
    data = response.json()
    assert data["stats"]["documents"] == 4
    assert len(data["csrfToken"]) == 64
    assert "token" not in data
    assert client.get("/api/search", params={"q": "rollback"}).json()["status"] == "matched"


def test_html_and_static_assets_have_security_headers(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "BriefLedger" in response.text
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert client.get("/static/app.js").status_code == 200


def test_data_requires_an_existing_browser_collection(client):
    assert client.get("/api/documents").status_code == 401
    assert client.get("/api/search", params={"q": "rollback"}).status_code == 401


def test_upload_search_open_and_delete_real_document(client):
    data = session(client)
    headers = write_headers(data)
    upload = client.post(
        "/api/documents",
        headers=headers,
        json={"filename": "test.md", "content": "# Private notes\nA kumquat evidence marker.\n"},
    )
    assert upload.status_code == 201
    doc = upload.json()["document"]
    matches = client.get("/api/search", params={"q": "kumquat"}).json()
    assert matches["evidence"][0]["documentId"] == doc["id"]
    opened = client.get("/api/documents/" + doc["id"]).json()
    assert opened["lines"][1] == "A kumquat evidence marker."
    assert client.delete("/api/documents/" + doc["id"], headers=headers).status_code == 200
    assert client.get("/api/search", params={"q": "kumquat"}).json()["status"] == "no_match"


def test_other_browser_cannot_read_delete_or_search_private_source(client):
    data = session(client)
    created = client.post(
        "/api/documents",
        headers=write_headers(data),
        json={"filename": "private.txt", "content": "Only this browser knows kumquat."},
    ).json()["document"]
    with TestClient(client.app, base_url="https://testserver") as other:
        other_data = session(other)
        assert other.get("/api/documents/" + created["id"]).status_code == 404
        assert (
            other.delete(
                "/api/documents/" + created["id"], headers=write_headers(other_data)
            ).status_code
            == 404
        )
        assert other.get("/api/search", params={"q": "kumquat"}).json()["status"] == "no_match"
    assert client.get("/api/documents/" + created["id"]).status_code == 200


@pytest.mark.parametrize(
    "changed", ["origin", "csrf", "missing-origin", "content-type", "fetch-site"]
)
def test_cookie_writes_reject_cross_site_or_missing_csrf_before_mutation(client, changed):
    data = session(client)
    headers = write_headers(data)
    if changed == "origin":
        headers["origin"] = "https://attacker.example"
    elif changed == "csrf":
        headers["x-csrf-token"] = "0" * 64
    elif changed == "missing-origin":
        del headers["origin"]
    elif changed == "content-type":
        headers["content-type"] = "text/plain"
    else:
        headers["sec-fetch-site"] = "cross-site"
    response = client.post(
        "/api/documents",
        headers=headers,
        json={"filename": "test.txt", "content": "Blocked source."},
    )
    assert response.status_code in (403, 415)
    assert client.get("/api/documents").json()["stats"]["documents"] == 4


def test_request_body_bound_applies_before_json_parsing(client):
    data = session(client)
    response = client.post("/api/documents", headers=write_headers(data), content=b"x" * 262145)
    assert response.status_code == 413
    assert "traceback" not in response.text.lower()


def test_invalid_upload_and_json_fail_without_echoing_source_text(client):
    data = session(client)
    response = client.post(
        "/api/documents",
        headers=write_headers(data),
        json={"filename": "bad.pdf", "content": "private-sensitive-marker"},
    )
    assert response.status_code == 400
    assert "private-sensitive-marker" not in response.text
    malformed = client.post("/api/documents", headers=write_headers(data), content="{broken")
    assert malformed.status_code == 400
    assert client.get("/api/documents").json()["stats"]["documents"] == 4


def test_reset_requires_confirmation_and_only_replaces_own_sources(client):
    data = session(client)
    headers = write_headers(data)
    assert client.post("/api/reset", headers=headers, json={"confirm": False}).status_code == 400
    uploaded = client.post(
        "/api/documents",
        headers=headers,
        json={"filename": "note.txt", "content": "Delete my kumquat note."},
    ).json()["document"]
    assert client.post("/api/reset", headers=headers, json={"confirm": True}).status_code == 200
    assert client.get("/api/documents/" + uploaded["id"]).status_code == 404
    assert client.get("/api/documents").json()["stats"]["documents"] == 4


def test_search_bounds_and_literal_operator_handling(client):
    session(client)
    assert client.get("/api/search", params={"q": "x" * 161}).status_code == 400
    assert client.get("/api/search", params={"q": "*"}).status_code == 400
    response = client.get("/api/search", params={"q": '" OR 1=1 --'})
    assert response.status_code == 200
    assert response.json()["status"] == "no_match"
    assert response.headers["cache-control"] == "no-store"


def test_source_markup_is_returned_as_plain_data_not_rendered_html(client):
    data = session(client)
    source = '<script>alert("inert")</script> source evidence'
    uploaded = client.post(
        "/api/documents",
        headers=write_headers(data),
        json={"filename": "markup.txt", "content": source},
    ).json()["document"]
    response = client.get("/api/documents/" + uploaded["id"])
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["content"] == source


def test_existing_collection_survives_a_new_application_instance(tmp_path):
    with TestClient(
        create_app(tmp_path, cookie_secure=True), base_url="https://testserver"
    ) as first:
        data = session(first)
        uploaded = first.post(
            "/api/documents",
            headers=write_headers(data),
            json={"filename": "saved.txt", "content": "Persistent kumquat evidence."},
        ).json()["document"]
        token = first.cookies.get("briefledger_session")
    with TestClient(
        create_app(tmp_path, cookie_secure=True), base_url="https://testserver"
    ) as second:
        second.cookies.set("briefledger_session", token)
        assert session(second)["stats"]["documents"] == 5
        assert second.get("/api/documents/" + uploaded["id"]).status_code == 200


def test_non_ascii_csrf_header_is_rejected_without_server_error(client):
    data = session(client)
    headers = write_headers(data)
    headers["x-csrf-token"] = b"\xe9"
    response = client.post("/api/reset", headers=headers, json={"confirm": True})
    assert response.status_code == 403


def test_excessively_long_content_length_is_rejected_before_integer_conversion(client):
    data = session(client)
    headers = write_headers(data)
    headers["content-length"] = "9" * 5000
    response = client.post("/api/reset", headers=headers, content="{}")
    assert response.status_code == 413


def test_invalid_unicode_filename_returns_safe_validation_error(client):
    data = session(client)
    response = client.post(
        "/api/documents",
        headers=write_headers(data),
        content=r'{"filename":"\ud800.md","content":"Readable source."}',
    )
    assert response.status_code == 400
    assert client.get("/api/documents").json()["stats"]["documents"] == 4


def test_streamed_body_without_content_length_is_still_bounded(client):
    data = session(client)

    def body_chunks():
        for _ in range(5):
            yield b"x" * 65536

    response = client.post("/api/documents", headers=write_headers(data), content=body_chunks())
    assert response.status_code == 413
    assert client.get("/api/documents").json()["stats"]["documents"] == 4


def test_source_filter_cannot_select_another_browsers_document(client):
    data = session(client)
    document = client.post(
        "/api/documents",
        headers=write_headers(data),
        json={"filename": "private.txt", "content": "Private kumquat evidence."},
    ).json()["document"]
    with TestClient(client.app, base_url="https://testserver") as other:
        session(other)
        response = other.get("/api/search", params={"q": "kumquat", "documentId": document["id"]})
        assert response.status_code == 404
        assert "Private kumquat evidence" not in response.text


def test_ephemeral_mode_discloses_restart_loss_and_synthetic_use(client, monkeypatch):
    monkeypatch.setenv("BRIEFLEDGER_EPHEMERAL", "true")
    data = session(client)
    assert data["storage"] == "ephemeral"
    assert "restarts" in data["storageNotice"]
    assert "redeployed" in data["storageNotice"]
    assert "synthetic or sample text only" in data["storageNotice"]


def test_local_mode_does_not_claim_ephemeral_storage(client, monkeypatch):
    monkeypatch.delenv("BRIEFLEDGER_EPHEMERAL", raising=False)
    data = session(client)
    assert data["storage"] == "local"
    assert data["storageNotice"] is None
