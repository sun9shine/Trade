# دليل التشغيل الكامل — Complete Startup Guide

## المتطلبات المسبقة | Prerequisites

### البرمجيات المطلوبة
| البرنامج | الإصدار | الغرض |
|----------|---------|-------|
| Docker Desktop | v24+ | تشغيل الحاويات |
| Docker Compose | v2.20+ | تنسيق الخدمات |
| Git | v2.40+ | إدارة الكود |
| Python 3.11+ | (اختياري) | تشغيل محلي بدون Docker |
| Node.js 20+ | (اختياري) | تطوير الواجهة محلياً |

### الحسابات المطلوبة
| الخدمة | الغرض | رابط التسجيل |
|--------|-------|-------------|
| OANDA أو MetaTrader 5 | بيانات الفوركس | oanda.com / mql5.com |
| Polymarket | أسواق التنبؤ (Polygon) | polymarket.com |
| Alchemy أو Infura | عُقد RPC | alchemy.com |
| (اختياري) Telegram Bot | إشعارات | @BotFather on Telegram |

### المحافظ المطلوبة
| الشبكة | العملة | الحد الأدنى |
|--------|--------|-------------|
| Polygon | MATIC + USDC | 10 MATIC + 50 USDC |
| Arbitrum | ETH + USDC | 0.01 ETH + 50 USDC |
| Solana | SOL + USDC | 0.5 SOL + 50 USDC |

---

## الخطوة 1: استنساخ المشروع

```bash
git clone https://github.com/sun9shine/Trade.git
cd Trade
```

---

## الخطوة 2: إنشاء مفتاح التشفير

```bash
# إنشاء مفتاح AES-256 (32 بايت بصيغة Base64)
python3 -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"
# مثال الناتج: dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcw==
```

---

## الخطوة 3: إعداد ملف البيئة

```bash
cp .env.example .env
```

### تعديل القيم الأساسية:

```bash
# ─── أمان التطبيق ───
APP_SECRET_KEY=كلمة-سر-طويلة-وعشوائية-هنا
JWT_SECRET=مفتاح-jwt-آخر-مختلف
ENCRYPTION_MASTER_KEY=الناتج-من-الخطوة-2

# ─── قاعدة البيانات ───
DB_PASSWORD=كلمة_سر_قوية_لقاعدة_البيانات
DATABASE_URL=postgresql+asyncpg://arbitrage_user:كلمة_سر_قوية@postgres:5432/arbitrage_bot
```

### إعداد وسيط الفوركس:

```bash
# ─── خيار أ: OANDA (الأسهل، يعمل على كل الأنظمة) ───
OANDA_API_KEY=your-oanda-api-token
OANDA_ACCOUNT_ID=101-001-XXXXXXX-001
OANDA_ENVIRONMENT=practice    # practice أو live

# ─── خيار ب: MetaTrader 5 (يتطلب Windows) ───
MT5_LOGIN=12345678
MT5_PASSWORD=your-password
MT5_SERVER=ICMarketsSC-Demo
```

### إعداد البلوكتشين:

```bash
# ─── Polygon (Polymarket) ───
POLYGON_RPC_URL=https://polygon-mainnet.g.alchemy.com/v2/YOUR-ALCHEMY-KEY
POLYGON_PRIVATE_KEY=0x_مفتاحك_الخاص_هنا
POLYMARKET_API_KEY=your-polymarket-key
POLYMARKET_API_SECRET=your-polymarket-secret
POLYMARKET_PASSPHRASE=your-passphrase

# ─── Arbitrum (Premu) ───
ARBITRUM_RPC_URL=https://arb-mainnet.g.alchemy.com/v2/YOUR-ALCHEMY-KEY
ARBITRUM_PRIVATE_KEY=0x_مفتاحك_الخاص_هنا
PREMU_VAULT_ADDRESS=0x_عنوان_عقد_Premu

# ─── Solana (Monaco) ───
SOLANA_RPC_URL=https://mainnet.helius-rpc.com/?api-key=YOUR-KEY
SOLANA_PRIVATE_KEY=مفتاح_base58_هنا
```

### إعداد حدود المخاطر:

```bash
MAX_POSITION_SIZE_USD=50         # ابدأ بمبلغ صغير!
LATENCY_ARB_MIN_GAP_PCT=1.5     # حد أدنى 1.5% فجوة
NEG_RISK_THRESHOLD=0.96          # عتبة المراجحة السلبية
KILL_SWITCH_ENABLED=false
```

### (اختياري) إعداد الإشعارات:

```bash
# Telegram
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=-1001234567890

# Email
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=app-specific-password
ALERT_EMAIL_TO=alerts@yourdomain.com
```

---

## الخطوة 4: تشغيل النظام

### التشغيل العادي (تطوير):
```bash
docker-compose up -d --build
```

### التشغيل الإنتاجي (مع Nginx + SSL):
```bash
# أولاً: ضع شهادات SSL
mkdir -p nginx/ssl
cp your-cert.pem nginx/ssl/cert.pem
cp your-key.pem nginx/ssl/key.pem

# تشغيل مع بروفايل الإنتاج
docker-compose --profile production up -d --build
```

---

## الخطوة 5: التحقق من التشغيل

