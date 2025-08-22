import discord
import google.generativeai as genai
import asyncio
import json
import os
import logging
from collections import deque
import sys

# === CONFIGURATION FROM ENVIRONMENT VARIABLES ===
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')

# CHANNEL_ID boşsa varsayılanı kullan
CHANNEL_ID_STR = os.getenv('CHANNEL_ID', '')
if CHANNEL_ID_STR:
    CHANNEL_ID = int(CHANNEL_ID_STR)
else:
    CHANNEL_ID = 1407490717676343296  # Varsayılan kanal ID

MAX_HISTORY = 20
TIMEOUT = 30
MAX_RETRIES = 3
MESSAGES_TO_CHECK = 10

# === SETUP LOGGING ===
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# === VALIDATION ===
if not DISCORD_TOKEN:
    logging.error("DISCORD_TOKEN environment variable not set!")
    sys.exit(1)

if not GOOGLE_API_KEY:
    logging.error("GOOGLE_API_KEY environment variable not set!")
    sys.exit(1)

# === GEMINI SETUP ===
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

# === DATA FILE HANDLING ===
DATA_FILE = "chat_histories.json"

def save_histories(user_histories):
    """Geçmişleri dosyaya kaydet"""
    try:
        data = {str(uid): list(hist) for uid, hist in user_histories.items()}
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logging.info("Chat histories saved successfully")
    except Exception as e:
        logging.error(f"Error saving histories: {e}")

def load_histories():
    """Geçmişleri dosyadan yükle"""
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            histories = {int(uid): deque(hist, maxlen=MAX_HISTORY) for uid, hist in data.items()}
            logging.info(f"Loaded histories for {len(histories)} users")
            return histories
        else:
            logging.info("No history file found, starting fresh")
            return {}
    except Exception as e:
        logging.error(f"Error loading histories: {e}")
        return {}

# === MAIN BOT LOGIC ===
async def get_last_messages(channel, limit=10):
    """Son mesajları al"""
    messages = []
    try:
        async for message in channel.history(limit=limit):
            if not message.author.bot and message.content.strip():
                messages.append(message)
        messages.reverse()  # En eskiden en yeniye
        logging.info(f"Retrieved {len(messages)} messages from channel")
        return messages
    except Exception as e:
        logging.error(f"Error retrieving messages: {e}")
        return []

async def process_message_with_gemini(message_content, history):
    """Gemini ile mesajı işle"""
    try:
        # Geçmiş formatını Gemini için hazırla
        prompt_history = list(history)
        prompt = prompt_history + [{"role": "user", "parts": [message_content]}]
        
        retries = 0
        while retries < MAX_RETRIES:
            try:
                response = await asyncio.wait_for(
                    model.generate_content_async(prompt),
                    timeout=TIMEOUT
                )
                if response.text:
                    logging.info("Successfully generated response with Gemini")
                    return response.text
                else:
                    logging.warning("Empty response from Gemini")
                    return None
            except asyncio.TimeoutError:
                logging.warning(f"Timeout on attempt {retries + 1}")
                retries += 1
            except Exception as e:
                logging.error(f"Error on attempt {retries + 1}: {e}")
                retries += 1
                if retries >= MAX_RETRIES:
                    break
                await asyncio.sleep(2)
        
        logging.error("Failed to get response after max retries")
        return None
    except Exception as e:
        logging.error(f"Error in process_message_with_gemini: {e}")
        return None

async def send_response(channel, response_text):
    """Yanıtı uygun formatta gönder"""
    try:
        if len(response_text) < 2000:
            message = await channel.send(response_text)
            logging.info("Sent response as regular message")
            return message
        elif len(response_text) < 4000:
            embed = discord.Embed(description=response_text[:4096])
            message = await channel.send(embed=embed)
            logging.info("Sent response as embed")
            return message
        else:
            filename = "response.txt"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(response_text)
            message = await channel.send("Cevap çok uzun, dosya olarak gönderiliyor:", file=discord.File(filename))
            os.remove(filename)
            logging.info("Sent response as file")
            return message
    except Exception as e:
        logging.error(f"Error sending response: {e}")
        return None

async def main():
    """Ana fonksiyon"""
    logging.info("Starting Discord Gemini Bot")
    logging.info(f"Target channel ID: {CHANNEL_ID}")
    
    # Geçmişleri yükle
    user_histories = load_histories()
    
    # Discord client oluştur
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)
    
    @client.event
    async def on_ready():
        logging.info(f'Logged in as {client.user}')
        
        # Kanalı bul
        channel = client.get_channel(CHANNEL_ID)
        if not channel:
            logging.error(f"Channel {CHANNEL_ID} not found!")
            await client.close()
            return
            
        logging.info(f"Processing channel: {channel.name} (ID: {channel.id})")
        
        # Son mesajları al
        messages = await get_last_messages(channel, MESSAGES_TO_CHECK)
        
        if not messages:
            logging.info("No new messages to process")
            await client.close()
            return
        
        # Her mesajı işle
        processed_count = 0
        for message in messages:
            user_id = message.author.id
            
            # Kullanıcı için geçmiş oluştur
            if user_id not in user_histories:
                user_histories[user_id] = deque(maxlen=MAX_HISTORY)
            
            history = user_histories[user_id]
            
            # Mesaj zaten işlenmiş mi kontrol et
            message_already_processed = any(
                isinstance(entry, dict) and entry.get('message_id') == message.id 
                for entry in history
            )
            
            if message_already_processed:
                logging.info(f"Message {message.id} already processed, skipping")
                continue
            
            logging.info(f"Processing message from {message.author}: {message.content[:50]}...")
            
            # Gemini ile yanıt üret
            response_text = await process_message_with_gemini(message.content, history)
            
            if response_text:
                # Geçmişe ekle
                history.append({
                    "message_id": message.id,
                    "role": "user",
                    "parts": [message.content],
                    "timestamp": message.created_at.isoformat()
                })
                
                history.append({
                    "role": "model",
                    "parts": [response_text],
                    "timestamp": discord.utils.utcnow().isoformat()
                })
                
                # Yanıtı gönder
                sent_message = await send_response(channel, response_text)
                if sent_message:
                    processed_count += 1
                    logging.info(f"Successfully responded to message {message.id}")
                    
                    # Rate limit önlemek için bekle
                    await asyncio.sleep(2)
            else:
                logging.warning(f"Failed to generate response for message {message.id}")
        
        # Geçmişleri kaydet
        save_histories(user_histories)
        
        logging.info(f"Bot run completed. Processed {processed_count} messages.")
        await client.close()
    
    # Botu başlat
    try:
        await client.start(DISCORD_TOKEN)
    except Exception as e:
        logging.error(f"Error starting bot: {e}")
        sys.exit(1)

# === RUN ===
if __name__ == "__main__":
    asyncio.run(main())
