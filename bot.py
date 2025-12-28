import os
import threading
from flask import Flask
from aiogram import Bot, Dispatcher, types
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ContentTypes  # ✅ to'g'ri import
)
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

from database import (
    users_col, pending_videos_col, approved_videos_col,
    channels_col, admins_col, settings_col
)

# ======================================
# Yordamchi funksiyalar
# ======================================

def get_base_channel():
    setting = settings_col.find_one({"key": "base_channel"})
    return setting["value"] if setting else None

def set_base_channel(channel_id):
    settings_col.update_one(
        {"key": "base_channel"},
        {"$set": {"value": channel_id}},
        upsert=True
    )

BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

if not BOT_TOKEN or not MONGO_URI:
    raise ValueError("BOT_TOKEN yoki MONGO_URI muhit o'zgaruvchisi mavjud emas!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

MAIN_ADMIN_ID = 7162630033

# ======================================
# Holatlar (FSM)
# ======================================

class AddChannel(StatesGroup):
    waiting_for_channel = State()

class SendMessageToAdmin(StatesGroup):
    waiting_for_message = State()

class BroadcastMessage(StatesGroup):
    waiting_for_message = State()

class AddAdmin(StatesGroup):
    waiting_for_id = State()

class RemoveAdmin(StatesGroup):
    waiting_for_id = State()

class AddSerial(StatesGroup):
    waiting_for_code = State()
    waiting_for_title = State()
    waiting_for_parts = State()

class SearchState(StatesGroup):
    searching = State()

class UserVideoState(StatesGroup):
    waiting_video = State()

class RemoveVideoState(StatesGroup):
    waiting_for_code = State()

class AddMovieState(StatesGroup):
    waiting_for_movie = State()

# ======================================
# Menyular
# ======================================

def main_menu():
    kb = [
        [KeyboardButton(text="🎬 Kino qidirish")],
        [KeyboardButton(text="🏆 Top kinolar"), KeyboardButton(text="📤 Kino yuborish")],
        [KeyboardButton(text="✍️ Adminga yozish"), KeyboardButton(text="📊 Statistika")],
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def admin_menu():
    kb = [
        [KeyboardButton(text="🆕 Kino qo'shish"), KeyboardButton(text="📺 Serial qo'shish")],
        [KeyboardButton(text="📢 Xabar yuborish"), KeyboardButton(text="🔍 Majburiy kanallar")],
        [KeyboardButton(text="📡 Baza kanal"), KeyboardButton(text="🗑 Kino o'chirish")],
        [KeyboardButton(text="👑 Admin qo'shish")],
        [KeyboardButton(text="🗑 Admin o'chirish"), KeyboardButton(text="📋 Adminlar")],
        [KeyboardButton(text="🔙 Orqaga")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def back_button():
    kb = [[KeyboardButton(text="🔙 Orqaga")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# ======================================
# Foydalanuvchi boshqaruvi
# ======================================

async def add_user(user_id: int, username: str = None):
    if not users_col.find_one({"user_id": user_id}):
        users_col.insert_one({"user_id": int(user_id), "username": username})

async def check_subscription(user_id: int) -> bool:
    channels = list(channels_col.find({}))
    if not channels:
        return True
    for ch in channels:
        try:
            chat_member = await bot.get_chat_member(chat_id=ch['channel_id'], user_id=user_id)
            if chat_member.status in ['left', 'kicked']:
                return False
        except Exception as e:
            print(f"❌ Kanal tekshirishda xato (ID: {ch.get('channel_id')}): {e}")
            return False
    return True

async def send_subscription_request(message: types.Message):
    channels = list(channels_col.find({}))
    if not channels:
        return
    text = "Quyidagi kanallarga obuna bo'ling:\n\n"
    btns = []
    for ch in channels:
        link = ch.get('link', ch['channel_id'])
        title = ch.get('title', link)
        text += f"• {title}\n"
        btns.append([InlineKeyboardButton(text=title, url=link)])
    btns.append([InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub")])
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

# ======================================
# Boshlang'ich handler
# ======================================

@dp.message_handler(commands=['start'])
async def start_handler(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    await add_user(user_id, username)
    is_admin = (user_id == MAIN_ADMIN_ID) or (admins_col.find_one({"user_id": user_id}) is not None)

    welcome_text = "Assalomu alaykum! Kino botga xush kelibsiz.\nQuyidagi tugmalardan foydalaning:"
    if is_admin:
        await message.answer(welcome_text, reply_markup=admin_menu())
    else:
        await message.answer(welcome_text, reply_markup=main_menu())

@dp.callback_query_handler(lambda c: c.data == "check_sub")
async def check_sub_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if await check_subscription(user_id):
        await callback.message.edit_text("✅ Obuna tasdiqlandi! Endi botdan foydalanishingiz mumkin.")
        await start_handler(callback.message)
    else:
        await callback.answer("❌ Hali ham kanallarga obuna bo'lmagansiz!", show_alert=True)

# ======================================
# Foydalanuvchi tugmalar (obuna talab qilinadi)
# ======================================

@dp.message_handler(lambda m: m.text == "🎬 Kino qidirish")
async def search_video(message: types.Message):
    user_id = message.from_user.id
    if not await check_subscription(user_id):
        await send_subscription_request(message)
        return
    await SearchState.searching.set()
    await message.answer("Kino/serial nomi yoki kodini kiriting:", reply_markup=back_button())

@dp.message_handler(state=SearchState.searching, content_types=ContentTypes.ANY)
async def process_search(message: types.Message, state: FSMContext):
    if message.text == "🔙 Orqaga":
        await state.finish()
        is_admin = (message.from_user.id == MAIN_ADMIN_ID) or (admins_col.find_one({"user_id": message.from_user.id}) is not None)
        if is_admin:
            await message.answer("Admin panel:", reply_markup=admin_menu())
        else:
            await message.answer("Asosiy menyu:", reply_markup=main_menu())
        return
    query = message.text.strip()
    video = approved_videos_col.find_one({"$or": [{"code": query}, {"title": {"$regex": query, "$options": "i"}}]})
    if video:
        approved_videos_col.update_one({"_id": video["_id"]}, {"$inc": {"views": 1}})
        if video.get("is_serial"):
            parts = video.get("parts", [])
            for part in parts:
                await bot.copy_message(
                    chat_id=message.chat.id,
                    from_chat_id=part["chat_id"],
                    message_id=part["message_id"]
                )
        else:
            await bot.copy_message(
                chat_id=message.chat.id,
                from_chat_id=video["chat_id"],
                message_id=video["message_id"]
            )
    else:
        await message.answer("Kino topilmadi!")
    await state.finish()
    is_admin = (message.from_user.id == MAIN_ADMIN_ID) or (admins_col.find_one({"user_id": message.from_user.id}) is not None)
    if is_admin:
        await message.answer("Admin panel:", reply_markup=admin_menu())
    else:
        await message.answer("Asosiy menyu:", reply_markup=main_menu())

@dp.message_handler(lambda m: m.text == "🏆 Top kinolar")
async def top_videos(message: types.Message):
    user_id = message.from_user.id
    if not await check_subscription(user_id):
        await send_subscription_request(message)
        return
    top_list = approved_videos_col.find().sort("views", -1).limit(10)
    text = "🏆 Top 10 kinolar:\n\n"
    for i, v in enumerate(top_list, 1):
        title = v.get('title', 'Noma\'lum')
        code = v.get('code', 'Kod yo\'q')
        typ = '📺 Serial' if v.get('is_serial') else '🎥 Kino'
        text += f"{i}. {title} (Kod: {code}) — {typ}\n"
    if text == "🏆 Top 10 kinolar:\n\n":
        text = "Hali hech qanday kino qo'shilmagan."
    await message.answer(text)

@dp.message_handler(lambda m: m.text == "📤 Kino yuborish")
async def send_video_request(message: types.Message):
    user_id = message.from_user.id
    if not await check_subscription(user_id):
        await send_subscription_request(message)
        return
    await UserVideoState.waiting_video.set()
    await message.answer("Kino/serialni shu botga yuboring (video sifatida):", reply_markup=back_button())

@dp.message_handler(state=UserVideoState.waiting_video, content_types=ContentTypes.ANY)
async def handle_user_video_or_back(message: types.Message, state: FSMContext):
    if message.text == "🔙 Orqaga":
        await state.finish()
        is_admin = (message.from_user.id == MAIN_ADMIN_ID) or (admins_col.find_one({"user_id": message.from_user.id}) is not None)
        if is_admin:
            await message.answer("Admin panel:", reply_markup=admin_menu())
        else:
            await message.answer("Asosiy menyu:", reply_markup=main_menu())
        return

    if message.content_type != "video":
        await message.answer("Faqat video yuboring!")
        return

    pending_videos_col.insert_one({
        "user_id": message.from_user.id,
        "video_file_id": message.video.file_id,
        "caption": message.caption or "",
        "chat_id": message.chat.id,
        "message_id": message.message_id,
        "status": "pending"
    })
    await message.answer("✅ Kino adminlarga yuborildi. Tasdiqlansa, botga qo'shiladi.")

    # Adminlarga xabar yuborish
    try:
        all_admins = [MAIN_ADMIN_ID]
        extra_admins = admins_col.find({})
        for a in extra_admins:
            uid = a["user_id"]
            if isinstance(uid, str):
                uid = int(uid)
            if uid != MAIN_ADMIN_ID:
                all_admins.append(uid)

        for admin_id in all_admins:
        for admin_id in all_admins:
    try:
        # Tugmalar yaratish
        approve_btn = InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve_{message.message_id}_{message.chat.id}")
        reject_btn = InlineKeyboardButton("❌ Rad etish", callback_data=f"reject_{message.message_id}")
        keyboard = InlineKeyboardMarkup().add(approve_btn, reject_btn)

        await bot.send_message(
            admin_id,
            f"📩 Yangi kino tasdiqlash uchun!\nFoydalanuvchi: {message.from_user.id}",
            reply_markup=keyboard
        )
        await bot.forward_message(admin_id, message.chat.id, message.message_id)
    except Exception as e:
        print(f"Admin {admin_id} ga xabar yuborishda xato: {e}")
    except Exception as e:
        print(f"Umumiy xabar yuborish xatosi: {e}")

    await state.finish()
    is_admin = (message.from_user.id == MAIN_ADMIN_ID) or (admins_col.find_one({"user_id": message.from_user.id}) is not None)
    if is_admin:
        await message.answer("Admin panel:", reply_markup=admin_menu())
    else:
        await message.answer("Asosiy menyu:", reply_markup=main_menu())

# ======================================
# Ochiq tugmalar (obuna talab qilinmaydi)
# ======================================

@dp.message_handler(lambda m: m.text == "✍️ Adminga yozish")
async def contact_admin(message: types.Message):
    await SendMessageToAdmin.waiting_for_message.set()
    await message.answer("Xabaringizni yozing:", reply_markup=back_button())

@dp.message_handler(state=SendMessageToAdmin.waiting_for_message, content_types=ContentTypes.ANY)
async def forward_to_admin(message: types.Message, state: FSMContext):
    if message.text == "🔙 Orqaga":
        await state.finish()
        is_admin = (message.from_user.id == MAIN_ADMIN_ID) or (admins_col.find_one({"user_id": message.from_user.id}) is not None)
        if is_admin:
            await message.answer("Admin panel:", reply_markup=admin_menu())
        else:
            await message.answer("Asosiy menyu:", reply_markup=main_menu())
        return
    text = f"📩 Yangi xabar:\n\nFoydalanuvchi: {message.from_user.full_name} (@{message.from_user.username or '---'})\nID: {message.from_user.id}\n\nXabar:\n{message.text}"
    try:
        all_admins = [MAIN_ADMIN_ID]
        extra_admins = admins_col.find({})
        for a in extra_admins:
            uid = a["user_id"]
            if isinstance(uid, str):
                uid = int(uid)
            if uid != MAIN_ADMIN_ID:
                all_admins.append(uid)
        for admin_id in all_admins:
            try:
                await bot.send_message(admin_id, text)
            except Exception as e:
                print(f"Admin {admin_id} ga xabar yuborishda xato: {e}")
    except Exception as e:
        print(f"Xabar yuborishda umumiy xato: {e}")
    await message.answer("✅ Xabaringiz adminlarga yuborildi!")
    await state.finish()
    is_admin = (message.from_user.id == MAIN_ADMIN_ID) or (admins_col.find_one({"user_id": message.from_user.id}) is not None)
    if is_admin:
        await message.answer("Admin panel:", reply_markup=admin_menu())
    else:
        await message.answer("Asosiy menyu:", reply_markup=main_menu())

@dp.message_handler(lambda m: m.text == "📊 Statistika")
async def stats(message: types.Message):
    total = users_col.count_documents({})
    videos = approved_videos_col.count_documents({})
    pending = pending_videos_col.count_documents({"status": "pending"})
    await message.answer(f"👤 Foydalanuvchilar: {total}\n🎥 Tasdiqlangan kinolar: {videos}\n⏳ Kutayotgan: {pending}")

# ======================================
# Admin panel
# ======================================

@dp.message_handler(lambda m: m.text == "👑 Admin panel")
async def admin_panel(message: types.Message):
    user_id = message.from_user.id
    is_admin = (user_id == MAIN_ADMIN_ID) or (admins_col.find_one({"user_id": user_id}) is not None)
    if not is_admin:
        await message.answer("Siz admin emassiz!")
        return
    await message.answer("Admin panel:", reply_markup=admin_menu())

# ======================================
# Baza kanal
# ======================================

@dp.message_handler(lambda m: m.text == "📡 Baza kanal")
async def manage_base_channel(message: types.Message):
    user_id = message.from_user.id
    is_admin = (user_id == MAIN_ADMIN_ID) or (admins_col.find_one({"user_id": user_id}) is not None)
    if not is_admin:
        return
    kb = [
        [KeyboardButton(text="➕ Baza kanal qo'shish")],
        [KeyboardButton(text="➖ Baza kanalni olib tashlash")],
        [KeyboardButton(text="🔙 Orqaga")]
    ]
    await message.answer("Baza kanal boshqaruvi:", reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))

@dp.message_handler(lambda m: m.text == "➕ Baza kanal qo'shish")
async def add_base_channel_start(message: types.Message):
    if message.from_user.id != MAIN_ADMIN_ID:
        return
    await message.answer("Baza kanal ID yoki username yuboring (masalan: @mybasechannel yoki -1001234567890):")

@dp.message_handler(lambda m: m.text.startswith("@") or (m.text.lstrip("-").isdigit() and len(m.text) > 5))
async def add_base_channel_finish(message: types.Message):
    if message.from_user.id != MAIN_ADMIN_ID:
        return
    ch_input = message.text.strip()
    try:
        chat = await bot.get_chat(ch_input)
        channel_id = str(chat.id)
        set_base_channel(channel_id)
        await message.answer(f"✅ Baza kanal sozlandi: {chat.title}")
    except Exception as e:
        await message.answer(f"❌ Xatolik: {e}")

@dp.message_handler(lambda m: m.text == "➖ Baza kanalni olib tashlash")
async def remove_base_channel(message: types.Message):
    if message.from_user.id != MAIN_ADMIN_ID:
        return
    settings_col.delete_one({"key": "base_channel"})
    await message.answer("✅ Baza kanal o'chirildi.")

# ======================================
# Admin kino qo'shish (FSM orqali)
# ======================================

@dp.message_handler(lambda m: m.text == "🆕 Kino qo'shish")
async def admin_add_movie(message: types.Message):
    user_id = message.from_user.id
    is_admin = (user_id == MAIN_ADMIN_ID) or (admins_col.find_one({"user_id": user_id}) is not None)
    if not is_admin:
        await message.answer("Siz admin emassiz!")
        return
    await AddMovieState.waiting_for_movie.set()
    await message.answer("Kino/serialni video sifatida yuboring:", reply_markup=back_button())

@dp.message_handler(state=AddMovieState.waiting_for_movie, content_types=ContentTypes.ANY)
async def save_admin_movie(message: types.Message, state: FSMContext):
    if message.text == "🔙 Orqaga":
        await state.finish()
        await message.answer("Admin panel:", reply_markup=admin_menu())
        return

    if message.content_type != "video":
        await message.answer("Faqat video yuboring!")
        return

    user_id = message.from_user.id
    is_admin = (user_id == MAIN_ADMIN_ID) or (admins_col.find_one({"user_id": user_id}) is not None)
    if not is_admin:
        await message.answer("Siz admin emassiz!")
        await state.finish()
        return

    code = str(approved_videos_col.count_documents({}) + 1).zfill(4)
    title = message.caption or f"Kino #{code}"
    approved_videos_col.insert_one({
        "code": code,
        "title": title,
        "chat_id": message.chat.id,
        "message_id": message.message_id,
        "is_serial": False,
        "views": 0
    })
    base_channel = get_base_channel()
    if base_channel:
        try:
            await bot.copy_message(
                chat_id=base_channel,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
                caption=f"✅ {title}\n\nKod: {code}"
            )
        except Exception as e:
            print(f"Baza kanalga xato: {e}")
    await message.answer(f"✅ Kino qo'shildi!\nKod: {code}")
    await state.finish()
    await message.answer("Admin panel:", reply_markup=admin_menu())

# ======================================
# Serial qo'shish
# ======================================

@dp.message_handler(lambda m: m.text == "📺 Serial qo'shish")
async def start_add_serial(message: types.Message):
    user_id = message.from_user.id
    is_admin = (user_id == MAIN_ADMIN_ID) or (admins_col.find_one({"user_id": user_id}) is not None)
    if not is_admin:
        return
    await AddSerial.waiting_for_code.set()
    await message.answer("Serial kodini kiriting (masalan: S001):", reply_markup=back_button())

@dp.message_handler(state=AddSerial.waiting_for_code, content_types=ContentTypes.ANY)
async def serial_code(message: types.Message, state: FSMContext):
    if message.text == "🔙 Orqaga":
        await state.finish()
        await message.answer("Admin panel:", reply_markup=admin_menu())
        return
    await state.update_data(code=message.text.strip())
    await message.answer("Serial nomini kiriting:")
    await AddSerial.waiting_for_title.set()

@dp.message_handler(state=AddSerial.waiting_for_title, content_types=ContentTypes.ANY)
async def serial_title(message: types.Message, state: FSMContext):
    if message.text == "🔙 Orqaga":
        await state.finish()
        await message.answer("Admin panel:", reply_markup=admin_menu())
        return
    await state.update_data(title=message.text.strip())
    await message.answer("Endi serial qismlarini bitta-bitta yuboring. Barcha qismlarni yuborgach, '✅ Yakunlandi' deb yozing.")
    await state.update_data(parts=[])
    await AddSerial.waiting_for_parts.set()

@dp.message_handler(state=AddSerial.waiting_for_parts, content_types=ContentTypes.ANY)
async def handle_serial_parts_or_finish(message: types.Message, state: FSMContext):
    if message.text == "🔙 Orqaga":
        await state.finish()
        await message.answer("Admin panel:", reply_markup=admin_menu())
        return
    if message.content_type == "text":
        if message.text.strip() == "✅ Yakunlandi":
            data = await state.get_data()
            parts = data.get("parts", [])
            if not parts:
                await message.answer("Hech qanday qism yuborilmadi!")
                return
            code = data["code"]
            title = data["title"]
            approved_videos_col.insert_one({
                "code": code,
                "title": title,
                "is_serial": True,
                "parts": parts,
                "views": 0
            })
            base_channel = get_base_channel()
            if base_channel:
                try:
                    last_part = parts[-1]
                    await bot.copy_message(
                        chat_id=base_channel,
                        from_chat_id=last_part["chat_id"],
                        message_id=last_part["message_id"],
                        caption=f"✅ Serial qo'shildi!\n{title}\nKod: {code}"
                    )
                except Exception as e:
                    print(f"Baza kanalga serial xato: {e}")
            await message.answer(f"✅ Serial qo'shildi!\nKod: {code}")
            await state.finish()
            await message.answer("Admin panel:", reply_markup=admin_menu())
        else:
            await message.answer("Faqat '✅ Yakunlandi' deb yozing yoki video yuboring.")
    elif message.content_type == "video":
        data = await state.get_data()
        parts = data.get("parts", [])
        parts.append({
            "chat_id": message.chat.id,
            "message_id": message.message_id
        })
        await state.update_data(parts=parts)
        await message.answer(f"✅ Qism qo'shildi. Hozircha {len(parts)} ta qism.")
    else:
        await message.answer("Faqat video yoki '✅ Yakunlandi' matnini yuboring.")

# ======================================
# 🗑 KINO O'CHIRISH
# ======================================

@dp.message_handler(lambda m: m.text == "🗑 Kino o'chirish")
async def remove_video_start(message: types.Message):
    user_id = message.from_user.id
    is_admin = (user_id == MAIN_ADMIN_ID) or (admins_col.find_one({"user_id": user_id}) is not None)
    if not is_admin:
        return
    await RemoveVideoState.waiting_for_code.set()
    await message.answer("O'chirish uchun kino/serial kodini kiriting:", reply_markup=back_button())

@dp.message_handler(state=RemoveVideoState.waiting_for_code, content_types=ContentTypes.ANY)
async def remove_video_finish(message: types.Message, state: FSMContext):
    if message.text == "🔙 Orqaga":
        await state.finish()
        await message.answer("Admin panel:", reply_markup=admin_menu())
        return
    code = message.text.strip()
    video = approved_videos_col.find_one({"code": code})
    if not video:
        await message.answer("Bunday kodli kino topilmadi!")
        return

    approved_videos_col.delete_one({"code": code})

    base_channel = get_base_channel()
    if base_channel:
        try:
            if video.get("is_serial"):
                last_part = video["parts"][-1]
                await bot.delete_message(chat_id=base_channel, message_id=last_part["message_id"])
            else:
                await bot.delete_message(chat_id=base_channel, message_id=video["message_id"])
        except Exception as e:
            print(f"Baza kanaldan o'chirishda xato: {e}")

    await message.answer(f"✅ Kino/serial (Kod: {code}) o'chirildi!")
    await state.finish()
    await message.answer("Admin panel:", reply_markup=admin_menu())

# ======================================
# Xabar yuborish (broadcast)
# ======================================

@dp.message_handler(lambda m: m.text == "📢 Xabar yuborish")
async def broadcast_start(message: types.Message):
    user_id = message.from_user.id
    is_admin = (user_id == MAIN_ADMIN_ID) or (admins_col.find_one({"user_id": user_id}) is not None)
    if not is_admin:
        return
    await BroadcastMessage.waiting_for_message.set()
    await message.answer("Xabarni yozing (matn, video, rasm — istalgan formatda):", reply_markup=back_button())

@dp.message_handler(state=BroadcastMessage.waiting_for_message, content_types=ContentTypes.ANY)
async def do_broadcast(message: types.Message, state: FSMContext):
    if message.text == "🔙 Orqaga":
        await state.finish()
        await message.answer("Admin panel:", reply_markup=admin_menu())
        return
    users = users_col.find({})
    sent = 0
    for user in users:
        try:
            await bot.copy_message(
                chat_id=user["user_id"],
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )
            sent += 1
        except Exception as e:
            print(f"Broadcast xato: {e}")
    await message.answer(f"✅ Xabar {sent} foydalanuvchiga yuborildi.")
    await state.finish()
    await message.answer("Admin panel:", reply_markup=admin_menu())

# ======================================
# Majburiy kanallar
# ======================================

@dp.message_handler(lambda m: m.text == "🔍 Majburiy kanallar")
async def manage_channels(message: types.Message):
    user_id = message.from_user.id
    is_admin = (user_id == MAIN_ADMIN_ID) or (admins_col.find_one({"user_id": user_id}) is not None)
    if not is_admin:
        return
    kb = [
        [KeyboardButton(text="➕ Kanal qo'shish")],
        [KeyboardButton(text="➖ Kanalni olib tashlash")],
        [KeyboardButton(text="📋 Ro'yxat"), KeyboardButton(text="🔙 Orqaga")]
    ]
    await message.answer("Kanallar boshqaruvi:", reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))

@dp.message_handler(lambda m: m.text == "➕ Kanal qo'shish")
async def add_channel_start(message: types.Message):
    user_id = message.from_user.id
    is_admin = (user_id == MAIN_ADMIN_ID) or (admins_col.find_one({"user_id": user_id}) is not None)
    if not is_admin:
        return
    await AddChannel.waiting_for_channel.set()
    await message.answer("Kanal linkini yoki ID sini yuboring (masalan: @mychannel yoki -1001234567890):")

@dp.message_handler(state=AddChannel.waiting_for_channel, content_types=ContentTypes.ANY)
async def add_channel_finish(message: types.Message, state: FSMContext):
    if message.text == "🔙 Orqaga":
        await state.finish()
        await manage_channels(message)
        return
    user_id = message.from_user.id
    is_admin = (user_id == MAIN_ADMIN_ID) or (admins_col.find_one({"user_id": user_id}) is not None)
    if not is_admin:
        return
    ch_input = message.text.strip()
    try:
        chat = await bot.get_chat(ch_input)
        channel_id = str(chat.id)
        title = chat.title or ch_input
        link = f"https://t.me/{chat.username}" if chat.username else ch_input  # ✅ tuzatildi!
        channels_col.update_one(
            {"channel_id": channel_id},
            {"$set": {"title": title, "link": link}},
            upsert=True
        )
        await message.answer(f"✅ Kanal qo'shildi: {title}")
    except Exception as e:
        await message.answer(f"❌ Xatolik: {e}")
    await state.finish()
    await manage_channels(message)

@dp.message_handler(lambda m: m.text == "📋 Ro'yxat")
async def list_channels(message: types.Message):
    user_id = message.from_user.id
    is_admin = (user_id == MAIN_ADMIN_ID) or (admins_col.find_one({"user_id": user_id}) is not None)
    if not is_admin:
        return
    channels = list(channels_col.find({}))
    if not channels:
        await message.answer("Hech qanday majburiy kanal qo'shilmagan.")
        return
    text = "🔹 Majburiy kanallar ro'yxati:\n\n"
    for ch in channels:
        title = ch.get('title', 'Noma\'lum')
        link = ch.get('link', ch['channel_id'])
        text += f"• {title} — {link}\n"
    await message.answer(text)

@dp.message_handler(lambda m: m.text == "➖ Kanalni olib tashlash")
async def remove_channel_start(message: types.Message):
    user_id = message.from_user.id
    is_admin = (user_id == MAIN_ADMIN_ID) or (admins_col.find_one({"user_id": user_id}) is not None)
    if not is_admin:
        return
    channels = list(channels_col.find({}))
    if not channels:
        await message.answer("Hech qanday kanal yo'q.")
        return
    btns = []
    for ch in channels:
        title = ch.get('title', ch['channel_id'])
        btns.append([InlineKeyboardButton(text=f"❌ {title}", callback_data=f"del_channel_{ch['channel_id']}")])
    btns.append([InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="cancel")])
    await message.answer("O'chirmoqchi bo'lgan kanalni tanlang:", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query_handler(lambda c: c.data.startswith("del_channel_"))
async def delete_channel(callback: types.CallbackQuery):
    channel_id = callback.data.replace("del_channel_", "")
    result = channels_col.delete_one({"channel_id": channel_id})
    if result.deleted_count:
        await callback.message.edit_text("✅ Kanal o'chirildi.")
    else:
        await callback.message.edit_text("❌ Xatolik yoki kanal topilmadi.")

@dp.callback_query_handler(lambda c: c.data == "cancel")
async def cancel_delete(callback: types.CallbackQuery):
    await callback.message.edit_text("Bekor qilindi.")
    await manage_channels(callback.message)

# ======================================
# Admin boshqaruvi
# ======================================

@dp.message_handler(lambda m: m.text == "👑 Admin qo'shish")
async def add_admin_start(message: types.Message):
    if message.from_user.id != MAIN_ADMIN_ID:
        return
    await AddAdmin.waiting_for_id.set()
    await message.answer("Yangi admin ID raqamini yuboring:")

@dp.message_handler(state=AddAdmin.waiting_for_id, content_types=ContentTypes.ANY)
async def add_admin_finish(message: types.Message, state: FSMContext):
    if message.text == "🔙 Orqaga":
        await state.finish()
        await message.answer("Admin panel:", reply_markup=admin_menu())
        return
    try:
        new_admin_id = int(message.text.strip())
        if new_admin_id == MAIN_ADMIN_ID:
            await message.answer("❌ Bu ID asosiy admin!")
        elif admins_col.find_one({"user_id": new_admin_id}):
            await message.answer("❌ Bu foydalanuvchi allaqachon admin!")
        else:
            admins_col.insert_one({"user_id": new_admin_id})
            await message.answer(f"✅ Foydalanuvchi {new_admin_id} admin qilindi!")
    except ValueError:
        await message.answer("❌ ID faqat raqam bo'lishi kerak. Qaytadan urinib ko'ring.")
    await state.finish()
    await message.answer("Admin panel:", reply_markup=admin_menu())

@dp.message_handler(lambda m: m.text == "🗑 Admin o'chirish")
async def remove_admin_start(message: types.Message):
    if message.from_user.id != MAIN_ADMIN_ID:
        return
    await RemoveAdmin.waiting_for_id.set()
    await message.answer("O'chiriladigan admin ID raqamini yuboring:")

@dp.message_handler(state=RemoveAdmin.waiting_for_id, content_types=ContentTypes.ANY)
async def remove_admin_finish(message: types.Message, state: FSMContext):
    if message.text == "🔙 Orqaga":
        await state.finish()
        await message.answer("Admin panel:", reply_markup=admin_menu())
        return
    try:
        admin_id_to_remove = int(message.text.strip())
        if admin_id_to_remove == MAIN_ADMIN_ID:
            await message.answer("❌ Asosiy adminni o'chirib bo'lmaydi!")
        else:
            result = admins_col.delete_one({"user_id": admin_id_to_remove})
            if result.deleted_count > 0:
                await message.answer(f"✅ Foydalanuvchi {admin_id_to_remove} adminlikdan chiqarildi.")
            else:
                await message.answer("❌ Bunday admin topilmadi.")
    except ValueError:
        await message.answer("❌ ID faqat raqam bo'lishi kerak.")
    await state.finish()
    await message.answer("Admin panel:", reply_markup=admin_menu())

@dp.message_handler(lambda m: m.text == "📋 Adminlar")
async def list_admins(message: types.Message):
    if message.from_user.id != MAIN_ADMIN_ID:
        return
    admins = admins_col.find({})
    text = "👑 Qo'shimcha adminlar:\n\n"
    count = 0
    for admin in admins:
        text += f"• {admin['user_id']}\n"
        count += 1
    if count == 0:
        text = "Hozircha qo'shimcha adminlar yo'q."
    await message.answer(text)

# ======================================
# Umumiy "Orqaga"
# ======================================

@dp.message_handler(lambda m: m.text == "🔙 Orqaga")
async def go_back(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state:
        await state.finish()
    # ⚠️ Admin paneldan chiqish uchun — har doim asosiy menyu!
    await message.answer("Asosiy menyu:", reply_markup=main_menu())

# ======================================
# Flask + Aiogram
# ======================================

flask_app = Flask(__name__)

@flask_app.route('/health')
def health():
    return "OK", 200

def start_bot():
    import asyncio
    import logging
    logging.basicConfig(level=logging.INFO)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    from aiogram import executor
    try:
        loop.run_until_complete(executor.start_polling(dp, skip_updates=True))
    except Exception as e:
        print(f"Aiogram xatosi: {e}")

if __name__ == "__main__":
    threading.Thread(target=start_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)
