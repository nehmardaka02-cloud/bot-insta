# -*- coding: utf-8 -*-
"""
بوت إنستغرام ديني متكامل:
- رد على السلام مع قائمة الميزات + توقيع المطور
- ردود دينية: أذكار / دعاء / آية / حديث / أسماء الله / قصص
- رد حسب الموضوع (صبر، شكر، توبة...)
- عدّاد التسبيح
- إذكار دورية للمتابعين (أذكار + آية) كل 10 دقائق
- مواقيت الصلاة والتذكير قبل الأذان (عبر api.aladhan.com)
- إرسال يومي للرسائل المحفوظة
"""

import json
import os
import sys
import time
import random
import urllib.request
from datetime import datetime, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from instagrapi import Client

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import religious_data as rd

CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
REPLIED_PATH = os.path.join(BASE_DIR, "replied.json")
STATE_PATH = os.path.join(BASE_DIR, "religious_state.json")

DEFAULT_CONFIG = {
    "session_id": "",
    "reply_text": "وعليكم السلام ورحمة الله وبركاته 🌹",
    "greeting_keywords": [
        "سلام عليكم", "السلام عليكم", "اسلام عليكم",
        "salam", "assalam", "hi", "hello",
    ],
    "check_interval": 10,
    "credit_handle": "j_.8._",
    "show_menu_on_greeting": True,
    "daily_schedule": [
        {"pool": "azkar_sabah", "hour_local": 6, "enabled": True},
        {"pool": "names", "hour_local": 8, "enabled": True},
        {"pool": "hadith", "hour_local": 11, "enabled": True},
        {"pool": "azkar_masaa", "hour_local": 19, "enabled": True},
    ],
    "broadcast_adhkar": {
        "enabled": True,
        "mode": "followers",
        "start_hour": 7,
        "end_hour": 23,
        "delay_between": 600,
        "user_gap_min": 10,
        "batch_size": 10,
        "max_per_day": 200,
        "include_verse": True,
        "prayer_to_followers": True,
        "prayer_interval_min": 150,
    },
    "prayer": {
        "enabled": True,
        "city": "Chlef",
        "country": "Algeria",
        "method": 3,
        "reminder_minutes": 10,
    },
}

TOPIC_WORDS = {
    "صبر": "صبر", "الصبر": "صبر", "مصيبة": "صبر", "مصيبت": "صبر",
    "شكر": "شكر", "الحمد": "شكر",
    "توبة": "توبة", "ذنب": "توبة", "ذنوب": "توبة", "خطيئة": "توبة", "خطايا": "توبة",
    "رزق": "رزق", "الرزق": "رزق", "مال": "رزق", "فقر": "رزق",
    "هموم": "هموم", "ضيق": "هموم", "قلق": "هموم", "حزن": "هموم", "كئيب": "هموم",
    "مرض": "مرض", "عيان": "مرض", "شفاء": "مرض",
    "خوف": "خوف", "وسواس": "خوف", "حصار": "خوف",
    "علم": "علم", "دراسة": "علم", "امتحان": "علم", "الاختبار": "علم",
    "سفر": "سفر", "مسافر": "سفر", "رحلة": "سفر",
    "زواج": "زواج", "تزويج": "زواج", "عريس": "زواج", "عروس": "زواج",
}

# أسماء الصلوات بالعربي
PRAYER_NAMES_AR = {
    "Fajr": "الفجر", "Dhuhr": "الظهر", "Asr": "العصر",
    "Maghrib": "المغرب", "Isha": "العشاء",
}


def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


# ---------------------------------------------------------------- الإعدادات
def safe_input(prompt=""):
    """نفس input لكن آمن في السحاب (لا يوجد شاشة تفاعلية)"""
    try:
        if not sys.stdin or not sys.stdin.isatty():
            return ""
        return input(prompt)
    except (EOFError, KeyboardInterrupt, OSError):
        return ""


