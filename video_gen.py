import asyncio
import requests
import streamlit as st
import os
import random
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
import edge_tts

# Продвинутый импорт MoviePy (дружит со всеми версиями)
try:
    from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip, AudioFileClip
except ImportError:
    from moviepy.video.io.VideoFileClip import VideoFileClip
    from moviepy.video.VideoClip import ImageClip
    from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
    from moviepy.audio.io.AudioFileClip import AudioFileClip

from PIL import Image, ImageDraw, ImageFont

logging.basicConfig(level=logging.INFO)

# Ключи из Secrets
TOKEN = st.secrets.get("VIDEO_BOT_TOKEN")
OR_KEY = st.secrets.get("OPENROUTER_API_KEY")

bot = Bot(token=TOKEN)
dp = Dispatcher()

FONT_PATH = "font.ttf"
RESULT_FILE = "tiktok_result.mp4"

def create_text_image(text, fontsize, color, font_path, video_w):
    """Создает PNG с текстом (замена ImageMagick)"""
    img_w = int(video_w * 0.9)
    img_h = 300
    img = Image.new('RGBA', (img_w, img_h), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype(font_path, fontsize)
    except:
        font = ImageFont.load_default()

    # Рисуем черную обводку для читаемости
    shadow_color = (0, 0, 0, 255)
    for offset in [(-3,-3), (3,-3), (-3,3), (3,3)]:
        draw.text(((img_w//2)+offset[0], (img_h//2)+offset[1]), text, font=font, fill=shadow_color, anchor="mm")
    
    # Основной текст (желтый)
    draw.text((img_w//2, img_h//2), text, font=font, fill=color, anchor="mm")
    
    temp_name = f"txt_{random.randint(1000, 9999)}.png"
    img.save(temp_name)
    return temp_name

def build_video(script):
    logging.info("Начинаю сборку видео...")
    audio = AudioFileClip("voice.mp3")
    
    # Берем случайный фон из папки backgrounds
    bg_folder = "backgrounds"
    files = [f for f in os.listdir(bg_folder) if f.lower().endswith(('.mp4', '.mov'))]
    random_bg = os.path.join(bg_folder, random.choice(files))
    
    video = VideoFileClip(random_bg)
    
    # Подгоняем длительность
    if video.duration < audio.duration:
        video = video.loop(duration=audio.duration)
    else:
        start = random.uniform(0, max(0, video.duration - audio.duration - 1))
        video = video.subclip(start, start + audio.duration)
    
    video = video.set_audio(audio)
    
    # Разбиваем текст на куски по 2 слова
    words = script.split()
    clips = [video]
    duration_per_word = audio.duration / len(words)
    group_size = 2
    
    for i in range(0, len(words), group_size):
        chunk = " ".join(words[i:i+group_size]).upper()
        
        # Создаем картинку с текстом
        img_path = create_text_image(chunk, 65, 'yellow', FONT_PATH, video.w)
        
        txt_clip = (ImageClip(img_path)
                    .set_start(i * duration_per_word)
                    .set_duration(duration_per_word * group_size)
                    .set_position(('center', video.h * 0.45)))
        
        clips.append(txt_clip)

    final = CompositeVideoClip(clips)
    final.write_videofile(RESULT_FILE, fps=24, codec="libx264", audio_codec="aac", logger=None)
    
    # Чистим временные PNG
    for f in os.listdir("."):
        if f.startswith("txt_") and f.endswith(".png"):
            os.remove(f)
            
    return RESULT_FILE

async def get_ai_script(topic):
    prompt = f"Напиши один короткий шокирующий факт на тему: {topic}. На 10-15 секунд озвучки. Только текст факта."
    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OR_KEY}", "HTTP-Referer": "https://streamlit.io"},
            json={"model": "openrouter/auto", "messages": [{"role": "user", "content": prompt}]},
            timeout=25
        )
        return response.json()['choices'][0]['message']['content']
    except Exception as e:
        logging.error(f"Ошибка ИИ: {e}")
        return None

@dp.message(F.text)
async def handle_request(message: types.Message):
    status = await message.answer("🧠 Пишу сценарий...")
    script = await get_ai_script(message.text)
    
    if not script:
        await status.edit_text("❌ Ошибка ИИ (проверь ключ/баланс)")
        return

    try:
        await status.edit_text("🎙 Озвучиваю...")
        communicate = edge_tts.Communicate(script, "ru-RU-DmitryNeural")
        await communicate.save("voice.mp3")
        
        await status.edit_text("🎞 Рендерю (Pillow Mode)...")
        video_path = build_video(script)
        
        await message.answer_video(video=types.FSFile(video_path), caption="✅ Готово для TikTok!")
    except Exception as e:
        await message.answer(f"❌ Ошибка рендера: {e}")
    finally:
        if os.path.exists("voice.mp3"): os.remove("voice.mp3")
        await status.delete()

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    if "run" not in st.session_state:
        st.session_state.run = True
        st.write("🤖 Бот-режиссер запущен!")
        asyncio.run(main())
