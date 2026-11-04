import asyncio
import httpx
from aiohttp import web
import time
import os
import re
import sys
import socket
import struct
import random
import uuid
import json
import jwt as pyjwt
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from colorama import Fore, Style, init

from test import *

KEY = bytes([89, 103, 38, 116, 99, 37, 68, 69, 117, 104, 54, 37, 90, 99, 94, 56])
IV = bytes([54, 111, 121, 90, 68, 114, 50, 50, 69, 51, 121, 99, 104, 106, 77, 37])

API_KEY = "xziko"
API_HOST = "0.0.0.0"
API_PORT = 8564

TEAM_SIZE_MAP = {
    2: 1,
    4: 3,
    5: 4,
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ACCS_FILE = os.path.join(BASE_DIR, "test.txt")
TOKEN_FILE = os.path.join(BASE_DIR, "data.json")

init(autoreset=True)
G = Fore.LIGHTGREEN_EX
Y = Fore.LIGHTYELLOW_EX
W = Fore.WHITE
R = Fore.LIGHTRED_EX
C = Fore.LIGHTCYAN_EX
B = Style.BRIGHT

connected_clients = {}
connected_clients_lock = asyncio.Lock()
TOTAL_ACCOUNTS = 0

client = httpx.AsyncClient(
    verify=False,
    timeout=15.0,
    limits=httpx.Limits(max_connections=300, max_keepalive_connections=150)
)

headers = {
    'User-Agent': 'UnityPlayer/2018.4.12f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)',
    'Connection': 'Keep-Alive',
    'Accept-Encoding': 'gzip',
    'Content-Type': 'application/x-www-form-urlencoded',
    'Expect': '100-continue',
    'X-Unity-Version': '2018.4.12f1',
    'X-GA-SV': '1789535859',
    'X-GA': 'v1 1',
    'ReleaseVersion': 'OB55'
}


class Codec:
    @staticmethod
    def vi(n):
        if n < 0:
            n = (1 << 64) + n
        o = bytearray()
        while True:
            b = n & 0x7F
            n >>= 7
            if n:
                b |= 0x80
            o.append(b)
            if not n:
                break
        return bytes(o)

    @staticmethod
    def rv(bl, i):
        r = 0
        s = 0
        while i < len(bl):
            b = bl[i]
            i += 1
            r |= (b & 0x7F) << s
            if not (b & 0x80):
                break
            s += 7
        return r, i

    @staticmethod
    def enc(fields):
        b = bytearray()
        for k, v in fields.items():
            if isinstance(v, bool):
                b += Codec.vi((k << 3) | 0) + Codec.vi(int(v))
            elif isinstance(v, int):
                b += Codec.vi((k << 3) | 0) + Codec.vi(v)
            elif isinstance(v, str):
                d = v.encode()
                b += Codec.vi((k << 3) | 2) + Codec.vi(len(d)) + d
            elif isinstance(v, (bytes, bytearray)):
                d = bytes(v)
                b += Codec.vi((k << 3) | 2) + Codec.vi(len(d)) + d
        return bytes(b)

    @staticmethod
    def dec(bl):
        f = {}
        i = 0
        n = len(bl)
        while i < n:
            try:
                k, i = Codec.rv(bl, i)
            except Exception:
                break
            if k == 0:
                i += 1
                continue
            fn, wt = k >> 3, k & 7
            try:
                if wt == 0:
                    v, i = Codec.rv(bl, i)
                elif wt == 2:
                    ln, i = Codec.rv(bl, i)
                    if ln < 0 or i + ln > n:
                        break
                    v = bl[i:i + ln]
                    i += ln
                elif wt == 5:
                    if i + 4 > n:
                        break
                    v = bl[i:i + 4]
                    i += 4
                elif wt == 1:
                    if i + 8 > n:
                        break
                    v = bl[i:i + 8]
                    i += 8
                else:
                    i += 1
                    continue
            except Exception:
                i += 1
                continue
            f.setdefault(fn, []).append(v)
        return f


def enc_ae(d, k, iv):
    return AES.new(k, AES.MODE_CBC, iv).encrypt(pad(d, 16))


def dec_ae(d, k, iv):
    try:
        return unpad(AES.new(k, AES.MODE_CBC, iv).decrypt(d), 16)
    except Exception:
        return None


def build_auth(aid, tok, ts, k, iv, reg="ME", typ='OnLine'):
    uh = f"{int(aid):016x}"
    th = f"{int(ts):08x}"
    e = enc_ae(tok.encode(), k, iv).hex()
    ln = f"{len(e) // 2:08x}"
    r = str(reg).upper() if reg else "ME"
    if typ == 'OnLine':
        pre = '7119' if r == 'ME' else ('7114' if r == 'IND' else '7115')
        return f"{pre}{uh}{th}00000000{ln}{e}"
    else:
        pre = '8119' if r == 'ME' else ('8114' if r == 'IND' else '8115')
        return f"{pre}{uh}{th}{ln}{e}"


_DNS_CACHE = {}
_DNS_CACHE_TTL = 300.0


async def resolve_host_cloudflare(hostname):
    if not hostname:
        return hostname
    parts = hostname.split('.')
    if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
        return hostname
    now = time.time()
    if hostname in _DNS_CACHE:
        ip, exp = _DNS_CACHE[hostname]
        if now < exp:
            return ip

    def _query(server_ip):
        s = None
        try:
            tx_id = random.randint(1000, 65535)
            header = struct.pack(">HHHHHH", tx_id, 0x0100, 1, 0, 0, 0)
            qname = b"".join(bytes([len(p)]) + p.encode('ascii') for p in hostname.split('.')) + b"\x00"
            query = header + qname + struct.pack(">HH", 1, 1)
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(1.2)
            s.sendto(query, (server_ip, 53))
            resp, _ = s.recvfrom(1024)
            if len(resp) >= 12:
                ancount = struct.unpack(">H", resp[6:8])[0]
                if ancount > 0:
                    offset = 12 + len(qname) + 4
                    for _ in range(ancount):
                        if offset >= len(resp):
                            break
                        if (resp[offset] & 0xC0) == 0xC0:
                            offset += 2
                        else:
                            while offset < len(resp) and resp[offset] != 0:
                                offset += 1 + resp[offset]
                            offset += 1
                        if offset + 10 > len(resp):
                            break
                        rtype, rclass, ttl, rdlen = struct.unpack(">HHIH", resp[offset:offset + 10])
                        offset += 10
                        if rtype == 1 and rdlen == 4 and offset + 4 <= len(resp):
                            return socket.inet_ntoa(resp[offset:offset + 4])
                        offset += rdlen
        except Exception:
            pass
        finally:
            if s:
                try:
                    s.close()
                except Exception:
                    pass
        return None

    loop = asyncio.get_running_loop()
    ip = await loop.run_in_executor(None, _query, "1.1.1.1")
    if not ip:
        ip = await loop.run_in_executor(None, _query, "1.0.0.1")
    if not ip:
        try:
            info = await loop.getaddrinfo(hostname, None, family=socket.AF_INET)
            if info:
                ip = info[0][4][0]
        except Exception:
            ip = hostname
    if ip:
        _DNS_CACHE[hostname] = (ip, now + _DNS_CACHE_TTL)
    return ip or hostname


def optimize_tcp_socket(sock):
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
    except Exception:
        pass


def mk_major_payload(open_id, access_token, client_version="1.132.13"):
    fields = {
        3: time.strftime("%Y-%m-%d %H:%M:%S"),
        4: "free fire",
        5: 1,
        7: str(client_version),
        8: "Android OS 14 / API-34",
        9: "Handheld",
        10: "Mobilis",
        11: "WIFI",
        12: 1600,
        13: 900,
        14: "240",
        15: "x86-64 SSE3 SSE4.1 SSE4.2 AVX | 2865 | 6",
        16: 5944,
        17: "Adreno (TM) 750",
        18: "OpenGL ES 3.1 v1",
        19: f"Google|{uuid.uuid4()}",
        20: f"{random.randint(1,223)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}",
        21: "ar",
        22: str(open_id),
        23: "4",
        24: "Handheld",
        25: "samsung SM-N9860",
        26: "ME",
        29: str(access_token),
        30: 1,
        41: "Mobilis",
        42: "WIFI",
        57: "7428b253defc164018c604a1ebbfebdf",
        60: 52691,
        61: 48409,
        62: 2519,
        63: 70,
        64: 23306,
        65: 25131,
        66: 50733,
        67: 52691,
        73: 3,
        74: "/data/app/lib/arm64",
        76: 1,
        77: "b8e0cd5e295eee42f5860d3c86e483dd|/data/app/base.apk",
        78: 3,
        79: 2,
        81: "64",
        83: "2019121229",
        85: 3,
        86: "OpenGLES2",
        87: 8191,
        88: 4,
        89: "KqsHT6dXfrd81vpmdClMMxZM3UCc59ys5/2cX5FVcMpI3tlWy8d0r8ZWGSBj+06/cGbBzY3JULeYT1rb5tBtz7+GCis6kpkGPjl2SSoYhrjsQOvA",
        92: 7303,
        93: "android",
        94: "KqsHT6dXfrd81vpmdClMMxZM3UCc59ys5/2cX5FVcMpI3tlWy8d0r8ZWGSBj+06/cGbBzY3JULeYT1rb5tBtz7+GCis6kpkGPjl2SSoYhrjsQOvA",
        95: 111207,
        96: '{"cur_rate":null,"support_etc2":false}',
        97: 1,
        98: 1,
        99: "4",
        100: "4",
        102: b"",
        104: 62270,
        105: 1,
        106: "https://dl.gmc.freefiremobile.com/live/ABHotUpdates/|https://core-gmc.freefiremobile.com/live/ABHotUpdates/|4a0070ac356973792f002e0b25b96c3b",
        107: "c8e41b7a93f02d56e1a94c7b8203f5d1",
    }
    raw = Codec.enc(fields)
    return enc_ae(raw, KEY, IV)


def parse_major(raw):
    for off in range(0, min(200, max(0, len(raw) - 32))):
        f = Codec.dec(raw[off:])
        if 8 in f:
            v = f[8][0]
            if isinstance(v, (bytes, bytearray)) and len(v) > 100 and bytes(v[:3]) == b'eyJ':
                return f
    return None


def parse_ld(raw, k, iv):
    if not raw:
        return None
    for off in range(0, min(64, max(0, len(raw) - 16))):
        d = dec_ae(raw[off:], k, iv)
        if d:
            f = Codec.dec(d)
            if f and (14 in f or 32 in f or 4 in f):
                return f
    for off in range(0, min(64, max(0, len(raw) - 16))):
        f = Codec.dec(raw[off:])
        if f and (14 in f or 32 in f or 4 in f):
            return f
    return None


def load_tokens():
    tk = {}
    if not os.path.exists(TOKEN_FILE):
        return tk
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or ":" not in line:
                    continue
                uid, tok = line.split(":", 1)
                if uid.strip() and tok.strip():
                    tk[uid.strip()] = tok.strip()
    except Exception:
        pass
    return tk


def save_tokens(tk):
    try:
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            for uid, tok in tk.items():
                f.write(f"{uid}:{tok}\n")
    except Exception:
        pass


def read_accs(path):
    if not os.path.exists(path):
        return []
    accs = []
    seen = set()
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = re.split(r'[|:,\s]+', line, maxsplit=1)
            if len(parts) < 2:
                continue
            uid, pwd = parts[0].strip(), parts[1].strip()
            if uid and pwd and uid not in seen:
                seen.add(uid)
                accs.append((uid, pwd))
    return accs


class Net:
    @staticmethod
    async def oauth(u, p):
        url = "https://100067.connect.garena.com/oauth/guest/token/grant"
        hdrs = {
            "Host": "100067.connect.garena.com",
            "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 12; SM-G998B Build/SP1A.210812.016)",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "close"
        }
        data = {
            "uid": u,
            "password": p,
            "response_type": "token",
            "client_type": "2",
            "client_secret": "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3",
            "client_id": "100067"
        }
        for _ in range(5):
            try:
                response = await client.post(url, headers=hdrs, data=data)
                if response.status_code == 200:
                    j = response.json()
                    payload = j.get("data", j)
                    oid = payload.get("open_id")
                    at = payload.get("access_token")
                    if oid and at:
                        return oid, at
                if response.status_code == 429:
                    await asyncio.sleep(1)
                    continue
            except Exception:
                pass
            await asyncio.sleep(0.5)
        return None

    @staticmethod
    async def send_majorlogin(data, release_version, server_url):
        try:
            url = f"{server_url}MajorLogin" if server_url.endswith('/') else f"{server_url}/MajorLogin"
            hdrs = headers.copy()
            hdrs["ReleaseVersion"] = str(release_version)
            r = await client.post(url, headers=hdrs, data=data)
            return r.content if r.status_code == 200 else None
        except Exception:
            return None

    @staticmethod
    async def send_getlogin(data, base_url, token, release_version):
        try:
            url = f"{base_url.rstrip('/')}/GetLoginData"
            host = base_url.split("//")[-1].split("/")[0]
            hdrs = headers.copy()
            hdrs["ReleaseVersion"] = release_version
            hdrs["Authorization"] = f"Bearer {token}"
            hdrs["Host"] = host
            r = await client.post(url, headers=hdrs, data=data)
            return r.content if r.status_code == 200 else None
        except Exception:
            return None


class Sock:
    KA_PACKET = bytes.fromhex("0219")

    @staticmethod
    async def _connect_and_hold(tok_hex, host, port, ready=None):
        resolved = await resolve_host_cloudflare(host)
        rd, wr = await asyncio.open_connection(resolved, int(port))
        raw = wr.get_extra_info('socket')
        if raw:
            optimize_tcp_socket(raw)
        wr.write(bytes.fromhex(tok_hex))
        await wr.drain()
        await asyncio.sleep(0.4)
        try:
            wr.write(Sock.KA_PACKET)
            await asyncio.wait_for(wr.drain(), timeout=3)
        except Exception:
            pass
        if ready is not None:
            ready.set()
        return rd, wr

    @staticmethod
    async def _hold_loop(tok_hex, host, port, ready=None, on_packet=None):
        while True:
            wr = None
            try:
                rd, wr = await Sock._connect_and_hold(tok_hex, host, port, ready)
                if on_packet:
                    try:
                        await on_packet(b"\x00", wr)
                    except Exception:
                        pass
                while True:
                    try:
                        wr.write(Sock.KA_PACKET)
                        await wr.drain()
                    except Exception:
                        break
                    try:
                        d = await asyncio.wait_for(rd.read(9999), timeout=5)
                        if not d:
                            break
                        if on_packet:
                            try:
                                await on_packet(d, wr)
                            except Exception:
                                pass
                    except asyncio.TimeoutError:
                        continue
                    except Exception:
                        break
            except asyncio.CancelledError:
                if wr:
                    try:
                        wr.close()
                        await wr.wait_closed()
                    except Exception:
                        pass
                raise
            except Exception:
                await asyncio.sleep(1)
            finally:
                if wr:
                    try:
                        wr.close()
                        await wr.wait_closed()
                    except Exception:
                        pass

    @staticmethod
    async def chat(tok_hex, host, port, ready, on_packet=None):
        await Sock._hold_loop(tok_hex, host, port, ready, on_packet)

    @staticmethod
    async def keep(tok_hex, host, port, on_packet=None):
        await Sock._hold_loop(tok_hex, host, port, None, on_packet)

    @staticmethod
    async def run(chat_hex, online_hex, func_addr, info_addr, on_packet=None, on_online=None):
        func_ip, func_port = func_addr.split(":")
        info_ip, info_port = info_addr.split(":")
        ready = asyncio.Event()
        t1 = asyncio.create_task(Sock.chat(chat_hex, info_ip, info_port, ready, on_packet))
        await ready.wait()
        await asyncio.sleep(0.5)
        t2 = asyncio.create_task(Sock.keep(online_hex, func_ip, func_port, on_online))
        await asyncio.gather(t1, t2)


class ChatBot:
    def __init__(self, uid, jwt_tok, key, iv):
        self.uid = uid
        self.jwt_tok = jwt_tok
        self.key = key
        self.iv = iv
        self.chat_wr = None
        self.online_wr = None
        self.client_uid = uid
        self.input_msg = ""
        self.lock = asyncio.Lock()
        self.ready = asyncio.Event()
        self._wr_linked = False
        self._online_linked = False

    async def send(self, payload_hex):
        if self.chat_wr is None:
            return False
        try:
            async with self.lock:
                if self.chat_wr.is_closing():
                    return False
                self.chat_wr.write(bytes.fromhex(payload_hex))
                await self.chat_wr.drain()
            return True
        except Exception:
            return False

    async def send_online(self, payload_hex):
        if self.online_wr is None:
            return False
        try:
            async with self.lock:
                if self.online_wr.is_closing():
                    return False
                self.online_wr.write(bytes.fromhex(payload_hex))
                await self.online_wr.drain()
            return True
        except Exception:
            return False

    async def send_text(self, text, target_uid=None):
        if target_uid is None:
            target_uid = self.client_uid or self.uid
        if not target_uid:
            return False
        try:
            pkt = xMsgPr(text, 2, target_uid, target_uid, self.key, self.iv)
            return await self.send(pkt.hex())
        except Exception:
            return False

    async def process_packet(self, raw):
        try:
            hexfull = raw.hex()
            if len(hexfull) < 20:
                return
            packet = None
            for offset in [10, 8, 12, 6, 14, 16, 0]:
                if offset >= len(hexfull):
                    continue
                try:
                    decoded = DeCode_PackEt(hexfull[offset:])
                    if decoded:
                        test_packet = json.loads(decoded)
                        if '5' in test_packet and 'data' in test_packet['5']:
                            packet = test_packet
                            break
                except Exception:
                    continue
            if packet is None:
                return
            data5 = packet['5']['data']
            if not isinstance(data5, dict):
                return
            sender_uid = None
            if '1' in data5 and isinstance(data5['1'], dict) and 'data' in data5['1']:
                try:
                    sender_uid = int(data5['1']['data'])
                except Exception:
                    pass
            if sender_uid and sender_uid == self.uid:
                return
            msg = None
            if '8' in data5:
                msg = 'InPuT_sTarT'
            elif '4' in data5 and isinstance(data5['4'], dict) and 'data' in data5['4']:
                msg = data5['4']['data']
            elif '3' in data5 and isinstance(data5['3'], dict) and 'data' in data5['3']:
                msg = data5['3']['data']
            elif '6' in data5 and isinstance(data5['6'], dict) and 'data' in data5['6']:
                msg = data5['6']['data']
            if not msg or not isinstance(msg, str):
                return
            if msg.startswith('[b][c]') or msg.startswith('[b][c]['):
                return
            self.input_msg = msg
            await self.handle_command(msg, reply_to=sender_uid)
        except Exception:
            pass

    async def handle_command(self, msg, reply_to=None):
        if reply_to is None:
            reply_to = self.uid
        self.client_uid = reply_to
        try:
            if msg.startswith('InPuT_sTarT') or msg in ("@start", "@help", "welcome", "hi", "start", "/start", "bot", "/bot", "help", "/help"):
                await self.send_text("""[b][c][FFFFFF]Team Bot

[0dff9a]@2x uid
[FFFFFF]Create 2-player team + invite

[0dff9a]@4x uid
[FFFFFF]Create 4-player team + invite

[0dff9a]@5x uid
[FFFFFF]Create 5-player team + invite
""")
                return

            m = re.match(r'^@([245])x\b', msg)
            if m:
                cmd = int(m.group(1))
                parts = msg.split(None, 1)
                if len(parts) < 2 or not parts[1].strip():
                    await self.send_text(f'[b][c][FF0000]Use: @{cmd}x target_uid')
                    return
                target_uid = parts[1].strip().split()[0]
                if not target_uid.isdigit():
                    await self.send_text('[b][c][FF0000]Invalid uid')
                    return
                proto_value = TEAM_SIZE_MAP.get(cmd, 3)
                try:
                    pkt = CreateTeam(self.key, self.iv, region="ME",
                                     game_version="1.132.13", team_size=proto_value)
                    if not await self.send_online(pkt.hex()):
                        await self.send_text('[b][c][FF0000]Create team failed')
                        return
                    await asyncio.sleep(2.0)
                    await self.send_online(TeamFresh(self.uid, self.key, self.iv).hex())
                    await asyncio.sleep(1.0)
                    pkt3 = AddPlayerToTeam(target_uid, self.key, self.iv)
                    if await self.send_online(pkt3.hex()):
                        await self.send_text(f'[b][c][99FF99]Team @{cmd}x + Invited {target_uid}')
                    else:
                        await self.send_text('[b][c][FF0000]Invite failed')
                    await asyncio.sleep(5.0)
                    await self.send_online(Exit('000000', self.key, self.iv).hex())
                    await self.send_text('[b][c][99FF99]Left team')
                except Exception as e:
                    await self.send_text(f'[b][c][FF0000]Error: {e}')
                return

        except Exception:
            pass


async def handle_account(uid_in, pass_in):
    try:
        auth = await Net.oauth(uid_in, pass_in)
        if not auth:
            return
        open_id, access_token = auth

        payload = mk_major_payload(open_id, access_token, "1.132.13")

        login_raw = await Net.send_majorlogin(payload, "OB55", "https://loginbp.ppmainecoonghj.com")
        if not login_raw:
            return

        f = parse_major(login_raw)
        if not f:
            return

        try:
            jwt_tok = f[8][0].decode()
            dj = pyjwt.decode(jwt_tok, options={"verify_signature": False})
            acc_id = int(dj.get("account_id"))
            server_time = int(f[21][0]) if 21 in f else int(time.time()) * 1_000_000_000
            try:
                aes_key = bytes(f[22][0])
                aes_iv = bytes(f[23][0])
                if len(aes_key) != 16 or len(aes_iv) != 16:
                    raise Exception()
            except Exception:
                aes_key, aes_iv = KEY, IV
            server_url = f[10][0].decode() if 10 in f else "https://loginbp.ppmainecoonghj.com/"
            region = f[26][0].decode() if 26 in f else "ME"
        except Exception:
            return

        set_session(aes_key, aes_iv, region, "1.132.13")

        try:
            saved_all = load_tokens()
            saved_all[str(uid_in)] = jwt_tok
            save_tokens(saved_all)
        except Exception:
            pass

        data = await Net.send_getlogin(payload, server_url, jwt_tok, "OB55")
        if not data:
            return

        g = parse_ld(data, aes_key, aes_iv)
        if not g:
            return

        func = None
        info = None
        if 14 in g:
            try:
                func = g[14][0].decode()
            except Exception:
                pass
        if 32 in g:
            try:
                info = g[32][0].decode()
            except Exception:
                pass

        if not func or not info:
            return

        online_hex = build_auth(acc_id, jwt_tok, server_time, aes_key, aes_iv, reg=region, typ='OnLine')
        chat_hex = build_auth(acc_id, jwt_tok, server_time, aes_key, aes_iv, reg=region, typ='ChaT')

        bot = ChatBot(acc_id, jwt_tok, aes_key, aes_iv)

        async with connected_clients_lock:
            if acc_id in connected_clients:
                existing = connected_clients[acc_id]
                if existing.chat_wr is not None and not existing.chat_wr.is_closing():
                    return
            connected_clients[acc_id] = bot

        async def on_packet(raw, wr):
            if not bot._wr_linked or bot.chat_wr is None or bot.chat_wr.is_closing():
                bot.chat_wr = wr
                if not bot._wr_linked:
                    bot._wr_linked = True
            if raw and len(raw) > 1:
                await bot.process_packet(raw)

        async def on_online_packet(raw, wr):
            if not bot._online_linked or bot.online_wr is None or bot.online_wr.is_closing():
                bot.online_wr = wr
                if not bot._online_linked:
                    bot._online_linked = True

        await Sock.run(chat_hex, online_hex, func, info, on_packet, on_online_packet)

    except Exception:
        pass


async def get_online_bot():
    async with connected_clients_lock:
        for bot in connected_clients.values():
            if bot.online_wr is not None and not bot.online_wr.is_closing():
                return bot
    return None


async def do_create_team_invite(target_uid, cmd=5):
    bot = await get_online_bot()
    if not bot:
        return False, "No online bot available"

    proto_value = TEAM_SIZE_MAP.get(cmd, 3)

    try:
        pkt = CreateTeam(bot.key, bot.iv, region="ME",
                         game_version="1.132.13", team_size=proto_value)
        if not await bot.send_online(pkt.hex()):
            return False, "Create team failed"

        await asyncio.sleep(2.0)
        await bot.send_online(TeamFresh(bot.uid, bot.key, bot.iv).hex())
        await asyncio.sleep(1.0)

        pkt3 = AddPlayerToTeam(target_uid, bot.key, bot.iv)
        if not await bot.send_online(pkt3.hex()):
            return False, "Invite failed"

        await asyncio.sleep(5.0)
        await bot.send_online(Exit("000000", bot.key, bot.iv).hex())
        return True, f"Team /{cmd} (proto={proto_value}) created + Invited {target_uid}"
    except Exception as e:
        return False, str(e)


def check_api_key(request):
    key = request.query.get("api_key") or request.headers.get("X-API-Key")
    return key == API_KEY


async def _handle_team_api(request, cmd):
    if not check_api_key(request):
        return web.json_response({"ok": False, "error": "Invalid api_key"}, status=401)
    uid = request.query.get("uid", "").strip()
    if not uid or not uid.isdigit():
        return web.json_response({"ok": False, "error": "uid required (digits only)"}, status=400)
    ok, msg = await do_create_team_invite(uid, cmd=cmd)
    return web.json_response(
        {"ok": ok, "cmd": f"/{cmd}", "proto_value": TEAM_SIZE_MAP.get(cmd), "message": msg},
        status=200 if ok else 500
    )


async def api_2(request):
    return await _handle_team_api(request, 2)


async def api_4(request):
    return await _handle_team_api(request, 4)


async def api_5(request):
    return await _handle_team_api(request, 5)


async def api_status(request):
    if not check_api_key(request):
        return web.json_response({"ok": False, "error": "Invalid api_key"}, status=401)
    async with connected_clients_lock:
        total = len(connected_clients)
        online = sum(
            1 for b in connected_clients.values()
            if b.online_wr is not None and not b.online_wr.is_closing()
        )
    return web.json_response({"ok": True, "total_bots": total, "online_bots": online})


async def start_api_server():
    app = web.Application()
    app.router.add_get("/2", api_2)
    app.router.add_get("/4", api_4)
    app.router.add_get("/5", api_5)
    app.router.add_get("/status", api_status)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, API_HOST, API_PORT)
    await site.start()

    print(f"{G}{B}API Online => http://{API_HOST}:{API_PORT}{W}")
    for n in (2, 4, 5):
        proto = TEAM_SIZE_MAP.get(n)
        print(f"{C}  /{n}?uid=PLAYER_UID&api_key={API_KEY}   (proto={proto}){W}")
    print(f"{C}  /status?api_key={API_KEY}{W}")
    print()


async def main():
    global TOTAL_ACCOUNTS
    os.system('cls' if os.name == 'nt' else 'clear')
    accs = read_accs(ACCS_FILE)
    if not accs:
        print(f"{R}{B}test.txt not found{W}")
        return
    TOTAL_ACCOUNTS = len(accs)

    print(f"{R}{B}Starting...{W}", end="\r", flush=True)

    for u, p in accs:
        asyncio.create_task(handle_account(u, p))

    for _ in range(30):
        async with connected_clients_lock:
            total_online = len(connected_clients)
        if total_online >= TOTAL_ACCOUNTS:
            break
        await asyncio.sleep(1)

    async with connected_clients_lock:
        total_online = len(connected_clients)

    sys.stdout.write("\033[K")
    sys.stdout.write("\r")
    sys.stdout.flush()

    print(f"{G}{B}Total bots online => {W}{total_online}{W}")
    print()

    await start_api_server()

    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass