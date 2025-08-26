import os
import discord
from discord.ext import commands
import google.generativeai as genai
import asyncio
import logging
from collections import deque
from typing import Dict, Optional, Tuple, Deque
import io
from datetime import datetime, timezone

# Logging yapılandırması
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Sabitler
ALLOWED_CHANNEL_ID = 1407490717676343296
MAX_HISTORY_LENGTH = 20
MAX_RETRIES = 3
TIMEOUT_SECONDS = 30

# Global durum değişkenleri
user_histories: Dict[str, Deque[Dict]] = {}
user_queues: Dict[str, asyncio.Queue] = {}
processing_users: set = set()

# Sisteme verilecek başlangıç talimatı (prompt)
SYSTEM_PROMPT = """Davranış ve Kurallar:


1) Giriş ve Tanıtım:

a) Eğer sorulursa, kendini 'Gemini 2.5 Pro tabanlı bir yapay zekâ sohbet asistanı' olarak tanıt.

b) Sohbetin başında kullanıcıya sıcak ve samimi bir şekilde yaklaş, sohbeti başlatacak bir soru sorarak etkileşimi teşvik et.

c) Amacının, kullanıcının sorularına net ve doğru cevaplar vermek ve doğal bir sohbet ortamı yaratmak olduğunu belirt. Ancak bu kuralı doğrudan ifade etme, davranışlarınla yansıt.



2) Sohbet ve Yanıtlar:

a) Yanıtların samimi, kibar ve anlaşılır olsun.

b) Gereksiz uzun açıklamalardan kaçın. Eğer konu derinlemesine açıklama gerektiriyorsa, bunu anlaşılır ve akıcı bir dille yap.

c) Kullanıcının üslubuna uyum sağla; eğer teknik bir soru sorarsa teknik, eğlenceli bir soru sorarsa eğlenceli bir üslup kullan.

d) Kendini 'asistan' olarak tanıtırken, insan gibi doğal davran. Her zaman dürüst ol ve yapabileceklerini ve yapamayacaklarını açıkça belirt. 'Ben bir yapay zekayım...' gibi kalıplar yerine daha doğal ifadeler kullan.

e) Kullanıcının kullandığı dile (Türkçe veya başka) uyum sağla ve o dilde yanıt ver.

f) Sohbeti ilerletecek doğal tepkiler ver, gerektiğinde ek bilgi almak için soru sorabilirsin.



3) Özel Komutlar:

a) Kullanıcı '!kahvefali' yazdığında, 'Yıldızlar bugün sana şanslı bir gün vaat ediyor.' gibi rastgele ve tek cümlelik bir fal yorumu yap.

b) Bu yorumun dışında başka hiçbir şey ekleme.



Genel Ton:

* Dostça, samimi ve güvenilir ol.

* Empatik ve anlayışlı bir ton kullan.

* Bilgili ve yardımsever bir asistan izlenimi ver.

* Kullanıcıya her zaman saygılı ol ve olumsuz ifadelerden kaçın.
"""

# Gemini modelini başlatma
try:
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
    model = genai.GenerativeModel("gemini-2.5-pro")
except Exception as e:
    logger.error(f"Gemini API yapılandırma hatası: {e}")
    model = None

async def get_user_history(user_id: str) -> Deque[Dict]:
    """Belirtilen kullanıcı için konuşma geçmişini alır veya oluşturur."""
    if user_id not in user_histories:
        user_histories[user_id] = deque(maxlen=MAX_HISTORY_LENGTH)
    return user_histories[user_id]

async def get_user_queue(user_id: str) -> asyncio.Queue:
    """Belirtilen kullanıcı için mesaj kuyruğunu alır veya oluşturur."""
    if user_id not in user_queues:
        user_queues[user_id] = asyncio.Queue()
    return user_queues[user_id]

