import telebot
from telebot import types
import sqlite3
from datetime import datetime
import pytz

# --- ပြင်ဆင်ရန် ---
API_TOKEN = '8280427701:AAFId7jPd4xY0FPPG6auBXqXAX5E_EOuKQc'
ADMIN_ID = 7947267218

# ----------------
from telebot import apihelper

# PythonAnywhere Proxy ကို သုံးဖို့ သတ်မှတ်ပေးခြင်း
apihelper.proxy = {'https': 'http://proxy.server:3128'}

bot = telebot.TeleBot(API_TOKEN, threaded=True, num_threads=20)
user_data = {}
closed_numbers = set()
is_maintenance = False
mm_tz = pytz.timezone('Asia/Yangon')

# --- Admin Menu Setup ---
def init_db():
    with sqlite3.connect('2d_betting.sqlite', timeout=20) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS users
                        (user_id INTEGER PRIMARY KEY, username TEXT, balance INTEGER DEFAULT 0, is_banned INTEGER DEFAULT 0)''')
        try: conn.execute("ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0")
        except: pass
        conn.execute('''CREATE TABLE IF NOT EXISTS history
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, num TEXT, amount INTEGER, date TEXT, session TEXT, time TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        conn.execute('CREATE TABLE IF NOT EXISTS limits (num TEXT PRIMARY KEY, max_amount INTEGER)')
        conn.commit()

init_db()

# --- Ban Check Helper ---
def is_user_banned(user_id):
    with sqlite3.connect('2d_betting.sqlite', timeout=20) as conn:
        res = conn.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return res[0] == 1 if res else False

# --- Helper Functions ---
def get_balance(user_id):
    with sqlite3.connect('2d_betting.sqlite', timeout=20) as conn:
        res = conn.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return res[0] if res else 0

def update_balance(user_id, amount, username=None):
    with sqlite3.connect('2d_betting.sqlite', timeout=20) as conn:
        conn.execute("INSERT OR IGNORE INTO users (user_id, username, balance) VALUES (?, ?, 0)", (user_id, username))
        if username:
            conn.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
        conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        conn.commit()

def get_market_status(session):
    now = datetime.now(mm_tz)
    day = now.strftime('%A')
    time_now = now.strftime('%H:%M')
    closing_times = {"9:30 AM": "08:50", "12:00 PM": "11:50", "4:30 PM": "15:50"}
    if day in ['Saturday', 'Sunday']: return False, "⚠️ ပိတ်ရက်ဖြစ်၍ ပိတ်ပါသည်။", ""
    target = closing_times.get(session)
    if time_now >= target: return False, f"⚠️ {session} ပွဲစဉ် ပိတ်သွားပါပြီ။", ""
    fmt = "%H:%M"
    tdelta = datetime.strptime(target, fmt) - datetime.strptime(time_now, fmt)
    total_minutes = tdelta.seconds // 60
    hours = total_minutes // 60
    minutes = total_minutes % 60
    time_str = f"⏳ ပိတ်ရန်: {hours} နာရီ {minutes} မိနစ်" if hours > 0 else f"⏳ ပိတ်ရန်: {minutes} မိနစ်"
    return True, "Open", time_str

def set_main_menu(user_id):
    bal = get_balance(user_id)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🎰 2D ထိုးမည်", "💰 ငွေသွင်းမည်")
    markup.row("💸 ငွေထုတ်မည်", "📜 မှတ်တမ်း")
    markup.row("📜 စည်းကမ်းချက်", f"💳 လက်ကျန်: {bal} MMK")
    markup.row("🔄 Bot ကို Restart လုပ်ရန်")
    if user_id == ADMIN_ID:
        markup.row("🛠 Admin Panel")
    return markup

# --- Middleware (Ban & Maintenance) ---
@bot.message_handler(func=lambda m: is_user_banned(m.chat.id))
def handle_banned(message):
    bot.send_message(message.chat.id, "🚫 သင်၏အကောင့်မှာ စည်းကမ်းဖောက်ဖျက်မှုကြောင့် ပိတ်ပင်ခံထားရပါသည်။ Admin ဆီသို့ ဆက်သွယ်ပါ။")

@bot.message_handler(func=lambda m: is_maintenance and m.chat.id != ADMIN_ID)
def maintenance_msg(message):
    bot.send_message(message.chat.id, "🛠 Bot သည် ခေတ္တပြုပြင်ထိန်းသိမ်းနေပါသည်။ မကြာမီ ပြန်ဖွင့်ပါမည်။")

