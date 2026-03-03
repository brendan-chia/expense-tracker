"""
Voice Expense Tracker - Telegram Bot (main entry point).

A Telegram bot that lets you track expenses by sending voice messages.
Uses ElevenLabs for speech-to-text and logs everything to Google Sheets.

Runs as a FastAPI server with a Telegram webhook (no polling).
"""

import sys
import os
import logging
from contextlib import asynccontextmanager

# Ensure the server directory is on the path for local imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from elevenlabs import transcribe_voice
from expense_parser import parse_expense, parse_delete_intent
from sheets import append_expense, get_month_summary, delete_expense_by_row

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Telegram Application (built once, shared across requests)
# ---------------------------------------------------------------------------
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")  # e.g. https://your-domain.com
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")  # secret token to verify Telegram requests


# /start command
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to the Voice Expense Tracker!\n\n"
        "Send me a *voice message* describing your expense, for example:\n"
        '"I spent 7 ringgit on chicken rice"\n'
        '"Paid 50 for groceries"\n'
        '"Grab ride 12 ringgit"\n\n'
        "*Remove an expense by voice:*\n"
        '"Delete the last expense"\n'
        '"Remove my grab entry"\n'
        '"Undo the food expense"\n\n'
        "*Commands:*\n"
        "/summary - View this month's expense summary\n"
        "/help - Show this help message",
        parse_mode="Markdown",
    )


# /help command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*Voice Expense Tracker - Help*\n\n"
        "*How to use:*\n"
        "1. Send a voice message describing your expense\n"
        "2. I'll transcribe it and extract the details\n"
        "3. The expense is automatically logged to Google Sheets\n\n"
        "*Voice message tips:*\n"
        '- Include the amount: "7 ringgit", "RM25", "fifty"\n'
        '- Include a category: "nasi lemak", "grab", "groceries"\n'
        '- Include a description: "lunch at mamak"\n\n'
        "*Removing an expense:*\n"
        'Say or type something like:\n'
        '• "Delete the last expense" — removes your most recent entry\n'
        '• "Remove my grab entry" — finds & removes the most recent Grab expense\n'
        '• "Undo the food expense" — removes the most recent Food \u0026 Dining entry\n\n'
        "*You can also type expenses:*\n"
        'Just type something like "Kopi RM5" or "Groceries 45 ringgit"\n\n'
        "*Commands:*\n"
        "/summary - This month's expense summary\n"
        "/help - Show this message",
        parse_mode="Markdown",
    )


# /summary command
async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.chat.send_action("typing")
        summary = get_month_summary()
        await update.message.reply_text(summary, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Summary error: {e}")
        await update.message.reply_text(
            "Failed to get summary. Check Google Sheets connection."
        )


# ---------------------------------------------------------------------------
# Shared deletion handler
# ---------------------------------------------------------------------------

async def handle_delete_intent(
    update: Update,
    intent: dict,
    transcript: str,
) -> bool:
    """
    Carry out a deletion based on `intent` returned by parse_delete_intent().

    Returns True if deletion was handled (success or failure), False if we
    should fall through to normal expense-logging.
    """
    await update.message.chat.send_action("typing")

    try:
        from sheets import get_client, ensure_sheet, SHEET_NAME
        ensure_sheet()
        sheet_id = os.environ.get("GOOGLE_SHEET_ID", "")
        service = get_client()
        result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=f"{SHEET_NAME}!A:E",
        ).execute()
        rows = result.get("values", [])
        data_rows = rows[1:] if len(rows) > 1 else []  # skip header
        all_expenses = []
        for idx, row in enumerate(data_rows, start=2):
            all_expenses.append({
                "row_number":  idx,
                "date":        row[0] if len(row) > 0 else "",
                "amount":      row[1] if len(row) > 1 else "",
                "category":    row[2] if len(row) > 2 else "",
                "description": row[3] if len(row) > 3 else "",
            })

        def _parse_date(date_str: str):
            """Parse d-m-yyyy into a sortable tuple. Falls back to (0,0,0)."""
            from datetime import datetime
            for fmt in ("%d-%m-%Y", "%d-%m-%y", "%Y-%m-%d"):
                try:
                    return datetime.strptime(date_str.strip(), fmt)
                except ValueError:
                    continue
            return datetime.min  # unparseable → sort to the very bottom

        # Sort ALL expenses by date descending (latest date first)
        recent = sorted(all_expenses, key=lambda e: _parse_date(e["date"]), reverse=True)
    except Exception as e:
        logger.error(f"Delete: failed to fetch recent expenses: {e}")
        await update.message.reply_text(
            "\u274c Couldn't reach Google Sheets. Please try again."
        )
        return True

    if not recent:
        await update.message.reply_text(
            "No expenses found to delete."
        )
        return True

    target = None

    if intent["mode"] == "last":
        target = recent[0]  # newest

    else:  # mode == "search"
        keyword = intent["keyword"].lower()
        category = intent["category"]

        # Priority 1: description keyword match
        for exp in recent:
            if keyword in exp["description"].lower():
                target = exp
                break

        # Priority 2: category match
        if target is None and category and category != "Other":
            for exp in recent:
                if exp["category"].lower() == category.lower():
                    target = exp
                    break

        # Priority 3: any field contains any word from the keyword
        if target is None:
            keywords = keyword.split()
            for exp in recent:
                haystack = " ".join([
                    exp["description"].lower(),
                    exp["category"].lower(),
                ])
                if any(kw in haystack for kw in keywords):
                    target = exp
                    break

    if target is None:
        await update.message.reply_text(
            f"\u274c Couldn't find a matching expense for: \"{transcript}\".\n"
            "Try being more specific, e.g. \"Remove my grab entry\" or \"Delete the last expense\"."
        )
        return True

    try:
        deleted = delete_expense_by_row(target["row_number"])
    except Exception as e:
        logger.error(f"Delete failed: {e}")
        await update.message.reply_text(
            "\u274c Failed to delete the expense. Please try again."
        )
        return True

    if deleted:
        await update.message.reply_text(
            "\u2705 *Expense deleted!*\n\n"
            f"Amount: *RM{deleted['amount']}*\n"
            f"Category: *{deleted['category']}*\n"
            f"Description: {deleted['description']}\n"
            f"Date: {deleted['date']}",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            "\u274c Could not find that row in the sheet. It may have already been deleted."
        )

    return True


