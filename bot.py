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
from concurrent.futures import ThreadPoolExecutor, as_completed

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN missing")

from voucher_checker import check_voucher, process_vouchers

# ========== RATE LIMITER FOR TELEGRAM ==========
class RateLimiter:
    def __init__(self, max_per_second=20):
        self.max_per_second = max_per_second
        self.lock = asyncio.Lock()
        self.tokens = max_per_second
        self.last_refill = time.time()
    
    async def acquire(self):
        async with self.lock:
            now = time.time()
            elapsed = now - self.last_refill
            self.tokens = min(self.max_per_second, self.tokens + elapsed * self.max_per_second)
            self.last_refill = now
            
            if self.tokens < 1:
                wait = 1 / self.max_per_second
                await asyncio.sleep(wait)
                self.tokens = 0
            else:
                self.tokens -= 1

rate_limiter = RateLimiter(max_per_second=20)

async def safe_send_message(chat_id, text, parse_mode=None, reply_markup=None, bot=None):
    await rate_limiter.acquire()
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup
        )
    except Exception as e:
        print(f"Send error: {e}")

# ========== GLOBAL VARIABLES ==========
auto_active = False
auto_counter = 0
valid_counter = 0
PREFIX = "SVC"  # 🔥 Sirf SVC prefix
RANDOM_LENGTH = 12
status_message = None
start_time = None
loop = None
auto_thread = None
status_thread = None
executor = ThreadPoolExecutor(max_workers=15)  # ⚡ 15 parallel workers

def generate_random_code():
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=RANDOM_LENGTH))
    return PREFIX + random_part  # SVC + 12 random chars = 15 total

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = """
╔══════════════════════════╗
║        VOUCHER BOT       ║
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
    global auto_thread, status_thread
    
    try:
        q = update.callback_query
        await q.answer()
        
        if q.data == "check":
            await q.message.reply_text("📂 Upload voucher TXT file.")
            return
        
        elif q.data == "auto":
            # Stop existing auto mode
            if auto_active:
                auto_active = False
                if auto_thread and auto_thread.is_alive():
                    auto_thread.join(timeout=2)
                if status_thread and status_thread.is_alive():
                    status_thread.join(timeout=2)
                time.sleep(1)
            
            # Reset counters
            auto_counter = 0
            valid_counter = 0
            start_time = time.time()
            loop = asyncio.get_running_loop()
            auto_active = True
            
            # Send fresh message
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
            
            # Status updater thread
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
                        try:
                            asyncio.run_coroutine_threadsafe(
                                status_message.edit_text(status_text, reply_markup=InlineKeyboardMarkup(keyboard)),
                                loop
                            )
                        except:
                            pass
            
            # Auto check thread
            def auto_loop():
                global auto_counter, valid_counter, auto_active
                
                while auto_active:
                    codes = [generate_random_code() for _ in range(15)]  # ⚡ 15 codes per batch
                    futures = []
                    for code in codes:
                        if not auto_active:
                            break
                        futures.append(executor.submit(check_voucher, code))
                    
                    for future in as_completed(futures):
                        if not auto_active:
                            break
                        
                        auto_counter += 1
                        current_count = auto_counter
                        
                        result = future.result()
                        
                        if result:
                            c, is_valid, msg = result
                            status = msg.split('(')[-1].rstrip(')')
                            emoji = "✅" if is_valid else "✗"
                            status_text = "Applicable" if is_valid else "Not applicable"
                            
                            print(f"{emoji} Auto #{current_count}: {c} -> {status_text} ({status})")
                            
                            if is_valid:
                                valid_counter += 1
                                try:
                                    asyncio.run_coroutine_threadsafe(
                                        safe_send_message(
                                            chat_id=q.message.chat_id,
                                            text=f"{emoji} Auto #{current_count}: `{c}` -> {status_text} ({status})",
                                            parse_mode="Markdown",
                                            bot=context.bot
                                        ),
                                        loop
                                    )
                                except:
                                    pass
            
            status_thread = threading.Thread(target=update_status, daemon=True)
            auto_thread = threading.Thread(target=auto_loop, daemon=True)
            status_thread.start()
            auto_thread.start()
            return
        
        elif q.data == "stop_auto":
            # Stop auto mode
            auto_active = False
            if auto_thread and auto_thread.is_alive():
                auto_thread.join(timeout=2)
            if status_thread and status_thread.is_alive():
                status_thread.join(timeout=2)
            time.sleep(1)
            
            # Update stop message
            if status_message:
                keyboard = [[InlineKeyboardButton("▶️ RESTART AUTO", callback_data="auto")]]
                try:
                    await status_message.edit_text(
                        f"✅ Auto mode stopped.\nTotal checked: {auto_counter} | Valid: {valid_counter}",
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                except Exception as e:
                    print(f"Stop error: {e}")
            return
            
    except Exception as e:
        print(f"Button handler error: {e}")

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        doc = update.message.document
        if not doc.file_name.endswith(".txt"):
            await update.message.reply_text("❌ Only TXT files allowed.")
            return

        uid = update.message.from_user.id
        file = await doc.get_file()
        path = f"{uid}_vouchers.txt"
        await file.download_to_drive(path)

        await safe_send_message(
            chat_id=update.message.chat_id,
            text="⚡ Processing file...",
            bot=context.bot
        )

        status_msg = await update.message.reply_text("Checking...\n\nProcessed: 0\nValid: 0")

        with open(path, "r", encoding="utf-8") as f:
            codes = [v.strip() for v in f if v.strip()]

        unique, seen = [], set()
        for c in codes:
            if c not in seen:
                unique.append(c)
                seen.add(c)

        if len(codes) != len(unique):
            await safe_send_message(
                chat_id=update.message.chat_id,
                text=f"📊 Removed {len(codes)-len(unique)} duplicates. Checking {len(unique)} unique.",
                bot=context.bot
            )

        loop = asyncio.get_running_loop()
        valid_vouchers = []

        def on_valid_found(voucher_code):
            asyncio.run_coroutine_threadsafe(
                safe_send_message(
                    chat_id=update.message.chat_id,
                    text=f"✅ Valid: `{voucher_code}`",
                    parse_mode="Markdown",
                    bot=context.bot
                ),
                loop
            )

        def progress(current, total, valid_count):
            asyncio.run_coroutine_threadsafe(
                status_msg.edit_text(f"Checking...\n\nProcessed: {current}\nValid: {valid_count}"),
                loop
            )

        with ThreadPoolExecutor(max_workers=5) as file_executor:
            futures = [file_executor.submit(check_voucher, code) for code in unique]
            
            for i, future in enumerate(as_completed(futures), 1):
                result = future.result()
                if result:
                    code, ok, msg = result
                    mark = "✓" if ok else "✗"
                    print(f"{i}/{len(unique)} [{mark}] {code} -> {msg}")
                    
                    if ok:
                        valid_vouchers.append(code)
                        on_valid_found(code)
                    
                    progress(i, len(unique), len(valid_vouchers))

        await safe_send_message(
            chat_id=update.message.chat_id,
            text=f"✅ Done. Total valid: {len(valid_vouchers)}",
            bot=context.bot
        )
        await status_msg.edit_text(f"✅ Completed. Valid: {len(valid_vouchers)}")
        os.remove(path)
    except Exception as e:
        print(f"File handler error: {e}")
        await safe_send_message(
            chat_id=update.message.chat_id,
            text="❌ Error processing file.",
            bot=context.bot
        )

def main():
    print("🚀 VOUCHER BOT started...")
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    app.run_polling()

if __name__ == "__main__":
    main()
