"""Synchronization regressions with real manifest transactions and fake sinks."""

import asyncio
from copy import deepcopy
import re
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import models
from app.services.knowledge.knowledge_base import service


VECTOR_DOMAINS = ("table_column", "table_value", "sql_sample")
TABLE_DOMAINS = ("table_column", "table_value", "es_table_value")
DOMAINS = (*VECTOR_DOMAINS, "es_table_value", "es_knowledge")


def source_attribute(domain):
    if domain in TABLE_DOMAINS:
        return "kb_table_structures"
    return "kb_sample_libraries" if domain == "sql_sample" else "kb_knowledge_terms"


def knowledge_term_reference(reference_id, knowledge_term_id, name, value):
    return models.KbKnowledgeTerm(
        id=reference_id, knowledge_base_id=71, knowledge_term_id=knowledge_term_id,
        knowledge_term=models.KnowledgeTerm(
            id=knowledge_term_id, knowledge_access_id=1, is_deleted=False,
            term_name=name, term_value=value,
        ),
    )


class SourceEngine:
    """Exercise the real DISTINCT iterator without a network connection."""

    def __init__(self):
        self.values = {
            ("sales", "city"): ["上海", "北京"],
            ("sales", "hospital"): ["医院 A"],
            ("obsolete", "province"): ["江苏"],
        }
        self.active = False

    def connect(self):
        engine = self

        class Connection:
            def __enter__(self):
                engine.active = True
                return self

            def __exit__(self, *args):
                engine.active = False

            def execution_options(self, **kwargs):
                return self

            def execute(self, query):
                field, table = re.match(r'SELECT DISTINCT "([^"]+)" FROM "([^"]+)"', str(query)).groups()
                self.rows = iter([(value,) for value in engine.values.get((table, field), [])])
                return self

            def fetchmany(self, size):
                rows = []
                for _ in range(size):
                    row = next(self.rows, None)
                    if row is None:
                        break
                    rows.append(row)
                return rows

            def close(self):
                pass

        return Connection()

    def dispose(self):
        pass


