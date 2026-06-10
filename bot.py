import logging
import json
import re
import time
from datetime import datetime
from groq import Groq
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler, ApplicationBuilder,
    ContextTypes, filters
)
import fitz  # PyMuPDF

# ==================== SOZLAMALAR ====================
BOT_TOKEN = "8556020862:AAHURupYErvh7aasPxlfwWv73pgM8fW9e_Q"
GROQ_API_KEY = "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"
ADMIN_ID = 0  # Sizning Telegram ID ingiz — keyinroq o'zgartiring
ADMIN_USERNAME = "@your_admin"

CHANNELS = [
    {"name": "Kanal 1", "url": "https://t.me/your_channel_1", "id": "@your_channel_1"},
    {"name": "Kanal 2", "url": "https://t.me/your_channel_2", "id": "@your_channel_2"},
    {"name": "Kanal 3", "url": "https://t.me/your_channel_3", "id": "@your_channel_3"},
]

groq_client = Groq(api_key=GROQ_API_KEY)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==================== MA'LUMOTLAR ====================
vip_users = set()        # VIP foydalanuvchilar
user_data = {}           # Statistika
quiz_sessions = {}       # Aktiv testlar
question_banks = {}      # Oddiy foydalanuvchilar savollar to'plami

def get_user(user_id):
    if user_id not in user_data:
        user_data[user_id] = {
            "total": 0, "correct": 0,
            "streak": 0, "last_date": "", "record_time": 0
        }
    return user_data[user_id]

def is_vip(user_id):
    return user_id in vip_users or user_id == ADMIN_ID

# ==================== KANAL TEKSHIRUV ====================
async def check_subscription(user_id, bot):
    for ch in CHANNELS:
        if "your_channel" in ch["id"]:
            return True
        try:
            member = await bot.get_chat_member(ch["id"], user_id)
            if member.status in ["left", "kicked", "banned"]:
                return False
        except:
            pass
    return True

async def show_subscription(update, context):
    keyboard = []
    for ch in CHANNELS:
        keyboard.append([InlineKeyboardButton(f"📢 {ch['name']}", url=ch['url'])])
    keyboard.append([InlineKeyboardButton("✅ Obuna bo'ldim", callback_data="check_sub")])
    text = (
        "🔐 *Botdan foydalanish uchun*\n\n"
        "Quyidagi kanallarga obuna bo'ling:\n\n" +
        "\n".join(f"{i+1}. {ch['name']}" for i, ch in enumerate(CHANNELS)) +
        "\n\nObuna bo'lgach tugmani bosing!"
    )
    if update.message:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# ==================== BOSH MENYU ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_user(user.id)

    subscribed = await check_subscription(user.id, context.bot)
    if not subscribed:
        await show_subscription(update, context)
        return

    vip = is_vip(user.id)
    badge = "👑 VIP" if vip else "👤"

    keyboard = []

    if vip:
        keyboard.append([
            InlineKeyboardButton("📄 PDF dan quiz", callback_data="mode_pdf"),
            InlineKeyboardButton("🤖 AI quiz", callback_data="mode_ai")
        ])

    keyboard.append([
        InlineKeyboardButton("✏️ Savol qo'shish", callback_data="mode_add_question"),
        InlineKeyboardButton("🎮 Test ishlash", callback_data="mode_play")
    ])
    keyboard.append([
        InlineKeyboardButton("📊 Statistika", callback_data="stats"),
        InlineKeyboardButton("🏆 Reyting", callback_data="leaderboard")
    ])
    keyboard.append([
        InlineKeyboardButton("❓ Yordam", callback_data="help"),
        InlineKeyboardButton("👨‍💼 Admin", callback_data="contact_admin")
    ])

    text = (
        f"👋 Salom, *{user.first_name}* {badge}!\n\n"
        "🤖 *Quiz Genius Bot*\n\n"
    )
    if vip:
        text += (
            "👑 *VIP imkoniyatlaringiz:*\n"
            "• PDF yuklash → tayyor savollarni quiz qilish\n"
            "• AI orqali savol tuzish\n"
            "• Savol qo'shish\n\n"
        )
    else:
        text += (
            "📌 *Imkoniyatlaringiz:*\n"
            "• Savol + javob qo'shib quiz tuzish\n"
            "• Tayyor testlarni ishlash\n\n"
        )
    text += "👇 Tanlang:"

    if update.message:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# ==================== ADMIN BUYRUQLAR ====================