```bash
# تحقق أن كل الخدمات تعمل
docker-compose ps

# يجب أن ترى:
# arb_postgres   ✅ running (healthy)
# arb_redis      ✅ running (healthy)
# arb_backend    ✅ running
# arb_worker     ✅ running
# arb_frontend   ✅ running
```

### اختبار الاتصال:
```bash
# Health check
curl http://localhost:8000/health
# المتوقع: {"status":"ok","version":"1.0.0"}

# API Docs
# افتح في المتصفح: http://localhost:8000/docs
```

---

## الخطوة 6: أول تسجيل دخول

عند التشغيل الأول، يُنشأ مستخدم admin تلقائياً:
- **اسم المستخدم:** `admin`
- **كلمة المرور:** أول 16 حرف من `APP_SECRET_KEY` + `Admin1!`

```bash
# مثال تسجيل دخول
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"YOUR_PASSWORD_HERE"}'

# الاستجابة ستحتوي على access_token
```

**⚠️ غيّر كلمة المرور فوراً بعد أول دخول!**

---

## الخطوة 7: تحديث خريطة الأسواق

افتح `backend/app/market_mapping.json` واستبدل القيم الوهمية:

```json
{
  "EURUSD": {
    "polymarket": {
      "market_id": "0x_ACTUAL_CONDITION_ID_FROM_POLYMARKET"
    },
    "premu": {
      "market_id": "ACTUAL_BYTES32_FROM_PREMU"
    }
  }
}
```

للعثور على معرفات الأسواق:
- **Polymarket:** https://polymarket.com → افتح سوق → انسخ condition_id من URL
- **Monaco:** استخدم Monaco Protocol explorer على Solana

---

## الخطوة 8: إدارة قاعدة البيانات

### تشغيل migrations:
```bash
docker-compose exec backend alembic upgrade head
```

### إنشاء migration جديد:
```bash
docker-compose exec backend alembic revision --autogenerate -m "description"
```

---

## الخطوة 9: مراقبة النظام

### سجلات مباشرة:
```bash
# كل الخدمات
docker-compose logs -f

# Worker فقط (الأهم)
docker-compose logs -f worker

# Backend API
docker-compose logs -f backend
```

### ملفات السجلات:
```bash
# داخل حاوية Backend/Worker
docker-compose exec backend ls -la /app/logs/
# arbitrage_bot.log — كل السجلات
# errors.log — الأخطاء فقط
# trades.log — سجل الصفقات
```

### لوحة التحكم:
- **Admin Panel:** http://localhost:3000
- **API Swagger:** http://localhost:8000/docs

---

## الخطوة 10: تشغيل الاختبارات

```bash
# تشغيل كل الاختبارات
docker-compose exec backend pytest tests/ -v

# اختبار محدد
docker-compose exec backend pytest tests/test_arbitrage_router.py -v

# مع تغطية الكود
docker-compose exec backend pytest tests/ --cov=app --cov-report=term-missing
```

---

## الخطوة 11: تشغيل Backtest

```bash
# من داخل الحاوية
docker-compose exec backend python -c "
import asyncio
from app.backtesting import BacktestEngine, BacktestConfig

config = BacktestConfig(
    strategy='latency_arb',
    position_size_usd=100,
    min_edge_pct=1.5,
)
engine = BacktestEngine(config)

# بيانات تجريبية
import random
ticks = [
    {'symbol': 'EURUSD', 'bid': 1.085 + random.gauss(0, 0.002),
     'ask': 1.0852 + random.gauss(0, 0.002),
     'timestamp_ms': 1717200000000 + i * 100}
    for i in range(10000)
]

result = asyncio.run(engine.run(ticks))
print(f'Total PnL: \${result.total_pnl:.2f}')
print(f'Win Rate: {result.win_rate:.1f}%')
print(f'Sharpe: {result.sharpe_ratio}')
print(f'Max Drawdown: {result.max_drawdown:.1f}%')
"
```

---

## الإيقاف والصيانة

### إيقاف طارئ (Kill Switch):
```bash
curl -X POST http://localhost:8000/api/kill-switch/activate \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### إيقاف النظام:
```bash
# إيقاف مع حفظ البيانات
docker-compose stop

# إيقاف وحذف الحاويات
docker-compose down

# إيقاف وحذف كل شيء (بما فيها DB!)
docker-compose down -v
```

### تحديث الكود:
```bash
git pull origin main
docker-compose up -d --build
```

---

## استكشاف الأخطاء

| المشكلة | الحل |
|---------|------|
| Backend لا يبدأ | تحقق من `DATABASE_URL` في `.env` |
| Worker يتوقف | تحقق من مفاتيح الفوركس (OANDA/MT5) |
| لا صفقات تُنفذ | تحقق من `market_mapping.json` — أزل القيم الوهمية |
| خطأ في البلوكتشين | تحقق من أرصدة الغاز وعُقد RPC |
| واجهة لا تعمل | `docker-compose logs frontend` |
| Kill Switch مُفعل | `POST /api/kill-switch/deactivate` |

---

## أوامر مفيدة

```bash
# إعادة بناء خدمة واحدة
docker-compose build backend && docker-compose up -d backend

# دخول shell داخل الحاوية
docker-compose exec backend bash

# مسح قاعدة البيانات والبدء من جديد
docker-compose down -v && docker-compose up -d --build

# فحص استهلاك الموارد
docker stats
```
