from pathlib import Path

import pytest

from briefledger.search import chunk_text, safe_query
from briefledger.store import CollectionStore, Registry, StoreError


@pytest.fixture
def store(tmp_path: Path):
    result = CollectionStore(tmp_path / "collection.sqlite3")
    result.initialize()
    return result


def test_chunks_preserve_exact_source_offsets_and_line_ranges():
    text = "# Guide\n" + "\n".join(f"Line {n}: evidence and context." for n in range(150))
    chunks = chunk_text(text)
    assert len(chunks) > 2
    for chunk in chunks:
        assert chunk.text == text[chunk.start : chunk.end]
        assert chunk.line_start == text.count("\n", 0, chunk.start) + 1
        assert chunk.line_end >= chunk.line_start
        assert len(chunk.text) <= 1400
    assert chunks[-1].end == len(text)


def test_a_long_single_line_is_bounded_without_losing_unicode():
    text = "café résumé " * 1200
    chunks = chunk_text(text)
    assert len(chunks) > 4
    assert all(0 < len(c.text) <= 1400 for c in chunks)
    assert chunks[-1].end == len(text)


def test_query_operators_are_data_not_executable_match_syntax():
    assert safe_query("rollback OR retention") == '"rollback" AND "OR" AND "retention"'
    assert safe_query('alpha" NEAR(beta)') == '"alpha" AND "NEAR" AND "beta"'
    with pytest.raises(StoreError):
        safe_query("***")


def test_search_returns_actual_evidence_and_source_locations(store):
    doc = store.add("incident.md", "# Incident guide\n\nThe rollback owner is the release lead.\n")
    result = store.search("rollback owner")
    assert result["status"] == "matched"
    evidence = result["evidence"][0]
    assert evidence["documentId"] == doc["id"]
    assert evidence["lineStart"] == 1
    assert "rollback" in "".join(s["text"] for s in evidence["segments"]).lower()
    assert any(s["match"] for s in evidence["segments"])
    assert store.document(doc["id"])["content"].endswith("release lead.\n")


def test_ranking_prefers_focused_matching_passage(store):
    focused = store.add("focused.txt", "Rollback rollback rollback ownership.")
    store.add("long.txt", "Rollback ownership. " + "Unrelated context. " * 50)
    assert store.search("rollback")["evidence"][0]["documentId"] == focused["id"]


def test_no_match_is_explicit_and_contains_no_invented_answer(store):
    store.add("notes.txt", "This collection discusses release checklists.")
    result = store.search("underwater volcanoes")
    assert result["status"] == "no_match"
    assert result["evidence"] == []
    assert result["matchCount"] == 0
    assert "answer" not in result


def test_queries_with_sql_and_fts_punctuation_cannot_expand_results(store):
    store.add("private.txt", "Confidential orchard budget.")
    assert store.search('" OR 1=1 --')["evidence"] == []
    assert store.search("orchard")["matchCount"] == 1


def test_delete_removes_source_and_search_index_atomically(store):
    doc = store.add("notes.md", "# Notes\nA uniquely searchable kumquat.")
    store.delete(doc["id"])
    assert store.search("kumquat")["status"] == "no_match"
    with pytest.raises(StoreError) as error:
        store.document(doc["id"])
    assert error.value.status == 404


def test_separate_collections_cannot_read_delete_or_rank_each_other(tmp_path):
    a = CollectionStore(tmp_path / "a.sqlite3")
    b = CollectionStore(tmp_path / "b.sqlite3")
    a.initialize()
    b.initialize()
    doc = a.add("private.md", "The private launch code is kumquat.")
    assert b.search("kumquat")["status"] == "no_match"
    with pytest.raises(StoreError):
        b.document(doc["id"])
    with pytest.raises(StoreError):
        b.delete(doc["id"])
    assert a.search("kumquat")["matchCount"] == 1


def test_reset_replaces_only_this_collection_with_samples(store):
    store.add("custom.md", "Private uploaded kumquat source.")
    store.reset_samples()
    assert len(store.list_documents()) == 4
    assert store.search("kumquat")["status"] == "no_match"
    assert store.search("rollback")["status"] == "matched"
    assert all(d["sample"] for d in store.list_documents())


@pytest.mark.parametrize(
    "filename,content",
    [
        ("bad.exe", "hello"),
        ("../path.md", "hello"),
        ("fine.md", "\x00bad"),
        ("empty.txt", "   "),
        ("big.txt", "a" * 131073),
    ],
    ids=["extension", "path", "binary", "empty", "oversized"],
)
def test_upload_validation_rejects_invalid_files_without_side_effects(store, filename, content):
    with pytest.raises(StoreError):
        store.add(filename, content)
    assert store.list_documents() == []


def test_duplicate_content_is_rejected_not_silently_duplicated(store):
    store.add("one.txt", "Same content.")
    with pytest.raises(StoreError) as error:
        store.add("two.txt", "Same content.")
    assert error.value.status == 409
    assert len(store.list_documents()) == 1


def test_document_quota_is_enforced(store):
    for n in range(30):
        store.add(f"{n}.txt", f"Unique document number {n}.")
    with pytest.raises(StoreError) as error:
        store.add("overflow.txt", "One too many.")
    assert error.value.status == 409
    assert len(store.list_documents()) == 30


def test_registry_stores_only_hashed_capabilities_and_expires(tmp_path):
    registry = Registry(tmp_path, max_collections=2)
    registry.initialize()
    collection = registry.create(now=1000)
    assert len(collection.token) == 64
    assert collection.key != collection.token
    assert collection.token not in collection.store.path.name
    assert registry.lookup(collection.token, now=1001).key == collection.key
    assert registry.lookup(collection.token, now=1000 + 604801) is None
    assert registry.lookup("not-a-token", now=1001) is None


def test_bom_only_upload_is_not_a_readable_document(store):
    with pytest.raises(StoreError):
        store.add("empty.md", "\ufeff  \n")
    assert store.list_documents() == []


def test_registry_capacity_is_bounded_and_expired_collections_are_removed(tmp_path):
    registry = Registry(tmp_path, max_collections=1)
    registry.initialize()
    previous = registry.create(now=1000)
    with pytest.raises(StoreError) as error:
        registry.create(now=1001)
    assert error.value.status == 503
    new = registry.create(now=1000 + 604801)
    assert new.key != previous.key
    assert not previous.store.path.exists()
    assert registry.lookup(new.token, now=1000 + 604802) is not None


def test_invalid_unicode_filename_is_validation_error_not_database_failure(store):
    with pytest.raises(StoreError):
        store.add("\ud800.md", "A readable source.")
    assert store.list_documents() == []


def test_total_source_text_quota_is_enforced_even_below_document_count_limit(store):
    for number in range(16):
        content = "a" * (131072 - 6) + f"{number:06}"
        store.add(f"large-{number}.txt", content)
    assert store.stats()["bytes"] == 2097152
    with pytest.raises(StoreError) as error:
        store.add("overflow.txt", "One byte too many.")
    assert error.value.status == 409
    assert store.stats()["documents"] == 16
