import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable
from app.providers.interfaces import ProviderError


class SQLiteMemoryStore:
    """Review memory in the same local SQLite file, in its own table."""

    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "clearpath.sqlite3"
        with self._connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS memory (id TEXT PRIMARY KEY, data TEXT NOT NULL)"
            )

    def _connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def get(self) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT data FROM memory WHERE id = 'v1'").fetchone()
        return json.loads(row[0]) if row else {"patterns": {}}

    def update(self, mutate: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT data FROM memory WHERE id = 'v1'").fetchone()
            data = json.loads(row[0]) if row else {"patterns": {}}
            mutate(data)
            db.execute(
                "INSERT OR REPLACE INTO memory VALUES ('v1', ?)", (json.dumps(data),)
            )
        return data


class SQLiteCaseStorage:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "clearpath.sqlite3"
        with self._connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS cases (id TEXT PRIMARY KEY, data TEXT NOT NULL)"
            )

    def _connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def create(self, record: dict[str, Any]) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO cases VALUES (?, ?)", (record["id"], json.dumps(record))
            )

    def get(self, case_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT data FROM cases WHERE id = ?", (case_id,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def update(
        self, case_id: str, mutate: Callable[[dict[str, Any]], None]
    ) -> dict[str, Any]:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT data FROM cases WHERE id = ?", (case_id,)
            ).fetchone()
            if not row:
                raise KeyError(case_id)
            data = json.loads(row[0])
            mutate(data)
            db.execute(
                "UPDATE cases SET data = ? WHERE id = ?", (json.dumps(data), case_id)
            )
        return data

    def _lease_expired(self, job: dict[str, Any]) -> bool:
        expires = job.get("lease_expires_at")
        return expires is None or time.time() > expires

    def claim_run(
        self, case_id: str, run_id: str, owner: str, lease_seconds: int
    ) -> bool:
        claimed = False
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT data FROM cases WHERE id = ?", (case_id,)
            ).fetchone()
            if not row:
                return False
            record = json.loads(row[0])
            job = record.get("job")
            if not job or job.get("id") != run_id:
                return False
            status = job.get("status")
            if status == "queued" or (
                status == "processing" and self._lease_expired(job)
            ):
                job.update(
                    status="processing",
                    lease_owner=owner,
                    lease_expires_at=time.time() + lease_seconds,
                )
                db.execute(
                    "UPDATE cases SET data = ? WHERE id = ?",
                    (json.dumps(record), case_id),
                )
                claimed = True
        return claimed

    def renew_run(
        self, case_id: str, run_id: str, owner: str, lease_seconds: int
    ) -> bool:
        renewed = False
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT data FROM cases WHERE id = ?", (case_id,)
            ).fetchone()
            if not row:
                return False
            record = json.loads(row[0])
            job = record.get("job")
            if (
                job
                and job.get("id") == run_id
                and job.get("status") == "processing"
                and job.get("lease_owner") == owner
            ):
                job["lease_expires_at"] = time.time() + lease_seconds
                db.execute(
                    "UPDATE cases SET data = ? WHERE id = ?",
                    (json.dumps(record), case_id),
                )
                renewed = True
        return renewed

    def finish_run(
        self, case_id: str, run_id: str, owner: str, result: dict[str, Any]
    ) -> bool:
        finished = False
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT data FROM cases WHERE id = ?", (case_id,)
            ).fetchone()
            if not row:
                return False
            record = json.loads(row[0])
            job = record.get("job")
            if (
                job
                and job.get("id") == run_id
                and job.get("status") == "processing"
                and job.get("lease_owner") == owner
            ):
                record.update(
                    findings=result.get("findings", []),
                    model_input_preview=result.get("model_input_preview", []),
                )
                job.update(
                    status=result["status"],
                    progress=result["progress"],
                    stage=result["stage"],
                    errors=result["errors"],
                )
                job.pop("lease_owner", None)
                job.pop("lease_expires_at", None)
                db.execute(
                    "UPDATE cases SET data = ? WHERE id = ?",
                    (json.dumps(record), case_id),
                )
                finished = True
        return finished

    def interrupt_pending(self) -> None:
        from datetime import datetime, timezone

        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for case_id, raw in db.execute("SELECT id, data FROM cases").fetchall():
                record = json.loads(raw)
                if record.get("job") and record["job"]["status"] in {
                    "queued",
                    "processing",
                }:
                    record["job"].update(
                        status="interrupted",
                        stage="Interrupted by local restart",
                        updated_at=datetime.now(timezone.utc).isoformat(),
                        errors=["Local processing stopped. Start a new analysis."],
                    )
                    db.execute(
                        "UPDATE cases SET data = ? WHERE id = ?",
                        (json.dumps(record), case_id),
                    )


class LocalDocumentStorage:
    def __init__(self, directory: Path):
        self.directory = directory.resolve()
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.directory / key).resolve()
        if not path.is_relative_to(self.directory):
            raise ProviderError("invalid_storage_key")
        return path

    def put(self, key: str, content: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        path.chmod(0o600)

    def get(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except OSError:
            raise ProviderError("document_unavailable") from None

    def presign_upload(self, key: str) -> dict:
        raise ProviderError("presigned_upload_requires_aws")

    def confirm_upload(self, key: str) -> int:
        return len(self.get(key))