# --- DEPOSIT & WITHDRAW LOGIC ---
@bot.message_handler(func=lambda m: m.text == "💰 ငွေသွင်းမည်")
def deposit_init(message):
    if is_user_banned(message.chat.id): return
    cid = message.chat.id
    msg = bot.send_message(cid, "🏦 **ငွေသွင်းရန် အချက်အလက်**\n\nKpay / Wave: **09660003855**\n\nသွင်းလိုသော ပမာဏကို ဂဏန်းဖြင့် ရိုက်ထည့်ပါ:")
    bot.register_next_step_handler(msg, process_dep_amt)

def process_dep_amt(message):
    cid = message.chat.id
    if not message.text.isdigit():
        bot.send_message(cid, "⚠️ ဂဏန်းသက်သက်ပဲ ရိုက်ပေးပါဗျ။")
        return
    user_data[cid] = {'d_amt': int(message.text)}
    msg = bot.send_message(cid, f"💰 သွင်းမည့်ပမာဏ: **{message.text}** MMK\n\nငွေလွှဲပြီးပါက လုပ်ငန်းစဉ်အမှတ် (သို့မဟုတ်) Screenshot မှ ဂဏန်း ၆ လုံးကို ပေးပို့ပေးပါ:")
    bot.register_next_step_handler(msg, process_dep_proof)

def process_dep_proof(message):
    cid = message.chat.id
    amt = user_data[cid].get('d_amt')
    markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("✅ အတည်ပြု", callback_data=f"okdep_{cid}_{amt}"), types.InlineKeyboardButton("❌ ပယ်ချ", callback_data=f"rejdep_{cid}"))
    bot.send_message(ADMIN_ID, f"📥 **ငွေသွင်းအော်ဒါ**\n👤 {message.from_user.first_name}\n🆔 `{cid}`\n💰 {amt} MMK\n🔢 Code: {message.text}", parse_mode="Markdown", reply_markup=markup)
    bot.send_message(cid, "✅ တင်ပြမှု အောင်မြင်ပါသည်။ ခေတ္တစောင့်ဆိုင်းပေးပါဗျ။", reply_markup=set_main_menu(cid))

@bot.message_handler(func=lambda m: m.text == "💸 ငွေထုတ်မည်")
def withdraw_init(message):
    if is_user_banned(message.chat.id): return
    bal = get_balance(message.chat.id)
    if bal < 1000: bot.send_message(message.chat.id, "⚠️ အနည်းဆုံး ၁၀၀၀ ကျပ် ရှိမှ ထုတ်နိုင်ပါတယ်။"); return
    msg = bot.send_message(message.chat.id, f"ထုတ်မည့်ပမာဏ (လက်ကျန်: {bal}):")
    bot.register_next_step_handler(msg, process_wd_amt)

def process_wd_amt(message):
    if not message.text.isdigit(): return
    amt = int(message.text)
    if amt > get_balance(message.chat.id): bot.send_message(message.chat.id, "❌ လက်ကျန်မလောက်ပါ။"); return
    user_data[message.chat.id] = {'w_amt': amt}
    markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("Kpay", callback_data="method_Kpay"), types.InlineKeyboardButton("WavePay", callback_data="method_WavePay"))
    bot.send_message(message.chat.id, "🏦 ငွေထုတ်မည့် အမျိုးအစားရွေးပါ:", reply_markup=markup)

def process_wd_name(message):
    user_data[message.chat.id]['w_name'] = message.text
    msg= bot.send_message(message.chat.id, "📱 ဖုန်းနံပါတ် ရိုက်ပါ:")
    bot.register_next_step_handler(msg, process_wd_final)

def process_wd_final(message):
    cid = message.chat.id
    d = user_data[cid]
    update_balance(cid, -d['w_amt'])
    markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("✅ လွှဲပြီး", callback_data=f"okwd_{cid}_{d['w_amt']}"), types.InlineKeyboardButton("❌ ပယ်ချ", callback_data=f"rejwd_{cid}_{d['w_amt']}"))
    bot.send_message(ADMIN_ID, f"📤 **ငွေထုတ်**\n🆔 `{cid}`\n💰 {d['w_amt']} MMK\n🏦 {d['method']}\n👤 {d['w_name']}\n📱 {message.text}", parse_mode="Markdown", reply_markup=markup)
    bot.send_message(cid, "✅ တင်ပြပြီးပါပြီ။ Admin အတည်ပြုချက်ကို စောင့်ပါ။", reply_markup=set_main_menu(cid))

