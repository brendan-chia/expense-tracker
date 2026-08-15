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