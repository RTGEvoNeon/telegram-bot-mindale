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

# ====== Проверка подписки ======
def is_subscribed(user_id):
    try:
        chat_member = bot.get_chat_member(CHANNEL, user_id)
        return chat_member.status in ["member", "creator", "administrator", "owner"]
    except Exception as e:
        print(f"Ошибка проверки подписки: {e}")
        return False

# ====== /start ======
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.username or "no_username"

    args = message.text.split()
    invited_by = int(args[1]) if len(args) > 1 else None

    # Проверяем пользователя в БД
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

    # Получаем количество приглашённых
    cursor.execute("SELECT invites_count FROM users WHERE id = %s", (user_id,))
    row = cursor.fetchone()
    invites_count = row['invites_count'] if row else 0

    # Клавиатура с красивым расположением кнопок
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
    keyboard.row(
        types.KeyboardButton("📩 Получить мою ссылку")
    )
    keyboard.row(
        types.KeyboardButton(f"👥 Мои приглашения ({invites_count})")
    )
    keyboard.row(types.KeyboardButton("🏆 Лидеры"))

    # Отправляем афишу
    with open("mindale.jpg", "rb") as photo:
        bot.send_photo(
            user_id,
            photo,
            caption=f"Привет, {username}! 🎉 Участвуй в розыгрыше — подпишись и приглашай друзей!"
        )

    # Отправляем клавиатуру отдельным сообщением
    bot.send_message(
        user_id,
        "Выбери действие 👇",
        reply_markup=keyboard
    )


# ====== Кнопка: получить ссылку ======
@bot.message_handler(func=lambda message: message.text == "📩 Получить мою ссылку")
def get_link(message):
    user_id = message.from_user.id

    if is_subscribed(user_id):
        bot.send_message(
            user_id,
            f"✅ Отлично! Ты подписан.\n"
            f"Вот твоя уникальная ссылка для приглашений:\n"
            f"https://t.me/{bot.get_me().username}?start={user_id}"
        )
    else:
        markup_inline = types.InlineKeyboardMarkup()
        btn_subscribe = types.InlineKeyboardButton("Подписаться на канал", url=f"https://t.me/{CHANNEL[1:]}")
        markup_inline.add(btn_subscribe)
        bot.send_message(
            user_id,
            "❌ Чтобы получить уникальную ссылку, сначала подпишись на канал:",
            reply_markup=markup_inline
        )

# ====== Кнопка: статистика ======
@bot.message_handler(func=lambda message: message.text.startswith("👥 Мои приглашения"))
def show_invitees(message):
    user_id = message.from_user.id
    cursor.execute("SELECT username FROM users WHERE invited_by = %s", (user_id,))
    rows = cursor.fetchall()
    
    if rows:
        invitees = "\n".join([f"- @{row['username']}" if row['username'] else "- (без username)" for row in rows])
        bot.send_message(user_id, f"📋 Ты пригласил следующих людей:\n{invitees}")
    else:
        bot.send_message(user_id, "❌ Пока никто не пришёл по твоей ссылке.")

# ====== Кнопка: лидеры ======
@bot.message_handler(func=lambda message: message.text == "🏆 Лидеры")
def show_leaders(message):
    cursor.execute("""
        SELECT username, invites_count 
        FROM users 
        ORDER BY invites_count DESC 
        LIMIT 15
    """)
    rows = cursor.fetchall()

    if not rows:
        bot.send_message(message.chat.id, "❌ Пока нет лидеров.")
        return

    text_parts = []

    # 🥇 Победитель
    first = rows[0]
    first_username = f"@{first['username']}" if first['username'] else "(без username)"
    text_parts.append(
        f"Положение на сегодня, но все может поменяться! 🏆\n\n"
        f"🎁Получает купон **3000₽** и мист *Victoria’s Secret!*\n"
        f"- {first_username} — {first['invites_count']} приглашений\n"
    )

    # 🥈 2–10 места
    if len(rows) > 1:
        text_parts.append("\n🎁 Получают мист *Victoria’s Secret!*\n")
        for row in rows[1:10]:
            username = f"@{row['username']}" if row['username'] else "(без username)"
            text_parts.append(f"- {username} — {row['invites_count']} приглашений")

    #  Остальные 11–15
    if len(rows) > 10:
        text_parts.append("\n🥉 Чуть-чуть не хватает до приза:\n")
        for row in rows[10:]:
            username = f"@{row['username']}" if row['username'] else "(без username)"
            text_parts.append(f"- {username} — {row['invites_count']} приглашений")

    bot.send_message(
        message.chat.id,
        "\n".join(text_parts),
        parse_mode="Markdown"
    )
# ====== Запуск бота ======
bot.infinity_polling()
