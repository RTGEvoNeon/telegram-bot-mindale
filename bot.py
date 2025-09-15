import os
import time
import psycopg2
from psycopg2.extras import RealDictCursor
import telebot
from telebot import types

# ====== Настройки ======
TOKEN = os.getenv("TOKEN")
CHANNEL = os.getenv("CHANNEL", "@FlowersMindale")

bot = telebot.TeleBot(TOKEN)

DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_NAME = os.getenv("DB_NAME", "botdb")
DB_USER = os.getenv("DB_USER", "botuser")
DB_PASS = os.getenv("DB_PASS", "botpass")

# ====== Подключение к БД с retry ======
def get_connection():
    while True:
        try:
            conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASS,
                cursor_factory=RealDictCursor
            )
            return conn
        except Exception as e:
            print(f"Ошибка подключения к базе: {e}. Повтор через 5 секунд...")
            time.sleep(5)

conn = get_connection()
cursor = conn.cursor()

# ====== Создание таблицы ======
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id BIGINT PRIMARY KEY,
    username TEXT,
    invited_by BIGINT,
    invites_count INT DEFAULT 0
);
""")
conn.commit()

# ====== /start ======
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.username or "no_username"

    args = message.text.split()
    invited_by = int(args[1]) if len(args) > 1 else None

    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()

    if not user:
        cursor.execute(
            "INSERT INTO users (id, username, invited_by) VALUES (%s, %s, %s)",
            (user_id, username, invited_by)
        )

        if invited_by:
            cursor.execute(
                "UPDATE users SET invites_count = invites_count + 1 WHERE id = %s",
                (invited_by,)
            )

        conn.commit()

    # Inline кнопка для подписки
    markup_inline = types.InlineKeyboardMarkup()
    btn_subscribe = types.InlineKeyboardButton("Подписаться на канал", url=f"https://t.me/{CHANNEL[1:]}")
    markup_inline.add(btn_subscribe)

    # Reply-клавиатура для кнопки "Мои приглашения"
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
    btn_stats = types.KeyboardButton("Мои приглашения")
    keyboard.add(btn_stats)

    # Сначала отправляем inline кнопки (подписка)
    bot.send_message(
        user_id,
        f"Привет, {username}!\nЧтобы участвовать, подпишись на канал {CHANNEL}.",
        reply_markup=markup_inline
    )

    # Потом отправляем reply-клавиатуру (статистика)
    bot.send_message(
        user_id,
        f"Твоя уникальная ссылка для приглашений:\nhttps://t.me/{bot.get_me().username}?start={user_id}",
        reply_markup=keyboard
    )

@bot.message_handler(func=lambda message: message.text == "Мои приглашения")
def show_stats(message):
    user_id = message.from_user.id
    cursor.execute("SELECT invites_count FROM users WHERE id = %s", (user_id,))
    row = cursor.fetchone()
    count = row['invites_count'] if row else 0
    bot.send_message(user_id, f"Ты пригласил {count} человек(а).")

# ====== Запуск бота ======
bot.infinity_polling()


