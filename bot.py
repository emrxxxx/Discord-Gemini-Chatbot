import os
import discord
from discord.ext import commands
import google.generativeai as genai
import asyncio
import logging
from collections import deque
from typing import Dict, Optional

# Logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
ALLOWED_CHANNEL_ID = 1407490717676343296
MAX_HISTORY_LENGTH = 20
MAX_RETRIES = 3
TIMEOUT_SECONDS = 30

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Global state
user_histories: Dict[str, deque] = {}
user_queues: Dict[str, asyncio.Queue] = {}
processing_users: set = set()

# System prompt
SYSTEM_PROMPT = """Sen Gemini 2.5 Pro tabanlı bir yapay zekâ sohbet asistanısın. 
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

# Initialize Gemini
try:
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
    model = genai.GenerativeModel("gemini-2.5-pro")
except Exception as e:
    logger.error(f"Gemini API yapılandırma hatası: {e}")
    model = None

async def get_user_history(user_id: str) -> deque:
    """Get or create user conversation history."""
    if user_id not in user_histories:
        user_histories[user_id] = deque(maxlen=MAX_HISTORY_LENGTH)
    return user_histories[user_id]

async def get_user_queue(user_id: str) -> asyncio.Queue:
    """Get or create user message queue."""
    if user_id not in user_queues:
        user_queues[user_id] = asyncio.Queue()
    return user_queues[user_id]

async def process_user_messages(user_id: str):
    """Process messages for a specific user sequentially."""
    queue = await get_user_queue(user_id)
    
    while True:
        try:
            # Get message from queue
            message_data = await queue.get()
            if message_data is None:  # Shutdown signal
                break
                
            message, content = message_data
            
            # Get user history and add new message
            history = await get_user_history(user_id)
            history.append(content)

            # Prepare messages for AI
            messages = [SYSTEM_PROMPT] + list(history)

            # 2 saniye bekle
            await asyncio.sleep(0.5)

            async with message.channel.typing():

                response = await generate_ai_response(messages)

                await asyncio.sleep(0.5)
                
                if response == "timeout":
                    await message.channel.send("⏳ İstek zaman aşımına uğradı, lütfen tekrar dene.")
                elif response:
                    history.append(response)
                    # Split long messages if needed
                    if len(response) > 2000:
                        for i in range(0, len(response), 2000):
                            await message.channel.send(response[i:i+2000])
                    else:
                        await message.channel.send(response)
                else:
                    await message.channel.send("❌ Yanıt alınamadı, lütfen tekrar dene.")
            
            queue.task_done()
            
        except Exception as e:
            logger.error(f"User {user_id} mesaj işleme hatası: {e}")
            queue.task_done()
    
    # Clean up when done
    processing_users.discard(user_id)

async def generate_ai_response(messages: list) -> Optional[str]:
    """Generate AI response with retry logic."""
    if not model:
        return None
        
    for attempt in range(MAX_RETRIES):
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(model.generate_content, [msg for msg in messages]),
                timeout=TIMEOUT_SECONDS
            )
            
            # Check if response has valid content
            if response and response.candidates:
                candidate = response.candidates[0]
                
                # Check finish reason
                if candidate.finish_reason == 1:  # STOP - normal completion
                    return response.text if response.text else "Yanıt boş geldi."
                elif candidate.finish_reason == 2:  # MAX_TOKENS
                    return "Yanıt çok uzun oldu, lütfen daha kısa bir soru sorun."
                elif candidate.finish_reason == 3:  # SAFETY
                    return "Bu konuda yanıt veremiyorum. Lütfen farklı bir soru sorun."
                elif candidate.finish_reason == 4:  # RECITATION
                    return "Bu içerik telif hakkı nedeniyle yanıtlanamıyor."
                else:
                    logger.warning(f"Bilinmeyen finish_reason: {candidate.finish_reason}")
                    return "Beklenmeyen bir durum oluştu."
            else:
                return None
                
        except asyncio.TimeoutError:
            logger.warning(f"Timeout on attempt {attempt + 1}")
            if attempt == MAX_RETRIES - 1:
                return "timeout"
        except Exception as e:
            error_msg = str(e)
            logger.error(f"API error on attempt {attempt + 1}: {error_msg}")
            
            # Handle specific error types
            if "response.text" in error_msg and "finish_reason" in error_msg:
                return "Bu konuda yanıt veremiyorum. Lütfen farklı bir soru sorun."
            elif attempt == MAX_RETRIES - 1:
                return None
                
    return None

def is_message_allowed(message: discord.Message) -> bool:
    """Check if message is from allowed channel or DM."""
    return (isinstance(message.channel, discord.DMChannel) or 
            message.channel.id == ALLOWED_CHANNEL_ID)

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
    
    if not content:  # Skip empty messages
        return

    # Get user queue and add message
    queue = await get_user_queue(user_id)
    await queue.put((message, content))
    
    # Start processing for this user if not already running
    if user_id not in processing_users:
        processing_users.add(user_id)
        asyncio.create_task(process_user_messages(user_id))

    await bot.process_commands(message)

def main():
    """Main function to run the bot."""
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
    
    try:
        bot.run(token)
    except Exception as e:
        logger.error(f"Bot çalıştırma hatası: {e}")

if __name__ == "__main__":
    main()
