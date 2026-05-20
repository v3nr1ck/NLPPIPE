"""SQLite persistence layer — seeds from control_table.csv on first run, syncs back on save."""
import sqlite3
import csv
import json
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).parent / "pipeline.db"
CONTROL_TABLE_PATH = Path(__file__).parent / "control_table.csv"
CSV_HEADERS = ["client_name", "source_field", "source_value",
               "target_field", "target_value", "strategy", "priority"]


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def db():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS rules (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                client_name  TEXT    NOT NULL DEFAULT '*',
                source_field TEXT    NOT NULL,
                source_value TEXT    NOT NULL DEFAULT '*',
                target_field TEXT    NOT NULL DEFAULT '',
                target_value TEXT    NOT NULL DEFAULT '',
                strategy     TEXT    NOT NULL CHECK(strategy IN ('map','context','ignore')),
                priority     INTEGER NOT NULL DEFAULT 5,
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS work_order_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                client_name     TEXT,
                vendor          TEXT,
                input_json      TEXT,
                mapped_fields   TEXT,
                context_fields  TEXT,
                ignored_fields  TEXT,
                trade_id        TEXT,
                equipment_id    TEXT,
                problem_type_id TEXT,
                problem_code_id TEXT,
                confidence      REAL,
                requires_review INTEGER,
                review_reason   TEXT,
                inference_ms    REAL,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        count = conn.execute("SELECT COUNT(*) FROM rules").fetchone()[0]
        if count == 0:
            _seed_from_csv(conn)


def _seed_from_csv(conn: sqlite3.Connection) -> None:
    if not CONTROL_TABLE_PATH.exists():
        return
    with open(CONTROL_TABLE_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sf = (row.get("source_field") or "").strip()
            if not sf or sf.startswith("#"):
                continue
            conn.execute(
                "INSERT INTO rules "
                "(client_name,source_field,source_value,target_field,target_value,strategy,priority) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    (row.get("client_name") or "*").strip() or "*",
                    sf,
                    (row.get("source_value") or "*").strip() or "*",
                    (row.get("target_field") or "").strip(),
                    (row.get("target_value") or "").strip(),
                    (row.get("strategy") or "context").strip(),
                    int(row.get("priority") or 5),
                ),
            )


def sync_to_csv() -> None:
    """Write all DB rules back to control_table.csv so the pipeline picks them up."""
    rules = get_rules()
    with open(CONTROL_TABLE_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()
        for r in rules:
            writer.writerow({k: r[k] for k in CSV_HEADERS})


# ── CRUD ──────────────────────────────────────────────────────────────────────

def get_rules(client_name: str | None = None, strategy: str | None = None) -> list[dict]:
    with db() as conn:
        q = "SELECT * FROM rules WHERE 1=1"
        params: list = []
        if client_name:
            q += " AND (client_name=? OR client_name='*')"
            params.append(client_name)
        if strategy:
            q += " AND strategy=?"
            params.append(strategy)
        q += " ORDER BY priority DESC, client_name, source_field"
        return [dict(r) for r in conn.execute(q, params).fetchall()]


def get_rules_grouped() -> dict[str, list[dict]]:
    """Return rules bucketed by strategy."""
    all_rules = get_rules()
    return {
        "map":     [r for r in all_rules if r["strategy"] == "map"],
        "context": [r for r in all_rules if r["strategy"] == "context"],
        "ignore":  [r for r in all_rules if r["strategy"] == "ignore"],
    }


def create_rule(
    client_name: str, source_field: str, source_value: str,
    target_field: str, target_value: str, strategy: str, priority: int = 5,
) -> int:
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO rules "
            "(client_name,source_field,source_value,target_field,target_value,strategy,priority) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                client_name or "*",
                source_field,
                source_value or "*",
                target_field or "",
                target_value or "",
                strategy,
                int(priority),
            ),
        )
        return cur.lastrowid  # type: ignore[return-value]


def delete_rule(rule_id: int) -> None:
    with db() as conn:
        conn.execute("DELETE FROM rules WHERE id=?", (rule_id,))


def get_clients() -> list[str]:
    with db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT client_name FROM rules "
            "WHERE client_name != '*' ORDER BY client_name"
        ).fetchall()
        return [r[0] for r in rows]


def log_work_order(client_name: str, vendor: str, input_fields: dict, result) -> int:
    with db() as conn:
        cur = conn.execute(
            """INSERT INTO work_order_log
               (client_name,vendor,input_json,mapped_fields,context_fields,ignored_fields,
                trade_id,equipment_id,problem_type_id,problem_code_id,
                confidence,requires_review,review_reason,inference_ms)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                client_name, vendor,
                json.dumps(input_fields),
                json.dumps(result.mapped_fields),
                json.dumps(result.context_fields),
                json.dumps(result.ignored_fields),
                result.mapping.trade_id.value,
                result.mapping.equipment_id.value,
                result.mapping.problem_type_id.value,
                result.mapping.problem_code_id.value,
                result.confidence_score,
                int(result.requires_review),
                result.review_reason,
                result.inference_time_ms,
            ),
        )
        return cur.lastrowid  # type: ignore[return-value]
