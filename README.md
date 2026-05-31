# بوت المراجحة عبر الأسواق — Cross-Market Latency Arbitrage Bot

<div dir="rtl">

## 📌 كيف يربح هذا البوت؟

### الاستراتيجية الأولى: المراجحة الزمنية (Latency Arbitrage)

```
┌──────────────┐        ┌──────────────────┐
│  سوق الفوركس  │ ──→ ──→ │  سوق التنبؤ       │
│  (يتحرك فوراً) │        │  (يتأخر 1-5 ثوانٍ) │
└──────────────┘        └──────────────────┘
       ▼                         ▼
  سعر الذهب يقفز              الاحتمالات لم تتغير بعد
  +2% خلال ثانية              لا تزال 50% صعود / 50% هبوط
       ▼                         ▼
  ─────────────── نشتري "صعود" بسعر رخيص ──────────────
       ▼
  بعد 5 دقائق: السوق يعدّل → نبيع بربح ✅
```

**مثال حقيقي بالأرقام:**

| الخطوة | التفصيل |
|--------|---------|
| 1️⃣ الرصد | البنك الفدرالي يرفع الفائدة → الدولار يقفز 1.8% فوراً |
| 2️⃣ الفحص | منصة Premu لا تزال تعرض: صعود الدولار = 50 سنت (احتمال 50%) |
| 3️⃣ الحساب | القيمة العادلة بعد الخبر = 75% على الأقل → فجوة 25% |
| 4️⃣ الشراء | نشتري 100 حصة "صعود" × 0.50$ = **50$ تكلفة** |
| 5️⃣ النتيجة | بعد 5 دقائق: الصعود يتأكد → كل حصة = 1$ → **100$ عائد** |
| 💰 الربح | 100$ - 50$ = **50$ ربح صافي** (100% عائد) |

---

### الاستراتيجية الثانية: المراجحة السلبية (Negative Risk Arbitrage)

```
سوق "من يفوز بالانتخابات؟" (3 مرشحين)
┌─────────────────────────────────┐
│  مرشح أ = 42 سنت               │
│  مرشح ب = 38 سنت               │
│  مرشح ج = 15 سنت               │
│  ─────────────────────────       │
│  المجموع = 95 سنت (أقل من $1!) │
└─────────────────────────────────┘

→ اشترِ الثلاثة بـ 95 سنت
→ مهما كانت النتيجة: تحصل على $1
→ ربح مضمون: 5 سنتات (5.26%)
```

**لماذا يحدث هذا؟**
- أسواق التنبؤ لامركزية ← لا صانع سوق واحد يوازن الأسعار
- فارق السيولة بين المنصات ← أسعار مختلفة لنفس الحدث
- البوت يراقب المجموع باستمرار ← إذا أقل من 96% يشتري فوراً

---

## 💸 كيف يتم سحب الأرباح؟

### مسار الأموال الكامل:

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│ محفظتك   │ ──→ │ شراء حصص │ ──→ │ تسوية    │ ──→ │ سحب USDC │
│ (USDC)   │     │ (تلقائي)  │     │ (فوز)    │     │ لمحفظتك  │
└──────────┘     └──────────┘     └──────────┘     └──────────┘
                                                         │
                                                         ▼
                                              ┌──────────────────┐
                                              │ تحويل لحسابك     │
                                              │ البنكي            │
                                              └──────────────────┘
