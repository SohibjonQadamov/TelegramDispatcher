from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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

if not BOT_TOKEN or not GROUP_CHAT_ID:
    raise RuntimeError(".env ni to'ldiring")

DB_PATH = Path("orders.db")
WEBAPP_PORT = int(os.environ.get("PORT", 8080))
WEBAPP_URL = os.getenv("WEBAPP_URL") or "https://d0fc-213-230-80-60.ngrok-free.app" # placeholder, user must update .env

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("bot")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ================= DB =================
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT, status TEXT DEFAULT 'NEW',
            full_name TEXT, phone TEXT, address TEXT,
            lat REAL, lon REAL,
            items TEXT, total INTEGER,
            created_by_id INTEGER, created_by_name TEXT,
            accepted_by_id INTEGER, accepted_by_name TEXT,
            accepted_at TEXT, closed_at TEXT,
            group_message_id INTEGER
        )""")
        try:
            conn.execute("ALTER TABLE orders ADD COLUMN store_id INTEGER")
        except sqlite3.OperationalError:
            pass

        conn.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            role TEXT DEFAULT 'user',
            registered_at TEXT
        )""")

        conn.execute("""CREATE TABLE IF NOT EXISTS stores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER UNIQUE,
            name TEXT, type TEXT, emoji TEXT, bg_color TEXT
        )""")

        conn.execute("""CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_id INTEGER,
            name TEXT, price INTEGER, desc TEXT, emoji TEXT, cat TEXT,
            old_price INTEGER, discount_qty INTEGER, discount_end TEXT
        )""")
        
        # Add new columns to existing products table if they don't exist
        try:
            conn.execute("ALTER TABLE products ADD COLUMN old_price INTEGER")
            conn.execute("ALTER TABLE products ADD COLUMN discount_qty INTEGER")
            conn.execute("ALTER TABLE products ADD COLUMN discount_end TEXT")
        except sqlite3.OperationalError:
            pass
            
        conn.commit()


def db_fetchone(sql, params=()):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None


def db_fetchall(sql, params=()):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def db_execute(sql, params=()):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(sql, params)
        conn.commit()


def create_order(full_name, phone, address, lat, lon, items, total, uid, uname, store_id=None):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "INSERT INTO orders (created_at, status, full_name, phone, address, lat, lon, items, total, created_by_id, created_by_name, store_id) VALUES (?, 'NEW', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (now_iso(), full_name, phone, address, lat, lon, items, total, uid, uname, store_id)
        )
        conn.commit()
        return int(cur.lastrowid)


def get_order(oid):
    return db_fetchone("SELECT * FROM orders WHERE id=?", (oid,))


def set_group_message_id(oid, mid):
    db_execute("UPDATE orders SET group_message_id=? WHERE id=?", (mid, oid))


