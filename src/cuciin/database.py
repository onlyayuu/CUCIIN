"""Setup koneksi & tabel database SQLite."""

import sqlite3
from pathlib import Path

DB_PATH = Path("cuciin.db")


def get_connection():
    """Bikin koneksi ke database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Bikin tabel kalau belum ada."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nama TEXT NOT NULL,
            no_hp TEXT,
            berat REAL NOT NULL,
            layanan TEXT NOT NULL,
            harga INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'dicuci',
            no_rak TEXT,
            sudah_bayar INTEGER DEFAULT 0,
            jumlah_bayar INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            diambil_at TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("Database siap.")