async def add_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Faqat admin uchun!")
        return
    if not context.args:
        await update.message.reply_text("Ishlatish: /addvip @username yoki /addvip 123456789")
        return
    target = context.args[0].replace("@", "")
    try:
        uid = int(target)
        vip_users.add(uid)
        await update.message.reply_text(f"✅ {uid} VIP qilindi!")
    except:
        await update.message.reply_text(f"✅ @{target} VIP qilindi! (Ular botga /start yuborganida kuchga kiradi)")

async def remove_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Faqat admin uchun!")
        return
    if not context.args:
        await update.message.reply_text("Ishlatish: /removevip 123456789")
        return
    try:
        uid = int(context.args[0])
        vip_users.discard(uid)
        await update.message.reply_text(f"✅ {uid} VIP dan chiqarildi!")
    except:
        await update.message.reply_text("❌ ID noto'g'ri!")

async def vip_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not vip_users:
        await update.message.reply_text("VIP foydalanuvchilar yo'q!")
        return
    text = "👑 *VIP foydalanuvchilar:*\n\n"
    for uid in vip_users:
        text += f"• `{uid}`\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def get_my_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Sizning ID: `{update.effective_user.id}`", parse_mode="Markdown")

# ==================== PDF REJIM ====================
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not is_vip(user.id):
        await update.message.reply_text("❌ PDF yuklash faqat VIP foydalanuvchilar uchun!\n\nSavol qo'shish uchun /start bosing.")
        return

    doc = update.message.document
    if not doc.file_name.lower().endswith('.pdf'):
        await update.message.reply_text("⚠️ Faqat *PDF* fayl yuboring!", parse_mode="Markdown")
        return

    msg = await update.message.reply_text("⏳ PDF o'qilmoqda...")
    try:
        file = await context.bot.get_file(doc.file_id)
        pdf_path = f"/tmp/quiz_{user.id}.pdf"
        await file.download_to_drive(pdf_path)

        pdf_doc = fitz.open(pdf_path)
        text = ""
        for page in pdf_doc:
            text += page.get_text()
        pdf_doc.close()

        if len(text.strip()) < 50:
            await msg.edit_text("❌ PDF da matn topilmadi!")
            return

        context.user_data['pdf_text'] = text
        context.user_data['pdf_mode'] = 'extract'  # PDFdan tayyor savollarni olish
        context.user_data['state'] = 'waiting_quiz_name'

        await msg.edit_text(
            "✅ *PDF yuklandi!*\n\n"
            "✏️ Bu testga *nom bering:*\n"
            "_Masalan: Biologiya 8-sinf, IELTS Grammar..._",
            parse_mode="Markdown"
        )
    except Exception as e:
        await msg.edit_text(f"❌ Xatolik: {str(e)}")

