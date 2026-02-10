import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from datetime import datetime, timedelta
import sqlite3
import json
import os
from threading import Timer
import asyncio

# Konfigurasi
TOKEN = "TOKEN_BOT_ANDA"
OWNER_ID = YOUR_OWNER_ID  # Ganti dengan ID Telegram Anda
CHANNEL_USERNAME = "@nama_channel_anda"  # Ganti dengan username channel
LOG_CHANNEL_ID = -1001234567890  # Ganti dengan ID channel log
CHANNEL_ID = -1001234567891  # Ganti dengan ID channel premium

# Harga premium
PRICES = {
    "7_hari": {"price": 20000, "days": 7},
    "30_hari": {"price": 50000, "days": 30},
    "1_tahun": {"price": 80000, "days": 365},
    "lifetime": {"price": 110000, "days": 99999}
}

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Setup database
def init_db():
    conn = sqlite3.connect('premium_bot.db')
    c = conn.cursor()
    
    # Tabel untuk user premium
    c.execute('''CREATE TABLE IF NOT EXISTS premium_users
                 (user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  expiry_date DATETIME,
                  package TEXT,
                  payment_status TEXT DEFAULT 'pending')''')
    
    # Tabel untuk transaksi
    c.execute('''CREATE TABLE IF NOT EXISTS transactions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  package TEXT,
                  amount INTEGER,
                  payment_date DATETIME,
                  status TEXT)''')
    
    # Tabel untuk QRIS
    c.execute('''CREATE TABLE IF NOT EXISTS qris_codes
                 (package TEXT PRIMARY KEY,
                  file_id TEXT)''')
    
    conn.commit()
    conn.close()

init_db()

# Fungsi database helper
def db_execute(query, params=()):
    conn = sqlite3.connect('premium_bot.db')
    c = conn.cursor()
    c.execute(query, params)
    conn.commit()
    conn.close()

def db_fetchone(query, params=()):
    conn = sqlite3.connect('premium_bot.db')
    c = conn.cursor()
    c.execute(query, params)
    result = c.fetchone()
    conn.close()
    return result

def db_fetchall(query, params=()):
    conn = sqlite3.connect('premium_bot.db')
    c = conn.cursor()
    c.execute(query, params)
    result = c.fetchall()
    conn.close()
    return result

# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Selamat datang di Premium Channel Bot!\n\n"
        "Perintah yang tersedia:\n"
        "/buy - Beli akses premium\n"
        "/cek - Cek sisa waktu premium\n"
        "/channel - Masuk ke channel premium\n\n"
        "Hubungi admin jika ada pertanyaan."
    )

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("7 Hari - Rp 20.000", callback_data="buy_7_hari"),
            InlineKeyboardButton("30 Hari - Rp 50.000", callback_data="buy_30_hari"),
        ],
        [
            InlineKeyboardButton("1 Tahun - Rp 80.000", callback_data="buy_1_tahun"),
            InlineKeyboardButton("Lifetime - Rp 110.000", callback_data="buy_lifetime"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Pilih paket premium yang diinginkan:",
        reply_markup=reply_markup
    )

async def cek(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    result = db_fetchone(
        "SELECT expiry_date, package FROM premium_users WHERE user_id = ? AND payment_status = 'paid'",
        (user_id,)
    )
    
    if result:
        expiry_date = datetime.strptime(result[0], '%Y-%m-%d %H:%M:%S')
        package = result[1]
        now = datetime.now()
        
        if expiry_date > now:
            remaining = expiry_date - now
            days = remaining.days
            hours = remaining.seconds // 3600
            minutes = (remaining.seconds % 3600) // 60
            
            await update.message.reply_text(
                f"Paket: {package}\n"
                f"Sisa waktu: {days} hari {hours} jam {minutes} menit\n"
                f"Berlaku hingga: {expiry_date.strftime('%d-%m-%Y %H:%M:%S')}"
            )
        else:
            await update.message.reply_text(
                "Premium Anda sudah habis. Silakan beli lagi dengan /buy"
            )
            # Hapus user dari database jika sudah expired
            db_execute("DELETE FROM premium_users WHERE user_id = ?", (user_id,))
    else:
        await update.message.reply_text(
            "Anda belum memiliki premium. Beli dengan /buy"
        )

async def channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    result = db_fetchone(
        "SELECT expiry_date FROM premium_users WHERE user_id = ? AND payment_status = 'paid'",
        (user_id,)
    )
    
    if result:
        expiry_date = datetime.strptime(result[0], '%Y-%m-%d %H:%M:%S')
        if expiry_date > datetime.now():
            keyboard = [[InlineKeyboardButton("Masuk Channel", url=f"https://t.me/{CHANNEL_USERNAME[1:]}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            message = await update.message.reply_text(
                "Klik tombol di bawah untuk masuk ke channel:",
                reply_markup=reply_markup
            )
            
            # Hapus pesan setelah 10 menit
            await asyncio.sleep(600)
            try:
                await message.delete()
            except:
                pass
        else:
            await update.message.reply_text(
                "Premium Anda sudah habis. Silakan beli lagi dengan /buy"
            )
            db_execute("DELETE FROM premium_users WHERE user_id = ?", (user_id,))
    else:
        await update.message.reply_text(
            "Anda belum memiliki akses premium. Beli dengan /buy"
        )

async def dev(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != OWNER_ID:
        await update.message.reply_text("Akses ditolak!")
        return
    
    if len(context.args) != 1:
        await update.message.reply_text(
            "Gunakan: /dev <menit>\n"
            "Contoh: /dev 5 untuk 5 menit premium"
        )
        return
    
    try:
        minutes = int(context.args[0])
        user_id = OWNER_ID  # Untuk testing, owner sendiri
        
        expiry_date = datetime.now() + timedelta(minutes=minutes)
        db_execute(
            """INSERT OR REPLACE INTO premium_users 
               (user_id, username, expiry_date, package, payment_status) 
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, "owner", expiry_date.strftime('%Y-%m-%d %H:%M:%S'), f"test_{minutes}min", "paid")
        )
        
        await update.message.reply_text(
            f"Premium test {minutes} menit berhasil diaktifkan!\n"
            f"Berlaku hingga: {expiry_date.strftime('%d-%m-%Y %H:%M:%S')}"
        )
        
    except ValueError:
        await update.message.reply_text("Masukkan angka yang valid!")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data.startswith("buy_"):
        package = data[4:]  # remove "buy_" prefix
        price_info = PRICES.get(package)
        
        if price_info:
            # Cek apakah ada QRIS untuk paket ini
            qris_data = db_fetchone("SELECT file_id FROM qris_codes WHERE package = ?", (package,))
            
            if qris_data:
                # Kirim QRIS yang sudah ada
                await query.message.reply_photo(
                    photo=qris_data[0],
                    caption=f"Paket: {package.replace('_', ' ').title()}\n"
                           f"Harga: Rp {price_info['price']:,}\n\n"
                           f"Silakan scan QRIS di atas untuk pembayaran.\n"
                           f"Setelah membayar, kirim bukti pembayaran ke admin."
                )
            else:
                # Jika belum ada QRIS, minta admin untuk mengupload
                await query.message.reply_text(
                    f"Paket: {package.replace('_', ' ').title()}\n"
                    f"Harga: Rp {price_info['price']:,}\n\n"
                    f"Silakan hubungi admin untuk pembayaran."
                )
            
            # Simpan data transaksi
            db_execute(
                """INSERT INTO transactions 
                   (user_id, package, amount, payment_date, status) 
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, package, price_info['price'], datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'pending')
            )
            
            # Log ke channel
            try:
                await context.bot.send_message(
                    chat_id=LOG_CHANNEL_ID,
                    text=f"🚨 TRANSAKSI BARU\n"
                         f"User: @{query.from_user.username or 'N/A'} ({user_id})\n"
                         f"Paket: {package}\n"
                         f"Harga: Rp {price_info['price']:,}\n"
                         f"Status: Menunggu pembayaran"
                )
            except:
                pass
    
    elif data.startswith("approve_"):
        if query.from_user.id != OWNER_ID:
            await query.answer("Hanya owner yang bisa approve!", show_alert=True)
            return
        
        transaction_id = data[8:]
        trans_data = db_fetchone(
            "SELECT user_id, package FROM transactions WHERE id = ?",
            (transaction_id,)
        )
        
        if trans_data:
            user_id, package = trans_data
            price_info = PRICES.get(package)
            
            if price_info:
                expiry_date = datetime.now() + timedelta(days=price_info['days'])
                
                # Update status user
                db_execute(
                    """INSERT OR REPLACE INTO premium_users 
                       (user_id, username, expiry_date, package, payment_status) 
                       VALUES (?, ?, ?, ?, ?)""",
                    (user_id, "user", expiry_date.strftime('%Y-%m-%d %H:%M:%S'), package, "paid")
                )
                
                # Update transaksi
                db_execute(
                    "UPDATE transactions SET status = 'approved' WHERE id = ?",
                    (transaction_id,)
                )
                
                # Kirim notifikasi ke user
                keyboard = [[InlineKeyboardButton("Masuk Channel", url=f"https://t.me/{CHANNEL_USERNAME[1:]}")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"✅ Pembayaran Anda untuk paket {package} telah diterima!\n"
                         f"Akses premium berlaku hingga: {expiry_date.strftime('%d-%m-%Y')}\n"
                         f"Klik tombol di bawah untuk masuk ke channel:",
                    reply_markup=reply_markup
                )
                
                await query.answer("Pembayaran disetujui!", show_alert=True)
                
                # Log ke channel
                try:
                    await context.bot.send_message(
                        chat_id=LOG_CHANNEL_ID,
                        text=f"✅ PEMBAYARAN DISETUJUI\n"
                             f"User ID: {user_id}\n"
                             f"Paket: {package}\n"
                             f"Expiry: {expiry_date.strftime('%d-%m-%Y')}"
                    )
                except:
                    pass

async def handle_payment_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        photo = update.message.photo[-1].file_id
        user_id = update.message.from_user.id
        
        # Cek transaksi pending user
        trans_data = db_fetchone(
            "SELECT id, package FROM transactions WHERE user_id = ? AND status = 'pending' ORDER BY id DESC LIMIT 1",
            (user_id,)
        )
        
        if trans_data:
            trans_id, package = trans_data
            
            # Kirim bukti ke channel log dengan tombol approve
            keyboard = [[InlineKeyboardButton("✅ Approve", callback_data=f"approve_{trans_id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            try:
                await context.bot.send_photo(
                    chat_id=LOG_CHANNEL_ID,
                    photo=photo,
                    caption=f"📤 BUKTI PEMBAYARAN\n"
                           f"User: @{update.message.from_user.username or 'N/A'} ({user_id})\n"
                           f"Paket: {package}",
                    reply_markup=reply_markup
                )
                
                await update.message.reply_text(
                    "✅ Bukti pembayaran telah diterima. Admin akan memverifikasi pembayaran Anda.\n"
                    "Anda akan mendapatkan notifikasi ketika pembayaran disetujui."
                )
            except:
                await update.message.reply_text(
                    "❌ Gagal mengirim bukti pembayaran. Silakan hubungi admin."
                )

async def auto_remove_expired_users(context: ContextTypes.DEFAULT_TYPE):
    """Fungsi untuk mengecek dan menghapus user yang sudah expired"""
    try:
        expired_users = db_fetchall(
            "SELECT user_id FROM premium_users WHERE expiry_date < ? AND payment_status = 'paid'",
            (datetime.now().strftime('%Y-%m-%d %H:%M:%S'),)
        )
        
        for user in expired_users:
            user_id = user[0]
            
            # Hapus dari database
            db_execute("DELETE FROM premium_users WHERE user_id = ?", (user_id,))
            
            # Kirim notifikasi ke user
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="⏰ Masa premium Anda telah habis. Silakan beli lagi dengan /buy untuk melanjutkan akses."
                )
            except:
                pass
            
            # Log ke channel
            try:
                await context.bot.send_message(
                    chat_id=LOG_CHANNEL_ID,
                    text=f"⏰ USER EXPIRED\n"
                         f"User ID: {user_id}\n"
                         f"Waktu: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}"
                )
            except:
                pass
    except Exception as e:
        logger.error(f"Error in auto_remove_expired_users: {e}")

async def set_qris(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != OWNER_ID:
        await update.message.reply_text("Akses ditolak!")
        return
    
    if not (update.message.reply_to_message and update.message.reply_to_message.photo):
        await update.message.reply_text(
            "Balas pesan dengan QRIS dan ketik:\n"
            "/setqris <nama_paket>\n\n"
            "Contoh: /setqris 7_hari\n"
            "Paket yang tersedia: 7_hari, 30_hari, 1_tahun, lifetime"
        )
        return
    
    if len(context.args) != 1:
        await update.message.reply_text("Format salah! Gunakan: /setqris <nama_paket>")
        return
    
    package = context.args[0]
    if package not in PRICES:
        await update.message.reply_text(
            f"Paket tidak valid! Paket yang tersedia:\n"
            f"- 7_hari\n- 30_hari\n- 1_tahun\n- lifetime"
        )
        return
    
    photo = update.message.reply_to_message.photo[-1].file_id
    
    db_execute(
        """INSERT OR REPLACE INTO qris_codes (package, file_id) 
           VALUES (?, ?)""",
        (package, photo)
    )
    
    await update.message.reply_text(f"✅ QRIS untuk paket {package} berhasil disimpan!")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != OWNER_ID:
        return
    
    # Hitung total user premium aktif
    active_users = db_fetchone("SELECT COUNT(*) FROM premium_users WHERE payment_status = 'paid'")
    
    # Hitung total pendapatan
    total_revenue = db_fetchone("SELECT SUM(amount) FROM transactions WHERE status = 'approved'")
    
    # Hitung total transaksi
    total_transactions = db_fetchone("SELECT COUNT(*) FROM transactions")
    
    await update.message.reply_text(
        "📊 STATISTIK BOT\n\n"
        f"Total User Premium Aktif: {active_users[0] or 0}\n"
        f"Total Transaksi: {total_transactions[0] or 0}\n"
        f"Total Pendapatan: Rp {total_revenue[0] or 0:,}\n\n"
        f"Paket tersedia:\n"
        f"- 7 Hari: Rp {PRICES['7_hari']['price']:,}\n"
        f"- 30 Hari: Rp {PRICES['30_hari']['price']:,}\n"
        f"- 1 Tahun: Rp {PRICES['1_tahun']['price']:,}\n"
        f"- Lifetime: Rp {PRICES['lifetime']['price']:,}"
    )

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != OWNER_ID:
        return
    
    if not context.args:
        await update.message.reply_text(
            "Gunakan: /broadcast <pesan>\n"
            "Contoh: /broadcast Ada update terbaru!"
        )
        return
    
    message = " ".join(context.args)
    users = db_fetchall("SELECT DISTINCT user_id FROM premium_users")
    
    count = 0
    for user in users:
        try:
            await context.bot.send_message(chat_id=user[0], text=message)
            count += 1
        except:
            continue
    
    await update.message.reply_text(f"✅ Broadcast berhasil dikirim ke {count} user")

def main():
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("buy", buy))
    application.add_handler(CommandHandler("cek", cek))
    application.add_handler(CommandHandler("channel", channel))
    application.add_handler(CommandHandler("dev", dev))
    application.add_handler(CommandHandler("setqris", set_qris))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("broadcast", broadcast))
    
    # Callback query handler
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Message handler untuk bukti pembayaran
    application.add_handler(MessageHandler(filters.PHOTO, handle_payment_proof))
    
    # Job queue untuk cek expired users (setiap 1 jam)
    job_queue = application.job_queue
    job_queue.run_repeating(auto_remove_expired_users, interval=3600, first=10)

    # Start the Bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
