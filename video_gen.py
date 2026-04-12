import asyncio
import requests
import streamlit as st
import os
import random
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
import edge_tts
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip, AudioFileClip

# --- КОНФИГ ---
TOKEN = st.secrets.get("VIDEO_BOT_TOKEN")
OR_KEY = st.secrets.get("OPENROUTER_API_KEY")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Путь к шрифту (убедись, что он так называется на GitHub)
FONT_PATH = "font.ttf"

async def generate_voice(text):
    communicate = edge_tts.Communicate(text, "ru-RU-DmitryNeural")
    await communicate.save("voice.mp3")

def get_random_background():
    """Автоматически находит любое видео в папке backgrounds"""
    files = [f for f in os.listdir("backgrounds") if f.endswith(('.mp4', '.MP4'))]
    if not files:
        raise Exception("Папка backgrounds пуста! Закинь туда видео.")
    return os.path.join("backgrounds", random.choice(files))

def build_video(script):
    audio = AudioFileClip("voice.mp3")
    
    # Бот сам выбирает случайный файл из тех, что на скрине
    random_bg = get_random_background()
    full_bg = VideoFileClip(random_bg)
    
    # Если фон короче аудио, зацикливаем. Если длиннее — берем случайный кусок.
    if full_bg.duration < audio.duration:
        video = full_bg.loop(duration=audio.duration).set_audio(audio)
    else:
        start_time = random.uniform(0, full_bg.duration - audio.duration - 0.5)
        video = full_bg.subclip(start_time, start_time + audio.duration).set_audio(audio)
    
    # Настройка текста
    words = script.split()
    word_clips = [video]
    duration_per_word = audio.duration / len(words)
    
    # Группируем по 2 слова для динамики
    group_size = 2
    for i in range(0, len(words), group_size):
        chunk = " ".join(words[i:i+group_size]).upper()
        
        txt = TextClip(
            chunk,
            fontsize=80,
            color='yellow',
            font=FONT_PATH,
            stroke_color='black',
            stroke_width=2,
            method='caption',
            size=(video.w * 0.8, None)
        ).set_start(i * duration_per_word).set_duration(duration_per_word * group_size).set_position('center')
        
        word_clips.append(txt)

    result_name = "tiktok_result.mp4"
    final = CompositeVideoClip(word_clips)
    final.write_videofile(result_name, fps=24, codec="libx264", audio_codec="aac", temp_audiofile='temp-audio.m4a', remove_temp=True)
    return result_name

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("🎬 **PIXPAX РЕЖИССЕР**\nНапиши тему для видео!")

@dp.message(F.text)
async def handle_request(message: types.Message):
    status = await message.answer("⏳ Готовлю контент...")
    
    try:
        # 1. Сценарий
        prompt = f"Напиши один шокирующий факт на тему: {message.text}. На 15 секунд. Только текст."
        res = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OR_KEY}"},
            json={"model": "google/gemini-2.0-flash-exp:free", "messages": [{"role": "user", "content": prompt}]}
        )
        script = res.json()['choices'][0]['message']['content']
        
        # 2. Озвучка
        await generate_voice(script)
        
        # 3. Монтаж
        video_path = build_video(script)
        
        # 4. Отправка
        caption = f"🔥 {message.text}\n\n#AI #нейросети #факты #pixpax"
        await message.answer_video(video=types.FSFile(video_path), caption=f"✅ Готово!\n\n`{caption}`", parse_mode="Markdown")
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
    
    await status.delete()

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, handle_signals=False)

if __name__ == "__main__":
    if "run" not in st.session_state:
        st.session_state.run = True
        asyncio.run(main())