def load_config():
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
        log("أنشأت ملف الإعدادات config.json — أدخل الـ Session ثم أعد التشغيل")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    # أدمج المفاتيح الجديدة في إعدادات قديمة
    merged = dict(DEFAULT_CONFIG)
    merged.update({k: v for k, v in cfg.items() if v not in (None, "")})
    cfg = merged
    # في السحاب (Render) الـ Session يأتي من متغير بيئة سري
    sid_env = os.environ.get("IG_SESSION_ID", "").strip()
    if sid_env:
        cfg["session_id"] = sid_env
        log("تم تحميل الـ Session من متغير البيئة (وضع السحاب) 🔒")
    elif not cfg.get("session_id"):
        sid = safe_input("\nالصق الـ Session ID الخاص بحسابك ثم اضغط Enter:\n> ").strip()
        if sid:
            cfg["session_id"] = sid
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            log("تم حفظ الـ Session في config.json")
    return cfg


def load_replied():
    if os.path.exists(REPLIED_PATH):
        try:
            with open(REPLIED_PATH, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()


def save_replied(replied):
    with open(REPLIED_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(replied), f)


def load_state():
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


# ---------------------------------------------------------------- مطابقة النصوص
def matches_greeting(text, keywords):
    t = (text or "").strip().lower()
    return any(k.lower() in t for k in keywords)


def match_religious(text):
    t = (text or "").strip().lower()
    for kw, pool in rd.RELIGIOUS_KEYWORDS.items():
        if kw in t:
            return pool
    return None


def resolve_pool(pool):
    """الأذكار تتفتق صباحاً مساءً حسب ساعة اليوم"""
    if pool == "dhikr":
        return "azkar_masaa" if datetime.now().hour >= 15 else "azkar_sabah"
    return pool


def match_topic(text):
    t = (text or "").strip().lower()
    for kw, topic in TOPIC_WORDS.items():
        if kw in t:
            return topic
    return None


def next_text(pool_key, state):
    arr = rd.POOLS[pool_key]
    i = int(state.get(pool_key + "_i", 0)) % len(arr)
    state[pool_key + "_i"] = (i + 1) % len(arr)
    save_state(state)
    return arr[i]


def credit_line(cfg):
    h = (cfg.get("credit_handle") or "").strip().strip("@")
    if not h:
        return ""
    return f"\n\n🛠 تطوير البوت: @{h} 🌟 تابعوا الحساب الشهير"


def features_menu(cfg):
    lines = [
        "",
        "🤖 أنا بوت إسلامي تلقائي! اكتب لي أي واحدة من هذه:",
        "📿 «أذكار» — ذكر صباحي أو مسائي",
        "🤲 «دعاء» — دعاء جديد كل مرة",
        "📖 «آية» — آية من القرآن الكريم",
        "🌙 «حديث» — حديث شريف بالمصدر",
        "✨ «أسماء الله» — اسم من أسماء الله الحسنى",
        "🌹 «قصة» — من قصص الصحابة والسيرة",
        "💬 «صبر» / «شكر» / «توبة» / «رزق» / «هموم» / «مرض» / «خوف» — رد خاص بالموضوع",
        "🕌 اكتب «سبحان الله» — عدّاد التسبيح يحسب لك!",
    ]
    return "\n".join(lines) + credit_line(cfg)


def due_daily_schedules(cfg, state):
    today = datetime.now().strftime("%Y-%m-%d")
    hour_now = datetime.now().hour
    due = []
    for sch in cfg.get("daily_schedule") or []:
        if not sch.get("enabled", True):
            continue
        pool = sch.get("pool")
        if pool not in rd.POOLS:
            continue
        if state.get("daily_" + pool) == today:
            continue
        if hour_now >= int(sch.get("hour_local", 6)):
            due.append((sch, today))
    return due


# ---------------------------------------------------------------- مواقيت الصلاة
def fetch_prayer_times(city, country, method=3):
    url = (
        "https://api.aladhan.com/v1/timingsByCity"
        f"?city={urllib.request.quote(city)}&country={urllib.request.quote(country)}&method={method}"
    )
    with urllib.request.urlopen(url, timeout=15) as r:
        data = json.loads(r.read().decode("utf-8"))
    d = data.get("data", {})
    timings = d.get("timings", {})
    times = {}
    for k in ("Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"):
        if k in timings:
            times[k] = str(timings[k]).split(" ")[0]
    hij = d.get("date", {}).get("hijri", {})
    hijri = f"{hij.get('day', '')} {hij.get('month', {}).get('ar', '')} {hij.get('year', '')}هـ"
    return times, hijri


def handle_prayer(cl, my_id, pr, state, bc=None, credit="", threads=None):
    """تقرير المواقيت صباحاً + تنبيه قبل كل أذان (لرسائلك المحفوظة)
    + توزيع التقرير على المتابعين مرة واحدة يومياً إذا prayer_to_followers"""
    today = datetime.now().strftime("%Y-%m-%d")
    if state.get("prayer_fail_date") == today:
        return
    times = state.get("prayer_times") or {}
    hijri = state.get("prayer_hijri", "")
    if state.get("prayer_date") != today:
        try:
            times, hijri = fetch_prayer_times(
                pr.get("city", "Algiers"), pr.get("country", "Algeria"), int(pr.get("method", 3))
            )
            state["prayer_date"] = today
            state["prayer_times"] = times
            state["prayer_hijri"] = hijri
            save_state(state)
            log(f"🕌 جلبت مواقيت اليوم ({hijri})")
        except Exception as e:
            state["prayer_fail_date"] = today
            log(f"تعذر جلب مواقيت الصلاة اليوم: {e}")
            save_state(state)
            return
    if not times:
        return

    # 1) تقرير المواقيت مرة واحدة يومياً بعد الفجر؛ لو فات اليوم كله أرسله عند التشغيل
    if state.get("prayer_report_date") != today:
        now_dt = datetime.now()
        fajr_h, fajr_m = (int(x) for x in times.get("Fajr", "4:30").split(":"))
        fajr_dt = now_dt.replace(hour=fajr_h, minute=fajr_m, second=0, microsecond=0)
        lines = [f"🕌 مواقيت الصلاة اليوم — {hijri}"]
        for k, t in times.items():
            lines.append(f"   {PRAYER_NAMES_AR.get(k, k)}: {t}")
        body = "\n".join(lines)
        if now_dt >= fajr_dt - timedelta(hours=2):
            try:
                cl.direct_send(body, [int(my_id)])
                state["prayer_report_date"] = today
                save_state(state)
                log("🕌 أرسل تقرير مواقيت اليوم إلى رسائلك المحفوظة")
            except Exception as e:
                log(f"فشل إرسال تقرير المواقيت: {e}")

    # 2) تنبيه قبل كل أذان بعشر دقائق
    rem = int(pr.get("reminder_minutes", 10))
    now = datetime.now()
    for k, t in times.items():
        try:
            hh, mm = (int(x) for x in t.split(":"))
        except ValueError:
            continue
        adhan = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if not (timedelta(0) <= now - (adhan - timedelta(minutes=rem)) <= timedelta(minutes=2)):
            continue
        key = f"prey_rem_{today}_{k}"
        if state.get(key):
            continue
        try:
            cl.direct_send(
                f"🕌 تنبيه: أذان {PRAYER_NAMES_AR.get(k, k)} بعد {rem} دقيقة تقريباً ({t}) — استعد للصلاة 🌟",
                [int(my_id)],
            )
            state[key] = 1
            save_state(state)
            log(f"🕌 تنبيه أذان {PRAYER_NAMES_AR.get(k, k)} أرسل بنجاح")
        except Exception as e:
            log(f"فشل تنبيه الأذان: {e}")

    # 3) توزيع تقرير المواقيت على المتابعين — مرة كل ساعتين ونصف (interval دقائق)
    if not (bc or {}).get("enabled") or not (bc or {}).get("prayer_to_followers", True):
        return
    lines = [f"🕌 مواقيت الصلاة اليوم — {hijri} 🌟"]
    for k, t in times.items():
        lines.append(f"   {PRAYER_NAMES_AR.get(k, k)}: {t}")
    if credit:
        lines.append(credit.lstrip("\n"))
    report = "\n".join(lines)
    receivers = broadcast_receivers_now(cl, my_id, (bc or {}).get("mode", "followers"), threads)
    if not receivers:
        return
    interval = int((bc or {}).get("prayer_interval_min", 150)) * 60
    now_ts = time.time()
    pr_utime = state.setdefault("pr_utime", {})
    due = [u for u in receivers if now_ts - float(pr_utime.get(u, 0)) >= interval]
    if not due:
        return
    batch = due[:max(1, int((bc or {}).get("batch_size", 10)))]
    for uid in batch:
        try:
            time.sleep(random.uniform(2, 5))
            cl.direct_send(report, [int(uid)])
            pr_utime[uid] = time.time()
            save_state(state)
            log(f"🕌 مواقيت الصلاة أرسلت للمتابع {uid} — التالية بعد {interval // 60} دقيقة")
        except Exception as e:
            log(f"تعذر إرسال المواقيت إلى {uid}: {e}")


# ---------------------------------------------------------------- التوزيع الدوري
_BC_CACHE = {"followers": None, "fetched_at": 0.0, "chats": set()}


def broadcast_receivers_now(cl, my_id, mode, threads):
    now = time.time()
    if mode == "followers":
        if _BC_CACHE["followers"] is None or now - _BC_CACHE["fetched_at"] > 6 * 3600:
            try:
                fl = cl.user_followers(int(my_id), amount=0)
                _BC_CACHE["followers"] = [str(k) for k in fl.keys() if str(k) != my_id]
                _BC_CACHE["fetched_at"] = now
                log(f"👥 جلبت قائمة المتابعين ({len(_BC_CACHE['followers'])} شخص) للإرسال الدوري")
            except Exception as e:
                log(f"تعذر جلب المتابعين: {e}")
                return []
        return list(_BC_CACHE["followers"])
    for t in threads or []:
        for u in getattr(t, "users", []) or []:
            upk = str(getattr(u, "pk", ""))
            if upk and upk != my_id:
                _BC_CACHE["chats"].add(upk)
    return list(_BC_CACHE["chats"])


_BC_FIRST = {"flag": True}


def handle_broadcast(cl, my_id, bc, state, threads, credit):
    """أذكار + آية للمتابعين — دورات حتى delay ثوانٍ، وعند التشغيل مباشرة ترسل للجميع"""
    now = time.time()
    today = datetime.now().strftime("%Y-%m-%d")
    st = state.setdefault("bc", {})
    if st.get("date") != today:
        st["date"] = today
        st["count"] = 0
        st["utime"] = {}
    maxday = int(bc.get("max_per_day", 200))
    if st.get("count", 0) >= maxday:
        return
    first = _BC_FIRST["flag"]
    h = datetime.now().hour
    delay = int(bc.get("delay_between", 600))
    if not first:
        if not (int(bc.get("start_hour", 7)) <= h < int(bc.get("end_hour", 23))):
            return
        if now - float(st.get("last_ts", 0)) < delay:
            return
    receivers = broadcast_receivers_now(cl, my_id, bc.get("mode", "followers"), threads)
    if not receivers:
        return
    utime = st["utime"]
    user_gap = (delay if first else int(bc.get("user_gap_min", 10)) * 60)
    pending = [u for u in receivers if now - float(utime.get(u, 0)) >= user_gap]
    if not pending:
        return
    batch = pending[:max(1, int(bc.get("batch_size", 10)))]
    pool_now = "azkar_masaa" if datetime.now().hour >= 15 else "azkar_sabah"
    seen = st.setdefault("seen_followers", {})
    ok = 0
    for uid in batch:
        try:
            time.sleep(random.uniform(2, 5))
            if not seen.get(uid):
                # 🎉 متابع جديد — رسالة ترحيب خاصة بمحل الأذكار الدوري
                body = (
                    "🕌 أهلاً وسهلاً بك في بوتنا الإسلامي! 🌟\n\n"
                    "من الآن فصاعداً ستصل إليك هنا:\n"
                    "📿 أذكار + آية كل 10 دقائق\n"
                    "🕌 مواقيت الصلاة كل ساعتين ونصف\n\n"
                    "✨ أرسل الحاضر «السلام عليكم» وسأرد عليك فوراً بقائمة كل الميزات\n"
                    "🌿 جرّب أيضاً: دعاء | آية | حديث | صبر | شكر | سبحان الله"
                )
                if credit:
                    body += credit
                cl.direct_send(body, [int(uid)])
                seen[uid] = 1
                st["count"] = int(st.get("count", 0)) + 1
                st["utime"][uid] = time.time()
                ok += 1
                log(f"🎉 رسالة ترحيب للمتابع الجديد {uid}")
                continue
            body = "📿 أذكار اليوم:\n" + next_text(pool_now, state)
            if bc.get("include_verse", True):
                body += "\n\n📖 آية:\n" + next_text("verse", state)
            if credit:
                body += credit
            cl.direct_send(body, [int(uid)])
            st["count"] = int(st.get("count", 0)) + 1
            st["utime"][uid] = time.time()
            ok += 1
            log(f"📿 أذكار + آية للمتابع {uid} ({st['count']}/{maxday})")
        except Exception as e2:
            log(f"تعذر إرسال الأذكار إلى {uid}: {e2}")
    if ok:
        st["last_ts"] = time.time()
        save_state(state)
        log(f"✅ انتهت دورة الإرسال — أرسل {ok} رسالة (الدورة القادمة بعد {delay}ث)")
    _BC_FIRST["flag"] = False


# ---------------------------------------------------------------- البوت
def main():
    print("=" * 60)
    print("  البوت الإسلامي الشامل - يسلم ويرد ويذكر ذكر")
    print("=" * 60)

    cfg = load_config()
    keywords = cfg.get("greeting_keywords") or DEFAULT_CONFIG["greeting_keywords"]
    reply_text = cfg.get("reply_text") or DEFAULT_CONFIG["reply_text"]
    interval = int(cfg.get("check_interval") or 30)
    credit = credit_line(cfg)
    show_menu = bool(cfg.get("show_menu_on_greeting", True))

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
    try:
        cl.login_by_sessionid(cfg["session_id"])
    except Exception as e:
        log(f"فشل الاتصال: {e}")
        log("غالباً الـ Session انتهى. خذ Session ID جديد وضعه في config.json")
        safe_input("\nاضغط Enter للخروج...")
        sys.exit(1)

    me = cl.account_info()
    my_id = str(me.pk)
    log(f"✅ تم الاتصال بنجاح باسم: @{me.username}")

    replied = load_replied()
    try:
        state["device"] = {"device_settings": cl.device_settings, "uuids": cl.uuids}
        if state["device"].get("device_settings"):
            save_state(state)
            log("📱 حفظت هوية الجهاز في الملفات — الجلسات القادمة ستكون موثوقة أكثر")
    except Exception:
        pass
    errors_in_row = 0
    log(f"يبدأ الفحص كل {interval} ثانية — للإيقاف اضغط Ctrl+C")
    log("السلام يقوبان بقائمة الميزات + توقيع المطور ✅")
    log("الميزات: أذكار / دعاء / آية / حديث / أسماء الله / قصص / مواضيع / التسبيح")
    log("دوري: أذكار + آية للمتابعين بكل 10 دقائق + مواقيت الصلاة + الإرسال اليومي")

    while True:
        try:
            # 1) الجدولة اليومية (أذكار/أسماء/أحاديث → الرسائل المحفوظة)
            for sch, today in due_daily_schedules(cfg, state):
                try:
                    txt = "🔔 أذكار وتذكير:\n" + next_text(sch["pool"], state) + credit
                    cl.direct_send(txt, [int(my_id)])
                    state["daily_" + sch["pool"]] = today
                    save_state(state)
                    log(f"📿 أرسلت التذكير اليومي ({sch['pool']}) إلى رسائلك المحفوظة")
                except Exception as e2:
                    log(f"فشل الإرسال اليومي ({sch['pool']}): {e2}")

            # 2) مواقيت الصلاة + تذكير الأذان + توزيع التقرير على المتابعين
            pr = cfg.get("prayer") or {}
            if pr.get("enabled"):
                bc_pr = cfg.get("broadcast_adhkar") or {}
                handle_prayer(cl, my_id, pr, state, bc_pr, credit, threads=None)

            # 3) فحص الرسائل الواردة — الصندوق العادي + طلبات الرسائل (من غير المتابعة المتبادلة)
            threads = cl.direct_threads(amount=20)
            try:
                reqs = cl.direct_requests(amount=20)
                if reqs:
                    log(f"📨 جلبت {len(reqs)} محادثة من طلبات الرسائل (حسابات خارج المتابعة)")
                threads = threads + reqs
            except Exception as e:
                log(f"تعذر جلب طلبات الرسائل: {e}")
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

                body = None
                if matches_greeting(text, keywords):
                    body = reply_text
                    if show_menu:
                        body += "\n" + features_menu(cfg)
                    log(f"رسالة سلام من: {text[:60]!r}")
                elif "سبحان الله" in text:
                    n = int(state.get("tasbih_n", 0)) + 1
                    state["tasbih_n"] = n
                    save_state(state)
                    body = f"📿 سبحان الله وبحمده! تم التسبيح {n} مرة في حسابنا 🌟\nزعجك؟ اكتب: أذكار"
                    log(f"عداد التسبيح زاد: {n} ({text[:40]!r})")
                else:
                    topic = match_topic(text)
                    if topic:
                        d = rd.TOPICS[topic]
                        body = (
                            f"🌿 عن «{topic}»:\n"
                            f"📖 آية: {d['verse']}\n"
                            f"🤲 دعاء: {d['dua']}"
                        )
                    else:
                        pool = resolve_pool(match_religious(text))
                        if pool:
                            body = "📿 " + next_text(pool, state)
                            log(f"طلب إسلامي ({pool}) من: {text[:40]!r}")
                if body is None or msg_id in replied:
                    continue
                # أضف توقيع المطور للرد الديني إن لم يكن قائمة
                if "🛠 تطوير البوت" not in body and credit:
                    body += credit

                targets = [
                    int(str(getattr(u, "pk", "")))
                    for u in (getattr(t, "users", []) or [])
                    if str(getattr(u, "pk", "")) and str(getattr(u, "pk", "")) != my_id
                ]
                if not targets:
                    continue
                time.sleep(random.uniform(1, 2))
                cl.direct_send(body, targets)
                replied.add(msg_id)
                save_replied(replied)
                log(f"✅ تم الرد على رسالة {msg_id} في محادثة {t.id}")

            # 4) التوزيع الدوري: أذكار + آية للمتابعين
            bc = cfg.get("broadcast_adhkar") or {}
            if bc.get("enabled"):
                handle_broadcast(cl, my_id, bc, state, threads, credit)

        except KeyboardInterrupt:
            raise
        except Exception as e:
            errors_in_row += 1
            wait = min(180, interval * errors_in_row * 3)
            log(f"خطأ أثناء الفحص ({errors_in_row} متتالي — انتظار {wait}ث): {e}")
            time.sleep(wait)
            continue
        errors_in_row = 0
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            break

    log("تم الإيقاف. إلى اللقاء!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nتم الإيقاف بواسطة المستخدم.")
    except Exception as e:
        log(f"خطأ غير متوقع: {e}")
        safe_input("اضغط Enter للخروج...")
