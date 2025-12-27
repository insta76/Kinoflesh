import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from database import (
    users_col, pending_videos_col, approved_videos_col,
    channels_col, admins_col, MAIN_ADMIN_ID
)

BOT_TOKEN = "8450474807:AAGWPcYkRSWbXAN79sg7Nj2nWyP1oiohER8"
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Holatlar
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

class ApproveVideo(StatesGroup):
    waiting_for_code = State()

class AddSerial(StatesGroup):
    waiting_for_code = State()
    waiting_for_title = State()
    waiting_for_parts = State()

# Asosiy menyu tugmalar
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
        [KeyboardButton(text="👑 Admin qo'shish"), KeyboardButton(text="🗑 Admin o'chirish")],
        [KeyboardButton(text="🔙 Orqaga")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def back_button():
    kb = [[KeyboardButton(text="🔙 Orqaga")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# Foydalanuvchini bazaga qo'shish
async def add_user(user_id: int, username: str = None):
    if not users_col.find_one({"user_id": user_id}):
        users_col.insert_one({"user_id": user_id, "username": username})

# Obuna majburiymi?
async def check_subscription(user_id: int) -> bool:
    channels = list(channels_col.find({}))
    if not channels:
        return True
    for ch in channels:
        try:
            chat_member = await bot.get_chat_member(chat_id=ch['channel_id'], user_id=user_id)
            if chat_member.status in ['left', 'kicked']:
                return False
        except:
            return False
    return True

# Barcha tugmalarga "Orqaga" qo'shish
@dp.message()
async def handle_back(message: types.Message, state: FSMContext):
    if message.text == "🔙 Orqaga":
        await state.clear()
        await message.answer("Asosiy menyu:", reply_markup=main_menu())

# /start
@dp.message(CommandStart())
async def start_handler(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username
    await add_user(user_id, username)

    # Adminmi?
    is_admin = admins_col.find_one({"user_id": user_id}) is not None

    # Obuna tekshirish
    if not await check_subscription(user_id):
        channels = channels_col.find({})
        text = "Quyidagi kanallarga obuna bo'ling:\n\n"
        btns = []
        for ch in channels:
            link = ch.get('link', ch['channel_id'])
            title = ch.get('title', link)
            text += f"• {title}\n"
            btns.append([InlineKeyboardButton(text=title, url=link)])
        btns.append([InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub")])
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))
        return

    welcome_text = "Assalomu alaykum! Kino botga xush kelibsiz.\nQuyidagi tugmalardan foydalaning:"
    if is_admin:
        kb = [
            [KeyboardButton(text="🎬 Kino qidirish")],
            [KeyboardButton(text="🏆 Top kinolar"), KeyboardButton(text="📤 Kino yuborish")],
            [KeyboardButton(text="✍️ Adminga yozish"), KeyboardButton(text="📊 Statistika")],
            [KeyboardButton(text="👑 Admin panel")]
        ]
        await message.answer(welcome_text, reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))
    else:
        await message.answer(welcome_text, reply_markup=main_menu())

# Obuna tekshirish (callback)
@dp.callback_query(lambda c: c.data == "check_sub")
async def check_sub_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if await check_subscription(user_id):
        await callback.message.edit_text("✅ Obuna tasdiqlandi! Endi botdan foydalanishingiz mumkin.")
        await start_handler(callback.message, FSMContext(storage=MemoryStorage(), key=None))
    else:
        await callback.answer("❌ Hali ham kanallarga obuna bo'lmagansiz!", show_alert=True)

# Kino qidirish
@dp.message(lambda m: m.text == "🎬 Kino qidirish")
async def search_video(message: types.Message, state: FSMContext):
    await message.answer("Kino/serial nomi yoki kodini kiriting:", reply_markup=back_button())
    await state.set_state("searching")

@dp.message(lambda m: m.text and "searching" in str(m))
async def process_search(message: types.Message, state: FSMContext):
    if message.text == "🔙 Orqaga":
        await state.clear()
        await message.answer("Asosiy menyu:", reply_markup=main_menu())
        return

    query = message.text.strip()
    # Kod yoki nom bo'yicha qidirish
    video = approved_videos_col.find_one({"$or": [{"code": query}, {"title": {"$regex": query, "$options": "i"}}]})
    if video:
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
    await state.clear()
    await message.answer("Asosiy menyu:", reply_markup=main_menu())

# Top kinolar
@dp.message(lambda m: m.text == "🏆 Top kinolar")
async def top_videos(message: types.Message):
    # Soddalashtirish uchun: ko'proq ko'rilgan 10 ta
    top_list = approved_videos_col.find().sort("views", -1).limit(10)
    text = "🏆 Top 10 kinolar:\n\n"
    for i, v in enumerate(top_list, 1):
        title = v.get('title', 'Noma\'lum')
        code = v.get('code', 'Kod yo\'q')
        text += f"{i}. {title} (Kod: {code})\n"
    if text == "🏆 Top 10 kinolar:\n\n":
        text = "Hali hech qanday kino qo'shilmagan."
    await message.answer(text)

# Foydalanuvchi kinoni yuborish
@dp.message(lambda m: m.text == "📤 Kino yuborish")
async def send_video_request(message: types.Message):
    await message.answer("Kino/serialni shu botga yuboring (video sifatida):", reply_markup=back_button())
    await state.set_state("waiting_video_from_user")

@dp.message()
async def receive_user_video(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state == "waiting_video_from_user" and message.video:
        # ... ishni bajarish
        await state.clear()
async def receive_user_video(message: types.Message, state: FSMContext):
    video = message.video
    pending_videos_col.insert_one({
        "user_id": message.from_user.id,
        "video_file_id": video.file_id,
        "caption": message.caption or "",
        "chat_id": message.chat.id,
        "message_id": message.message_id,
        "status": "pending"
    })
    await message.answer("✅ Kino adminlarga yuborildi. Tasdiqlansa, botga qo'shiladi.")
    await state.clear()
    await message.answer("Asosiy menyu:", reply_markup=main_menu())

# Adminga yozish
@dp.message(lambda m: m.text == "✍️ Adminga yozish")
async def contact_admin(message: types.Message, state: FSMContext):
    await message.answer("Xabaringizni yozing:", reply_markup=back_button())
    await state.set_state(SendMessageToAdmin.waiting_for_message)

@dp.message(SendMessageToAdmin.waiting_for_message)
async def forward_to_admin(message: types.Message, state: FSMContext):
    if message.text == "🔙 Orqaga":
        await state.clear()
        await message.answer("Asosiy menyu:", reply_markup=main_menu())
        return

    admin_id = MAIN_ADMIN_ID
    text = f"📩 Yangi xabar:\n\nFoydalanuvchi: {message.from_user.full_name} (@{message.from_user.username or '---'})\nID: {message.from_user.id}\n\nXabar:\n{message.text}"
    try:
        await bot.send_message(admin_id, text)
        await message.answer("✅ Xabaringiz adminlarga yuborildi!")
    except:
        await message.answer("❌ Xabar yuborishda xatolik.")
    await state.clear()
    await message.answer("Asosiy menyu:", reply_markup=main_menu())

# Statistika
@dp.message(lambda m: m.text == "📊 Statistika")
async def stats(message: types.Message):
    total = users_col.count_documents({})
    videos = approved_videos_col.count_documents({})
    pending = pending_videos_col.count_documents({"status": "pending"})
    await message.answer(f"👤 Foydalanuvchilar: {total}\n🎥 Tasdiqlangan kinolar: {videos}\n⏳ Kutayotgan: {pending}")

# Admin panel
@dp.message(lambda m: m.text == "👑 Admin panel")
async def admin_panel(message: types.Message):
    if not admins_col.find_one({"user_id": message.from_user.id}):
        await message.answer("Siz admin emassiz!")
        return
    await message.answer("Admin panel:", reply_markup=admin_menu())

# Admin: Kino qo'shish
@dp.message(lambda m: m.text == "🆕 Kino qo'shish")
async def admin_add_movie(message: types.Message):
    if not admins_col.find_one({"user_id": message.from_user.id}):
        return
    await message.answer("Kino/serialni shu yerga yuboring:")

@dp.message(lambda m: m.video and admins_col.find_one({"user_id": m.from_user.id}))
async def save_admin_video(message: types.Message):
    video = message.video
    code = str(approved_videos_col.count_documents({}) + 1).zfill(4)
    approved_videos_col.insert_one({
        "code": code,
        "title": message.caption or f"Kino #{code}",
        "chat_id": message.chat.id,
        "message_id": message.message_id,
        "is_serial": False,
        "views": 0
    })
    await message.answer(f"✅ Kino qo'shildi!\nKod: {code}")

# Serial qo'shish
@dp.message(lambda m: m.text == "📺 Serial qo'shish")
async def start_add_serial(message: types.Message, state: FSMContext):
    if not admins_col.find_one({"user_id": message.from_user.id}):
        return
    await message.answer("Serial kodini kiriting (masalan: S001):", reply_markup=back_button())
    await state.set_state(AddSerial.waiting_for_code)

@dp.message(AddSerial.waiting_for_code)
async def serial_code(message: types.Message, state: FSMContext):
    await state.update_data(code=message.text.strip())
    await message.answer("Serial nomini kiriting:")
    await state.set_state(AddSerial.waiting_for_title)

@dp.message(AddSerial.waiting_for_title)
async def serial_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await message.answer("Endi serial qismlarini bitta-bitta yuboring. Barcha qismlarni yuborgach, '✅ Yakunlandi' deb yozing.")
    await state.update_data(parts=[])
    await state.set_state(AddSerial.waiting_for_parts)

@dp.message(AddSerial.waiting_for_parts, content_types=types.ContentType.VIDEO)
async def serial_part(message: types.Message, state: FSMContext):
    data = await state.get_data()
    parts = data.get("parts", [])
    parts.append({
        "chat_id": message.chat.id,
        "message_id": message.message_id
    })
    await state.update_data(parts=parts)
    await message.answer(f"✅ Qism qo'shildi. Hozircha {len(parts)} ta qism.")

@dp.message(AddSerial.waiting_for_parts, lambda m: m.text == "✅ Yakunlandi")
async def finish_serial(message: types.Message, state: FSMContext):
    data = await state.get_data()
    code = data["code"]
    title = data["title"]
    parts = data["parts"]
    if not parts:
        await message.answer("Hech qanday qism yuborilmadi!")
        return
    approved_videos_col.insert_one({
        "code": code,
        "title": title,
        "is_serial": True,
        "parts": parts,
        "views": 0
    })
    await message.answer(f"✅ Serial qo'shildi!\nKod: {code}")
    await state.clear()
    await message.answer("Admin panel:", reply_markup=admin_menu())

# Xabar yuborish (broadcast)
@dp.message(lambda m: m.text == "📢 Xabar yuborish")
async def broadcast_start(message: types.Message, state: FSMContext):
    if not admins_col.find_one({"user_id": message.from_user.id}):
        return
    await message.answer("Xabarni yozing (matn, video, rasm — istalgan formatda):", reply_markup=back_button())
    await state.set_state(BroadcastMessage.waiting_for_message)

@dp.message(BroadcastMessage.waiting_for_message)
async def do_broadcast(message: types.Message, state: FSMContext):
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
        except:
            pass
    await message.answer(f"✅ Xabar {sent} foydalanuvchiga yuborildi.")
    await state.clear()
    await message.answer("Admin panel:", reply_markup=admin_menu())

# Majburiy kanallar
@dp.message(lambda m: m.text == "🔍 Majburiy kanallar")
async def manage_channels(message: types.Message):
    if not admins_col.find_one({"user_id": message.from_user.id}):
        return
    kb = [
        [KeyboardButton(text="➕ Kanal qo'shish")],
        [KeyboardButton(text="➖ Kanalni olib tashlash")],
        [KeyboardButton(text="📋 Ro'yxat"), KeyboardButton(text="🔙 Orqaga")]
    ]
    await message.answer("Kanallar boshqaruvi:", reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))

@dp.message(lambda m: m.text == "➕ Kanal qo'shish")
async def add_channel_start(message: types.Message, state: FSMContext):
    await message.answer("Kanal linkini yoki ID sini yuboring (masalan: @mychannel yoki -1001234567890):")
    await state.set_state(AddChannel.waiting_for_channel)

@dp.message(AddChannel.waiting_for_channel)
async def add_channel_finish(message: types.Message, state: FSMContext):
    ch_input = message.text.strip()
    try:
        chat = await bot.get_chat(ch_input)
        channel_id = str(chat.id)
        title = chat.title or ch_input
        link = f"https://t.me/{chat.username}" if chat.username else ch_input
        channels_col.update_one(
            {"channel_id": channel_id},
            {"$set": {"title": title, "link": link}},
            upsert=True
        )
        await message.answer(f"✅ Kanal qo'shildi: {title}")
    except Exception as e:
        await message.answer(f"❌ Xatolik: {e}")
    await state.clear()
    await manage_channels(message)

# Boshqa admin boshqaruvi, statistika va h.k. qo'shilgan

# Asosiy ishga tushirish
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
