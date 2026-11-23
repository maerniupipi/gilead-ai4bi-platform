"""Regress the large joined result that broke real large-result chat requests."""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app import models
from app.core.database import Base
from app.repositories.knowledge.knowledge_base.repository import get_knowledge_base_detail


def test_detail_loads_complete_collections_without_cartesian_growth():
    engine = create_engine("sqlite://")
    types = (models.DataSource, models.KnowledgeAccess, models.KnowledgeBase, models.TableStructure,
             models.TableField, models.KbTableStructure, models.KbTableField, models.KnowledgeTerm,
             models.KbKnowledgeTerm, models.SampleLibrary, models.KbSampleLibrary)
    Base.metadata.create_all(engine, tables=[model.__table__ for model in types])
    with Session(engine) as db:
        db.add(models.KnowledgeBase(id=1, name="large", knowledge_access_id=1, space_id=7))
        db.add(models.KbTableStructure(id=1, knowledge_base_id=1, table_structure_id=1, table_name="sales"))
        for n in range(15):
            db.add(models.KbTableField(kb_table_structure_id=1, table_field_id=n + 1, field_name=f"f{n}", field_type="varchar"))
        for n in range(10):
            db.add(models.KbKnowledgeTerm(knowledge_base_id=1, knowledge_term_id=n + 1, term_name_cache=f"term{n}"))
        for n in range(12):
            db.add(models.KbSampleLibrary(knowledge_base_id=1, sample_id=n + 1, sample_name_cache=f"sample{n}"))
        db.commit()
    queries = []
    def capture(conn, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith("SELECT"):
            queries.append((statement, parameters))
    event.listen(engine, "before_cursor_execute", capture)
    with Session(engine) as db:
        kb = get_knowledge_base_detail(db, 1, 7)
        assert len(kb.kb_table_structures[0].kb_table_fields) == 15
        assert len(kb.kb_knowledge_terms) == 10 and len(kb.kb_sample_libraries) == 12
        assert kb.kb_knowledge_terms[0].term_name == "term0"
        assert kb.kb_sample_libraries[0].sample_name == "sample0"
    event.remove(engine, "before_cursor_execute", capture)
    # Count physical rows transferred, not ORM objects (which hide join duplication).
    raw = engine.raw_connection()
    try:
        cursor = raw.cursor()
        physical_rows = sum(len(cursor.execute(sql, params).fetchall()) for sql, params in queries)
    finally:
        raw.close()
    assert len(queries) <= 6
    assert physical_rows <= 40  # Old multi-collection JOIN returned 1,800 rows here.
    with Session(engine) as db:
        assert get_knowledge_base_detail(db, 1, 99) is None
        db.get(models.KnowledgeBase, 1).is_deleted = True
        db.commit()
        assert get_knowledge_base_detail(db, 1, 7) is None
    engine.dispose()