# --- CALLBACK HANDLER ---
@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    if is_user_banned(call.message.chat.id): return
    cid = call.message.chat.id
    d = call.data.split("_")
    action = d[0]

    # --- Admin Inline Actions ---
    if action == "admin":
        if d[1] == "win":
            markup = types.InlineKeyboardMarkup()
            markup.row(types.InlineKeyboardButton("🌅 9:30 AM", callback_data="winset_!p1"), types.InlineKeyboardButton("☀️ 12:00 PM", callback_data="winset_!p2"))
            markup.row(types.InlineKeyboardButton("🌆 4:30 PM", callback_data="winset_!p3"))
            bot.edit_message_text("🏆 ပေါက်သီးထုတ်မည့် ပွဲစဉ်ရွေးပါ:", cid, call.message.message_id, reply_markup=markup)
        elif d[1] == "close":
            msg = bot.send_message(cid, "🚫 ပိတ်မည့်ဂဏန်းကို ရိုက်ထည့်ပါ (ဥပမာ- 05):")
            bot.register_next_step_handler(msg, close_num_by_btn)
        elif d[1] == "open":
            msg = bot.send_message(cid, "✅ ပြန်ဖွင့်မည့်ဂဏန်းကို ရိုက်ထည့်ပါ (ဥပမာ- 05):")
            bot.register_next_step_handler(msg, open_num_by_btn)
        elif d[1] == "ban":
            msg = bot.send_message(cid, "🚫 Ban မည့် User ID ကို ရိုက်ထည့်ပါ:")
            bot.register_next_step_handler(msg, ban_user_by_btn)
        elif d[1] == "unban":
            msg = bot.send_message(cid, "✅ ပြန်ဖွင့်ပေးမည့် User ID ကို ရိုက်ထည့်ပါ:")
            bot.register_next_step_handler(msg, unban_user_by_btn)

    elif action == "winset":
        msg = bot.send_message(cid, f"🔢 {d[1]} အတွက် ပေါက်ဂဏန်း ရိုက်ပါ:")
        bot.register_next_step_handler(msg, lambda m: win_declare_by_btn(m, d[1]))

    # --- Original Actions ---
    elif action == "okdep":
        update_balance(int(d[1]), int(d[2]))
        bot.send_message(int(d[1]), f"🎉 သင်၏ငွေသွင်းမှု {d[2]} MMK အောင်မြင်ပါသည်။", reply_markup=set_main_menu(int(d[1])))
        bot.edit_message_text(call.message.text + "\n✅ Approved", cid, call.message.message_id)
    elif action == "rejdep":
        bot.send_message(int(d[1]), "⚠️ သင်၏ငွေသွင်းမှုကို Admin မှ ပယ်ချလိုက်ပါသည်။", reply_markup=set_main_menu(int(d[1])))
        bot.edit_message_text(call.message.text + "\n❌ Rejected", cid, call.message.message_id)
    elif action == "okwd":
        bot.send_message(int(d[1]), f"🎉 သင်ထုတ်ယူသောငွေ {d[2]} MMK ကို လွှဲပေးပြီးပါပြီ။", reply_markup=set_main_menu(int(d[1])))
        bot.edit_message_text(call.message.text + "\n✅ Transferred", cid, call.message.message_id)
    elif action == "rejwd":
        update_balance(int(d[1]), int(d[2]))
        bot.send_message(int(d[1]), f"⚠️ သင်၏ငွေထုတ်မှုကို ပယ်ဖျက်လိုက်သဖြင့် {d[2]} MMK ပြန်အမ်းထားပါသည်။", reply_markup=set_main_menu(int(d[1])))
        bot.edit_message_text(call.message.text + "\n❌ Rejected", cid, call.message.message_id)
    elif action == "method":
        if cid not in user_data: user_data[cid] = {}
        user_data[cid]['method'] = d[1]
        msg = bot.send_message(cid, "👤 ငွေလက်ခံမည့်အမည် ရိုက်ပါ:")
        bot.register_next_step_handler(msg, process_wd_name)
    elif action == "sess":
        is_open, msg, timer = get_market_status(d[1])
        if not is_open: bot.answer_callback_query(call.id, msg, show_alert=True); return
        user_data[cid] = {'session': d[1], 'selected': [], 'page': 0}
        bot.edit_message_text(f"🎰 **{d[1]}** ({timer})\nဂဏန်းရွေးချယ်ပါ -", cid, call.message.message_id, reply_markup=get_2d_keyboard(0))
    elif action == "page":
        user_data[cid]['page'] = int(d[1])
        bot.edit_message_text(f"🎰 **{user_data[cid]['session']}**", cid, call.message.message_id, reply_markup=get_2d_keyboard(int(d[1]), user_data[cid]['selected']))
    elif action == "sel":
        if d[1] in user_data[cid]['selected']: user_data[cid]['selected'].remove(d[1])
        else: user_data[cid]['selected'].append(d[1])
        bot.edit_message_reply_markup(cid, call.message.message_id, reply_markup=get_2d_keyboard(user_data[cid]['page'], user_data[cid]['selected']))
    elif action == "sp":
        if d[1] == "double": user_data[cid]['selected'] = [str(i*11).zfill(2) for i in range(10)]
        elif d[1] == "power": user_data[cid]['selected'] = ["05","50","16","61","27","72","38","83","49","94"]
        elif d[1] == "nat": user_data[cid]['selected'] = ["07","70","18","81","24","42","35","53","69","96"]
        elif d[1] == "bro": user_data[cid]['selected'] = [str(i).zfill(2) for i in range(100) if abs(int(str(i).zfill(2)[0]) - int(str(i).zfill(2)[1])) == 1 or str(i).zfill(2) in ["09","90"]]
        elif d[1] == "brake":
            bot.send_message(cid, "🔢 မည်သည့် ဘရိတ်လဲ? (0-9)")
            bot.register_next_step_handler_by_chat_id(cid, process_shortcut, "brake", call.message.message_id)
            return
        elif d[1] == "head":
            bot.send_message(cid, "🔢 မည်သည့် ထိပ်စီးလဲ? (0-9)")
            bot.register_next_step_handler_by_chat_id(cid, process_shortcut, "head", call.message.message_id)
            return
        elif d[1] == "tail":
            bot.send_message(cid, "🔢 မည်သည့် နောက်ပိတ်လဲ? (0-9)")
            bot.register_next_step_handler_by_chat_id(cid, process_shortcut, "tail", call.message.message_id)
            return
        elif d[1] == "patthee":
            bot.send_message(cid, "🌀 မည်သည့်ပတ်သီးလဲ? (0-9)")
            bot.register_next_step_handler_by_chat_id(cid, process_patthee, call.message.message_id)
            return
        bot.edit_message_reply_markup(cid, call.message.message_id, reply_markup=get_2d_keyboard(user_data[cid]['page'], user_data[cid]['selected']))
    elif action == "confirm":
        bot.answer_callback_query(call.id, "⚠️ သတိပြုရန်!\nထိုးပြီးသားဂဏန်းများကို ပြန်ပြင်၍မရပါ။", show_alert=True)
        msg = bot.send_message(cid, f"🔢 ဂဏန်းများ: {', '.join(user_data[cid]['selected'])}\n💰 တစ်ကွက်လျှင် ထိုးမည့်ပမာဏ (100 - 500,000):")
        bot.register_next_step_handler(msg, process_final_bet)