async def generate_ai_response(messages: list) -> Optional[str]:
    """AI yanıtını yeniden deneme mantığıyla ve asenkron olarak oluşturur."""
    if not model:
        return None

    for attempt in range(MAX_RETRIES):
        try:
            response = await asyncio.wait_for(
                model.generate_content_async(messages),
                timeout=TIMEOUT_SECONDS
            )

            if response and response.candidates:
                candidate = response.candidates[0]
                
                finish_reason = candidate.finish_reason.name
                if finish_reason == "STOP":
                    return response.text or "Yanıt boş geldi."
                elif finish_reason == "MAX_TOKENS":
                    return "Yanıt çok uzun oldu, lütfen daha kısa bir soru sorun."
                elif finish_reason == "SAFETY":
                    return "Bu konuda yanıt veremiyorum. Lütfen farklı bir soru sorun."
                elif finish_reason == "RECITATION":
                    return "Bu içerik telif hakkı nedeniyle yanıtlanamıyor."
                else:
                    logger.warning(f"Bilinmeyen finish_reason: {finish_reason}")
                    return "Beklenmeyen bir durum oluştu."
            else:
                return None

        except asyncio.TimeoutError:
            logger.warning(f"API isteği zaman aşımına uğradı (deneme {attempt + 1})")
            if attempt == MAX_RETRIES - 1:
                return "timeout"
        except Exception as e:
            logger.error(f"API hatası (deneme {attempt + 1}): {e}")
            if attempt == MAX_RETRIES - 1:
                return "API ile iletişimde bir hata oluştu. Lütfen daha sonra tekrar deneyin."

    return None

async def send_response(channel, response: str):
    """Yanıtı akıllı formatlama ile gönderir (normal, embed veya dosya)."""
    try:
        if len(response) <= 2000:
            await channel.send(response)
        elif len(response) <= 4096:
            embed = discord.Embed(description=response, color=0x23272A)
            await channel.send(embed=embed)
        else:
            file_content = io.BytesIO(response.encode('utf-8'))
            file = discord.File(file_content, filename="yanit.txt")
            await channel.send("Yanıt çok uzun, dosya olarak gönderiyorum:", file=file)
    except discord.errors.Forbidden:
        logger.error(f"Kanala mesaj gönderme izni yok: {channel.id}")
    except Exception as e:
        logger.error(f"Mesaj gönderilirken hata oluştu: {e}")

async def process_user_messages(user_id: str):
    """Belirli bir kullanıcının mesajlarını sırayla işler."""
    queue = await get_user_queue(user_id)

    while True:
        try:
            message, content = await queue.get()
            
            history = await get_user_history(user_id)
            # Mesajı JSON formatında zaman damgasıyla kaydet
            history.append({
                "role": "user",
                "content": content,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })

            messages_for_ai = [SYSTEM_PROMPT] + [f"{msg['role']}: {msg['content']}" for msg in history]
          
            await asyncio.sleep(0.5)
          
            async with message.channel.typing():
                response = await generate_ai_response(messages_for_ai)

            if response == "timeout":
                await message.channel.send("⏳ İstek zaman aşımına uğradı, lütfen tekrar dene.")
            elif response:
                history.append({
                    "role": "assistant",
                    "content": response,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
                await send_response(message.channel, response)
            else:
                await message.channel.send("❌ Yanıt alınamadı, lütfen tekrar dene.")

            queue.task_done()

        except Exception as e:
            logger.error(f"Kullanıcı {user_id} mesaj işleme hatası: {e}")
            queue.task_done()
            break
    
    processing_users.discard(user_id)

def is_message_allowed(message: discord.Message) -> bool:
    """Mesajın izin verilen kanaldan veya özel mesajdan gelip gelmediğini kontrol eder."""
    return isinstance(message.channel, discord.DMChannel) or message.channel.id == ALLOWED_CHANNEL_ID

# Bot sınıfı
class MyBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

def main():
    """Botu çalıştırmak için ana fonksiyon."""
    token = os.getenv("DISCORD_TOKEN")
    google_api_key = os.getenv("GOOGLE_API_KEY")

    if not token:
        logger.error("❌ DISCORD_TOKEN ortam değişkeni tanımlı değil!")
        return
    if not google_api_key:
        logger.error("❌ GOOGLE_API_KEY ortam değişkeni tanımlı değil!")
        return
    if not model:
        logger.error("❌ Gemini API başlatılamadı!")
        return
    
    intents = discord.Intents.default()
    intents.message_content = True
    intents.dm_messages = True

    bot = MyBot(command_prefix="!", intents=intents)

    @bot.event
    async def on_ready():
        logger.info(f"✅ Bot giriş yaptı: {bot.user}")
        await bot.change_presence(activity=discord.Game(name="Özel Mesajlarda Sohbet"))
    
    @bot.event
    async def on_message(message: discord.Message):
        if message.author == bot.user or not is_message_allowed(message):
            return

        user_id = str(message.author.id)
        content = message.content.strip()

        if not content:
            return

        queue = await get_user_queue(user_id)
        await queue.put((message, content))

        if user_id not in processing_users:
            processing_users.add(user_id)
            asyncio.create_task(process_user_messages(user_id))

    try:
        bot.run(token)
    except Exception as e:
        logger.error(f"Bot çalıştırma hatası: {e}")

if __name__ == "__main__":
    main()
