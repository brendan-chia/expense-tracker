"""
Google Sheets module - handles authentication, sheet setup, and expense logging.
"""

import base64
import json
import logging
import os
import re
from datetime import datetime

from google.oauth2 import service_account
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

SHEET_NAME = os.environ.get("GOOGLE_EXPENSES_SHEET", "April")
EVENT_TAB_PREFIX = "Event - "
HEADERS = ["Date", "Amount", "Category", "Description", "Timestamp"]

_DATE_FORMATS = (
    "%b %d, %Y",
    "%B %d, %Y",
    "%d-%m-%Y",
    "%d-%m-%y",
    "%Y-%m-%d",
    "%d %B %Y",
    "%d %b %Y",
)
_MONTH_TAB_PATTERN = re.compile(
    r"^(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"(?:\s+\d{4})?$",
    re.IGNORECASE,
)
_EVENT_INVALID_CHARS = re.compile(r"[\[\]:*?/\\]")

_sheets_client = None


def _get_sheet_id():
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    if not sheet_id:
        raise ValueError("GOOGLE_SHEET_ID is not set in .env file")
    return sheet_id


def _get_credentials_file():
    """Resolve credentials path relative to the project root (parent of server/)."""
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "./google-credentials.json")
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(project_root, raw)


def get_client():
    """Authenticate with Google Sheets using a Service Account.

    Supports two modes:
    1. GOOGLE_CREDENTIALS_JSON env var — JSON string (recommended for cloud/Vercel).
    2. GOOGLE_SERVICE_ACCOUNT_FILE env var — path to a local JSON file.
    """
    global _sheets_client
    if _sheets_client:
        return _sheets_client

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]

    # Prefer env-var JSON (for serverless / cloud deployments)
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    creds_b64 = os.environ.get("GOOGLE_CREDENTIALS_BASE64")
    if creds_json:
        info = json.loads(creds_json)
        credentials = service_account.Credentials.from_service_account_info(
            info, scopes=scopes,
        )
    elif creds_b64:
        info = json.loads(base64.b64decode(creds_b64).decode("utf-8"))
        credentials = service_account.Credentials.from_service_account_info(
            info, scopes=scopes,
        )
    else:
        credentials_file = _get_credentials_file()
        if not os.path.exists(credentials_file):
            raise FileNotFoundError(
                f"Google credentials file not found at: {os.path.abspath(credentials_file)}\n"
                "Set GOOGLE_CREDENTIALS_JSON env var or provide a credentials file.\n"
                "See README.md for setup instructions."
            )
        credentials = service_account.Credentials.from_service_account_file(
            credentials_file, scopes=scopes,
        )

    _sheets_client = build("sheets", "v4", credentials=credentials)
    return _sheets_client


def _quote_sheet_name(sheet_name: str) -> str:
    """Quote a Google Sheets tab name for use in an A1 range."""
    return "'" + sheet_name.replace("'", "''") + "'"


def normalize_event_name(event_name: str) -> str:
    """Normalize an event name before using it in a Google Sheets tab title."""
    name = re.sub(r"\s+", " ", str(event_name or "").strip())
    if name.casefold().startswith(EVENT_TAB_PREFIX.casefold()):
        name = name[len(EVENT_TAB_PREFIX):].strip()
    name = _EVENT_INVALID_CHARS.sub("-", name).strip(" .")
    name = name[: (100 - len(EVENT_TAB_PREFIX))].strip(" .")
    if not name:
        raise ValueError("Event name cannot be empty")
    return name


def event_sheet_name(event_name: str) -> str:
    """Return the Google Sheets tab title for an event."""
    return f"{EVENT_TAB_PREFIX}{normalize_event_name(event_name)}"


def _parse_expense_date(date_value) -> datetime | None:
    """Parse dates written by the bot or entered manually in the sheet."""
    if isinstance(date_value, datetime):
        return date_value

    text = str(date_value or "").strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _get_sheet_properties(service, spreadsheet=None) -> list[dict]:
    """Return the spreadsheet's tab properties."""
    spreadsheet_id = _get_sheet_id()
    if spreadsheet is None:
        spreadsheet = service.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
        ).execute()
    return [
        sheet.get("properties", {})
        for sheet in spreadsheet.get("sheets", [])
        if sheet.get("properties", {}).get("title")
    ]