```

### خطوات سحب الأرباح لكل منصة:

#### 1. Polymarket (شبكة Polygon)

| الخطوة | العملية |
|--------|---------|
| 1 | الأرباح تُودع تلقائياً كـ USDC في محفظتك على Polygon |
| 2 | افتح محفظة MetaMask → شبكة Polygon |
| 3 | أرسل USDC إلى بورصة مركزية (Binance/Bybit) عبر Polygon |
| 4 | بع USDC مقابل عملتك المحلية (SAR/AED/USD) |
| 5 | اسحب للحساب البنكي |

#### 2. Premu (شبكة Arbitrum)

| الخطوة | العملية |
|--------|---------|
| 1 | الأرباح تُودع كـ USDC على Arbitrum |
| 2 | ابقَ على Arbitrum أو اعبر جسر (Bridge) إلى Ethereum |
| 3 | أرسل لبورصة تدعم Arbitrum (Binance/OKX) |
| 4 | بع وحوّل لحسابك |

#### 3. Monaco Protocol (شبكة Solana)

| الخطوة | العملية |
|--------|---------|
| 1 | الأرباح تُودع كـ USDC على Solana |
| 2 | أرسل إلى Phantom Wallet أو مباشرة لبورصة |
| 3 | بورصات تدعم Solana USDC: Binance, Bybit, Coinbase |
| 4 | بع واسحب |

### ⚡ خلاصة السحب:
> **الأرباح = USDC (دولار رقمي) ← بورصة ← حسابك البنكي**
>
> المدة: 5-30 دقيقة (حسب البورصة وطريقة السحب)

### 💡 نصائح للسحب:
- **استخدم شبكة Polygon أو Arbitrum** — رسوم أقل من Ethereum
- **Binance P2P** — أسهل طريقة لتحويل USDC → عملة محلية في الخليج
- **لا تسحب كل شيء** — أبقِ رصيد للصفقات + رسوم الغاز
- **وثّق كل عملية** — للأغراض الضريبية

---

## 🚀 دليل التشغيل خطوة بخطوة

### المرحلة 1: التجهيز (مرة واحدة فقط)

#### 1.1 — تثبيت Docker
```bash
# على Ubuntu/Debian
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# على Mac
# حمّل Docker Desktop من docker.com

# على Windows
# حمّل Docker Desktop + فعّل WSL2
```

#### 1.2 — استنساخ المشروع
```bash
git clone https://github.com/sun9shine/Trade.git
cd Trade
```

#### 1.3 — إنشاء مفتاح التشفير
```bash
python3 -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"
# احفظ الناتج — ستحتاجه في الخطوة التالية
```

#### 1.4 — إعداد ملف البيئة
```bash
cp .env.example .env
nano .env    # أو أي محرر نصوص
```

**القيم المطلوب تعبئتها:**

```bash
# ═══════════════════════════════════════════
# أساسي (أنشئ قيم عشوائية قوية)
# ═══════════════════════════════════════════
APP_SECRET_KEY=my-super-secret-key-change-this-now
JWT_SECRET=another-random-secret-for-jwt
ENCRYPTION_MASTER_KEY=الناتج_من_الخطوة_1.3
DB_PASSWORD=strong-database-password-here

# ═══════════════════════════════════════════
# الفوركس — اختر واحد:
# ═══════════════════════════════════════════

# خيار أ: OANDA (يعمل على كل الأنظمة)
OANDA_API_KEY=افتح-حساب-مجاني-من-oanda.com
OANDA_ACCOUNT_ID=101-001-XXXXXXX-001
OANDA_ENVIRONMENT=practice

# ═══════════════════════════════════════════
# البلوكتشين
# ═══════════════════════════════════════════

# Polygon (لـ Polymarket)
POLYGON_RPC_URL=https://polygon-mainnet.g.alchemy.com/v2/مفتاحك
POLYGON_PRIVATE_KEY=0xالمفتاح_الخاص_لمحفظة_polygon

# Arbitrum (لـ Premu)
ARBITRUM_RPC_URL=https://arb-mainnet.g.alchemy.com/v2/مفتاحك
ARBITRUM_PRIVATE_KEY=0xالمفتاح_الخاص_لمحفظة_arbitrum

# Solana (لـ Monaco)
SOLANA_RPC_URL=https://mainnet.helius-rpc.com/?api-key=مفتاحك
SOLANA_PRIVATE_KEY=المفتاح_الخاص_base58

# Polymarket API
POLYMARKET_API_KEY=من-polymarket.com
POLYMARKET_API_SECRET=السر
POLYMARKET_PASSPHRASE=عبارة-المرور

