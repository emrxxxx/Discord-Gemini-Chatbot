import os
import discord
from discord.ext import commands
import google.generativeai as genai
import asyncio
import logging
from collections import deque
from googlesearch import search
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

user_histories = {}
base_system_prompt = {
    "role": "system",
    "content": """Sen Gemini 2.5 Flash tabanlı bir yapay zekâ sohbet asistanısın. 
Amacın kullanıcıyla doğal, akıcı ve insana yakın bir şekilde sohbet etmek, 
sorularına net ve doğru cevaplar vermek. Google araması yapabilirsin.

Kurallar:
- Yanıtların samimi, kibar ve anlaşılır olsun.
- Gereksiz uzun açıklamalardan kaçın, ama soruları gerektiğinde derinlemesine açıkla.
- Kullanıcının isteğine göre teknik, eğlenceli, ciddi veya gündelik bir üslup kullanabil.
- Kendini "asistan" olarak tanıt, insan gibi davran ama her zaman dürüst ol: 
  yapabileceklerini ve yapamayacaklarını açıkça belirt.
- Kullanıcının diline (Türkçe veya başka) uyum sağla.
- Google araması gerektiğinde, en fazla 3 sonucu özetle ve ilgili bilgileri sun.
- Sohbeti ilerletecek doğal tepkiler ver, gerektiğinde soru sorabilirsin."""
}

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

@bot.event
async def on_ready():
    print(f"✅ Bot giriş yaptı: {bot.user}")
    await bot.change_presence(activity=discord.Game(name="Özel Mesajlarda Sohbet"))

@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return

    allowed_channel_id = 1407490717676343296
    
    if not isinstance(message.channel, discord.DMChannel) and message.channel.id != allowed_channel_id:
        return

    user_id = str(message.author.id)
    content = message.content.strip()

    if user_id not in user_histories:
        user_histories[user_id] = deque(maxlen=20)

    history = user_histories[user_id]
    history.append({"role": "user", "content": content})

    messages = [base_system_prompt] + list(history)

    async with message.channel.typing():
        response = None
        search_results = None

        # Google araması yap
        if content.lower().startswith("ara:"):
            query = content[4:].strip()
            try:
                search_results = []
                for i, url in enumerate(search(query, num_results=3)):
                    search_results.append(f"[{i+1}] {url}")
                search_results = "\n".join(search_results) or "Arama sonucu bulunamadı."
                messages.append({"role": "system", "content": f"Google arama sonuçları: {search_results}"})
            except Exception as e:
                logger.error(f"Google arama hatası: {e}")
                search_results = "Arama yapılamadı."

        for attempt in range(3):
            try:
                model = genai.GenerativeModel("gemini-2.5-flash")
                response = await asyncio.to_thread(
                    model.generate_content,
                    [msg["content"] for msg in messages]
                )
                if response.candidates and response.candidates[0].content.parts:
                    response = response.candidates[0].content.parts[0].text
                else:
                    logger.error("Yanıt engellendi veya boş (safety block).")
                    await message.channel.send("❌ Yanıt engellendi veya alınamadı, lütfen farklı bir şekilde sor.")
                    return
                break
            except asyncio.TimeoutError:
                if attempt == 2:
                    await message.channel.send("⏳ İstek zaman aşımına uğradı, lütfen tekrar dene.")
                    return
            except Exception as e:
                logger.error(f"Hata oluştu (attempt {attempt+1}): {e}")
                if "429" in str(e):
                    await message.channel.send("❌ API kota sınırı aşıldı. Lütfen birkaç dakika bekle ve tekrar dene.")
                    return
                if attempt == 2:
                    await message.channel.send("❌ Bir hata oluştu.")
                    return
            time.sleep(2)  # Rate limit için bekleme

        if response:
            history.append({"role": "assistant", "content": response})
            if search_results and content.lower().startswith("ara:"):
                response = f"{response}\n\n**Arama Sonuçları:**\n{search_results}"
            await message.channel.send(response)
        else:
            await message.channel.send("❌ Yanıt alınamadı, lütfen tekrar dene.")

    await bot.process_commands(message)

if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_TOKEN")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if TOKEN and GEMINI_API_KEY:
        bot.run(TOKEN)
    else:
        logger.error("❌ DISCORD_TOKEN veya GEMINI_API_KEY ortam değişkeni tanımlı değil!")