# ==================== SAVOL QO'SHISH (ODDIY) ====================
async def show_add_question(query, context, user_id):
    if user_id not in question_banks:
        question_banks[user_id] = []

    count = len(question_banks[user_id])
    keyboard = [
        [InlineKeyboardButton("➕ Savol qo'shish", callback_data="add_new_q")],
    ]
    if count >= 5:
        keyboard.append([InlineKeyboardButton(f"🎮 Testni boshlash ({count} ta savol)", callback_data="start_bank_quiz")])
    keyboard.append([InlineKeyboardButton("🗑 Savollarni tozalash", callback_data="clear_bank")])
    keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data="back_home")])

    await query.edit_message_text(
        f"✏️ *Savol qo'shish*\n\n"
        f"📝 Hozir: *{count} ta savol* to'plangan\n\n"
        f"Savol qo'shib, keyin test tuzasiz!\n"
        f"_(Minimum 5 ta savol kerak)_",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# ==================== MATN XABARLAR ====================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text

    if text.startswith('/'):
        return

    state = context.user_data.get('state', '')

    # Quiz nomi
    if state == 'waiting_quiz_name':
        context.user_data['quiz_name'] = text
        context.user_data['state'] = 'waiting_count'
        pdf_mode = context.user_data.get('pdf_mode', 'extract')

        if pdf_mode == 'ai':
            label = "🤖 AI savol tuzadi"
        else:
            label = "📄 PDFdan savollar olinadi"

        keyboard = [
            [InlineKeyboardButton("20 ta 📝", callback_data="count_20"),
             InlineKeyboardButton("30 ta 📝", callback_data="count_30")],
            [InlineKeyboardButton("50 ta 📝", callback_data="count_50"),
             InlineKeyboardButton("100 ta 📝", callback_data="count_100")],
            [InlineKeyboardButton("🔙 Bekor", callback_data="back_home")]
        ]
        await update.message.reply_text(
            f"✅ Test nomi: *{text}*\n"
            f"_{label}_\n\n"
            f"📊 *Nechta savol?*",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return

    # AI rejim: matn kutilmoqda
    if state == 'waiting_ai_text':
        context.user_data['pdf_text'] = text
        context.user_data['state'] = 'waiting_quiz_name'
        context.user_data['pdf_mode'] = 'ai'
        await update.message.reply_text(
            "✅ Matn qabul qilindi!\n\n"
            "✏️ Testga *nom bering:*",
            parse_mode="Markdown"
        )
        return

    # Savol qo'shish jarayoni
    if state == 'adding_question':
        context.user_data['new_q'] = {'q': text}
        context.user_data['state'] = 'adding_correct'
        await update.message.reply_text(
            f"❓ Savol: _{text}_\n\n"
            "✅ *To'g'ri javobni yozing:*",
            parse_mode="Markdown"
        )
        return

    if state == 'adding_correct':
        context.user_data['new_q']['correct'] = text
        context.user_data['new_q']['opts'] = [text]
        context.user_data['state'] = 'adding_wrong1'
        await update.message.reply_text(
            f"✅ To'g'ri javob: _{text}_\n\n"
            "❌ *1-noto'g'ri javobni yozing:*",
            parse_mode="Markdown"
        )
        return

    if state == 'adding_wrong1':
        context.user_data['new_q']['opts'].append(text)
        context.user_data['state'] = 'adding_wrong2'
        await update.message.reply_text(
            "❌ *2-noto'g'ri javobni yozing:*",
            parse_mode="Markdown"
        )
        return

    if state == 'adding_wrong2':
        context.user_data['new_q']['opts'].append(text)
        context.user_data['state'] = 'adding_wrong3'
        await update.message.reply_text(
            "❌ *3-noto'g'ri javobni yozing:*",
            parse_mode="Markdown"
        )
        return

    if state == 'adding_wrong3':
        context.user_data['new_q']['opts'].append(text)
        context.user_data['state'] = ''

        # Savolni saqlash
        import random
        q_data = context.user_data['new_q']
        opts = q_data['opts'].copy()
        random.shuffle(opts)
        correct_idx = opts.index(q_data['correct'])

        if user.id not in question_banks:
            question_banks[user.id] = []

        question_banks[user.id].append({
            'q': q_data['q'],
            'opts': opts,
            'ans': correct_idx
        })

        count = len(question_banks[user.id])
        keyboard = [
            [InlineKeyboardButton("➕ Yana savol qo'shish", callback_data="add_new_q")],
        ]
        if count >= 5:
            keyboard.append([InlineKeyboardButton(f"🎮 Testni boshlash ({count} ta)", callback_data="start_bank_quiz")])
        keyboard.append([InlineKeyboardButton("🏠 Bosh menyu", callback_data="back_home")])

        await update.message.reply_text(
            f"✅ *Savol saqlandi!*\n\n"
            f"📝 Jami: *{count} ta savol*\n\n"
            f"_{q_data['q']}_",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return

    # Bank quiz nomi
    if state == 'waiting_bank_name':
        context.user_data['state'] = ''
        questions = question_banks.get(user.id, [])
        if not questions:
            await update.message.reply_text("❌ Savollar topilmadi!")
            return
        await update.message.reply_text(f"🎮 *{text}* — test boshlanmoqda!", parse_mode="Markdown")
        await start_quiz(user.id, questions, text, context, update.message.chat_id)
        return

    # Admin murojaat
    if state == 'waiting_admin_msg':
        context.user_data['state'] = ''
        if ADMIN_ID:
            try:
                await context.bot.send_message(
                    ADMIN_ID,
                    f"📨 *Yangi murojaat:*\n\n"
                    f"👤 {user.first_name} (@{user.username})\n"
                    f"🆔 `{user.id}`\n\n"
                    f"💬 {text}",
                    parse_mode="Markdown"
                )
            except:
                pass
        await update.message.reply_text(
            "✅ Xabaringiz adminga yuborildi!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Bosh menyu", callback_data="back_home")]])
        )
        return

    await update.message.reply_text("📎 /start bosing yoki PDF yuboring.")