def _get_expense_sheet_names(
    service,
    spreadsheet=None,
    include_events: bool = False,
) -> list[str]:
    """Find the legacy, month, and optionally event tabs used for expenses."""
    known_name = SHEET_NAME.casefold()
    names = []
    for properties in _get_sheet_properties(service, spreadsheet):
        title = properties["title"]
        if (
            title.casefold() in {known_name, "expenses"}
            or _MONTH_TAB_PATTERN.fullmatch(title.strip())
            or (
                include_events
                and title.casefold().startswith(EVENT_TAB_PREFIX.casefold())
            )
        ):
            names.append(title)
    return names


def _choose_month_sheet_name(expense: dict, existing_titles: set[str]) -> str:
    """Choose the tab for an expense, preserving existing month-only tabs."""
    expense_date = _parse_expense_date(expense.get("date"))
    if expense_date is None:
        return SHEET_NAME

    month_name = expense_date.strftime("%B")
    canonical_name = f"{month_name} {expense_date.year}"
    title_lookup = {title.casefold(): title for title in existing_titles}

    # Prefer a full month/year tab when it already exists.
    if canonical_name.casefold() in title_lookup:
        return title_lookup[canonical_name.casefold()]

    # Keep using an existing tab named just "April", "May", etc. This
    # preserves the user's current April tab without moving its data.
    if month_name.casefold() in title_lookup:
        return title_lookup[month_name.casefold()]

    return canonical_name


def ensure_sheet(sheet_name: str = SHEET_NAME):
    """Ensure a named expense tab exists with the standard headers."""
    if not sheet_name or not sheet_name.strip():
        raise ValueError("Sheet tab name cannot be empty")

    service = get_client()
    sheets = service.spreadsheets()
    spreadsheet_id = _get_sheet_id()
    sheet_name = sheet_name.strip()

    try:
        spreadsheet = sheets.get(spreadsheetId=spreadsheet_id).execute()
        properties = next(
            (
                item
                for item in _get_sheet_properties(service, spreadsheet)
                if item["title"] == sheet_name
            ),
            None,
        )

        if properties is None:
            sheets.batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={
                    "requests": [
                        {
                            "addSheet": {
                                "properties": {"title": sheet_name}
                            }
                        }
                    ]
                },
            ).execute()
            spreadsheet = sheets.get(spreadsheetId=spreadsheet_id).execute()
            properties = next(
                (
                    item
                    for item in _get_sheet_properties(service, spreadsheet)
                    if item["title"] == sheet_name
                ),
                None,
            )

        if properties is None:
            raise ValueError(f"Sheet tab '{sheet_name}' could not be created")

        quoted_name = _quote_sheet_name(sheet_name)
        header_check = sheets.values().get(
            spreadsheetId=spreadsheet_id,
            range=f"{quoted_name}!A1:E1",
        ).execute()

        if not header_check.get("values"):
            sheets.values().update(
                spreadsheetId=spreadsheet_id,
                range=f"{quoted_name}!A1:E1",
                valueInputOption="RAW",
                body={"values": [HEADERS]},
            ).execute()

            sheets.batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={
                    "requests": [
                        {
                            "repeatCell": {
                                "range": {
                                    "sheetId": properties["sheetId"],
                                    "startRowIndex": 0,
                                    "endRowIndex": 1,
                                    "startColumnIndex": 0,
                                    "endColumnIndex": len(HEADERS),
                                },
                                "cell": {
                                    "userEnteredFormat": {
                                        "textFormat": {"bold": True},
                                        "backgroundColor": {
                                            "red": 0.9,
                                            "green": 0.9,
                                            "blue": 0.95,
                                        },
                                    }
                                },
                                "fields": "userEnteredFormat(textFormat,backgroundColor)",
                            }
                        }
                    ]
                },
            ).execute()

            logger.info("Created expense sheet tab '%s' with headers", sheet_name)

        return sheet_name

    except Exception as e:
        logger.error("Sheet setup error for '%s': %s", sheet_name, e)
        raise