# ═══════════════════════════════════════════
# حدود المخاطرة
# ═══════════════════════════════════════════
MAX_POSITION_SIZE_USD=50
LATENCY_ARB_MIN_GAP_PCT=1.5
NEG_RISK_THRESHOLD=0.96
KILL_SWITCH_ENABLED=false
```

---

### المرحلة 2: التشغيل

#### 2.1 — بناء وتشغيل كل الخدمات
```bash
docker-compose up -d --build
```

#### 2.2 — التحقق
```bash
docker-compose ps

# يجب أن ترى:
# arb_postgres   ✅ running (healthy)
# arb_redis      ✅ running (healthy)
# arb_backend    ✅ running
# arb_worker     ✅ running ← هذا هو محرك التداول
# arb_frontend   ✅ running
```

#### 2.3 — فتح لوحة التحكم
```
🖥️  لوحة التحكم:  http://localhost:3000
📊  API Docs:      http://localhost:8000/docs
❤️  Health Check:  http://localhost:8000/health
```

#### 2.4 — تسجيل الدخول الأول
- **المستخدم:** `admin`
- **كلمة المرور:** أول 16 حرف من APP_SECRET_KEY + `Admin1!`

---

### المرحلة 3: تفعيل التداول

#### 3.1 — تمويل المحافظ
- أرسل MATIC إلى محفظة Polygon (لرسوم الغاز)
- أرسل ETH إلى محفظة Arbitrum (لرسوم الغاز)
- أرسل SOL إلى محفظة Solana (لرسوم الغاز)
- أرسل USDC إلى كل محفظة (للتداول)

#### 3.2 — تحديث خريطة الأسواق
افتح `backend/app/market_mapping.json` وضع معرفات أسواق حقيقية:
- اذهب لـ polymarket.com → اختر سوق → انسخ condition_id
- ضعه في الملف بدل `REPLACE_WITH_ACTUAL_CONDITION_ID`

#### 3.3 — تأكد أن Worker يعمل
```bash
docker-compose logs -f worker

# يجب أن ترى:
# worker.running tasks=4
# worker.forex_stream_starting source=oanda
# worker.heartbeat ticks=0 signals=0
```

---

### المرحلة 4: المراقبة اليومية

#### أوامر المراقبة:
```bash
# مشاهدة سجلات التداول مباشرة
docker-compose logs -f worker

# حالة النظام
curl http://localhost:8000/api/metrics \
  -H "Authorization: Bearer YOUR_TOKEN"

# إيقاف طارئ
curl -X POST http://localhost:8000/api/kill-switch/activate \
  -H "Authorization: Bearer YOUR_TOKEN"
```

#### من لوحة التحكم (http://localhost:3000):
- 📊 **المقاييس** — P&L + عدد الصفقات + أرصدة الغاز
- 🔑 **المفاتيح** — تحديث API keys
- 🌐 **RPC** — اختبار سرعة العُقد
- 🔗 **Webhooks** — استقبال أخبار اقتصادية

---

## ⚠️ تحذيرات مهمة

| التحذير | التفصيل |
|---------|---------|
| 🚨 **ابدأ بمبلغ صغير** | لا تضع أكثر من $50 حتى تفهم النظام |
| 🔐 **لا تشارك .env** | يحتوي مفاتيحك الخاصة — إذا سُرق تُسرق أموالك |
| ⛽ **راقب أرصدة الغاز** | بدون MATIC/ETH/SOL لن تُنفذ أي صفقة |
| 📉 **لا ربح مضمون** | الأسواق تتطور — الفجوات قد تختفي |
| 🧪 **اختبر أولاً** | استخدم `OANDA_ENVIRONMENT=practice` للتجربة بدون مال حقيقي |
| ⏱️ **السرعة مهمة** | استخدم RPC سريع (Alchemy/Helius) — العُقد المجانية بطيئة |
| 🔄 **حدّث market_mapping** | الأسواق تنتهي — يجب تحديث المعرفات أسبوعياً |

---

## 📊 العوائد المتوقعة

> **تنبيه:** هذه تقديرات مبنية على ظروف سوق طبيعية — ليست ضمانات.

| الاستراتيجية | العائد المتوقع | التكرار | المخاطرة |
|--------------|---------------|---------|----------|
| مراجحة زمنية | 2-10% لكل صفقة | 3-10 صفقات/يوم | متوسطة |
| مراجحة سلبية | 1-5% مضمون | 1-3 فرص/أسبوع | منخفضة جداً |

**العوامل المؤثرة:**
- سرعة اتصالك بالإنترنت
- رأس المال المتاح
- عدد الأسواق المراقبة
- سرعة عُقد RPC

---

## 🛑 كيف توقف النظام؟

```bash
# إيقاف عادي (البيانات محفوظة)
docker-compose stop

