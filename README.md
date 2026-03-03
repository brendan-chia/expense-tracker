# Voice Expense Tracker - Telegram Bot

A Telegram bot that lets you track expenses by sending voice messages. It uses **ElevenLabs** for speech-to-text transcription and logs everything to **Google Sheets**.

## Features

- **Voice messages** — Send a voice message describing your expense
- **Text input** — Or just type your expense
- **Smart parsing** — Automatically extracts amount, category, and description
- **Google Sheets** — All expenses logged to a spreadsheet you can view/edit
- **Monthly summary** — View spending breakdown with `/summary`

## Setup

### 1. Telegram Bot

1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow the prompts
3. Copy the **bot token** you receive

### 2. ElevenLabs API Key

1. Sign up at [elevenlabs.io](https://elevenlabs.io)
2. Go to [API Keys settings](https://elevenlabs.io/app/settings/api-keys)
3. Create and copy an API key

### 3. Google Sheets Setup

#### Create a Google Cloud Service Account:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select existing)
3. Enable the **Google Sheets API**:
   - Go to **APIs & Services > Library**
   - Search for "Google Sheets API" and click **Enable**
4. Create a Service Account:
   - Go to **APIs & Services > Credentials**
   - Click **Create Credentials > Service Account**
   - Give it a name (e.g., "expense-tracker")
   - Click **Done**
5. Create a key for the service account:
   - Click on the service account you just created
   - Go to **Keys** tab > **Add Key > Create new key**
   - Choose **JSON** and download the file
   - Save it as `google-credentials.json` in this project's root folder

#### Create and share a Google Sheet:

1. Create a new Google Sheet at [sheets.google.com](https://sheets.google.com)
2. Copy the **Sheet ID** from the URL:
   ```
   https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID_HERE/edit
   ```
3. **Share the sheet** with your service account email:
   - Click **Share** on the Google Sheet
   - Add the service account email (found in `google-credentials.json` as `client_email`)
   - Give it **Editor** access

### 4. Environment Variables

1. Copy the example env file:
   ```bash
   cp .env.example .env
   ```
2. Fill in your values in `.env`:
   ```
   TELEGRAM_BOT_TOKEN=your_bot_token
   ELEVENLABS_API_KEY=your_elevenlabs_key
   GOOGLE_SHEET_ID=your_sheet_id
   GOOGLE_SERVICE_ACCOUNT_FILE=./google-credentials.json
   ```

### 5. Install & Run

```bash
pip install -r requirements.txt
python server/main.py
```

For development, you can use auto-reload with tools like `watchdog`:
```bash
pip install watchdog
watchmedo auto-restart --patterns="*.py" --recursive -- python server/main.py
```

## Usage

| Action | How |
|--------|-----|
| Log expense (voice) | Send a voice message: *"I spent 7 ringgit on chicken rice"* |
| Log expense (text) | Type: *"Kopi RM5"* or *"Groceries 45 ringgit"* |
| View summary | Send `/summary` |
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

## Google Sheet Format

The bot creates an "Expenses" sheet with these columns:

| Date | Amount | Category | Description | Timestamp |
|------|--------|----------|-------------|-----------|
| Feb 12, 2026 | 7 | Food & Dining | Spent 7 ringgit on chicken rice | 2026-02-12T12:00:00Z |
