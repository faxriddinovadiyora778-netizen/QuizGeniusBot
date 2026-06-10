import logging
import json
import re
import time
from datetime import datetime
from groq import Groq
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import fitz

BOT_TOKEN = "8556020862:AAHURupYErvh7aasPxlfwWv73pgM8fW9e_Q"
GROQ_API_KEY = "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"
ADMIN_ID = 0
ADMIN_USERNAME = "@your_admin"

CHANNELS = [
    {"name": "Kanal 1", "url": "https://t.me/your_channel_1", "id": "@your_channel_1"},
    {"name": "Kanal 2", "url": "https://t.me/your_channel_2", "id": "@your_channel_2"},
    {"name": "Kanal 3", "url": "https://t.me/your_channel_3", "id": "@your_channel_3"},
]

groq_client = Groq(api_key=GROQ_API_KEY)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

vip_users = set()
user_data = {}
quiz_sessions = {}
question_banks = {}

def get_user(uid):
    if uid not in user_data:
        user_data[uid] = {"total": 0, "correct": 0, "streak": 0, "last_date": "", "record_time": 0}
    return user_data[uid]

def is_vip(uid):
    return uid in vip_users or uid == ADMIN_ID

async def check_sub(uid, bot):
    for ch in CHANNELS:
        if "your_channel" in ch["id"]:
            return True
        try:
            m = await bot.get_chat_member(ch["id"], uid)
            if m.status in ["left", "kicked", "banned"]:
                return False
        except:
            pass
    return True

async def show_sub(update, context):
    kb = [[InlineKeyboardButton(f"📢 {ch['name']}", url=ch['url'])] for ch in CHANNELS]
    kb.append([InlineKeyboardButton("✅ Obuna bo'ldim", callback_data="check_sub")])
    text = "🔐 *Botdan foydalanish uchun*\n\nKanallarga obuna bo'ling:\n\n"
    text += "\n".join(f"{i+1}. {ch['name']}" for i, ch in enumerate(CHANNELS))
    text += "\n\nObuna bo'lgach tugmani bosing!"
    if update.message:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    else:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_user(user.id)
    if not await check_sub(user.id, context.bot):
        await show_sub(update, context)
        return
    vip = is_vip(user.id)
    badge = "👑 VIP" if vip else "👤"
    kb = []
    if vip:
        kb.append([InlineKeyboardButton("📄 PDF dan quiz", callback_data="mode_pdf"),
                   InlineKeyboardButton("🤖 AI quiz", callback_data="mode_ai")])
    kb.append([InlineKeyboardButton("✏️ Savol qo'shish", callback_data="mode_add"),
               InlineKeyboardButton("🎮 Test ishlash", callback_data="mode_play")])
    kb.append([InlineKeyboardButton("📊 Statistika", callback_data="stats"),
               InlineKeyboardButton("🏆 Reyting", callback_data="leaderboard")])
    kb.append([InlineKeyboardButton("❓ Yordam", callback_data="help"),
               InlineKeyboardButton("👨‍💼 Admin", callback_data="contact_admin")])
    text = f"👋 Salom, *{user.first_name}* {badge}!\n\n🤖 *Quiz Genius Bot*\n\n"
    if vip:
        text += "👑 *VIP:* PDF yuklash, AI quiz\n"
    text += "✏️ Savol qo'shib test tuzing\n🎮 Tayyor testlarni ishlang\n\n👇 Tanlang:"
    if update.message:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    else:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def add_vip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if context.args:
        try:
            uid = int(context.args[0])
            vip_users.add(uid)
            await update.message.reply_text(f"✅ {uid} VIP qilindi!")
        except:
            await update.message.reply_text("❌ ID noto'g'ri!")

async def myid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Sizning ID: `{update.effective_user.id}`", parse_mode="Markdown")