# --- Shortcut Processors ---
def process_shortcut(message, stype, mid):
    cid = message.chat.id
    if not message.text.isdigit(): return
    val = int(message.text[0])
    if stype == "brake":
        user_data[cid]['selected'] = [str(i).zfill(2) for i in range(100) if (int(str(i).zfill(2)[0]) + int(str(i).zfill(2)[1])) % 10 == val]
    elif stype == "head":
        user_data[cid]['selected'] = [str(i).zfill(2) for i in range(100) if int(str(i).zfill(2)[0]) == val]
    elif stype == "tail":
        user_data[cid]['selected'] = [str(i).zfill(2) for i in range(100) if int(str(i).zfill(2)[1]) == val]
    try: bot.edit_message_reply_markup(cid, mid, reply_markup=get_2d_keyboard(user_data[cid]['page'], user_data[cid]['selected']))
    except: pass

def process_patthee(message, mid):
    cid = message.chat.id
    if not message.text.isdigit(): return
    p = message.text[0]
    user_data[cid]['selected'] = [str(i).zfill(2) for i in range(100) if p in str(i).zfill(2) and str(i).zfill(2) not in closed_numbers]
    try: bot.edit_message_reply_markup(cid, mid, reply_markup=get_2d_keyboard(user_data[cid]['page'], user_data[cid]['selected']))
    except: pass

