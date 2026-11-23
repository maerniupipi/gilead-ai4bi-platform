"""Bounded SQLAlchemy connections and durable batch history (PostgreSQL/SQLite)."""
import hashlib
import hmac
import secrets
import time

from sqlalchemy import (Boolean, Column, Float, ForeignKey, Index, Integer, JSON,
                        MetaData, String, Table, Text, create_engine, delete, func,
                        insert, or_, select, update)

metadata = MetaData()
accounts = Table("batch_accounts", metadata,
    Column("username", String(64), primary_key=True), Column("password_hash", Text, nullable=False))
sessions = Table("batch_sessions", metadata,
    Column("token_hash", String(64), primary_key=True),
    Column("username", String(64), ForeignKey("batch_accounts.username"), nullable=False),
    Column("csrf", String(64), nullable=False), Column("expires_at", Float, nullable=False, index=True))
jobs = Table("batch_jobs", metadata,
    Column("job_id", String(32), primary_key=True), Column("title", String(200), nullable=False),
    Column("filename", String(200), nullable=False), Column("status", String(32), nullable=False),
    Column("created_at", String(40), nullable=False), Column("archived", Boolean, nullable=False, default=False),
    Column("payload", JSON, nullable=False))
Index("ix_batch_jobs_history", jobs.c.archived, jobs.c.created_at, jobs.c.job_id)
rows = Table("batch_rows", metadata,
    Column("job_id", String(32), ForeignKey("batch_jobs.job_id"), primary_key=True),
    Column("row_id", String(32), primary_key=True), Column("status", String(32), nullable=False),
    Column("payload", JSON, nullable=False))


def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=32768,
                            r=8, p=1, maxmem=64 * 1024 * 1024).hex()
    return f"scrypt${salt}${digest}"


def verify_password(password, encoded):
    try:
        algorithm, salt, expected = encoded.split("$")
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=32768,
                                r=8, p=1, maxmem=64 * 1024 * 1024).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


