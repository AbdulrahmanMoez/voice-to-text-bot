import os
from datetime import datetime
from pathlib import Path
import assemblyai as aai
import asyncio
import tempfile
import logging
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler
)
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import filters

# Configuration
TELEGRAM_BOT_TOKEN = "8131175099:AAEy3hwN2thPulSRRF6BY3GSZfzo7AUz5yY"
ASSEMBLY_API_KEY = "2f237a1af6b543e6806656b53204f654"
aai.settings.api_key = ASSEMBLY_API_KEY
FILES_DIR = Path("/bot_data")
FILES_DIR.mkdir(exist_ok=True)

# Conversation states
CHOOSING_LANGUAGE = 0
PROCESSING_AUDIO = 1

class TranscriptionBot:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.transcriber = aai.Transcriber()
        self.is_processing = False
        self.user_language = {}
        self.language_configs = {
            "ar": aai.TranscriptionConfig(
                language_code="ar",
                speech_model="nano"
            ),
            "en": aai.TranscriptionConfig(
                language_code="en"
            )
        }

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [
                InlineKeyboardButton("Arabic 🇸🇦", callback_data="ar"),
                InlineKeyboardButton("English 🇬🇧", callback_data="en")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Please choose transcription language:",
            reply_markup=reply_markup
        )
        return CHOOSING_LANGUAGE

    async def language_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        chat_id = query.message.chat_id
        self.user_language[chat_id] = query.data
        await query.edit_message_text(
            f"Selected language: {query.data.upper()}\nNow send me an audio file to transcribe."
        )
        return PROCESSING_AUDIO

    async def handle_audio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            chat_id = update.message.chat_id
            if chat_id not in self.user_language:
                return await self.start(update, context)

            if self.is_processing:
                await update.message.reply_text("⚠️ Bot is busy. Please try again later.")
                return ConversationHandler.END

            self.is_processing = True
            file = update.message.audio or update.message.voice
            input_file = FILES_DIR / f"{file.file_id}_{datetime.now().timestamp()}.mp3"

            try:
                # Download to FILES_DIR
                telegram_file = await context.bot.get_file(file.file_id)
                await telegram_file.download_to_drive(custom_path=input_file)
                await update.message.reply_text("📥 Processing audio...")

                # Use AssemblyAI recommended approach
                lang = self.user_language[chat_id]
                config = self.language_configs[lang]
                transcript = self.transcriber.transcribe(str(input_file), config)

                if transcript.status == aai.TranscriptStatus.error:
                    self.logger.error(f"Transcription failed: {transcript.error}")
                    await update.message.reply_text("❌ Transcription failed")
                    return ConversationHandler.END

                # Send results
                if transcript.text:
                    text_file = FILES_DIR / f"transcript_{datetime.now().timestamp()}.txt"
                    text_file.write_text(transcript.text, encoding='utf-8')  # Ensure UTF-8 encoding
                    
                    await update.message.reply_text(f"✅ Transcription:\n\n{transcript.text}")
                    await context.bot.send_document(
                        chat_id=chat_id,
                        document=text_file,
                        filename=f"transcription_{lang}.txt"
                    )
                    text_file.unlink()

            finally:
                if input_file.exists():
                    input_file.unlink()
                self.is_processing = False
                del self.user_language[chat_id]

        except Exception as e:
            self.logger.error(f"Error: {str(e)}")
            await update.message.reply_text("❌ Something went wrong")
            self.is_processing = False
            if chat_id in self.user_language:
                del self.user_language[chat_id]
            return ConversationHandler.END

def main():
    logging.basicConfig(level=logging.INFO)
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    bot = TranscriptionBot()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", bot.start)],
        states={
            CHOOSING_LANGUAGE: [
                CallbackQueryHandler(bot.language_callback)
            ],
            PROCESSING_AUDIO: [
                MessageHandler(filters.AUDIO | filters.VOICE, bot.handle_audio)
            ]
        },
        fallbacks=[CommandHandler("start", bot.start)]
    )
    
    application.add_handler(conv_handler)
    application.run_polling()

if __name__ == "__main__":
    main()
