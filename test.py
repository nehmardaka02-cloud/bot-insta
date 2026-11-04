import json
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

Key = bytes([89, 103, 38, 116, 99, 37, 68, 69, 117, 104, 54, 37, 90, 99, 94, 56])
Iv  = bytes([54, 111, 121, 90, 68, 114, 50, 50, 69, 51, 121, 99, 104, 106, 77, 37])

CUR_KEY = Key
CUR_IV  = Iv
CUR_REGION = "ME"


def set_session(key=None, iv=None, region=None, version=None):
    global CUR_KEY, CUR_IV, CUR_REGION
    if key and len(key) == 16:
        CUR_KEY = bytes(key)
    if iv and len(iv) == 16:
        CUR_IV = bytes(iv)
    if region:
        CUR_REGION = str(region).upper()


def get_session():
    return CUR_KEY, CUR_IV


def EnC_PacKeT(HeX, K, V):
    return AES.new(K, AES.MODE_CBC, V).encrypt(pad(bytes.fromhex(HeX), 16)).hex()


def EnC_Vr(N):
    if N < 0:
        N = (1 << 64) + N
    H = []
    while True:
        BesTo = N & 0x7F
        N >>= 7
        if N:
            BesTo |= 0x80
        H.append(BesTo)
        if not N:
            break
    return bytes(H)


def CrEaTe_VarianT(field_number, value):
    field_header = (field_number << 3) | 0
    return EnC_Vr(field_header) + EnC_Vr(value)


def CrEaTe_LenGTh(field_number, value):
    field_header = (field_number << 3) | 2
    encoded_value = value.encode() if isinstance(value, str) else value
    return EnC_Vr(field_header) + EnC_Vr(len(encoded_value)) + encoded_value


def CrEaTe_ProTo(fields):
    packet = bytearray()
    for field, value in fields.items():
        if isinstance(value, dict):
            nested_packet = CrEaTe_ProTo(value)
            packet.extend(CrEaTe_LenGTh(field, nested_packet))
        elif isinstance(value, int):
            packet.extend(CrEaTe_VarianT(field, value))
        elif isinstance(value, (str, bytes)):
            packet.extend(CrEaTe_LenGTh(field, value))
    return packet


def DecodE_HeX(H):
    R = hex(H)
    F = str(R)[2:]
    if len(F) == 1:
        F = "0" + F
    return F


def GeneRaTePk(Pk, N, K, V):
    PkEnc = EnC_PacKeT(Pk, K, V)
    _ = DecodE_HeX(int(len(PkEnc) // 2))
    if len(_) == 2:
        HeadEr = N + "000000"
    elif len(_) == 3:
        HeadEr = N + "00000"
    elif len(_) == 4:
        HeadEr = N + "0000"
    elif len(_) == 5:
        HeadEr = N + "000"
    else:
        HeadEr = N + "000000"
    return bytes.fromhex(HeadEr + _ + PkEnc)


def CreateTeam(key, iv, region="ME", game_version="1.132.13", team_size=3):
    fields = {
        1: 1,
        2: {
            2: bytes.fromhex("01"),
            3: 1,
            4: int(team_size),
            5: "en",
            8: {1: "IDC3", 2: 123, 3: region},
            9: 1,
            10: bytes.fromhex("01090a0b1219202729"),
            11: 2,
            13: 1,
            14: {
                1: "08FBA33B4BABE2790205390333330000009700050092005F72697EB2134DCBB2467625142201040e38e848dc0e748c3f6aa04d81000000ff1113090dcacfa16d",
                2: 478,
                3: "7e585d55",
                4: "y[Z]",
                6: 12,
                7: "15686677735a7506101c",
                8: str(game_version),
                9: 3,
                10: 1,
                11: "03626253513637754174"
            },
            19: 329,
            21: bytes.fromhex("374f521955"),
            24: {1: 21},
            27: "a_6534489873065906362"
        }
    }
    return GeneRaTePk(CrEaTe_ProTo(fields).hex(), "0515", key, iv)


def TeamFresh(account_id, key, iv):
    fields = {1: 72, 2: {1: int(account_id)}}
    return GeneRaTePk(CrEaTe_ProTo(fields).hex(), "0515", key, iv)


def AddPlayerToTeam(target_uid, key, iv, region="ME"):
    fields = {1: 2, 2: {1: int(target_uid), 2: region, 4: 1}}
    return GeneRaTePk(CrEaTe_ProTo(fields).hex(), "0515", key, iv)


def Exit(idT, K, V):
    fields = {1: 7, 2: {1: idT}}
    return GeneRaTePk(CrEaTe_ProTo(fields).hex(), "0515", K, V)


def xMsgPr(Msg, Tp, Tp2, id, K, V):
    fields = {
        1: int(Tp),
        2: {1: int(id), 2: int(Tp2), 3: str(Msg), 4: 1, 5: int(id)}
    }
    return GeneRaTePk(CrEaTe_ProTo(fields).hex(), "1215", K, V)


def _V(b, i):
    r = s = 0
    while True:
        c = b[i]
        i += 1
        r |= (c & 0x7F) << s
        if c < 0x80:
            break
        s += 7
    return r, i


def PrOtO(hx):
    b, i, R = bytes.fromhex(hx), 0, {}
    while i < len(b):
        H, i = _V(b, i)
        F, T = H >> 3, H & 7
        if T == 0:
            R[F], i = _V(b, i)
        elif T == 2:
            L, i = _V(b, i)
            S = b[i:i + L]
            i += L
            try:
                R[F] = S.decode()
            except:
                try:
                    R[F] = PrOtO(S.hex())
                except:
                    R[F] = S
        elif T == 5:
            R[F] = int.from_bytes(b[i:i + 4], 'little')
            i += 4
        else:
            break
    return R


try:
    from protobuf_decoder.protobuf_decoder import Parser
    _HAS_PB = True
except ImportError:
    _HAS_PB = False
    class Parser:
        def parse(self, data):
            raise ImportError("protobuf_decoder not installed")


def Fix_PackEt(parsed_results):
    result_dict = {}
    for result in parsed_results:
        field_data = {}
        field_data['wire_type'] = result.wire_type
        if result.wire_type == "varint":
            field_data['data'] = result.data
        if result.wire_type == "string":
            field_data['data'] = result.data
        if result.wire_type == "bytes":
            field_data['data'] = result.data
        elif result.wire_type == 'length_delimited':
            field_data["data"] = Fix_PackEt(result.data.results)
        result_dict[result.field] = field_data
    return result_dict


def DeCode_PackEt(input_text):
    if _HAS_PB:
        try:
            parsed_results = Parser().parse(input_text)
            parsed_results_dict = Fix_PackEt(parsed_results)
            return json.dumps(parsed_results_dict)
        except Exception:
            pass
    try:
        result = PrOtO(input_text)

        def convert(obj):
            if isinstance(obj, dict):
                out = {}
                for k, v in obj.items():
                    if isinstance(v, dict):
                        out[str(k)] = {"data": convert(v), "wire_type": "length_delimited"}
                    elif isinstance(v, (str, bytes)):
                        out[str(k)] = {"data": v if isinstance(v, str) else v.decode(errors="ignore"), "wire_type": "string"}
                    else:
                        out[str(k)] = {"data": v, "wire_type": "varint"}
                return out
            return obj

        return json.dumps(convert(result))
    except Exception:
        return None