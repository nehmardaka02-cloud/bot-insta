# 🕌 بوت إنستغرام للأذكار — من القرآن والسنة

بوت يرد على كل متابع يراسله بـ **ذكر من القرآن والسنة مع مصدره** + رسالة أذكار الصباح التلقائية (06:00 توقيت الجزائر) لكل من كان نشطًا خلال 24 ساعة.

## 📁 الملفات
| الملف | وظيفتو |
|---|---|
| `server.js` | الكود: الويب هوك + توقيع Meta + الإرسال + ذكر الصباح اليومي |
| `adhkar.js` | الأذكار والآيات بمصادرها — زيد/بدّل كيف تحب |
| `.env` | التوكن وسري (احتفظ به محفوظًا، لا تشاركه مع أحد!) |

## ⚙️ نظام الاستعمال (المتابعة من DM)
- «سلام» → القائمة والترحيب
- «صباح» → أذكار الصباح | «مساء» → أذكار المساء | «آية» → آية من القرآن
- أي كلام آخر → ذكر عشوائي
- «بسّر» → إيقاف ذكر الصباح التلقائي | «كمّل» → إعادته

## ⚠️ قيد مهم من إنستغرام (وقانونية = مهم)
إنستغرام يسمح بالمراسلة **فقط داخل نافذة 24 ساعة** بعد آخر تفاعل من المستخدم.
- هناك بوت يرد على رسائل كل من يراسله ✅
- ذكر الصباح التلقائي يُرسل **فقط للأشخاص النشطين خلال 24 ساعة الماضية** (الكود يسجل الأوقات)
- **إرسال غامق broadcast لكل المتابعين = مخالف لشروط Meta** — يتجنب بواسطة الكود الآن

## 📝 متطلبات الحساب
- حساب إنستغرام **احترافي (Business/Creator)** مرتبط بتطبيق Meta المذكور
- التطبيق في Meta يحتاج صلاحيات: `instagram_business_basic` و `instagram_business_manage_messages`
- تطبيق في وضع **Development** = يعمل مع Admins/Testers فقط حتى موافقة المراجعة

## 🚀 النشر على Render (نفس طريقة ب البوت الآخر)
1. ارفع الملفات في `GitHub` (repo جديد: `instagram-dhikr-bot`)
2. في **Render**: New → Web Service → اختار الريبو
   - Build: `npm install` | Start: `node server.js` | Type: Free
3. في **Environment Variables** أضف كل القيم اللي في `.env` واحد واحد:
   - `IG_ACCESS_TOKEN` · `IG_USER_ID` · `API_VERSION` · `VERIFY_TOKEN` · `META_APP_SECRET`
4. انسخ الـ URL: `https://YOUR-BOT.onrender.com`

## 🔗 ربط الويب هوك في Meta
1. developers.facebook.com → تطبيقك → **Instagram** → **Webhooks**
2. **Callback URL**: `https://YOUR-BOT.onrender.com/webhook`
3. **Verify Token**: `masjon_webhook_verify_2026`
4. **Verify and Save** → ثم **Subscribe** إلى حقل **`messages`**

## ⏰ ملاحظة التوكن (مهم)
توكن إنستغرام (Instagram API with Instagram Login) يبقى صالحًا **~60 يومًا**. بعد انتهائه:
- جدّده بطلب:
  `GET https://graph.instagram.com/refresh_access_token?grant_type=ig_exchange_token&client_secret={META_APP_SECRET}&access_token={IG_ACCESS_TOKEN}`
- حدّد تذكيرًا في هاتفك بعد 50 يومًا باش ما تنساش 🔔

## 🔒 الأمان
- العمرك ما تشارك التوكنات في أي مكان
- ومن بعد ما شاركتها هنا في المحادثة — **الزين تبدّلها**:
  - `META_APP_SECRET`: من طبقة التطبيق → App Settings → Basic → App Secret → Reset
  - `IG_ACCESS_TOKEN`: يبدّل وروح من dashboard
