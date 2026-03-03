"""
ElevenLabs Speech-to-Text module.
Downloads a voice file from Telegram and transcribes it using the ElevenLabs API.
"""

import logging
import os

import requests

logger = logging.getLogger(__name__)

STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"


def transcribe_voice(file_path: str) -> str:
    """
    Downloads a voice file from Telegram and transcribes it using ElevenLabs Speech-to-Text API.

    Args:
        file_path: The relative file path returned by Telegram (e.g. 'voice/file_xxx.oga').

    Returns:
        The transcribed text.
    """
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise ValueError("ELEVENLABS_API_KEY is not set in .env file")

    # 1. Build the download URL.
    #    python-telegram-bot returns the full URL in file_path already,
    #    but guard against a bare relative path just in case.
    if file_path.startswith("https://") or file_path.startswith("http://"):
        telegram_url = file_path
    else:
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        if not bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is not set in .env file")
        telegram_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"

    response = requests.get(telegram_url)
    response.raise_for_status()
    audio_data = response.content

    # 2. Send to ElevenLabs Speech-to-Text API
    files = {
        "file": ("voice.ogg", audio_data, "audio/ogg"),
    }
    data = {
        "model_id": "scribe_v1",
    }
    headers = {
        "xi-api-key": api_key,
    }

    transcription = requests.post(STT_URL, files=files, data=data, headers=headers)
    transcription.raise_for_status()

    text = transcription.json().get("text", "")
    logger.info("Transcription completed successfully")
    return text.strip()
