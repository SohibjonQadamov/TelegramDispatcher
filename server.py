from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DB_PATH = Path("orders.db")

def now():
    return datetime.now(timezone.utc).isoformat()

def db_execute(sql, params=()):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid

def db_fetchall(sql, params=()):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(sql, params).fetchall()]

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS stores (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, phone TEXT,
            address TEXT, latitude REAL, longitude REAL,
            logo TEXT, is_active INTEGER DEFAULT 1, created_at TEXT
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT, store_id INTEGER DEFAULT 1,
            name TEXT, price INTEGER, category TEXT, emoji TEXT,
            description TEXT, image TEXT, is_available INTEGER DEFAULT 1,
            created_at TEXT, FOREIGN KEY (store_id) REFERENCES stores(id)
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, store_id INTEGER DEFAULT 1,
            user_id INTEGER, customer_name TEXT, phone TEXT, address TEXT,
            lat REAL, lon REAL, items TEXT, total INTEGER, status TEXT DEFAULT 'NEW',
            created_at TEXT, FOREIGN KEY (store_id) REFERENCES stores(id)
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER, store_id INTEGER, role TEXT DEFAULT 'user',
            name TEXT, phone TEXT, registered_at TEXT,
            PRIMARY KEY (user_id, store_id)
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS discounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, store_id INTEGER,
            product_id INTEGER, old_price INTEGER, new_price INTEGER,
            badge TEXT, is_active INTEGER DEFAULT 1
        )""")
        conn.commit()

init_db()

# === API: Stores ===
@app.get("/api/stores")
def get_stores():
    return JSONResponse(db_fetchall("SELECT * FROM stores WHERE is_active=1"))

@app.post("/api/stores")
async def add_store(request: Request):
    d = await request.json()
    db_execute("INSERT INTO stores (name, phone, address, latitude, longitude, created_at) VALUES (?,?,?,?,?,?)",
               (d['name'], d.get('phone'), d.get('address'), d.get('lat'), d.get('lon'), now()))
    return {"ok": True}

# === API: Products ===
@app.get("/api/products")
def get_products(store_id: int = 1):
    return JSONResponse(db_fetchall("SELECT * FROM products WHERE store_id=? AND is_available=1", (store_id,)))

@app.post("/api/products")
async def add_product(request: Request):
    d = await request.json()
    db_execute("INSERT INTO products (store_id, name, price, category, emoji, description, created_at) VALUES (?,?,?,?,?,?,?)",
               (d.get('store_id', 1), d['name'], d['price'], d['category'], d.get('emoji','🍔'), d.get('description',''), now()))
    return {"ok": True}

@app.delete("/api/products/{pid}")
def delete_product(pid: int):
    db_execute("UPDATE products SET is_available=0 WHERE id=?", (pid,))
    return {"ok": True}

# === API: Discounts ===
@app.get("/api/discounts")
def get_discounts(store_id: int = 1):
    return JSONResponse(db_fetchall("SELECT * FROM discounts WHERE store_id=? AND is_active=1", (store_id,)))

# === API: Orders ===
@app.get("/api/orders")
def get_orders(store_id: int = 1):
    return JSONResponse(db_fetchall("SELECT * FROM orders WHERE store_id=? ORDER BY id DESC", (store_id,)))

@app.post("/api/orders")
async def create_order(request: Request):
    d = await request.json()
    oid = db_execute("INSERT INTO orders (store_id, user_id, customer_name, phone, address, lat, lon, items, total, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
               (d.get('store_id',1), d.get('user_id'), d['name'], d['phone'], d['address'], d.get('lat'), d.get('lon'), d['items'], d['total'], now()))
    return {"ok": True, "order_id": oid}

# === Static ===
app.mount("/", StaticFiles(directory="webapp", html=True), name="static")
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)