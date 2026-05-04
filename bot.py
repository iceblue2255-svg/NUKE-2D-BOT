import os
import sqlite3
import logging
from datetime import datetime
from flask import Flask, request
import telebot
from telebot import types
import pytz

# --- Configuration ---
API_TOKEN = os.environ.get('8280427701:AAFId7jPd4xY0FPPG6auBXqXAX5E_EOuKQc', 'YOUR_TOKEN_HERE')
ADMIN_ID = int(os.environ.get('7947267218', '0'))

# --- Logging ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Flask App ---
app = Flask(__name__)

# --- Bot Init ---
bot = telebot.TeleBot(API_TOKEN, threaded=True, num_threads=20)
user_data = {}
closed_numbers = set()
is_maintenance = False
mm_tz = pytz.timezone('Asia/Yangon')

# --- Database Setup ---
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

# --- Helper Functions ---
def is_user_banned(user_id):
    with sqlite3.connect('2d_betting.sqlite', timeout=20) as conn:
        res = conn.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return res[0] == 1 if res else False

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

# --- Flask Routes ---
@app.route('/')
def home():
    return "✅ NuKe 2D Bot is Running!"

@app.route(f'/{API_TOKEN}', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    else:
        return 'Error', 403

# --- Bot Handlers ---
@bot.message_handler(func=lambda m: is_user_banned(m.chat.id))
def handle_banned(message):
    bot.send_message(message.chat.id, "🚫 သင်၏အကောင့်မှာ စည်းကမ်းဖောက်ဖျက်မှုကြောင့် ပိတ်ပင်ခံထားရပါသည်။")

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

# [နင့်ရဲ့ ကျန်တဲ့ Handler တွေ ဒီမှာ ထည့်ထား]
# Deposit, Withdraw, Betting, Admin Panel, etc.

# --- Webhook Setup ---
def set_webhook():
    render_url = os.environ.get('RENDER_EXTERNAL_URL', '')
    if render_url:
        webhook_url = f"{render_url}/{API_TOKEN}"
        bot.remove_webhook()
        bot.set_webhook(url=webhook_url)
        logger.info(f"Webhook set to: {webhook_url}")

if __name__ == '__main__':
    set_webhook()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