# --- 2D KEYBOARD ---
def get_2d_keyboard(start_num, selected_list=None):
    if selected_list is None: selected_list = []
    markup = types.InlineKeyboardMarkup(row_width=5)
    end_num = min(start_num + 24, 99)
    btns = []
    for i in range(start_num, end_num + 1):
        num_str = str(i).zfill(2)
        txt = f"✅ {num_str}" if num_str in selected_list else num_str
        if num_str in closed_numbers: txt = f"❌ {num_str}"
        btns.append(types.InlineKeyboardButton(txt, callback_data=f"sel_{num_str}" if num_str not in closed_numbers else "none"))
    markup.add(*btns)
    markup.row(types.InlineKeyboardButton("⬅️ ရှေ့", callback_data=f"page_{max(0, start_num-25)}"), types.InlineKeyboardButton("နောက် ➡️", callback_data=f"page_{min(75, start_num+25)}"))
    markup.row(types.InlineKeyboardButton("⚡ ပါဝါ", callback_data="sp_power"), types.InlineKeyboardButton("🪐 နက္ခတ်", callback_data="sp_nat"), types.InlineKeyboardButton("👬 ညီကို", callback_data="sp_bro"))
    markup.row(types.InlineKeyboardButton("🛑 ဘရိတ်", callback_data="sp_brake"), types.InlineKeyboardButton("🔝 ထိပ်စီး", callback_data="sp_head"), types.InlineKeyboardButton("🔚 နောက်ပိတ်", callback_data="sp_tail"))
    markup.row(types.InlineKeyboardButton("💎 အပူး", callback_data="sp_double"), types.InlineKeyboardButton("🌀 ပတ်သီး", callback_data="sp_patthee"))
    if selected_list: markup.row(types.InlineKeyboardButton(f"✅ {len(selected_list)} လုံး ထိုးမည်", callback_data="confirm"))
    return markup

def process_final_bet(message):
    cid = message.chat.id
    try:
        if not message.text.isdigit():
            msg = bot.send_message(cid, "⚠️ ဂဏန်းသက်သက်ပဲ ရိုက်ပါ။")
            bot.register_next_step_handler(msg, process_final_bet)
            return
        amt = int(message.text)
        if amt < 100 or amt > 500000:
            msg = bot.send_message(cid, "❌ တစ်ကွက်လျှင် ၁၀၀ မှ ၅ သိန်းထိပဲ လက်ခံပါတယ်။ ပြန်ရိုက်ပါ:")
            bot.register_next_step_handler(msg, process_final_bet)
            return
        nums = [n for n in user_data[cid]['selected'] if n not in closed_numbers]
        if not nums:
            bot.send_message(cid, "❌ သင်ရွေးချယ်ထားသော ဂဏန်းများအားလုံး ပိတ်သွားပါပြီ။", reply_markup=set_main_menu(cid))
            return
        total = amt * len(nums)
        current_bal = get_balance(cid)
        if current_bal < total:
            bot.send_message(cid, f"❌ လက်ကျန်မလောက်ပါ။\nလိုအပ်ငွေ: {total} MMK\nလက်ရှိ: {current_bal} MMK", reply_markup=set_main_menu(cid))
            return
        today = datetime.now(mm_tz).strftime('%Y-%m-%d')
        update_balance(cid, -total)
        with sqlite3.connect('2d_betting.sqlite', timeout=20) as conn:
            for n in nums:
                conn.execute("INSERT INTO history (user_id, num, amount, date, session) VALUES (?, ?, ?, ?, ?)", (cid, n, amt, today, user_data[cid]['session']))
        admin_noti = (
            f"🎰 **ဂဏန်းထိုးစာရင်းအသစ်**\n\n"
            f"👤 အမည်: {message.from_user.first_name}\n"
            f"🆔 ID: `{cid}`\n"
            f"🕒 ပွဲစဉ်: {user_data[cid]['session']}\n"
            f"🔢 ဂဏန်းများ: {', '.join(nums)}\n"
            f"💰 တစ်ကွက်နှုန်း: {amt} MMK\n"
            f"💵 စုစုပေါင်း: {total} MMK"
        )
        bot.send_message(ADMIN_ID, admin_noti, parse_mode="Markdown")
        bot.send_message(cid, f"✅ **အောင်မြင်စွာ ထိုးပြီးပါပြီ**\n\n🔢 ဂဏန်းများ: {', '.join(nums)}\n💰 စုစုပေါင်း: {total} MMK\n💳 လက်ကျန်: **{get_balance(cid)}** MMK", reply_markup=set_main_menu(cid))
        if cid in user_data: del user_data[cid]
    except Exception as e:
        bot.send_message(cid, "⚠️ အမှားအယွင်းတစ်ခု ဖြစ်သွားပါတယ်။ တစ်ကျော့ပြန်ပြန်ထိုးပေးပါ။", reply_markup=set_main_menu(cid))

