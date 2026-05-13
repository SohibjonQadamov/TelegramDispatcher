from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone, date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import aiohttp
from aiohttp import web
from aiogram.types import WebAppInfo
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
GROUP_CHAT_ID = int((os.getenv("GROUP_CHAT_ID") or "0").strip() or 0)
ADMIN_IDS = [int(x) for x in (os.getenv("ADMIN_IDS") or "").split(",") if x.strip()]
PAYME_KEY = os.getenv("PAYME_KEY", "")
CLICK_SERVICE_ID = os.getenv("CLICK_SERVICE_ID", "")
CLICK_SECRET_KEY = os.getenv("CLICK_SECRET_KEY", "")
YANDEX_DELIVERY_TOKEN = os.getenv("YANDEX_DELIVERY_TOKEN", "")
YANDEX_DELIVERY_URL = "https://b2b.taxi.yandex.net/b2b/cargo/integration/v2"

if not BOT_TOKEN or not GROUP_CHAT_ID:
    raise RuntimeError(".env ni to'ldiring")

DB_PATH = Path("orders.db")
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()   # Neon/Render PostgreSQL URL
USE_PG = bool(DATABASE_URL)
WEBAPP_PORT = int(os.environ.get("PORT", 8080))
WEBAPP_URL = os.getenv("WEBAPP_URL") or "https://d0fc-213-230-80-60.ngrok-free.app"

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("bot")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ================= DB =================
# Schema — shared DDL logic; caller passes execute/executemany functions
_TABLES_SQL = [
    # orders
    """CREATE TABLE IF NOT EXISTS orders (
        id {id_def},
        created_at TEXT, status TEXT DEFAULT 'NEW',
        full_name TEXT, phone TEXT, address TEXT,
        lat REAL, lon REAL,
        items TEXT, total INTEGER,
        created_by_id BIGINT, created_by_name TEXT,
        accepted_by_id BIGINT, accepted_by_name TEXT,
        accepted_at TEXT, closed_at TEXT,
        group_message_id INTEGER,
        store_id INTEGER, target_chat_id BIGINT,
        yandex_claim_id TEXT, yandex_status TEXT,
        yandex_tracking_url TEXT, delivery_type TEXT DEFAULT 'own'
    )""",
    # users
    """CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY,
        role TEXT DEFAULT 'user',
        registered_at TEXT,
        first_name TEXT, last_name TEXT,
        username TEXT, language_code TEXT,
        photo_url TEXT, onboarded INTEGER DEFAULT 0,
        region TEXT, city TEXT, district TEXT
    )""",
    # stores  ← CENTRAL TABLE: stores/products/orders separated
    """CREATE TABLE IF NOT EXISTS stores (
        id {id_def},
        admin_id BIGINT UNIQUE,
        name TEXT, type TEXT, emoji TEXT, bg_color TEXT,
        delivery_fee INTEGER DEFAULT 15000,
        eta INTEGER DEFAULT 25,
        radius REAL DEFAULT 5,
        min_order INTEGER DEFAULT 50000,
        hours_weekday TEXT DEFAULT '09:00-22:00',
        hours_weekend TEXT DEFAULT '10:00-23:00',
        is_open INTEGER DEFAULT 1,
        accent_color TEXT DEFAULT '#FF6B35',
        cover_url TEXT, description TEXT,
        phone TEXT, address TEXT,
        region TEXT, city TEXT, district TEXT,
        lat REAL, lon REAL
    )""",
    # products  ← SEPARATE from stores
    """CREATE TABLE IF NOT EXISTS products (
        id {id_def},
        store_id INTEGER,
        name TEXT, price INTEGER,
        desc TEXT, emoji TEXT, cat TEXT,
        old_price INTEGER, discount_qty INTEGER, discount_end TEXT
    )""",
    # ratings
    """CREATE TABLE IF NOT EXISTS ratings (
        id {id_def},
        order_id INTEGER UNIQUE,
        user_id BIGINT, store_id INTEGER,
        stars INTEGER, comment TEXT, created_at TEXT
    )""",
    # subscriptions
    """CREATE TABLE IF NOT EXISTS subscriptions (
        id {id_def},
        store_id INTEGER UNIQUE,
        admin_id BIGINT,
        plan TEXT DEFAULT 'free',
        orders_this_month INTEGER DEFAULT 0,
        billing_month TEXT, next_billing TEXT, created_at TEXT
    )""",
    # transactions
    """CREATE TABLE IF NOT EXISTS transactions (
        id {id_def},
        provider TEXT, provider_tx_id TEXT UNIQUE,
        order_id INTEGER, amount INTEGER,
        state INTEGER DEFAULT 1,
        created_at TEXT, performed_at TEXT,
        cancelled_at TEXT, reason INTEGER
    )""",
    # promo_codes  ← Marketing tool
    """CREATE TABLE IF NOT EXISTS promo_codes (
        id {id_def},
        code TEXT UNIQUE,
        store_id INTEGER,
        discount_pct INTEGER DEFAULT 0,
        discount_amount INTEGER DEFAULT 0,
        min_order INTEGER DEFAULT 0,
        max_uses INTEGER DEFAULT 0,
        used_count INTEGER DEFAULT 0,
        expires_at TEXT,
        active INTEGER DEFAULT 1,
        created_at TEXT,
        created_by BIGINT
    )""",
    # promo_uses — track per-user usage
    """CREATE TABLE IF NOT EXISTS promo_uses (
        id {id_def},
        promo_id INTEGER,
        user_id BIGINT,
        order_id INTEGER,
        used_at TEXT
    )""",
    # referrals — user acquisition
    """CREATE TABLE IF NOT EXISTS referrals (
        id {id_def},
        referrer_id BIGINT,
        referred_id BIGINT UNIQUE,
        bonus_amount INTEGER DEFAULT 10000,
        status TEXT DEFAULT 'pending',
        created_at TEXT,
        rewarded_at TEXT
    )""",
]


def init_db():
    if USE_PG:
        _init_db_pg()
    else:
        _init_db_sqlite()


def _init_db_pg():
    import psycopg2, psycopg2.extras
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            for tpl in _TABLES_SQL:
                cur.execute(tpl.format(id_def="BIGSERIAL PRIMARY KEY"))
            # Safe column migrations for PG (IF NOT EXISTS supported PG 9.6+)
            safe_cols = [
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS store_id INTEGER",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS target_chat_id BIGINT",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS yandex_claim_id TEXT",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS yandex_status TEXT",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS yandex_tracking_url TEXT",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivery_type TEXT DEFAULT 'own'",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS group_message_id INTEGER",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS first_name TEXT",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_name TEXT",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS username TEXT",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS language_code TEXT",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS photo_url TEXT",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarded INTEGER DEFAULT 0",
                "ALTER TABLE stores ADD COLUMN IF NOT EXISTS admin_id BIGINT",
                "ALTER TABLE stores ADD COLUMN IF NOT EXISTS name TEXT",
                "ALTER TABLE stores ADD COLUMN IF NOT EXISTS type TEXT",
                "ALTER TABLE stores ADD COLUMN IF NOT EXISTS emoji TEXT",
                "ALTER TABLE stores ADD COLUMN IF NOT EXISTS bg_color TEXT",
                "ALTER TABLE stores ADD COLUMN IF NOT EXISTS delivery_fee INTEGER DEFAULT 15000",
                "ALTER TABLE stores ADD COLUMN IF NOT EXISTS eta INTEGER DEFAULT 25",
                "ALTER TABLE stores ADD COLUMN IF NOT EXISTS radius REAL DEFAULT 5",
                "ALTER TABLE stores ADD COLUMN IF NOT EXISTS min_order INTEGER DEFAULT 50000",
                "ALTER TABLE stores ADD COLUMN IF NOT EXISTS hours_weekday TEXT DEFAULT '09:00-22:00'",
                "ALTER TABLE stores ADD COLUMN IF NOT EXISTS hours_weekend TEXT DEFAULT '10:00-23:00'",
                "ALTER TABLE stores ADD COLUMN IF NOT EXISTS is_open INTEGER DEFAULT 1",
                "ALTER TABLE stores ADD COLUMN IF NOT EXISTS accent_color TEXT DEFAULT '#FF6B35'",
                "ALTER TABLE stores ADD COLUMN IF NOT EXISTS cover_url TEXT",
                "ALTER TABLE stores ADD COLUMN IF NOT EXISTS description TEXT",
                "ALTER TABLE stores ADD COLUMN IF NOT EXISTS phone TEXT",
                "ALTER TABLE stores ADD COLUMN IF NOT EXISTS address TEXT",
                "ALTER TABLE stores ADD COLUMN IF NOT EXISTS region TEXT",
                "ALTER TABLE stores ADD COLUMN IF NOT EXISTS city TEXT",
                "ALTER TABLE stores ADD COLUMN IF NOT EXISTS district TEXT",
                "ALTER TABLE stores ADD COLUMN IF NOT EXISTS lat REAL",
                "ALTER TABLE stores ADD COLUMN IF NOT EXISTS lon REAL",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS region TEXT",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS city TEXT",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS district TEXT",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by BIGINT",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS bonus_balance INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone TEXT",
                "ALTER TABLE products ADD COLUMN IF NOT EXISTS photo_url TEXT",
                "ALTER TABLE products ADD COLUMN IF NOT EXISTS is_featured INTEGER DEFAULT 0",
                "ALTER TABLE products ADD COLUMN IF NOT EXISTS store_id INTEGER",
                "ALTER TABLE products ADD COLUMN IF NOT EXISTS name TEXT",
                "ALTER TABLE products ADD COLUMN IF NOT EXISTS price INTEGER",
                "ALTER TABLE products ADD COLUMN IF NOT EXISTS desc TEXT",
                "ALTER TABLE products ADD COLUMN IF NOT EXISTS emoji TEXT",
                "ALTER TABLE products ADD COLUMN IF NOT EXISTS cat TEXT",
                "ALTER TABLE products ADD COLUMN IF NOT EXISTS old_price INTEGER",
                "ALTER TABLE products ADD COLUMN IF NOT EXISTS discount_qty INTEGER",
                "ALTER TABLE products ADD COLUMN IF NOT EXISTS discount_end TEXT",
            ]
            for col in safe_cols:
                try: cur.execute(col)
                except Exception: pass
        conn.commit()
        logger.info("PostgreSQL schema ready ✓")
    finally:
        conn.close()


