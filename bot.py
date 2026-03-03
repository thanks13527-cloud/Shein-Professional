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
PREFIXES = ["SVD", "SVH", "SVI", "SVC"]
RANDOM_LENGTH = 12

def generate_random_code():
    prefix = random.choice(PREFIXES)
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=RANDOM_LENGTH))
    return prefix + random_part

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("✅ Check Voucher", callback_data="check")],
        [InlineKeyboardButton("🤖 Auto Generate Mode", callback_data="auto")]
    ]
    await update.message.reply_text(
        "Welcome 👋\nChoose mode:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global auto_active, auto_counter
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
        await q.message.reply_text(
            "🤖 Auto Generate Mode started!\n"
            "I'll show live results below.\n"
            "Use /stopauto to stop."
        )
        
        def valid_callback(code, status_code, is_valid):
            asyncio.run_coroutine_threadsafe(
                q.message.reply_text(
                    f"{'✅' if is_valid else '✗'} Auto #{auto_counter}: `{code}` -> {'Applicable' if is_valid else 'Not applicable'} ({status_code})",
                    parse_mode="Markdown"
                ),
                asyncio.get_running_loop()
            )
        
        def auto_loop():
            global auto_counter, auto_active
            while auto_active:
                code = generate_random_code()
                auto_counter += 1
                print(f"🤖 Auto #{auto_counter}: Checking {code}")
                
                # First attempt
                result = check_voucher(code)
                if result is None:
                    # Failed - recheck once
                    print(f"🔄 Rechecking failed voucher: {code}")
                    time.sleep(2)
                    result = check_voucher(code)
                
                if result:
                    code, is_valid, msg = result
                    status_code = msg.split('(')[-1].rstrip(')') if '(' in msg else '200'
                    valid_callback(code, status_code, is_valid)
                else:
                    valid_callback(code, 'Timeout', False)
                
                time.sleep(2)
        
        thread = threading.Thread(target=auto_loop, daemon=True)
        thread.start()

# File upload handler (unchanged)
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc.file_name.endswith(".txt"):
        await update.message.reply_text("❌ Only TXT files allowed.")
        return

    uid = update.message.from_user.id
    file = await doc.get_file()
    path = f"{uid}_vouchers.txt"
    await file.download_to_drive(path)

    await update.message.reply_text("⚡ Starting fast check...")

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
    global auto_active
    auto_active = False
    await update.message.reply_text(f"🛑 Auto mode stopped. Total checked: {auto_counter}")

def main():
    print("⚡ Ultra Fast Bot with Auto Mode started...")
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stopauto", stopauto))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    app.run_polling()

if __name__ == "__main__":
    main()
