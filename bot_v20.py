
"""
Telegram бот для управления напоминаниями и командами
Версия для python-telegram-bot 20.4 и Python 3.13
"""

import json
import logging
import sqlite3
import os
from datetime import datetime, time
import calendar
from typing import Dict, List, Any, Optional, Union

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

with open("config.json") as f:
    config=json.load(f)
TOKEN=config["TOKEN"]

# Константы для ConversationHandler
MENU, TEAM, TEAM_NAME, TEAM_MEMBERS, TEAM_VIEW = range(5)
REMINDER, REMINDER_CREATE, REMINDER_TEAM, REMINDER_TEXT, REMINDER_DATE, REMINDER_TIME, REMINDER_VIEW = range(5, 12)
INVITES, INVITE_ACTIONS, TEAM_LEAVE = range(12, 15)  # Новые состояния для управления приглашениями и выходом из команды

# Хранилище данных пользователя
user_data_dict: Dict[int, Dict[str, Any]] = {}

# Класс для работы с базой данных
class Database:
    def __init__(self, db_name="bot_database.db"):
        """Инициализация базы данных."""
        self.db_name = db_name
        self.conn = None
        self.cursor = None
        self.connect()
        self.create_tables()
    
    def connect(self):
        """Подключение к базе данных."""
        try:
            self.conn = sqlite3.connect(self.db_name)
            self.conn.row_factory = sqlite3.Row  # Возвращать результаты как словари
            self.cursor = self.conn.cursor()
            logger.info(f"Успешное подключение к базе данных {self.db_name}")
        except sqlite3.Error as e:
            logger.error(f"Ошибка подключения к базе данных: {e}")
    
    def create_tables(self):
        """Создание таблиц в базе данных."""
        try:
            # Таблица команд
            self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                members TEXT NOT NULL,
                created_by INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            # Таблица напоминаний
            self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                reminder_time TEXT NOT NULL,
                reminder_text TEXT NOT NULL,
                team_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            # Таблица приглашений в команды
            self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS team_invites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id INTEGER NOT NULL,
                team_name TEXT NOT NULL,
                invited_username TEXT NOT NULL,
                invited_by INTEGER NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (team_id) REFERENCES teams (id)
            )
            ''')
            
            self.conn.commit()
            logger.info("Таблицы успешно созданы или уже существуют")
        except sqlite3.Error as e:
            logger.error(f"Ошибка создания таблиц: {e}")
    
    def add_team(self, name, members, created_by):
        """Добавление новой команды в базу данных."""
        try:
            # Сохраняем список участников как строку JSON
            members_json = json.dumps(members)
            
            self.cursor.execute(
                "INSERT INTO teams (name, members, created_by) VALUES (?, ?, ?)",
                (name, members_json, created_by)
            )
            self.conn.commit()
            logger.info(f"Команда '{name}' успешно добавлена")
            return True
        except sqlite3.Error as e:
            logger.error(f"Ошибка добавления команды: {e}")
            return False
    
    def get_teams(self, user_id=None):
        """Получение списка команд."""
        try:
            if user_id:
                # Получаем команды, где пользователь является участником
                self.cursor.execute("SELECT * FROM teams")
                all_teams = self.cursor.fetchall()
                
                user_teams = []
                for team in all_teams:
                    members = json.loads(team['members'])
                    if user_id in members:
                        user_teams.append({
                            'id': team['id'],
                            'name': team['name'],
                            'members': members,
                            'created_by': team['created_by']
                        })
                
                return user_teams
            else:
                # Получаем все команды
                self.cursor.execute("SELECT * FROM teams")
                teams = self.cursor.fetchall()
                
                return [{
                    'id': team['id'],
                    'name': team['name'],
                    'members': json.loads(team['members']),
                    'created_by': team['created_by']
                } for team in teams]
                
        except sqlite3.Error as e:
            logger.error(f"Ошибка получения команд: {e}")
            return []
    
    def add_reminder(self, user_id, reminder_time, reminder_text, team_name=None):
        """Добавление нового напоминания в базу данных."""
        try:
            self.cursor.execute(
                "INSERT INTO reminders (user_id, reminder_time, reminder_text, team_name) VALUES (?, ?, ?, ?)",
                (user_id, reminder_time, reminder_text, team_name)
            )
            self.conn.commit()
            logger.info(f"Напоминание успешно добавлено для пользователя {user_id}")
            return True
        except sqlite3.Error as e:
            logger.error(f"Ошибка добавления напоминания: {e}")
            return False
    
    def get_reminders(self, user_id=None, team_name=None):
        """Получение списка напоминаний."""
        try:
            if user_id and team_name:
                # Получаем напоминания для пользователя и команды
                self.cursor.execute(
                    "SELECT * FROM reminders WHERE user_id = ? AND team_name = ?",
                    (user_id, team_name)
                )
            elif user_id:
                # Получаем все напоминания пользователя
                self.cursor.execute(
                    "SELECT * FROM reminders WHERE user_id = ? OR team_name IN (SELECT name FROM teams WHERE members LIKE ?)",
                    (user_id, f"%{user_id}%")
                )
            elif team_name:
                # Получаем напоминания для команды
                self.cursor.execute(
                    "SELECT * FROM reminders WHERE team_name = ?",
                    (team_name,)
                )
            else:
                # Получаем все напоминания
                self.cursor.execute("SELECT * FROM reminders")
            
            reminders = self.cursor.fetchall()
            
            return [{
                'id': reminder['id'],
                'user_id': reminder['user_id'],
                'reminder_time': reminder['reminder_time'],
                'reminder_text': reminder['reminder_text'],
                'team_name': reminder['team_name']
            } for reminder in reminders]
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка получения напоминаний: {e}")
            return []
    
    def add_team_invite(self, team_id, team_name, invited_username, invited_by):
        """Добавление приглашения в команду.
        
        Args:
            team_id (int): ID команды
            team_name (str): Название команды
            invited_username (str): Username приглашаемого
            invited_by (int): ID пользователя, отправившего приглашение
            
        Returns:
            int: ID приглашения или None при ошибке
        """
        try:
            self.cursor.execute(
                "INSERT INTO team_invites (team_id, team_name, invited_username, invited_by) VALUES (?, ?, ?, ?)",
                (team_id, team_name, invited_username, invited_by)
            )
            self.conn.commit()
            invite_id = self.cursor.lastrowid
            logger.info(f"Создано приглашение #{invite_id} для пользователя {invited_username} в команду {team_name}")
            return invite_id
        except sqlite3.Error as e:
            logger.error(f"Ошибка создания приглашения: {e}")
            return None
            
    def get_pending_invites(self, username=None):
        """Получение ожидающих приглашений.
        
        Args:
            username (str, optional): Фильтр по username пользователя
            
        Returns:
            list: Список приглашений
        """
        try:
            if username:
                self.cursor.execute(
                    "SELECT * FROM team_invites WHERE invited_username = ? AND status = 'pending'",
                    (username,)
                )
            else:
                self.cursor.execute("SELECT * FROM team_invites WHERE status = 'pending'")
                
            invites = self.cursor.fetchall()
            
            return [{
                'id': invite['id'],
                'team_id': invite['team_id'],
                'team_name': invite['team_name'],
                'invited_username': invite['invited_username'],
                'invited_by': invite['invited_by'],
                'created_at': invite['created_at']
            } for invite in invites]
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка получения приглашений: {e}")
            return []
            
    def update_invite_status(self, invite_id, status):
        """Обновление статуса приглашения.
        
        Args:
            invite_id (int): ID приглашения
            status (str): Новый статус ('accepted', 'rejected', 'canceled')
            
        Returns:
            bool: Успех операции
        """
        try:
            self.cursor.execute(
                "UPDATE team_invites SET status = ? WHERE id = ?",
                (status, invite_id)
            )
            self.conn.commit()
            logger.info(f"Статус приглашения #{invite_id} изменен на {status}")
            return True
        except sqlite3.Error as e:
            logger.error(f"Ошибка обновления статуса приглашения: {e}")
            return False
            
    def add_user_to_team(self, team_id, user_id):
        """Добавление пользователя в команду.
        
        Args:
            team_id (int): ID команды
            user_id (int): ID пользователя
            
        Returns:
            bool: Успех операции
        """
        try:
            # Получаем текущий список участников
            self.cursor.execute("SELECT members FROM teams WHERE id = ?", (team_id,))
            team = self.cursor.fetchone()
            
            if not team:
                logger.error(f"Команда с ID {team_id} не найдена")
                return False
                
            members = json.loads(team['members'])
            
            # Проверяем, не состоит ли пользователь уже в команде
            if user_id in members:
                logger.info(f"Пользователь {user_id} уже состоит в команде {team_id}")
                return True
                
            # Добавляем пользователя в список
            members.append(user_id)
            members_json = json.dumps(members)
            
            # Обновляем список участников команды
            self.cursor.execute(
                "UPDATE teams SET members = ? WHERE id = ?",
                (members_json, team_id)
            )
            self.conn.commit()
            logger.info(f"Пользователь {user_id} добавлен в команду {team_id}")
            return True
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка добавления пользователя в команду: {e}")
            return False
            
    def remove_user_from_team(self, team_id, user_id):
        """Удаление пользователя из команды.
        
        Args:
            team_id (int): ID команды
            user_id (int): ID пользователя
            
        Returns:
            bool: Успех операции
        """
        try:
            # Получаем текущий список участников и данные о команде
            self.cursor.execute("SELECT members, created_by FROM teams WHERE id = ?", (team_id,))
            team = self.cursor.fetchone()
            
            if not team:
                logger.error(f"Команда с ID {team_id} не найдена")
                return False
                
            members = json.loads(team['members'])
            created_by = team['created_by']
            
            # Проверяем, состоит ли пользователь в команде
            if user_id not in members:
                logger.info(f"Пользователь {user_id} не состоит в команде {team_id}")
                return True
                
            # Удаляем пользователя из списка
            members.remove(user_id)
            members_json = json.dumps(members)
            
            # Обновляем список участников команды
            self.cursor.execute(
                "UPDATE teams SET members = ? WHERE id = ?",
                (members_json, team_id)
            )
            self.conn.commit()
            logger.info(f"Пользователь {user_id} удален из команды {team_id}")
            return True
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка удаления пользователя из команды: {e}")
            return False
            
    def delete_reminder(self, reminder_id):
        """Удаление напоминания.
        
        Args:
            reminder_id (int): ID напоминания
            
        Returns:
            bool: Успех операции
        """
        try:
            self.cursor.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
            self.conn.commit()
            logger.info(f"Напоминание {reminder_id} удалено")
            return True
        except sqlite3.Error as e:
            logger.error(f"Ошибка удаления напоминания: {e}")
            return False
            
    def delete_team(self, team_id):
        """Удаление команды.
        
        Args:
            team_id (int): ID команды
            
        Returns:
            bool: Успех операции
        """
        try:
            # Получаем информацию о команде
            team = self.get_team_by_id(team_id)
            if not team:
                logger.error(f"Команда с ID {team_id} не найдена")
                return False
                
            # Удаляем связанные напоминания
            self.cursor.execute("DELETE FROM reminders WHERE team_name = ?", (team['name'],))
            
            # Удаляем команду
            self.cursor.execute("DELETE FROM teams WHERE id = ?", (team_id,))
            
            # Отменяем все приглашения в эту команду
            self.cursor.execute(
                "UPDATE team_invites SET status = 'canceled' WHERE team_id = ? AND status = 'pending'", 
                (team_id,)
            )
            
            self.conn.commit()
            logger.info(f"Команда {team_id} удалена")
            return True
        except sqlite3.Error as e:
            logger.error(f"Ошибка удаления команды: {e}")
            return False
            
    def get_team_by_id(self, team_id):
        """Получение информации о команде по ID.
        
        Args:
            team_id (int): ID команды
            
        Returns:
            dict: Информация о команде или None при ошибке
        """
        try:
            self.cursor.execute("SELECT * FROM teams WHERE id = ?", (team_id,))
            team = self.cursor.fetchone()
            
            if not team:
                return None
                
            return {
                'id': team['id'],
                'name': team['name'],
                'members': json.loads(team['members']),
                'created_by': team['created_by']
            }
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка получения информации о команде: {e}")
            return None
            
    def get_invite_by_id(self, invite_id):
        """Получение информации о приглашении по ID.
        
        Args:
            invite_id (int): ID приглашения
            
        Returns:
            dict: Информация о приглашении или None при ошибке
        """
        try:
            self.cursor.execute("SELECT * FROM team_invites WHERE id = ?", (invite_id,))
            invite = self.cursor.fetchone()
            
            if not invite:
                return None
                
            return {
                'id': invite['id'],
                'team_id': invite['team_id'],
                'team_name': invite['team_name'],
                'invited_username': invite['invited_username'],
                'invited_by': invite['invited_by'],
                'status': invite['status'],
                'created_at': invite['created_at']
            }
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка получения информации о приглашении: {e}")
            return None
    
    def close(self):
        """Закрытие соединения с базой данных."""
        if self.conn:
            self.conn.close()
            logger.info("Соединение с базой данных закрыто")

# Инициализация базы данных
db = Database()

# Обработчики сообщений для бота

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отображение главного меню с кнопками."""
    user = update.effective_user
    username = user.username
    
    # Проверяем наличие приглашений для пользователя
    if username:
        invites = db.get_pending_invites(username)
        invites_count = len(invites)
        invite_button_text = f"Приглашения ({invites_count})" if invites_count > 0 else "Приглашения"
    else:
        invite_button_text = "Приглашения"
        
    keyboard = [
        [InlineKeyboardButton("Команды", callback_data='commands'),
         InlineKeyboardButton("Личные напоминания", callback_data='personal_reminders')],
        [InlineKeyboardButton(invite_button_text, callback_data='invites')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Пожалуйста выберите:", reply_markup=reply_markup)
    return MENU

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора в главном меню."""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    # Проверяем наличие приглашений для пользователя
    if username:
        pending_invites = db.get_pending_invites(username)
        
        if pending_invites:
            # Если есть приглашения, показываем их
            invites_text = "У вас есть приглашения в команды:\n\n"
            keyboard = []
            
            for invite in pending_invites:
                invites_text += f"👥 Команда: {invite['team_name']}\n"
                keyboard.append([
                    InlineKeyboardButton("✅ Принять", callback_data=f"accept_invite_{invite['id']}"),
                    InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_invite_{invite['id']}")
                ])
            
            keyboard.append([InlineKeyboardButton("В главное меню", callback_data="back_to_main")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(invites_text, reply_markup=reply_markup)
            return INVITES
    
    # Обычная обработка главного меню, если нет приглашений
    if query.data == 'commands':
        # Переход в меню команд
        keyboard = [
            [InlineKeyboardButton("Создать команду", callback_data='create_team'),
             InlineKeyboardButton("Просмотреть команды", callback_data='view_teams')],
            [InlineKeyboardButton("Выйти из команды", callback_data='leave_team')],
            [InlineKeyboardButton("Назад", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Выберите действие с командами:", reply_markup=reply_markup)
        return TEAM
    
    elif query.data == 'personal_reminders':
        # Переход в меню напоминаний
        keyboard = [
            [InlineKeyboardButton("Создать напоминание", callback_data='create_reminder'),
             InlineKeyboardButton("Просмотреть напоминания", callback_data='view_reminders')],
            [InlineKeyboardButton("Назад", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Выберите действие с напоминаниями:", reply_markup=reply_markup)
        return REMINDER
    
    # Главное меню
    keyboard = [
        [InlineKeyboardButton("Команды", callback_data='commands'),
         InlineKeyboardButton("Личные напоминания", callback_data='personal_reminders')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Пожалуйста выберите:", reply_markup=reply_markup)
    return MENU
async def team_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка меню команд."""
    query = update.callback_query
    await query.answer()

    if query.data == 'create_team':
        await query.edit_message_text("Введите название команды:")
        return TEAM_NAME
    
    elif query.data == 'view_teams':
        user_id = update.effective_user.id
        teams = db.get_teams(user_id)
        
        if not teams:
            keyboard = [[InlineKeyboardButton("Назад", callback_data='back_to_team')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("У вас нет команд. Создайте новую команду.", reply_markup=reply_markup)
            return TEAM
        
        # Отображение команд
        team_text = "Ваши команды:\n\n"
        for i, team in enumerate(teams, 1):
            member_count = len(team['members'])
            team_text += f"{i}. {team['name']} - {member_count} участников\n"
        
        keyboard = [[InlineKeyboardButton("Назад", callback_data='back_to_team')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(team_text, reply_markup=reply_markup)
        return TEAM_VIEW

    elif query.data == 'delete_team':
        # Проверяем, состоит ли пользователь в каких-либо командах
        user_id = update.effective_user.id
        teams = db.get_teams(user_id)
        
        if not teams:
            keyboard = [[InlineKeyboardButton("Назад", callback_data='back_to_team')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "У вас нет команд для удаления.",
                reply_markup=reply_markup
            )
            return TEAM
            
        # Показываем список команд для удаления
        delete_text = "Выберите команду для удаления:\n\n"
        keyboard = []
        
        for team in teams:
            # Проверяем, является ли пользователь создателем команды
            if team['created_by'] == user_id:
                delete_text += f"📋 {team['name']} (вы создатель)\n"
                keyboard.append([InlineKeyboardButton(f"Удалить команду {team['name']}", callback_data=f"confirm_delete_{team['id']}")])
            else:
                delete_text += f"📋 {team['name']} (вы участник, но не создатель)\n"
                
        keyboard.append([InlineKeyboardButton("Назад", callback_data='back_to_team')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(delete_text, reply_markup=reply_markup)
        return TEAM
        
    elif query.data.startswith('confirm_delete_'):
        # Удаление команды
        user_id = update.effective_user.id
        team_id = int(query.data.split('_')[-1])
        team = db.get_team_by_id(team_id)
        
        if not team:
            await query.edit_message_text("Команда не найдена.")
            return ConversationHandler.END
            
        # Проверяем, является ли пользователь создателем команды
        if team['created_by'] != user_id:
            keyboard = [[InlineKeyboardButton("Назад", callback_data='delete_team')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "Вы не можете удалить эту команду, так как не являетесь её создателем.",
                reply_markup=reply_markup
            )
            return TEAM
            
        # Удаляем команду
        success = db.delete_team(team_id)
        
        if success:
            keyboard = [
                [InlineKeyboardButton("К командам", callback_data='back_to_team')],
                [InlineKeyboardButton("В главное меню", callback_data='back_to_main')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"Команда '{team['name']}' успешно удалена.\nВсе связанные напоминания и приглашения также удалены.",
                reply_markup=reply_markup
            )
            return TEAM
        else:
            await query.edit_message_text("Произошла ошибка при удалении команды.")
            return ConversationHandler.END
    
    elif query.data == 'back_to_team':
        keyboard = [
            [InlineKeyboardButton("Создать команду", callback_data='create_team'),
             InlineKeyboardButton("Просмотреть команды", callback_data='view_teams')],
            [InlineKeyboardButton("Удалить команду", callback_data='delete_team')],
            [InlineKeyboardButton("Назад", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Выберите действие с командами:", reply_markup=reply_markup)
        return TEAM
    
    elif query.data == 'back_to_main':
        return await menu_handler(update, context)
    
    return TEAM

async def team_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ввода названия команды."""
    team_name = update.message.text
    
    # Сохранение названия команды в данных пользователя
    user_id = update.effective_user.id
    if user_id not in user_data_dict:
        user_data_dict[user_id] = {}
    user_data_dict[user_id]['team_name'] = team_name
    
    # Инициализируем список участников команды
    user_data_dict[user_id]['team_members'] = []
    user_data_dict[user_id]['invited_usernames'] = []
    
    # Добавляем создателя команды в список участников
    user_data_dict[user_id]['team_members'].append(user_id)
    
    # Запрос участников команды
    await update.message.reply_text(
        "Введите username участников команды через запятую (например: @user1, @user2).\n"
        "Вы уже добавлены в команду как создатель.\n"
        "Введите 'готово', если не хотите добавлять участников."
    )
    return TEAM_MEMBERS

async def team_members_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ввода участников команды."""
    members_text = update.message.text
    user_id = update.effective_user.id
    
    # Если пользователь ввел "готово", сохраняем команду с текущими участниками
    if members_text.lower() == 'готово':
        team_name = user_data_dict[user_id]['team_name']
        
        # Сначала создаем команду только с создателем
        initial_members = [user_id]  # Только создатель в качестве начального участника
        success = db.add_team(team_name, initial_members, user_id)
        
        if success:
            # Получаем ID созданной команды
            teams = db.get_teams(user_id)
            team_id = None
            for team in teams:
                if team['name'] == team_name:
                    team_id = team['id']
                    break
            
            if team_id:
                # Отправка приглашений всем указанным пользователям
                invited_usernames = user_data_dict[user_id].get('invited_usernames', [])
                for username in invited_usernames:
                    invite_id = db.add_team_invite(team_id, team_name, username, user_id)
                    if invite_id:
                        logger.info(f"Создано приглашение #{invite_id} для пользователя {username} в команду {team_name}")
                
                keyboard = [
                    [InlineKeyboardButton("В главное меню", callback_data='back_to_main')],
                    [InlineKeyboardButton("К командам", callback_data='back_to_team')]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                invite_message = ""
                if invited_usernames:
                    invite_message = f"\n\nПриглашения отправлены пользователям: {', '.join(['@' + username for username in invited_usernames])}"
                
                await update.message.reply_text(
                    f"Команда '{team_name}' успешно создана!{invite_message}",
                    reply_markup=reply_markup
                )
            else:
                await update.message.reply_text("Произошла ошибка при создании команды. Не удалось получить ID команды.")
                return ConversationHandler.END
        else:
            await update.message.reply_text("Произошла ошибка при создании команды. Попробуйте еще раз.")
            return ConversationHandler.END
        
        return TEAM
    
    # Список для хранения username'ов для приглашения
    usernames = [username.strip().lstrip('@') for username in members_text.split(',')]
    if 'invited_usernames' not in user_data_dict[user_id]:
        user_data_dict[user_id]['invited_usernames'] = []
    user_data_dict[user_id]['invited_usernames'].extend(usernames)
    
    # Сохраняем имена пользователей для последующей идентификации
    for username in usernames:
        logger.info(f"Пользователь {user_id} добавил {username} в команду {user_data_dict[user_id]['team_name']}")
    
    # Информируем пользователя о приглашениях, которые будут отправлены
    await update.message.reply_text(
        f"После создания команды, пользователям {', '.join(['@' + username for username in usernames])} будут отправлены приглашения.\n\n"
        "Вы можете добавить ещё участников или ввести 'готово', чтобы завершить создание команды."
    )
    
    return TEAM_MEMBERS

async def reminder_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка меню напоминаний."""
    query = update.callback_query
    await query.answer()

    if query.data == 'create_reminder':
        keyboard = [
            [InlineKeyboardButton("Личное напоминание", callback_data='personal_reminder')],
            [InlineKeyboardButton("Напоминание для команды", callback_data='team_reminder')],
            [InlineKeyboardButton("Назад", callback_data='back_to_reminder')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Выберите тип напоминания:", reply_markup=reply_markup)
        return REMINDER_CREATE
    
    elif query.data == 'view_reminders':
        user_id = update.effective_user.id
        reminders = db.get_reminders(user_id=user_id)
        
        if not reminders:
            keyboard = [[InlineKeyboardButton("Назад", callback_data='back_to_reminder')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("У вас нет напоминаний.", reply_markup=reply_markup)
            return REMINDER
        
        # Сохраняем напоминания в user_data_dict для последующего использования
        if user_id not in user_data_dict:
            user_data_dict[user_id] = {}
        user_data_dict[user_id]['reminders'] = reminders
        
        # Отображение напоминаний
        reminder_text = "Ваши напоминания:\n\n"
        for i, reminder in enumerate(reminders, 1):
            reminder_time = datetime.fromisoformat(reminder['reminder_time']).strftime('%d.%m.%Y %H:%M')
            team_info = f" (Команда: {reminder['team_name']})" if reminder['team_name'] else ""
            reminder_text += f"{i}. {reminder_time}{team_info}\n{reminder['reminder_text']}\n\n"
        
        # Добавляем кнопки для удаления напоминаний
        keyboard = []
        for i, reminder in enumerate(reminders, 1):
            keyboard.append([InlineKeyboardButton(f"Удалить напоминание #{i}", callback_data=f"delete_reminder_{reminder['id']}")])
        
        keyboard.append([InlineKeyboardButton("Назад", callback_data='back_to_reminder')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(reminder_text, reply_markup=reply_markup)
        return REMINDER_VIEW
    
    elif query.data == 'leave_team_menu':
        # Проверяем, состоит ли пользователь в каких-либо командах
        user_id = update.effective_user.id
        teams = db.get_teams(user_id)
        
        if not teams:
            keyboard = [[InlineKeyboardButton("Назад", callback_data='back_to_reminder')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "Вы не состоите ни в одной команде.",
                reply_markup=reply_markup
            )
            return REMINDER
            
        # Показываем список команд для выхода
        leave_text = "Выберите команду, из которой хотите выйти:\n\n"
        keyboard = []
        
        for team in teams:
            # Проверяем, является ли пользователь создателем команды
            if team['created_by'] == user_id:
                leave_text += f"📋 {team['name']} (вы создатель)\n"
                keyboard.append([InlineKeyboardButton(f"Выйти из {team['name']}", callback_data=f"leave_creator_{team['id']}")])
            else:
                leave_text += f"📋 {team['name']}\n"
                keyboard.append([InlineKeyboardButton(f"Выйти из {team['name']}", callback_data=f"leave_member_{team['id']}")])
                
        keyboard.append([InlineKeyboardButton("Назад", callback_data='back_to_reminder')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(leave_text, reply_markup=reply_markup)
        return REMINDER
    
    elif query.data.startswith('leave_member_'):
        # Выход обычного участника из команды
        team_id = int(query.data.split('_')[-1])
        team = db.get_team_by_id(team_id)
        
        if not team:
            await query.edit_message_text("Команда не найдена.")
            return ConversationHandler.END
            
        user_id = update.effective_user.id
        # Удаляем пользователя из команды
        success = db.remove_user_from_team(team_id, user_id)
        
        if success:
            # Удаляем напоминания этой команды
            reminders = db.get_reminders(user_id, team_name=team['name'])
            for reminder in reminders:
                db.delete_reminder(reminder['id'])
                
            keyboard = [[InlineKeyboardButton("Назад", callback_data='back_to_reminder')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"Вы успешно вышли из команды '{team['name']}'. Все напоминания этой команды удалены.",
                reply_markup=reply_markup
            )
        else:
            await query.edit_message_text("Произошла ошибка при выходе из команды.")
            return ConversationHandler.END
            
        return REMINDER
    
    elif query.data.startswith('leave_creator_'):
        # Создатель выходит и удаляет команду
        team_id = int(query.data.split('_')[-1])
        team = db.get_team_by_id(team_id)
        
        if not team:
            await query.edit_message_text("Команда не найдена.")
            return ConversationHandler.END
            
        user_id = update.effective_user.id
        # Проверяем, является ли пользователь создателем команды
        if team['created_by'] != user_id:
            keyboard = [[InlineKeyboardButton("Назад", callback_data='leave_team_menu')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "Вы не можете удалить эту команду, так как не являетесь её создателем.",
                reply_markup=reply_markup
            )
            return REMINDER
            
        # Удаляем команду
        success = db.delete_team(team_id)
        
        if success:
            keyboard = [[InlineKeyboardButton("Назад", callback_data='back_to_reminder')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"Команда '{team['name']}' успешно удалена. Все связанные напоминания и приглашения удалены.",
                reply_markup=reply_markup
            )
        else:
            await query.edit_message_text("Произошла ошибка при удалении команды.")
            return ConversationHandler.END
            
        return REMINDER
    
    elif query.data == 'back_to_reminder':
        keyboard = [
            [InlineKeyboardButton("Создать напоминание", callback_data='create_reminder'),
             InlineKeyboardButton("Просмотреть напоминания", callback_data='view_reminders')],
            [InlineKeyboardButton("Выйти из команды", callback_data='leave_team_menu')],
            [InlineKeyboardButton("Назад", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Выберите действие с напоминаниями:", reply_markup=reply_markup)
        return REMINDER
    
    elif query.data == 'back_to_main':
        return await menu_handler(update, context)
    
    return REMINDER

async def reminder_create_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора типа напоминания."""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in user_data_dict:
        user_data_dict[user_id] = {}
    
    if query.data == 'personal_reminder':
        user_data_dict[user_id]['reminder_type'] = 'personal'
        await query.edit_message_text("Введите текст напоминания:")
        return REMINDER_TEXT
    
    elif query.data == 'team_reminder':
        # Проверка наличия команд у пользователя
        teams = db.get_teams(user_id)
        if not teams:
            keyboard = [[InlineKeyboardButton("Назад", callback_data='back_to_reminder_create')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "У вас нет команд для создания напоминания. Сначала создайте команду.",
                reply_markup=reply_markup
            )
            return REMINDER_CREATE
        
        user_data_dict[user_id]['reminder_type'] = 'team'
        keyboard = []
        for team in teams:
            keyboard.append([InlineKeyboardButton(team['name'], callback_data=f"team_{team['name']}")])
        keyboard.append([InlineKeyboardButton("Выйти из команды", callback_data='leave_team_from_reminder')])
        keyboard.append([InlineKeyboardButton("Назад", callback_data='back_to_reminder_create')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Выберите команду для напоминания:", reply_markup=reply_markup)
        return REMINDER_TEAM
    
    elif query.data == 'back_to_reminder_create':
        return await reminder_handler(update, context)
    
    return REMINDER_CREATE

async def reminder_team_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора команды для напоминания."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    if query.data.startswith('team_'):
        team_name = query.data[5:]  # Убираем префикс 'team_'
        user_data_dict[user_id]['team_name'] = team_name
        
        await query.edit_message_text("Введите текст напоминания:")
        return REMINDER_TEXT
    
    elif query.data == 'leave_team_from_reminder':
        # Перенаправляем на основной интерфейс выхода из команды
        keyboard = [
            [InlineKeyboardButton("Выйти из команды", callback_data='leave_team_menu')],
            [InlineKeyboardButton("К меню напоминаний", callback_data='back_to_reminder')],
            [InlineKeyboardButton("Назад", callback_data='back_to_reminder_create')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "Нажмите кнопку 'Выйти из команды', чтобы перейти к выбору команды для выхода.",
            reply_markup=reply_markup
        )
        return REMINDER_CREATE
    
    elif query.data.startswith('confirm_leave_reminder_'):
        # Подтверждение выхода из команды
        team_id = int(query.data.split('_')[-1])
        team = db.get_team_by_id(team_id)
        
        if not team:
            await query.edit_message_text("Команда не найдена.")
            return ConversationHandler.END
            
        # Проверяем, не является ли пользователь создателем команды
        if team['created_by'] == user_id:
            keyboard = [[InlineKeyboardButton("Назад", callback_data='leave_team_from_reminder')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "Вы не можете выйти из команды, так как являетесь её создателем.",
                reply_markup=reply_markup
            )
            return REMINDER_TEAM
            
        # Удаляем пользователя из команды
        success = db.remove_user_from_team(team_id, user_id)
        
        if success:
            # Удаляем напоминания этой команды
            reminders = db.get_reminders(user_id, team_name=team['name'])
            for reminder in reminders:
                db.delete_reminder(reminder['id'])
                
            # Возвращаемся к выбору команды для напоминания
            keyboard = [[InlineKeyboardButton("Назад", callback_data='back_to_reminder_create')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"Вы успешно вышли из команды '{team['name']}'. Все напоминания этой команды удалены.",
                reply_markup=reply_markup
            )
        else:
            await query.edit_message_text("Произошла ошибка при выходе из команды.")
            return ConversationHandler.END
            
        return REMINDER_TEAM
    
    elif query.data == 'back_to_reminder_create':
        return await reminder_create_handler(update, context)
    
    return REMINDER_TEAM

async def reminder_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ввода текста напоминания."""
    reminder_text = update.message.text
    user_id = update.effective_user.id
    user_data_dict[user_id]['reminder_text'] = reminder_text
    
    # Запрашиваем выбор даты с помощью кнопок календаря
    current_date = datetime.now()
    
    # Создание календаря на текущий месяц
    keyboard = create_calendar_keyboard(current_date.year, current_date.month)
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Выберите дату для напоминания:",
        reply_markup=reply_markup
    )
    return REMINDER_DATE

def create_calendar_keyboard(year, month):
    """Создание клавиатуры с календарем."""
    keyboard = []
    
    # Заголовок календаря
    month_names = [
        "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
        "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
    ]
    
    # Строка для навигации по месяцам
    header_row = [
        InlineKeyboardButton(
            "◀️", callback_data=f"calendar_month:{year}:{month-1 if month > 1 else 12}:{year if month > 1 else year-1}"
        ),
        InlineKeyboardButton(f"{month_names[month-1]} {year}", callback_data="ignore"),
        InlineKeyboardButton(
            "▶️", callback_data=f"calendar_month:{year}:{month+1 if month < 12 else 1}:{year if month < 12 else year+1}"
        )
    ]
    keyboard.append(header_row)
    
    # Добавляем названия дней недели
    week_days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    calendar_row = []
    for day in week_days:
        calendar_row.append(InlineKeyboardButton(day, callback_data="ignore"))
    keyboard.append(calendar_row)
    
    # Получаем календарь на текущий месяц
    month_calendar = calendar.monthcalendar(year, month)
    
    # Добавляем дни месяца
    for week in month_calendar:
        calendar_row = []
        for day in week:
            if day == 0:
                calendar_row.append(InlineKeyboardButton(" ", callback_data="ignore"))
            else:
                # Форматируем день в строку для callback_data
                date_str = f"{day:02d}.{month:02d}.{year}"
                calendar_row.append(InlineKeyboardButton(
                    str(day), callback_data=f"calendar_day:{date_str}"
                ))
        keyboard.append(calendar_row)
    
    # Добавляем кнопку "Назад"
    keyboard.append([InlineKeyboardButton("Назад", callback_data="back_to_reminder_create")])
    
    return keyboard

async def calendar_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка взаимодействия с календарем."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    if query.data == "ignore":
        return REMINDER_DATE
    
    if query.data == "back_to_reminder_create":
        return await back_handler(update, context)
    
    if query.data.startswith("calendar_month:"):
        # Обработка навигации по месяцам
        _, year, month, year_nav = query.data.split(":")
        year, month = int(year), int(month)
        
        # Создание новой клавиатуры календаря для выбранного месяца
        keyboard = create_calendar_keyboard(year, month)
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "Выберите дату для напоминания:",
            reply_markup=reply_markup
        )
        return REMINDER_DATE
    
    if query.data.startswith("calendar_day:"):
        # Обработка выбора дня
        selected_date = query.data.split(":")[1]
        user_data_dict[user_id]['reminder_date'] = selected_date
        
        # Запрос времени
        keyboard = []
        # Добавление предустановленных вариантов времени
        times = [
            ["9:00", "12:00", "15:00"],
            ["18:00", "21:00", "23:00"]
        ]
        for time_row in times:
            row = []
            for t in time_row:
                row.append(InlineKeyboardButton(t, callback_data=f"time_{t}"))
            keyboard.append(row)
            
        # Кнопка для ввода произвольного времени
        keyboard.append([InlineKeyboardButton("Другое время", callback_data="time_custom")])
        keyboard.append([InlineKeyboardButton("Назад", callback_data="back_to_calendar")])
            
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"Выбрана дата: {selected_date}\nВыберите время напоминания:",
            reply_markup=reply_markup
        )
        return REMINDER_TIME
        
    return REMINDER_DATE

async def reminder_time_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора времени напоминания."""
    user_id = update.effective_user.id
    
    # Проверяем, это текстовое сообщение или callback
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        
        if query.data == "back_to_calendar":
            # Возврат к выбору даты
            current_date = datetime.now()
            keyboard = create_calendar_keyboard(current_date.year, current_date.month)
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "Выберите дату для напоминания:",
                reply_markup=reply_markup
            )
            return REMINDER_DATE
        
        if query.data.startswith("time_"):
            time_value = query.data[5:]  # Удаляем "time_" из начала
            
            if time_value == "custom":
                await query.edit_message_text(
                    "Введите время в формате ЧЧ:ММ (например: 14:30):"
                )
                return REMINDER_TIME
            
            # Используем выбранное время и дату из кнопок
            selected_date = user_data_dict[user_id]['reminder_date']
            date_time_str = f"{selected_date} {time_value}"
            
            try:
                reminder_time = datetime.strptime(date_time_str, '%d.%m.%Y %H:%M')
                
                # Сохранение в базу данных
                reminder_type = user_data_dict[user_id]['reminder_type']
                reminder_text = user_data_dict[user_id]['reminder_text']
                
                if reminder_type == 'personal':
                    success = db.add_reminder(
                        user_id=user_id,
                        reminder_time=reminder_time.isoformat(),
                        reminder_text=reminder_text
                    )
                else:  # Напоминание для команды
                    team_name = user_data_dict[user_id]['team_name']
                    success = db.add_reminder(
                        user_id=user_id,
                        reminder_time=reminder_time.isoformat(),
                        reminder_text=reminder_text,
                        team_name=team_name
                    )
                
                if success:
                    reminder_type_text = "личное" if reminder_type == 'personal' else f"для команды '{user_data_dict[user_id]['team_name']}'"
                    keyboard = [
                        [InlineKeyboardButton("В главное меню", callback_data='back_to_main')],
                        [InlineKeyboardButton("К напоминаниям", callback_data='back_to_reminder')]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await query.edit_message_text(
                        f"Напоминание {reminder_type_text} успешно создано на {date_time_str}!",
                        reply_markup=reply_markup
                    )
                else:
                    await query.edit_message_text("Произошла ошибка при создании напоминания. Попробуйте еще раз.")
                    return ConversationHandler.END
                
            except ValueError:
                await query.edit_message_text(
                    "Неверный формат времени. Выберите время снова."
                )
                return REMINDER_TIME
            
            return REMINDER
    else:
        # Это обычное текстовое сообщение с произвольным временем
        time_text = update.message.text
        
        try:
            # Парсим только время
            time_obj = datetime.strptime(time_text, '%H:%M').time()
            
            # Объединяем с выбранной датой
            selected_date = user_data_dict[user_id]['reminder_date']
            date_obj = datetime.strptime(selected_date, '%d.%m.%Y').date()
            
            # Создаем полную дату с временем
            reminder_time = datetime.combine(date_obj, time_obj)
            date_time_str = reminder_time.strftime('%d.%m.%Y %H:%M')
            
            # Сохранение в базу данных
            reminder_type = user_data_dict[user_id]['reminder_type']
            reminder_text = user_data_dict[user_id]['reminder_text']
            
            if reminder_type == 'personal':
                success = db.add_reminder(
                    user_id=user_id,
                    reminder_time=reminder_time.isoformat(),
                    reminder_text=reminder_text
                )
            else:  # Напоминание для команды
                team_name = user_data_dict[user_id]['team_name']
                success = db.add_reminder(
                    user_id=user_id,
                    reminder_time=reminder_time.isoformat(),
                    reminder_text=reminder_text,
                    team_name=team_name
                )
            
            if success:
                reminder_type_text = "личное" if reminder_type == 'personal' else f"для команды '{user_data_dict[user_id]['team_name']}'"
                keyboard = [
                    [InlineKeyboardButton("В главное меню", callback_data='back_to_main')],
                    [InlineKeyboardButton("К напоминаниям", callback_data='back_to_reminder')]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    f"Напоминание {reminder_type_text} успешно создано на {date_time_str}!",
                    reply_markup=reply_markup
                )
            else:
                await update.message.reply_text("Произошла ошибка при создании напоминания. Попробуйте еще раз.")
                return ConversationHandler.END
        
        except ValueError:
            await update.message.reply_text(
                "Неверный формат времени. Пожалуйста, используйте формат ЧЧ:ММ (например: 14:30)."
            )
            return REMINDER_TIME
        
        return REMINDER

async def delete_reminder_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка удаления напоминания."""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith('delete_reminder_'):
        reminder_id = int(query.data.split('_')[-1])
        user_id = update.effective_user.id
        
        # Удаление напоминания
        success = db.delete_reminder(reminder_id)
        
        if success:
            logger.info(f"Напоминание {reminder_id} успешно удалено пользователем {user_id}")
            
            # Получаем обновленный список напоминаний
            reminders = db.get_reminders(user_id=user_id)
            
            if not reminders:
                keyboard = [[InlineKeyboardButton("Назад", callback_data='back_to_reminder')]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text("Напоминание удалено. У вас больше нет напоминаний.", reply_markup=reply_markup)
                return REMINDER
            
            # Обновляем список напоминаний в user_data_dict
            if user_id not in user_data_dict:
                user_data_dict[user_id] = {}
            user_data_dict[user_id]['reminders'] = reminders
            
            # Отображение обновленных напоминаний
            reminder_text = "Напоминание удалено!\n\nВаши напоминания:\n\n"
            for i, reminder in enumerate(reminders, 1):
                reminder_time = datetime.fromisoformat(reminder['reminder_time']).strftime('%d.%m.%Y %H:%M')
                team_info = f" (Команда: {reminder['team_name']})" if reminder['team_name'] else ""
                reminder_text += f"{i}. {reminder_time}{team_info}\n{reminder['reminder_text']}\n\n"
            
            # Добавляем кнопки для удаления напоминаний
            keyboard = []
            for i, reminder in enumerate(reminders, 1):
                keyboard.append([InlineKeyboardButton(f"Удалить напоминание #{i}", callback_data=f"delete_reminder_{reminder['id']}")])
            
            keyboard.append([InlineKeyboardButton("Назад", callback_data='back_to_reminder')])
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(reminder_text, reply_markup=reply_markup)
            return REMINDER_VIEW
        else:
            await query.edit_message_text("Произошла ошибка при удалении напоминания.")
            return ConversationHandler.END
    # Если это кнопка "Назад"
    if query.data == 'back_to_reminder':
        # Возврат в меню напоминаний
        keyboard = [
            [InlineKeyboardButton("Создать напоминание", callback_data='create_reminder'),
             InlineKeyboardButton("Просмотреть напоминания", callback_data='view_reminders')],
            [InlineKeyboardButton("Выйти из команды", callback_data='leave_team_menu')],
            [InlineKeyboardButton("Назад", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Выберите действие с напоминаниями:", reply_markup=reply_markup)
        return REMINDER
        
    return REMINDER_VIEW

async def back_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка кнопки 'Назад'."""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'back_to_main':
        # Возврат в главное меню
        keyboard = [
            [InlineKeyboardButton("Команды", callback_data='commands'),
             InlineKeyboardButton("Личные напоминания", callback_data='personal_reminders')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Пожалуйста выберите:", reply_markup=reply_markup)
        return MENU
    
    elif query.data == 'back_to_team':
        # Возврат в меню команд
        keyboard = [
            [InlineKeyboardButton("Создать команду", callback_data='create_team'),
             InlineKeyboardButton("Просмотреть команды", callback_data='view_teams')],
            [InlineKeyboardButton("Удалить команду", callback_data='delete_team')],
            [InlineKeyboardButton("Назад", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Выберите действие с командами:", reply_markup=reply_markup)
        return TEAM
    
    elif query.data == 'back_to_reminder':
        # Возврат в меню напоминаний
        keyboard = [
            [InlineKeyboardButton("Создать напоминание", callback_data='create_reminder'),
             InlineKeyboardButton("Просмотреть напоминания", callback_data='view_reminders')],
            [InlineKeyboardButton("Выйти из команды", callback_data='leave_team_menu')],
            [InlineKeyboardButton("Назад", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Выберите действие с напоминаниями:", reply_markup=reply_markup)
        return REMINDER
    
    elif query.data == 'back_to_reminder_create':
        # Возврат в меню создания напоминания
        keyboard = [
            [InlineKeyboardButton("Личное напоминание", callback_data='personal_reminder')],
            [InlineKeyboardButton("Напоминание для команды", callback_data='team_reminder')],
            [InlineKeyboardButton("Назад", callback_data='back_to_reminder')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Выберите тип напоминания:", reply_markup=reply_markup)
        return REMINDER_CREATE
    
    # По умолчанию: возврат в главное меню
    return await menu_handler(update, context)

async def invite_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка действий с приглашениями."""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    if query.data.startswith('accept_invite_'):
        # Принятие приглашения
        invite_id = int(query.data.split('_')[-1])
        invite = db.get_invite_by_id(invite_id)
        
        if not invite:
            await query.edit_message_text("Приглашение не найдено или уже обработано.")
            return ConversationHandler.END
            
        # Проверяем, что статус приглашения все еще "pending"
        if invite['status'] != 'pending':
            await query.edit_message_text(f"Приглашение уже было {invite['status']}.")
            return ConversationHandler.END
            
        # Обновляем статус приглашения
        db.update_invite_status(invite_id, 'accepted')
        
        # Добавляем пользователя в команду
        team_id = invite['team_id']
        success = db.add_user_to_team(team_id, user_id)
        
        if success:
            team = db.get_team_by_id(team_id)
            keyboard = [[InlineKeyboardButton("В главное меню", callback_data='back_to_main')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"Вы приняли приглашение в команду '{team['name']}'!",
                reply_markup=reply_markup
            )
        else:
            await query.edit_message_text("Произошла ошибка при добавлении вас в команду.")
            return ConversationHandler.END
            
        return MENU
        
    elif query.data.startswith('reject_invite_'):
        # Отклонение приглашения
        invite_id = int(query.data.split('_')[-1])
        invite = db.get_invite_by_id(invite_id)
        
        if not invite:
            await query.edit_message_text("Приглашение не найдено или уже обработано.")
            return ConversationHandler.END
            
        # Проверяем, что статус приглашения все еще "pending"
        if invite['status'] != 'pending':
            await query.edit_message_text(f"Приглашение уже было {invite['status']}.")
            return ConversationHandler.END
            
        # Обновляем статус приглашения
        db.update_invite_status(invite_id, 'rejected')
        
        keyboard = [[InlineKeyboardButton("В главное меню", callback_data='back_to_main')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"Вы отклонили приглашение в команду '{invite['team_name']}'.",
            reply_markup=reply_markup
        )
        return MENU
        
    elif query.data == 'back_to_main':
        return await menu_handler(update, context)
    
    return INVITES

async def leave_team_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выхода из команды."""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    if query.data == 'leave_team':
        # Функционал выхода из команды перенесен в раздел напоминаний
        # Изменение структуры меню, перенаправляем пользователя к созданию напоминаний
        keyboard = [
            [InlineKeyboardButton("Создать напоминание", callback_data='create_reminder')],
            [InlineKeyboardButton("Назад", callback_data='back_to_team')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "Функционал выхода из команды перенесен в раздел напоминаний.\n"
            "Перейдите в 'Личные напоминания' -> 'Создать напоминание' -> 'Напоминание для команды' -> 'Выйти из команды'",
            reply_markup=reply_markup
        )
        return TEAM
            
    elif query.data.startswith('delete_team_'):
        # Функционал удаления команды перенесен в меню команд
        keyboard = [
            [InlineKeyboardButton("К командам", callback_data='back_to_team')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "Функционал удаления команды перенесен в раздел команд.\n"
            "Перейдите в 'Команды' -> 'Удалить команду'",
            reply_markup=reply_markup
        )
        return TEAM
    
    elif query.data == 'back_to_team':
        keyboard = [
            [InlineKeyboardButton("Создать команду", callback_data='create_team'),
             InlineKeyboardButton("Просмотреть команды", callback_data='view_teams')],
            [InlineKeyboardButton("Удалить команду", callback_data='delete_team')],
            [InlineKeyboardButton("Назад", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Выберите действие с командами:", reply_markup=reply_markup)
        return TEAM
        
    # Если ни одно условие не совпало
    return TEAM

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка ошибок."""
    logger.error(f"Ошибка: {context.error}")

async def check_reminders(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Функция для проверки и отправки напоминаний."""
    logger.info("Проверка напоминаний...")
    
    # Получаем текущее время в ISO формате
    now = datetime.now()
    current_time = now.replace(second=0, microsecond=0).isoformat()
    
    # Получаем все напоминания
    reminders = db.get_reminders()
    
    # Фильтруем только те, время которых пришло или чуть-чуть не дошло
    # (в течение последней минуты)
    pending_reminders = []
    for reminder in reminders:
        reminder_time = datetime.fromisoformat(reminder['reminder_time'])
        if now >= reminder_time and (now - reminder_time).total_seconds() < 60:
            pending_reminders.append(reminder)
    
    logger.info(f"Найдено {len(pending_reminders)} напоминаний, требующих отправки")
    
    # Отправляем напоминания
    for reminder in pending_reminders:
        user_id = reminder['user_id']
        team_name = reminder['team_name']
        reminder_text = reminder['reminder_text']
        
        if team_name:
            # Это командное напоминание, отправим всем участникам команды
            logger.info(f"Отправка командного напоминания для {team_name}")
            teams = db.get_teams()
            for team in teams:
                if team['name'] == team_name:
                    members = team['members']
                    for member_id in members:
                        try:
                            await context.bot.send_message(
                                chat_id=member_id,
                                text=f"⏰ Напоминание для команды {team_name}:\n\n{reminder_text}"
                            )
                            logger.info(f"Напоминание отправлено участнику {member_id} команды {team_name}")
                        except Exception as e:
                            logger.error(f"Ошибка отправки напоминания пользователю {member_id}: {e}")
        else:
            # Это личное напоминание
            logger.info(f"Отправка личного напоминания для пользователя {user_id}")
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"⏰ Напоминание:\n\n{reminder_text}"
                )
                logger.info(f"Напоминание отправлено пользователю {user_id}")
            except Exception as e:
                logger.error(f"Ошибка отправки напоминания пользователю {user_id}: {e}")
    
    # Здесь можно добавить удаление отправленных напоминаний или 
    # установку флага "отправлено" в базе данных

def run_bot():
    """Функция для запуска бота в non-asyncio режиме."""
    try:
        # Первое что сделаем - проверим, не запущен ли уже бот
        import os
        import subprocess
        import sys
        
        # Проверяем количество экземпляров бота
        try:
            bot_processes = subprocess.check_output(['pgrep', '-f', 'run_bot_v20.py']).decode().strip().split('\n')
            current_pid = str(os.getpid())
            bot_processes = [pid for pid in bot_processes if pid != current_pid and pid.strip()]
            
            if len(bot_processes) > 0:
                logger.info(f"Обнаружены другие экземпляры бота (PID: {', '.join(bot_processes)}). Текущий процесс: {current_pid}")
                logger.info("Бот уже запущен, завершаем текущий процесс")
                sys.exit(0)
        except Exception as e:
            logger.error(f"Ошибка при проверке запущенных экземпляров: {e}")
        
        # Проверяем, установлен ли модуль nest_asyncio
        try:
            import nest_asyncio
            nest_asyncio.apply()  # Позволяет запустить бота в тех окружениях, где цикл событий уже запущен
        except ImportError:
            logger.info("nest_asyncio не установлен, используем стандартный запуск")
        
    except Exception as e:
        logger.error(f"Ошибка при подготовке к запуску бота: {e}")
        
    # Создание приложения
    application = Application.builder().token(TOKEN).build()
    
    # Создание ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MENU: [CallbackQueryHandler(menu_handler)],
            TEAM: [CallbackQueryHandler(team_handler)],
            TEAM_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, team_name_handler)],
            TEAM_MEMBERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, team_members_handler)],
            TEAM_VIEW: [CallbackQueryHandler(team_handler)],
            TEAM_LEAVE: [CallbackQueryHandler(leave_team_handler)],
            INVITES: [CallbackQueryHandler(invite_handler)],
            REMINDER: [CallbackQueryHandler(reminder_handler)],
            REMINDER_CREATE: [CallbackQueryHandler(reminder_create_handler)],
            REMINDER_TEAM: [CallbackQueryHandler(reminder_team_handler)],
            REMINDER_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, reminder_text_handler)],
            REMINDER_DATE: [CallbackQueryHandler(calendar_handler)],
            REMINDER_TIME: [
                CallbackQueryHandler(reminder_time_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, reminder_time_handler)
            ],
            REMINDER_VIEW: [CallbackQueryHandler(delete_reminder_handler)],
        },
        fallbacks=[CommandHandler("start", start)],
    )
    
    # Добавление обработчика диалогов в приложение
    application.add_handler(conv_handler)
    application.add_error_handler(error_handler)
    
    # Добавление планировщика задач для проверки напоминаний каждую минуту
    job_queue = application.job_queue
    job_queue.run_repeating(check_reminders, interval=60, first=10)
    logger.info("📅 Планировщик напоминаний запущен")
    
    # Запуск бота в non-blocking режиме
    logger.info("🔄 Запуск бота...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

def main():
    """Основная функция запуска бота с asyncio."""
    import asyncio
    try:
        asyncio.run(async_main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("👋 Бот остановлен пользователем.")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        # Если асинхронный запуск не работает, пробуем обычный
        run_bot()

async def async_main():
    """Асинхронная функция запуска бота."""
    # Создание приложения
    application = Application.builder().token(TOKEN).build()
    
    # Создание ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MENU: [CallbackQueryHandler(menu_handler)],
            TEAM: [CallbackQueryHandler(team_handler)],
            TEAM_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, team_name_handler)],
            TEAM_MEMBERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, team_members_handler)],
            TEAM_VIEW: [CallbackQueryHandler(delete_reminder_handler)],
            TEAM_LEAVE: [CallbackQueryHandler(leave_team_handler)],
            INVITES: [CallbackQueryHandler(invite_handler)],
            REMINDER: [CallbackQueryHandler(reminder_handler)],
            REMINDER_CREATE: [CallbackQueryHandler(reminder_create_handler)],
            REMINDER_TEAM: [CallbackQueryHandler(reminder_team_handler)],
            REMINDER_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, reminder_text_handler)],
            REMINDER_DATE: [CallbackQueryHandler(calendar_handler)],
            REMINDER_TIME: [
                CallbackQueryHandler(reminder_time_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, reminder_time_handler)
            ],
            REMINDER_VIEW: [CallbackQueryHandler(delete_reminder_handler)],
        },
        fallbacks=[CommandHandler("start", start)],
    )
    
    # Добавление обработчика диалогов в приложение
    application.add_handler(conv_handler)
    application.add_error_handler(error_handler)
    
    # Добавление планировщика задач для проверки напоминаний каждую минуту
    job_queue = application.job_queue
    job_queue.run_repeating(check_reminders, interval=60, first=10)
    logger.info("📅 Планировщик напоминаний запущен")
    
    # Запуск бота в poll режиме
    logger.info("🚀 Запуск асинхронного бота...")
    await application.initialize()
    await application.start()
    await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    
    try:
        # Ждать пока бот будет остановлен
        await application.updater.stop()
        await application.stop()
    finally:
        # Закрываем соединение с базой данных
        db.close()

if __name__ == "__main__":
    try:
        # Пробуем запустить run_bot() напрямую
        run_bot()
    except Exception as e:
        logger.error(f"Ошибка при запуске run_bot(): {e}")
        # Если не получилось, используем main()
        main()