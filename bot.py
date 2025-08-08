import os
import discord
from discord.ext import commands
from discord import FFmpegPCMAudio
import g4f
import re
import asyncio
import logging
from collections import deque

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

RADIO_URL = "http://shoutcast.radyogrup.com:1020/;"
CHANNEL_ID = 1392962273374375959

message_history = deque(maxlen=20)

# KOMUTLAR
@bot.command(name="ping")
async def ping(ctx):
    """Botun çalışıp çalışmadığını kontrol eder"""
    latency = round(bot.latency * 1000)
    await ctx.send(f"🏓 Pong! Gecikme: {latency}ms")

@bot.command(name="yardim", aliases=["help"])
async def yardim(ctx):
    """Yardım komutu"""
    embed = discord.Embed(
        title="🤖 Bot Komutları",
        description="Kullanabileceğiniz komutlar:",
        color=discord.Color.blue()
    )
    embed.add_field(name="!ping", value="Botun çalışıp çalışmadığını kontrol eder", inline=False)
    embed.add_field(name="!kahvefali [soru]", value="Kahve falı bakar", inline=False)
    embed.add_field(name="!hesapla <işlem>", value="Matematiksel işlem yapar (örn: 5 + 3)", inline=False)
    embed.add_field(name="!cevir <metin> -tr/-en", value="Metni çevirir", inline=False)
    embed.add_field(name="!yardim", value="Bu yardım menüsünü gösterir", inline=False)
    embed.set_footer(text="Bot @bot etiketlenerek de kullanabilirsiniz")
    await ctx.send(embed=embed)

@bot.command(name="kahvefali")
async def kahvefali(ctx, *, soru: str = None):
    """Kahve falı bakar. Kullanım: !kahvefali [isteğe bağlı soru]"""
    async with ctx.typing():
        try:
            system_prompt = """
            Sen tecrübeli bir kahve falı ustası gibisin. 
            Kahve fincanındaki şekillere bakarak fal yorumu yapacaksın.
            Yanıtların ilham verici, pozitif ve umut dolu olmalı.
            Kullanıcıya kişisel rehberlik sunan bir ton kullan.
            Fal yorumunu eğlenceli ve samimi bir dille yap.
            Eğer kullanıcı belirli bir soru sorduysa, fal yorumunu bu soruya göre şekillendir.
            """

            if soru:
                user_prompt = f"Kullanıcının sorusu: '{soru}'. Bu soruya göre kahve falı yorumu yap."
            else:
                user_prompt = "Kullanıcı genel bir kahve falı yorumu istedi. Rastgele ama anlamlı bir fal yorumu yap."

            response = await asyncio.wait_for(
                asyncio.to_thread(
                    g4f.ChatCompletion.create,
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                ),
                timeout=30.0
            )

            if response:
                embed = discord.Embed(
                    title="☕ Kahve Falı",
                    description=response,
                    color=discord.Color.from_rgb(139, 69, 19)
                )
                embed.set_footer(text=f"Fal bakan: {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
                await ctx.send(embed=embed)
            else:
                await ctx.send("❌ Kahve falı yorumu yapılırken bir hata oluştu. Lütfen tekrar dene.")

        except asyncio.TimeoutError:
            await ctx.send("⏳ Kahve falı yorumu yapılırken zaman aşımı oluştu. Lütfen tekrar dene.", delete_after=15)
        except Exception as e:
            logger.error(f"Kahve falı hatası: {e}", exc_info=True)
            await ctx.send("❌ Kahve falı yorumu yapılırken bir hata oluştu.", delete_after=15)

@bot.command(name="hesapla")
async def hesapla(ctx, *, expression: str):
    """Matematiksel işlem yapar"""
    pattern = r'(\d+)\s*([+\-*/])\s*(\d+)'
    match = re.search(pattern, expression)

    if match:
        num1 = float(match.group(1))
        operator = match.group(2)
        num2 = float(match.group(3))

        if operator == '+':
            result = num1 + num2
        elif operator == '-':
            result = num1 - num2
        elif operator == '*':
            result = num1 * num2
        elif operator == '/':
            if num2 == 0:
                await ctx.send("HATA: Sıfıra bölme!")
                return
            result = num1 / num2

        await ctx.send(f"Sonuç: {result}")
    else:
        await ctx.send("❌ Geçersiz işlem formatı. Örnek: `5 + 3`")

async def translate_text(text, lang_code, lang_name):
    try:
        prompt = f"Please translate the following text to {lang_name}:\n\n{text}"
        response = await asyncio.wait_for(
            asyncio.to_thread(
                g4f.ChatCompletion.create,
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Just type the translated text."},
                    {"role": "user", "content": prompt}
                ]
            ),
            timeout=30.0
        )
        return response
    except Exception as e:
        return f"❌ Çeviri hatası: {e}"