# ==================== SAVOLLARNI PDFdan OLISH ====================
def extract_questions_from_pdf(text, count):
    """PDFdagi tayyor savollarni olib, quiz formatiga o'tkazadi"""
    prompt = (
        f"Quyidagi matnda tayyor test savollari va javoblari bor. "
        f"Ularni o'qib, AYNAN {count} tasini JSON formatga o'tkazib ber. "
        f"Agar {count} tadan kam savol bo'lsa, barchasini ber. "
        f"FAQAT JSON, boshqa hech narsa yozma:\n"
        f'[{{"q":"Savol matni?","opts":["To\'g\'ri javob","Noto\'g\'ri 1","Noto\'g\'ri 2","Noto\'g\'ri 3"],"ans":0}}]\n'
        f'"ans" = to\'g\'ri javob indeksi (0,1,2,3)\n\n'
        f"Matn:\n{text[:12000]}"
    )
    response = groq_client.chat.completions.create(
        model="llama3-70b-8192",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=6000,
        temperature=0.1
    )
    raw = response.choices[0].message.content
    raw = re.sub(r'```json|```', '', raw).strip()
    start = raw.find('[')
    end = raw.rfind(']')
    questions = json.loads(raw[start:end+1])
    return questions[:count]

def generate_ai_questions(text, count):
    """AI o'zi savol tuzadi"""
    prompt = (
        f"Quyidagi matn asosida AYNAN {count} ta yangi test savoli tuz. "
        f"Har biri 4 ta variant. Bitta to'g'ri javob. "
        f"FAQAT JSON:\n"
        f'[{{"q":"Savol?","opts":["A","B","C","D"],"ans":0}}]\n\n'
        f"Matn:\n{text[:10000]}"
    )
    response = groq_client.chat.completions.create(
        model="llama3-70b-8192",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=6000,
        temperature=0.3
    )
    raw = response.choices[0].message.content
    raw = re.sub(r'```json|```', '', raw).strip()
    start = raw.find('[')
    end = raw.rfind(']')
    questions = json.loads(raw[start:end+1])
    return questions[:count]

