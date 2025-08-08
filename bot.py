import os
import discord
from discord.ext import commands
from discord import FFmpegPCMAudio
import g4f
import re
import asyncio
import logging
from collections import deque, defaultdict
import json
import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

RADIO_URL = "http://shoutcast.radyogrup.com:1020/;"
CHANNEL_ID = 1392962273374375959

# Kullanıcı bazlı geçmiş saklama (son 10 mesaj)
user_histories = defaultdict(lambda: deque(maxlen=10))

# KOMUTLAR
@bot.command(name="ping")
async def ping(ctx):
    """Botun çalışıp çalışmadığını kontrol eder"""
    latency = round(bot.latency * 1000)
    await ctx.send(f"🏓 Pong! Gecikme: {latency}ms")

@bot.command(name="yardim")
async def yardim(ctx):
    """Yardım komutu"""
    embed = discord.Embed(
        title="🤖 Bot Komutları",
        description="Kullanabileceğiniz komutlar:",
        color=discord.Color.blue()
    )
    embed.add_field(name="!ping", value="Botun çalışıp çalışmadığını kontrol eder", inline=False)
    embed.add_field(name="!kahvefali [soru]", value="Gerçek kahve falı bakar", inline=False)
    embed.add_field(name="!tarotfali [kart sayısı] [soru]", value="Tarot falı bakar (kart sayısı: 1, 3, 7, 12 - varsayılan: 3)", inline=False)
    embed.add_field(name="!hesapla <işlem>", value="Matematiksel işlem yapar (örn: 5 + 3)", inline=False)
    embed.add_field(name="!cevir <metin> -tr/-en", value="Metni çevirir", inline=False)
    embed.add_field(name="!yardim", value="Bu yardım menüsünü gösterir", inline=False)
    embed.set_footer(text="Bot @bot etiketlenerek de kullanabilirsiniz")
    await ctx.send(embed=embed)

