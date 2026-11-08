"""Profile-local SQLite ledger; hashes instead of recipient/body content."""
from contextlib import closing, contextmanager
from hashlib import sha256
import re
import sqlite3


def body_hash(value):
    return sha256(value.encode("utf-8")).hexdigest()


def canonical_recipient(value):
    if not isinstance(value, str) or not value or len(value) > 256:
        raise ValueError("invalid recipient")
    if re.fullmatch(r"\+[0-9 ()-]+", value):
        value = re.sub(r"[ ()-]", "", value)
    if any(c.isspace() or ord(c) < 32 for c in value):
        raise ValueError("invalid recipient")
    return value


def recipient_id(value):
    return body_hash(canonical_recipient(value))


def thread_id(value):
    if not isinstance(value, str) or len(value) > 256:
        raise ValueError("invalid thread")
    return body_hash(value)


_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS contacts (recipient_id TEXT NOT NULL, channel TEXT NOT NULL, "
    "source TEXT NOT NULL, date TEXT NOT NULL, timezone TEXT NOT NULL, region TEXT NOT NULL, "
    "variables TEXT NOT NULL DEFAULT '{}', PRIMARY KEY(recipient_id,channel))",
    "CREATE TABLE IF NOT EXISTS suppressions (recipient_id TEXT PRIMARY KEY)",
    "CREATE TABLE IF NOT EXISTS decisions (id INTEGER PRIMARY KEY, at REAL NOT NULL, "
    "channel TEXT NOT NULL, recipient_id TEXT NOT NULL, thread_id TEXT NOT NULL, "
    "body_hash TEXT NOT NULL, rule TEXT NOT NULL, outcome TEXT NOT NULL)",
)


class Ledger:
    def __init__(self, connect):
        self.connect = connect

    @contextmanager
    def transaction(self):
        with closing(self.connect()) as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE")
            try:
                for statement in _SCHEMA:
                    db.execute(statement)
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    @staticmethod
    def optout(db, recipient):
        db.execute("INSERT OR IGNORE INTO suppressions VALUES (?)", (recipient_id(recipient),))

    @staticmethod
    def log(db, channel, recipient, thread, message, rule, outcome, at):
        return db.execute(
            "INSERT INTO decisions (at,channel,recipient_id,thread_id,body_hash,rule,outcome) "
            "VALUES (?,?,?,?,?,?,?)",
            (at, channel, recipient_id(recipient), thread_id(thread), body_hash(message), rule, outcome),
        ).lastrowid
