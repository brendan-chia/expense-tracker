# Voice Expense Tracker - Telegram Bot

A Telegram bot that lets you track expenses by sending voice messages. It uses **ElevenLabs** for speech-to-text transcription and logs everything to **Google Sheets**.

## Features

- **Voice messages** — Send a voice message describing your expense
- **Text input** — Or just type your expense
- **Smart parsing** — Automatically extracts amount, category, and description
- **Category correction and learning** — Correct miscategorized expenses in natural language, and the bot remembers keyword/category mappings for future expenses
- **Google Sheets** — Enter an expense month/date and the bot automatically creates or uses the matching tab
- **Event tracking** — Select an event such as `Unit Rental` and keep its expenses in a dedicated tab
- **Monthly summary** — View spending breakdown with `/summary`

## Usage

| Action | How |
|--------|-----|
| Log expense (voice) | Send a voice message: *"I spent 7 ringgit on chicken rice"* |
| Log expense (text) | Type: *"Kopi RM5"* or *"Groceries 45 ringgit"* |
| Remove latest expense | Say or type: *"Remove the most recent response"* or *"Delete the last expense"* |
| Correct a category | Say or type: *"Actually, bread should be groceries"* or *"rice, curry paste should be groceries"* |
| Log an expense for another month | Include the date: *"RM25 groceries on 5 May 2026"*. The `May 2026` tab is created automatically. |
| Start event tracking | Send `/event Unit Rental`. This creates/uses the `Event - Unit Rental` tab. |
| Calculate event expenses | Send `/event_summary` or `/event_summary Unit Rental` |
| Leave event mode | Send `/event off` to return to monthly tabs |
| List event tabs | Send `/events` |
| View summary | Send `/summary` |
| Sort expense dates | Send `/sort` to sort existing tabs; new expenses are sorted automatically |
| Get help | Send `/help` |

## Supported Categories

Expenses are automatically categorized:

- **Food & Dining** — lunch, dinner, coffee, restaurant, etc.
- **Transport** — taxi, uber, gas, parking, etc.
- **Groceries** — grocery, supermarket, etc.
- **Shopping** — clothes, amazon, electronics, etc.
- **Entertainment** — movie, netflix, gaming, etc.
- **Bills & Utilities** — rent, electric, phone, internet, etc.
- **Health** — doctor, pharmacy, gym, etc.
- **Education** — books, course, tuition, etc.
- **Other** — anything that doesn't match above

### Category learning

If an expense is categorized incorrectly, say or type a correction such as
*"Actually, bread should be groceries"*. For multiple items, separate them
with commas, for example *"rice, curry paste should be groceries"*. The bot
updates the matching expense and saves one keyword/category mapping per item
in a `Category Learning` tab. Future expenses containing those keywords use
the learned category before the default keyword rules.

## Google Sheet Format

When you include a month/date in an expense, the bot automatically creates or uses a tab named for that month, such as `May 2026`. You do not need to create the tab manually. Each tab contains these columns:

| Date | Amount | Category | Description | Timestamp |
|------|--------|----------|-------------|-----------|
| Feb 12, 2026 | 7 | Food & Dining | Spent 7 ringgit on chicken rice | 2026-02-12T12:00:00Z |

### Event tabs

To track a specific event:

1. Send `/event Unit Rental` in Telegram.
2. Send expenses normally, by voice or text. They will be added to `Event - Unit Rental`.
3. Send `/event_summary` to see the total grouped by category.
4. Send `/event off` when you want new expenses to go back to monthly tabs.

Event-tab expenses are kept separate from monthly summaries so they are not counted twice.
