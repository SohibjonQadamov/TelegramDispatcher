from pathlib import Path
import sqlite3

DB_PATH = Path("database.db")

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT,
                status TEXT DEFAULT 'NEW',
                full_name TEXT,
                phone TEXT,
                address TEXT,
                product_id INTEGER,
                FOREIGN KEY (product_id) REFERENCES products (id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                price REAL,
                description TEXT,
                image_url TEXT
            )
        """)
        conn.commit()

def create_order(full_name, phone, address, product_id):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "INSERT INTO orders (created_at, status, full_name, phone, address, product_id) VALUES (datetime('now'), 'NEW', ?, ?, ?, ?)",
            (full_name, phone, address, product_id)
        )
        conn.commit()
        return cur.lastrowid

def fetch_orders():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute("SELECT * FROM orders").fetchall()]

def fetch_products():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute("SELECT * FROM products").fetchall()]