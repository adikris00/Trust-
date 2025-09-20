import os
import sqlite3
import requests
import asyncio
import csv
import io
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ambil token dari environment variable
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("⚠️  Silakan set TELEGRAM_BOT_TOKEN di environment variables.")

# --- Database Setup ---
DB_FILE = "domain_checker.db"

def init_database():
    """Initialize SQLite database with required tables"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # User history table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS domain_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            domain TEXT NOT NULL,
            status TEXT NOT NULL,
            blocked BOOLEAN NOT NULL,
            check_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # User bookmarks table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS domain_bookmarks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            domain TEXT NOT NULL,
            added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, domain)
        )
    ''')
    
    # Domain monitoring subscriptions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS domain_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            domain TEXT NOT NULL,
            current_status TEXT,
            current_blocked BOOLEAN,
            last_check TIMESTAMP,
            created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, domain)
        )
    ''')
    
    # User statistics
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_stats (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            total_checks INTEGER DEFAULT 0,
            first_use TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_use TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

# --- Database Helper Functions ---

def save_domain_check(user_id: int, username: str, domain: str, status: str, blocked: bool):
    """Save domain check to history"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO domain_history (user_id, username, domain, status, blocked)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, username, domain, status, blocked))
    
    # Update user stats
    cursor.execute('''
        INSERT OR REPLACE INTO user_stats (user_id, username, total_checks, first_use, last_use)
        VALUES (?, ?, 
                COALESCE((SELECT total_checks FROM user_stats WHERE user_id = ?), 0) + 1,
                COALESCE((SELECT first_use FROM user_stats WHERE user_id = ?), CURRENT_TIMESTAMP),
                CURRENT_TIMESTAMP)
    ''', (user_id, username, user_id, user_id))
    
    conn.commit()
    conn.close()

def get_user_history(user_id: int, limit: int = 20):
    """Get user's domain check history"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT domain, status, blocked, check_date
        FROM domain_history
        WHERE user_id = ?
        ORDER BY check_date DESC
        LIMIT ?
    ''', (user_id, limit))
    
    results = cursor.fetchall()
    conn.close()
    return results

def add_bookmark(user_id: int, domain: str):
    """Add domain to user's bookmarks"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO domain_bookmarks (user_id, domain)
            VALUES (?, ?)
        ''', (user_id, domain))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False

def remove_bookmark(user_id: int, domain: str):
    """Remove domain from user's bookmarks"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        DELETE FROM domain_bookmarks
        WHERE user_id = ? AND domain = ?
    ''', (user_id, domain))
    
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0

def get_user_bookmarks(user_id: int):
    """Get user's bookmarked domains"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT domain, added_date
        FROM domain_bookmarks
        WHERE user_id = ?
        ORDER BY added_date DESC
    ''', (user_id,))
    
    results = cursor.fetchall()
    conn.close()
    return results

def add_subscription(user_id: int, domain: str, current_status: str, current_blocked: bool):
    """Add domain monitoring subscription"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT OR REPLACE INTO domain_subscriptions 
            (user_id, domain, current_status, current_blocked, last_check)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (user_id, domain, current_status, current_blocked))
        conn.commit()
        conn.close()
        return True
    except Exception:
        conn.close()
        return False

def get_user_subscriptions(user_id: int):
    """Get user's domain subscriptions"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT domain, current_status, current_blocked, last_check, created_date
        FROM domain_subscriptions
        WHERE user_id = ?
        ORDER BY created_date DESC
    ''', (user_id,))
    
    results = cursor.fetchall()
    conn.close()
    return results

def get_all_subscriptions():
    """Get all domain subscriptions for monitoring"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT user_id, domain, current_status, current_blocked
        FROM domain_subscriptions
    ''')
    
    results = cursor.fetchall()
    conn.close()
    return results

def update_subscription_status(user_id: int, domain: str, new_status: str, new_blocked: bool):
    """Update subscription status"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE domain_subscriptions
        SET current_status = ?, current_blocked = ?, last_check = CURRENT_TIMESTAMP
        WHERE user_id = ? AND domain = ?
    ''', (new_status, new_blocked, user_id, domain))
    
    conn.commit()
    conn.close()

