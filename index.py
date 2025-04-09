import json
import sqlite3
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, CallbackContext, filters
from threading import Timer

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

with open('config.json', 'r') as f:
    config = json.load(f)
token = config["TOKEN"]

# Создание базы данных и таблиц
def create_db():
    conn = sqlite3.connect('reminders.db')
    c = conn.cursor()

    # Создание таблицы команд
    c.execute('''CREATE TABLE IF NOT EXISTS teams (
                    id INTEGER PRIMARY KEY,
                    name TEXT)''')

    # Создание таблицы напоминаний
    c.execute('''CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER,
                    message TEXT,
                    time TEXT,
                    is_group BOOLEAN)''')

    conn.commit()
    conn.close()

# Функция проверки напоминаний
def check_reminders(context: CallbackContext):
    conn = sqlite3.connect('reminders.db')
    c = conn.cursor()
    c.execute("SELECT user_id, message FROM reminders WHERE time <= datetime('now') AND is_group = 0")
    reminders = c.fetchall()
    
    for user_id, message in reminders:
        context.bot.send_message(chat_id=user_id, text=message)
        c.execute("DELETE FROM reminders WHERE user_id = ? AND message = ?", (user_id, message))

    conn.commit()
    conn.close()
    Timer(60, check_reminders, [context]).start()  # Проверка каждую минуту

# Начальная команда
def start(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("Команды", callback_data='commands')],
        [InlineKeyboardButton("Личные напоминания", callback_data='personal_reminders')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text('Выберите опцию:', reply_markup=reply_markup)

# Обработка нажатий на кнопки
def button(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()

    if query.data == 'commands':
        keyboard = [
            [InlineKeyboardButton("Создать команду", callback_data='create_team')],
            [InlineKeyboardButton("Просмотреть команды", callback_data='view_teams')],
            [InlineKeyboardButton("Назад", callback_data='back')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text(text="Выберите действие:", reply_markup=reply_markup)

    elif query.data == 'personal_reminders':
        keyboard = [
            [InlineKeyboardButton("Создать напоминание", callback_data='create_reminder')],
            [InlineKeyboardButton("Просмотреть напоминания", callback_data='view_reminders')],
            [InlineKeyboardButton("Назад", callback_data='back')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text(text="Выберите действие:", reply_markup=reply_markup)

    elif query.data == 'back':
        start(update, context)

    elif query.data == 'create_team':
        query.edit_message_text(text="Введите название команды:")
        return

    elif query.data == 'view_teams':
        # Логика для просмотра команд
        pass

    elif query.data == 'create_reminder':
        query.edit_message_text(text="Введите ваше напоминание:")
        return

    elif query.data == 'view_reminders':
        # Логика для просмотра напоминаний
        pass

# Обработка текстовых сообщений
def handle_message(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    text = update.message.text

    if update.message.reply_to_message:

        if "Введите название команды:" in update.message.reply_to_message.text:
            # Логика для создания команды
            create_team(user_id, text)
            update.message.reply_text(f"Команда '{text}' создана.")
            start(update, context)

        elif "Введите ваше напоминание:" in update.message.reply_to_message.text:
            # Логика для создания напоминания
            create_reminder(user_id, text)
            update.message.reply_text(f"Напоминание '{text}' создано.")
            start(update, context)

# Функция для создания команды в базе данных
def create_team(user_id, team_name):
    conn = sqlite3.connect('reminders.db')
    c = conn.cursor()
    c.execute("INSERT INTO teams (name) VALUES (?)", (team_name,))
    conn.commit()
    conn.close()

# Функция для создания личного напоминания в базе данных
def create_reminder(user_id, reminder_text):
    conn = sqlite3.connect('reminders.db')
    c = conn.cursor()
    c.execute("INSERT INTO reminders (user_id, message, time, is_group) VALUES (?, ?, datetime('now', '+1 minute'), ?)", (user_id, reminder_text, False))
    conn.commit()
    conn.close()

def main():
    create_db()
    global updater
    updater = ApplicationBuilder().token(token).build()
    updater.add_handler(CommandHandler("start", start))
    updater.add_handler(CallbackQueryHandler(button))
    updater.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Запуск проверки напоминаний
    check_reminders(None)

    updater.run_polling()
    updater.idle()

if __name__ == '__main__':
    main()