@pytest.fixture
def sync_job(monkeypatch):
    engine = create_engine("sqlite://")
    models.KbVectorManifest.__table__.create(engine)
    db = Session(engine, autoflush=False)

    def field(field_id, name):
        return SimpleNamespace(
            id=field_id, field_name=name, field_alias=name, is_enabled=True,
            is_vectorized=True, is_value_vectorized=False,
        )

    kb = SimpleNamespace(
        id=71, space_id=3, vector_progress=0, knowledge_term_dirty=True,
        sample_library_dirty=True, vector_collection_name="v_kb71",
        kb_table_structures=[
            SimpleNamespace(table_name="sales", table_alias="销售", kb_table_fields=[
                field(1, "city"), field(2, "hospital"),
            ]),
            SimpleNamespace(table_name="obsolete", table_alias="历史", kb_table_fields=[
                field(3, "province"),
            ]),
        ],
        kb_knowledge_terms=[knowledge_term_reference(201, 10, "销售额", "含税金额")],
        kb_sample_libraries=[SimpleNamespace(
            id=20, sample_id=20, sample_name="查询销售额", sample_content="SELECT SUM(amount) FROM sales",
        )],
        knowledge_access=SimpleNamespace(id=1, data_source=SimpleNamespace(
            database_type="postgresql", host="unused", port=5432, default_database="unused",
        )),
    )
    source = SourceEngine()
    state = SimpleNamespace(
        vectors=[], es={"es_knowledge": {}, "es_table_value": {}}, embeddings=[], es_upserts=[],
        insert_calls=0, fail_insert=False, fail_embedding=False, fail_delete=False,
        partial_insert_failure=False, collection_exists=True,
        partial_delete_failure=False, malformed_embedding=None,
        index_exists={"es_knowledge": True, "es_table_value": True},
        embedding_config={"model": "embedding-test", "base_url": "https://unused.invalid", "dimension": 3},
        store_config={"id": 1, "provider": "milvus", "host": "unused", "port": 19530,
                      "database": "default", "collection_prefix": "v_kb", "dimension": 3},
        es_config={"id": 1, "host": "unused", "port": 9200, "provider": "elasticsearch"},
    )

    # The transaction behavior of manifests is real. Only field-status lookup is
    # substituted because this fixture deliberately creates no business tables.
    manifest_query = db.query

    def query(*entities, **kwargs):
        if len(entities) == 1 and entities[0] is models.KbTableField:
            class FieldQuery:
                def filter_by(self, **filters):
                    self.field_id = filters["id"]
                    return self

                def first(self):
                    return next((field for table in kb.kb_table_structures
                                 for field in table.kb_table_fields if field.id == self.field_id), None)

            return FieldQuery()
        return manifest_query(*entities, **kwargs)

    monkeypatch.setattr(db, "query", query)

    class Embeddings:
        dimension = 3

        def __init__(self, config):
            pass

        def get_embeddings(self, texts):
            assert not source.active
            state.embeddings.extend(texts)
            if state.fail_embedding:
                raise RuntimeError("embedding unavailable")
            if state.malformed_embedding == "count":
                return [[0.1, 0.2, 0.3] for _ in texts[:-1]]
            if state.malformed_embedding == "dimension":
                return [[0.1, 0.2] for _ in texts]
            return [[0.1, 0.2, 0.3] for _ in texts]

    def delete_scope(db, kb_id, field_type, table_name=None, field_code=None, space_id=None):
        if state.fail_delete:
            return False
        matching = [row for row in state.vectors if (
            row["kb_id"] == kb_id and row["field_type"] == field_type
            and (table_name is None or row["field_table"] == table_name)
            and (field_code is None or row["field_code"] == field_code)
        )]
        if state.partial_delete_failure:
            if matching:
                state.vectors.remove(matching[0])
            return False
        state.vectors[:] = [row for row in state.vectors if row not in matching]
        return True

    def delete_items(db, kb_id, field_type, items, space_id=None):
        if items and state.fail_delete:
            return False
        state.vectors[:] = [row for row in state.vectors if not (
            row["kb_id"] == kb_id and row["field_type"] == field_type
            and any(all(row.get(key) == value for key, value in item.items()
                        if key in ("field_table", "field_code", "field_value") and value is not None)
                    for item in items)
        )]
        return True

    def insert(db, kb_id, items, space_id=None):
        state.insert_calls += 1
        if state.partial_insert_failure:
            state.vectors.extend(deepcopy(items[:1]))
            return False
        if state.fail_insert:
            return False
        # Preserve duplicate inserts, as a real vector store with generated
        # primary keys does; successful retries must perform their own deletes.
        state.vectors.extend(deepcopy(items))
        return True

    doc_id = service.ElasticsearchService._doc_id

    class Elasticsearch:
        _doc_id = staticmethod(doc_id)

        def __init__(self, config):
            pass

        def index_exists(self, index_name):
            domain = "es_knowledge" if index_name.endswith("_knowledge") else "es_table_value"
            return state.index_exists[domain]

        def delete_knowledge_index(self, kb_id):
            if state.fail_delete:
                return False
            state.es["es_knowledge"].clear()
            state.index_exists["es_knowledge"] = False
            if state.partial_delete_failure:
                return False
            return True

        def delete_table_value_index(self, kb_id):
            if state.fail_delete:
                return False
            state.es["es_table_value"].clear()
            state.index_exists["es_table_value"] = False
            if state.partial_delete_failure:
                return False
            return True

        def upsert_knowledge_terms(self, kb_id, terms):
            state.es_upserts.append(("es_knowledge", deepcopy(terms)))
            state.es["es_knowledge"].update({item["id"]: deepcopy(item) for item in terms})
            state.index_exists["es_knowledge"] = True
            return True

        def upsert_table_values(self, kb_id, items):
            assert not source.active
            state.es_upserts.append(("es_table_value", deepcopy(items)))
            state.es["es_table_value"].update({item["id"]: deepcopy(item) for item in items})
            state.index_exists["es_table_value"] = True
            return True

        def delete_knowledge_terms_by_ids(self, kb_id, ids):
            if ids and state.fail_delete:
                return False
            for doc_id in ids:
                state.es["es_knowledge"].pop(doc_id, None)
            return True

        def delete_table_values_by_ids(self, kb_id, ids):
            if ids and state.fail_delete:
                return False
            for doc_id in ids:
                state.es["es_table_value"].pop(doc_id, None)
            return True

    monkeypatch.setattr(service, "EmbeddingService", Embeddings)
    monkeypatch.setattr(service, "ElasticsearchService", Elasticsearch)
    monkeypatch.setattr(service, "resolve_embedding_config", lambda *args, **kwargs: state.embedding_config)
    monkeypatch.setattr(service, "resolve_es_config", lambda *args, **kwargs: state.es_config)
    monkeypatch.setattr(service, "_raise_if_vectorization_cancelled", lambda *args: None)
    monkeypatch.setattr(service, "_create_external_source_engine", lambda _: source)
    monkeypatch.setattr(service, "DEFAULT_EMBEDDING_BATCH_SLEEP_SECONDS", 0)
    monkeypatch.setattr(service.VectorStoreService, "resolve_active_store", lambda *args, **kwargs: state.store_config)
    def create_collection(*args, **kwargs):
        state.collection_exists = True
        return True

    monkeypatch.setattr(service.VectorStoreService, "collection_exists_for_kb",
                        lambda *args, **kwargs: state.collection_exists, raising=False)
    monkeypatch.setattr(service.VectorStoreService, "create_collection_for_kb", create_collection)
    monkeypatch.setattr(service.VectorStoreService, "delete_vectors_by_table_field", delete_scope)
    monkeypatch.setattr(service.VectorStoreService, "delete_vectors_by_field_type", delete_scope)
    monkeypatch.setattr(service.VectorStoreService, "delete_vector_items", delete_items)
    monkeypatch.setattr(service.VectorStoreService, "insert_vectors", insert)

    def run(domain, mode="incremental"):
        functions = {
            "table_column": service._do_field_vectorization,
            "table_value": service._do_table_value_vectorization,
            "sql_sample": service._do_sample_library_vectorization,
            "es_table_value": service._do_table_values_to_es,
            "es_knowledge": service._do_knowledge_term_to_es,
        }
        args = (db, kb, "v_kb71", 1, 1, mode) if domain in VECTOR_DOMAINS else (db, kb, 1, 1, mode)
        asyncio.run(functions[domain](*args))

    def rows(domain):
        if domain in VECTOR_DOMAINS:
            return [row for row in state.vectors if row["field_type"] == domain]
        return list(state.es[domain].values())

    def manifests(domain):
        return db.query(models.KbVectorManifest).filter_by(kb_id=kb.id, domain=domain).all()

    def empty_source(domain):
        setattr(kb, source_attribute(domain), [])

    yield SimpleNamespace(db=db, kb=kb, state=state, source=source, run=run,
                          rows=rows, manifests=manifests, empty_source=empty_source)
    db.close()
    engine.dispose()


