import os
import discord
from discord.ext import commands
from g4f.client import Client
from g4f.Provider import PuterJS
import asyncio
import logging
from collections import deque
from typing import Dict, Optional, Tuple, Deque
import io
from datetime import datetime, timezone
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

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
SYSTEM_PROMPT = """Sen, Discord sunucularında veya DM’lerde kullanıcılarla doğal ve samimi sohbetler kuran bir yapay zekasın. Adın Hel. Görevlerin:

1. **Doğal Sohbet:** Kullanıcılarla anlamlı, empatik ve akıcı sohbetler yap. Mesajları dikkatle oku, bağlamı anla ve yanıt ver.
2. **Kullanıcı Geçmişine Duyarlılık:** Kullanıcının önceki mesajlarını dikkate alarak tutarlı ve bağlama uygun yanıtlar oluştur.
3. **Bilgi ve Yardım:** Sorulan sorulara doğru, güncel ve anlaşılır cevap ver. Gerektiğinde kısa açıklamalar veya örnekler ekle.
4. **Kibar ve Nazik:** Uygunsuz, saldırgan veya spam içeriklere karşı dikkatli ol; gerektiğinde kibarca uyar.  
5. **Mizah ve Eğlence:** Sohbeti canlı tutmak için uygun yerlerde espri, emoji veya hafif mizah kullan.  
6. **Dil ve Tarz:** Türkçe ve İngilizce’de akıcı ve doğal konuş. Dil bilgisi hatası yapma.  
7. **Mesaj Uzunluğu ve Formatlama:** Yanıtlar 2000 karakteri geçiyorsa embed veya dosya olarak gönderilebileceğini bil; ama yanıtlarını mümkün olduğunca kısa ve anlaşılır tut.  
8. **Komutsuz Çalış:** Kullanıcılar doğrudan mesaj yazdığında yanıt ver, komut bekleme.  

**Ek Talimat:** Yanıt verirken kullanıcıya değer kat, onu sohbete dahil et ve konuyu kapatmadığı sürece etkileşimi teşvik et. Gereksiz tekrar ve boş mesajlardan kaçın.
"""

# PuterJS client'ı başlatma
try:
    api_key = os.getenv("PUTER_API_KEY")
    
    client = Client(
        provider=PuterJS,
        api_key=api_key
    )
    model_name = 'o3'
except Exception as e:
    logger.error(f"PuterJS API yapılandırma hatası: {e}")
    client = None
    model_name = None

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
    if not client or not model_name:
        return None

    for attempt in range(MAX_RETRIES):
        try:
            # Convert messages to the format expected by g4f
            formatted_messages = []
            for msg in messages:
                if isinstance(msg, str):
                    if msg.startswith("user:"):
                        formatted_messages.append({"role": "user", "content": msg[5:].strip()})
                    elif msg.startswith("assistant:"):
                        formatted_messages.append({"role": "assistant", "content": msg[10:].strip()})
                    # elif not any(msg.startswith(prefix) for prefix in ["user:", "assistant:"]):
                        # This is likely the system prompt
                       # formatted_messages.insert(0, {"role": "system", "content": msg})
                elif isinstance(msg, dict):
                    formatted_messages.append(msg)

            # Ensure we have at least one user message
            if not any(msg.get("role") == "user" for msg in formatted_messages):
                return "Lütfen bir mesaj yazın."

            # Run the synchronous call in a thread pool to avoid blocking
            if client is None or model_name is None:
                return "Client or model not initialized"
            
            # Type assertion for mypy/pylint
            client_instance = client
            model_instance = model_name
            
            loop = asyncio.get_event_loop()
            response = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: client_instance.chat.completions.create(
                        model=model_instance,
                        messages=formatted_messages,
                        stream=False
                    )
                ),
                timeout=TIMEOUT_SECONDS
            )

            if response and response.choices:
                content = response.choices[0].message.content
                if content:
                    return content.strip()
                else:
                    return "Yanıt boş geldi."
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

            messages_for_ai = [f"{msg['role']}: {msg['content']}" for msg in history]
            # or
            # messages_for_ai = [SYSTEM_PROMPT] + [f"{msg['role']}: {msg['content']}" for msg in history]

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
    puter_api_key = os.getenv("PUTER_API_KEY")

    if not token:
        logger.error("❌ DISCORD_TOKEN ortam değişkeni tanımlı değil!")
        return
    if not puter_api_key:
        logger.warning("⚠️ PUTER_API_KEY ortam değişkeni tanımlı değil, varsayılan anahtar kullanılıyor!")
    if not client or not model_name:
        logger.error("❌ PuterJS API başlatılamadı!")
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
