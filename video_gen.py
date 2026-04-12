import asyncio
import requests
import streamlit as st
import os
import random
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
import edge_tts
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip, AudioFileClip
from moviepy.config import change_settings

# Настройка логов
logging.basicConfig(level=logging.INFO)

# --- ЧТЕНИЕ КЛЮЧЕЙ ---
TOKEN = st.secrets.get("VIDEO_BOT_TOKEN")
OR_KEY = st.secrets.get("OPENROUTER_API_KEY")

bot = Bot(token=TOKEN)
dp = Dispatcher()

FONT_PATH = "font.ttf"
RESULT_FILE = "tiktok_result.mp4"

FREE_MODELS = [
    "openrouter/auto", 
    "google/gemini-2.0-flash-exp:free",
    "meta-llama/llama-3.1-8b-instruct:free"
]

async def generate_voice(text):
    communicate = edge_tts.Communicate(text, "ru-RU-DmitryNeural")
    await communicate.save("voice.mp3")

def get_random_background():
    if not os.path.exists("backgrounds"):
        os.makedirs("backgrounds")
    files = [f for f in os.listdir("backgrounds") if f.lower().endswith(('.mp4', '.mov'))]
    if not files:
        raise Exception("Папка backgrounds пуста!")
    return os.path.join("backgrounds", random.choice(files))

def build_video(script):
    logging.info("Старт монтажа...")
    
    # Пытаемся пофиксить путь к ImageMagick для Linux-сервера
    if os.path.exists("/usr/bin/convert"):
        change_settings({"IMAGEMAGICK_BINARY": "/usr/bin/convert"})

    audio = AudioFileClip("voice.mp3")
    random_bg = get_random_background()
    full_bg = VideoFileClip(random_bg)
    
    # Подгонка видео под звук
    if full_bg.duration < audio.duration:
        video = full_bg.loop(duration=audio.duration).set_audio(audio)
    else:
        start_time = random.uniform(0, max(0, full_bg.duration - audio.duration - 1))
        video = full_bg.subclip(start_time, start_time + audio.duration).set_audio(audio)
    
    # Создание субтитров
    words = script.split()
    word_clips = [video]
    duration_per_word = audio.duration / len(words)
    
    group_size = 2
    for i in range(0, len(words), group_size):
        chunk = " ".join(words[i:i+group_size]).upper()
        
        # Используем label вместо caption для стабильности
        txt = TextClip(
            chunk, 
            fontsize=70, 
            color='yellow', 
            font=FONT_PATH,
            stroke_color='black', 
            stroke_width=2, 
            method='label',
            size=(video.w * 0.9, None)
        ).set_start(i * duration_per_word).set_duration(duration_per_word * group_size).set_position(('center', video.h * 0.4))
        
        word_clips.append(txt)

    final = CompositeVideoClip(word_clips)
    final.write_videofile(RESULT_FILE, fps=24, codec="libx264", audio_codec="aac", logger=None)
    return RESULT_FILE

async def get_ai_script(topic):
    prompt = f"Напиши один короткий шокирующий факт на тему: {topic}. На 15 секунд. Только текст факта."
    for model in FREE_MODELS:
        try:
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OR_KEY}",
                    "HTTP-Referer": "https://streamlit.io",
                    "X-Title": "PixPax Video Maker"
                },
                json={"model": model, "messages": [{"role": "user", "content": prompt}]},
                timeout=20
            )
            data = response.json()
            if 'choices' in data:
                return data['choices'][0]['message']['content']
        except Exception as e:
            logging.error(f"Ошибка модели {model}: {e}")
    return None

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("🎬 **PIXPAX ULTRA-BOT**\nПришли тему для видео!")

@dp.message(F.text)
async def handle_request(message: types.Message):
    status = await message.answer("🧠 **Шаг 1:** Сценарий...")
    script = await get_ai_script(message.text)
    
    if not script:
        await status.edit_text("❌ Ошибка ИИ. Проверь баланс OpenRouter.")
        return

    try:
        await status.edit_text("🎙 **Шаг 2:** Озвучка...")
        await generate_voice(script)
        
        await status.edit_text("🎞 **Шаг 3:** Монтаж (рендер)...")
        video_path = build_video(script)
        
        caption = f"🔥 {message.text}\n\n#AI #нейросети #pixpax"
        await message.answer_video(video=types.FSFile(video_path), caption=f"✅ Готово!\n\n`{caption}`", parse_mode="Markdown")
        await status.delete()
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: `{str(e)}`", parse_mode="Markdown")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, handle_signals=False)

if __name__ == "__main__":
    if "run" not in st.session_state:
        st.session_state.run = True
        st.write("🤖 Видео-бот запущен!")
        asyncio.run(main())