@pytest.mark.parametrize("domain", DOMAINS)
@pytest.mark.parametrize("mode", ["incremental", "full"])
def test_empty_source_removes_previous_domain_without_touching_other_domains(sync_job, domain, mode):
    job = sync_job
    for selected in DOMAINS:
        job.run(selected)
    other_rows = {selected: deepcopy(job.rows(selected)) for selected in DOMAINS if selected != domain}
    other_manifest_ids = {selected: [row.id for row in job.manifests(selected)] for selected in other_rows}

    job.empty_source(domain)
    job.run(domain, mode)

    assert job.rows(domain) == []
    assert job.manifests(domain) == []
    assert job.kb.vector_progress == 100
    for selected, original in other_rows.items():
        assert job.rows(selected) == original
        assert [row.id for row in job.manifests(selected)] == other_manifest_ids[selected]


@pytest.mark.parametrize("domain", TABLE_DOMAINS)
@pytest.mark.parametrize("mode", ["incremental", "full"])
def test_removed_tables_and_disabled_fields_are_removed_from_entire_domain(sync_job, domain, mode):
    job = sync_job
    job.run(domain)
    job.kb.kb_table_structures.pop()
    job.kb.kb_table_structures[0].kb_table_fields[0].is_enabled = False

    job.run(domain, mode)

    assert {row["field_code"] for row in job.rows(domain)} == {"sales&&hospital"}
    assert {row.field_code for row in job.manifests(domain)} == {"sales&&hospital"}