def ensure_event_sheet(event_name: str) -> str:
    """Create an event tab if needed and return its clean display name."""
    clean_name = normalize_event_name(event_name)
    ensure_sheet(event_sheet_name(clean_name))
    return clean_name


def list_event_names() -> list[str]:
    """Return the names of all event tabs in the spreadsheet."""
    service = get_client()
    spreadsheet = service.spreadsheets().get(
        spreadsheetId=_get_sheet_id(),
    ).execute()
    prefix_length = len(EVENT_TAB_PREFIX)
    return [
        properties["title"][prefix_length:]
        for properties in _get_sheet_properties(service, spreadsheet)
        if properties["title"].casefold().startswith(EVENT_TAB_PREFIX.casefold())
    ]


def _read_expenses_from_sheet(
    sheets,
    spreadsheet_id: str,
    sheet_name: str,
) -> list[dict]:
    """Read expense rows from one tab, retaining tab and row identity."""
    result = sheets.values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{_quote_sheet_name(sheet_name)}!A:E",
    ).execute()
    rows = result.get("values", [])
    expenses = []

    for row_number, row in enumerate(rows[1:], start=2):
        if not row:
            continue
        expenses.append(
            {
                "sheet_name": sheet_name,
                "row_number": row_number,
                "date": row[0] if len(row) > 0 else "",
                "amount": row[1] if len(row) > 1 else "",
                "category": row[2] if len(row) > 2 else "",
                "description": row[3] if len(row) > 3 else "",
                "timestamp": row[4] if len(row) > 4 else "",
            }
        )
    return expenses


