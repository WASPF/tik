import asyncio
import requests
import streamlit as st
import os
import random
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
import edge_tts
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip, AudioFileClip

# --- ЧТЕНИЕ КЛЮЧЕЙ ИЗ SECRETS ---
TOKEN = st.secrets.get("VIDEO_BOT_TOKEN")
OR_KEY = st.secrets.get("OPENROUTER_API_KEY")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Пути к ресурсам
FONT_PATH = "font.ttf"
RESULT_FILE = "tiktok_result.mp4"

async def generate_voice(text):
    """Превращаем текст в озвучку"""
    # Если хочешь женский голос, замени на "ru-RU-SvetlanaNeural"
    communicate = edge_tts.Communicate(text, "ru-RU-DmitryNeural")
    await communicate.save("voice.mp3")

def get_random_background():
    """Ищет любое видео в папке backgrounds"""
    if not os.path.exists("backgrounds"):
        os.makedirs("backgrounds")
        raise Exception("Папка backgrounds была пуста и создана. Закинь туда .mp4 файлы!")
    
    files = [f for f in os.listdir("backgrounds") if f.lower().endswith(('.mp4', '.mov'))]
    if not files:
        raise Exception("В папке backgrounds нет видеофайлов!")
    
    return os.path.join("backgrounds", random.choice(files))

def build_video(script):
    """Монтаж: фон + звук + субтитры"""
    audio = AudioFileClip("voice.mp3")
    
    # Выбор фона
    random_bg = get_random_background()
    full_bg = VideoFileClip(random_bg)
    
    # Подгонка длины
    if full_bg.duration < audio.duration:
        video = full_bg.loop(duration=audio.duration).set_audio(audio)
    else:
        start_time = random.uniform(0, max(0, full_bg.duration - audio.duration - 1))
        video = full_bg.subclip(start_time, start_time + audio.duration).set_audio(audio)
    
    # Магия субтитров
    words = script.split()
    word_clips = [video]
    duration_per_word = audio.duration / len(words)
    
    # Группируем по 2 слова для динамики (TikTok style)
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

    # Сборка финального файла
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
    await message.answer("🎬 **PIXPAX РЕЖИССЕР**\n\nПришли мне тему, и я сделаю видео для TikTok!")

@dp.message(F.text)
async def handle_request(message: types.Message):
    status = await message.answer("🧠 **Шаг 1:** Пишу сценарий...")
    
    prompt = f"Напиши один короткий, шокирующий факт на тему: {message.text}. На 15 секунд озвучки. Только текст факта."
    
    try:
        # Запрос к OpenRouter
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OR_KEY}"},
            json={
                "model": "google/gemini-2.0-flash-exp:free", 
                "messages": [{"role": "user", "content": prompt}]
            }
        )
        
        data = response.json()

        # ПРОВЕРКА ОШИБОК API
        if 'error' in data:
            error_msg = data['error'].get('message', 'Неизвестная ошибка API')
            await status.edit_text(f"❌ Ошибка OpenRouter: {error_msg}")
            return
            
        if 'choices' not in data:
            await status.edit_text(f"❌ API прислал странный ответ. Проверь баланс OpenRouter.")
            return

        script = data['choices'][0]['message']['content']
        
        await status.edit_text("🎙 **Шаг 2:** Озвучиваю...")
        await generate_voice(script)
        
        await status.edit_text("🎞 **Шаг 3:** Монтирую (может занять до 1 мин)...")
        video_path = build_video(script)
        
        # Описание для ТТ
        caption = f"💡 Тема: {message.text}\n\n#AI #нейросети #интересно #pixpax"
        
        await message.answer_video(
            video=types.FSFile(video_path),
            caption=f"✅ Готово!\n\nОписание для видео:\n`{caption}`",
            parse_mode="Markdown"
        )
        
    except Exception as e:
        await message.answer(f"❌ Системная ошибка: {str(e)}")
    
    finally:
        await status.delete()

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, handle_signals=False)

if __name__ == "__main__":
    # Streamlit обертка для запуска
    if "run" not in st.session_state:
        st.session_state.run = True
        st.write("🤖 Видео-бот запущен и работает в фоне!")
        asyncio.run(main())