@pytest.mark.parametrize("domain", TABLE_DOMAINS)
def test_all_fields_disabled_remove_previous_vectors_and_manifests(sync_job, domain):
    job = sync_job
    job.run(domain)
    for table in job.kb.kb_table_structures:
        for field in table.kb_table_fields:
            field.is_enabled = False

    job.run(domain)

    assert job.rows(domain) == []
    assert job.manifests(domain) == []


@pytest.mark.parametrize("domain", ["table_value", "es_table_value"])
def test_unchecked_value_vectorization_removes_previous_values(sync_job, domain):
    job = sync_job
    job.run(domain)
    for table in job.kb.kb_table_structures:
        for field in table.kb_table_fields:
            field.is_vectorized = False

    job.run(domain)

    assert job.rows(domain) == []
    assert job.manifests(domain) == []


@pytest.mark.parametrize("domain", ["table_value", "es_table_value"])
def test_empty_distinct_result_removes_previous_values(sync_job, domain):
    job = sync_job
    job.run(domain)
    job.source.values.clear()

    job.run(domain)

    assert job.rows(domain) == []
    assert job.manifests(domain) == []


def test_sample_insert_failure_can_be_retried_incrementally(sync_job):
    job = sync_job
    job.state.fail_insert = True
    with pytest.raises(Exception, match="sample"):
        job.run("sql_sample")
    job.db.rollback()
    assert job.rows("sql_sample") == []

    job.state.fail_insert = False
    job.run("sql_sample")

    assert len(job.rows("sql_sample")) == 1
    assert len(job.manifests("sql_sample")) == 1
    assert job.state.insert_calls == 2


def test_failed_full_field_rebuild_can_be_retried_incrementally(sync_job):
    job = sync_job
    job.run("table_column")
    expected = deepcopy(job.rows("table_column"))
    job.state.fail_embedding = True
    with pytest.raises(RuntimeError, match="embedding unavailable"):
        job.run("table_column", "full")
    # A failed background task closes its session, rolling back pending SQL.
    job.db.rollback()

    job.state.fail_embedding = False
    job.run("table_column")

    assert sorted(job.rows("table_column"), key=lambda row: row["field_code"]) == sorted(
        expected, key=lambda row: row["field_code"],
    )


def test_samples_with_same_name_are_updated_and_deleted_by_id(sync_job):
    job = sync_job
    first = job.kb.kb_sample_libraries[0]
    second = SimpleNamespace(id=21, sample_id=21, sample_name=first.sample_name, sample_content="SELECT 2")
    job.kb.kb_sample_libraries.append(second)
    job.run("sql_sample", "full")

    second.sample_content = "SELECT 3"
    job.run("sql_sample")
    assert {row["sql_content"] for row in job.rows("sql_sample")} == {first.sample_content, "SELECT 3"}
    codes = {row["field_code"] for row in job.rows("sql_sample")}
    assert len(codes) == 2
    assert "" not in codes

    job.kb.kb_sample_libraries.remove(second)
    job.run("sql_sample")
    assert [row["sql_content"] for row in job.rows("sql_sample")] == [first.sample_content]


@pytest.mark.parametrize("domain", VECTOR_DOMAINS)
def test_unchanged_incremental_run_does_not_embed_or_duplicate_vectors(sync_job, domain):
    job = sync_job
    job.run(domain)
    expected = deepcopy(job.rows(domain))
    job.state.embeddings.clear()
    insert_calls = job.state.insert_calls

    job.run(domain)

    assert job.rows(domain) == expected
    assert job.state.embeddings == []
    assert job.state.insert_calls == insert_calls


@pytest.mark.parametrize("domain", VECTOR_DOMAINS)
def test_embedding_model_change_rebuilds_previously_unchanged_items(sync_job, domain):
    job = sync_job
    job.run(domain)
    expected_count = len(job.rows(domain))
    job.state.embeddings.clear()
    job.state.embedding_config["model"] = "embedding-updated"

    job.run(domain)

    assert len(job.state.embeddings) == expected_count
    assert len(job.rows(domain)) == expected_count


