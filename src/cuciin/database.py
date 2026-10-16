"""Setup koneksi & tabel database SQLite."""

import hashlib
import hmac
import os
import secrets
import sqlite3
from pathlib import Path

DB_PATH = Path("cuciin.db")
PASSWORD_ITERATIONS = 600_000


def _hash_password(password: str) -> str:
    """Simpan password sebagai hash PBKDF2 dengan salt unik."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored_hash: str) -> bool:
    """Bandingkan password dengan hash yang tersimpan."""
    algorithm, iterations, salt_hex, digest_hex = stored_hash.split("$")
    if algorithm != "pbkdf2_sha256":
        return False

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        int(iterations),
    )
    return hmac.compare_digest(digest.hex(), digest_hex)


def get_connection():
    """Bikin koneksi ke database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Bikin tabel kalau belum ada."""
    conn = get_connection()
    try:
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
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        admin_exists = cursor.execute(
            "SELECT 1 FROM admins LIMIT 1"
        ).fetchone()
        if admin_exists is None:
            username = os.environ.get("CUCIIN_ADMIN_USERNAME", "admin").strip()
            password = os.environ.get("CUCIIN_ADMIN_PASSWORD", "password")
            if not username or not password:
                raise ValueError("Username dan password admin awal tidak boleh kosong.")
            cursor.execute(
                "INSERT INTO admins (username, password_hash) VALUES (?, ?)",
                (username, _hash_password(password)),
            )

        conn.commit()
    finally:
        conn.close()


def create_admin(username: str, password: str) -> None:
    """Tambahkan akun admin baru; password tidak disimpan dalam bentuk teks."""
    username = username.strip()
    if not username or not password:
        raise ValueError("Username dan password tidak boleh kosong.")

    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO admins (username, password_hash) VALUES (?, ?)",
            (username, _hash_password(password)),
        )
        conn.commit()
    finally:
        conn.close()


def verify_admin(username: str, password: str) -> bool:
    """Periksa username dan password admin dari database."""
    conn = get_connection()
    try:
        admin = conn.execute(
            "SELECT password_hash FROM admins WHERE username = ?",
            (username.strip(),),
        ).fetchone()
    finally:
        conn.close()

    return admin is not None and _verify_password(password, admin["password_hash"])


if __name__ == "__main__":
    init_db()
    print("Database siap.")