async def handle_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_vip(user.id):
        await update.message.reply_text("❌ PDF yuklash faqat VIP uchun!")
        return
    doc = update.message.document
    if not doc.file_name.lower().endswith('.pdf'):
        await update.message.reply_text("⚠️ Faqat PDF yuboring!")
        return
    msg = await update.message.reply_text("⏳ PDF o'qilmoqda...")
    try:
        file = await context.bot.get_file(doc.file_id)
        path = f"/tmp/quiz_{user.id}.pdf"
        await file.download_to_drive(path)
        pdf = fitz.open(path)
        text = "".join(page.get_text() for page in pdf)
        pdf.close()
        if len(text.strip()) < 50:
            await msg.edit_text("❌ PDF da matn topilmadi!")
            return
        context.user_data['pdf_text'] = text
        context.user_data['pdf_mode'] = 'extract'
        context.user_data['state'] = 'waiting_name'
        await msg.edit_text("✅ *PDF yuklandi!*\n\n✏️ Testga *nom bering:*", parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"❌ Xatolik: {e}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text
    if text.startswith('/'):
        return
    state = context.user_data.get('state', '')

    if state == 'waiting_name':
        context.user_data['quiz_name'] = text
        context.user_data['state'] = 'waiting_count'
        kb = [
            [InlineKeyboardButton("20 📝", callback_data="count_20"), InlineKeyboardButton("30 📝", callback_data="count_30")],
            [InlineKeyboardButton("50 📝", callback_data="count_50"), InlineKeyboardButton("100 📝", callback_data="count_100")],
            [InlineKeyboardButton("🔙 Bekor", callback_data="back_home")]
        ]
        await update.message.reply_text(
            f"✅ Test nomi: *{text}*\n\n📊 *Nechta savol?*",
            reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        return

    if state == 'waiting_ai_text':
        context.user_data['pdf_text'] = text
        context.user_data['pdf_mode'] = 'ai'
        context.user_data['state'] = 'waiting_name'
        await update.message.reply_text("✅ Matn qabul qilindi!\n\n✏️ Testga *nom bering:*", parse_mode="Markdown")
        return

    if state == 'adding_q':
        context.user_data['new_q'] = {'q': text}
        context.user_data['state'] = 'adding_correct'
        await update.message.reply_text(f"❓ _{text}_\n\n✅ *To'g'ri javobni yozing:*", parse_mode="Markdown")
        return

    if state == 'adding_correct':
        context.user_data['new_q']['correct'] = text
        context.user_data['new_q']['opts'] = [text]
        context.user_data['state'] = 'adding_w1'
        await update.message.reply_text("❌ *1-noto'g'ri javob:*", parse_mode="Markdown")
        return

    if state == 'adding_w1':
        context.user_data['new_q']['opts'].append(text)
        context.user_data['state'] = 'adding_w2'
        await update.message.reply_text("❌ *2-noto'g'ri javob:*", parse_mode="Markdown")
        return

    if state == 'adding_w2':
        context.user_data['new_q']['opts'].append(text)
        context.user_data['state'] = 'adding_w3'
        await update.message.reply_text("❌ *3-noto'g'ri javob:*", parse_mode="Markdown")
        return

    if state == 'adding_w3':
        context.user_data['new_q']['opts'].append(text)
        context.user_data['state'] = ''
        import random
        q_data = context.user_data['new_q']
        opts = q_data['opts'].copy()
        random.shuffle(opts)
        ans = opts.index(q_data['correct'])
        if user.id not in question_banks:
            question_banks[user.id] = []
        question_banks[user.id].append({'q': q_data['q'], 'opts': opts, 'ans': ans})
        count = len(question_banks[user.id])
        kb = [[InlineKeyboardButton("➕ Yana qo'shish", callback_data="add_new_q")]]
        if count >= 5:
            kb.append([InlineKeyboardButton(f"🎮 Testni boshlash ({count} ta)", callback_data="start_bank")])
        kb.append([InlineKeyboardButton("🏠 Bosh menyu", callback_data="back_home")])
        await update.message.reply_text(
            f"✅ *Savol saqlandi!*\n📝 Jami: *{count} ta*",
            reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        return

    if state == 'waiting_bank_name':
        context.user_data['state'] = ''
        questions = context.user_data.get('last_questions', [])
        await update.message.reply_text(f"🎮 *{text}* boshlanmoqda!", parse_mode="Markdown")
        await start_quiz(user.id, questions, text, context, update.message.chat_id)
        return

    if state == 'admin_msg':
        context.user_data['state'] = ''
        if ADMIN_ID:
            try:
                await context.bot.send_message(ADMIN_ID, f"📨 *Murojaat:*\n👤 {user.first_name} (@{user.username})\n🆔 {user.id}\n\n💬 {text}", parse_mode="Markdown")
            except:
                pass
        await update.message.reply_text("✅ Xabaringiz adminga yuborildi!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Bosh menyu", callback_data="back_home")]]))
        return

    await update.message.reply_text("📎 /start bosing yoki PDF yuboring.")