# إيقاف مع حذف الحاويات
docker-compose down

# إيقاف وحذف كل شيء (بما فيها قاعدة البيانات)
docker-compose down -v

# تشغيل مرة أخرى
docker-compose up -d
```

---

## 🏗 هيكل المشروع

```
Trade/
├── backend/                    # محرك التنفيذ (Python)
│   ├── app/
│   │   ├── worker.py           # ← الحلقة الرئيسية للتداول
│   │   ├── connectors/         # موصلات المنصات
│   │   │   ├── forex_engine.py # بيانات الفوركس (MT5/OANDA)
│   │   │   ├── polymarket.py   # Polymarket V2
│   │   │   ├── premu.py        # Premu.xyz (Arbitrum)
│   │   │   └── monaco.py       # Monaco (Solana)
│   │   ├── engine/
│   │   │   ├── arbitrage_router.py  # منطق المراجحة
│   │   │   └── webhook_handler.py   # معالجة الأخبار
│   │   ├── auth.py             # مصادقة + صلاحيات
│   │   ├── alerts.py           # إشعارات Telegram/Email
│   │   ├── backtesting.py      # اختبار تاريخي
│   │   ├── market_mapping.json # خريطة الأسواق
│   │   └── resilience.py       # إعادة الاتصال التلقائي
│   ├── tests/                  # اختبارات آلية
│   └── migrations/             # مخططات قاعدة البيانات
├── frontend/                   # لوحة التحكم (عربي/إنجليزي)
├── nginx/                      # خادم وكيل + SSL
├── docs/                       # التوثيق
├── docker-compose.yml          # تشغيل كل الخدمات
└── .env.example                # نموذج الإعدادات
```

---

## 🔧 الدعم الفني

- **المشاكل والاستفسارات:** افتح Issue على GitHub
- **دليل التشغيل المفصّل:** `docs/STARTUP_GUIDE.md`
- **هيكل النظام:** `docs/ARCHITECTURE.md`

</div>

---

## English Summary

### How the bot makes money:
1. **Latency Arbitrage** — Forex moves instantly; prediction markets lag 1-5 seconds → buy underpriced outcomes
2. **Negative Risk Arbitrage** — When all outcome prices sum to <$1, buy all outcomes for risk-free profit at settlement

### How to withdraw profits:
- Profits settle as **USDC** (stablecoin) in your wallets on Polygon/Arbitrum/Solana
- Send USDC to a centralized exchange (Binance, Bybit, Coinbase)
- Sell USDC for local currency → withdraw to bank account
- Timeline: 5-30 minutes depending on exchange

### Quick Start:
```bash
git clone https://github.com/sun9shine/Trade.git
cd Trade
cp .env.example .env        # Edit with your credentials
docker-compose up -d --build # Start all services
# Admin Panel: http://localhost:3000
# API Docs: http://localhost:8000/docs
```

### Architecture:
- **Backend:** Python FastAPI + async execution engine
- **Frontend:** Next.js 14 + Tailwind CSS (Arabic RTL / English LTR)
- **Database:** PostgreSQL 15 + Redis 7
- **Blockchain:** Polygon + Arbitrum + Solana (3 chains)
- **Security:** AES-256-GCM encryption, JWT auth, RBAC, rate limiting
