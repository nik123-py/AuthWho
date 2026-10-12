import uuid

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from server.db.migrate import MigrationError, apply_migrations, discover

pytestmark = pytest.mark.integration


@pytest.fixture
def scratch_url(pg_url):
    """Connection string whose search_path is a throwaway schema."""
    schema = f"mig_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(pg_url, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    params = conninfo_to_dict(pg_url)
    params["options"] = f"-c search_path={schema}"
    yield make_conninfo(**params)
    with psycopg.connect(pg_url, autocommit=True) as conn:
        conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def _write(root, folder, name, text):
    path = root / folder / "migrations"
    path.mkdir(parents=True, exist_ok=True)
    (path / name).write_text(text, encoding="utf-8")


def test_discover_orders_globally_by_filename_across_folders(tmp_path):
    _write(tmp_path, "policy", "0100_policies.sql", "SELECT 1;")
    _write(tmp_path, "db", "0002_sessions.sql", "SELECT 1;")
    _write(tmp_path, "db", "0001_users.sql", "SELECT 1;")
    assert [m.filename for m in discover(tmp_path)] == [
        "0001_users.sql",
        "0002_sessions.sql",
        "0100_policies.sql",
    ]


def test_discover_rejects_duplicate_filenames(tmp_path):
    _write(tmp_path, "db", "0001_users.sql", "SELECT 1;")
    _write(tmp_path, "policy", "0001_users.sql", "SELECT 1;")
    with pytest.raises(MigrationError, match="duplicate"):
        discover(tmp_path)


def test_discover_rejects_names_without_number_prefix(tmp_path):
    _write(tmp_path, "db", "users.sql", "SELECT 1;")
    with pytest.raises(MigrationError, match="NNNN_"):
        discover(tmp_path)


def test_applies_in_order_records_and_is_idempotent(tmp_path, scratch_url):
    _write(tmp_path, "b", "0002_child.sql", "CREATE TABLE child (id int REFERENCES parent(id));")
    _write(tmp_path, "a", "0001_parent.sql", "CREATE TABLE parent (id int PRIMARY KEY);")
    assert apply_migrations(scratch_url, root=tmp_path) == ["0001_parent.sql", "0002_child.sql"]
    assert apply_migrations(scratch_url, root=tmp_path) == []
    with psycopg.connect(scratch_url) as conn:
        rows = conn.execute("SELECT filename FROM schema_migrations ORDER BY filename").fetchall()
    assert [r[0] for r in rows] == ["0001_parent.sql", "0002_child.sql"]


def test_failed_migration_is_rolled_back_and_not_recorded(tmp_path, scratch_url):
    _write(tmp_path, "a", "0001_ok.sql", "CREATE TABLE ok (id int);")
    _write(tmp_path, "a", "0002_bad.sql", "CREATE TABLE half (id int); SELECT * FROM missing_table;")
    with pytest.raises(MigrationError, match="0002_bad.sql"):
        apply_migrations(scratch_url, root=tmp_path)
    with psycopg.connect(scratch_url) as conn:
        applied = [r[0] for r in conn.execute("SELECT filename FROM schema_migrations").fetchall()]
        half = conn.execute("SELECT to_regclass('half')").fetchone()[0]
    assert applied == ["0001_ok.sql"]
    assert half is None


def test_changed_applied_migration_is_refused(tmp_path, scratch_url):
    _write(tmp_path, "a", "0001_t.sql", "CREATE TABLE t (id int);")
    apply_migrations(scratch_url, root=tmp_path)
    _write(tmp_path, "a", "0001_t.sql", "CREATE TABLE t (id bigint);")
    with pytest.raises(MigrationError, match="changed"):
        apply_migrations(scratch_url, root=tmp_path)


def _columns(conn, table):
    rows = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = %s",
        (table,),
    ).fetchall()
    return {r[0] for r in rows}


def test_real_migrations_create_users_and_sessions(pg_conn):
    assert _columns(pg_conn, "users") == {
        "user_id", "app_id", "role", "consent_version", "consent_at",
        "research_consent", "research_consent_at", "opt_outs", "exempt", "pointer_device",
        "created_at",
    }
    assert _columns(pg_conn, "sessions") == {
        "session_id", "user_id", "app_id", "role", "status", "created_at", "ended_at",
    }


def test_real_migrations_are_idempotent(pg_url):
    assert apply_migrations(pg_url) == []