def _init_db_sqlite():
    with sqlite3.connect(DB_PATH) as conn:
        for tpl in _TABLES_SQL:
            conn.execute(tpl.format(id_def="INTEGER PRIMARY KEY AUTOINCREMENT"))
        # COMPREHENSIVE migrations — every possible column for every table.
        # try/except silently skips columns that already exist.
        safe_cols = [
            # orders
            "ALTER TABLE orders ADD COLUMN store_id INTEGER",
            "ALTER TABLE orders ADD COLUMN target_chat_id INTEGER",
            "ALTER TABLE orders ADD COLUMN yandex_claim_id TEXT",
            "ALTER TABLE orders ADD COLUMN yandex_status TEXT",
            "ALTER TABLE orders ADD COLUMN yandex_tracking_url TEXT",
            "ALTER TABLE orders ADD COLUMN delivery_type TEXT DEFAULT 'own'",
            "ALTER TABLE orders ADD COLUMN group_message_id INTEGER",
            # users
            "ALTER TABLE users ADD COLUMN first_name TEXT",
            "ALTER TABLE users ADD COLUMN last_name TEXT",
            "ALTER TABLE users ADD COLUMN username TEXT",
            "ALTER TABLE users ADD COLUMN language_code TEXT",
            "ALTER TABLE users ADD COLUMN photo_url TEXT",
            "ALTER TABLE users ADD COLUMN onboarded INTEGER DEFAULT 0",
            # stores — all columns
            "ALTER TABLE stores ADD COLUMN admin_id INTEGER",
            "ALTER TABLE stores ADD COLUMN name TEXT",
            "ALTER TABLE stores ADD COLUMN type TEXT",
            "ALTER TABLE stores ADD COLUMN emoji TEXT",
            "ALTER TABLE stores ADD COLUMN bg_color TEXT",
            "ALTER TABLE stores ADD COLUMN delivery_fee INTEGER DEFAULT 15000",
            "ALTER TABLE stores ADD COLUMN eta INTEGER DEFAULT 25",
            "ALTER TABLE stores ADD COLUMN radius REAL DEFAULT 5",
            "ALTER TABLE stores ADD COLUMN min_order INTEGER DEFAULT 50000",
            "ALTER TABLE stores ADD COLUMN hours_weekday TEXT DEFAULT '09:00-22:00'",
            "ALTER TABLE stores ADD COLUMN hours_weekend TEXT DEFAULT '10:00-23:00'",
            "ALTER TABLE stores ADD COLUMN is_open INTEGER DEFAULT 1",
            "ALTER TABLE stores ADD COLUMN accent_color TEXT DEFAULT '#FF6B35'",
            "ALTER TABLE stores ADD COLUMN cover_url TEXT",
            "ALTER TABLE stores ADD COLUMN description TEXT",
            "ALTER TABLE stores ADD COLUMN phone TEXT",
            "ALTER TABLE stores ADD COLUMN address TEXT",
            "ALTER TABLE stores ADD COLUMN region TEXT",
            "ALTER TABLE stores ADD COLUMN city TEXT",
            "ALTER TABLE stores ADD COLUMN district TEXT",
            "ALTER TABLE stores ADD COLUMN lat REAL",
            "ALTER TABLE stores ADD COLUMN lon REAL",
            "ALTER TABLE users ADD COLUMN region TEXT",
            "ALTER TABLE users ADD COLUMN city TEXT",
            "ALTER TABLE users ADD COLUMN district TEXT",
            "ALTER TABLE users ADD COLUMN referred_by INTEGER",
            "ALTER TABLE users ADD COLUMN bonus_balance INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN phone TEXT",
            "ALTER TABLE products ADD COLUMN photo_url TEXT",
            "ALTER TABLE products ADD COLUMN is_featured INTEGER DEFAULT 0",
            # products — ALL columns
            "ALTER TABLE products ADD COLUMN store_id INTEGER",
            "ALTER TABLE products ADD COLUMN name TEXT",
            "ALTER TABLE products ADD COLUMN price INTEGER",
            "ALTER TABLE products ADD COLUMN desc TEXT",
            "ALTER TABLE products ADD COLUMN emoji TEXT",
            "ALTER TABLE products ADD COLUMN cat TEXT",
            "ALTER TABLE products ADD COLUMN old_price INTEGER",
            "ALTER TABLE products ADD COLUMN discount_qty INTEGER",
            "ALTER TABLE products ADD COLUMN discount_end TEXT",
        ]
        for col in safe_cols:
            try: conn.execute(col)
            except sqlite3.OperationalError: pass
        conn.commit()
        logger.info("SQLite schema ready ✓")


# ── PostgreSQL helpers ──────────────────────────────────────────────────────
def _pg_conn():
    import psycopg2, psycopg2.extras
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)

def _pg(sql: str) -> str:
    """Convert SQLite ? placeholders to PostgreSQL %s"""
    return sql.replace("?", "%s")

# ── Unified DB API ───────────────────────────────────────────────────────────
def db_fetchone(sql, params=()):
    if USE_PG:
        conn = _pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(_pg(sql), params)
                row = cur.fetchone()
                return dict(row) if row else None
        finally:
            conn.close()
    else:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(sql, params).fetchone()
            return dict(row) if row else None


def db_fetchall(sql, params=()):
    if USE_PG:
        conn = _pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(_pg(sql), params)
                return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()
    else:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(sql, params).fetchall()]


def db_execute(sql, params=()):
    if USE_PG:
        conn = _pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(_pg(sql), params)
            conn.commit()
        finally:
            conn.close()
    else:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(sql, params)
            conn.commit()


def create_order(full_name, phone, address, lat, lon, items, total, uid, uname, store_id=None, target_chat_id=None):
    if USE_PG:
        conn = _pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO orders (created_at, status, full_name, phone, address, lat, lon, items, total, created_by_id, created_by_name, store_id, target_chat_id) VALUES (%s, 'NEW', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                    (now_iso(), full_name, phone, address, lat, lon, items, total, uid, uname, store_id, target_chat_id)
                )
                oid = cur.fetchone()["id"]
            conn.commit()
            return int(oid)
        finally:
            conn.close()
    else:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.execute(
                "INSERT INTO orders (created_at, status, full_name, phone, address, lat, lon, items, total, created_by_id, created_by_name, store_id, target_chat_id) VALUES (?, 'NEW', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (now_iso(), full_name, phone, address, lat, lon, items, total, uid, uname, store_id, target_chat_id)
            )
            conn.commit()
            return int(cur.lastrowid)


def get_order(oid):
    return db_fetchone("SELECT * FROM orders WHERE id=?", (oid,))


def set_group_message_id(oid, mid):
    db_execute("UPDATE orders SET group_message_id=? WHERE id=?", (mid, oid))


def try_accept_order(oid, cid, cname):
    if USE_PG:
        conn = _pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE orders SET status='IN_PROGRESS', accepted_by_id=%s, accepted_by_name=%s, accepted_at=%s WHERE id=%s AND status='NEW'",
                    (cid, cname, now_iso(), oid)
                )
                rows = cur.rowcount
            conn.commit()
            return rows == 1
        finally:
            conn.close()
    else:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.execute(
                "UPDATE orders SET status='IN_PROGRESS', accepted_by_id=?, accepted_by_name=?, accepted_at=? WHERE id=? AND status='NEW'",
                (cid, cname, now_iso(), oid)
            )
            conn.commit()
            return cur.rowcount == 1


def close_order(oid, status):
    db_execute("UPDATE orders SET status=?, closed_at=? WHERE id=?", (status, now_iso(), oid))


def reset_order(oid):
    db_execute("UPDATE orders SET status='NEW', accepted_by_id=NULL, accepted_by_name=NULL, accepted_at=NULL, group_message_id=NULL WHERE id=?", (oid,))


def has_active_order(cid):
    return db_fetchone("SELECT * FROM orders WHERE accepted_by_id=? AND status='IN_PROGRESS'", (cid,)) is not None


def set_user_role(uid, role):
    db_execute("INSERT OR REPLACE INTO users (user_id, role, registered_at) VALUES (?, ?, ?)", (uid, role, now_iso()))


def get_user_role(uid):
    u = db_fetchone("SELECT role FROM users WHERE user_id=?", (uid,))
    return u['role'] if u else None


# ================= FSM =================
class OrderState(StatesGroup):
    waiting_name = State()
    waiting_address = State()
    waiting_confirm = State()

class StoreState(StatesGroup):
    waiting_name = State()
    waiting_type = State()
    waiting_emoji = State()

class ProductState(StatesGroup):
    waiting_name = State()
    waiting_price = State()
    waiting_desc = State()
    waiting_emoji = State()
    waiting_cat = State()


# ================= UI =================
def main_kb(uid=None):
    rows = [
        [KeyboardButton(text="📱 Menyu", web_app=WebAppInfo(url=WEBAPP_URL + "/index1.html"))]
    ]

    # Admin tugmalari
    if uid and (is_admin(uid) or db_fetchone("SELECT id FROM stores WHERE admin_id=?", (uid,))):
        rows.append([KeyboardButton(text="⚙️ Boshqaruv", web_app=WebAppInfo(url=WEBAPP_URL + "/admin.html"))])
    else:
        # Oddiy foydalanuvchilar uchun kuryerlik
        if uid:
            role = get_user_role(uid)
            if role == 'courier':
                rows.append([KeyboardButton(text="🚗 Kuryer panel")])
                rows.append([KeyboardButton(text="🔴 Kuryerlikdan chiqish")])
            else:
                rows.append([KeyboardButton(text="🚗 Kuryer bo'lish")])

    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def location_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Lokatsiya yuborish", request_location=True)],
            [KeyboardButton(text="✍️ Matn bilan yozish")],
            [KeyboardButton(text="❌ Bekor qilish")],
        ],
        resize_keyboard=True, one_time_keyboard=True
    )


def group_accept_kb(oid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="☑️ Qabul qildim", callback_data=f"accept:{oid}")]
    ])


def courier_kb(oid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Yetkazildi", callback_data=f"done:{oid}"),
         InlineKeyboardButton(text="❌ Bekor", callback_data=f"cancel:{oid}")]
    ])


def fmt_order(order):
    oid = order['id']
    s = (order.get('status') or 'NEW').upper()
    phone = order.get('phone', '-')
    items = order.get('items', '')

    em = {"NEW": ("🆕", "YANGI"), "IN_PROGRESS": ("🚚", "YETKAZILMOQDA"),
          "DELIVERED": ("✅", "YETKAZILDI"), "CANCELLED": ("❌", "BEKOR")}
    e, st = em.get(s, ("ℹ️", s))
    c = order.get("accepted_by_name") or "-"

    txt = f"{e} Buyurtma #{oid}\n\n"
    if items: txt += f"🛒 {items}\n💰 Jami: {order.get('total', 0):,} so'm\n\n"
    txt += f"👤 Ism: {order.get('full_name', '-')}\n"
    txt += f"📞 Telefon: <a href='tel:{phone}'>{phone}</a>\n"
    txt += f"📍 Manzil: {order.get('address', '-')}\n\n"
    txt += f"Status: {st}" + (f" ({c})" if s == 'IN_PROGRESS' else '')
    return txt


router = Router()

# ================= KURYER =================
@router.message(Command("kuryer"))
async def become_courier_cmd(msg: Message):
    if not msg.from_user: return
    if is_admin(msg.from_user.id):
        await msg.answer("❌ Adminlar kuryer bo'la olmaydi!"); return
    set_user_role(msg.from_user.id, 'courier')
    await msg.answer("✅ Kuryersiz!", reply_markup=main_kb(msg.from_user.id))


@router.message(Command("user"))
async def become_user_cmd(msg: Message):
    if not msg.from_user: return
    if has_active_order(msg.from_user.id):
        await msg.answer("❌ Avval buyurtmani yakunlang!"); return
    set_user_role(msg.from_user.id, 'user')
    await msg.answer("✅ Oddiy foydalanuvchi.", reply_markup=main_kb(msg.from_user.id))


