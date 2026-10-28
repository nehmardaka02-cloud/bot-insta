# -*- coding: utf-8 -*-
"""
البوت الذكي (AI) — ردود ذكاء اصطناعي + إنشاء صور في رسائل Instagram الخاصة
- يرد على كل الرسائل الواردة (الوارد العادي + طلبات الرسائل) بالذكاء الاصطناعي — مجاناً (Pollinations)
- إن كتب المستخدم "ارسم ..." أو "صمم ..." ينشئ صورة ويرسلها في الخاص مباشرة
- لا يرسل أي رسائل استباقية — رد فقط = نشاط طبيعي أكثر أماناً للحساب
- تذكّر آخر 12 رسالة لكل مستخدم (ذاكرة محادثة)
الجلسة: config.json (session_id) أو متغير البيئة IG_SESSION_ID
تطوير: @j_.8._
"""

import os
import sys
import time
import json
import random
from pathlib import Path
from datetime import datetime

import requests
import urllib.parse
from instagrapi import Client

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
STATE_PATH = os.path.join(BASE_DIR, "religious_state.json")
REPLIED_PATH = os.path.join(BASE_DIR, "replied.json")

CREDIT = "\n\n🛠 تطوير البوت: @j_.8._"

SYSTEM_PROMPT = (
    "أنت MASJON GPT — مساعد ذكاء اصطناعي شامل (مثل ChatGPT) يعمل في الرسائل الخاصة على Instagram، "
    "مطوَّر بواسطة @j_.8._. شخصيتك ودودة وواثقة وعملية. قواعدك:\n"
    "1) تجيب على كل شيء: الواجبات والدراسة (برمجة، رياضيات، فيزياء، كيمياء، لغات)، العلوم، "
    "التكنولوجيا، الترجمة، كتابة النصوص والمقالات، أفكار المشاريع، مشورة الحياة اليومية، الطبخ، "
    "الرياضة، والصحة العامة، وأي سؤال ديني تجيب بدقة وتذكر المصدر (السورة/الراوي) عند اليقين فقط.\n"
    "2) تجيب بلغة المستخدم نفسها (العربية غالباً) بأسلوب واضح ومباشر.\n"
    "3) أجب مختصراً ومفيداً (من سطرين إلى خمسة أسطر)، وتفصّل فقط عندما يطلب المستخدم شرحاً أطول.\n"
    "4) لا تختلق معلومات أو مصادر أو أحاديث؛ إن لم تكن واثقاً قل ذلك بصراحة.\n"
    "5) اعرف اسمك جيداً: أنت MASJON GPT — إذا سألك أحدهم «من أنت؟» قدم نفسك بهذا الاسم.\n"
    "6) ارفض بلطف وجملة قصيرة أي محتوى غير لائق (إباحي، تحريضي، متطرف).\n"
    "7) لا تضف توقيعاً في نهاية رسائلك — التوقيع يضاف تلقائياً بواسطة الكود.\n"
    "8) لديك أيضاً قابلية إنشاء الصور: أذكر أحياناً للمستخدم أنه يستطيع طلب صورة بكتابة «ارسم ...»."
)

IMAGE_WORDS = (
    "ارسم", "أرسم", "صمم", "أنشئ صورة", "أنشيء صورة", "اعمل صورة", "عمل صورة",
    "صورة لـ", "صورة ل", "صورة عن", "صورة:", "رسم", "draw", "generate image",
    "create image", "make an image", "image of",
)


def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def safe_input(msg):
    try:
        return input(msg)
    except EOFError:
        return ""


# ---------------------------------------------------------------- إعدادات والحالة
DEFAULT_CONFIG = {
    "session_id": "",
    "check_interval": 15,
    "credit_handle": "j_.8._",
    "ai": {
        "text_model": "openai-fast",   # pollinations: openai-fast / openai
        "gemini_key": "",              # اختياري: مفتاح Gemini المجاني إن توفّر
    },
    "max_history": 12,
}


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            cfg.update(data)
    except FileNotFoundError:
        log("لم أجد config.json — سأستخدم الإعدادات الافتراضية")
    env_session = os.environ.get("IG_SESSION_ID")
    if env_session:
        cfg["session_id"] = env_session
    return cfg


