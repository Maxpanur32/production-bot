import logging
import os
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Состояния диалога ──
TASK, FROM_WHO, RESPONSIBLE, PRIORITY, DEADLINE, CONFIRM = range(6)

TEAM = ["Макс", "Оксана", "Аня", "Оля", "Даша", "Макс Дранков"]
PRIORITIES = ["🔴 Высокий", "🟡 Средний", "🟢 Низкий"]

# ── Google Sheets ──
def get_sheet():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    import json
info = json.loads(os.environ["GOOGLE_CREDENTIALS"])
creds = Credentials.from_service_account_info(info, scopes=scopes)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(os.environ["GOOGLE_SHEET_ID"]).sheet1
    return sheet

def save_task(data: dict):
    sheet = get_sheet()
    # Добавить заголовки если таблица пустая
    if sheet.row_count == 0 or sheet.cell(1, 1).value != "№":
        sheet.insert_row(
            ["№", "Дата", "Задача", "От кого", "Ответственный",
             "Приоритет", "Статус", "Дедлайн", "Комментарий"],
            index=1
        )
    rows = sheet.get_all_values()
    next_num = len(rows)  # уже учитывает заголовок
    sheet.append_row([
        next_num,
        datetime.now().strftime("%d.%m.%Y"),
        data.get("task", ""),
        data.get("from_who", ""),
        data.get("responsible", ""),
        data.get("priority", ""),
        "Новая",
        data.get("deadline", ""),
        "",
    ])

# ── Хэндлеры ──
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот команды продакшена.\n\n"
        "Напиши задачу в свободной форме, и я помогу её оформить.\n\n"
        "Например: *«Сделать баннер для новой коллекции диванов»*",
        parse_mode="Markdown"
    )
    return TASK

async def get_task(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["task"] = update.message.text
    await update.message.reply_text(
        "📌 Понял! От какого отдела или человека пришла задача?",
        reply_markup=ReplyKeyboardRemove()
    )
    return FROM_WHO

async def get_from_who(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["from_who"] = update.message.text
    keyboard = [[name] for name in TEAM]
    await update.message.reply_text(
        "👤 Кто возьмёт задачу?",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return RESPONSIBLE

async def get_responsible(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["responsible"] = update.message.text
    keyboard = [[p] for p in PRIORITIES]
    await update.message.reply_text(
        "⚡ Приоритет задачи?",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return PRIORITY

async def get_priority(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["priority"] = update.message.text
    await update.message.reply_text(
        "📅 Дедлайн? Напиши дату в формате *ДД.ММ.ГГГГ*\n"
        "Или напиши *«нет»* если дедлайна нет.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )
    return DEADLINE

async def get_deadline(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    deadline = update.message.text
    ctx.user_data["deadline"] = "" if deadline.lower() == "нет" else deadline

    d = ctx.user_data
    summary = (
        f"✅ *Проверь задачу:*\n\n"
        f"📌 *Задача:* {d['task']}\n"
        f"🏢 *От кого:* {d['from_who']}\n"
        f"👤 *Ответственный:* {d['responsible']}\n"
        f"⚡ *Приоритет:* {d['priority']}\n"
        f"📅 *Дедлайн:* {d['deadline'] or 'не указан'}\n\n"
        f"Всё верно?"
    )
    keyboard = [["✅ Да, сохранить"], ["✏️ Начать заново"]]
    await update.message.reply_text(
        summary,
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return CONFIRM

async def confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if "Да" in text:
        try:
            save_task(ctx.user_data)
            await update.message.reply_text(
                "🎉 Задача сохранена в таблицу!\n\n"
                "Чтобы добавить новую — напиши /start",
                reply_markup=ReplyKeyboardRemove()
            )
        except Exception as e:
            logger.error(f"Ошибка сохранения: {e}")
            await update.message.reply_text(
                "❌ Ошибка при сохранении. Проверь настройки Google Sheets.\n"
                f"Детали: {e}"
            )
    else:
        await update.message.reply_text(
            "Хорошо, начнём заново. Напиши задачу:",
            reply_markup=ReplyKeyboardRemove()
        )
        return TASK
    return ConversationHandler.END

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменено.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# ── Запуск ──
def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start),
                      MessageHandler(filters.TEXT & ~filters.COMMAND, get_task)],
        states={
            TASK:        [MessageHandler(filters.TEXT & ~filters.COMMAND, get_task)],
            FROM_WHO:    [MessageHandler(filters.TEXT & ~filters.COMMAND, get_from_who)],
            RESPONSIBLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_responsible)],
            PRIORITY:    [MessageHandler(filters.TEXT & ~filters.COMMAND, get_priority)],
            DEADLINE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, get_deadline)],
            CONFIRM:     [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(conv)
    logger.info("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
