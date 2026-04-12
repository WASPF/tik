import asyncio
import requests
import streamlit as st
import os
import random
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
import edge_tts
from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip, AudioFileClip
from PIL import Image, ImageDraw, ImageFont

logging.basicConfig(level=logging.INFO)

TOKEN = st.secrets.get("VIDEO_BOT_TOKEN")
OR_KEY = st.secrets.get("OPENROUTER_API_KEY")

bot = Bot(token=TOKEN)
dp = Dispatcher()

FONT_PATH = "font.ttf"
RESULT_FILE = "tiktok_result.mp4"

def create_text_image(text, fontsize, color, font_path, video_w):
    """Рисуем текст на прозрачной картинке через Pillow (замена ImageMagick)"""
    img_w = int(video_w * 0.8)
    img_h = 400
    img = Image.new('RGBA', (img_w, img_h), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype(font_path, fontsize)
    except:
        font = ImageFont.load_default()

    # Рисуем обводку
    shadow = (0, 0, 0, 255)
    for offset in [(-2,-2), (2,-2), (-2,2), (2,2)]:
        draw.text(((img_w//2)+offset[0], (img_h//2)+offset[1]), text, font=font, fill=shadow, anchor="mm")
    
    # Рисуем основной текст
    draw.text((img_w//2, img_h//2), text, font=font, fill=color, anchor="mm")
    
    img_path = f"tmp_{random.randint(0,999)}.png"
    img.save(img_path)
    return img_path

def build_video(script):
    audio = AudioFileClip("voice.mp3")
    
    files = [f for f in os.listdir("backgrounds") if f.lower().endswith(('.mp4', '.mov'))]
    random_bg = os.path.join("backgrounds", random.choice(files))
    full_bg = VideoFileClip(random_bg)
    
    if full_bg.duration < audio.duration:
        video = full_bg.loop(duration=audio.duration).set_audio(audio)
    else:
        start_time = random.uniform(0, max(0, full_bg.duration - audio.duration - 1))
        video = full_bg.subclip(start_time, start_time + audio.duration).set_audio(audio)
    
    words = script.split()
    clips = [video]
    duration_per_word = audio.duration / len(words)
    
    group_size = 2
    for i in range(0, len(words), group_size):
        chunk = " ".join(words[i:i+group_size]).upper()
        
        # Генерируем картинку с текстом
        img_p = create_text_image(chunk, 70, 'yellow', FONT_PATH, video.w)
        
        txt_clip = (ImageClip(img_p)
                    .set_start(i * duration_per_word)
                    .set_duration(duration_per_word * group_size)
                    .set_position('center'))
        
        clips.append(txt_clip)

    final = CompositeVideoClip(clips)
    final.write_videofile(RESULT_FILE, fps=24, codec="libx264", audio_codec="aac", logger=None)
    
    # Чистим временные картинки
    for f in os.listdir("."):
        if f.startswith("tmp_") and f.endswith(".png"):
            os.remove(f)
            
    return RESULT_FILE

async def get_ai_script(topic):
    prompt = f"Напиши один короткий факт на тему: {topic}. На 10-15 секунд. Только текст."
    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OR_KEY}"},
            json={"model": "openrouter/auto", "messages": [{"role": "user", "content": prompt}]},
            timeout=20
        )
        return response.json()['choices'][0]['message']['content']
    except: return None

@dp.message(F.text)
async def handle_request(message: types.Message):
    status = await message.answer("🧠 Сценарий...")
    script = await get_ai_script(message.text)
    if not script: return
    
    try:
        await status.edit_text("🎙 Озвучка...")
        communicate = edge_tts.Communicate(script, "ru-RU-DmitryNeural")
        await communicate.save("voice.mp3")
        
        await status.edit_text("🎞 Рендер (Pillow Mode)...")
        video_path = build_video(script)
        
        await message.answer_video(video=types.FSFile(video_path))
    except Exception as e:
        await message.answer(f"Ошибка: {e}")
    finally:
        await status.delete()

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    if "run" not in st.session_state:
        st.session_state.run = True
        asyncio.run(main())