# ==================== QUIZ ====================
async def start_quiz(user_id, questions, quiz_name, context, chat_id):
    quiz_sessions[user_id] = {
        "questions": questions,
        "current": 0,
        "correct": 0,
        "wrong": 0,
        "skip": 0,
        "name": quiz_name,
        "start_time": time.time(),
    }
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"🎯 *{quiz_name}*\n\n"
            f"📝 Jami: *{len(questions)} ta savol*\n\n"
            f"Boshlayapmiz! 🚀"
        ),
        parse_mode="Markdown"
    )
    await send_question(user_id, chat_id, context)

async def send_question(user_id, chat_id, context):
    session = quiz_sessions.get(user_id)
    if not session:
        return

    current = session["current"]
    questions = session["questions"]
    total = len(questions)

    if current >= total:
        await show_result(user_id, chat_id, context)
        return

    q = questions[current]
    letters = ["🅰️", "🅱️", "🇨", "🇩"]
    keyboard = []
    for i, opt in enumerate(q["opts"]):
        keyboard.append([InlineKeyboardButton(
            f"{letters[i]}  {opt}",
            callback_data=f"ans_{user_id}_{i}"
        )])
    keyboard.append([InlineKeyboardButton("⏭ O'tkazish", callback_data=f"skip_{user_id}")])

    done = min(current, 20)
    left = min(total - current, 20)
    progress = "🟩" * done + "⬜" * left

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"❓ *{current+1}/{total}-savol*\n"
            f"{progress}\n\n"
            f"{q['q']}"
        ),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def show_result(user_id, chat_id, context):
    session = quiz_sessions.get(user_id)
    if not session:
        return

    correct = session["correct"]
    wrong = session["wrong"]
    skip = session["skip"]
    total = len(session["questions"])
    pct = round((correct / total) * 100) if total > 0 else 0
    elapsed = round(time.time() - session["start_time"])

    u = get_user(user_id)
    u["total"] += total
    u["correct"] += correct

    today = datetime.now().strftime("%Y-%m-%d")
    if u["last_date"] != today:
        u["streak"] += 1
        u["last_date"] = today

    new_record = ""
    if elapsed < u["record_time"] or u["record_time"] == 0:
        u["record_time"] = elapsed
        new_record = "🏆 *Yangi rekord!*\n"

    if pct >= 90: emoji, msg = "🏆", "Ajoyib! Zo'rsiz!"
    elif pct >= 70: emoji, msg = "🎉", "Yaxshi natija!"
    elif pct >= 50: emoji, msg = "👍", "O'rtacha. Harakat qiling!"
    else: emoji, msg = "😔", "Ko'proq o'qish kerak!"

    mins, secs = elapsed // 60, elapsed % 60
    bar = "🟩" * (pct // 10) + "⬜" * (10 - pct // 10)

    keyboard = [
        [InlineKeyboardButton("🔄 Qayta", callback_data="restart_quiz"),
         InlineKeyboardButton("📤 Ulashish", callback_data="share_quiz")],
        [InlineKeyboardButton("🏠 Bosh menyu", callback_data="back_home")]
    ]

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"{emoji} *{session['name']}*\n\n"
            f"{bar}\n"
            f"📈 *{pct}%* — {msg}\n\n"
            f"{new_record}"
            f"✅ To'g'ri: *{correct}*\n"
            f"❌ Xato: *{wrong}*\n"
            f"⏭ O'tkazilgan: *{skip}*\n\n"
            f"⏱ Vaqt: *{mins}:{secs:02d}*\n"
            f"🔥 Streak: *{u['streak']} kun*"
        ),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    del quiz_sessions[user_id]