def generate_from_pdf(text, count):
    prompt = f"Quyidagi matndagi tayyor test savollarini o'qib, {count} tasini JSON formatga o'tkaz. FAQAT JSON:\n[{{\"q\":\"Savol?\",\"opts\":[\"To'g'ri\",\"Xato1\",\"Xato2\",\"Xato3\"],\"ans\":0}}]\n\nMatn:\n{text[:12000]}"
    r = groq_client.chat.completions.create(model="llama3-70b-8192", messages=[{"role": "user", "content": prompt}], max_tokens=6000, temperature=0.1)
    raw = re.sub(r'```json|```', '', r.choices[0].message.content).strip()
    return json.loads(raw[raw.find('['):raw.rfind(']')+1])[:count]

def generate_ai(text, count):
    prompt = f"Matn asosida {count} ta test savoli tuz. FAQAT JSON:\n[{{\"q\":\"?\",\"opts\":[\"A\",\"B\",\"C\",\"D\"],\"ans\":0}}]\n\nMatn:\n{text[:10000]}"
    r = groq_client.chat.completions.create(model="llama3-70b-8192", messages=[{"role": "user", "content": prompt}], max_tokens=6000, temperature=0.3)
    raw = re.sub(r'```json|```', '', r.choices[0].message.content).strip()
    return json.loads(raw[raw.find('['):raw.rfind(']')+1])[:count]

async def start_quiz(uid, questions, name, context, chat_id):
    quiz_sessions[uid] = {"questions": questions, "current": 0, "correct": 0, "wrong": 0, "skip": 0, "name": name, "start_time": time.time()}
    await context.bot.send_message(chat_id, f"🎯 *{name}*\n📝 *{len(questions)} ta savol*\n\nBoshlanmoqda! 🚀", parse_mode="Markdown")
    await send_q(uid, chat_id, context)

