import os
import discord
from discord.ext import commands
import g4f
import asyncio
import logging

# Logging ayarı
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot ayarları
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Sohbet geçmişi (kullanıcı bazlı)
user_histories = {}

@bot.event
async def on_ready():
    print(f"✅ Bot giriş yaptı: {bot.user}")
    await bot.change_presence(activity=discord.Game(name="Özel Mesajlarda Sohbet"))

@bot.event
async def on_message(message: discord.Message):
    # Botun kendi mesajlarını görmezden gel
    if message.author == bot.user:
        return

    # Sadece DM kabul et
    if not isinstance(message.channel, discord.DMChannel):
        return

    user_id = str(message.author.id)
    content = message.content.strip()

    # Geçmiş sohbetleri sakla (son 10 mesaj)
    if user_id not in user_histories:
        user_histories[user_id] = []
    history = user_histories[user_id]

    # Kullanıcı mesajını geçmişe ekle
    history.append({"role": "user", "content": content})

    # Geçmişi maksimum 10 mesaj ile sınırla
    if len(history) > 10:
        history.pop(0)

    try:
        # Typing efekti
        async with message.channel.typing():
            # G4F ile yanıt oluştur
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    g4f.ChatCompletion.create,
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "Sen Türkçe konuşan, samimi ve yardımcı bir asistansın. Kullanıcıya nazik ve açık cevaplar ver."},
                        *history
                    ]
                ),
                timeout=30.0
            )

        if response:
            # Botun yanıtını geçmişe ekle
            history.append({"role": "assistant", "content": response})
            await message.channel.send(response)
        else:
            await message.channel.send("❌ Bir hata oluştu, lütfen tekrar dene.")

    except asyncio.TimeoutError:
        await message.channel.send("⏳ İstek zaman aşımına uğradı, lütfen tekrar dene.")
    except Exception as e:
        logger.error(f"Hata oluştu: {e}", exc_info=True)
        await message.channel.send("❌ Bir hata oluştu.")

# Botu başlat
if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_TOKEN")
    if TOKEN:
        bot.run(TOKEN)
    else:
        logger.error("❌ DISCORD_TOKEN ortam değişkeni tanımlı değil!")
