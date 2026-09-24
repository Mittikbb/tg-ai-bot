import asyncio
import io
import os
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatType
from aiogram.types import Message
from aiohttp import web
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PORT = int(os.getenv("PORT", 8080))
TRIGGER_PREFIX = "!"

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
ai_client = genai.Client(api_key=GEMINI_API_KEY)


# --- Веб-сервер для "Health Check" хостинга ---
async def health_check(request):
    """Хостинг будет стучаться сюда и получать 200 OK, не краша контейнер."""
    return web.Response(text="Bot is running fine!", status=200)


async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()


# --- Системный промпт для ИИ ---
SYSTEM_PROMPT = (
    "Ты — полезный ассистент в чате. Отвечай чётко, структурно и по делу. "
    "Если тебе прислали задание/задачу (включая фото), распиши понятное пошаговое решение."
)


# --- Хэндлер для текстовых сообщений с префиксом ---
@dp.message(F.text.startswith(TRIGGER_PREFIX))
async def handle_text(message: Message):
    query = message.text[len(TRIGGER_PREFIX) :].strip()
    if not query:
        return

    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    try:
        response = ai_client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=query,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT
            ),
        )
        await message.reply(response.text)
    except Exception as e:
        await message.reply(f"Ошибка при обработке запроса: {e}")


# --- Хэндлер для фото с подписью, начинающейся с префикса ---
@dp.message(F.photo, F.caption.startswith(TRIGGER_PREFIX))
async def handle_photo(message: Message):
    query = message.caption[len(TRIGGER_PREFIX) :].strip()
    if not query:
        query = "Реши задачу с этой фотографии и подробно распиши шаги."

    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    try:
        # Скачиваем фото наилучшего качества в память
        photo = message.photo[-1]
        file_io = io.BytesIO()
        await bot.download(photo, destination=file_io)
        image_bytes = file_io.getvalue()

        # Формируем запрос с картинкой
        image_part = types.Part.from_bytes(
            data=image_bytes,
            mime_type="image/jpeg",
        )

        response = ai_client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=[image_part, query],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT
            ),
        )
        await message.reply(response.text)
    except Exception as e:
        await message.reply(f"Ошибка при обработке фото: {e}")


# --- Запуск ---
async def main():
    # Запускаем фоновый сервер для пинга хостинга
    await start_web_server()
    print(f"Health-check сервер запущен на порту {PORT}")

    # Запускаем поллинг сообщений телеграма
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())