def load_state():
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state):
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=1)
    except Exception as e:
        log(f"تعذر حفظ الحالة: {e}")


def load_replied():
    try:
        with open(REPLIED_PATH, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_replied(replied):
    try:
        with open(REPLIED_PATH, "w", encoding="utf-8") as f:
            json.dump(sorted(replied)[-5000:], f)
    except Exception as e:
        log(f"تعذر حفظ الجواب المسبق: {e}")


# ---------------------------------------------------------------- الذكاء الاصطناعي
def _pollinations_text(messages, model="openai-fast"):
    """ذكاء اصطناعي مجاني بلا مفتاح — Pollinations (OpenAI متوافق)"""
    last_err = None
    for attempt in range(2):
        try:
            r = requests.post(
                "https://text.pollinations.ai/openai",
                json={"model": model, "messages": messages,
                      "referrer": "masjon-bot-chelfawi",
                      "seed": random.randint(0, 10_000_000)},
                timeout=90,
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            last_err = e
            time.sleep(2 + attempt * 3)
    # بديل: طلب GET مبسط (سطر واحد بلا أسطر جديدة)
    try:
        sys_txt = " ".join(m["content"] for m in messages if m.get("role") == "system")
        convo = " ".join((m.get("content") or "") for m in messages if m.get("role") != "system")
        prompt = (sys_txt + " || الرسالة: " + convo + " || الرد بالعربية:").replace("\n", " ")
        url = "https://text.pollinations.ai/" + urllib.parse.quote(prompt[:600]) + f"?model={model}"
        r = requests.get(url, timeout=90)
        r.raise_for_status()
        return r.text
    except Exception as e:
        raise RuntimeError(f"faily AI text: {last_err} / {e}")


def _gemini_text(messages, key):
    """Google Gemini المجاني (إن أضاف المستخدم مفتاحاً) — جودة أعلى"""
    contents = []
    for m in messages:
        if m["role"] == "system":
            continue
        contents.append({
            "role": "model" if m["role"] == "assistant" else "user",
            "parts": [{"text": m["content"]}],
        })
    sys_txt = "\n".join(m["content"] for m in messages if m["role"] == "system")
    body = {"contents": contents}
    if sys_txt:
        body["systemInstruction"] = {"parts": [{"text": sys_txt}]}
    r = requests.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
        params={"key": key}, json=body, timeout=90,
    )
    r.raise_for_status()
    cands = r.json().get("candidates") or []
    return cands[0]["content"]["parts"][0]["text"]


def ai_text(messages, cfg):
    """بوابة منع الازدحام: لا على الأقل كل 3 ثواني طلب واحد"""
    now = time.time()
    wait = 3.0 - (now - _AI_GATE["last"])
    if wait > 0:
        time.sleep(wait)
    ai = cfg.get("ai") or {}
    key = (ai.get("gemini_key") or "").strip()
    if key:
        try:
            out = _gemini_text(messages, key)
        except Exception as e:
            log(f"تعذر Gemini ({e}) — التحويل إلى البديل المجاني")
            out = None
        if out:
            _AI_GATE["last"] = time.time()
            return out
    model = ai.get("text_model") or "openai-fast"
    out = _pollinations_text(messages, model)
    _AI_GATE["last"] = time.time()
    return out


def is_image_request(text):
    t = (text or "").strip().lower()
    if len(t) < 4:
        return False
    return any(w in t for w in IMAGE_WORDS)


def ai_image_prompt(user_request, cfg):
    """يترجم طلب الرسم إلى وصف إنجليزي قصير تنتج به صناعة الصورة — лучший جودة"""
    instr = (
        "حوّل طلب المستخدم التالي إلى وصف إنجليزي موجز (أقل من 45 كلمة) لإنشاء صورة رقمية. "
        "اجعل الوصف آمناً ومهذباً ومطابقاً للطلب. أخرج الوصف الإنجليزي فقط دون أي كلام آخر.\n\n"
        f"طلب المستخدم: {user_request}"
    )
    try:
        out = ai_text([{"role": "user", "content": instr}], cfg)
        out = (out or "").strip()
        # لو رد بالعربية أو طويل، استعمل الطلب كما هو
        if out and len(out.split()) < 70:
            return out
    except Exception as e:
        log(f"تعذر ترجمة وصف الصورة: {e}")
    return user_request


def generate_image(en_prompt):
    """ينشئ الصورة مجاناً عبر Pollinations — 3 محاولات متسامحة (الخدمة أحياناً مزدحمة)"""
    last_err = None
    for attempt, extra in enumerate(("?width=768&height=768&nologo=true&model=flux",
                                     "?width=768&height=768&nologo=true&model=turbo",
                                     "?width=704&height=704&nologo=true")):
        for inner in range(2):
            try:
                url = (
                    "https://image.pollinations.ai/prompt/"
                    + urllib.parse.quote(en_prompt)
                    + extra
                    + "&seed=" + str(random.randint(0, 10_000_000))
                )
                r = requests.get(url, timeout=180)
                r.raise_for_status()
                ctype = (r.headers.get("Content-Type") or "").lower()
                if not ctype.startswith("image"):
                    raise RuntimeError(f"الرد ليس صورة ({ctype})")
                path = Path(BASE_DIR) / f"ai_img_{int(time.time()*1000)}.jpg"
                path.write_bytes(r.content)
                return path
            except Exception as e:
                last_err = e
                log(f"محاولة صورة {attempt+1}.{inner+1} فشلت: {e} — انتظار ...")
                time.sleep(8 + attempt * 5)
    raise RuntimeError(f"تعذر توليد الصورة بعد كل المحاولات: {last_err}")


# ---------------------------------------------------------------- قلب البوت
_HIST = {}  # uid -> قائمة رسائل المحادثة
_AI_GATE = {"last": 0.0}  # منع الازدحام بين طلبات الذكاء الاصطناعي


def handle_incoming(cl, my_id, cfg, replied):
    """يفحص الوارد + طلبات الرسائل، ويرد بالذكاء الاصطناعي أو ينشئ صورة"""
    threads = cl.direct_threads(amount=20)
    try:
        reqs = cl.direct_requests(amount=20)
        if reqs:
            log(f"📨 جلبت {len(reqs)} محادثة من طلبات الرسائل (حسابات خارج المتابعة)")
        threads += reqs
    except Exception as e:
        log(f"تعذر جلب طلبات الرسائل: {e}")

    max_hist = int((cfg.get("max_history") or 12))
    for t in threads:
        msgs = getattr(t, "messages", []) or []
        if not msgs:
            continue
        last = msgs[0]
        text = getattr(last, "text", None)
        sender = str(getattr(last, "user_id", ""))
        msg_id = str(getattr(last, "id", "")) or f"{t.id}_{sender}"
        if not text or sender == my_id or sender == "17841400000000000":
            continue
        if msg_id in replied:
            continue
        # علّم مبكراً حتى لا نرد مرتين على نفس الرسالة
        replied.add(msg_id)
        save_replied(replied)

        targets = [
            int(str(getattr(u, "pk", "")))
            for u in (getattr(t, "users", []) or [])
            if str(getattr(u, "pk", "")) and str(getattr(u, "pk", "")) != my_id
        ]
        if not targets:
            continue
        uid = str(targets[0])
        body = (text or "").strip()

        try:
            if is_image_request(body):
                time.sleep(random.uniform(1, 2))
                cl.direct_send(f"🖌 جارٍ إنشاء صورتك: «{body[:60]}» — انتظر لحظات...", [targets[0]])
                log(f"🖼 طلب صورة من {uid}: {body[:60]!r}")
                try:
                    en = ai_image_prompt(body, cfg)
                    path = generate_image(en)
                    cl.direct_send_photo(path, [targets[0]])
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                    cl.direct_send("🎨 هذه صورتك! اطلب تعديلاً أو ارسم أخرى 🌟" + CREDIT, [targets[0]])
                    log(f"✅ أرسلت الصورة إلى {uid}")
                except Exception as e2:
                    log(f"تعذر توليد الصورة لـ {uid}: {e2}")
                    cl.direct_send(
                        "😅 تعذر إنشاء الصورة الآن — خدمة الصور مجانية ومزدحمة أحياناً.\n"
                        "أعد المحاولة بعد دقيقة بكتابة: ارسم ..." + CREDIT,
                        [targets[0]],
                    )
            else:
                time.sleep(random.uniform(1, 2))
                h = _HIST.setdefault(uid, [])
                h.append({"role": "user", "content": body})
                if len(h) > max_hist:
                    h[:] = h[-max_hist:]
                msgs2 = [{"role": "system", "content": SYSTEM_PROMPT}] + h
                reply = (ai_text(msgs2, cfg) or "").strip()
                if not reply:
                    continue
                h.append({"role": "assistant", "content": reply})
                if len(h) > max_hist:
                    h[:] = h[-max_hist:]
                if "🛠 تطوير البوت" not in reply:
                    reply += CREDIT
                cl.direct_send(reply, [targets[0]])
                log(f"🤖 رد ذكي إلى {uid} — «{body[:40]!r}»")
        except Exception as e:
            log(f"تعذر الرد على {uid}: {e}")


# ---------------------------------------------------------------- الاتصال والتشغيل
def main():
    print("=" * 60)
    print("  MASJON GPT - الذكاء الاصطناعي الشامل في إنستغرام")
    print("=" * 60)

    cfg = load_config()
    if not (cfg.get("session_id") or "").strip():
        log("لا يوجد Session! ضع session_id في config.json أو متغير البيئة IG_SESSION_ID")
        safe_input("\nاضغط Enter للخروج...")
        sys.exit(1)
    interval = int(cfg.get("check_interval") or 15)

    cl = Client()
    cl.delay_range = [1, 3]
    cl.handle_exception = False

    state = load_state()
    dev = state.get("device") or {}
    try:
        if dev.get("device_settings"):
            cl.set_device(dev["device_settings"])
        if dev.get("uuids"):
            cl.set_uuids(dev["uuids"])
        if dev:
            log("📱 أعدت استخدام هوية الجهاز المحفوظة — ثبات الجلسة أفضل")
    except Exception as e:
        log(f"تعذّر ضبط هوية الجهاز: {e}")

    log("جارٍ الاتصال بالحساب عبر الـ Session ...")
    connected = False
    for attempt in range(1, 4):
        try:
            cl.login_by_sessionid(cfg["session_id"])
            connected = True
            break
        except Exception as e:
            log(f"فشل الاتصال (محاولة {attempt}/3): {e}")
            if attempt < 3:
                log("انتظار 60 ثانية قبل إعادة المحاولة ...")
                time.sleep(60)
    if not connected:
        log("غالباً الـ Session انتهى أو مطلوب تحقق. أكمل التحقق في التطبيق ثم خذ Session جديد وحدّثه في config.json على GitHub")
        safe_input("\nاضغط Enter للخروج...")
        sys.exit(1)

    me = None
    for attempt in range(1, 4):
        try:
            me = cl.account_info()
            break
        except Exception as e:
            log(f"تعذر جلب معلومات الحساب (محاولة {attempt}/3): {e}")
            if attempt < 3:
                time.sleep(60)
    if me is None:
        log("فشل تأكيد الهوية بعد 3 محاولات — خذ Session جديد وحدّثه في config.json")
        sys.exit(1)
    my_id = str(me.pk)
    log(f"✅ تم الاتصال بنجاح باسم: @{me.username}")

    try:
        state["device"] = {"device_settings": cl.device_settings, "uuids": cl.uuids}
        if state["device"].get("device_settings"):
            save_state(state)
            log("📱 حفظت هوية الجهاز في الملفات")
    except Exception:
        pass

    replied = load_replied()
    log("🤖 MASJON GPT جاهز — أنتظر الرسائل ...")

    errors_in_row = 0
    while True:
        try:
            handle_incoming(cl, my_id, cfg, replied)
            errors_in_row = 0
            time.sleep(interval)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            errors_in_row += 1
            log(f"خطأ في الدورة ({errors_in_row}): {e}")
            if errors_in_row >= 10:
                log("أخطاء متتالية كثيرة — إعادة تشغيل نظيفة (Render سيعاد تشغيله تلقائياً)")
                sys.exit(1)
            time.sleep(min(60 * errors_in_row, 300))


if __name__ == "__main__":
    main()
