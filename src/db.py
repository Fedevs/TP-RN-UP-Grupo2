import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "products.db"

# Se crea acá y no en create_db.py para que funcione también con bases creadas antes.
AUCTIONS_TABLE = """
    CREATE TABLE IF NOT EXISTS auctions (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        title          TEXT    NOT NULL,
        description    TEXT    NOT NULL,
        category       TEXT    NOT NULL,
        product_name   TEXT    NOT NULL,
        condition      TEXT,
        starting_price INTEGER NOT NULL CHECK (starting_price > 0),
        duration_days  INTEGER NOT NULL CHECK (duration_days > 0),
        created_at     TEXT    NOT NULL,
        ends_at        TEXT    NOT NULL
    )
"""


def connect():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute(AUCTIONS_TABLE)
    return connection
