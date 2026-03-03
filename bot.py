import os
import asyncio
import threading
import time
import random
import string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN missing")

from voucher_checker import check_voucher, process_vouchers

# Auto mode variables
auto_active = False
auto_counter = 0
valid_counter = 0
PREFIXES = ["SVD", "SVH", "SVI", "SVC"]
RANDOM_LENGTH = 12
status_message = None
start_time = None
loop = None

def generate_random_code():
    prefix = random.choice(PREFIXES)
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=RANDOM_LENGTH))
    return prefix + random_part

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = """
╔══════════════════════════╗
║     🎫 VOUCHER BOT       ║
╠══════════════════════════╣
║ • Fast checking          ║
║ • Auto generate mode     ║
║ • Real-time valid alerts ║
╚══════════════════════════╝

Choose mode below 👇
    """
    
    keyboard = [
        [InlineKeyboardButton("✅ Check Voucher", callback_data="check")],
        [InlineKeyboardButton("🤖 Auto Generate", callback_data="auto")]
    ]
    await update.message.reply_text(
        welcome_text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global auto_active, auto_counter, valid_counter, status_message, start_time, loop
    q = update.callback_query
    await q.answer()
    
    if q.data == "check":
        await q.message.reply_text("📂 Upload voucher TXT file.")
    
    elif q.data == "auto":
        if auto_active:
            await q.message.reply_text("⚠️ Auto mode already running!")
            return
            
        auto_active = True
        auto_counter = 0
        valid_counter = 0
        start_time = time.time()
        loop = asyncio.get_running_loop()
        
        # Send live status message with stop button
        status_text = """
╔══════════════════════════╗
║     🤖 AUTO MODE ON      ║
╠══════════════════════════╣
║ 📊 Checked: 0            ║
║ ✅ Valid: 0              ║
║ ⚡ Speed: 0/min          ║
╚══════════════════════════╝
        """
        
        keyboard = [[InlineKeyboardButton("🛑 STOP AUTO", callback_data="stop_auto")]]
        status_message = await q.message.reply_text(
            status_text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        def update_status():
            global auto_counter, valid_counter, status_message, start_time, auto_active, loop
            while auto_active:
                time.sleep(1)
                if status_message and start_time:
                    elapsed = time.time() - start_time
                    speed = int(auto_counter / (elapsed / 60)) if elapsed > 0 else 0
                    status_text = f"""
╔══════════════════════════╗
║     🤖 AUTO MODE ON      ║
╠══════════════════════════╣
║ 📊 Checked: {auto_counter}            ║
║ ✅ Valid: {valid_counter}              ║
║ ⚡ Speed: {speed}/min          ║
╚══════════════════════════╝
                    """
                    keyboard = [[InlineKeyboardButton("🛑 STOP AUTO", callback_data="stop_auto")]]
                    asyncio.run_coroutine_threadsafe(
                        status_message.edit_text(status_text, reply_markup=InlineKeyboardMarkup(keyboard)),
                        loop
                    )
        
        def send_message(text):
            asyncio.run_coroutine_threadsafe(
                q.message.reply_text(text, parse_mode="Markdown"),
                loop
            )
        
        def auto_loop():
            global auto_counter, valid_counter, auto_active
            while auto_active:
                code = generate_random_code()
                auto_counter += 1
                
                # First attempt
                result = check_voucher(code)
                
                if result is None:
                    # Recheck failed
                    time.sleep(1)
                    result = check_voucher(code, is_retry=True)
                
                if result:
                    c, is_valid, msg = result
                    status = msg.split('(')[-1].rstrip(')')
                    emoji = "✅" if is_valid else "✗"
                    status_text = "Applicable" if is_valid else "Not applicable"
                    
                    if is_valid:
                        valid_counter += 1
                        send_message(f"{emoji} Auto #{auto_counter}: `{c}` -> {status_text} ({status})")
                    else:
                        print(f"{emoji} Auto #{auto_counter}: {c} -> {status_text} ({status})")
                else:
                    print(f"❌ Auto #{auto_counter}: {code} -> Failed")
                
                time.sleep(1)  # ⚡ Fast delay
        
        # Start status updater thread
        threading.Thread(target=update_status, daemon=True).start()
        # Start auto check thread
        threading.Thread(target=auto_loop, daemon=True).start()
    
    elif q.data == "stop_auto":
        await stopauto(update, context)

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc.file_name.endswith(".txt"):
        await update.message.reply_text("❌ Only TXT files allowed.")
        return

    uid = update.message.from_user.id
    file = await doc.get_file()
    path = f"{uid}_vouchers.txt"
    await file.download_to_drive(path)

    await update.message.reply_text("⚡ Processing file...")

    status_msg = await update.message.reply_text("Checking...\n\nProcessed: 0\nValid: 0")

    with open(path, "r", encoding="utf-8") as f:
        codes = [v.strip() for v in f if v.strip()]

    unique, seen = [], set()
    for c in codes:
        if c not in seen:
            unique.append(c)
            seen.add(c)

    if len(codes) != len(unique):
        await update.message.reply_text(f"📊 Removed {len(codes)-len(unique)} duplicates. Checking {len(unique)} unique.")

    loop = asyncio.get_running_loop()

    def on_valid_found(voucher_code):
        asyncio.run_coroutine_threadsafe(
            update.message.reply_text(f"✅ Valid: `{voucher_code}`", parse_mode="Markdown"),
            loop
        )

    def progress(current, total, valid_count):
        asyncio.run_coroutine_threadsafe(
            status_msg.edit_text(f"Checking...\n\nProcessed: {current}\nValid: {valid_count}"),
            loop
        )

    valid_vouchers = await asyncio.to_thread(
        process_vouchers,
        unique,
        progress,
        on_valid_found,
        uid
    )

    await update.message.reply_text(f"✅ Done. Total valid: {len(valid_vouchers)}")
    await status_msg.edit_text(f"✅ Completed. Valid: {len(valid_vouchers)}")
    os.remove(path)

async def stopauto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global auto_active, status_message
    auto_active = False
    if status_message:
        keyboard = [[InlineKeyboardButton("▶️ RESTART AUTO", callback_data="auto")]]
        await status_message.edit_text(
            f"🛑 Auto mode stopped.\nTotal checked: {auto_counter} | Valid: {valid_counter}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        status_message = None

def main():
    print("🚀 VOUCHER BOT started...")
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    app.run_polling()

if __name__ == "__main__":
    main()
