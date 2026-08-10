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
from datetime import datetime, timezone

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

try:
    from server.elevenlabs import transcribe_voice
    from server.expense_parser import parse_expense, parse_delete_intent
    from server.sheets import (
        append_expense,
        ensure_event_sheet,
        get_event_summary,
        get_all_expenses,
        get_month_summary,
        list_event_names,
        delete_expense_by_row,
    )
except ImportError:
    # Fallback for running directly: python server/main.py
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from elevenlabs import transcribe_voice           # type: ignore
    from expense_parser import parse_expense, parse_delete_intent  # type: ignore
    from sheets import (  # type: ignore
        append_expense,
        ensure_event_sheet,
        get_event_summary,
        get_all_expenses,
        get_month_summary,
        list_event_names,
        delete_expense_by_row,
    )

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
        'To log an expense for another month, include its date, e.g. '
        '"RM25 groceries on 5 May 2026"\n\n'
        "*Remove an expense by voice:*\n"
        '"Delete the last expense"\n'
        '"Remove the most recent response"\n'
        '"Remove my grab entry"\n'
        '"Undo the food expense"\n\n'
        "*Commands:*\n"
        "/summary - View this month's expense summary\n"
        "/event Unit Rental - create/select an event tab\n"
        "/event_summary - calculate the selected event\n"
        "/event off - return to monthly tabs\n"
        "/events - list event tabs\n"
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
        '- For a different month, include a date: "RM25 groceries on 5 May 2026"\n\n'
        "*Removing an expense:*\n"
        'Say or type something like:\n'
        '• "Delete the last expense" — removes your most recent entry\n'
        '• "Remove the most recent response" — also removes your latest entry\n'
        '• "Remove my grab entry" — finds & removes the most recent Grab expense\n'
        '• "Undo the food expense" — removes the most recent Food \u0026 Dining entry\n\n'
        "*You can also type expenses:*\n"
        'Just type something like "Kopi RM5" or "Groceries 45 ringgit"\n\n'
        "*Commands:*\n"
        "/summary - This month's expense summary\n"
        "/event Unit Rental - create/select an event tab\n"
        "/event_summary - calculate the selected event\n"
        "/event off - return to monthly tabs\n"
        "/events - list event tabs\n"
        "/help - Show this message",
        parse_mode="Markdown",
    )


async def event_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Create/select an event tab or leave event mode."""
    args = context.args or []
    event_name = " ".join(args).strip()

    if event_name.casefold() in {"off", "none", "stop", "clear"}:
        previous = context.chat_data.pop("active_event", None)
        if previous:
            await update.message.reply_text(
                f"Event mode off. New expenses will return to monthly tabs.\n"
                f"Previous event: {previous}"
            )
        else:
            await update.message.reply_text(
                "Event mode is already off. New expenses will use monthly tabs."
            )
        return

    if not event_name:
        active_event = context.chat_data.get("active_event")
        if active_event:
            await update.message.reply_text(
                f"Current event: *{active_event}*\n\n"
                "Use `/event off` to return to monthly tabs or "
                "`/event_summary` to calculate its total.",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                "Use `/event Unit Rental` to create/select an event.\n"
                "Use `/event off` to return to monthly tabs.",
                parse_mode="Markdown",
            )
        return

    try:
        clean_name = ensure_event_sheet(event_name)
        context.chat_data["active_event"] = clean_name
        await update.message.reply_text(
            f"✅ Event selected: *{clean_name}*\n\n"
            f"New expenses will be logged in the `Event - {clean_name}` tab.\n"
            "Use `/event_summary` for the total or `/event off` to leave event mode.",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Event setup error: {e}")
        await update.message.reply_text(
            "Failed to create the event tab. Check Google Sheets connection."
        )


async def events_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all event tabs."""
    try:
        events = list_event_names()
        active_event = context.chat_data.get("active_event")
        if not events:
            await update.message.reply_text(
                "No event tabs yet. Create one with `/event Unit Rental`.",
                parse_mode="Markdown",
            )
            return

        lines = ["*Event tabs:*"]
        for name in events:
            marker = " ✅" if name.casefold() == str(active_event or "").casefold() else ""
            lines.append(f"• {name}{marker}")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Event list error: {e}")
        await update.message.reply_text(
            "Failed to list event tabs. Check Google Sheets connection."
        )