# --- Admin Functions (Original Commands) ---
@bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID and m.text == "🛠 Admin Panel")
def admin_panel(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("📊 Report", "👥 Users", "🛠 Maintenance")
    markup.row("🔄 Back to Main Menu")

    # Inline Buttons for Admin Controls
    ctrl_markup = types.InlineKeyboardMarkup()
    ctrl_markup.row(types.InlineKeyboardButton("🏆 ပေါက်သီးထုတ်ရန်", callback_data="admin_win"))
    ctrl_markup.row(types.InlineKeyboardButton("🚫 ဂဏန်းပိတ်ရန်", callback_data="admin_close"), types.InlineKeyboardButton("✅ ဂဏန်းဖွင့်ရန်", callback_data="admin_open"))
    ctrl_markup.row(types.InlineKeyboardButton("🚫 User Ban ရန်", callback_data="admin_ban"), types.InlineKeyboardButton("✅ User Unban ရန်", callback_data="admin_unban"))

    bot.send_message(ADMIN_ID, "🛠 **Admin Control Panel**\n\nအောက်ပါခလုတ်များကို အသုံးပြုနိုင်သည် (သို့မဟုတ်) Keywords များသုံးနိုင်သည်:", reply_markup=markup)
    bot.send_message(ADMIN_ID, "Quick Actions:", reply_markup=ctrl_markup)

# Admin Btn Step Handlers
def close_num_by_btn(message):
    if not message.text.isdigit(): return
    num = message.text.zfill(2)
    closed_numbers.add(num)
    bot.send_message(ADMIN_ID, f"🚫 {num} ကို ပိတ်လိုက်ပါပြီ။")

def open_num_by_btn(message):
    if not message.text.isdigit(): return
    num = message.text.zfill(2)
    closed_numbers.discard(num)
    bot.send_message(ADMIN_ID, f"✅ {num} ကို ပြန်ဖွင့်လိုက်ပါပြီ။")

def ban_user_by_btn(message):
    if not message.text.isdigit(): return
    uid = message.text
    with sqlite3.connect('2d_betting.sqlite') as conn:
        conn.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (uid,))
    bot.send_message(ADMIN_ID, f"🚫 User ID: `{uid}` ကို Ban လိုက်ပါပြီ။")

def unban_user_by_btn(message):
    if not message.text.isdigit(): return
    uid = message.text
    with sqlite3.connect('2d_betting.sqlite') as conn:
        conn.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (uid,))
    bot.send_message(ADMIN_ID, f"✅ User ID: `{uid}` ကို ပြန်ဖွင့်ပေးလိုက်ပါပြီ။")

def win_declare_by_btn(message, cmd_prefix):
    try:
        win_num = message.text.zfill(2)
        sess_name = {'!p1': '9:30 AM', '!p2': '12:00 PM', '!p3': '4:30 PM'}[cmd_prefix]
        today = datetime.now(mm_tz).strftime('%Y-%m-%d')
        with sqlite3.connect('2d_betting.sqlite', timeout=20) as conn:
            winners = conn.execute("SELECT user_id, amount FROM history WHERE num = ? AND session = ? AND date = ?", (win_num, sess_name, today)).fetchall()
            for w in winners:
                win_amount = w[1] * 80
                update_balance(w[0], win_amount)
                try: bot.send_message(w[0], f"🎉 ဂုဏ်ယူပါတယ်! {sess_name} ပွဲစဉ်မှာ {win_num} ဖြင့် {win_amount:,} MMK ပေါက်ပါသည်။")
                except: pass
        bot.send_message(ADMIN_ID, f"✅ {sess_name} အတွက် {win_num} ထုတ်ပြန်ပြီး။")
    except: pass

@bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID and m.text == "🔄 Back to Main Menu")
def back_to_main(message):
    bot.send_message(ADMIN_ID, "ပင်မမီနူးသို့ ပြန်ရောက်ပါပြီ။", reply_markup=set_main_menu(ADMIN_ID))

@bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID and m.text.startswith('!ban'))
def ban_user(message):
    try:
        uid = message.text.split()[1]
        with sqlite3.connect('2d_betting.sqlite') as conn:
            conn.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (uid,))
        bot.send_message(ADMIN_ID, f"🚫 User ID: `{uid}` ကို Ban လိုက်ပါပြီ။")
    except: bot.send_message(ADMIN_ID, "⚠️ အသုံးပြုပုံ: !ban [user_id]")

@bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID and m.text.startswith('!unban'))
def unban_user(message):
    try:
        uid = message.text.split()[1]
        with sqlite3.connect('2d_betting.sqlite') as conn:
            conn.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (uid,))
        bot.send_message(ADMIN_ID, f"✅ User ID: `{uid}` ကို ပြန်ဖွင့်ပေးလိုက်ပါပြီ။")
    except: bot.send_message(ADMIN_ID, "⚠️ အသုံးပြုပုံ: !unban [user_id]")

@bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID and m.text.startswith('!close'))
def close_num(message):
    try:
        num = message.text.split()[1].zfill(2)
        closed_numbers.add(num)
        bot.send_message(ADMIN_ID, f"🚫 {num} ကို ပိတ်လိုက်ပါပြီ။")
    except: pass

@bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID and m.text.startswith('!open'))
def open_num(message):
    try:
        num = message.text.split()[1].zfill(2)
        closed_numbers.discard(num)
        bot.send_message(ADMIN_ID, f"✅ {num} ကို ပြန်ဖွင့်လိုက်ပါပြီ။")
    except: pass

@bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID and (m.text == "🛠 Maintenance" or m.text == "!maintenance"))
def toggle_maintenance(message):
    global is_maintenance
    is_maintenance = not is_maintenance
    bot.send_message(ADMIN_ID, f"🛠 Maintenance Mode: **{'ON' if is_maintenance else 'OFF'}**")

@bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID and m.text.startswith('!broadcast'))
def broadcast(message):
    text = message.text.replace("!broadcast ", "")
    with sqlite3.connect('2d_betting.sqlite', timeout=20) as conn:
        users = conn.execute("SELECT user_id FROM users").fetchall()
    for u in users:
        try: bot.send_message(u[0], f"📢 **အထူးအသိပေးချက်**\n\n{text}")
        except: pass

@bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID and m.text.startswith(('!p1', '!p2', '!p3')))
def win_declare(message):
    try:
        cmd = message.text.split()
        win_num = cmd[1].zfill(2)
        sess_name = {'!p1': '9:30 AM', '!p2': '12:00 PM', '!p3': '4:30 PM'}[cmd[0]]
        today = datetime.now(mm_tz).strftime('%Y-%m-%d')
        with sqlite3.connect('2d_betting.sqlite', timeout=20) as conn:
            winners = conn.execute("SELECT user_id, amount FROM history WHERE num = ? AND session = ? AND date = ?", (win_num, sess_name, today)).fetchall()
            for w in winners:
                win_amount = w[1] * 80
                update_balance(w[0], win_amount)
                try: bot.send_message(w[0], f"🎉 ဂုဏ်ယူပါတယ်! {sess_name} ပွဲစဉ်မှာ {win_num} ဖြင့် {win_amount:,} MMK ပေါက်ပါသည်။")
                except: pass
        bot.send_message(ADMIN_ID, f"✅ {sess_name} အတွက် {win_num} ထုတ်ပြန်ပြီး။")
    except: pass

@bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID and (m.text == "📊 Report" or m.text == "!report"))
def report(message):
    today = datetime.now(mm_tz).strftime('%Y-%m-%d')
    with sqlite3.connect('2d_betting.sqlite', timeout=20) as conn:
        total = conn.execute("SELECT SUM(amount) FROM history WHERE date = ?", (today,)).fetchone()[0] or 0
    bot.send_message(ADMIN_ID, f"📊 ယနေ့အရောင်းစုစုပေါင်း: {total} MMK")

@bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID and (m.text == "👥 Users" or m.text == "!users"))
def list_users(message):
    with sqlite3.connect('2d_betting.sqlite', timeout=20) as conn:
        rows = conn.execute("SELECT user_id, username, balance FROM users").fetchall()
    txt = "\n".join([f"🆔 `{r[0]}` | {r[1]} | 💰 {r[2]} MMK" for r in rows])
    bot.send_message(ADMIN_ID, txt if txt else "User မရှိပါ။", parse_mode="Markdown")

# --- CORE COMMANDS ---
@bot.message_handler(commands=['start'])
def start(message):
    if is_user_banned(message.chat.id): return
    update_balance(message.chat.id, 0, message.from_user.first_name)
    welcome_text = (
        "မင်္ဂလာပါခင်ဗျာ... 🙏\n\n"
        "**'ရွှေလာဘ်' 2D Online ဝန်ဆောင်မှုမှ ကြိုဆိုပါတယ်။**\n\n"
        "ယုံကြည်မှုနဲ့အတူ ကံကောင်းခြင်း ရွှေလာဘ်များ ပိုင်ဆိုင်နိုင်ကြပါစေဗျာ။ 🍀"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=set_main_menu(message.chat.id))

