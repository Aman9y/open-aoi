"""Inspection history persistence (SQLite + result JSON)."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from ..config import Settings
from ..schemas.inspection import InspectionResult, MultiViewResult
from .db import connect, init_db


class InspectionRepository:
    def __init__(self, cfg: Settings) -> None:
        self._db_path: Path = cfg.db_path
        init_db(self._db_path)

    def _insert(self, r: InspectionResult | MultiViewResult) -> None:
        conn = connect(self._db_path)
        try:
            conn.execute(
                """INSERT OR REPLACE INTO inspections
                   (inspection_id, timestamp, reference_id, profile_kind, status,
                    reason, overall_confidence, inspection_time_ms, defect_count,
                    result_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    r.inspection_id, r.timestamp, r.reference_id, r.profile_kind,
                    r.status.value, r.reason.value, r.overall_confidence,
                    r.inspection_time_ms, len(r.defects), r.model_dump_json(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def save(self, result: InspectionResult) -> None:
        self._insert(result)

    def save_multi(self, result: MultiViewResult) -> None:
        self._insert(result)

    def get(self, inspection_id: str) -> InspectionResult | MultiViewResult | None:
        conn = connect(self._db_path)
        try:
            row = conn.execute(
                "SELECT result_json FROM inspections WHERE inspection_id = ?",
                (inspection_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        raw = row["result_json"]
        if '"result_type":"multi"' in raw or '"result_type": "multi"' in raw:
            return MultiViewResult.model_validate_json(raw)
        return InspectionResult.model_validate_json(raw)

    def list(
        self,
        *,
        status: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict]:
        clauses: list[str] = []
        params: list[object] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if date_from:
            clauses.append("timestamp >= ?")
            params.append(date_from)
        if date_to:
            clauses.append("timestamp <= ?")
            params.append(date_to)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        conn = connect(self._db_path)
        try:
            rows = conn.execute(
                f"""SELECT inspection_id, timestamp, reference_id, profile_kind, status,
                           reason, overall_confidence, inspection_time_ms, defect_count
                    FROM inspections {where}
                    ORDER BY timestamp DESC
                    LIMIT ? OFFSET ?""",
                (*params, limit, offset),
            ).fetchall()
        finally:
            conn.close()
        return [dict(r) for r in rows]

    def stats(self, date_from: str | None = None) -> dict:
        conn = connect(self._db_path)
        try:
            where = "WHERE timestamp >= ?" if date_from else ""
            params = (date_from,) if date_from else ()
            total = conn.execute(
                f"SELECT COUNT(*) c, AVG(inspection_time_ms) t FROM inspections {where}",
                params,
            ).fetchone()
            by_status = conn.execute(
                f"SELECT status, COUNT(*) c FROM inspections {where} GROUP BY status",
                params,
            ).fetchall()
        finally:
            conn.close()

        counts = {r["status"]: r["c"] for r in by_status}
        return {
            "total": total["c"] or 0,
            "avg_time_ms": round(total["t"] or 0.0, 1),
            "good": counts.get("GOOD", 0),
            "defective": counts.get("DEFECTIVE", 0),
            "review": counts.get("REVIEW", 0),
        }

    def export_csv(self, **filters) -> str:
        rows = self.list(limit=100_000, **filters)
        buf = io.StringIO()
        fields = [
            "inspection_id", "timestamp", "reference_id", "profile_kind", "status",
            "reason", "overall_confidence", "inspection_time_ms", "defect_count",
        ]
        writer = csv.DictWriter(buf, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
        return buf.getvalue()