def get_user_stats(user_id: int):
    """Get user statistics"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT total_checks, first_use, last_use
        FROM user_stats
        WHERE user_id = ?
    ''', (user_id,))
    
    result = cursor.fetchone()
    conn.close()
    return result

def get_top_domains(limit: int = 10):
    """Get most checked domains"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT domain, COUNT(*) as check_count
        FROM domain_history
        WHERE check_date >= datetime('now', '-30 days')
        GROUP BY domain
        ORDER BY check_count DESC
        LIMIT ?
    ''', (limit,))
    
    results = cursor.fetchall()
    conn.close()
    return results

# --- Utility Functions ---

def format_single_result(domain: str, result: dict) -> str:
    if not result:
        return f"Domain: {domain}\nStatus: Tidak dapat memeriksa\n"

    blocked = result.get("blocked", False)
    status_text = "🔴 Diblokir" if blocked else "🟢 Tidak Diblokir"
    return f"🌐 Domain: {domain}\n📊 Status: {status_text}\n"

def format_bulk_results(domains: list, results: dict) -> str:
    output_lines = ["📋 Hasil Pengecekan Domain\n"]
    
    success_count = 0
    blocked_count = 0
    error_domains = []

    for domain in domains:
        result = results.get(domain)
        if not result:
            error_domains.append(domain)
            output_lines.append(format_single_result(domain, {}))
        else:
            output_lines.append(format_single_result(domain, result))
            success_count += 1
            if result.get("blocked", False):
                blocked_count += 1

    # Summary
    summary = f"\n📊 Ringkasan:\n"
    summary += f"✅ Berhasil diperiksa: {success_count}\n"
    summary += f"🔴 Diblokir: {blocked_count}\n"
    if error_domains:
        summary += f"❌ Gagal diperiksa: {len(error_domains)} ({', '.join(error_domains)})\n"
    
    output_lines.append(summary)
    return "\n".join(output_lines)

def create_domain_keyboard(domain: str, is_bookmarked: bool = False, is_subscribed: bool = False):
    """Create inline keyboard for domain actions"""
    keyboard = [
        [
            InlineKeyboardButton("🔄 Cek Ulang", callback_data=f"recheck_{domain}"),
            InlineKeyboardButton("📊 Riwayat", callback_data=f"history_{domain}")
        ]
    ]
    
    bookmark_text = "❌ Hapus Bookmark" if is_bookmarked else "⭐ Bookmark"
    subscribe_text = "🔕 Berhenti Monitor" if is_subscribed else "🔔 Monitor"
    
    keyboard.append([
        InlineKeyboardButton(bookmark_text, callback_data=f"bookmark_{domain}"),
        InlineKeyboardButton(subscribe_text, callback_data=f"subscribe_{domain}")
    ])
    
    return InlineKeyboardMarkup(keyboard)

async def check_domain_api(domain: str) -> dict:
    """Check domain status via API"""
    try:
        api_url = f"https://check.skiddle.id/?domains={domain}"
        response = requests.get(api_url, timeout=15)
        response.raise_for_status()
        results = response.json()
        return results.get(domain, {})
    except Exception as e:
        logger.error(f"Error checking domain {domain}: {e}")
        return {}

# --- Bot Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_text = (
        f"🤖 Halo {user.first_name}! Selamat datang di Domain Trust+ Checker Bot!\n\n"
        "🔍 Saya dapat memeriksa status domain dan memberikan monitoring otomatis.\n\n"
        "📋 Perintah yang tersedia:\n"
        "• Kirim domain untuk pengecekan\n"
        "• /history - Riwayat pengecekan\n"
        "• /bookmarks - Domain favorit\n"
        "• /subscriptions - Domain yang dimonitor\n"
        "• /stats - Statistik penggunaan\n"
        "• /export - Export data ke CSV\n"
        "• /help - Bantuan lengkap\n\n"
        "💡 Tips: Gunakan tombol interaktif untuk aksi cepat!"
    )
    await update.message.reply_text(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📚 Bantuan Domain Trust+ Checker\n\n"
        "🔍 Pengecekan Domain:\n"
        "• Kirim satu domain: `google.com`\n"
        "• Kirim banyak domain: `google.com, yahoo.com`\n\n"
        "⭐ Fitur Lanjutan:\n"
        "• /history - Lihat riwayat pengecekan\n"
        "• /bookmarks - Kelola domain favorit\n"
        "• /subscriptions - Monitor domain otomatis\n"
        "• /stats - Statistik penggunaan pribadi\n"
        "• /report - Laporan domain populer\n"
        "• /export - Export data ke file CSV\n\n"
        "🔔 Monitoring:\n"
        "• Notifikasi otomatis jika status berubah\n"
        "• Pengecekan harian untuk domain berlangganan\n\n"
        "⚡ Tombol Interaktif:\n"
        "• Cek ulang domain dengan satu klik\n"
        "• Bookmark domain favorit\n"
        "• Subscribe untuk monitoring\n\n"
        "📊 Batasan:\n"
        "• Maksimal 10 domain per pengecekan bulk\n"
        "• Maksimal 20 bookmark per user\n"
        "• Maksimal 10 subscription per user"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def check_domain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_input = update.message.text.strip()

    if not user_input:
        await update.message.reply_text("Silakan kirimkan nama domain yang ingin dicek.")
        return

    # Detect bulk or single
    if ',' in user_input:
        domains_raw = [d.strip() for d in user_input.split(',')]
        if len(domains_raw) > 10:
             await update.message.reply_text("⚠️ Maksimal 10 domain sekaligus. Silakan kurangi jumlah domain.")
             return
        domains = list(filter(None, domains_raw))
        if not domains:
            await update.message.reply_text("Format tidak valid. Silakan kirim domain yang dipisahkan dengan koma.")
            return
        is_bulk = True
    else:
        domains = [user_input]
        is_bulk = False

    # Send "processing" message
    processing_msg = await update.message.reply_text("🔄 Sedang memeriksa domain...")

    try:
        # Call API
        domains_param = ",".join(domains)
        api_url = f"https://check.skiddle.id/?domains={domains_param}"
        response = requests.get(api_url, timeout=15)
        response.raise_for_status()
        results_data = response.json()

        # Save to database and format response
        if is_bulk:
            for domain in domains:
                result = results_data.get(domain, {})
                if result:
                    status = "Diblokir" if result.get("blocked", False) else "Tidak Diblokir"
                    save_domain_check(user.id, user.username or user.first_name, domain, status, result.get("blocked", False))
            
            formatted_response = format_bulk_results(domains, results_data)
            await processing_msg.edit_text(formatted_response)
        else:
            domain = domains[0]
            result = results_data.get(domain, {})
            
            if not result:
                await processing_msg.edit_text(f"🌐 Domain: {domain}\n❌ Status: Tidak dapat memeriksa")
                return
            
            blocked = result.get("blocked", False)
            status = "Diblokir" if blocked else "Tidak Diblokir"
            status_emoji = "🔴" if blocked else "🟢"
            
            # Save to database
            save_domain_check(user.id, user.username or user.first_name, domain, status, blocked)
            
            # Check if bookmarked/subscribed
            bookmarks = get_user_bookmarks(user.id)
            subscriptions = get_user_subscriptions(user.id)
            
            is_bookmarked = any(bookmark[0] == domain for bookmark in bookmarks)
            is_subscribed = any(sub[0] == domain for sub in subscriptions)
            
            formatted_response = f"🌐 Domain: {domain}\n📊 Status: {status_emoji} {status}"
            keyboard = create_domain_keyboard(domain, is_bookmarked, is_subscribed)
            
            await processing_msg.edit_text(formatted_response, reply_markup=keyboard)

    except requests.exceptions.Timeout:
        await processing_msg.edit_text("⏱️ Permintaan ke API terlalu lama. Silakan coba lagi.")
    except requests.exceptions.RequestException as e:
        await processing_msg.edit_text(f"❌ Gagal menghubungi API pengecekan domain.\nDetail: {str(e)}")
    except Exception as e:
        await processing_msg.edit_text(f"⚠️ Terjadi kesalahan saat memproses permintaan.\nDetail: {str(e)}")

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    history = get_user_history(user.id, 20)
    
    if not history:
        await update.message.reply_text("📭 Anda belum memiliki riwayat pengecekan domain.")
        return
    
    history_text = "📋 Riwayat Pengecekan Domain (20 terakhir):\n\n"
    
    for domain, status, blocked, check_date in history:
        emoji = "🔴" if blocked else "🟢"
        date_obj = datetime.fromisoformat(check_date.replace('Z', '+00:00'))
        formatted_date = date_obj.strftime("%d/%m/%Y %H:%M")
        history_text += f"{emoji} {domain} - {status}\n   📅 {formatted_date}\n\n"
    
    if len(history_text) > 4096:  # Telegram message limit
        history_text = history_text[:4000] + "\n\n... (gunakan /export untuk data lengkap)"
    
    await update.message.reply_text(history_text)

async def bookmarks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    bookmarks = get_user_bookmarks(user.id)
    
    if not bookmarks:
        await update.message.reply_text("⭐ Anda belum memiliki bookmark domain.\n\nGunakan tombol 'Bookmark' setelah mengecek domain untuk menambahkan ke favorit.")
        return
    
    bookmarks_text = "⭐ Domain Bookmark Anda:\n\n"
    keyboard = []
    
    for i, (domain, added_date) in enumerate(bookmarks, 1):
        date_obj = datetime.fromisoformat(added_date.replace('Z', '+00:00'))
        formatted_date = date_obj.strftime("%d/%m/%Y")
        bookmarks_text += f"{i}. {domain}\n   📅 Ditambahkan: {formatted_date}\n\n"
        
        # Add inline button for quick check
        keyboard.append([
            InlineKeyboardButton(f"🔍 Cek {domain}", callback_data=f"recheck_{domain}"),
            InlineKeyboardButton("❌ Hapus", callback_data=f"remove_bookmark_{domain}")
        ])
    
    reply_markup = InlineKeyboardMarkup(keyboard[:10])  # Limit to 10 buttons
    await update.message.reply_text(bookmarks_text, reply_markup=reply_markup)

async def subscriptions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    subscriptions = get_user_subscriptions(user.id)
    
    if not subscriptions:
        await update.message.reply_text("🔔 Anda belum memiliki domain yang dimonitor.\n\nGunakan tombol 'Monitor' setelah mengecek domain untuk mendapatkan notifikasi otomatis jika status berubah.")
        return
    
    subs_text = "🔔 Domain yang Dimonitor:\n\n"
    keyboard = []
    
    for domain, current_status, current_blocked, last_check, created_date in subscriptions:
        emoji = "🔴" if current_blocked else "🟢"
        last_check_obj = datetime.fromisoformat(last_check.replace('Z', '+00:00'))
        formatted_date = last_check_obj.strftime("%d/%m/%Y %H:%M")
        
        subs_text += f"{emoji} {domain}\n"
        subs_text += f"   📊 Status: {current_status}\n"
        subs_text += f"   🕐 Terakhir dicek: {formatted_date}\n\n"
        
        keyboard.append([
            InlineKeyboardButton(f"🔍 Cek {domain}", callback_data=f"recheck_{domain}"),
            InlineKeyboardButton("🔕 Berhenti", callback_data=f"unsubscribe_{domain}")
        ])
    
    reply_markup = InlineKeyboardMarkup(keyboard[:10])
    await update.message.reply_text(subs_text, reply_markup=reply_markup)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    stats = get_user_stats(user.id)
    
    if not stats:
        await update.message.reply_text("📊 Anda belum memiliki statistik penggunaan.")
        return
    
    total_checks, first_use, last_use = stats
    first_use_obj = datetime.fromisoformat(first_use.replace('Z', '+00:00'))
    last_use_obj = datetime.fromisoformat(last_use.replace('Z', '+00:00'))
    
    # Get additional stats
    bookmarks = get_user_bookmarks(user.id)
    subscriptions = get_user_subscriptions(user.id)
    recent_history = get_user_history(user.id, 7)
    
    stats_text = (
        f"📊 Statistik Penggunaan - {user.first_name}\n\n"
        f"🔍 Total pengecekan: {total_checks}\n"
        f"⭐ Bookmark aktif: {len(bookmarks)}\n"
        f"🔔 Domain dimonitor: {len(subscriptions)}\n"
        f"📅 Pengecekan 7 hari terakhir: {len(recent_history)}\n\n"
        f"🚀 Pertama menggunakan: {first_use_obj.strftime('%d/%m/%Y')}\n"
        f"🕐 Terakhir menggunakan: {last_use_obj.strftime('%d/%m/%Y %H:%M')}\n\n"
        f"💡 Tips: Gunakan /export untuk mendapatkan data lengkap dalam format CSV!"
    )
    
    await update.message.reply_text(stats_text)

async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    history = get_user_history(user.id, 1000)  # Get up to 1000 records
    
    if not history:
        await update.message.reply_text("📭 Tidak ada data untuk diekspor.")
        return
    
    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Domain', 'Status', 'Diblokir', 'Tanggal Pengecekan'])
    
    for domain, status, blocked, check_date in history:
        writer.writerow([domain, status, 'Ya' if blocked else 'Tidak', check_date])
    
    output.seek(0)
    csv_content = output.getvalue()
    output.close()
    
    # Send as file
    csv_file = io.BytesIO(csv_content.encode('utf-8'))
    csv_file.name = f"domain_history_{user.id}_{datetime.now().strftime('%Y%m%d')}.csv"
    
    await update.message.reply_document(
        document=csv_file,
        filename=csv_file.name,
        caption=f"📊 Export riwayat domain checker\n👤 User: {user.first_name}\n📅 Total records: {len(history)}"
    )

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    top_domains = get_top_domains(15)
    
    if not top_domains:
        await update.message.reply_text("📊 Belum ada data untuk laporan bulanan.")
        return
    
    report_text = "📈 Laporan Domain Populer (30 hari terakhir):\n\n"
    
    for i, (domain, count) in enumerate(top_domains, 1):
        report_text += f"{i}. {domain} - {count} kali dicek\n"
    
    report_text += f"\n📊 Total domain unik yang dicek: {len(top_domains)}"
    
    await update.message.reply_text(report_text)

# --- Callback Query Handler ---

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    action, domain = query.data.split('_', 1)
    
    if action == "recheck":
        # Recheck domain
        await query.edit_message_text("🔄 Sedang mengecek ulang domain...")
        
        result = await check_domain_api(domain)
        if not result:
            await query.edit_message_text(f"🌐 Domain: {domain}\n❌ Status: Tidak dapat memeriksa")
            return
        
        blocked = result.get("blocked", False)
        status = "Diblokir" if blocked else "Tidak Diblokir"
        status_emoji = "🔴" if blocked else "🟢"
        
        # Save to database
        save_domain_check(user.id, user.username or user.first_name, domain, status, blocked)
        
        # Check if bookmarked/subscribed
        bookmarks = get_user_bookmarks(user.id)
        subscriptions = get_user_subscriptions(user.id)
        
        is_bookmarked = any(bookmark[0] == domain for bookmark in bookmarks)
        is_subscribed = any(sub[0] == domain for sub in subscriptions)
        
        formatted_response = f"🌐 Domain: {domain}\n📊 Status: {status_emoji} {status}\n🕐 Diperbarui: {datetime.now().strftime('%H:%M')}"
        keyboard = create_domain_keyboard(domain, is_bookmarked, is_subscribed)
        
        await query.edit_message_text(formatted_response, reply_markup=keyboard)
    
    elif action == "bookmark":
        # Toggle bookmark
        bookmarks = get_user_bookmarks(user.id)
        is_bookmarked = any(bookmark[0] == domain for bookmark in bookmarks)
        
        if is_bookmarked:
            if remove_bookmark(user.id, domain):
                await query.edit_message_reply_markup(reply_markup=create_domain_keyboard(domain, False, False))
                await context.bot.send_message(user.id, f"❌ {domain} dihapus dari bookmark")
            else:
                await context.bot.send_message(user.id, "⚠️ Gagal menghapus bookmark")
        else:
            if len(bookmarks) >= 20:
                await context.bot.send_message(user.id, "⚠️ Maksimal 20 bookmark per user. Hapus beberapa bookmark terlebih dahulu.")
                return
            
            if add_bookmark(user.id, domain):
                await query.edit_message_reply_markup(reply_markup=create_domain_keyboard(domain, True, False))
                await context.bot.send_message(user.id, f"⭐ {domain} ditambahkan ke bookmark")
            else:
                await context.bot.send_message(user.id, "⚠️ Domain sudah ada di bookmark")
    
    elif action == "subscribe":
        # Toggle subscription
        subscriptions = get_user_subscriptions(user.id)
        is_subscribed = any(sub[0] == domain for sub in subscriptions)
        
        if is_subscribed:
            # Remove subscription
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute('DELETE FROM domain_subscriptions WHERE user_id = ? AND domain = ?', (user.id, domain))
            conn.commit()
            conn.close()
            
            await context.bot.send_message(user.id, f"🔕 Monitoring untuk {domain} dihentikan")
        else:
            if len(subscriptions) >= 10:
                await context.bot.send_message(user.id, "⚠️ Maksimal 10 domain monitoring per user.")
                return
            
            # Get current status
            result = await check_domain_api(domain)
            if result:
                blocked = result.get("blocked", False)
                status = "Diblokir" if blocked else "Tidak Diblokir"
                
                if add_subscription(user.id, domain, status, blocked):
                    await context.bot.send_message(user.id, f"🔔 {domain} ditambahkan ke monitoring harian")
                else:
                    await context.bot.send_message(user.id, "⚠️ Gagal menambahkan subscription")
    
    elif action == "unsubscribe":
        # Remove subscription
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM domain_subscriptions WHERE user_id = ? AND domain = ?', (user.id, domain))
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        
        if affected > 0:
            await context.bot.send_message(user.id, f"🔕 Monitoring untuk {domain} dihentikan")
        else:
            await context.bot.send_message(user.id, "⚠️ Domain tidak ditemukan dalam subscription")
    
    elif action == "remove" and query.data.startswith("remove_bookmark_"):
        domain = query.data.replace("remove_bookmark_", "")
        if remove_bookmark(user.id, domain):
            await context.bot.send_message(user.id, f"❌ {domain} dihapus dari bookmark")
            # Refresh bookmarks list
            await bookmarks_command(update, context)
        else:
            await context.bot.send_message(user.id, "⚠️ Gagal menghapus bookmark")

# --- Background Monitoring Task ---

async def check_subscriptions():
    """Background task to check all domain subscriptions"""
    logger.info("Starting daily subscription check...")
    subscriptions = get_all_subscriptions()
    
    for user_id, domain, old_status, old_blocked in subscriptions:
        try:
            # Check domain status
            result = await check_domain_api(domain)
            
            if not result:
                continue
            
            new_blocked = result.get("blocked", False)
            new_status = "Diblokir" if new_blocked else "Tidak Diblokir"
            
            # Check if status changed
            if new_blocked != old_blocked:
                # Send notification
                status_emoji = "🔴" if new_blocked else "🟢"
                change_emoji = "🔴➡️🟢" if old_blocked and not new_blocked else "🟢➡️🔴"
                
                notification_text = (
                    f"🔔 Status Domain Berubah!\n\n"
                    f"🌐 Domain: {domain}\n"
                    f"📊 Status Baru: {status_emoji} {new_status}\n"
                    f"🔄 Perubahan: {change_emoji}\n"
                    f"🕐 Waktu: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
                    f"💡 Gunakan /subscriptions untuk mengelola monitoring"
                )
                
                try:
                    # Get bot instance from global context
                    bot = application.bot
                    await bot.send_message(user_id, notification_text)
                    logger.info(f"Notification sent to user {user_id} for domain {domain}")
                except Exception as e:
                    logger.error(f"Failed to send notification to user {user_id}: {e}")
            
            # Update subscription status
            update_subscription_status(user_id, domain, new_status, new_blocked)
            
            # Small delay to avoid rate limiting
            await asyncio.sleep(1)
            
        except Exception as e:
            logger.error(f"Error checking subscription for user {user_id}, domain {domain}: {e}")
    
    logger.info(f"Daily subscription check completed. Checked {len(subscriptions)} subscriptions.")

# --- Setup Application ---

def setup_scheduler(app):
    """Setup background scheduler for monitoring"""
    scheduler = AsyncIOScheduler()
    
    # Schedule daily check at 9 AM
    scheduler.add_job(
        check_subscriptions,
        CronTrigger(hour=9, minute=0),  # 9:00 AM daily
        id='daily_domain_check',
        replace_existing=True
    )
    
    # You can also add hourly checks if needed
    # scheduler.add_job(
    #     check_subscriptions,
    #     CronTrigger(minute=0),  # Every hour
    #     id='hourly_domain_check',
    #     replace_existing=True
    # )
    
    scheduler.start()
    logger.info("Background scheduler started")
    return scheduler

# --- Main Application ---

if __name__ == "__main__":
    print("🚀 Enhanced Domain Checker Bot sedang berjalan...")
    
    # Initialize database
    init_database()
    logger.info("Database initialized")
    
    # Build application
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Setup scheduler for background monitoring
    scheduler = setup_scheduler(application)
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("bookmarks", bookmarks_command))
    application.add_handler(CommandHandler("subscriptions", subscriptions_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("export", export_command))
    application.add_handler(CommandHandler("report", report_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_domain))
    
    try:
        # Run the bot
        application.run_polling()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    finally:
        scheduler.shutdown()
        logger.info("Scheduler shut down")
