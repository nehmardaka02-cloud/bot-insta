# -*- coding: utf-8 -*-
"""
نقطة الدخول للسحابة (Render):
- يفتح سيرفر HTTP صغير يحافظ على الخدمة حيّة (Keep-alive)
  أي زيارة لرابط الخدمة = استجابة "البوت حي" → Render لا يطفئه
  (استخدم UptimeRobot ليزور الرابط كل 5 دقائق)
- ثم يشغّل البوت كاملاً في نفس العملية
الـ Session يؤتى بمتغير البيئة: IG_SESSION_ID
"""

import os
import sys
import threading
import http.server
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_BOT_START = datetime.now()
STATUS = {"last_beat": _BOT_START.strftime("%Y-%m-%d %H:%M:%S"),
          "errors": 0}


class StatusHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = (
            "🤖 البوت الإسلامي يعمل الآن على Render!"
            f"\nتشغيل منذ: {_BOT_START:%Y-%m-%d %H:%M:%S} UTC"
            f"\nآخر نبضة: {STATUS['last_beat']}"
            f"\nأخطاء متتالية أخيرة: {STATUS['errors']}"
            f"\n\n🛠 تطوير: @j_.8._"
        )
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_HEAD(self):
        # UptimeRobot يفحص بطلبات HEAD — نجيب بـ 200 حتى لا تسجل حادثة كاذبة
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()

    def do_POST(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()

    def log_message(self, fmt, *args):
        pass  # صمت عن سجلات الزيارات المتكررة


def start_http():
    port = int(os.environ.get("PORT", "10000"))
    with http.server.ThreadingHTTPServer(("0.0.0.0", port), StatusHandler) as srv:
        print(f"[HTTP] سيرفر النبض شغّال على المنفذ {port}", flush=True)
        srv.serve_forever()


if __name__ == "__main__":
    print("=" * 60, flush=True)
    print("  البوت الإسلامي - وضع السحابة (Render)", flush=True)
    print("=" * 60, flush=True)
    t = threading.Thread(target=start_http, daemon=True)
    t.start()
    import bot
    bot.STATUS_REF = STATUS  # لو أراد البوت تحديث الحالة مستقبلاً
    bot.main()