@bot.message_handler(func=lambda m: m.text == "📜 စည်းကမ်းချက်")
def rules_handler(message):
    if is_user_banned(message.chat.id): return
    rules_text = (
        "📜 **'ရွှေလာဘ်' 2D စည်းကမ်းချက်များ**\n\n"
        "၁။ **ပေါက်ဂဏန်း** - ထိုင်းနိုင်ငံ Stock Exchange (SET) အပိတ်ဈေးနှုန်းမူရင်းအတိုင်း တိကျစွာ ပေါက်ကြေးပေးပါသည်။ 💹\n\n"
        "၂။ **ငွေသွင်း/ငွေထုတ်** - မနက် (၆:၀၀) မှ ည (၉:၀၀) အတွင်းသာ ဆောင်ရွက်ပေးပါသည်။ 🕒\n\n"
        "၃။ **ဂဏန်းပိတ်ချိန်** - ပွဲစဉ်မထွက်မီ (၁၀) မိနစ်အလိုတွင် ပိတ်ပါမည်။ သတိပြု၍ ကြိုတင်ထိုးပေးကြပါရန်။ ⚠️\n\n"
        "၄။ **ပြင်ဆင်ခွင့်** - ထိုးပြီးသားဂဏန်းများကို ပြန်ဖျက်ခြင်း/ပြင်ဆင်ခြင်း လုံးဝပြုလုပ်၍မရပါ။ ❌\n\n"
        "၅။ **ပေါက်ကြေး** - (၁) ကျပ်လျှင် (၈၀) ကျပ်နှုန်း တိကျစွာ ပေါက်ကြေးပေးပါသည်။ 💰\n\n"
        "၆။ **ဂဏန်းပိတ်ခြင်း** - ဂဏန်းအပြည့် (Limit) ဖြစ်သွားပါက Admin မှ အချိန်မရွေး ပိတ်ပိုင်ခွင့်ရှိသည်။ 🚫\n\n"
        "၇။ **နားရက်များ** - စနေ၊ တနင်္ဂနွေ နှင့် ရုံးပိတ်ရက်များတွင် ပိတ်ပါသည်။ 📅\n\n"
        "၈။ **အနည်းဆုံး/အများဆုံး** - တစ်ကွက်လျှင် ၁၀၀ ကျပ်မှ ၅ သိန်းထိ ထိုးနိုင်ပါသည်။ ⚖️\n\n"
        "၉။ **ငွေသွင်းခြင်း** - ငွေသွင်းပြီးပါက လုပ်ငန်းစဉ်အမှတ်ကို မှန်ကန်စွာ ပေးပို့ရပါမည်။ ငွေသွင်းပြီး (၁၅) မိနစ်အတွင်း ငွေမဝင်ပါက Admin ဆီသို့ တိုက်ရိုက်ဆက်သွယ်ပါ 📲\n\n"
        "၁၀။ **ဆုံးဖြတ်ချက်** - အငြင်းပွားမှုတစ်စုံတစ်ရာ ရှိလာပါက Admin ၏ ဆုံးဖြတ်ချက်သာ အတည်ဖြစ်ပါသည်။ ⚖️\n\n"
        "🔗 **Official Links:**\n"
        "ရွှေလာဘ်ချန်နယ် - https://t.me/ShweLattMain\n"
        "ရွှေလာဘ်စကားဝိုင်း - https://t.me/shwelattchat\n\n"
        "📩 သိလိုသည်များရှိပါက @ShwelabbCustomerService ထံသို့ အချိန်မရွေး ဆက်သွယ်နိုင်ပါသည်။"
    )
    bot.send_message(message.chat.id, rules_text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🔄 Bot ကို Restart လုပ်ရန်")
def user_restart(message):
    start(message)

@bot.message_handler(func=lambda m: m.text == "🎰 2D ထိုးမည်")
def session_menu(message):
    if is_user_banned(message.chat.id): return
    markup = types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton("🌅 9:30 AM", callback_data="sess_9:30 AM"),
        types.InlineKeyboardButton("☀️ 12:00 PM", callback_data="sess_12:00 PM"),
        types.InlineKeyboardButton("🌆 4:30 PM", callback_data="sess_4:30 PM")
    )
    bot.send_message(message.chat.id, "မည်သည့်ပွဲစဉ်အတွက် ထိုးမည်နည်း?", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "📜 မှတ်တမ်း")
def history_view(message):
    if is_user_banned(message.chat.id): return
    today = datetime.now(mm_tz).strftime('%Y-%m-%d')
    try:
        with sqlite3.connect('2d_betting.sqlite', timeout=20) as conn:
            rows = conn.execute("SELECT num, amount, session FROM history WHERE user_id = ? AND date = ?", (message.chat.id, today)).fetchall()
        if rows:
            txt = "📜 **ယနေ့မှတ်တမ်း**\n" + "\n".join([f"🔹 {r[0]} ({r[2]}) | {r[1]} MMK" for r in rows])
            bot.send_message(message.chat.id, txt, parse_mode="Markdown")
        else: bot.send_message(message.chat.id, "📅 မှတ်တမ်းမရှိသေးပါ။")
    except: pass

@bot.message_handler(func=lambda m: "လက်ကျန်:" in m.text)
def bal_check(message):
    bot.send_message(message.chat.id, f"💳 လက်ကျန်ငွေ: {get_balance(message.chat.id)} MMK")

bot.infinity_polling()