# ==================== TUGMALAR ====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = query.from_user

    if data.startswith("ans_") or data.startswith("skip_"):
        await handle_game(update, context)
        return

    if data == "check_sub":
        subscribed = await check_subscription(user.id, context.bot)
        if subscribed:
            await start(update, context)
        else:
            await query.answer("❌ Hali obuna bo'lmadingiz!", show_alert=True)

    elif data == "back_home":
        context.user_data.clear()
        await start(update, context)

    elif data == "mode_pdf":
        if not is_vip(user.id):
            await query.answer("❌ Faqat VIP uchun!", show_alert=True)
            return
        context.user_data['pdf_mode'] = 'extract'
        await query.edit_message_text(
            "📄 *PDF dan Quiz*\n\n"
            "PDFda tayyor savollar va javoblar bo'lishi kerak.\n"
            "Bot ularni o'qib, quiz formatiga o'tkazadi!\n\n"
            "📎 *PDF faylni yuboring:*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="back_home")]])
        )

    elif data == "mode_ai":
        if not is_vip(user.id):
            await query.answer("❌ Faqat VIP uchun!", show_alert=True)
            return
        context.user_data['pdf_mode'] = 'ai'
        context.user_data['state'] = 'waiting_ai_text'
        await query.edit_message_text(
            "🤖 *AI Quiz*\n\n"
            "Istalgan mavzu matni yoki mazmunini yozing.\n"
            "AI o'zi savol tuzadi!\n\n"
            "✏️ *Matnni yozing:*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="back_home")]])
        )

    elif data == "mode_add_question":
        await show_add_question(query, context, user.id)

    elif data == "add_new_q":
        context.user_data['state'] = 'adding_question'
        await query.edit_message_text(
            "✏️ *Yangi savol qo'shish*\n\n"
            "❓ *Savol matnini yozing:*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Bekor", callback_data="mode_add_question")]])
        )

    elif data == "clear_bank":
        question_banks[user.id] = []
        await query.answer("✅ Savollar tozalandi!", show_alert=True)
        await show_add_question(query, context, user.id)

    elif data == "start_bank_quiz":
        questions = question_banks.get(user.id, [])
        if len(questions) < 5:
            await query.answer("❌ Kamida 5 ta savol kerak!", show_alert=True)
            return
        context.user_data['state'] = 'waiting_bank_name'
        context.user_data['last_questions'] = questions
        await query.edit_message_text(
            f"🎮 *Test boshlash*\n\n"
            f"📝 {len(questions)} ta savol tayyor!\n\n"
            f"✏️ Bu testga *nom bering:*",
            parse_mode="Markdown"
        )

    elif data == "mode_play":
        # Mavjud testlar ro'yxati — hozircha foydalanuvchining o'z savollar banki
        questions = question_banks.get(user.id, [])
        if not questions:
            await query.edit_message_text(
                "📭 *Hozircha test yo'q!*\n\n"
                "Avval savol qo'shing yoki VIP bo'lib PDF yuklang.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✏️ Savol qo'shish", callback_data="mode_add_question")],
                    [InlineKeyboardButton("🔙 Orqaga", callback_data="back_home")]
                ])
            )
            return
        context.user_data['state'] = 'waiting_bank_name'
        context.user_data['last_questions'] = questions
        await query.edit_message_text(
            f"🎮 *Test ishlash*\n\n"
            f"📝 {len(questions)} ta savol bor!\n\n"
            f"✏️ Testga *nom bering:*",
            parse_mode="Markdown"
        )

    elif data.startswith("count_"):
        count = int(data.split("_")[1])
        pdf_text = context.user_data.get('pdf_text', '')
        quiz_name = context.user_data.get('quiz_name', 'Quiz Test')
        pdf_mode = context.user_data.get('pdf_mode', 'extract')

        if not pdf_text:
            await query.edit_message_text("❌ Matn topilmadi! Qaytadan /start bosing.")
            return

        await query.edit_message_text(
            f"⏳ *{quiz_name}*\n\n"
            f"{'📄 PDF savollar o\'qilmoqda' if pdf_mode == 'extract' else '🤖 AI savol tuzmoqda'}...\n"
            f"*{count} ta savol* tayyorlanmoqda...",
            parse_mode="Markdown"
        )

        try:
            if pdf_mode == 'extract':
                questions = extract_questions_from_pdf(pdf_text, count)
            else:
                questions = generate_ai_questions(pdf_text, count)

            context.user_data['last_questions'] = questions
            context.user_data['last_quiz_name'] = quiz_name
            context.user_data['state'] = ''

            keyboard = [
                [InlineKeyboardButton("▶️ Testni boshlash", callback_data="start_my_quiz")],
                [InlineKeyboardButton("👥 Guruhda boshlash", callback_data="start_group_quiz")],
                [InlineKeyboardButton("📤 Ulashish", callback_data="share_quiz")],
                [InlineKeyboardButton("🏠 Bosh menyu", callback_data="back_home")]
            ]
            await query.edit_message_text(
                f"✅ *{quiz_name}*\n\n"
                f"📝 *{len(questions)} ta savol* tayyor!\n\n"
                f"Qanday boshlaysiz?",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Error: {e}")
            await query.edit_message_text(
                f"❌ Xatolik: {str(e)}\n\nQaytadan urinib ko'ring.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Bosh menyu", callback_data="back_home")]])
            )

    elif data == "start_my_quiz":
        questions = context.user_data.get('last_questions')
        quiz_name = context.user_data.get('last_quiz_name', 'Quiz')
        if questions:
            await query.edit_message_text("▶️ Boshlanmoqda...")
            await start_quiz(user.id, questions, quiz_name, context, query.message.chat_id)

    elif data == "start_group_quiz":
        questions = context.user_data.get('last_questions')
        quiz_name = context.user_data.get('last_quiz_name', 'Quiz')
        if questions:
            bot_info = await context.bot.get_me()
            keyboard = [
                [InlineKeyboardButton("▶️ Testni boshlash", url=f"https://t.me/{bot_info.username}?start=go")],
                [InlineKeyboardButton("🔙 Orqaga", callback_data="back_home")]
            ]
            await query.edit_message_text(
                f"👥 *Guruhda test*\n\n"
                f"🎯 *{quiz_name}* — {len(questions)} ta savol\n\n"
                f"Havolani guruhga yuboring:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )

    elif data == "share_quiz":
        questions = context.user_data.get('last_questions')
        quiz_name = context.user_data.get('last_quiz_name', 'Quiz')
        if questions:
            bot_info = await context.bot.get_me()
            keyboard = [
                [InlineKeyboardButton("📤 Do'stga yuborish",
                    url=f"https://t.me/share/url?url=https://t.me/{bot_info.username}&text={quiz_name}")],
                [InlineKeyboardButton("🔙 Orqaga", callback_data="back_home")]
            ]
            await query.edit_message_text(
                f"📤 *{quiz_name}* — {len(questions)} ta savol",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )

    elif data == "restart_quiz":
        questions = context.user_data.get('last_questions')
        quiz_name = context.user_data.get('last_quiz_name', 'Quiz')
        if questions:
            await query.edit_message_text("🔄 Qayta boshlanmoqda...")
            await start_quiz(user.id, questions, quiz_name, context, query.message.chat_id)

    elif data == "stats":
        u = get_user(user.id)
        total = u["total"]
        correct = u["correct"]
        pct = round((correct / total) * 100) if total > 0 else 0
        r = u["record_time"]
        vip_badge = "👑 VIP\n" if is_vip(user.id) else ""
        await query.edit_message_text(
            f"📊 *Statistika*\n{vip_badge}\n"
            f"📝 Jami: *{total}*\n"
            f"✅ To'g'ri: *{correct}*\n"
            f"📈 Foiz: *{pct}%*\n"
            f"🔥 Streak: *{u['streak']} kun*\n"
            f"⏱ Rekord: *{r//60}:{r%60:02d}*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="back_home")]])
        )

    elif data == "leaderboard":
        sorted_u = sorted(user_data.items(), key=lambda x: x[1]["correct"], reverse=True)[:10]
        medals = ["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
        text = "🏆 *TOP 10 Reyting*\n\n"
        for i, (uid, ud) in enumerate(sorted_u):
            vip = "👑" if uid in vip_users else ""
            text += f"{medals[i]} {vip} {ud['correct']} to'g'ri\n"
        if not sorted_u:
            text += "_Hali ma'lumot yo'q_"
        await query.edit_message_text(
            text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="back_home")]])
        )

    elif data == "help":
        vip = is_vip(user.id)
        text = "❓ *Yordam*\n\n"
        if vip:
            text += (
                "👑 *VIP imkoniyatlar:*\n"
                "📄 PDF yuklash → tayyor savollarni quiz qilish\n"
                "🤖 AI orqali savol tuzish\n"
                "20 / 30 / 50 / 100 ta savol\n\n"
            )
        text += (
            "✏️ *Savol qo'shish:*\n"
            "Savol → To'g'ri javob → 3 ta noto'g'ri javob\n"
            "5 tadan keyin test boshlash mumkin!\n\n"
            "🎮 *Test ishlash:*\n"
            "Tayyor testlarni ishlash\n\n"
            "❓ Muammo? /admin"
        )
        await query.edit_message_text(
            text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="back_home")]])
        )

    elif data == "contact_admin":
        context.user_data['state'] = 'waiting_admin_msg'
        await query.edit_message_text(
            f"👨‍💼 *Adminga murojaat*\n\n"
            f"Muammo yoki taklifingizni yozing:\n"
            f"📱 {ADMIN_USERNAME}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Bekor", callback_data="back_home")]])
        )

