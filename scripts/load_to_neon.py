"""Safely upsert processed CSV datasets into Neon PostgreSQL.

Default behavior is non-destructive: existing dimension/fact records are
updated by their primary keys and existing campaign proposals are preserved.
Use --replace-existing only when an intentional full dataset replacement is
required and a database backup has been taken.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from psycopg2 import sql

BASE_DIR = Path(__file__).resolve().parents[1]
CLEAN_DIR = BASE_DIR / "data" / "processed" / "clean_db_ready"
SCHEMA_PATH = CLEAN_DIR / "schema_neon.sql"

TABLES = [
    ("dim_products", "dim_products.csv", ("product_id",), "update"),
    ("dim_campaigns", "dim_campaigns.csv", ("campaign_id",), "update"),
    ("fct_inventory_snapshots", "fct_inventory_snapshots.csv", ("product_id", "store_id"), "update"),
    ("fct_supplier_replenishment", "fct_supplier_replenishment.csv", ("supplier_id", "product_id"), "update"),
    ("fct_campaign_cost_assumptions", "fct_campaign_cost_assumptions.csv", ("campaign_id",), "update"),
    # Seed proposal files must never overwrite live human approval decisions.
    ("fct_daily_sales", "fct_daily_sales.csv", ("product_id", "store_id", "date"), "update"),
]

# Historical proposal CSV is deliberately not imported into the live proposal
# table: it contains pre-approved sample decisions. Runtime proposals must be
# created by the API and approved by authenticated human accounts.

TRUNCATE_ORDER = [
    "fct_daily_sales",
    "fct_campaign_proposals",
    "fct_campaign_cost_assumptions",
    "fct_supplier_replenishment",
    "fct_inventory_snapshots",
    "dim_campaigns",
    "dim_products",
]


def _upsert_table(cursor, connection, table: str, csv_path: Path, key_columns: tuple[str, ...], conflict_mode: str) -> int:
    stage = f"stage_{table}"
    cursor.execute(
        sql.SQL("CREATE TEMP TABLE {} (LIKE {} INCLUDING DEFAULTS) ON COMMIT DROP").format(
            sql.Identifier(stage), sql.Identifier(table)
        )
    )
    copy_query = sql.SQL("COPY {} FROM STDIN WITH CSV HEADER NULL ''").format(sql.Identifier(stage))
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        cursor.copy_expert(copy_query.as_string(connection), handle)

    cursor.execute(
        sql.SQL("SELECT column_name FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = %s ORDER BY ordinal_position"),
        (table,),
    )
    columns = [row[0] for row in cursor.fetchall()]
    if not columns:
        raise RuntimeError(f"Table '{table}' was not found after schema initialization.")
    missing_keys = set(key_columns) - set(columns)
    if missing_keys:
        raise RuntimeError(f"Table '{table}' is missing primary-key columns: {sorted(missing_keys)}")

    insert = sql.SQL("INSERT INTO {} ({}) SELECT {} FROM {}").format(
        sql.Identifier(table),
        sql.SQL(", ").join(map(sql.Identifier, columns)),
        sql.SQL(", ").join(map(sql.Identifier, columns)),
        sql.Identifier(stage),
    )
    if conflict_mode == "preserve":
        statement = insert + sql.SQL(" ON CONFLICT ({}) DO NOTHING").format(
            sql.SQL(", ").join(map(sql.Identifier, key_columns))
        )
    else:
        update_columns = [column for column in columns if column not in key_columns]
        if not update_columns:
            statement = insert + sql.SQL(" ON CONFLICT ({}) DO NOTHING").format(
                sql.SQL(", ").join(map(sql.Identifier, key_columns))
            )
        else:
            assignments = sql.SQL(", ").join(
                sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(column), sql.Identifier(column))
                for column in update_columns
            )
            statement = insert + sql.SQL(" ON CONFLICT ({}) DO UPDATE SET {}").format(
                sql.SQL(", ").join(map(sql.Identifier, key_columns)), assignments
            )
    cursor.execute(statement)
    cursor.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table)))
    return int(cursor.fetchone()[0])


def load_tables(replace_existing: bool = False) -> dict[str, int]:
    load_dotenv(BASE_DIR / ".env")
    db_url = os.getenv("DATABASE_URL", "").strip()
    if not db_url:
        raise RuntimeError("DATABASE_URL is not configured in the environment or project .env file.")
    if not SCHEMA_PATH.is_file():
        raise FileNotFoundError(f"Schema file not found: {SCHEMA_PATH}")

    missing_files = [filename for _, filename, _, _ in TABLES if not (CLEAN_DIR / filename).is_file()]
    if missing_files:
        raise FileNotFoundError("Required processed CSV files are missing: " + ", ".join(missing_files))

    connection = psycopg2.connect(db_url)
    counts: dict[str, int] = {}
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
                if replace_existing:
                    print("WARNING: --replace-existing requested; clearing target tables (CASCADE can also clear runtime proposals).")
                    cursor.execute(
                        sql.SQL("TRUNCATE TABLE {} CASCADE").format(
                            sql.SQL(", ").join(map(sql.Identifier, TRUNCATE_ORDER))
                        )
                    )

                for table, filename, keys, conflict_mode in TABLES:
                    count = _upsert_table(
                        cursor,
                        connection,
                        table,
                        CLEAN_DIR / filename,
                        keys,
                        conflict_mode,
                    )
                    counts[table] = count
                    print(f"{table}: {count:,} rows present after ingestion")
        print("Neon ingestion transaction committed successfully.")
        return counts
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Destructively truncate all target tables before loading. Back up Neon first.",
    )
    args = parser.parse_args()
    load_tables(replace_existing=args.replace_existing)


if __name__ == "__main__":
    main()
