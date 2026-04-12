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

# Настройка логов для Streamlit Cloud
logging.basicConfig(level=logging.INFO)

# --- ЧТЕНИЕ КЛЮЧЕЙ ---
TOKEN = st.secrets.get("VIDEO_BOT_TOKEN")
OR_KEY = st.secrets.get("OPENROUTER_API_KEY")

bot = Bot(token=TOKEN)
dp = Dispatcher()

FONT_PATH = "font.ttf"
RESULT_FILE = "tiktok_result.mp4"

async def generate_voice(text):
    logging.info(f"Начинаю озвучку текста: {text[:30]}...")
    communicate = edge_tts.Communicate(text, "ru-RU-DmitryNeural")
    await communicate.save("voice.mp3")

def get_random_background():
    if not os.path.exists("backgrounds"):
        os.makedirs("backgrounds")
        raise Exception("Папка backgrounds не найдена. Создал её. Загрузи туда mp4!")
    
    files = [f for f in os.listdir("backgrounds") if f.lower().endswith(('.mp4', '.mov'))]
    if not files:
        raise Exception("В папке backgrounds нет видео-файлов!")
    
    selected = os.path.join("backgrounds", random.choice(files))
    logging.info(f"Выбран фон: {selected}")
    return selected

def build_video(script):
    logging.info("Старт монтажа MoviePy...")
    if not os.path.exists(FONT_PATH):
        raise Exception(f"Шрифт не найден по пути: {FONT_PATH}. Проверь название файла на GitHub!")

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
            chunk,
            fontsize=85,
            color='yellow',
            font=FONT_PATH,
            stroke_color='black',
            stroke_width=2,
            method='caption',
            size=(video.w * 0.8, None)
        ).set_start(i * duration_per_word).set_duration(duration_per_word * group_size).set_position('center')
        
        word_clips.append(txt)

    final = CompositeVideoClip(word_clips)
    final.write_videofile(
        RESULT_FILE, 
        fps=24, 
        codec="libx264", 
        audio_codec="aac", 
        temp_audiofile='temp-audio.m4a', 
        remove_temp=True
    )
    return RESULT_FILE

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("🎬 **PIXPAX РЕЖИССЕР ЗАПУЩЕН**\nНапиши тему, и я сделаю видео!")

@dp.message(F.text)
async def handle_request(message: types.Message):
    status = await message.answer("🧠 **Шаг 1:** Запрос к ИИ...")
    logging.info(f"Пользователь запросил тему: {message.text}")
    
    prompt = f"Напиши один шокирующий факт на тему: {message.text}. На 15 секунд. Только текст."
    
    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OR_KEY}"},
            json={
                "model": "google/gemini-2.0-flash-exp:free", 
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=30
        )
        
        data = response.json()

        if 'error' in data:
            await status.edit_text(f"❌ Ошибка OpenRouter: {data['error'].get('message')}")
            return
            
        script = data['choices'][0]['message']['content']
        
        await status.edit_text("🎙 **Шаг 2:** Озвучка...")
        await generate_voice(script)
        
        await status.edit_text("🎞 **Шаг 3:** Монтаж (рендер)...")
        video_path = build_video(script)
        
        caption = f"🔥 {message.text}\n\n#AI #нейросети #pixpax"
        
        await message.answer_video(
            video=types.FSFile(video_path),
            caption=f"✅ Готово!\n\n`{caption}`",
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logging.error(f"ОШИБКА: {str(e)}")
        await message.answer(f"❌ Произошла ошибка:\n`{str(e)}`", parse_mode="Markdown")

async def main():
    logging.info("Бот начинает опрос (polling)...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, handle_signals=False)

if __name__ == "__main__":
    if "run" not in st.session_state:
        st.session_state.run = True
        st.write("🤖 Видео-бот работает. Проверь Telegram!")
        asyncio.run(main())