@pytest.mark.parametrize("domain", VECTOR_DOMAINS)
def test_partial_insert_failure_is_cleaned_when_source_is_removed(sync_job, domain):
    job = sync_job
    job.state.partial_insert_failure = True
    with pytest.raises(Exception):
        job.run(domain)
    job.db.rollback()
    assert job.rows(domain), "the fake sink must have accepted part of the failed batch"

    job.state.partial_insert_failure = False
    job.empty_source(domain)
    job.run(domain)

    assert job.rows(domain) == []
    assert job.manifests(domain) == []


@pytest.mark.parametrize("domain", DOMAINS)
def test_failed_delete_then_restored_source_recovers_without_duplicates(sync_job, domain):
    job = sync_job
    job.run(domain)
    original_source = list(getattr(job.kb, source_attribute(domain)))
    expected = deepcopy(job.rows(domain))
    job.empty_source(domain)
    job.state.fail_delete = True
    with pytest.raises(Exception):
        job.run(domain)
    job.db.rollback()

    setattr(job.kb, source_attribute(domain), original_source)
    job.state.fail_delete = False
    job.run(domain)

    assert sorted(job.rows(domain), key=repr) == sorted(expected, key=repr)
    assert len(job.manifests(domain)) == len(expected)


@pytest.mark.parametrize("domain", VECTOR_DOMAINS)
@pytest.mark.parametrize("change", ["target_config", "missing_collection"])
def test_incremental_populates_new_or_recreated_vector_target(sync_job, domain, change):
    job = sync_job
    job.run(domain)
    expected = deepcopy(job.rows(domain))
    job.state.vectors.clear()
    job.state.embeddings.clear()
    if change == "target_config":
        job.state.store_config["host"] = "new-target.invalid"
    else:
        job.state.collection_exists = False

    job.run(domain)

    assert sorted(job.rows(domain), key=repr) == sorted(expected, key=repr)
    assert len(job.state.embeddings) == len(expected)


@pytest.mark.parametrize("domain", ["es_table_value", "es_knowledge"])
@pytest.mark.parametrize("change", ["target_config", "missing_index"])
def test_incremental_populates_new_or_recreated_es_target(sync_job, domain, change):
    job = sync_job
    job.run(domain)
    expected_ids = set(job.state.es[domain])
    job.state.es[domain].clear()
    if change == "target_config":
        job.state.es_config["host"] = "new-search.invalid"
    else:
        job.state.index_exists[domain] = False

    job.run(domain)

    assert set(job.state.es[domain]) == expected_ids


def test_recreated_shared_collection_invalidates_all_vector_domains(sync_job):
    job = sync_job
    for domain in VECTOR_DOMAINS:
        job.run(domain)
    expected = {domain: deepcopy(job.rows(domain)) for domain in VECTOR_DOMAINS}
    job.state.vectors.clear()
    job.state.collection_exists = False

    # The first step recreates the collection. Later steps therefore see an
    # existing collection, but their old manifest entries are still invalid.
    for domain in VECTOR_DOMAINS:
        job.run(domain)

    for domain in VECTOR_DOMAINS:
        assert sorted(job.rows(domain), key=repr) == sorted(expected[domain], key=repr)


@pytest.mark.parametrize("domain", DOMAINS)
def test_partial_full_cleanup_failure_can_be_recovered_incrementally(sync_job, domain):
    job = sync_job
    job.run(domain)
    expected = deepcopy(job.rows(domain))
    job.state.partial_delete_failure = True
    with pytest.raises(RuntimeError, match="reset"):
        job.run(domain, "full")
    job.db.rollback()
    assert len(job.rows(domain)) < len(expected)

    job.state.partial_delete_failure = False
    job.run(domain)

    assert sorted(job.rows(domain), key=repr) == sorted(expected, key=repr)


