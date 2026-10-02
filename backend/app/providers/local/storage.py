import json
import sqlite3
from pathlib import Path
from typing import Any, Callable
from app.providers.interfaces import ProviderError


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
