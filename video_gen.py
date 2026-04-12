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

# Настройка логов
logging.basicConfig(level=logging.INFO)

# --- ЧТЕНИЕ КЛЮЧЕЙ ---
TOKEN = st.secrets.get("VIDEO_BOT_TOKEN")
OR_KEY = st.secrets.get("OPENROUTER_API_KEY")

bot = Bot(token=TOKEN)
dp = Dispatcher()

FONT_PATH = "font.ttf"
RESULT_FILE = "tiktok_result.mp4"

# Список моделей (от самых стабильных к запасным)
FREE_MODELS = [
    "openrouter/auto", 
    "google/gemini-2.0-flash-exp:free",
    "meta-llama/llama-3.1-8b-instruct:free",
    "mistralai/mistral-7b-instruct:free",
    "google/gemma-2-9b-it:free"
]

async def generate_voice(text):
    communicate = edge_tts.Communicate(text, "ru-RU-DmitryNeural")
    await communicate.save("voice.mp3")

def get_random_background():
    if not os.path.exists("backgrounds"):
        os.makedirs("backgrounds")
    files = [f for f in os.listdir("backgrounds") if f.lower().endswith(('.mp4', '.mov'))]
    if not files:
        raise Exception("Папка backgrounds пуста! Загрузи видео.")
    return os.path.join("backgrounds", random.choice(files))

def build_video(script):
    if not os.path.exists(FONT_PATH):
        raise Exception(f"Шрифт {FONT_PATH} не найден в корне GitHub!")

    audio = AudioFileClip("voice.mp3")
    random_bg = get_random_background()
    full_bg = VideoFileClip(random_bg)
    
    if full_bg.duration < audio.duration:
        video = full_bg.loop(duration=audio.duration).set_audio(audio)
    else:
        start_time = random.uniform(0, max(0, full_bg.duration - audio.duration - 1))
        video = full_bg.subclip(start_time, start_time + audio.duration).set_audio(audio)
    
    words = script.split()
    word_clips = [video]
    duration_per_word = audio.duration / len(words)
    
    group_size = 2
    for i in range(0, len(words), group_size):
        chunk = " ".join(words[i:i+group_size]).upper()
        txt = TextClip(
            chunk, fontsize=80, color='yellow', font=FONT_PATH,
            stroke_color='black', stroke_width=2, method='caption',
            size=(video.w * 0.8, None)
        ).set_start(i * duration_per_word).set_duration(duration_per_word * group_size).set_position('center')
        word_clips.append(txt)

    final = CompositeVideoClip(word_clips)
    final.write_videofile(RESULT_FILE, fps=24, codec="libx264", audio_codec="aac", remove_temp=True)
    return RESULT_FILE

async def get_ai_script(topic):
    # ПРОВЕРКА КЛЮЧА
    if not OR_KEY or len(OR_KEY) < 10:
        logging.error("КЛЮЧ OPENROUTER НЕ НАЙДЕН В SECRETS!")
        return "ERROR_NO_KEY"
        
    prompt = f"Напиши один короткий шокирующий факт на тему: {topic}. На 15 секунд. Только текст факта."
    
    for model in FREE_MODELS:
        try:
            logging.info(f"Пробую модель: {model}")
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OR_KEY}",
                    "HTTP-Referer": "https://streamlit.io", # Важно для OpenRouter
                    "X-Title": "PixPax Video Maker"
                },
                json={"model": model, "messages": [{"role": "user", "content": prompt}]},
                timeout=20
            )
            data = response.json()
            if 'choices' in data:
                return data['choices'][0]['message']['content']
            else:
                logging.warning(f"Модель {model} не ответила: {data}")
        except Exception as e:
            logging.error(f"Ошибка сети на {model}: {e}")
    return None

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("🎬 **PIXPAX РЕЖИССЕР**\nПришли тему для видео!")

@dp.message(F.text)
async def handle_request(message: types.Message):
    status = await message.answer("🧠 **Шаг 1:** Пишу сценарий...")
    
    script = await get_ai_script(message.text)
    
    if script == "ERROR_NO_KEY":
        await status.edit_text("❌ Ошибка: Бот не видит API-ключ в Secrets!")
        return
    if not script:
        await status.edit_text("❌ Все модели OpenRouter отказали. Проверь баланс или попробуй позже.")
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