# Handle voice messages
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id

    try:
        await update.message.chat.send_action("typing")
        await update.message.reply_text("Processing your voice message...")

        # 1. Download voice file from Telegram
        voice_file = await update.message.voice.get_file()
        file_url = voice_file.file_path

        # 2. Transcribe using ElevenLabs
        transcript = transcribe_voice(file_url)

        if not transcript or not transcript.strip():
            await update.message.reply_text(
                "Couldn't understand the voice message. Please try again."
            )
            return

        await update.message.reply_text(f'Heard: "{transcript}"')

        # 3. Check for delete intent FIRST
        delete_intent = parse_delete_intent(transcript)
        if delete_intent:
            await handle_delete_intent(update, delete_intent, transcript)
            return

        # 4. Parse expense from transcript
        expense = parse_expense(transcript)

        if not expense["amount"]:
            await update.message.reply_text(
                f"Couldn't extract an expense amount from: \"{transcript}\"\n\n"
                'Please include an amount, e.g. "I spent 7 ringgit on chicken rice"'
            )
            return

        # 5. Log to Google Sheets
        append_expense(expense)

        await update.message.reply_text(
            "*Expense logged!*\n\n"
            f"Amount: *RM{expense['amount']:.2f}*\n"
            f"Category: *{expense['category']}*\n"
            f"Description: {expense['description']}\n"
            f"Date: {expense['date']}",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Voice processing error: {e}")
        await update.message.reply_text(
            "Something went wrong processing your voice message. Please try again."
        )


# Handle text messages as typed expenses
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    # Skip commands
    if not text or text.startswith("/"):
        return

    try:
        await update.message.chat.send_action("typing")

        # Check for delete intent FIRST
        delete_intent = parse_delete_intent(text)
        if delete_intent:
            await handle_delete_intent(update, delete_intent, text)
            return

        expense = parse_expense(text)

        if not expense["amount"]:
            await update.message.reply_text(
                f"Couldn't extract an expense from: \"{text}\"\n\n"
                'Try: "Kopi RM5" or "Groceries 45 ringgit"'
            )
            return

        append_expense(expense)

        await update.message.reply_text(
            "*Expense logged!*\n\n"
            f"Amount: *RM{expense['amount']:.2f}*\n"
            f"Category: *{expense['category']}*\n"
            f"Description: {expense['description']}\n"
            f"Date: {expense['date']}",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Text expense error: {e}")
        await update.message.reply_text("Failed to log expense. Please try again.")


def _build_application():
    """Build the python-telegram-bot Application with all handlers."""
    if not TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set in .env file")

    app = ApplicationBuilder().token(TOKEN).updater(None).build()

    # Register handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("summary", summary_command))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    return app


ptb_app = _build_application()


# ---------------------------------------------------------------------------
# FastAPI lifespan — initialise / tear-down the Telegram Application
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(_app: FastAPI):
    await ptb_app.initialize()
    await ptb_app.start()

    webhook_path = f"{WEBHOOK_URL}/webhook"
    webhook_kwargs = {"url": webhook_path}
    if WEBHOOK_SECRET:
        webhook_kwargs["secret_token"] = WEBHOOK_SECRET
    await ptb_app.bot.set_webhook(**webhook_kwargs)
    logger.info(f"Webhook set to {webhook_path}")

    yield

    await ptb_app.bot.delete_webhook()
    await ptb_app.stop()
    await ptb_app.shutdown()


app = FastAPI(lifespan=lifespan)


@app.post("/webhook")
async def telegram_webhook(request: Request) -> Response:
    """Receive Telegram updates via webhook."""
    # Verify the request is actually from Telegram
    if WEBHOOK_SECRET:
        token_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if token_header != WEBHOOK_SECRET:
            logger.warning("Rejected webhook request: invalid secret token")
            return Response(status_code=403)

    data = await request.json()
    update = Update.de_json(data=data, bot=ptb_app.bot)
    await ptb_app.process_update(update)
    return Response(status_code=200)


@app.get("/")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
