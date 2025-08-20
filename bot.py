import os
import discord
from discord.ext import commands
import g4f
import asyncio
import logging
from collections import deque

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

user_histories = {}
base_system_prompt = {
    "role": "system",
    "content": """Sen GPT-5 tabanlı bir yapay zekâ sohbet asistanısın. 
Amacın kullanıcıyla doğal, akıcı ve insana yakın bir şekilde sohbet etmek, 
sorularına net ve doğru cevaplar vermek. 

Kurallar:
- Yanıtların samimi, kibar ve anlaşılır olsun.
- Gereksiz uzun açıklamalardan kaçın, ama soruları gerektiğinde derinlemesine açıkla.
- Kullanıcının isteğine göre teknik, eğlenceli, ciddi veya gündelik bir üslup kullanabil.
- Kendini "asistan" olarak tanıt, insan gibi davran ama her zaman dürüst ol: 
  yapabileceklerini ve yapamayacaklarını açıkça belirt.
- Kullanıcının diline (Türkçe veya başka) uyum sağla.
- Sohbeti ilerletecek doğal tepkiler ver, gerektiğinde soru sorabilirsin."""
}

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
        user_histories[user_id] = deque(maxlen=500)

    history = user_histories[user_id]
    history.append({"role": "user", "content": content})

    messages = [base_system_prompt] + list(history)

    try:
        async with message.channel.typing():
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    g4f.ChatCompletion.create,
                    model="gpt-4o",
                    provider=g4f.Provider.ChatgptLogin,
                    messages=messages
                ),
                timeout=30.0
            )

        if response:
            history.append({"role": "assistant", "content": response})
            await message.channel.send(response)
        else:
            await message.channel.send("❌ Bir hata oluştu, lütfen tekrar dene.")

    except asyncio.TimeoutError:
        await message.channel.send("⏳ İstek zaman aşımına uğradı, lütfen tekrar dene.")
    except Exception as e:
        logger.error(f"Hata oluştu: {e}", exc_info=True)
        await message.channel.send("❌ Bir hata oluştu.")

    await bot.process_commands(message)

if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_TOKEN")
    if TOKEN:
        bot.run(TOKEN)
    else:
        logger.error("❌ DISCORD_TOKEN ortam değişkeni tanımlı değil!")