async def send_q(uid, chat_id, context):
    s = quiz_sessions.get(uid)
    if not s:
        return
    cur = s["current"]
    qs = s["questions"]
    if cur >= len(qs):
        await show_result(uid, chat_id, context)
        return
    q = qs[cur]
    letters = ["🅰️", "🅱️", "🇨", "🇩"]
    kb = [[InlineKeyboardButton(f"{letters[i]}  {opt}", callback_data=f"ans_{uid}_{i}")] for i, opt in enumerate(q["opts"])]
    kb.append([InlineKeyboardButton("⏭ O'tkazish", callback_data=f"skip_{uid}")])
    bar = "🟩" * min(cur, 20) + "⬜" * min(len(qs)-cur, 20)
    await context.bot.send_message(chat_id, f"❓ *{cur+1}/{len(qs)}*\n{bar}\n\n{q['q']}", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def show_result(uid, chat_id, context):
    s = quiz_sessions.get(uid)
    if not s:
        return
    correct, wrong, skip = s["correct"], s["wrong"], s["skip"]
    total = len(s["questions"])
    pct = round(correct/total*100) if total else 0
    elapsed = round(time.time() - s["start_time"])
    u = get_user(uid)
    u["total"] += total
    u["correct"] += correct
    today = datetime.now().strftime("%Y-%m-%d")
    if u["last_date"] != today:
        u["streak"] += 1
        u["last_date"] = today
    if elapsed < u["record_time"] or u["record_time"] == 0:
        u["record_time"] = elapsed
    if pct >= 90: emoji, msg = "🏆", "Ajoyib!"
    elif pct >= 70: emoji, msg = "🎉", "Yaxshi natija!"
    elif pct >= 50: emoji, msg = "👍", "O'rtacha"
    else: emoji, msg = "😔", "Ko'proq o'qing!"
    bar = "🟩"*(pct//10) + "⬜"*(10-pct//10)
    kb = [[InlineKeyboardButton("🔄 Qayta", callback_data="restart"), InlineKeyboardButton("🏠 Menyu", callback_data="back_home")]]
    await context.bot.send_message(chat_id,
        f"{emoji} *{s['name']}*\n\n{bar}\n📈 *{pct}%* — {msg}\n\n✅ To'g'ri: *{correct}*\n❌ Xato: *{wrong}*\n⏭ O'tkazilgan: *{skip}*\n⏱ Vaqt: *{elapsed//60}:{elapsed%60:02d}*\n🔥 Streak: *{u['streak']} kun*",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    del quiz_sessions[uid]

async def btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = query.from_user

    if data.startswith("ans_") or data.startswith("skip_"):
        await game_handler(update, context)
        return

    if data == "check_sub":
        if await check_sub(user.id, context.bot):
            await start(update, context)
        else:
            await query.answer("❌ Hali obuna bo'lmadingiz!", show_alert=True)

    elif data == "back_home":
        context.user_data.clear()
        await start(update, context)

    elif data == "mode_pdf":
        if not is_vip(user.id):
            await query.answer("❌ Faqat VIP uchun!", show_alert=True); return
        context.user_data['pdf_mode'] = 'extract'
        await query.edit_message_text("📄 *PDF yuklash*\n\nPDF faylni yuboring:", parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="back_home")]]))

    elif data == "mode_ai":
        if not is_vip(user.id):
            await query.answer("❌ Faqat VIP uchun!", show_alert=True); return
        context.user_data['pdf_mode'] = 'ai'
        context.user_data['state'] = 'waiting_ai_text'
        await query.edit_message_text("🤖 *AI Quiz*\n\nMavzu matnini yozing:", parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="back_home")]]))

    elif data == "mode_add":
        count = len(question_banks.get(user.id, []))
        kb = [[InlineKeyboardButton("➕ Savol qo'shish", callback_data="add_new_q")]]
        if count >= 5:
            kb.append([InlineKeyboardButton(f"🎮 Test boshlash ({count} ta)", callback_data="start_bank")])
        kb.append([InlineKeyboardButton("🗑 Tozalash", callback_data="clear_bank"), InlineKeyboardButton("🔙 Orqaga", callback_data="back_home")])
        await query.edit_message_text(f"✏️ *Savol qo'shish*\n\n📝 Hozir: *{count} ta savol*\n_(Min 5 ta kerak)_",
            reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif data == "add_new_q":
        context.user_data['state'] = 'adding_q'
        await query.edit_message_text("✏️ *Savol matnini yozing:*", parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Bekor", callback_data="mode_add")]]))

    elif data == "clear_bank":
        question_banks[user.id] = []
        await query.answer("✅ Tozalandi!", show_alert=True)
        await btn(update, context)

    elif data == "start_bank":
        qs = question_banks.get(user.id, [])
        if len(qs) < 5:
            await query.answer("❌ Kamida 5 ta savol kerak!", show_alert=True); return
        context.user_data['last_questions'] = qs
        context.user_data['state'] = 'waiting_bank_name'
        await query.edit_message_text(f"🎮 *{len(qs)} ta savol tayyor!*\n\n✏️ Test nomini yozing:", parse_mode="Markdown")

    elif data == "mode_play":
        qs = question_banks.get(user.id, [])
        if not qs:
            await query.edit_message_text("📭 *Test yo'q!*\n\nAvval savol qo'shing.", parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✏️ Savol qo'shish", callback_data="mode_add")], [InlineKeyboardButton("🔙 Orqaga", callback_data="back_home")]]))
            return
        context.user_data['last_questions'] = qs
        context.user_data['state'] = 'waiting_bank_name'
        await query.edit_message_text(f"🎮 *{len(qs)} ta savol bor!*\n\n✏️ Test nomini yozing:", parse_mode="Markdown")

    elif data.startswith("count_"):
        count = int(data.split("_")[1])
        pdf_text = context.user_data.get('pdf_text', '')
        quiz_name = context.user_data.get('quiz_name', 'Quiz')
        pdf_mode = context.user_data.get('pdf_mode', 'extract')
        if not pdf_text:
            await query.edit_message_text("❌ Matn topilmadi!"); return
        await query.edit_message_text(f"⏳ *{quiz_name}*\n\n{'📄 PDFdan' if pdf_mode=='extract' else '🤖 AI'} {count} ta savol tayyorlanmoqda...", parse_mode="Markdown")
        try:
            qs = generate_from_pdf(pdf_text, count) if pdf_mode == 'extract' else generate_ai(pdf_text, count)
            context.user_data['last_questions'] = qs
            context.user_data['last_quiz_name'] = quiz_name
            context.user_data['state'] = ''
            kb = [
                [InlineKeyboardButton("▶️ Boshlash", callback_data="start_my")],
                [InlineKeyboardButton("👥 Guruhda", callback_data="group_quiz"), InlineKeyboardButton("📤 Ulashish", callback_data="share_quiz")],
                [InlineKeyboardButton("🏠 Menyu", callback_data="back_home")]
            ]
            await query.edit_message_text(f"✅ *{quiz_name}*\n\n📝 *{len(qs)} ta savol* tayyor!", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        except Exception as e:
            await query.edit_message_text(f"❌ Xatolik: {e}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menyu", callback_data="back_home")]]))

    elif data == "start_my":
        qs = context.user_data.get('last_questions', [])
        name = context.user_data.get('last_quiz_name', 'Quiz')
        if qs:
            await query.edit_message_text("▶️ Boshlanmoqda...")
            await start_quiz(user.id, qs, name, context, query.message.chat_id)

    elif data == "restart":
        qs = context.user_data.get('last_questions', [])
        name = context.user_data.get('last_quiz_name', 'Quiz')
        if qs:
            await query.edit_message_text("🔄 Qayta boshlanmoqda...")
            await start_quiz(user.id, qs, name, context, query.message.chat_id)

    elif data == "group_quiz":
        qs = context.user_data.get('last_questions', [])
        name = context.user_data.get('last_quiz_name', 'Quiz')
        bot_info = await context.bot.get_me()
        kb = [[InlineKeyboardButton("▶️ Testni boshlash", url=f"https://t.me/{bot_info.username}?start=go")], [InlineKeyboardButton("🔙 Orqaga", callback_data="back_home")]]
        await query.edit_message_text(f"👥 *{name}* — {len(qs)} ta savol\n\nHavolani guruhga yuboring:", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif data == "share_quiz":
        qs = context.user_data.get('last_questions', [])
        name = context.user_data.get('last_quiz_name', 'Quiz')
        bot_info = await context.bot.get_me()
        kb = [[InlineKeyboardButton("📤 Do'stga yuborish", url=f"https://t.me/share/url?url=https://t.me/{bot_info.username}&text={name}")], [InlineKeyboardButton("🔙 Orqaga", callback_data="back_home")]]
        await query.edit_message_text(f"📤 *{name}* — {len(qs)} ta savol", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif data == "stats":
        u = get_user(user.id)
        pct = round(u['correct']/u['total']*100) if u['total'] else 0
        r = u['record_time']
        vip_b = "👑 VIP\n" if is_vip(user.id) else ""
        await query.edit_message_text(
            f"📊 *Statistika*\n{vip_b}\n📝 Jami: *{u['total']}*\n✅ To'g'ri: *{u['correct']}*\n📈 Foiz: *{pct}%*\n🔥 Streak: *{u['streak']} kun*\n⏱ Rekord: *{r//60}:{r%60:02d}*",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="back_home")]]))

    elif data == "leaderboard":
        su = sorted(user_data.items(), key=lambda x: x[1]["correct"], reverse=True)[:10]
        medals = ["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
        text = "🏆 *TOP 10*\n\n"
        for i, (uid, ud) in enumerate(su):
            text += f"{medals[i]} {'👑' if uid in vip_users else ''} {ud['correct']} to'g'ri\n"
        if not su: text += "_Hali ma'lumot yo'q_"
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="back_home")]]))

    elif data == "help":
        vip = is_vip(user.id)
        text = "❓ *Yordam*\n\n"
        if vip:
            text += "👑 *VIP:*\n📄 PDF → savollarni quiz qilish\n🤖 AI → savol tuzish\n20/30/50/100 ta\n\n"
        text += "✏️ *Savol qo'shish:*\nSavol → To'g'ri → 3 noto'g'ri\n5 tadan keyin test!\n\n❓ Muammo? /admin"
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="back_home")]]))

    elif data == "contact_admin":
        context.user_data['state'] = 'admin_msg'
        await query.edit_message_text(f"👨‍💼 *Adminga murojaat*\n\nXabaringizni yozing:\n{ADMIN_USERNAME}", parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Bekor", callback_data="back_home")]]))

async def game_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    caller = query.from_user.id

    if data.startswith("ans_"):
        parts = data.split("_")
        tuid = int(parts[1])
        chosen = int(parts[2])
        if caller != tuid:
            await query.answer("⚠️ Bu sizning testingiz emas!", show_alert=True); return
        s = quiz_sessions.get(tuid)
        if not s: return
        cur = s["current"]
        q = s["questions"][cur]
        correct = q["ans"]
        letters = ["A","B","C","D"]
        if chosen == correct:
            s["correct"] += 1
            fb = "✅ *To'g'ri!*"
        else:
            s["wrong"] += 1
            fb = f"❌ *Xato!*\nTo'g'ri: *{letters[correct]}) {q['opts'][correct]}*"
        s["current"] += 1
        await query.edit_message_text(f"❓ *{cur+1}-savol*\n\n{q['q']}\n\n{fb}", parse_mode="Markdown")
        await send_q(tuid, query.message.chat_id, context)

    elif data.startswith("skip_"):
        tuid = int(data.split("_")[1])
        if caller != tuid:
            await query.answer("⚠️ Bu sizning testingiz emas!", show_alert=True); return
        s = quiz_sessions.get(tuid)
        if not s: return
        cur = s["current"]
        q = s["questions"][cur]
        letters = ["A","B","C","D"]
        s["skip"] += 1
        s["current"] += 1
        await query.edit_message_text(f"⏭ *O'tkazildi*\nTo'g'ri: *{letters[q['ans']]}) {q['opts'][q['ans']]}*", parse_mode="Markdown")
        await send_q(tuid, query.message.chat_id, context)

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['state'] = 'admin_msg'
    await update.message.reply_text("👨‍💼 *Adminga murojaat*\n\nXabaringizni yozing:", parse_mode="Markdown")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CommandHandler("myid", myid_cmd))
    app.add_handler(CommandHandler("addvip", add_vip_cmd))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_doc))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(btn))
    logger.info("✅ Quiz Genius Bot ishga tushdi!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