@pytest.mark.parametrize("domain", VECTOR_DOMAINS)
@pytest.mark.parametrize("malformed", ["count", "dimension"])
def test_malformed_embeddings_leave_previous_vectors_untouched(sync_job, domain, malformed):
    job = sync_job
    job.run(domain)
    expected = deepcopy(job.rows(domain))
    expected_hashes = {row.item_key: row.embedding_hash for row in job.manifests(domain)}
    job.state.embedding_config["model"] = "embedding-updated"
    job.state.malformed_embedding = malformed

    with pytest.raises(RuntimeError, match="count or dimension"):
        job.run(domain)
    job.db.rollback()

    assert job.rows(domain) == expected
    assert {row.item_key: row.embedding_hash for row in job.manifests(domain)} == expected_hashes


def test_legacy_same_name_samples_migrate_to_stable_ids(sync_job):
    job = sync_job
    first = job.kb.kb_sample_libraries[0]
    job.kb.kb_sample_libraries.append(SimpleNamespace(
        id=21, sample_id=21, sample_name=first.sample_name, sample_content="SELECT 2",
    ))
    job.run("sql_sample")
    for row in job.rows("sql_sample"):
        row["field_code"] = ""
    for row in job.manifests("sql_sample"):
        row.field_code = None
    job.db.commit()

    job.run("sql_sample")

    assert {row["field_code"] for row in job.rows("sql_sample")} == {"sample:20", "sample:21"}
    assert len(job.rows("sql_sample")) == 2
    assert {row.field_code for row in job.manifests("sql_sample")} == {"sample:20", "sample:21"}


@pytest.mark.parametrize("mode", ["full", "incremental"])
def test_same_name_terms_are_renamed_and_removed_by_knowledge_term_id(sync_job, mode):
    job = sync_job
    first = job.kb.kb_knowledge_terms[0]
    second = knowledge_term_reference(202, 11, first.knowledge_term.term_name, "不含税金额")
    job.kb.kb_knowledge_terms.append(second)
    job.run("es_knowledge", mode)
    original = {row["term_key"]: deepcopy(row) for row in job.rows("es_knowledge")}
    assert set(original) == {"10", "11"}
    assert len(job.manifests("es_knowledge")) == 2

    first.knowledge_term.term_name = "总销售额"
    first.knowledge_term.term_value = "更新后的含税金额"
    job.state.es_upserts.clear()
    job.run("es_knowledge")

    renamed = {row["term_key"]: row for row in job.rows("es_knowledge")}
    assert set(renamed) == {"10", "11"}
    assert renamed["10"]["id"] == original["10"]["id"]
    assert renamed["10"]["term_name"] == "总销售额"
    assert renamed["10"]["term_value"] == "更新后的含税金额"
    assert renamed["11"] == original["11"]
    assert [row["id"] for domain, rows in job.state.es_upserts for row in rows
            if domain == "es_knowledge"] == [original["10"]["id"]]

    job.kb.kb_knowledge_terms.remove(second)
    job.run("es_knowledge")
    assert [row["id"] for row in job.rows("es_knowledge")] == [original["10"]["id"]]
    assert len(job.manifests("es_knowledge")) == 1


def test_legacy_name_key_term_manifest_migrates_to_separate_source_ids(sync_job):
    job = sync_job
    job.run("es_knowledge")
    source = job.kb.kb_knowledge_terms[0].knowledge_term
    old_key = service._manifest_key(job.kb.id, "es_knowledge", source.term_name)
    old_doc_id = service.ElasticsearchService._doc_id(f"es_kb{job.kb.id}_knowledge", old_key)
    old_doc = deepcopy(job.rows("es_knowledge")[0])
    old_doc.update(id=old_doc_id, term_key=source.term_name)
    job.state.es["es_knowledge"] = {old_doc_id: old_doc}
    job.manifests("es_knowledge")[0].item_key = old_key
    job.db.commit()
    job.kb.kb_knowledge_terms.append(knowledge_term_reference(202, 11, source.term_name, "不含税金额"))

    job.run("es_knowledge")

    assert old_doc_id not in job.state.es["es_knowledge"]
    assert {row["term_key"] for row in job.rows("es_knowledge")} == {"10", "11"}
    assert {row.item_key for row in job.manifests("es_knowledge")} == {
        service._manifest_key(job.kb.id, "es_knowledge", "10"),
        service._manifest_key(job.kb.id, "es_knowledge", "11"),
    }
    job.state.es_upserts.clear()
    job.run("es_knowledge")
    assert job.state.es_upserts == []