async def event_summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show a total for an event, using the selected event when omitted."""
    args = context.args or []
    event_name = " ".join(args).strip() or context.chat_data.get("active_event")
    if not event_name:
        await update.message.reply_text(
            "Select an event first, for example `/event Unit Rental`, "
            "then use `/event_summary`.",
            parse_mode="Markdown",
        )
        return

    try:
        await update.message.chat.send_action("typing")
        summary = get_event_summary(event_name)
        await update.message.reply_text(summary, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Event summary error: {e}")
        await update.message.reply_text(
            "Failed to calculate the event total. Check Google Sheets connection."
        )


# /summary command
async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Usage:
      /summary              → current month
      /summary march        → March of current year
      /summary 3            → March of current year
      /summary march 2025   → March 2025
      /summary 3 2025       → March 2025
    """
    import calendar
    from datetime import datetime

    now = datetime.now()
    month: int | None = None
    year:  int | None = None

    args = context.args or []

    if args:
        # Try to parse month from first arg (name or number)
        month_arg = args[0].strip()
        try:
            month = int(month_arg)
        except ValueError:
            # Try full or abbreviated month name (e.g. "march" or "mar")
            month_arg_cap = month_arg.capitalize()
            matched = None
            for fmt in ("%B", "%b"):
                try:
                    matched = datetime.strptime(month_arg_cap, fmt).month
                    break
                except ValueError:
                    continue
            if matched is None:
                await update.message.reply_text(
                    f'❌ Couldn\'t recognise "{month_arg}" as a month.\n'
                    "Try: `/summary march`, `/summary 3`, or `/summary march 2025`",
                    parse_mode="Markdown",
                )
                return
            month = matched

        if not (1 <= month <= 12):
            await update.message.reply_text("❌ Month must be between 1 and 12.")
            return

        # Optional second arg: year
        if len(args) >= 2:
            try:
                year = int(args[1].strip())
            except ValueError:
                await update.message.reply_text(
                    f'❌ Couldn\'t recognise "{args[1]}" as a year.'
                )
                return

    try:
        await update.message.chat.send_action("typing")
        summary = get_month_summary(month=month, year=year)
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
    # Keep this boundary defensive. The parser normally returns this schema,
    # but a future parser change or a malformed transcription must not turn a
    # delete request into an unhandled KeyError/AttributeError.
    if not isinstance(intent, dict):
        await update.message.reply_text(
            "I understood this as a removal request, but couldn't determine "
            "which expense to remove. Try \"remove the most recent expense\"."
        )
        return True

    mode = intent.get("mode")
    if mode not in {"last", "search"}:
        await update.message.reply_text(
            "I understood this as a removal request, but couldn't determine "
            "which expense to remove. Try \"remove the most recent expense\"."
        )
        return True

    keyword = str(intent.get("keyword") or "").strip().casefold()
    category = str(intent.get("category") or "").strip()
    if mode == "search" and not keyword:
        # Treat an incomplete search intent as a request for the latest entry
        # rather than crashing or searching for an empty string.
        mode = "last"

    try:
        await update.message.chat.send_action("typing")

        # Read every legacy/month tab so deletion works after expenses are split
        # across tabs. The row number is kept per tab for the Sheets API.
        all_expenses = get_all_expenses(include_events=True)

        def _parse_datetime(value):
            """Parse timestamps and dates stored by Google Sheets."""
            value = str(value or "").strip()
            if not value:
                return None

            # New rows contain an ISO timestamp. Normalize timezone-aware
            # values before comparing them with older, naive sheet dates.
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.tzinfo is not None:
                    parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
                return parsed
            except ValueError:
                pass

            for fmt in (
                "%d/%m/%Y %H:%M:%S",
                "%m/%d/%Y %H:%M:%S",
                "%d/%m/%Y %H:%M",
                "%m/%d/%Y %H:%M",
                "%d/%m/%Y %I:%M:%S %p",
                "%m/%d/%Y %I:%M:%S %p",
                "%d/%m/%Y %I:%M %p",
                "%m/%d/%Y %I:%M %p",
                "%d-%m-%Y",
                "%d-%m-%y",
                "%Y-%m-%d",
                "%b %d, %Y",
                "%B %d, %Y",
            ):
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
            return None

        def _expense_sort_key(expense: dict):
            # "Most recent" means the latest logged record, not merely the
            # latest expense date. Fall back to the date for legacy rows that
            # do not have a timestamp, then to the row number for a stable tie.
            logged_at = _parse_datetime(expense.get("timestamp"))
            expense_date = _parse_datetime(expense.get("date"))
            row_number = expense.get("row_number", 0)
            try:
                row_number = int(row_number)
            except (TypeError, ValueError):
                row_number = 0
            return (logged_at or expense_date or datetime.min, row_number)

        # Sort ALL expenses across all tabs, newest logged entry first.
        recent = sorted(all_expenses or [], key=_expense_sort_key, reverse=True)
    except Exception:
        logger.exception("Delete: failed to fetch recent expenses")
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

    if mode == "last":
        target = recent[0]  # newest

    else:  # mode == "search"
        # Priority 1: description keyword match
        for exp in recent:
            description = str(exp.get("description") or "").casefold()
            if keyword in description:
                target = exp
                break

        # Priority 2: category match
        if target is None and category and category != "Other":
            for exp in recent:
                expense_category = str(exp.get("category") or "").casefold()
                if expense_category == category.casefold():
                    target = exp
                    break

        # Priority 3: any field contains any word from the keyword
        if target is None:
            keywords = keyword.split()
            for exp in recent:
                haystack = " ".join([
                    str(exp.get("description") or "").casefold(),
                    str(exp.get("category") or "").casefold(),
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
        deleted = delete_expense_by_row(
            target["row_number"],
            sheet_name=target["sheet_name"],
        )
    except (KeyError, TypeError, ValueError):
        logger.exception("Delete failed: selected expense has invalid row data")
        await update.message.reply_text(
            "\u274c I found the expense, but its sheet row is invalid. "
            "Please try again or remove it manually in Google Sheets."
        )
        return True
    except Exception:
        logger.exception("Delete failed")
        await update.message.reply_text(
            "\u274c Failed to delete the expense. Please try again."
        )
        return True

    if deleted:
        await update.message.reply_text(
            "\u2705 *Expense deleted!*\n\n"
            f"Amount: *RM{deleted.get('amount', '')}*\n"
            f"Category: *{deleted.get('category', 'Other')}*\n"
            f"Description: {deleted.get('description', '')}\n"
            f"Date: {deleted.get('date', '')}",
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

        if not isinstance(transcript, str) or not transcript.strip():
            await update.message.reply_text(
                "Couldn't understand the voice message. Please try again."
            )
            return

        transcript = transcript.strip()

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

        # 5. Log to Google Sheets (selected event or automatic month tab)
        active_event = context.chat_data.get("active_event")
        target_tab = append_expense(expense, event_name=active_event)
        destination = (
            f"Event: *{active_event}*"
            if active_event
            else f"Tab: *{target_tab}*"
        )

        await update.message.reply_text(
            "*Expense logged!*\n\n"
            f"Amount: *RM{expense['amount']:.2f}*\n"
            f"Category: *{expense['category']}*\n"
            f"Description: {expense['description']}\n"
            f"Date: {expense['date']}\n"
            f"{destination}",
            parse_mode="Markdown",
        )
    except Exception:
        logger.exception("Voice processing error")
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

        active_event = context.chat_data.get("active_event")
        target_tab = append_expense(expense, event_name=active_event)
        destination = (
            f"Event: *{active_event}*"
            if active_event
            else f"Tab: *{target_tab}*"
        )

        await update.message.reply_text(
            "*Expense logged!*\n\n"
            f"Amount: *RM{expense['amount']:.2f}*\n"
            f"Category: *{expense['category']}*\n"
            f"Description: {expense['description']}\n"
            f"Date: {expense['date']}\n"
            f"{destination}",
            parse_mode="Markdown",
        )
    except Exception:
        logger.exception("Text expense error")
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
    app.add_handler(CommandHandler("event", event_command))
    app.add_handler(CommandHandler("event_summary", event_summary_command))
    app.add_handler(CommandHandler("eventsummary", event_summary_command))
    app.add_handler(CommandHandler("events", events_command))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    return app


ptb_app = None


def _get_ptb_app():
    """Lazily build and return the PTB application (created once)."""
    global ptb_app
    if ptb_app is None:
        ptb_app = _build_application()
    return ptb_app


# ---------------------------------------------------------------------------
# FastAPI lifespan — initialise / tear-down the Telegram Application
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(_app: FastAPI):
    app_instance = _get_ptb_app()
    await app_instance.initialize()

    # Optionally set webhook on startup (useful for local dev).
    # On Vercel, set the webhook once manually via the Telegram API instead.
    if WEBHOOK_URL and os.environ.get("AUTO_SET_WEBHOOK", "").lower() in ("1", "true"):
        try:
            webhook_path = f"{WEBHOOK_URL}/webhook"
            webhook_kwargs = {"url": webhook_path}
            if WEBHOOK_SECRET:
                webhook_kwargs["secret_token"] = WEBHOOK_SECRET
            await app_instance.bot.set_webhook(**webhook_kwargs)
            logger.info(f"Webhook set to {webhook_path}")
        except Exception as e:
            logger.warning(f"Failed to set webhook: {e}")

    yield

    try:
        await app_instance.shutdown()
    except Exception:
        pass


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
    app_instance = _get_ptb_app()
    update = Update.de_json(data=data, bot=app_instance.bot)
    await app_instance.process_update(update)
    return Response(status_code=200)


@app.get("/")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("server.main:app", host="0.0.0.0", port=port, reload=True)
