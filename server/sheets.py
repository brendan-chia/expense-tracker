"""
Google Sheets module - handles authentication, sheet setup, and expense logging.
"""

import json
import logging
import os
from datetime import datetime

from google.oauth2 import service_account
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

SHEET_NAME = "Expenses"

_sheets_client = None


def _get_sheet_id():
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    if not sheet_id:
        raise ValueError("GOOGLE_SHEET_ID is not set in .env file")
    return sheet_id


def _get_credentials_file():
    """Resolve credentials path relative to the project root (parent of server/)."""
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "./google-credentials.json")
    # Resolve relative to project root, not cwd
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
    if creds_json:
        info = json.loads(creds_json)
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


def ensure_sheet():
    """Ensure the 'Expenses' sheet exists with proper headers."""
    service = get_client()
    sheets = service.spreadsheets()

    try:
        # Check if sheet exists
        sheet_id = _get_sheet_id()
        spreadsheet = sheets.get(spreadsheetId=sheet_id).execute()
        sheet_exists = any(
            s["properties"]["title"] == SHEET_NAME
            for s in spreadsheet.get("sheets", [])
        )

        if not sheet_exists:
            # Create the Expenses sheet
            sheets.batchUpdate(
                spreadsheetId=sheet_id,
                body={
                    "requests": [
                        {
                            "addSheet": {
                                "properties": {"title": SHEET_NAME}
                            }
                        }
                    ]
                },
            ).execute()

        # Check if headers exist
        header_check = sheets.values().get(
            spreadsheetId=sheet_id,
            range=f"{SHEET_NAME}!A1:E1",
        ).execute()

        if not header_check.get("values"):
            # Add headers
            sheets.values().update(
                spreadsheetId=sheet_id,
                range=f"{SHEET_NAME}!A1:E1",
                valueInputOption="RAW",
                body={
                    "values": [["Date", "Amount", "Category", "Description", "Timestamp"]],
                },
            ).execute()

            # Bold the header row
            spreadsheet_data = sheets.get(spreadsheetId=sheet_id).execute()
            sheet_id = None
            for s in spreadsheet_data.get("sheets", []):
                if s["properties"]["title"] == SHEET_NAME:
                    sheet_id = s["properties"]["sheetId"]
                    break

            if sheet_id is not None:
                sheets.batchUpdate(
                    spreadsheetId=sheet_id,
                    body={
                        "requests": [
                            {
                                "repeatCell": {
                                    "range": {
                                        "sheetId": sheet_id,
                                        "startRowIndex": 0,
                                        "endRowIndex": 1,
                                        "startColumnIndex": 0,
                                        "endColumnIndex": 5,
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

            logger.info("Created Expenses sheet with headers")

    except Exception as e:
        logger.error(f"Sheet setup error: {e}")
        raise


def append_expense(expense: dict):
    """
    Append an expense row to Google Sheets.

    Args:
        expense: Dict with keys: amount, category, description, date.
    """
    ensure_sheet()
    service = get_client()
    sheets = service.spreadsheets()
    sheet_id = _get_sheet_id()

    timestamp = datetime.now().isoformat()
    row = [
        expense["date"],
        expense["amount"],
        expense["category"],
        expense["description"],
        timestamp,
    ]

    sheets.values().append(
        spreadsheetId=sheet_id,
        range=f"{SHEET_NAME}!A:E",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={
            "values": [row],
        },
    ).execute()

    logger.info(f"Logged expense: RM{expense['amount']} - {expense['category']}")





def delete_expense_by_row(row_number: int) -> dict | None:
    """
    Delete a single expense row from the sheet by its 1-based row number.

    Returns the deleted row's data (for confirmation), or None if not found.
    """
    ensure_sheet()
    service = get_client()
    sheets = service.spreadsheets()
    spreadsheet_id = _get_sheet_id()

    # First, read the row so we can return it for confirmation
    result = sheets.values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{SHEET_NAME}!A{row_number}:E{row_number}",
    ).execute()
    row_values = result.get("values", [])
    if not row_values:
        return None

    row = row_values[0]
    deleted = {
        "row_number":  row_number,
        "date":        row[0] if len(row) > 0 else "",
        "amount":      row[1] if len(row) > 1 else "",
        "category":    row[2] if len(row) > 2 else "",
        "description": row[3] if len(row) > 3 else "",
    }

    # Look up the internal sheet tab ID (sheetId) for the Expenses tab
    spreadsheet_meta = sheets.get(spreadsheetId=spreadsheet_id).execute()
    tab_id = None
    for s in spreadsheet_meta.get("sheets", []):
        if s["properties"]["title"] == SHEET_NAME:
            tab_id = s["properties"]["sheetId"]
            break

    if tab_id is None:
        raise ValueError(f"Sheet tab '{SHEET_NAME}' not found")

    # Delete the row (0-based index in the API)
    sheets.batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            "requests": [
                {
                    "deleteDimension": {
                        "range": {
                            "sheetId": tab_id,
                            "dimension": "ROWS",
                            "startIndex": row_number - 1,  # 0-based
                            "endIndex":   row_number,       # exclusive
                        }
                    }
                }
            ]
        },
    ).execute()

    logger.info(f"Deleted row {row_number}: {deleted['category']} RM{deleted['amount']}")
    return deleted


def get_month_summary() -> str:
    """Get a summary of this month's expenses from Google Sheets."""
    ensure_sheet()
    service = get_client()
    sheets = service.spreadsheets()
    sheet_id = _get_sheet_id()

    result = sheets.values().get(
        spreadsheetId=sheet_id,
        range=f"{SHEET_NAME}!A:E",
    ).execute()

    rows = result.get("values", [])
    if len(rows) <= 1:
        return "No expenses recorded yet. Send a voice message to start tracking!"

    # Filter for current month
    now = datetime.now()
    current_month = now.month
    current_year = now.year

    month_expenses = []
    for row in rows[1:]:  # Skip header
        try:
            date = datetime.strptime(row[0], "%b %d, %Y")
            if date.month == current_month and date.year == current_year:
                month_expenses.append(row)
        except (ValueError, IndexError):
            continue

    if not month_expenses:
        return "No expenses recorded this month yet."

    # Calculate totals by category
    category_totals: dict[str, float] = {}
    total = 0.0

    for row in month_expenses:
        try:
            amount = float(row[1])
        except (ValueError, IndexError):
            amount = 0.0
        category = row[2] if len(row) > 2 else "Other"
        category_totals[category] = category_totals.get(category, 0) + amount
        total += amount

    # Build summary message
    month_name = now.strftime("%B %Y")
    summary = f"*Expense Summary - {month_name}*\n\n"

    # Sort categories by total (descending)
    sorted_categories = sorted(category_totals.items(), key=lambda x: x[1], reverse=True)

    for category, amount in sorted_categories:
        percentage = int((amount / total) * 100) if total > 0 else 0
        summary += f"* {category}: *RM{amount:.2f}* ({percentage}%)\n"

    summary += f"\n*Total: RM{total:.2f}*"
    summary += f"\n{len(month_expenses)} expense(s) recorded"

    return summary