async def run_g4f_chat(channel_id, user_id, message):
    try:
        history_context = "\n".join([f"{msg['author']}: {msg['content']}" for msg in message_history])
        system_prompt = "You are a helpful assistant. Speak in Turkish. Summarize the last 20 messages and respond clearly and contextually to the user's latest question. Be polite, concise, and avoid unnecessary details."
        user_prompt = f"Previous messages:\n{history_context}\n\nUser ({user_id}) question: {message}"
        logger.debug(f"System Prompt: {system_prompt}\nUser Prompt: {user_prompt}")
        
        response = await asyncio.wait_for(
            asyncio.to_thread(
                g4f.ChatCompletion.create,
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            ),
            timeout=30.0
        )
        return response
    except Exception as e:
        logger.error(f"g4f error: {e}", exc_info=True)
        return f"❌ g4f error: {e}"

async def send_response_parts(message, content):
    if len(content) <= 2000:
        await message.channel.send(content)
    elif len(content) <= 4096:
        embed = discord.Embed(description=content, color=discord.Color.blue())
        await message.channel.send(embed=embed)
    else:
        filename = "cevap.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)
        await message.channel.send("Cevap dosya olarak gönderildi:", file=discord.File(filename))
        os.remove(filename)  # Dosyayı sil

@bot.event
async def on_ready():
    print(f"✅ Bot giriş yaptı: {bot.user}")
    
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="Pal Station"))

    try:
        channel = await bot.fetch_channel(CHANNEL_ID)
        if isinstance(channel, discord.VoiceChannel):
            voice_client = discord.utils.get(bot.voice_clients, guild=channel.guild)
            if voice_client and voice_client.is_connected():
                await voice_client.disconnect()
            
            voice_client = await channel.connect()

            ffmpeg_options = {
                "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                "options": "-vn -b:a 256k -ar 48000 -ac 2 -bufsize 512k"
            }

            voice_client.play(
                FFmpegPCMAudio(RADIO_URL, **ffmpeg_options)
            )

            print(f"🎵 {channel.name} kanalına bağlanıldı ve radyo başladı.")
        else:
            print(f"❌ Kanal ID {CHANNEL_ID} bir ses kanalı değil.")
    except Exception as e:
        import traceback
        print(f"❌ Ses kanalına bağlanırken hata oluştu: {e}")
        traceback.print_exc()

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
        
    if isinstance(message.channel, discord.DMChannel):
        return
        
    message_history.append({
        "author": str(message.author),
        "content": message.content
    })

    ctx = await bot.get_context(message)
    if ctx.valid:
        await bot.process_commands(message)
        return

    # Matematiksel işlemler (komutsuz)
    pattern = r'(\d+)\s*([+\-*/])\s*(\d+)'
    match = re.search(pattern, message.content)

    if match:
        num1 = float(match.group(1))
        operator = match.group(2)
        num2 = float(match.group(3))

        if operator == '+':
            result = num1 + num2
        elif operator == '-':
            result = num1 - num2
        elif operator == '*':
            result = num1 * num2
        elif operator == '/':
            if num2 == 0:
                await message.channel.send("HATA: Sıfıra bölme!")
                return
            result = num1 / num2

        await message.channel.send(f"Sonuç: {result}")
        return
        
    # Çeviri (komutsuz)
    translate_match = re.search(r'^(.*?)\s+-(tr|en)$', message.content, re.IGNORECASE | re.DOTALL)
    if translate_match:
        text_to_translate = translate_match.group(1).strip()
        lang_code = translate_match.group(2).lower()
        lang_name = "Turkish" if lang_code == "tr" else "English"

        if text_to_translate:
            async with message.channel.typing():
                try:
                    translated_text = await translate_text(text_to_translate, lang_code, lang_name)
                    if translated_text:
                        await message.channel.send(translated_text)
                    else:
                        await message.channel.send("❌ Metin çevrilemedi.", delete_after=10)
                except Exception as e:
                    logger.error(f"Çeviri hatası: {e}", exc_info=True)
                    await message.channel.send("❌ Çeviri sırasında hata oluştu.", delete_after=10)
        return
        
    # AI sohbet (etiketleme ile)
    if bot.user not in message.mentions:
        return
    
    async with message.channel.typing():
        try:
            user_id = str(message.author.id)
            channel_id = message.channel.id
            response_content = await run_g4f_chat(channel_id, user_id, message.content)
            if response_content:
                await send_response_parts(message, response_content)
        except asyncio.TimeoutError:
            await message.reply("⏳ İstek zaman aşımına uğradı, lütfen tekrar deneyin.", delete_after=15)
        except Exception:
            await message.reply("❌ Yanıt alınırken bir hata oluştu.", delete_after=15)

TOKEN = os.getenv("DISCORD_TOKEN")
if TOKEN:
    bot.run(TOKEN)
else:
    print("❌ HATA: DISCORD_TOKEN ortam değişkeni tanımlı değil!")