def try_accept_order(oid, cid, cname):
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
    if uid and is_admin(uid):
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
    data = json.loads(msg.web_app_data.data)
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
    await msg.answer("🍔 Fast Food", reply_markup=main_kb(msg.from_user.id if msg.from_user else None))


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
        oid = create_order(fn, ph, ad, lat, lon, items, total, cb.from_user.id, cb.from_user.full_name, store_id)
        order = get_order(oid)
        txt = fmt_order(order)
        
        target_chat = GROUP_CHAT_ID
        if store_id:
            store = db_fetchone("SELECT admin_id FROM stores WHERE id=?", (store_id,))
            if store and store['admin_id']:
                target_chat = store['admin_id']

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
    if mid:
        try:
            await cb.bot.edit_message_text(GROUP_CHAT_ID, int(mid), text=fmt_order(order), reply_markup=None,
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
    mid = order.get('group_message_id')
    if mid:
        try: await cb.bot.edit_message_text(GROUP_CHAT_ID, int(mid), text=fmt_order(order), reply_markup=None, parse_mode="HTML")
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
    await cb.answer("❌ Bekor qilindi")
    try:
        txt = fmt_order(order)
        if order.get('lat') and order.get('lon'):
            loc_msg = await cb.bot.send_location(GROUP_CHAT_ID, order['lat'], order['lon'])
            sent = await cb.bot.send_message(GROUP_CHAT_ID, txt, reply_to_message_id=loc_msg.message_id,
                                             reply_markup=group_accept_kb(oid), parse_mode="HTML")
        else:
            sent = await cb.bot.send_message(GROUP_CHAT_ID, txt, reply_markup=group_accept_kb(oid), parse_mode="HTML")
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
    stores_db = db_fetchall("SELECT * FROM stores")
    products_db = db_fetchall("SELECT * FROM products")
    
    stores = []
    for s in stores_db:
        stores.append({
            "id": s['id'],
            "name": s['name'],
            "emoji": s['emoji'],
            "time": "15-30",
            "rating": "5.0",
            "type": s['type'],
            "bg": s['bg_color'] or "linear-gradient(135deg, #a18cd1, #fbc2eb)"
        })
        
    menuItems = {}
    for p in products_db:
        sid = p['store_id']
        if sid not in menuItems: menuItems[sid] = []
        menuItems[sid].append({
            "id": p['id'],
            "name": p['name'],
            "price": p['price'],
            "desc": p['desc'],
            "emoji": p['emoji'],
            "cat": p['cat'],
            "store_id": p['store_id'],
            "old_price": p['old_price'],
            "discount_qty": p['discount_qty'],
            "discount_end": p['discount_end']
        })
        
    return web.json_response({"stores": stores, "menuItems": menuItems})

async def handle_admin_data(request):
    admin_id = request.query.get("admin_id")
    if not admin_id: return web.json_response({"error": "admin_id required"}, status=400)
    
    store = db_fetchone("SELECT * FROM stores WHERE admin_id=?", (admin_id,))
    products = []
    if store:
        products = db_fetchall("SELECT * FROM products WHERE store_id=?", (store['id'],))
        
    return web.json_response({"store": store, "products": products})

async def handle_update_store(request):
    data = await request.json()
    admin_id = data.get('admin_id')
    name = data.get('name')
    type_ = data.get('type')
    emoji = data.get('emoji')
    bg = "linear-gradient(135deg, #FF9A9E, #FECFEF)"
    
    store = db_fetchone("SELECT * FROM stores WHERE admin_id=?", (admin_id,))
    if store:
        db_execute("UPDATE stores SET name=?, type=?, emoji=? WHERE admin_id=?", (name, type_, emoji, admin_id))
    else:
        db_execute("INSERT INTO stores (admin_id, name, type, emoji, bg_color) VALUES (?, ?, ?, ?, ?)", (admin_id, name, type_, emoji, bg))
    return web.json_response({"status": "ok"})

async def handle_update_product(request):
    data = await request.json()
    admin_id = data.get('admin_id')
    store = db_fetchone("SELECT * FROM stores WHERE admin_id=?", (admin_id,))
    if not store: return web.json_response({"error": "Store not found"}, status=400)
    
    p_id = data.get('id')
    name = data.get('name')
    price = data.get('price')
    desc = data.get('desc', '')
    emoji = data.get('emoji')
    cat = data.get('cat')
    old_price = data.get('old_price')
    discount_qty = data.get('discount_qty')
    discount_end = data.get('discount_end')
    
    if p_id:
        db_execute("""UPDATE products SET name=?, price=?, desc=?, emoji=?, cat=?, old_price=?, discount_qty=?, discount_end=? 
                      WHERE id=? AND store_id=?""", 
                   (name, price, desc, emoji, cat, old_price, discount_qty, discount_end, p_id, store['id']))
    else:
        db_execute("""INSERT INTO products (store_id, name, price, desc, emoji, cat, old_price, discount_qty, discount_end) 
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
                   (store['id'], name, price, desc, emoji, cat, old_price, discount_qty, discount_end))
    return web.json_response({"status": "ok"})

async def handle_delete_product(request):
    data = await request.json()
    admin_id = data.get('admin_id')
    p_id = data.get('id')
    store = db_fetchone("SELECT * FROM stores WHERE admin_id=?", (admin_id,))
    if store and p_id:
        db_execute("DELETE FROM products WHERE id=? AND store_id=?", (p_id, store['id']))
    return web.json_response({"status": "ok"})

# 1. Portni dinamik qiling (Kodingizning tepa qismida)
WEBAPP_PORT = int(os.environ.get("PORT", 10000))

# 2. Main funksiyasini mana bunga almashtiring:
async def main():
    init_db()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # Setup aiohttp app
    app = web.Application()
    app.router.add_get('/', handle_index)
    app.router.add_get('/index1.html', handle_index)
    app.router.add_get('/admin.html', handle_admin)
    app.router.add_get('/api/data', handle_api_data)
    app.router.add_get('/api/admin_data', handle_admin_data)
    app.router.add_post('/api/store', handle_update_store)
    app.router.add_post('/api/product', handle_update_product)
    app.router.add_post('/api/delete_product', handle_delete_product)
    
    # MUHIM: Statik fayllar uchun yo'l (agar papka nomi webapp bo'lsa)
    # App ichida statik fayllarni ko'rsatib qo'yish kerak
    if os.path.exists("webapp"):
        app.router.add_static('/webapp/', path='webapp', name='webapp')

    runner = web.AppRunner(app)
    await runner.setup()
    
    # Render PORT o'zgaruvchisini ishlatsin
    site = web.TCPSite(runner, '0.0.0.0', WEBAPP_PORT)
    await site.start()
    
    logger.info(f"Web server started on port {WEBAPP_PORT}")

    # Botni yurgizish (Webhook ishlatishni maslahat berardim, lekin polling bo'lsa ham port to'g'ri bo'lishi shart)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
    init_db()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    me = await bot.get_me()
    logger.info("Bot started @%s", me.username)
    
    # Setup aiohttp app
    app = web.Application()
    app.router.add_get('/', handle_index)
    app.router.add_get('/index1.html', handle_index)
    app.router.add_get('/admin.html', handle_admin)
    app.router.add_get('/api/data', handle_api_data)
    app.router.add_get('/api/admin_data', handle_admin_data)
    app.router.add_post('/api/store', handle_update_store)
    app.router.add_post('/api/product', handle_update_product)
    app.router.add_post('/api/delete_product', handle_delete_product)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', WEBAPP_PORT)
    await site.start()
    logger.info(f"Web server started on port {WEBAPP_PORT}")

    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())