import asyncio
import requests
import streamlit as st
import os
import random
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
import edge_tts

# Исправленные импорты MoviePy
try:
    from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip, AudioFileClip
except ImportError:
    from moviepy.video.io.VideoFileClip import VideoFileClip
    from moviepy.video.VideoClip import ImageClip
    from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
    from moviepy.audio.io.AudioFileClip import AudioFileClip

from PIL import Image, ImageDraw, ImageFont

# Настройка логов
logging.basicConfig(level=logging.INFO)

# Чтение ключей из Streamlit Secrets
TOKEN = st.secrets.get("VIDEO_BOT_TOKEN")
OR_KEY = st.secrets.get("OPENROUTER_API_KEY")

bot = Bot(token=TOKEN)
dp = Dispatcher()

FONT_PATH = "font.ttf"
RESULT_FILE = "tiktok_result.mp4"

def create_text_image(text, fontsize, color, font_path, video_w):
    """Генерация PNG с текстом через Pillow"""
    img_w = int(video_w * 0.9)
    img_h = 300
    img = Image.new('RGBA', (img_w, img_h), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype(font_path, fontsize)
    except:
        font = ImageFont.load_default()

    # Рисуем черную обводку
    shadow = (0, 0, 0, 255)
    for offset in [(-3,-3), (3,-3), (-3,3), (3,3)]:
        draw.text(((img_w//2)+offset[0], (img_h//2)+offset[1]), text, font=font, fill=shadow, anchor="mm")
    
    # Основной текст
    draw.text((img_w//2, img_h//2), text, font=font, fill=color, anchor="mm")
    
    temp_name = f"tmp_{random.randint(1000, 9999)}.png"
    img.save(temp_name)
    return temp_name

def build_video(script):
    logging.info("Сборка видео началась...")
    audio = AudioFileClip("voice.mp3")
    
    # Случайный фон
    bg_folder = "backgrounds"
    files = [f for f in os.listdir(bg_folder) if f.lower().endswith(('.mp4', '.mov'))]
    if not files:
        raise Exception("Папка backgrounds пуста!")
        
    video = VideoFileClip(os.path.join(bg_folder, random.choice(files)))
    
    # Длительность
    if video.duration < audio.duration:
        video = video.loop(duration=audio.duration)
    else:
        start = random.uniform(0, max(0, video.duration - audio.duration - 1))
        video = video.subclip(start, start + audio.duration)
    
    video = video.set_audio(audio)
    
    # Субтитры
    words = script.split()
    clips = [video]
    duration_per_word = audio.duration / len(words)
    group_size = 2
    
    for i in range(0, len(words), group_size):
        chunk = " ".join(words[i:i+group_size]).upper()
        img_p = create_text_image(chunk, 65, 'yellow', FONT_PATH, video.w)
        
        txt_clip = (ImageClip(img_p)
                    .set_start(i * duration_per_word)
                    .set_duration(duration_per_word * group_size)
                    .set_position(('center', video.h * 0.45)))
        clips.append(txt_clip)

    final = CompositeVideoClip(clips)
    final.write_videofile(RESULT_FILE, fps=24, codec="libx264", audio_codec="aac", logger=None)
    
    # Удаление временных картинок
    for f in os.listdir("."):
        if f.startswith("tmp_") and f.endswith(".png"):
            os.remove(f)
            
    return RESULT_FILE

async def get_ai_script(topic):
    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OR_KEY}", "HTTP-Referer": "https://streamlit.io"},
            json={
                "model": "openrouter/auto", 
                "messages": [{"role": "user", "content": f"Напиши один шокирующий факт на тему: {topic}. Коротко, на 10 сек."}]
            },
            timeout=25
        )
        return response.json()['choices'][0]['message']['content']
    except:
        return None

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("🎬 Бот запущен! Пришли тему.")

@dp.message(F.text)
async def handle_request(message: types.Message):
    status = await message.answer("🧠 Пишу сценарий...")
    script = await get_ai_script(message.text)
    
    if not script:
        await status.edit_text("❌ Ошибка ИИ")
        return

    try:
        await status.edit_text("🎙 Озвучка...")
        communicate = edge_tts.Communicate(script, "ru-RU-DmitryNeural")
        await communicate.save("voice.mp3")
        
        await status.edit_text("🎞 Рендер видео...")
        video_path = build_video(script)
        
        await message.answer_video(video=types.FSFile(video_path), caption="Готово!")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
    finally:
        await status.delete()

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    # Исправление ошибки Runtime Error:
    await dp.start_polling(bot, handle_signals=False)

if __name__ == "__main__":
    if "run" not in st.session_state:
        st.session_state.run = True
        st.write("🤖 Бот-режиссер запущен!")
        asyncio.run(main())