# SHU YERGA QO'SHING:
@router.message(F.text == "🚗 Kuryer bo'lish")
async def become_courier(msg: Message):
    if not msg.from_user: return
    if is_admin(msg.from_user.id):
        await msg.answer("❌ Adminlar kuryer bo'la olmaydi!"); return
    set_user_role(msg.from_user.id, 'courier')
    await msg.answer("✅ Kuryersiz!", reply_markup=main_kb(msg.from_user.id))


@router.message(F.text == "🔴 Kuryerlikdan chiqish")
async def leave_courier(msg: Message):
    if not msg.from_user: return
    if has_active_order(msg.from_user.id):
        await msg.answer("❌ Avval aktiv buyurtmani yakunlang!"); return
    set_user_role(msg.from_user.id, 'user')
    await msg.answer("🔴 Kuryerlikdan chiqdingiz.", reply_markup=main_kb(msg.from_user.id))


# ================= ORDER FLOW =================
# ================= WEB APP =================
@router.message(F.web_app_data)
async def webapp_handler(msg: Message, state: FSMContext):
    if not msg.from_user: return
    try:
        data = json.loads(msg.web_app_data.data)
    except Exception:
        return

    action = data.get("action")

    # Onboarding tugadi — foydalanuvchini ro'yxatdan o'tkazamiz
    if action == "registered":
        uid = msg.from_user.id
        db_execute(
            """INSERT INTO users (user_id, role, registered_at, first_name, onboarded)
               VALUES (?, 'user', ?, ?, 1)
               ON CONFLICT(user_id) DO UPDATE SET onboarded=1""",
            (uid, now_iso(), msg.from_user.first_name or '')
        )
        name = msg.from_user.first_name or "do'st"
        await msg.answer(
            f"✅ <b>Xush kelibsiz, {name}!</b>\n\n"
            f"Profil muvaffaqiyatli yaratildi. Endi buyurtma berishingiz mumkin! 🍔",
            reply_markup=main_kb(uid),
            parse_mode="HTML"
        )
        return

    # Oddiy buyurtma
    items = data.get("items", "")
    total = data.get("total", 0)
    store_id = data.get("store_id")

    await state.update_data(webapp_items=items, webapp_total=total, store_id=store_id)
    await state.set_state(OrderState.waiting_name)
    await msg.answer(
        f"📱 {items}\n💰 Jami: {total:,} so'm\n\n👤 Ismingizni yuboring:",
        reply_markup=ReplyKeyboardRemove()
    )


# ================= START =================
@router.message(CommandStart())
async def start(msg: Message, state: FSMContext):
    await state.clear()
    if not msg.from_user:
        await msg.answer("🍔 Fast Food", reply_markup=main_kb())
        return

    uid = msg.from_user.id
    user = db_fetchone("SELECT * FROM users WHERE user_id=?", (uid,))

    # Check for referral code in /start payload: /start ref<user_id>
    referrer_id = None
    try:
        parts = (msg.text or '').split(maxsplit=1)
        if len(parts) > 1 and parts[1].startswith('ref'):
            ref_uid = int(parts[1][3:])
            if ref_uid and ref_uid != uid:
                referrer_id = ref_uid
    except (ValueError, IndexError):
        pass

    # Record referral if new user
    if referrer_id and (not user or not user.get('onboarded')):
        try:
            existing_ref = db_fetchone("SELECT id FROM referrals WHERE referred_id=?", (uid,))
            if not existing_ref:
                db_execute(
                    "INSERT INTO referrals (referrer_id, referred_id, bonus_amount, status, created_at) VALUES (?, ?, 10000, 'pending', ?)",
                    (referrer_id, uid, now_iso())
                )
                logger.info(f"Referral recorded: {referrer_id} → {uid}")
        except Exception as e:
            logger.warning(f"Referral insert failed: {e}")

    if not user or not user.get('onboarded'):
        # Yangi foydalanuvchi — onboarding yuborish
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="🚀 Boshlash",
                web_app=WebAppInfo(url=WEBAPP_URL + "/onboarding.html")
            )
        ]])
        name = msg.from_user.first_name or "do'st"
        await msg.answer(
            f"👋 Salom, <b>{name}</b>!\n\n"
            f"🍔 <b>FoodBot</b> ga xush kelibsiz!\n\n"
            f"Telegram orqali ovqat buyurtma qiling, restoran oching, yetkazib berish — barchasi bir joyda.\n\n"
            f"⬇️ Boshlash uchun tugmani bosing:",
            reply_markup=kb,
            parse_mode="HTML"
        )
    else:
        # Qaytib kelgan foydalanuvchi
        await msg.answer(
            f"👋 Xush kelibsiz, <b>{msg.from_user.first_name}</b>!",
            reply_markup=main_kb(uid),
            parse_mode="HTML"
        )


@router.message(F.text == "❌ Bekor qilish")
async def cancel_anywhere(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("❌ Bekor qilindi", reply_markup=main_kb(msg.from_user.id if msg.from_user else None))


# ================= KURYER =================
@router.message(F.text == "🚗 Kuryer panel")
async def courier_panel(msg: Message):
    if not msg.from_user or get_user_role(msg.from_user.id) != 'courier':
        await msg.answer("Siz kuryer emassiz. /kuryer yozing."); return
    o = db_fetchone("SELECT * FROM orders WHERE accepted_by_id=? AND status='IN_PROGRESS'", (msg.from_user.id,))
    if o:
        await msg.answer(fmt_order(o), parse_mode="HTML")
        await msg.answer("Yakunlash:", reply_markup=courier_kb(o['id']))
    else:
        await msg.answer("Aktiv buyurtma yo'q.")


@router.message(Command("kuryer"))
async def become_courier(msg: Message):
    if not msg.from_user: return
    set_user_role(msg.from_user.id, 'courier')
    await msg.answer("✅ Kuryersiz!", reply_markup=main_kb(msg.from_user.id))


@router.message(Command("user"))
async def become_user(msg: Message):
    if not msg.from_user: return
    if has_active_order(msg.from_user.id):
        await msg.answer("❌ Avval buyurtmani yakunlang!"); return
    set_user_role(msg.from_user.id, 'user')
    await msg.answer("✅ Oddiy foydalanuvchi.", reply_markup=main_kb(msg.from_user.id))


# ================= ORDER FLOW =================
@router.message(OrderState.waiting_name)
async def get_name(msg: Message, state: FSMContext):
    t = (msg.text or "").strip()
    if len(t) < 2: await msg.answer("To'g'ri kiriting"); return
    await state.update_data(full_name=t)
    await state.set_state(OrderState.waiting_address)
    await msg.answer("📍 Manzil yoki lokatsiya yuboring:", reply_markup=location_kb())


@router.message(OrderState.waiting_address, F.location)
async def get_addr_loc(msg: Message, state: FSMContext):
    lat, lon = msg.location.latitude, msg.location.longitude
    await state.update_data(address=f"https://maps.google.com/?q={lat},{lon}", lat=lat, lon=lon)
    await state.set_state(OrderState.waiting_confirm)
    d = await state.get_data()
    await msg.answer(
        f"📋 Tasdiqlaysizmi?\n\n👤 {d.get('full_name')}\n📍 Google Maps\n\n"
        f"🛒 {d.get('webapp_items','')}\n💰 Jami: {d.get('webapp_total',0):,} so'm",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="confirm_order"),
             InlineKeyboardButton(text="❌ Bekor", callback_data="cancel_new_order")]
        ])
    )


@router.message(OrderState.waiting_address)
async def get_addr_text(msg: Message, state: FSMContext):
    t = (msg.text or "").strip()
    if t == "❌ Bekor qilish": await cancel_anywhere(msg, state); return
    if t == "✍️ Matn bilan yozish":
        await msg.answer("Manzilni yozing:", reply_markup=ReplyKeyboardRemove()); return
    if len(t) < 3: await msg.answer("To'liqroq yozing"); return
    await state.update_data(address=t, lat=None, lon=None)
    await state.set_state(OrderState.waiting_confirm)
    d = await state.get_data()
    await msg.answer(
        f"📋 Tasdiqlaysizmi?\n\n👤 {d.get('full_name')}\n📍 {t}\n\n"
        f"🛒 {d.get('webapp_items','')}\n💰 Jami: {d.get('webapp_total',0):,} so'm",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="confirm_order"),
             InlineKeyboardButton(text="❌ Bekor", callback_data="cancel_new_order")]
        ])
    )