@bot.command(name="kahvefali")
async def kahvefali(ctx, *, soru: str = None):
    """Gerçek kahve falı gibi detaylı fal bakar. Kullanım: !kahvefali [isteğe bağlı soru]"""
    async with ctx.typing():
        try:
            system_prompt = """
            Sen çok deneyimli bir Türk kahve falı ustası gibisin. 
            Gerçek kahve falı ustalarının yaptığı gibi detaylı ve anlamlı yorumlar yapacaksın.
            KAHVE FALI YORUMUNDA ŞUNLARI YAP:
            1. Kahve fincanındaki şekillere göre detaylı yorum yap
            2. Klasik Türk kahve falı sembollerini ve anlamlarını kullan
            3. Şekillerin konumlarını ve birbirleriyle ilişkilerini değerlendir
            4. Geleneksel kahve falı yorum tekniklerini uygula
            FAL YORUMU YAPARKEN:
            - Önce ana mesajı ver
            - Şekil yorumlarını detaylandır
            - Zaman dilimlerini belirt (yakın zaman, uzak zaman)
            - Şartlı durumları açıkla ("eğer... ise...")
            - Pozitif ve negatif olasılıkları değerlendir
            - Kullanıcı dostu ve ilham verici ol
            EĞER KULLANICI SORU SORDUYSA:
            - Soruya odaklı yorum yap
            - İlgili şekillere dikkat çek
            - Net cevap ver ama alternatifleri de göster
            EĞER SORU YOKSA:
            - Genel yaşam akışını yorumla
            - Aşk, para, sağlık, iş gibi temel alanları değerlendir
            - Kişisel gelişim önerileri sun
            YANIT FORMATI:
            ☕ GERÇEK KAHVE FALI ☕
            🔍 FİNDEKİ ŞEKİLLER:
            [Gözlemlenen şekilleri ve konumlarını listele]
            📖 ŞEKİL YORUMLARI:
            [Her şeklin detaylı yorumu]
            🎯 ANA MESAJ:
            [Kahvenin verdiği ana mesaj]
            ⏰ ZAMANLAMA:
            [Olayların ne zaman gerçekleşeceği]
            💭 DETAYLI YORUM:
            [Kapsamlı ve kişisel yorum]
            💫 REHBERLİK:
            [Kullanıcıya özel öneriler ve uyarılar]
            Dili samimi, geleneksel kahve falı ustaları gibi tut. 
            Türk kahve falı geleneklerine sadık kal.
            Her yorum kişisel, anlamlı ve ilham verici olsun.
            """

            if soru:
                user_prompt = f"Kullanıcının sorusu: '{soru}'. Bu soruya göre gerçek kahve falı gibi detaylı yorum yap."
            else:
                user_prompt = "Kullanıcı genel bir kahve falı yorumu istedi. Gerçek kahve falı ustası gibi detaylı yorum yap."

            response = await asyncio.wait_for(
                asyncio.to_thread(
                    g4f.ChatCompletion.create,
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                ),
                timeout=45.0
            )

            if response:
                # Uzun yanıtlar için dosya gönderme
                if len(response) > 3800:
                    filename = f"kahve_fali_{ctx.author.id}.txt"
                    with open(filename, "w", encoding="utf-8") as f:
                        f.write(f"☕ GERÇEK KAHVE FALI - {ctx.author}\n")
                        f.write(response)
                        f.write(f"\n📅 Fal Tarihi: {discord.utils.utcnow().strftime('%d.%m.%Y %H:%M')}")
                    
                    embed = discord.Embed(
                        title="☕ Gerçek Kahve Falı",
                        description="Fal yorumunuz çok detaylı olduğu için dosya olarak gönderildi.\nGeleneksel kahve falı yorumlarını içeren dosyayı inceleyin.",
                        color=discord.Color.from_rgb(139, 69, 19)
                    )
                    embed.set_footer(text=f"Fal bakan: {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
                    await ctx.send(embed=embed, file=discord.File(filename))
                    os.remove(filename)
                else:
                    embed = discord.Embed(
                        title="☕ Gerçek Kahve Falı",
                        description=response,
                        color=discord.Color.from_rgb(139, 69, 19)
                    )
                    embed.set_footer(text=f"Fal bakan: {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
                    await ctx.send(embed=embed)
            else:
                await ctx.send("❌ Kahve falı yorumu yapılırken bir hata oluştu. Lütfen tekrar dene.")

        except asyncio.TimeoutError:
            await ctx.send("⏳ Gerçek kahve falı yorumu yapılırken zaman aşımı oluştu. Lütfen tekrar dene.", delete_after=15)
        except Exception as e:
            logger.error(f"Gerçek kahve falı hatası: {e}", exc_info=True)
            await ctx.send("❌ Gerçek kahve falı yorumu yapılırken bir hata oluştu.", delete_after=15)

@bot.command(name="tarotfali")
async def tarotfali(ctx, kart_sayisi: int = 3, *, soru: str = None):
    """Tarot falı bakar. Kullanım: !tarotfali [kart sayısı] [soru]
    Kart sayısı: 1, 3, 7, 12 (varsayılan: 3)"""
    async with ctx.typing():
        try:
            # Geçerli kart sayılarını kontrol et
            if kart_sayisi not in [1, 3, 7, 12]:
                await ctx.send("❌ Geçersiz kart sayısı. Kullanılabilir seçenekler: 1, 3, 7, 12")
                return
            
            # Kart sayısına göre sistem promptu oluştur
            if kart_sayisi == 1:
                system_prompt = """
                Sen çok deneyimli bir tarot falı ustası gibisin. 
                Kullanıcıya tek kartlık güçlü ve odaklı bir tarot falı yorumu yapacaksın.
                TEK KARTI SEÇ VE YORUMLA:
                🎴 [Kart Adı]
                DETAYLI YORUM:
                - Kartın temel anlamı
                - Kullanıcı için özel mesajı
                - Zamanlama ve enerji
                - Rehberlik ve öneriler
                Dili samimi ve ilham verici tut.
                """
                
            elif kart_sayisi == 3:
                system_prompt = """
                Sen çok deneyimli bir tarot falı ustası gibisin. 
                Kullanıcıya 3 kartlık klasik past-present-future tarot falı yorumu yapacaksın.
                3 KARTI ŞU SIRAYLA YORUMLA:
                🎴 1. KART - Geçmiş/Kök Neden
                🎴 2. KART - Şimdiki Durum/Mevcut Enerji  
                🎴 3. KART - Gelecek/Potansiyel Sonuç
                GENEL YORUM:
                - 3 kartın birbiriyle bağlantısı
                - Ana mesaj ve rehberlik
                - Kullanıcı için öneriler
                Dili samimi ve ilham verici tut.
                """
                
            elif kart_sayisi == 7:
                system_prompt = """
                Sen çok deneyimli bir tarot falı ustası gibisin. 
                Kullanıcıya 7 kartlık kapsamlı ve detaylı bir tarot falı yorumu yapacaksın.
                7 KARTI ŞU SIRAYLA YORUMLA:
                🎴 1. KART - Geçmiş/Kök Neden
                🎴 2. KART - Şimdiki Durum/Mevcut Enerji  
                🎴 3. KART - Gelecek/Potansiyel Sonuç
                🎴 4. KART - Bilinçaltı/Zihinsel Durum
                🎴 5. KART - Duygusal Durum/Hisler
                🎴 6. KART - Dış Etkiler/Çevre
                🎴 7. KART - Sonuç/Rehberlik
                GENEL YORUM VE REHBERLİK:
                - 7 kartın birleşimi ve ana mesajlar
                - Kullanıcı için en önemli 3 öneri
                Dili samimi ve ilham verici tut.
                """
                
            elif kart_sayisi == 12:
                system_prompt = """
                Sen çok deneyimli bir tarot falı ustası gibisin. 
                Kullanıcıya 12 kartlık astrolojik tarot falı yorumu yapacaksın.
                Her kart bir burçla ilişkilidir ve kullanıcı için kapsamlı bir yorum yapılır.
                12 KARTI ŞU SIRAYLA YORUMLA:
                🎴 1. KART - Koç - Benlik ve irade
                🎴 2. KART - Boğa - Değerler ve güvenlik  
                🎴 3. KART - İkizler - İletişim ve zihin
                🎴 4. KART - Yengeç - Duygular ve ev
                🎴 5. KART - Aslan - Yaratıcılık ve ifade
                🎴 6. KART - Başak - Hizmet ve sağlık
                🎴 7. KART - Terazi - İlişkiler ve denge
                🎴 8. KART - Akrep - Dönüşüm ve gizli güçler
                🎴 9. KART - Yay - Genişlik ve felsefe
                🎴 10. KART - Oğlak - Yapı ve başarı
                🎴 11. KART - Kova - Yenilik ve dostluk
                🎴 12. KART - Balık - Sezgi ve ruh
                GENEL YORUM:
                - 12 kartın birleşimi ve yaşam haritası
                - Güçlü enerjiler ve fırsatlar
                - Gelişme alanları ve rehberlik
                Dili samimi ve ilham verici tut.
                """

            if soru:
                user_prompt = f"Kullanıcının sorusu: '{soru}'. Bu soruya göre {kart_sayisi} kartlık tarot falı yorumu yap."
            else:
                user_prompt = f"Kullanıcı genel bir tarot falı yorumu istedi. {kart_sayisi} kartlık detaylı tarot yorumu yap."

            response = await asyncio.wait_for(
                asyncio.to_thread(
                    g4f.ChatCompletion.create,
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                ),
                timeout=60.0 if kart_sayisi > 3 else 30.0
            )

            if response:
                title_map = {
                    1: "🃏 Tek Kartlık Tarot Falı",
                    3: "🃏 3 Kartlık Tarot Falı",
                    7: "🃏 7 Kartlık Detaylı Tarot Falı",
                    12: "🃏 12 Kartlık Astrolojik Tarot Falı"
                }
                
                embed = discord.Embed(
                    title=title_map[kart_sayisi],
                    description=response,
                    color=discord.Color.gold()
                )
                embed.set_footer(text=f"Fal bakan: {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
                await ctx.send(embed=embed)
            else:
                await ctx.send("❌ Tarot falı yorumu yapılırken bir hata oluştu. Lütfen tekrar dene.")

        except asyncio.TimeoutError:
            await ctx.send("⏳ Tarot falı yorumu yapılırken zaman aşımı oluştu. Lütfen tekrar dene.", delete_after=15)
        except Exception as e:
            logger.error(f"Tarot falı hatası: {e}", exc_info=True)
            await ctx.send("❌ Tarot falı yorumu yapılırken bir hata oluştu.", delete_after=15)

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

async def run_g4f_chat(channel_id, user_id, message, user_history):
    try:
        # Kullanıcı geçmişini stringe çevir
        history_context = "\n".join([f"{msg['author']}: {msg['content']}" for msg in user_history])
        
        system_prompt = """You are a helpful assistant. Speak in Turkish. 
        Consider the user's recent message history to provide more contextual responses.
        Be polite, concise, and avoid unnecessary details.
        If the user asks about previous conversations, refer to the history provided."""
        
        user_prompt = f"Recent conversation history:\n{history_context}\n\nUser ({user_id}) question: {message}"
        
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
    
    # Kullanıcı mesaj geçmişini güncelle
    user_histories[str(message.author.id)].append({
        "author": str(message.author),
        "content": message.content,
        "timestamp": datetime.datetime.now().isoformat()
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
            # Kullanıcıya özel geçmişi al
            user_history = user_histories[user_id]
            response_content = await run_g4f_chat(channel_id, user_id, message.content, user_history)
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
