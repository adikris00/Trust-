# Enhanced Domain Trust+ Checker Bot

Bot Telegram untuk mengecek status domain dengan fitur monitoring, bookmark, dan analytics lengkap.

## 🚀 Fitur Utama

### 📊 Domain Checking
- Cek satu domain atau bulk (hingga 10 domain)
- Status real-time: Diblokir/Tidak Diblokir
- Tombol interaktif untuk aksi cepat

### 💾 Database & History
- Riwayat pengecekan per user
- Bookmark domain favorit (maksimal 20)
- Statistik penggunaan personal
- Export data ke CSV

### 🔔 Monitoring & Alerts
- Monitor domain harian otomatis
- Notifikasi real-time jika status berubah
- Subscription management (maksimal 10 domain)
- Background scheduler dengan APScheduler

### 📈 Analytics & Reporting
- Statistik penggunaan bot
- Laporan domain populer bulanan
- Export riwayat dalam format CSV

## 📋 Commands

```
/start - Mulai bot
/help - Bantuan lengkap
/history - Riwayat pengecekan (20 terakhir)
/bookmarks - Kelola domain favorit
/subscriptions - Kelola domain monitoring
/stats - Statistik penggunaan pribadi
/export - Download data dalam CSV
/report - Laporan domain populer
```

## 🛠️ Setup & Deploy

### Environment Variables
```
TELEGRAM_BOT_TOKEN=your_bot_token_here
```

### Files Required
- `main.py` - Main bot application
- `requirements.txt` - Python dependencies  
- `railway.toml` - Railway configuration (optional)

### Deploy to Railway
1. Connect GitHub repository to Railway
2. Set environment variable `TELEGRAM_BOT_TOKEN`
3. Deploy automatically from main branch

## 💡 Usage

### Basic Domain Check
```
google.com
```

### Bulk Domain Check
```
google.com, yahoo.com, github.com
```

### Interactive Features
- 🔄 **Cek Ulang** - Re-check domain instantly
- ⭐ **Bookmark** - Save to favorites
- 🔔 **Monitor** - Get notifications on status change
- ❌ **Remove** - Delete from bookmarks/subscriptions

## 🔧 Technical Details

- **Database**: SQLite (persistent on Railway)
- **Scheduler**: APScheduler for daily monitoring (9 AM)
- **API**: Integration dengan check.skiddle.id
- **Rate Limiting**: 1 second delay between API calls
- **Message Limits**: Telegram 4096 character limit handled

## 📊 Database Schema

### Tables
- `domain_history` - User check history
- `domain_bookmarks` - User favorite domains
- `domain_subscriptions` - Monitoring subscriptions
- `user_stats` - User statistics

## 🚨 Limitations

- Maksimal 10 domain per bulk check
- Maksimal 20 bookmark per user
- Maksimal 10 subscription per user
- API timeout 15 seconds

## 📝 Changelog

### v2.0 (Enhanced)
- ✅ Database integration with SQLite
- ✅ User history and bookmarks
- ✅ Domain monitoring with notifications
- ✅ Interactive buttons and callbacks
- ✅ Statistics and reporting
- ✅ CSV export functionality
- ✅ Background scheduler for monitoring

### v1.0 (Basic)
- ✅ Basic domain checking
- ✅ Bulk domain support
- ✅ Simple text responses

## 🤝 Contributing

1. Fork the repository
2. Create feature branch
3. Make your changes
4. Submit pull request

## 📞 Support

Jika ada pertanyaan atau masalah, silakan buat issue di GitHub repository.

---

**Bot Status**: 🟢 Active and Running on Railway
**Last Updated**: September 2025