class Database:
    def __init__(self, url):
        options = {"pool_pre_ping": True, "pool_size": 2, "max_overflow": 1,
                   "pool_timeout": 15, "hide_parameters": True}
        if url.startswith("sqlite:"):
            options["connect_args"] = {"check_same_thread": False, "timeout": 20}
        self.engine = create_engine(url, **options)
        metadata.create_all(self.engine)

    def healthy(self):
        with self.engine.connect() as connection:
            connection.execute(select(1))
        return True

    def ensure_admin(self, password):
        with self.engine.begin() as connection:
            if connection.execute(select(accounts.c.username)).first():
                return
            if len(password) < 10:
                raise ValueError("初始管理员密码至少需要 10 个字符")
            connection.execute(insert(accounts).values(username="admin", password_hash=hash_password(password)))

    def has_admin(self):
        with self.engine.connect() as connection:
            return connection.execute(select(accounts.c.username)).first() is not None

    def login(self, username, password, lifetime):
        with self.engine.connect() as connection:
            encoded = connection.execute(select(accounts.c.password_hash).where(
                accounts.c.username == "admin")).scalar_one()
        # Run the same expensive check for an unknown account to avoid timing disclosure.
        valid = verify_password(password, encoded)
        if username != "admin" or not valid:
            return None
        token, csrf = secrets.token_urlsafe(32), secrets.token_hex(32)
        with self.engine.begin() as connection:
            connection.execute(delete(sessions).where(sessions.c.expires_at <= time.time()))
            connection.execute(insert(sessions).values(token_hash=hashlib.sha256(token.encode()).hexdigest(),
                username="admin", csrf=csrf, expires_at=time.time() + lifetime))
        return {"token": token, "csrf": csrf, "username": "admin"}

    def session(self, token):
        if not token or len(token) > 128:
            return None
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self.engine.connect() as connection:
            found = connection.execute(select(sessions).where(
                sessions.c.token_hash == digest, sessions.c.expires_at > time.time())).mappings().first()
        return dict(found) if found else None

    def logout(self, token):
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self.engine.begin() as connection:
            connection.execute(delete(sessions).where(sessions.c.token_hash == digest))

    def save_job(self, job):
        values = {key: job[key] for key in ("job_id", "filename", "status", "created_at")}
        values["payload"] = job
        with self.engine.begin() as connection:
            existing = connection.execute(select(jobs.c.job_id).where(jobs.c.job_id == job["job_id"])).first()
            if existing:
                connection.execute(update(jobs).where(jobs.c.job_id == job["job_id"]).values(**values))
            else:
                connection.execute(insert(jobs).values(**values, title=job["filename"], archived=False))

    def create_job(self, job, results):
        """Commit the task and all initial rows together, so recovery never sees a half-created task."""
        values = {key: job[key] for key in ("job_id", "filename", "status", "created_at")}
        with self.engine.begin() as connection:
            connection.execute(insert(jobs).values(**values, payload=job, title=job["filename"], archived=False))
            if results:
                connection.execute(insert(rows), [{"job_id": job["job_id"], "row_id": row.row_id,
                    "status": row.status, "payload": row.to_dict()} for row in results])

    def save_row(self, job_id, row):
        condition = (rows.c.job_id == job_id) & (rows.c.row_id == row.row_id)
        values = {"status": row.status, "payload": row.to_dict()}
        with self.engine.begin() as connection:
            if connection.execute(select(rows.c.row_id).where(condition)).first():
                connection.execute(update(rows).where(condition).values(**values))
            else:
                connection.execute(insert(rows).values(job_id=job_id, row_id=row.row_id, **values))

    def load(self, job_id):
        with self.engine.connect() as connection:
            item = connection.execute(select(jobs).where(jobs.c.job_id == job_id)).mappings().first()
            if item is None:
                return None
            saved = connection.execute(select(rows.c.payload).where(rows.c.job_id == job_id)).scalars().all()
        job = {**item["payload"], "title": item["title"], "archived": item["archived"]}
        by_id = {row["row_id"]: row for row in saved}
        return job, [by_id[row_id] for row_id in job["row_ids"]]

    def list_jobs(self, query="", status="", archived=False, offset=0, limit=50):
        conditions = [jobs.c.archived == archived]
        if query:
            pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            conditions.append(or_(jobs.c.title.ilike(pattern, escape="\\"),
                                  jobs.c.filename.ilike(pattern, escape="\\"), jobs.c.job_id == query))
        if status:
            conditions.append(jobs.c.status == status)
        with self.engine.connect() as connection:
            total = connection.execute(select(func.count()).select_from(jobs).where(*conditions)).scalar_one()
            records = connection.execute(select(jobs).where(*conditions).order_by(
                jobs.c.created_at.desc(), jobs.c.job_id.desc()).offset(offset).limit(limit)).mappings().all()
            ids = [record["job_id"] for record in records]
            counts = connection.execute(select(rows.c.job_id, rows.c.status, func.count()).where(
                rows.c.job_id.in_(ids)).group_by(rows.c.job_id, rows.c.status)).all() if ids else []
        totals = {}
        for job_id, row_status, count in counts:
            totals.setdefault(job_id, {})[row_status] = count
        items = []
        for record in records:
            item = {key: record[key] for key in ("job_id", "title", "filename", "status", "created_at", "archived")}
            item["counts"] = totals.get(item["job_id"], {})
            item["total"] = sum(item["counts"].values())
            item["target"] = record["payload"].get("target", {})
            items.append(item)
        return {"items": items, "total": total, "offset": offset, "limit": limit}

    def edit_job(self, job_id, changes):
        with self.engine.begin() as connection:
            changed = connection.execute(update(jobs).where(jobs.c.job_id == job_id).values(**changes))
            if not changed.rowcount:
                raise FileNotFoundError()