@router.callback_query(F.data == "cancel_new_order")
async def cancel_new(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer("Bekor qilindi")
    if cb.message:
        await cb.message.answer("❌ Bekor qilindi", reply_markup=main_kb(cb.from_user.id if cb.from_user else None))


@router.callback_query(F.data == "confirm_order")
async def confirm_order(cb: CallbackQuery, state: FSMContext):
    if not cb.from_user: return
    d = await state.get_data()
    fn = (d.get('full_name', '') or '').strip()
    ad = (d.get('address', '') or '').strip()
    lat, lon = d.get('lat'), d.get('lon')
    items = d.get('webapp_items', '')
    total = d.get('webapp_total', 0)
    store_id = d.get('store_id')

    if cb.from_user.username:
        ph = f"@{cb.from_user.username}"
    else:
        ph = f"ID{cb.from_user.id}"

    if not fn or not ad:
        await cb.answer("Ism va manzil to'ldirilishi shart", show_alert=True); return

    try:
        # Qaysi chatga yuborish kerakligini aniqlaymiz
        target_chat = GROUP_CHAT_ID
        if store_id:
            store = db_fetchone("SELECT admin_id FROM stores WHERE id=?", (store_id,))
            if store and store['admin_id']:
                target_chat = store['admin_id']

        oid = create_order(fn, ph, ad, lat, lon, items, total, cb.from_user.id, cb.from_user.full_name, store_id, target_chat)
        order = get_order(oid)
        txt = fmt_order(order)

        if lat and lon:
            loc_msg = await cb.bot.send_location(target_chat, lat, lon)
            sent = await cb.bot.send_message(target_chat, txt, reply_to_message_id=loc_msg.message_id,
                                             reply_markup=group_accept_kb(oid), parse_mode="HTML")
        else:
            sent = await cb.bot.send_message(target_chat, txt, reply_markup=group_accept_kb(oid), parse_mode="HTML")

        set_group_message_id(oid, sent.message_id)
        await state.clear()
        await cb.answer("✅ Yuborildi")
        if cb.message:
            await cb.message.answer(f"✅ Buyurtma #{oid} qabul qilindi!", reply_markup=main_kb(cb.from_user.id))
    except Exception as e:
        logger.exception("Xato")
        if cb.message: await cb.message.answer(f"❌ Xato: {e}")
        await state.clear()


# ================= CALLBACKS =================
@router.callback_query(F.data.startswith("accept:"))
async def accept(cb: CallbackQuery):
    if not cb.from_user: return
    oid = int(cb.data.split(":")[1])

    # Admin tekshiruvi
    if is_admin(cb.from_user.id):
        await cb.answer("❌ Siz adminsiz! Kuryerlik siz uchun cheklangan.",
                        show_alert=True)
        return

    if get_user_role(cb.from_user.id) != 'courier':
        await cb.answer("❌ Siz kuryer emassiz! '🚗 Kuryer bo'lish' tugmasini bosing.", show_alert=True)
        return

    order = get_order(oid)
    if not order: await cb.answer("Topilmadi"); return

    if order.get('created_by_id') == cb.from_user.id:
        await cb.answer("❌ O'zingizning buyurtmangizni qabul qila olmaysiz!", show_alert=True)
        return

    if has_active_order(cb.from_user.id):
        await cb.answer("❌ Sizda aktiv buyurtma bor!", show_alert=True)
        return

    ok = try_accept_order(oid, cb.from_user.id, cb.from_user.full_name)
    if not ok: await cb.answer("Qabul qilingan!"); return

    order = get_order(oid)
    await cb.answer("✅ Qabul qilindi")

    mid = order.get('group_message_id')
    chat_id = order.get('target_chat_id') or GROUP_CHAT_ID
    if mid:
        try:
            await cb.bot.edit_message_text(chat_id, int(mid), text=fmt_order(order), reply_markup=None,
                                           parse_mode="HTML")
        except:
            pass
    try:
        if order.get('lat') and order.get('lon'):
            await cb.bot.send_location(cb.from_user.id, order['lat'], order['lon'])
        await cb.bot.send_message(cb.from_user.id, fmt_order(order), reply_markup=courier_kb(oid), parse_mode="HTML")
    except:
        pass

@router.callback_query(F.data.startswith("done:"))
async def done(cb: CallbackQuery):
    if not cb.from_user: return
    oid = int(cb.data.split(":")[1])
    order = get_order(oid)
    if not order or (order.get('accepted_by_id') and int(order['accepted_by_id']) != cb.from_user.id):
        await cb.answer("Sizniki emas!"); return
    close_order(oid, "DELIVERED")
    order = get_order(oid) or order
    await cb.answer("✅ Yetkazildi")
    chat_id = order.get('target_chat_id') or GROUP_CHAT_ID
    mid = order.get('group_message_id')
    if mid:
        try: await cb.bot.edit_message_text(chat_id, int(mid), text=fmt_order(order), reply_markup=None, parse_mode="HTML")
        except: pass
    try: await cb.message.delete()
    except: pass
    try: await cb.bot.send_message(order['created_by_id'], f"✅ Yetkazildi! #{oid}")
    except: pass


@router.callback_query(F.data.startswith("cancel:"))
async def cancel(cb: CallbackQuery):
    if not cb.from_user: return
    oid = int(cb.data.split(":")[1])
    order = get_order(oid)
    if not order or (order.get('accepted_by_id') and int(order['accepted_by_id']) != cb.from_user.id):
        await cb.answer("Sizniki emas!"); return
    reset_order(oid)
    order = get_order(oid)
    chat_id = order.get('target_chat_id') or GROUP_CHAT_ID
    await cb.answer("❌ Bekor qilindi")
    try:
        txt = fmt_order(order)
        if order.get('lat') and order.get('lon'):
            loc_msg = await cb.bot.send_location(chat_id, order['lat'], order['lon'])
            sent = await cb.bot.send_message(chat_id, txt, reply_to_message_id=loc_msg.message_id,
                                             reply_markup=group_accept_kb(oid), parse_mode="HTML")
        else:
            sent = await cb.bot.send_message(chat_id, txt, reply_markup=group_accept_kb(oid), parse_mode="HTML")
        set_group_message_id(oid, sent.message_id)
    except: pass
    try: await cb.message.delete()
    except: pass


# ================= ADMIN FSM =================
@router.message(Command("mystore"))
async def create_store_cmd(msg: Message, state: FSMContext):
    if not msg.from_user: return
    store = db_fetchone("SELECT * FROM stores WHERE admin_id=?", (msg.from_user.id,))
    if store:
        await msg.answer(f"Sizning do'koningiz: {store['name']}\nMahsulot qo'shish uchun /addproduct yozing.")
        return
    await state.set_state(StoreState.waiting_name)
    await msg.answer("🏪 Do'kon nomini kiriting:")

@router.message(StoreState.waiting_name)
async def store_name(msg: Message, state: FSMContext):
    await state.update_data(s_name=msg.text)
    await state.set_state(StoreState.waiting_type)
    await msg.answer("Do'kon turi (Masalan: Fast Food, Milliy, Pitsa):")

@router.message(StoreState.waiting_type)
async def store_type(msg: Message, state: FSMContext):
    await state.update_data(s_type=msg.text)
    await state.set_state(StoreState.waiting_emoji)
    await msg.answer("Do'kon uchun bitta emoji yuboring (Masalan: 🍔):")

@router.message(StoreState.waiting_emoji)
async def store_emoji(msg: Message, state: FSMContext):
    d = await state.get_data()
    bg = "linear-gradient(135deg, #FF9A9E, #FECFEF)"
    db_execute(
        "INSERT INTO stores (admin_id, name, type, emoji, bg_color) VALUES (?, ?, ?, ?, ?)",
        (msg.from_user.id, d['s_name'], d['s_type'], msg.text, bg)
    )
    await state.clear()
    await msg.answer("✅ Do'koningiz muvaffaqiyatli ochildi!\nMahsulot qo'shish uchun /addproduct buyrug'idan foydalaning.")

@router.message(Command("addproduct"))
async def add_product_cmd(msg: Message, state: FSMContext):
    if not msg.from_user: return
    store = db_fetchone("SELECT * FROM stores WHERE admin_id=?", (msg.from_user.id,))
    if not store:
        await msg.answer("❌ Avval /mystore orqali do'kon oching!")
        return
    await state.update_data(store_id=store['id'])
    await state.set_state(ProductState.waiting_name)
    await msg.answer("🍔 Mahsulot nomini kiriting:")

@router.message(ProductState.waiting_name)
async def prod_name(msg: Message, state: FSMContext):
    await state.update_data(p_name=msg.text)
    await state.set_state(ProductState.waiting_price)
    await msg.answer("💰 Narxini raqamda kiriting (Masalan: 25000):")

@router.message(ProductState.waiting_price)
async def prod_price(msg: Message, state: FSMContext):
    if not msg.text.isdigit():
        await msg.answer("❌ Faqat raqam kiriting!")
        return
    await state.update_data(p_price=int(msg.text))
    await state.set_state(ProductState.waiting_desc)
    await msg.answer("📝 Mahsulot tarkibi/ta'rifini yozing:")

@router.message(ProductState.waiting_desc)
async def prod_desc(msg: Message, state: FSMContext):
    await state.update_data(p_desc=msg.text)
    await state.set_state(ProductState.waiting_emoji)
    await msg.answer("🍔 Mahsulot emojisini yuboring:")

@router.message(ProductState.waiting_emoji)
async def prod_emoji(msg: Message, state: FSMContext):
    await state.update_data(p_emoji=msg.text)
    await state.set_state(ProductState.waiting_cat)
    await msg.answer("Kategoriya kiriting (Masalan: Burger, Lavash, Ichimlik):")

@router.message(ProductState.waiting_cat)
async def prod_cat(msg: Message, state: FSMContext):
    d = await state.get_data()
    db_execute(
        "INSERT INTO products (store_id, name, price, desc, emoji, cat) VALUES (?, ?, ?, ?, ?, ?)",
        (d['store_id'], d['p_name'], d['p_price'], d['p_desc'], d['p_emoji'], msg.text)
    )
    await state.clear()
    await msg.answer("✅ Mahsulot do'koningizga qo'shildi!")


# ================= AIOHTTP & MAIN =================
async def handle_index(request):
    return web.FileResponse('webapp/index1.html')

async def handle_admin(request):
    return web.FileResponse('webapp/admin.html')

async def handle_api_data(request):
    # Optional region filter — users see only stores in their region
    region = (request.query.get("region") or '').strip()
    city   = (request.query.get("city")   or '').strip()

    stores_db = db_fetchall("SELECT * FROM stores")
    products_db = db_fetchall("SELECT * FROM products")

    stores = []
    for s in stores_db:
        s_region   = s.get('region')   or ''
        s_city     = s.get('city')     or ''
        s_district = s.get('district') or ''
        # Apply region filter if user provided one
        if region and s_region and s_region.lower() != region.lower():
            continue
        if city and s_city and s_city.lower() != city.lower():
            continue
        stores.append({
            "id": s['id'],
            "name": s['name'] or '',
            "emoji": s['emoji'] or '🍔',
            "time": str(s['eta'] or 25),
            "rating": "5.0",
            "type": s['type'] or '',
            "bg": s['bg_color'] or "linear-gradient(135deg, #a18cd1, #fbc2eb)",
            "delivery_fee": s['delivery_fee'] or 15000,
            "min_order": s['min_order'] or 50000,
            "region": s_region,
            "city": s_city,
            "district": s_district,
            "address": s.get('address') or '',
            "phone": s.get('phone') or '',
            "description": s.get('description') or '',
            "hours_weekday": s.get('hours_weekday') or '09:00-22:00',
            "hours_weekend": s.get('hours_weekend') or '10:00-23:00',
            "is_open": s.get('is_open', 1),
            "lat": s.get('lat'),
            "lon": s.get('lon'),
        })
    visible_store_ids = {s['id'] for s in stores}

    menuItems = {}
    for p in products_db:
        sid = p['store_id']
        # only include products for visible stores
        if sid not in visible_store_ids:
            continue
        if sid not in menuItems: menuItems[sid] = []
        menuItems[sid].append({
            "id": p['id'],
            "name": p['name'] or '',
            "price": p['price'] or 0,
            "desc": p.get('desc') or '',
            "emoji": p['emoji'] or '🍽️',
            "cat": p['cat'] or '',
            "store_id": p['store_id'],
            "old_price": p['old_price'],
            "discount_qty": p['discount_qty'],
            "discount_end": p['discount_end'],
            "photo_url": p.get('photo_url') or '',
            "is_featured": p.get('is_featured') or 0,
        })

    return web.json_response({"stores": stores, "menuItems": menuItems})

async def handle_admin_data(request):
    admin_id = request.query.get("admin_id")
    if not admin_id or admin_id == '0':
        return web.json_response({"error": "admin_id required"}, status=400)
    try:
        admin_id_int = int(admin_id)
    except ValueError:
        return web.json_response({"error": "invalid admin_id"}, status=400)

    store = db_fetchone("SELECT * FROM stores WHERE admin_id=?", (admin_id_int,))
    products = []
    if store:
        products = db_fetchall("SELECT * FROM products WHERE store_id=?", (store['id'],))

    return web.json_response({"store": store, "products": products})

async def handle_update_store(request):
    try:
        data = await request.json()
    except Exception as e:
        logger.error(f"handle_update_store: bad JSON: {e}")
        return web.json_response({"error": "Invalid JSON"}, status=400)

    try:
        admin_id = data.get('admin_id')
        if not admin_id or int(admin_id) == 0:
            return web.json_response({"error": "admin_id required"}, status=400)
        admin_id = int(admin_id)

        name          = (data.get('name') or '').strip()
        type_         = (data.get('type') or '').strip()
        emoji         = (data.get('emoji') or '🍔').strip() or '🍔'
        delivery_fee  = int(data.get('delivery_fee') or 15000)
        eta           = int(data.get('eta') or 25)
        radius        = float(data.get('radius') or 5)
        min_order     = int(data.get('min_order') or 50000)
        hours_weekday = str(data.get('hours_weekday') or '09:00-22:00')
        hours_weekend = str(data.get('hours_weekend') or '10:00-23:00')
        region        = (data.get('region') or '').strip()
        city          = (data.get('city') or '').strip()
        district      = (data.get('district') or '').strip()
        address       = (data.get('address') or '').strip()
        phone         = (data.get('phone') or '').strip()
        description   = (data.get('description') or '').strip()
        lat = data.get('lat')
        lon = data.get('lon')
        try: lat = float(lat) if lat is not None else None
        except: lat = None
        try: lon = float(lon) if lon is not None else None
        except: lon = None
        bg            = "linear-gradient(135deg, #FF9A9E, #FECFEF)"

        store = db_fetchone("SELECT * FROM stores WHERE admin_id=?", (admin_id,))
        if store:
            db_execute(
                "UPDATE stores SET name=?, type=?, emoji=?, delivery_fee=?, eta=?, radius=?, min_order=?, hours_weekday=?, hours_weekend=?, region=?, city=?, district=?, address=?, phone=?, description=?, lat=?, lon=? WHERE admin_id=?",
                (name, type_, emoji, delivery_fee, eta, radius, min_order, hours_weekday, hours_weekend, region, city, district, address, phone, description, lat, lon, admin_id)
            )
            logger.info(f"Store updated: admin_id={admin_id} name={name}")
        else:
            db_execute(
                "INSERT INTO stores (admin_id, name, type, emoji, bg_color, delivery_fee, eta, radius, min_order, hours_weekday, hours_weekend, region, city, district, address, phone, description, lat, lon) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (admin_id, name, type_, emoji, bg, delivery_fee, eta, radius, min_order, hours_weekday, hours_weekend, region, city, district, address, phone, description, lat, lon)
            )
            logger.info(f"Store created: admin_id={admin_id} name={name}")

        return web.json_response({"status": "ok", "name": name})

    except Exception as e:
        logger.exception(f"handle_update_store error: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def handle_update_product(request):
    try:
        data = await request.json()
        admin_id = data.get('admin_id')
        if not admin_id:
            return web.json_response({"error": "admin_id required"}, status=400)
        admin_id = int(admin_id)
        store = db_fetchone("SELECT * FROM stores WHERE admin_id=?", (admin_id,))
        if not store:
            return web.json_response({"error": "Do'kon topilmadi. Avval do'kon yarating."}, status=400)

        p_id       = data.get('id')
        name       = (data.get('name') or '').strip()
        price      = int(data.get('price') or 0)
        desc       = (data.get('desc') or data.get('description') or '').strip()
        emoji      = (data.get('emoji') or '🍽️').strip()
        cat        = (data.get('cat') or '').strip()
        old_price  = data.get('old_price') or None
        disc_qty   = data.get('discount_qty') or None
        disc_end   = data.get('discount_end') or None
        photo_url  = (data.get('photo_url') or '').strip() or None
        is_feat    = 1 if data.get('is_featured') else 0

        if not name:
            return web.json_response({"error": "Mahsulot nomi majburiy"}, status=400)

        if p_id:
            db_execute(
                "UPDATE products SET name=?, price=?, desc=?, emoji=?, cat=?, old_price=?, discount_qty=?, discount_end=?, photo_url=?, is_featured=? WHERE id=? AND store_id=?",
                (name, price, desc, emoji, cat, old_price, disc_qty, disc_end, photo_url, is_feat, int(p_id), store['id'])
            )
        else:
            db_execute(
                "INSERT INTO products (store_id, name, price, desc, emoji, cat, old_price, discount_qty, discount_end, photo_url, is_featured) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (store['id'], name, price, desc, emoji, cat, old_price, disc_qty, disc_end, photo_url, is_feat)
            )
        logger.info(f"Product saved: store={store['id']} name={name}")
        return web.json_response({"status": "ok"})
    except Exception as e:
        logger.exception(f"handle_update_product error: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def handle_delete_product(request):
    data = await request.json()
    admin_id = data.get('admin_id')
    p_id = data.get('id')
    store = db_fetchone("SELECT * FROM stores WHERE admin_id=?", (admin_id,))
    if store and p_id:
        db_execute("DELETE FROM products WHERE id=? AND store_id=?", (p_id, store['id']))
    return web.json_response({"status": "ok"})


async def handle_user_region(request):
    """Save user's region preference."""
    try:
        data = await request.json()
        uid = data.get('user_id')
        region = (data.get('region') or '').strip()
        if not uid:
            return web.json_response({"error": "user_id required"}, status=400)
        uid = int(uid)
        db_execute("UPDATE users SET region=? WHERE user_id=?", (region, uid))
        return web.json_response({"status": "ok", "region": region})
    except Exception as e:
        logger.exception(f"handle_user_region: {e}")
        return web.json_response({"error": str(e)}, status=500)


# ─── PROMO CODES ──────────────────────────────────────────────────────────────
async def handle_create_promo(request):
    """Admin creates a promo code."""
    try:
        data = await request.json()
        admin_id = int(data.get('admin_id') or 0)
        if not admin_id:
            return web.json_response({"error": "admin_id required"}, status=400)
        store = db_fetchone("SELECT id FROM stores WHERE admin_id=?", (admin_id,))
        if not store:
            return web.json_response({"error": "Avval do'kon yarating"}, status=400)

        code = (data.get('code') or '').strip().upper()
        if not code or len(code) < 3:
            return web.json_response({"error": "Promo kod 3+ harfdan iborat bo'lsin"}, status=400)

        discount_pct    = int(data.get('discount_pct') or 0)
        discount_amount = int(data.get('discount_amount') or 0)
        min_order       = int(data.get('min_order') or 0)
        max_uses        = int(data.get('max_uses') or 0)
        expires_at      = (data.get('expires_at') or '').strip() or None

        # Check uniqueness
        existing = db_fetchone("SELECT id FROM promo_codes WHERE code=?", (code,))
        if existing:
            return web.json_response({"error": "Bu kod allaqachon mavjud"}, status=400)

        db_execute(
            "INSERT INTO promo_codes (code, store_id, discount_pct, discount_amount, min_order, max_uses, used_count, expires_at, active, created_at, created_by) VALUES (?, ?, ?, ?, ?, ?, 0, ?, 1, ?, ?)",
            (code, store['id'], discount_pct, discount_amount, min_order, max_uses, expires_at, now_iso(), admin_id)
        )
        logger.info(f"Promo created: {code} by admin {admin_id}")
        return web.json_response({"status": "ok", "code": code})
    except Exception as e:
        logger.exception(f"create_promo: {e}")
        return web.json_response({"error": str(e)}, status=500)


async def handle_list_promos(request):
    """List promos for an admin's store."""
    admin_id = request.query.get("admin_id")
    if not admin_id:
        return web.json_response({"promos": []})
    try:
        admin_id = int(admin_id)
    except ValueError:
        return web.json_response({"promos": []})
    store = db_fetchone("SELECT id FROM stores WHERE admin_id=?", (admin_id,))
    if not store:
        return web.json_response({"promos": []})
    promos = db_fetchall(
        "SELECT * FROM promo_codes WHERE store_id=? ORDER BY created_at DESC",
        (store['id'],)
    )
    return web.json_response({"promos": promos})


async def handle_delete_promo(request):
    try:
        data = await request.json()
        admin_id = int(data.get('admin_id') or 0)
        promo_id = int(data.get('id') or 0)
        store = db_fetchone("SELECT id FROM stores WHERE admin_id=?", (admin_id,))
        if not store:
            return web.json_response({"error": "Store not found"}, status=400)
        db_execute("DELETE FROM promo_codes WHERE id=? AND store_id=?", (promo_id, store['id']))
        return web.json_response({"status": "ok"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_validate_promo(request):
    """User validates a promo code at checkout."""
    try:
        data = await request.json()
        code = (data.get('code') or '').strip().upper()
        store_id = data.get('store_id')
        user_id = data.get('user_id')
        order_total = int(data.get('order_total') or 0)

        if not code:
            return web.json_response({"valid": False, "error": "Kod kiriting"}, status=400)

        promo = db_fetchone("SELECT * FROM promo_codes WHERE code=? AND active=1", (code,))
        if not promo:
            return web.json_response({"valid": False, "error": "Bunday promo kod yo'q"})

        # Store match (None store_id = global, applies to all)
        if promo['store_id'] and store_id and int(promo['store_id']) != int(store_id):
            return web.json_response({"valid": False, "error": "Bu promo boshqa do'kon uchun"})

        # Expires
        if promo['expires_at']:
            try:
                exp = datetime.fromisoformat(promo['expires_at'].replace('Z', '+00:00'))
                if datetime.now(timezone.utc) > exp:
                    return web.json_response({"valid": False, "error": "Promo muddati tugagan"})
            except Exception:
                pass

        # Max uses
        if promo['max_uses'] and (promo['used_count'] or 0) >= promo['max_uses']:
            return web.json_response({"valid": False, "error": "Promo limiti tugagan"})

        # Min order
        if promo['min_order'] and order_total < promo['min_order']:
            return web.json_response({
                "valid": False,
                "error": f"Minimal buyurtma {promo['min_order']:,} so'm"
            })

        # Per-user limit (only once per user)
        if user_id:
            try:
                used = db_fetchone(
                    "SELECT id FROM promo_uses WHERE promo_id=? AND user_id=?",
                    (promo['id'], int(user_id))
                )
                if used:
                    return web.json_response({"valid": False, "error": "Siz bu kodni ishlatib bo'lgansiz"})
            except Exception:
                pass

        # Calculate discount
        pct = promo['discount_pct'] or 0
        amt = promo['discount_amount'] or 0
        discount = max(int(order_total * pct / 100), amt)

        return web.json_response({
            "valid": True,
            "promo_id": promo['id'],
            "code": promo['code'],
            "discount": discount,
            "discount_pct": pct,
            "discount_amount": amt,
        })
    except Exception as e:
        logger.exception(f"validate_promo: {e}")
        return web.json_response({"valid": False, "error": str(e)}, status=500)


# ─── REFERRAL ─────────────────────────────────────────────────────────────────
async def handle_referral_link(request):
    """Get user's referral code/stats."""
    uid = request.query.get("user_id")
    if not uid:
        return web.json_response({"error": "user_id required"}, status=400)
    try:
        uid = int(uid)
    except ValueError:
        return web.json_response({"error": "bad user_id"}, status=400)

    invited = db_fetchall("SELECT * FROM referrals WHERE referrer_id=?", (uid,))
    user = db_fetchone("SELECT bonus_balance FROM users WHERE user_id=?", (uid,))
    return web.json_response({
        "user_id": uid,
        "invited_count": len(invited),
        "bonus_balance": (user or {}).get('bonus_balance', 0),
        "share_url": f"https://t.me/share/url?url=https://t.me/{os.getenv('BOT_USERNAME', 'zakaz_manager_uz_bot')}?start=ref{uid}"
    })


async def handle_orders(request):
    """Buyurtmalar ro'yxati — admin paneli uchun."""
    admin_id = request.query.get("admin_id")
    if not admin_id or admin_id == '0':
        return web.json_response({"error": "admin_id required"}, status=400)
    try:
        admin_id_int = int(admin_id)
    except ValueError:
        return web.json_response({"error": "invalid admin_id"}, status=400)

    store = db_fetchone("SELECT * FROM stores WHERE admin_id=?", (admin_id_int,))
    if store:
        orders = db_fetchall(
            "SELECT * FROM orders WHERE store_id=? ORDER BY created_at DESC LIMIT 100",
            (store['id'],)
        )
    elif admin_id_int in ADMIN_IDS:
        orders = db_fetchall("SELECT * FROM orders ORDER BY created_at DESC LIMIT 100")
    else:
        orders = []

    return web.json_response({"orders": orders})


STATUS_MESSAGES = {
    'IN_PROGRESS': "🔧 <b>Buyurtmangiz #{oid} qabul qilindi!</b>\n\nRestoran tayyorlamoqda. Tez orada tayyor bo'ladi.",
    'READY':       "✅ <b>Buyurtma #{oid} tayyor!</b>\n\nKuryer yetkazib berishga chiqyapti.",
    'IN_DELIVERY': "🚗 <b>Buyurtma #{oid} yo'lda!</b>\n\nTez orada sizga yetkazib beriladi. 📍",
    'DELIVERED':   "🎉 <b>Buyurtma #{oid} yetkazib berildi!</b>\n\nBahomi bering. Yaxshi ovqatlanishingizni tilaymiz!",
    'CANCELLED':   "❌ <b>Buyurtma #{oid} bekor qilindi.</b>\n\nSavollar bo'lsa qo'llab-quvvatlash bilan bog'laning.",
}


async def handle_order_status(request):
    data = await request.json()
    order_id = data.get('order_id')
    status = data.get('status')
    allowed = {'NEW', 'IN_PROGRESS', 'READY', 'IN_DELIVERY', 'DELIVERED', 'CANCELLED'}
    if status not in allowed:
        return web.json_response({"error": "invalid status"}, status=400)
    if status == 'DELIVERED':
        db_execute("UPDATE orders SET status=?, closed_at=? WHERE id=?", (status, now_iso(), order_id))
    else:
        db_execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))

    # ── Notify user via bot ──
    try:
        order = db_fetchone("SELECT created_by_id FROM orders WHERE id=?", (order_id,))
        if order and order.get('created_by_id') and status in STATUS_MESSAGES:
            msg = STATUS_MESSAGES[status].format(oid=order_id)
            await bot.send_message(int(order['created_by_id']), msg, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"order status notify failed: {e}")

    return web.json_response({"status": "ok"})


# ─── REGISTER ───
async def handle_register(request):
    data = await request.json()
    uid = data.get('user_id')
    if not uid:
        return web.json_response({"error": "user_id required"}, status=400)
    db_execute(
        """INSERT INTO users (user_id, role, registered_at, first_name, last_name, username, language_code, photo_url, onboarded)
           VALUES (?, 'user', ?, ?, ?, ?, ?, ?, 1)
           ON CONFLICT(user_id) DO UPDATE SET
             first_name=excluded.first_name,
             last_name=excluded.last_name,
             username=excluded.username,
             language_code=excluded.language_code,
             photo_url=excluded.photo_url,
             onboarded=1""",
        (uid, now_iso(),
         data.get('first_name', ''), data.get('last_name', ''),
         data.get('username', ''), data.get('language_code', 'uz'),
         data.get('photo_url', ''))
    )
    return web.json_response({"status": "ok"})


# ─── BRANDING ───
async def handle_branding(request):
    store_id = request.query.get("store_id")
    admin_id = request.query.get("admin_id")
    if store_id:
        store = db_fetchone("SELECT * FROM stores WHERE id=?", (store_id,))
    elif admin_id:
        store = db_fetchone("SELECT * FROM stores WHERE admin_id=?", (admin_id,))
    else:
        return web.json_response({"error": "store_id or admin_id required"}, status=400)
    if not store:
        return web.json_response({"accent_color": "#FF6B35", "cover_url": None, "description": None, "phone": None, "address": None})
    return web.json_response({
        "accent_color": store.get("accent_color") or "#FF6B35",
        "cover_url": store.get("cover_url"),
        "description": store.get("description"),
        "phone": store.get("phone"),
        "address": store.get("address"),
    })


async def handle_update_branding(request):
    data = await request.json()
    admin_id = data.get("admin_id")
    if not admin_id:
        return web.json_response({"error": "admin_id required"}, status=400)
    fields = {k: data[k] for k in ("accent_color", "cover_url", "description", "phone", "address") if k in data}
    if not fields:
        return web.json_response({"status": "ok"})
    set_clause = ", ".join(f"{k}=?" for k in fields)
    db_execute(f"UPDATE stores SET {set_clause} WHERE admin_id=?", (*fields.values(), admin_id))
    return web.json_response({"status": "ok"})


# ─── ORDER TRACKING ───
async def handle_order_track(request):
    order_id = request.query.get("order_id")
    user_id = request.query.get("user_id")
    if not order_id:
        return web.json_response({"error": "order_id required"}, status=400)
    order = db_fetchone("SELECT * FROM orders WHERE id=?", (order_id,))
    if not order:
        return web.json_response({"error": "not found"}, status=404)
    # Only allow the order creator or admins to track
    if user_id and int(user_id) != order.get("created_by_id", 0) and int(user_id) not in ADMIN_IDS:
        return web.json_response({"error": "forbidden"}, status=403)
    status = order.get("status", "NEW")
    steps = ["NEW", "IN_PROGRESS", "READY", "IN_DELIVERY", "DELIVERED"]
    step_idx = steps.index(status) if status in steps else 0
    return web.json_response({
        "order_id": order["id"],
        "status": status,
        "step": step_idx,
        "total_steps": len(steps),
        "created_at": order.get("created_at"),
        "accepted_at": order.get("accepted_at"),
        "closed_at": order.get("closed_at"),
        "courier": order.get("accepted_by_name"),
    })


# ─── RATINGS ───
async def handle_submit_rating(request):
    data = await request.json()
    order_id = data.get("order_id")
    user_id = data.get("user_id")
    stars = data.get("stars")
    comment = data.get("comment", "")
    if not all([order_id, user_id, stars]):
        return web.json_response({"error": "order_id, user_id, stars required"}, status=400)
    if not (1 <= int(stars) <= 5):
        return web.json_response({"error": "stars must be 1-5"}, status=400)
    order = db_fetchone("SELECT * FROM orders WHERE id=?", (order_id,))
    if not order:
        return web.json_response({"error": "order not found"}, status=404)
    try:
        db_execute(
            "INSERT INTO ratings (order_id, user_id, store_id, stars, comment, created_at) VALUES (?,?,?,?,?,?)",
            (order_id, user_id, order.get("store_id"), stars, comment, now_iso())
        )
    except sqlite3.IntegrityError:
        db_execute(
            "UPDATE ratings SET stars=?, comment=?, created_at=? WHERE order_id=?",
            (stars, comment, now_iso(), order_id)
        )
    return web.json_response({"status": "ok"})


async def handle_ratings(request):
    store_id = request.query.get("store_id")
    admin_id = request.query.get("admin_id")
    if admin_id:
        store = db_fetchone("SELECT id FROM stores WHERE admin_id=?", (admin_id,))
        store_id = store["id"] if store else None
    if not store_id:
        return web.json_response({"ratings": [], "avg": 0})
    rows = db_fetchall("SELECT * FROM ratings WHERE store_id=? ORDER BY created_at DESC LIMIT 50", (store_id,))
    avg = sum(r["stars"] for r in rows) / len(rows) if rows else 0
    return web.json_response({"ratings": rows, "avg": round(avg, 1), "count": len(rows)})


# ─── SUBSCRIPTION ───
def _get_or_create_subscription(store_id, admin_id):
    sub = db_fetchone("SELECT * FROM subscriptions WHERE store_id=?", (store_id,))
    if not sub:
        month = date.today().strftime("%Y-%m")
        db_execute(
            "INSERT INTO subscriptions (store_id, admin_id, plan, orders_this_month, billing_month, created_at) VALUES (?,?,?,?,?,?)",
            (store_id, admin_id, "free", 0, month, now_iso())
        )
        sub = db_fetchone("SELECT * FROM subscriptions WHERE store_id=?", (store_id,))
    # Reset monthly counter if new month
    current_month = date.today().strftime("%Y-%m")
    if sub and sub.get("billing_month") != current_month:
        db_execute("UPDATE subscriptions SET orders_this_month=0, billing_month=? WHERE store_id=?", (current_month, store_id))
        sub["orders_this_month"] = 0
        sub["billing_month"] = current_month
    return sub


async def handle_subscription(request):
    admin_id = request.query.get("admin_id")
    if not admin_id:
        return web.json_response({"error": "admin_id required"}, status=400)
    store = db_fetchone("SELECT * FROM stores WHERE admin_id=?", (admin_id,))
    if not store:
        return web.json_response({"plan": "free", "orders_this_month": 0, "limit": 50, "next_billing": None})
    sub = _get_or_create_subscription(store["id"], int(admin_id))
    limits = {"free": 50, "pro": 999999, "business": 999999}
    plan = sub.get("plan", "free")
    return web.json_response({
        "plan": plan,
        "orders_this_month": sub.get("orders_this_month", 0),
        "limit": limits.get(plan, 50),
        "next_billing": sub.get("next_billing"),
    })


async def handle_upgrade_subscription(request):
    data = await request.json()
    admin_id = data.get("admin_id")
    plan = data.get("plan")
    if plan not in ("free", "pro", "business"):
        return web.json_response({"error": "invalid plan"}, status=400)
    store = db_fetchone("SELECT id FROM stores WHERE admin_id=?", (admin_id,))
    if not store:
        return web.json_response({"error": "store not found"}, status=404)
    next_bill = (date.today() + timedelta(days=30)).isoformat()
    db_execute(
        "UPDATE subscriptions SET plan=?, next_billing=? WHERE store_id=?",
        (plan, next_bill, store["id"])
    )
    return web.json_response({"status": "ok", "plan": plan})


# ─── PAYME WEBHOOK ───
_PAYME_STATE_CREATED = 1
_PAYME_STATE_DONE = 2
_PAYME_STATE_CANCELLED = -1
_PAYME_STATE_CANCELLED_AFTER_DONE = -2


def _payme_error(code, msg, data=None):
    return web.json_response({"error": {"code": code, "message": {"uz": msg, "ru": msg, "en": msg}, "data": data}})


async def handle_payme(request):
    auth = request.headers.get("Authorization", "")
    if PAYME_KEY and auth != f"Basic {PAYME_KEY}":
        return web.json_response({"error": {"code": -32504, "message": {"uz": "Ruxsat yo'q"}}})
    body = await request.json()
    method = body.get("method")
    params = body.get("params", {})
    rid = body.get("id", 1)

    def ok(result):
        return web.json_response({"id": rid, "result": result})

    if method == "CheckPerformTransaction":
        order_id = params.get("account", {}).get("order_id")
        order = db_fetchone("SELECT * FROM orders WHERE id=?", (order_id,)) if order_id else None
        if not order:
            return _payme_error(-31050, "Buyurtma topilmadi", "order_id")
        amount = params.get("amount", 0)
        if amount != order["total"] * 100:
            return _payme_error(-31001, "Noto'g'ri summa", "amount")
        return ok({"allow": True})

    elif method == "CreateTransaction":
        tx_id = params.get("id")
        order_id = params.get("account", {}).get("order_id")
        amount = params.get("amount", 0)
        order = db_fetchone("SELECT * FROM orders WHERE id=?", (order_id,)) if order_id else None
        if not order:
            return _payme_error(-31050, "Buyurtma topilmadi", "order_id")
        if amount != order["total"] * 100:
            return _payme_error(-31001, "Noto'g'ri summa", "amount")
        existing = db_fetchone("SELECT * FROM transactions WHERE provider_tx_id=?", (tx_id,))
        if existing:
            if existing["state"] == _PAYME_STATE_CANCELLED:
                return _payme_error(-31008, "Tranzaksiya bekor qilingan")
            return ok({"create_time": int(existing["created_at"] or 0), "transaction": str(existing["id"]), "state": existing["state"]})
        ts = int(time.time() * 1000)
        db_execute(
            "INSERT INTO transactions (provider, provider_tx_id, order_id, amount, state, created_at) VALUES (?,?,?,?,?,?)",
            ("payme", tx_id, order_id, amount, _PAYME_STATE_CREATED, str(ts))
        )
        row = db_fetchone("SELECT id FROM transactions WHERE provider_tx_id=?", (tx_id,))
        return ok({"create_time": ts, "transaction": str(row["id"]), "state": _PAYME_STATE_CREATED})

    elif method == "PerformTransaction":
        tx_id = params.get("id")
        tx = db_fetchone("SELECT * FROM transactions WHERE provider_tx_id=?", (tx_id,))
        if not tx:
            return _payme_error(-31003, "Tranzaksiya topilmadi")
        if tx["state"] == _PAYME_STATE_DONE:
            return ok({"transaction": str(tx["id"]), "perform_time": int(tx["performed_at"] or 0), "state": _PAYME_STATE_DONE})
        if tx["state"] != _PAYME_STATE_CREATED:
            return _payme_error(-31008, "Amalga oshirib bo'lmaydi")
        ts = int(time.time() * 1000)
        db_execute("UPDATE transactions SET state=?, performed_at=? WHERE provider_tx_id=?", (_PAYME_STATE_DONE, str(ts), tx_id))
        db_execute("UPDATE orders SET status='DELIVERED', closed_at=? WHERE id=?", (now_iso(), tx["order_id"]))
        return ok({"transaction": str(tx["id"]), "perform_time": ts, "state": _PAYME_STATE_DONE})

    elif method == "CancelTransaction":
        tx_id = params.get("id")
        reason = params.get("reason", 0)
        tx = db_fetchone("SELECT * FROM transactions WHERE provider_tx_id=?", (tx_id,))
        if not tx:
            return _payme_error(-31003, "Tranzaksiya topilmadi")
        if tx["state"] in (_PAYME_STATE_CANCELLED, _PAYME_STATE_CANCELLED_AFTER_DONE):
            return ok({"transaction": str(tx["id"]), "cancel_time": int(tx["cancelled_at"] or 0), "state": tx["state"]})
        new_state = _PAYME_STATE_CANCELLED_AFTER_DONE if tx["state"] == _PAYME_STATE_DONE else _PAYME_STATE_CANCELLED
        ts = int(time.time() * 1000)
        db_execute("UPDATE transactions SET state=?, cancelled_at=?, reason=? WHERE provider_tx_id=?", (new_state, str(ts), reason, tx_id))
        return ok({"transaction": str(tx["id"]), "cancel_time": ts, "state": new_state})

    elif method == "CheckTransaction":
        tx_id = params.get("id")
        tx = db_fetchone("SELECT * FROM transactions WHERE provider_tx_id=?", (tx_id,))
        if not tx:
            return _payme_error(-31003, "Tranzaksiya topilmadi")
        return ok({
            "create_time": int(tx["created_at"] or 0),
            "perform_time": int(tx["performed_at"] or 0),
            "cancel_time": int(tx["cancelled_at"] or 0),
            "transaction": str(tx["id"]),
            "state": tx["state"],
            "reason": tx.get("reason"),
        })

    return web.json_response({"error": {"code": -32601, "message": {"uz": "Method topilmadi"}}})


# ─── CLICK WEBHOOK ───
async def handle_click(request):
    data = await request.post()
    click_trans_id = data.get("click_trans_id", "")
    service_id = data.get("service_id", "")
    merchant_trans_id = data.get("merchant_trans_id", "")  # order_id
    amount = float(data.get("amount", 0))
    action = int(data.get("action", 0))
    sign_time = data.get("sign_time", "")
    sign_string = data.get("sign_string", "")
    error = int(data.get("error", 0))

    # Verify signature
    if CLICK_SECRET_KEY:
        expected_sign = hashlib.md5(f"{click_trans_id}{service_id}{CLICK_SECRET_KEY}{merchant_trans_id}{amount}{action}{sign_time}".encode()).hexdigest()
        if sign_string != expected_sign:
            return web.json_response({"error": -1, "error_note": "SIGN CHECK FAILED!"})

    order = db_fetchone("SELECT * FROM orders WHERE id=?", (merchant_trans_id,))
    if not order:
        return web.json_response({"error": -5, "error_note": "User does not exist"})
    if abs(order["total"] - amount) > 1:
        return web.json_response({"error": -2, "error_note": "Incorrect parameter amount"})

    if action == 0:  # prepare
        return web.json_response({
            "click_trans_id": click_trans_id,
            "merchant_trans_id": merchant_trans_id,
            "merchant_prepare_id": merchant_trans_id,
            "error": 0,
            "error_note": "Success"
        })
    elif action == 1:  # complete
        if error < 0:
            return web.json_response({"click_trans_id": click_trans_id, "merchant_trans_id": merchant_trans_id, "merchant_confirm_id": None, "error": error, "error_note": "Payment cancelled"})
        db_execute("UPDATE orders SET status='DELIVERED', closed_at=? WHERE id=?", (now_iso(), merchant_trans_id))
        return web.json_response({
            "click_trans_id": click_trans_id,
            "merchant_trans_id": merchant_trans_id,
            "merchant_confirm_id": merchant_trans_id,
            "error": 0,
            "error_note": "Success"
        })
    return web.json_response({"error": -3, "error_note": "Action not found"})


# ─── YANDEX DELIVERY ───
def _yandex_headers():
    return {
        "Authorization": f"Bearer {YANDEX_DELIVERY_TOKEN}",
        "Content-Type": "application/json",
        "Accept-Language": "ru",
    }


async def handle_yandex_price(request):
    """Yetkazish narxini hisoblash — admin panel uchun."""
    data = await request.json()
    order_id = data.get("order_id")
    order = db_fetchone("SELECT * FROM orders WHERE id=?", (order_id,)) if order_id else None
    if not order:
        return web.json_response({"error": "order not found"}, status=404)

    # Do'kon manzilini olish
    store = db_fetchone("SELECT * FROM stores WHERE id=?", (order.get("store_id"),)) if order.get("store_id") else None
    store_lat = data.get("store_lat") or 41.2995
    store_lon = data.get("store_lon") or 69.2401

    if not YANDEX_DELIVERY_TOKEN:
        # Demo rejim — haqiqiy token bo'lmasa
        return web.json_response({
            "price": 25000,
            "currency": "UZS",
            "eta_min": 20,
            "eta_max": 40,
            "demo": True,
        })

    payload = {
        "route_points": [
            {
                "coordinates": {"lat": store_lat, "lon": store_lon},
                "fullname": store["address"] if store and store.get("address") else "Do'kon manzili",
                "type": "source",
            },
            {
                "coordinates": {"lat": order.get("lat") or 41.2995, "lon": order.get("lon") or 69.2401},
                "fullname": order.get("address") or "Mijoz manzili",
                "type": "destination",
                "contact": {"name": order.get("full_name") or "Mijoz", "phone": order.get("phone") or ""},
            },
        ],
        "items": [{"cost_value": str(order.get("total", 0)), "cost_currency": "UZS", "quantity": 1,
                   "size": {"height": 0.3, "length": 0.4, "width": 0.3}, "weight": 2,
                   "title": "Ovqat buyurtmasi"}],
        "due": None,
        "comment": f"Buyurtma #{order['id']}",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{YANDEX_DELIVERY_URL}/check-price",
                json=payload, headers=_yandex_headers(), timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                result = await resp.json()
                if resp.status != 200:
                    return web.json_response({"error": result}, status=resp.status)
                price_data = result.get("price", {})
                return web.json_response({
                    "price": int(float(price_data.get("value", 25000))),
                    "currency": price_data.get("currency", "UZS"),
                    "eta_min": 20, "eta_max": 45,
                })
    except Exception as e:
        logger.exception("Yandex price error")
        return web.json_response({"error": str(e)}, status=500)


async def handle_yandex_create(request):
    """Yandex Delivery orqali kuryer chaqirish."""
    data = await request.json()
    order_id = data.get("order_id")
    store_lat = data.get("store_lat", 41.2995)
    store_lon = data.get("store_lon", 69.2401)
    store_name = data.get("store_name", "Do'kon")
    store_phone = data.get("store_phone", "+998901234567")

    order = db_fetchone("SELECT * FROM orders WHERE id=?", (order_id,)) if order_id else None
    if not order:
        return web.json_response({"error": "order not found"}, status=404)

    if not YANDEX_DELIVERY_TOKEN:
        # Demo rejim
        fake_claim_id = f"demo-{order_id}-{int(time.time())}"
        db_execute(
            "UPDATE orders SET yandex_claim_id=?, yandex_status=?, delivery_type=?, yandex_tracking_url=? WHERE id=?",
            (fake_claim_id, "estimating", "yandex",
             f"https://taxi.yandex.uz/share/{fake_claim_id}", order_id)
        )
        return web.json_response({
            "claim_id": fake_claim_id,
            "status": "estimating",
            "tracking_url": f"https://taxi.yandex.uz/share/{fake_claim_id}",
            "demo": True,
        })

    import uuid
    request_id = str(uuid.uuid4())
    payload = {
        "request_id": request_id,
        "callback_properties": {"callback_url": f"{WEBAPP_URL}/api/yandex_webhook"},
        "route_points": [
            {
                "coordinates": {"lat": store_lat, "lon": store_lon},
                "fullname": store_name,
                "type": "source",
                "contact": {"name": store_name, "phone": store_phone},
                "skip_confirmation": True,
            },
            {
                "coordinates": {
                    "lat": order.get("lat") or 41.2995,
                    "lon": order.get("lon") or 69.2401,
                },
                "fullname": order.get("address") or "Mijoz manzili",
                "type": "destination",
                "contact": {
                    "name": order.get("full_name") or "Mijoz",
                    "phone": order.get("phone") or "+998900000000",
                },
            },
        ],
        "items": [
            {
                "cost_value": str(order.get("total", 0)),
                "cost_currency": "UZS",
                "droppof_point": 1,
                "quantity": 1,
                "size": {"height": 0.3, "length": 0.4, "width": 0.3},
                "weight": 2,
                "title": f"Buyurtma #{order['id']}",
            }
        ],
        "comment": f"Buyurtma #{order['id']}: {order.get('items', '')[:100]}",
        "requirements": {"taxi_class": "express"},
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{YANDEX_DELIVERY_URL}/claims/create?request_id={request_id}",
                json=payload, headers=_yandex_headers(), timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                result = await resp.json()
                if resp.status not in (200, 201):
                    return web.json_response({"error": result}, status=resp.status)

                claim_id = result.get("id", "")
                status = result.get("status", "estimating")
                tracking_url = f"https://taxi.yandex.uz/route/{claim_id}"

                db_execute(
                    "UPDATE orders SET yandex_claim_id=?, yandex_status=?, delivery_type=?, yandex_tracking_url=? WHERE id=?",
                    (claim_id, status, "yandex", tracking_url, order_id)
                )

                # Confirm claim (accept price automatically)
                await asyncio.sleep(2)
                async with session.post(
                    f"{YANDEX_DELIVERY_URL}/claims/accept?claim_id={claim_id}",
                    json={"version": result.get("version", 1)},
                    headers=_yandex_headers()
                ) as _:
                    pass

                return web.json_response({
                    "claim_id": claim_id,
                    "status": status,
                    "tracking_url": tracking_url,
                })
    except Exception as e:
        logger.exception("Yandex create error")
        return web.json_response({"error": str(e)}, status=500)


async def handle_yandex_status(request):
    """Yandex buyurtma holatini tekshirish."""
    order_id = request.query.get("order_id")
    order = db_fetchone("SELECT * FROM orders WHERE id=?", (order_id,)) if order_id else None
    if not order or not order.get("yandex_claim_id"):
        return web.json_response({"error": "no yandex delivery"}, status=404)

    claim_id = order["yandex_claim_id"]

    if not YANDEX_DELIVERY_TOKEN or claim_id.startswith("demo-"):
        return web.json_response({
            "claim_id": claim_id,
            "status": order.get("yandex_status", "estimating"),
            "tracking_url": order.get("yandex_tracking_url"),
            "demo": True,
        })

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{YANDEX_DELIVERY_URL}/claims/info?claim_id={claim_id}",
                headers=_yandex_headers(), timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                result = await resp.json()
                status = result.get("status", "unknown")
                db_execute("UPDATE orders SET yandex_status=? WHERE id=?", (status, order_id))
                return web.json_response({
                    "claim_id": claim_id,
                    "status": status,
                    "tracking_url": order.get("yandex_tracking_url"),
                    "courier": result.get("performer_info", {}).get("name"),
                    "courier_phone": result.get("performer_info", {}).get("phone"),
                })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_yandex_webhook(request):
    """Yandex Delivery status webhook."""
    try:
        data = await request.json()
        claim_id = data.get("id")
        status = data.get("status")
        if claim_id and status:
            order = db_fetchone("SELECT * FROM orders WHERE yandex_claim_id=?", (claim_id,))
            if order:
                db_execute("UPDATE orders SET yandex_status=? WHERE yandex_claim_id=?", (status, claim_id))
                if status in ("delivered", "delivery_arrived"):
                    db_execute("UPDATE orders SET status='DELIVERED', closed_at=? WHERE yandex_claim_id=?",
                               (now_iso(), claim_id))
    except Exception:
        pass
    return web.json_response({"ok": True})


async def handle_yandex_cancel(request):
    """Yandex kuryerini bekor qilish."""
    data = await request.json()
    order_id = data.get("order_id")
    order = db_fetchone("SELECT * FROM orders WHERE id=?", (order_id,)) if order_id else None
    if not order or not order.get("yandex_claim_id"):
        return web.json_response({"error": "no yandex delivery"}, status=404)

    claim_id = order["yandex_claim_id"]
    if not YANDEX_DELIVERY_TOKEN or claim_id.startswith("demo-"):
        db_execute("UPDATE orders SET yandex_status='cancelled', delivery_type='own' WHERE id=?", (order_id,))
        return web.json_response({"status": "cancelled", "demo": True})

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{YANDEX_DELIVERY_URL}/claims/cancel?claim_id={claim_id}",
                json={"cancel_state": "free", "version": 1},
                headers=_yandex_headers(), timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                db_execute("UPDATE orders SET yandex_status='cancelled', delivery_type='own' WHERE id=?", (order_id,))
                return web.json_response({"status": "cancelled"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# ─── DAILY REPORT BACKGROUND TASK ───
async def daily_report_loop(bot: "Bot"):
    while True:
        now = datetime.now(timezone.utc)
        # Schedule for 18:00 UTC (≈23:00 Tashkent +5)
        target = now.replace(hour=18, minute=0, second=0, microsecond=0)
        if now >= target:
            target = target + timedelta(days=1)
        await asyncio.sleep((target - now).total_seconds())
        try:
            today = date.today().isoformat()
            stores = db_fetchall("SELECT * FROM stores")
            for store in stores:
                sid = store["id"]
                row = db_fetchone(
                    "SELECT COUNT(*) as cnt, COALESCE(SUM(total),0) as rev FROM orders WHERE store_id=? AND created_at LIKE ?",
                    (sid, today + "%")
                ) or {}
                top = db_fetchall(
                    """SELECT items, COUNT(*) as c FROM orders
                       WHERE store_id=? AND created_at LIKE ?
                       GROUP BY items ORDER BY c DESC LIMIT 3""",
                    (sid, today + "%")
                )
                msg = (
                    f"📊 <b>{store['name']} — Kunlik hisobot</b>\n"
                    f"📅 {today}\n\n"
                    f"📦 Buyurtmalar: <b>{row.get('cnt', 0)}</b>\n"
                    f"💰 Tushum: <b>{row.get('rev', 0):,} so'm</b>\n"
                )
                if top:
                    msg += "\n🔥 Top mahsulotlar:\n"
                    for t in top:
                        msg += f"  • {t['items']} ({t['c']} ta)\n"
                try:
                    await bot.send_message(store["admin_id"], msg, parse_mode="HTML")
                except Exception:
                    pass
                # Update monthly order count in subscription
                _get_or_create_subscription(sid, store["admin_id"])
        except Exception as e:
            logger.exception(f"Daily report error: {e}")


async def handle_stats(request):
    admin_id = request.query.get("admin_id")
    if not admin_id or admin_id == '0':
        return web.json_response({"error": "admin_id required"}, status=400)
    try:
        admin_id_int = int(admin_id)
    except ValueError:
        return web.json_response({"error": "invalid admin_id"}, status=400)

    store = db_fetchone("SELECT * FROM stores WHERE admin_id=?", (admin_id_int,))
    store_cond = " AND store_id=?" if store else ""
    store_p = (store['id'],) if store else ()

    today = date.today().isoformat()

    today_row = db_fetchone(
        f"SELECT COUNT(*) as cnt, COALESCE(SUM(total),0) as rev FROM orders WHERE created_at LIKE ?{store_cond}",
        (today + '%',) + store_p
    ) or {}

    total_row = db_fetchone(
        f"SELECT COUNT(*) as cnt, COALESCE(SUM(total),0) as rev FROM orders WHERE 1=1{store_cond}",
        store_p
    ) or {}

    active_row = db_fetchone(
        f"SELECT COUNT(*) as cnt FROM orders WHERE status='IN_PROGRESS'{store_cond}",
        store_p
    ) or {}

    weekly = []
    for i in range(6, -1, -1):
        d = (date.today() - timedelta(days=i)).isoformat()
        row = db_fetchone(
            f"SELECT COUNT(*) as cnt, COALESCE(SUM(total),0) as rev FROM orders WHERE created_at LIKE ?{store_cond}",
            (d + '%',) + store_p
        ) or {}
        weekly.append({"date": d, "count": row.get('cnt', 0), "revenue": row.get('rev', 0)})

    return web.json_response({
        "today_orders": today_row.get('cnt', 0),
        "today_revenue": today_row.get('rev', 0),
        "total_orders": total_row.get('cnt', 0),
        "total_revenue": total_row.get('rev', 0),
        "active_deliveries": active_row.get('cnt', 0),
        "weekly": weekly,
    })

# 1. Portni dinamik qiling (Kodingizning tepa qismida)
WEBAPP_PORT = int(os.environ.get("PORT", 10000))


async def main():
    # 1. Ma'lumotlar bazasini yangilash
    init_db()

    # 2. Bot va Dispatcher obyektlarini yaratish
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # 3. MUHIM: Routerni polling boshlanishidan OLDIN ulash shart!
    # Agarda bu qator pastda bo'lsa, bot xabarlarni ko'rmaydi.
    dp.include_router(router)

    # Bot haqida ma'lumotni logga chiqarish
    me = await bot.get_me()
    logger.info(f"Bot started @{me.username}")

    # 4. Web server sozlamalari (aiohttp)
    app = web.Application()
    app.router.add_get('/', handle_index)
    app.router.add_get('/index1.html', handle_index)
    app.router.add_get('/admin.html', handle_admin)
    app.router.add_get('/onboarding.html', lambda r: web.FileResponse('webapp/onboarding.html'))
    app.router.add_post('/api/register', handle_register)
    app.router.add_get('/api/data', handle_api_data)
    app.router.add_get('/api/admin_data', handle_admin_data)
    app.router.add_post('/api/store', handle_update_store)
    app.router.add_post('/api/product', handle_update_product)
    app.router.add_post('/api/delete_product', handle_delete_product)
    app.router.add_post('/api/user_region', handle_user_region)
    # Promo codes
    app.router.add_post('/api/promo', handle_create_promo)
    app.router.add_get('/api/promos', handle_list_promos)
    app.router.add_post('/api/delete_promo', handle_delete_promo)
    app.router.add_post('/api/validate_promo', handle_validate_promo)
    # Referrals
    app.router.add_get('/api/referral', handle_referral_link)
    app.router.add_get('/api/orders', handle_orders)
    app.router.add_get('/api/stats', handle_stats)
    app.router.add_post('/api/order_status', handle_order_status)
    # Branding
    app.router.add_get('/api/branding', handle_branding)
    app.router.add_post('/api/branding', handle_update_branding)
    # Order tracking
    app.router.add_get('/api/order_track', handle_order_track)
    # Ratings
    app.router.add_post('/api/rating', handle_submit_rating)
    app.router.add_get('/api/ratings', handle_ratings)
    # Subscription
    app.router.add_get('/api/subscription', handle_subscription)
    app.router.add_post('/api/subscription', handle_upgrade_subscription)
    # Payment webhooks
    app.router.add_post('/api/payme', handle_payme)
    app.router.add_post('/api/click', handle_click)
    # Yandex Delivery
    app.router.add_post('/api/yandex/price', handle_yandex_price)
    app.router.add_post('/api/yandex/create', handle_yandex_create)
    app.router.add_get('/api/yandex/status', handle_yandex_status)
    app.router.add_post('/api/yandex/cancel', handle_yandex_cancel)
    app.router.add_post('/api/yandex_webhook', handle_yandex_webhook)
    # Landing page
    app.router.add_get('/landing', lambda r: web.FileResponse('webapp/landing.html'))

    # Statik fayllar uchun (agar kerak bo'lsa)
    if os.path.exists("webapp"):
        app.router.add_static('/webapp/', path='webapp', name='webapp')

    runner = web.AppRunner(app)
    await runner.setup()

    # Render PORT'ida web-serverni ishga tushirish
    site = web.TCPSite(runner, '0.0.0.0', WEBAPP_PORT)
    await site.start()
    logger.info(f"Web server started on port {WEBAPP_PORT}")

    # 5. Kunlik hisobot fon vazifasi
    asyncio.create_task(daily_report_loop(bot))

    # 6. Botni polling rejimida yoqish
    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())