def append_expense(expense: dict, event_name: str | None = None) -> str:
    """Append an expense to an event tab or the tab matching its month/year."""
    service = get_client()
    sheets = service.spreadsheets()
    spreadsheet_id = _get_sheet_id()
    if event_name:
        clean_event_name = ensure_event_sheet(event_name)
        sheet_name = event_sheet_name(clean_event_name)
    else:
        spreadsheet = sheets.get(spreadsheetId=spreadsheet_id).execute()
        existing_titles = {
            properties["title"]
            for properties in _get_sheet_properties(service, spreadsheet)
        }
        sheet_name = _choose_month_sheet_name(expense, existing_titles)
        ensure_sheet(sheet_name)

    timestamp = datetime.now().isoformat()
    row = [
        expense["date"],
        expense["amount"],
        expense["category"],
        expense["description"],
        timestamp,
    ]

    sheets.values().append(
        spreadsheetId=spreadsheet_id,
        range=f"{_quote_sheet_name(sheet_name)}!A:E",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()

    logger.info(
        "Logged expense in '%s': RM%s - %s",
        sheet_name,
        expense["amount"],
        expense["category"],
    )
    return sheet_name


def get_all_expenses(include_events: bool = False) -> list[dict]:
    """Read expense rows from month tabs and optionally event tabs."""
    service = get_client()
    sheets = service.spreadsheets()
    spreadsheet_id = _get_sheet_id()
    spreadsheet = sheets.get(spreadsheetId=spreadsheet_id).execute()
    sheet_names = _get_expense_sheet_names(
        service,
        spreadsheet,
        include_events=include_events,
    )

    if not sheet_names:
        ensure_sheet()
        sheet_names = [SHEET_NAME]

    all_expenses = []
    for sheet_name in sheet_names:
        all_expenses.extend(
            _read_expenses_from_sheet(sheets, spreadsheet_id, sheet_name)
        )
    return all_expenses


def get_event_summary(event_name: str) -> str:
    """Calculate totals for one event tab, grouped by category."""
    clean_name = ensure_event_sheet(event_name)
    sheet_name = event_sheet_name(clean_name)
    service = get_client()
    sheets = service.spreadsheets()
    expenses = _read_expenses_from_sheet(
        sheets,
        _get_sheet_id(),
        sheet_name,
    )

    if not expenses:
        return f"No expenses recorded for *{clean_name}*."

    category_totals: dict[str, float] = {}
    total = 0.0
    for expense in expenses:
        try:
            amount = float(expense["amount"])
        except (ValueError, TypeError):
            amount = 0.0
        category = expense.get("category") or "Other"
        category_totals[category] = category_totals.get(category, 0) + amount
        total += amount

    summary = f"*Event Summary - {clean_name}*\n\n"
    for category, amount in sorted(
        category_totals.items(),
        key=lambda item: item[1],
        reverse=True,
    ):
        percentage = int((amount / total) * 100) if total > 0 else 0
        summary += f"• {category}: *RM{amount:.2f}* ({percentage}%)\n"

    summary += f"\n*Total: RM{total:.2f}*"
    summary += f"\n{len(expenses)} expense(s) recorded"
    return summary


def delete_expense_by_row(
    row_number: int,
    sheet_name: str = SHEET_NAME,
) -> dict | None:
    """Delete a single expense row from a named tab."""
    ensure_sheet(sheet_name)
    service = get_client()
    sheets = service.spreadsheets()
    spreadsheet_id = _get_sheet_id()
    quoted_name = _quote_sheet_name(sheet_name)

    result = sheets.values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{quoted_name}!A{row_number}:E{row_number}",
    ).execute()
    row_values = result.get("values", [])
    if not row_values:
        return None

    row = row_values[0]
    deleted = {
        "sheet_name": sheet_name,
        "row_number": row_number,
        "date": row[0] if len(row) > 0 else "",
        "amount": row[1] if len(row) > 1 else "",
        "category": row[2] if len(row) > 2 else "",
        "description": row[3] if len(row) > 3 else "",
    }

    spreadsheet_meta = sheets.get(spreadsheetId=spreadsheet_id).execute()
    tab_id = next(
        (
            properties["sheetId"]
            for properties in _get_sheet_properties(service, spreadsheet_meta)
            if properties["title"] == sheet_name
        ),
        None,
    )
    if tab_id is None:
        raise ValueError(f"Sheet tab '{sheet_name}' not found")

    sheets.batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            "requests": [
                {
                    "deleteDimension": {
                        "range": {
                            "sheetId": tab_id,
                            "dimension": "ROWS",
                            "startIndex": row_number - 1,
                            "endIndex": row_number,
                        }
                    }
                }
            ]
        },
    ).execute()

    logger.info(
        "Deleted row %s from '%s': %s RM%s",
        row_number,
        sheet_name,
        deleted["category"],
        deleted["amount"],
    )
    return deleted


def get_month_summary(month: int | None = None, year: int | None = None) -> str:
    """Get a summary of expenses for a given month/year."""
    now = datetime.now()
    target_month = month if month is not None else now.month
    target_year = year if year is not None else now.year
    period_label = datetime(target_year, target_month, 1).strftime("%B %Y")

    month_expenses = []
    for expense in get_all_expenses():
        expense_date = _parse_expense_date(expense.get("date"))
        if (
            expense_date
            and expense_date.month == target_month
            and expense_date.year == target_year
        ):
            month_expenses.append(expense)

    if not month_expenses:
        return f"No expenses recorded for *{period_label}*."

    category_totals: dict[str, float] = {}
    total = 0.0

    for expense in month_expenses:
        try:
            amount = float(expense["amount"])
        except (ValueError, TypeError):
            amount = 0.0
        category = expense.get("category") or "Other"
        category_totals[category] = category_totals.get(category, 0) + amount
        total += amount

    summary = f"*Expense Summary - {period_label}*\n\n"
    sorted_categories = sorted(
        category_totals.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    for category, amount in sorted_categories:
        percentage = int((amount / total) * 100) if total > 0 else 0
        summary += f"• {category}: *RM{amount:.2f}* ({percentage}%)\n"

    summary += f"\n*Total: RM{total:.2f}*"
    summary += f"\n{len(month_expenses)} expense(s) recorded"
    return summary
