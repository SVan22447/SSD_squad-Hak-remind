
import json
import logging
from collections import defaultdict
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackContext,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ExtBot,
    TypeHandler,
)

with open('config.json', 'r') as f:
    config = json.load(f)
token = config["TOKEN"]

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


class ChatData:
    """Custom class for chat_data. Here we store data per message."""

    def __init__(self) -> None:
        self.clicks_per_message: defaultdict[int, int] = defaultdict(int)


# The [ExtBot, dict, ChatData, dict] is for type checkers like mypy
# class CustomContext(CallbackContext[ExtBot, dict, ChatData, dict]):
#     """Custom class for context."""

#     def __init__(
#         self,
#         application: Application,
#         chat_id: Optional[int] = None,
#         user_id: Optional[int] = None,
#     ):
#         super().__init__(application=application, chat_id=chat_id, user_id=user_id)
#         self._message_id: Optional[int] = None

#     @property
#     def bot_user_ids(self) -> set[int]:
#         """Custom shortcut to access a value stored in the bot_data dict"""
#         return self.bot_data.setdefault("user_ids", set())

#     @property
#     def message_clicks(self) -> Optional[int]:
#         """Access the number of clicks for the message this context object was built for."""
#         if self._message_id:
#             return self.chat_data.clicks_per_message[self._message_id]
#         return None

#     @message_clicks.setter
#     def message_clicks(self, value: int) -> None:
#         """Allow to change the count"""
#         if not self._message_id:
#             raise RuntimeError("There is no message associated with this context object.")
#         self.chat_data.clicks_per_message[self._message_id] = value

#     @classmethod
#     def from_update(cls, update: object, application: "Application") -> "CustomContext":
#         """Override from_update to set _message_id."""
#         # Make sure to call super()
#         context = super().from_update(update, application)

#         if context.chat_data and isinstance(update, Update) and update.effective_message:
#             # pylint: disable=protected-access
#             context._message_id = update.effective_message.message_id

#         # Remember to return the object
#         return context


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display a message with a button."""
   
    keyboard=[
        InlineKeyboardButton("Команды", callback_data='commands'),
        InlineKeyboardButton("Личные напоминания", callback_data='personal_reminders')
    ],
    reply_markup = InlineKeyboardMarkup(keyboard)   
    await update.message.reply_text("Please choose:", reply_markup=reply_markup)

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Parses the CallbackQuery and updates the message text."""
    query = update.callback_query

    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    await query.answer()

    await query.edit_message_text(text=f"Selected option: {query.data}")



def main() -> None:
    """Run the bot."""
    context_types = ContextTypes(context=ContextTypes.DEFAULT_TYPE, chat_data=ChatData)
    application = Application.builder().token(token).context_types(context_types).build()

    # run track_users in its own group to not interfere with the user handlers
    # application.add_handler(TypeHandler(Update, track_users), group=-1)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button))
    # application.add_handler(CallbackQueryHandler(count_click))
    # application.add_handler(CommandHandler("print_users", print_users))

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()