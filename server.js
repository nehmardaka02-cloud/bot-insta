// =============================================
//  بوت إنستغرام للأذكار — من القرآن والسنة 🕌
//  يعمل على Render.com أو أي سيرفر Node.js
//  هوك: /webhook
// =============================================

const crypto = require("crypto");
const express = require("express");
const cron = require("node-cron");
const { buildReply, formatDhikr, pickFrom, adhkarData } = require("./adhkar");

const app = express();

const IG_ACCESS_TOKEN = process.env.IG_ACCESS_TOKEN || "";
const IG_USER_ID = process.env.IG_USER_ID || "";
const API_VERSION = process.env.API_VERSION || "v25.0";
const VERIFY_TOKEN = process.env.VERIFY_TOKEN || "masjon_webhook_verify_2026";
const META_APP_SECRET = process.env.META_APP_SECRET || "";

// التقاط الجسم الخام للتحقق من التوقيع
app.use(
  express.json({
    verify: (req, _res, buf) => {
      req.rawBody = buf;
    },
  })
);

// المشتركون في رسالة الصباح اليومية: id PhysicalId → آخر وقت نشاط
// (الملاحظة: إنستغرام يسمح بالمراسلة داخل نافذة 24 ساعة بعد آخر تفاعل)
const dailyOptOut = new Set(); // اللي قال «بسّر» ما يوصلهوش ذكر الصباح
const lastActive = new Map();
const TWENTY_FOUR_H = 24 * 60 * 60 * 1000;

// ---------- إرسال الرسائل ----------
function postTo(url, body) {
  return fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(async (r) => {
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      const err = new Error(`SendAPI ${r.status}: ${JSON.stringify(data).slice(0, 300)}`);
      err.status = r.status;
      throw err;
    }
    return data;
  });
}

async function callSendAPI(recipientId, message) {
  // المسار الأول: graph.instagram.com (Instagram API with Instagram Login)
  try {
    return await postTo(`https://graph.instagram.com/${API_VERSION}/me/messages`, {
      recipient: { id: recipientId },
      message,
      access_token: IG_ACCESS_TOKEN,
    });
  } catch (err) {
    // المسار البديل: graph.facebook.com (التطبيق مربوط بصفحة فيسبوك)
    if (err.status === 404 || err.status === 401 || err.status === 403) {
      return await postTo(`https://graph.facebook.com/${API_VERSION}/${IG_USER_ID}/messages`, {
        recipient: { id: recipientId },
        message,
        access_token: IG_ACCESS_TOKEN,
      });
    }
    throw err;
  }
}

// ---------- التحقق من توقيع Meta ----------
function verifySignature(req) {
  if (!META_APP_SECRET) return true; // غير مفعل — يفضل تفعيله
  const header = req.headers["x-hub-signature-256"] || "";
  if (!header.startsWith("sha256=")) return false;
  const expected = crypto
    .createHmac("sha256", META_APP_SECRET)
    .update(req.rawBody)
    .digest("hex");
  const got = header.slice(7);
  const a = Buffer.from(expected, "hex");
  const b = Buffer.from(got, "hex");
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

// ---------- تحقق الويب هوك (GET) ----------
app.get("/webhook", (req, res) => {
  const mode = req.query["hub.mode"];
  const token = req.query["hub.verify_token"];
  const challenge = req.query["hub.challenge"];

  if (mode === "subscribe" && token === VERIFY_TOKEN) {
    console.log("✅ WEBHOOK تم التحقق منه");
    res.status(200).send(challenge);
  } else {
    res.sendStatus(403);
  }
});

// ---------- استقبال الرسائل (POST) ----------
app.post("/webhook", async (req, res) => {
  if (!verifySignature(req)) {
    console.warn("🚫 توقيع غير صالح");
    return res.sendStatus(403);
  }

  const body = req.body;
  if (!["instagram", "page"].includes(body.object)) {
    return res.sendStatus(404);
  }

  for (const entry of body.entry || []) {
    for (const event of entry.messaging || []) {
      // نتجاوز الصدى (رسائل الحساب نفسه)
      if (event.message?.is_echo) continue;

      const senderId = event.sender?.id;
      const text = event.message?.text || "";

      if (senderId && text) {
        lastActive.set(senderId, Date.now());

        const t = text.toLowerCase();
        let reply;

        if (["بسّر", "بسر", "وقف", "stop", "لا تبعث"].some(w => t.includes(w))) {
          dailyOptOut.add(senderId);
          reply = "تم ✅ لن يوصلك ذكر الصباح التلقائي. نرسل لك غير حين تراسلني.\n﴿وَذَكِّرْ فَإِنَّ الذِّكْرَىٰ تَنفَعُ الْمُؤْمِنِينَ﴾";
        } else if (["كمّل", "أواصل", "resume"].some(w => t.includes(w))) {
          dailyOptOut.delete(senderId);
          reply = "ولّينا نعاودو 🌅 ذكر الصباح يوصلك كل يوم باقية التصق.\n" + formatDhikr(pickFrom(adhkarData.morning));
        } else {
          reply = buildReply(text);
        }

        try {
          await callSendAPI(senderId, { text: reply });
        } catch (err) {
          console.error("❌ فشل الإرسال إلى", senderId, ":", err.message);
        }
      }
    }
  }

  res.status(200).send("EVENT_RECEIVED");
});

// ---------- صفحة رئيسية (باش Render ما يقولشي كذا) ----------
app.get("/", (_req, res) => {
  res.send("🕌 بوت الأذكار راه خدّام! (الويب هوك: /webhook)");
});

// ---------- ذكر الصباح التلقائي: كل يوم 06:00 توقيت الجزائر ----------
// يصله غير اللي تفعّل معايا خلال 24 ساعة (قند قوانين إنستغرام)
cron.schedule("0 6 * * *", async () => {
  console.log("⏰ ذكر الصباح...");
  const now = Date.now();
  for (const [id, ts] of lastActive.entries()) {
    if (now - ts > TWENTY_FOUR_H) continue; // برا نافذة الإرسال
    if (dailyOptOut.has(id)) continue;
    try {
      const msg = "🌅 أذكار الصباح 🌅\n\n" + formatDhikr(pickFrom(adhkarData.morning));
      await callSendAPI(id, { text: msg });
      console.log("✅ تم إرسال ذكر الصباح إلى", id);
    } catch (err) {
      // إذا خارج النافذة نحيدو المرسل من القائمة هذي المرة
      console.error("❌ فشل الإرسال إلى", id, ":", err.message);
    }
  }
}, { timezone: "Africa/Algiers" });

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`🚀 سيرفر الأذكار خدّام على المنفذ ${PORT}`);
  if (!IG_ACCESS_TOKEN) console.warn("⚠️ IG_ACCESS_TOKEN فارغ! حطّه في Environment Variables");
});