# ==================== O'YIN JAVOBLARI ====================
async def handle_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    caller = query.from_user.id

    if data.startswith("ans_"):
        parts = data.split("_")
        target_uid = int(parts[1])
        chosen = int(parts[2])

        if caller != target_uid:
            await query.answer("⚠️ Bu sizning testingiz emas!", show_alert=True)
            return

        session = quiz_sessions.get(target_uid)
        if not session:
            return

        current = session["current"]
        q = session["questions"][current]
        correct_idx = q["ans"]
        letters = ["A", "B", "C", "D"]

        if chosen == correct_idx:
            session["correct"] += 1
            feedback = "✅ *To'g'ri!*"
        else:
            session["wrong"] += 1
            feedback = f"❌ *Xato!*\nTo'g'ri: *{letters[correct_idx]}) {q['opts'][correct_idx]}*"

        session["current"] += 1
        await query.edit_message_text(
            f"❓ *{current+1}-savol*\n\n{q['q']}\n\n{feedback}",
            parse_mode="Markdown"
        )
        await send_question(target_uid, query.message.chat_id, context)

    elif data.startswith("skip_"):
        target_uid = int(data.split("_")[1])
        if caller != target_uid:
            await query.answer("⚠️ Bu sizning testingiz emas!", show_alert=True)
            return

        session = quiz_sessions.get(target_uid)
        if not session:
            return

        current = session["current"]
        q = session["questions"][current]
        letters = ["A", "B", "C", "D"]
        session["skip"] += 1
        session["current"] += 1

        await query.edit_message_text(
            f"⏭ *O'tkazildi*\nTo'g'ri: *{letters[q['ans']]}) {q['opts'][q['ans']]}*",
            parse_mode="Markdown"
        )
        await send_question(target_uid, query.message.chat_id, context)

# ==================== ASOSIY ====================
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['state'] = 'waiting_admin_msg'
    await update.message.reply_text("👨‍💼 *Adminga murojaat*\n\nXabaringizni yozing:", parse_mode="Markdown")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("myid", get_my_id))
    app.add_handler(CommandHandler("addvip", add_vip))
    app.add_handler(CommandHandler("removevip", remove_vip))
    app.add_handler(CommandHandler("viplist", vip_list))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(button_handler))
    logger.info("✅ Quiz Genius Bot ishga tushdi!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
