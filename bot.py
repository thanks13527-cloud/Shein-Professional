import os
import asyncio
import threading
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN missing")

from voucher_checker import process_vouchers, start_auto_check

# Global counters
total_checked = 0
valid_found = 0
start_time = None

# ========== START COMMAND ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global start_time
    start_time = time.time()
    
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
        [InlineKeyboardButton("📂 Upload TXT File", callback_data="check")],
        [InlineKeyboardButton("🤖 Auto Generate Mode", callback_data="auto")],
        [InlineKeyboardButton("📊 Statistics", callback_data="stats")]
    ]
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ========== BUTTON HANDLER ==========
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global total_checked, valid_found, start_time
    
    q = update.callback_query
    await q.answer()
    
    if q.data == "check":
        await q.message.reply_text("📂 Please upload your voucher TXT file.")
    
    elif q.data == "auto":
        await q.message.reply_text(
            "🤖 Auto Generate Mode activated!\n\n"
            "I will notify you whenever a valid voucher is found."
        )
        
        def valid_callback(code):
            global valid_found
            valid_found += 1
            asyncio.run_coroutine_threadsafe(
                q.message.reply_text(f"✅✅✅ VALID VOUCHER: `{code}`", parse_mode="Markdown"),
                asyncio.get_running_loop()
            )
        
        def update_counter():
            global total_checked
            total_checked += 1
        
        # Start auto check in background
        thread = threading.Thread(
            target=start_auto_check,
            args=(valid_callback, update_counter),
            daemon=True
        )
        thread.start()
    
    elif q.data == "stats":
        elapsed = time.time() - start_time if start_time else 1
        speed = int(total_checked / (elapsed / 60)) if elapsed > 0 else 0
        
        stats_text = f"""
╔══════════════════════════╗
║      📊 STATISTICS       ║
╠══════════════════════════╣
║ 📋 Total Checked: {total_checked}
║ ✅ Valid Found: {valid_found}
║ ⚡ Speed: {speed}/min
╚══════════════════════════╝
        """
        
        await q.message.reply_text(stats_text)

# ========== FILE UPLOAD HANDLER ==========
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

    # Remove duplicates
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

# ========== MAIN ==========
def main():
    print("🚀 VOUCHER BOT started...")
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    app.run_polling()

if __name__ == "__main__":
    main()
