"""迅雷网盘（token 认证 + 验证码盾 + 转存取直链）。"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import random
import time
import urllib.parse

from ..link_parser import parse_share
from ..models import ApiError, DownloadLink, PanFile, Platform, ShareSession
from ..net import api_request
from ..util import app_data_dir
from .base import Logger, PanClient

AUTH_BASE = "https://xluser-ssl.xunlei.com"
PAN_BASE = "https://api-pan.xunlei.com"

CLIENT_ID = "Xp6vsxz_7IYVw2BB"
CLIENT_SECRET = "Xp6vsy4tN9toTVdMSpomVdXpRmES"
CLIENT_VERSION = "8.31.0.9726"
PACKAGE_NAME = "com.xunlei.downloadprovider"

APP_UA = (
    "ANDROID-com.xunlei.downloadprovider/8.31.0.9726 netWorkType/5G appid/40 "
    "deviceName/Xiaomi_M2004j7ac deviceModel/M2004J7AC OSVersion/12 protocolVersion/301 "
    "platformVersion/10 sdkVersion/512000 Oauth2Client/0.9 (Linux 4_14_186-perf-gddfs8vbb238b) (JAVA 0)"
)
WEB_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
TEMP_DIR_NAME = "亦析临时转存"

CAPTCHA_SALTS = [
    "9uJNVj/wLmdwKrJaVj/omlQ",
    "Oz64Lp0GigmChHMf/6TNfxx7O9PyopcczMsnf",
    "Eb+L7Ce+Ej48u",
    "jKY0",
    "ASr0zCl6v8W4aidjPK5KHd1Lq3t+vBFf41dqv5+fnOd",
    "wQlozdg6r1qxh0eRmt3QgNXOvSZO6q/GXK",
    "gmirk+ciAvIgA/cxUUCema47jr/YToixTT+Q6O",
    "5IiCoM9B1/788ntB",
    "P07JH0h6qoM6TSUAK2aL9T5s2QBVeY9JWvalf",
    "+oK0AN",
]

HEX = "0123456789abcdef"
_DEVICE_FILE = os.path.join(app_data_dir(), "xunlei_device.json")
APP_KEY = "34a062aaa22f906fca4fefe9fb3a3021"
APP_ID = "40"


def _md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _load_device() -> dict:
    """设备指纹（device_id / peer_id / devicesign），首次生成后持久化复用。"""
    try:
        with open(_DEVICE_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if data.get("device_id") and data.get("peer_id") and data.get("device_sign"):
            return data
    except (OSError, ValueError):
        pass
    device_id = "".join(random.choice(HEX) for _ in range(32))
    peer_id = "".join(random.choice(HEX) for _ in range(32))
    device_sign = "div101." + device_id + _md5(_sha1(device_id + PACKAGE_NAME + APP_ID + APP_KEY))
    data = {"device_id": device_id, "peer_id": peer_id, "device_sign": device_sign}
    try:
        with open(_DEVICE_FILE, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    except OSError:
        pass
    return data


def _load_device_id() -> str:
    return _load_device()["device_id"]


def _login_base_body(device_id: str, client_version: str, sdk_version: str, credit_key: str = "") -> dict:
    device = _load_device()
    return {
        "protocolVersion": "301",
        "sequenceNo": str(random.randint(10000000, 99999999)),
        "platformVersion": "10",
        "isCompressed": "0",
        "appid": APP_ID,
        "clientVersion": client_version,
        "peerID": device["peer_id"],
        "appName": "ANDROID-com.xunlei.downloadprovider",
        "sdkVersion": sdk_version,
        "devicesign": device["device_sign"],
        "netWorkType": "WIFI",
        "providerName": "NONE",
        "deviceModel": "M2004J7AC",
        "deviceName": "Xiaomi_M2004j7ac",
        "OSVersion": "12",
        "creditkey": credit_key,
        "hl": "zh-CN",
    }


SDK_UA = "android-ok-http-client/xl-acc-sdk/version-5.0.12.512000"
LOGIN_UA = "android-ok-http-client/xl-acc-sdk/version-5.1.3.513006"


def _parse_login(data: dict) -> dict:
    error_code = str(data.get("errorCode") or "")
    if error_code == "0" or data.get("error") == "success":
        session_id = data.get("sessionID", "") or ""
        if not session_id:
            return {"ok": False, "message": "登录成功但未返回会话，请重试"}
        return {
            "ok": True,
            "session_id": session_id,
            "nickname": data.get("nickName", "") or "",
            "user_id": data.get("userID", "") or "",
            "message": "登录成功",
        }
    error = data.get("error") or ""
    verify_type = str(data.get("verifyType") or "")
    need_sms = error == "review_panel" or error_code == "1007" or bool(verify_type)
    message = (
        data.get("errorDesc")
        or data.get("error_description")
        or error
        or "登录失败"
    )
    return {"ok": False, "need_sms": need_sms, "message": message}


def login_with_password(username: str, password: str, device_id: str, check_code: str = "") -> dict:
    """账号密码登录；触发风控时返回 need_sms=True。"""
    body = _login_base_body(device_id, "25.0.5.25", "513006")
    body.update(
        {
            "userName": username,
            "passWord": password,
            "verifyKey": "",
            "verifyCode": check_code,
            "isMd5Pwd": "0",
        }
    )
    resp = api_request(
        "POST",
        f"{AUTH_BASE}/xluser.core.login/v3/login",
        headers={"User-Agent": LOGIN_UA, "Content-Type": "application/json"},
        data=json.dumps(body),
    )
    try:
        data = resp.json() or {}
    except ValueError:
        return {"ok": False, "message": f"登录接口返回异常（HTTP {resp.status_code}）"}
    return _parse_login(data)


def login_captcha_token(device_id: str, username: str = "", user_id: str = "") -> str:
    """登录用验证码盾初始化，返回 captcha_token（换 token 时要放请求头）。"""
    ts = str(int(time.time() * 1000))
    body = {
        "action": "POST:/auth/signin/token",
        "captcha_token": "",
        "client_id": CLIENT_ID,
        "device_id": device_id,
        "meta": {
            "username": username,
            "client_version": CLIENT_VERSION,
            "package_name": PACKAGE_NAME,
            "timestamp": ts,
            "captcha_sign": build_captcha_sign(device_id, ts),
            "user_id": user_id,
        },
        "redirect_uri": "xlaccsdk01://xunlei.com/callback?state=harbor",
    }
    try:
        resp = api_request(
            "POST",
            f"{AUTH_BASE}/v1/shield/captcha/init",
            headers={
                "User-Agent": APP_UA,
                "Accept": "application/json;charset=UTF-8",
                "Content-Type": "application/json",
                "X-Client-Id": CLIENT_ID,
                "X-Device-Id": device_id,
                "X-Client-Version": CLIENT_VERSION,
            },
            data=json.dumps(body),
        )
        return (resp.json() or {}).get("captcha_token", "") or ""
    except Exception:  # noqa: BLE001
        return ""


def send_sms_code(mobile: str, device_id: str) -> dict:
    """发送短信验证码，返回 {ok, message, credit_key, token}。"""
    body = _login_base_body(device_id, CLIENT_VERSION, "231500")
    body.update({"mobile": mobile, "register": "0"})
    resp = api_request(
        "POST",
        f"{AUTH_BASE}/xluser.core.login/v3/sendsms",
        headers={"User-Agent": SDK_UA, "Content-Type": "application/json"},
        data=json.dumps(body),
    )
    data = resp.json() or {}
    ok = str(data.get("errorCode") or "0") == "0"
    message = data.get("errorDesc") or data.get("error_description") or data.get("error") or ""
    return {
        "ok": ok,
        "message": message or ("短信已发送" if ok else "发送失败"),
        "credit_key": data.get("creditkey", "") or "",
        "token": data.get("token", "") or "",
    }


def sms_login(mobile: str, code: str, credit_key: str, sms_token: str, device_id: str) -> dict:
    """用短信验证码登录，成功返回 {ok, session_id, message}。"""
    body = _login_base_body(device_id, CLIENT_VERSION, "231500", credit_key)
    body.update({"mobile": mobile, "smsCode": code, "token": sms_token, "register": "0"})
    resp = api_request(
        "POST",
        f"{AUTH_BASE}/xluser.core.login/v3/smslogin",
        headers={"User-Agent": SDK_UA, "Content-Type": "application/json"},
        data=json.dumps(body),
    )
    try:
        data = resp.json() or {}
    except ValueError:
        return {"ok": False, "message": f"登录接口返回异常（HTTP {resp.status_code}）"}
    result = _parse_login(data)
    if not result.get("ok") and not result.get("message"):
        result["message"] = "验证码错误或已过期"
    return result


def exchange_access_token(session_id: str, device_id: str, captcha_token: str, user_id: str = "") -> dict:
    """用 sessionID 换取 access_token / refresh_token。"""
    body = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "provider": "access_end_point_token",
        "signin_token": session_id,
    }
    headers = {
        "User-Agent": APP_UA,
        "Accept": "application/json;charset=UTF-8",
        "Content-Type": "application/json",
        "X-Client-Id": CLIENT_ID,
        "X-Device-Id": device_id,
        "X-Client-Version": CLIENT_VERSION,
    }
    if captcha_token:
        headers["X-Captcha-Token"] = captcha_token
    resp = api_request(
        "POST",
        f"{AUTH_BASE}/v1/auth/signin/token",
        headers=headers,
        data=json.dumps(body),
    )
    data = resp.json() or {}
    access = data.get("access_token") or data.get("accessToken") or ""
    refresh = data.get("refresh_token") or data.get("refreshToken") or ""
    if not access:
        message = (
            data.get("error_description")
            or data.get("message")
            or data.get("error")
            or f"换取 token 失败（HTTP {resp.status_code}）"
        )
        return {"ok": False, "message": message}
    return {"ok": True, "access_token": access, "refresh_token": refresh, "message": "登录成功"}


# --------------------------------------------------------------------------
# 扫码 / 网页登录（OAuth 设备码流程，官方网页确认授权）
# --------------------------------------------------------------------------
#: 网页客户端 ID（pan.xunlei.com 自己用）。注意：它签发的 token 不能用于下载接口——
#: 服务端要求验证码的 client_id 与 token 一致，而网页客户端的验签算法是混淆的、无法复现。
WEB_CLIENT_ID = "Xqp0kJBXWhwaTpB6"
#: 网页授权页同样接受安卓客户端 ID，用它换到的 token 才能配我们生成的验证码，
#: 因此网页登录统一走这个 client。
OAUTH_CLIENT_ID = CLIENT_ID
WEB_AUTHORIZE_PAGE = "https://i.xunlei.com/center/account/personal/oauth/"
WEB_REDIRECT_URI = "https://pan.xunlei.com/login/?sso_sign_in_in_iframe="
WEB_SCOPE = "profile offline pan sso user"
WEB_SIGN_OUT_URI = "https://pan.xunlei.com/login/?sso_sign_out="


def make_pkce() -> tuple[str, str]:
    """生成 PKCE 的 code_verifier / code_challenge（S256）。"""
    verifier = base64.urlsafe_b64encode(os.urandom(48)).decode().rstrip("=")
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


def build_authorize_url(challenge: str, state: str) -> str:
    """网页登录的授权页地址（在窗口里打开它，用户自己登录）。"""
    query = urllib.parse.urlencode(
        {
            "client_id": OAUTH_CLIENT_ID,
            "redirect_uri": WEB_REDIRECT_URI,
            "scope": WEB_SCOPE,
            "state": state,
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "sign_out_uri": WEB_SIGN_OUT_URI,
        }
    )
    return f"{WEB_AUTHORIZE_PAGE}?{query}"


def exchange_authorization_code(code: str, code_verifier: str) -> dict:
    """用授权码换 access_token / refresh_token（网页登录的最后一步）。"""
    body = {
        "grant_type": "authorization_code",
        "client_id": OAUTH_CLIENT_ID,
        "code": code,
        "redirect_uri": WEB_REDIRECT_URI,
        "code_verifier": code_verifier,
    }
    try:
        resp = api_request(
            "POST",
            f"{AUTH_BASE}/v1/auth/token",
            headers={
                "User-Agent": WEB_UA,
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json",
                "Origin": "https://pan.xunlei.com",
                "Referer": "https://pan.xunlei.com/",
            },
            data=json.dumps(body),
        )
        data = resp.json() or {}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "message": f"换取凭证失败：{exc}"}
    access = data.get("access_token") or data.get("accessToken") or ""
    if access:
        return {
            "ok": True,
            "access_token": access,
            "refresh_token": data.get("refresh_token") or data.get("refreshToken") or "",
            "message": "登录成功",
        }
    return {
        "ok": False,
        "message": data.get("error_description") or data.get("error") or "换取凭证失败",
    }


def request_device_code() -> dict:
    """申请设备码，返回 verification_uri_complete / user_code / device_code 等。"""
    device_id = _load_device_id()
    captcha = login_captcha_token(device_id, "")
    body = {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "scope": ""}
    resp = api_request(
        "POST",
        f"{AUTH_BASE}/v1/auth/device/code",
        headers={
            "User-Agent": APP_UA,
            "Accept": "application/json;charset=UTF-8",
            "Content-Type": "application/json",
            "X-Client-Id": CLIENT_ID,
            "X-Device-Id": device_id,
            "X-Client-Version": CLIENT_VERSION,
            "X-Captcha-Token": captcha,
        },
        data=json.dumps(body),
    )
    data = resp.json() or {}
    if not data.get("device_code"):
        raise ApiError(
            data.get("error_description") or "申请设备码失败，请稍后重试"
        )
    data["interval"] = max(2, int(data.get("interval") or 2))
    data["expires_in"] = int(data.get("expires_in") or 120)
    return data


def poll_device_token(device_code: str) -> dict:
    """轮询设备码授权结果。

    返回 {ok, pending, access_token, refresh_token, message}；
    pending=True 表示用户还没完成授权。
    """
    device_id = _load_device_id()
    body = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "device_code": device_code,
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
    }
    try:
        resp = api_request(
            "POST",
            f"{AUTH_BASE}/v1/auth/token",
            headers={
                "User-Agent": APP_UA,
                "Accept": "application/json;charset=UTF-8",
                "Content-Type": "application/json",
                "X-Client-Id": CLIENT_ID,
                "X-Device-Id": device_id,
                "X-Client-Version": CLIENT_VERSION,
            },
            data=json.dumps(body),
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "pending": True, "message": f"网络错误：{exc}"}
    try:
        data = resp.json() or {}
    except ValueError:
        return {"ok": False, "pending": True, "message": f"接口返回异常（HTTP {resp.status_code}）"}
    access = data.get("access_token") or data.get("accessToken") or ""
    if access:
        return {
            "ok": True,
            "pending": False,
            "access_token": access,
            "refresh_token": data.get("refresh_token") or data.get("refreshToken") or "",
            "message": "登录成功",
        }
    error = data.get("error") or ""
    if error in ("authorization_pending", "slow_down"):
        return {"ok": False, "pending": True, "message": "等待授权"}
    return {
        "ok": False,
        "pending": False,
        "message": data.get("error_description") or error or "授权失败",
    }


def build_captcha_sign(device_id: str, ts_ms: str) -> str:
    value = CLIENT_ID + CLIENT_VERSION + PACKAGE_NAME + device_id + ts_ms
    for salt in CAPTCHA_SALTS:
        value = _md5(value + salt)
    return "1." + value


def jwt_claims(token: str) -> dict:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload).decode("utf-8", "ignore"))
    except Exception:  # noqa: BLE001
        return {}


class XunleiClient(PanClient):
    platform = Platform.XUNLEI
    cred_kind = "token"
    cred_title = "access_token"
    cred_help = (
        "推荐：点下方「网页登录」，在弹出的官方页面里登录并确认授权"
        "（可用迅雷 App 扫码），程序会自动拿到 access_token 与 refresh_token"
        "（token 过期会自动续期）。\n\n"
        "如果网页登录不方便，也可以点「账号密码登录」，"
        "用迅雷账号 + 密码登录，触发风控时会自动走短信验证码。\n\n"
        "手动方式：已有 access_token 的话也可以直接粘贴到这里。"
    )

    def __init__(self) -> None:
        super().__init__()
        self.device_id = _load_device_id()
        self.access_token = ""
        self.refresh_token = ""
        #: action -> captcha_token（迅雷的验证码按动作绑定，不能混用）
        self._captcha_tokens: dict[str, str] = {}
        self._user_id = ""

    # -- 凭证 ---------------------------------------------------------------
    def check_credential(self, credential: str) -> str | None:
        self.access_token = self.require_credential(credential)
        claims = jwt_claims(self.access_token)
        self._user_id = str(claims.get("sub") or "")
        if not self._user_id:
            raise ApiError("无法解析 access_token，请确认粘贴的是迅雷网盘的登录 token")
        # 用一个轻量 pan 接口验证
        self._ensure_captcha("GET:/drive/v1/about")
        payload = self._pan_request(f"{PAN_BASE}/drive/v1/about", "GET:/drive/v1/about")
        nickname = ((payload.get("data") or {}).get("user") or {}).get("name")
        return nickname or self._user_id

    def token_expired(self) -> bool:
        exp = jwt_claims(self.access_token).get("exp") or 0
        try:
            exp = float(exp)
        except (TypeError, ValueError):
            return True
        return exp > 0 and exp - time.time() < 120

    # -- 短信验证码登录（与安卓版同一套官方接口） -----------------------------
    def password_login(self, username: str, password: str) -> dict:
        """账号密码登录；返回 need_sms=True 表示需要短信验证码。"""
        self.device_id = _load_device_id()
        return login_with_password(username, password, self.device_id)

    def begin_sms_login(self, mobile: str) -> dict:
        """发送短信验证码。"""
        self.device_id = _load_device_id()
        return send_sms_code(mobile, self.device_id)

    def complete_sms_login(
        self, mobile: str, code: str, credit_key: str, sms_token: str
    ) -> dict:
        """校验验证码并换取 access_token / refresh_token。"""
        device_id = _load_device_id()
        step = sms_login(mobile, code, credit_key, sms_token, device_id)
        if not step.get("ok"):
            return step
        captcha = login_captcha_token(device_id, mobile, step.get("user_id", ""))
        result = exchange_access_token(
            step["session_id"], device_id, captcha, step.get("user_id", "")
        )
        return self._apply_tokens(result, step.get("nickname", ""), step.get("user_id", ""))

    def complete_password_login(self, username: str, password: str) -> dict:
        """账号密码登录（若直接成功则直接换取 token）。"""
        device_id = _load_device_id()
        step = login_with_password(username, password, device_id)
        if not step.get("ok"):
            return step
        captcha = login_captcha_token(device_id, username, step.get("user_id", ""))
        result = exchange_access_token(
            step["session_id"], device_id, captcha, step.get("user_id", "")
        )
        return self._apply_tokens(result, step.get("nickname", ""), step.get("user_id", ""))

    def _apply_tokens(self, result: dict, nickname: str = "", user_id: str = "") -> dict:
        if result.get("ok"):
            self.access_token = result["access_token"]
            self.refresh_token = result.get("refresh_token") or ""
            self.refreshed_credential = self.access_token
            if user_id:
                self._user_id = user_id
            result["nickname"] = nickname or result.get("nickname") or ""
        return result

    def refresh_access_token(self) -> bool:
        if not self.refresh_token:
            return False
        body = urllib.parse.urlencode(
            {
                "grant_type": "refresh_token",
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "refresh_token": self.refresh_token,
            }
        )
        try:
            resp = api_request(
                "POST",
                f"{AUTH_BASE}/v1/auth/token",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "X-Device-Id": self.device_id,
                },
                data=body,
            )
            data = resp.json()
        except Exception:  # noqa: BLE001
            return False
        access = data.get("access_token") or data.get("accessToken")
        if not access:
            return False
        self.access_token = access
        self.refresh_token = data.get("refresh_token") or data.get("refreshToken") or self.refresh_token
        self.refreshed_credential = access
        self._user_id = str(jwt_claims(access).get("sub") or self._user_id)
        self._captcha_tokens.clear()
        return True

    # -- 验证码盾 -----------------------------------------------------------
    def _ensure_captcha(self, action: str, force: bool = False) -> None:
        """按 action 申请 captcha_token。

        关键：迅雷的 X-Captcha-Token 与「动作」绑定，不同接口（列表 / 详情 /
        转存 / 删除…）必须各自申请，复用会报「验证码无效」。
        """
        if not force and self._captcha_tokens.get(action):
            return
        ts = str(int(time.time() * 1000))
        body = {
            "client_id": CLIENT_ID,
            "action": action,
            "device_id": self.device_id,
            "redirect_uri": "xlaccsdk01://xunlei.com/callback?state=harbor",
            "meta": {
                "client_version": CLIENT_VERSION,
                "package_name": PACKAGE_NAME,
                "timestamp": ts,
                "captcha_sign": build_captcha_sign(self.device_id, ts),
                "user_id": self._user_id,
            },
        }
        try:
            resp = api_request(
                "POST",
                f"{AUTH_BASE}/v1/shield/captcha/init",
                headers={
                    "User-Agent": APP_UA,
                    "Accept": "application/json;charset=UTF-8",
                    "Content-Type": "application/json",
                    "X-Client-Id": CLIENT_ID,
                    "X-Device-Id": self.device_id,
                    "X-Client-Version": CLIENT_VERSION,
                },
                data=json.dumps(body),
            )
            data = resp.json()
        except Exception:  # noqa: BLE001
            return
        token = data.get("captcha_token")
        if token:
            self._captcha_tokens[action] = token

    def _captcha_for(self, action: str) -> str:
        self._ensure_captcha(action)
        return self._captcha_tokens.get(action, "")

    def verify_pan_access(self) -> None:
        """确认该 token 真能调用 pan 接口。

        服务端要求 X-Captcha-Token 的 client_id 与 access_token 一致；
        网页客户端签发的 token 会在这里被拒（网页客户端验签算法是混淆的，无法复现）。
        """
        self._pan_request(
            f"{PAN_BASE}/drive/v1/files?parent_id=&limit=1",
            "GET:/drive/v1/files",
        )

    # -- Pan 请求 -----------------------------------------------------------
    def _pan_request(
        self,
        url: str,
        action: str,
        method: str = "GET",
        body: dict | None = None,
        retry: bool = True,
    ) -> dict:
        captcha = self._captcha_for(action)
        headers = {
            "User-Agent": WEB_UA,
            "Authorization": f"Bearer {self.access_token}",
            "X-Device-Id": self.device_id,
            "X-Client-Version": CLIENT_VERSION,
            "Content-Type": "application/json",
            "Origin": "https://pan.xunlei.com",
            "Referer": "https://pan.xunlei.com/",
        }
        if captcha:
            headers["X-Captcha-Token"] = captcha
        kwargs = {"headers": headers}
        if body is not None or method in ("POST", "PATCH"):
            kwargs["data"] = json.dumps(body if body is not None else {})
        resp = api_request(method, url, **kwargs)
        try:
            payload = resp.json()
        except ValueError:
            raise ApiError(f"接口返回异常（HTTP {resp.status_code}）")
        if resp.status_code >= 400 or payload.get("error"):
            error = payload.get("error") or ""
            if retry and (resp.status_code == 401 or error == "unauthenticated"):
                if self.refresh_access_token():
                    return self._pan_request(url, action, method, body, retry=False)
            if retry and error == "captcha_invalid":
                self._ensure_captcha(action, force=True)
                return self._pan_request(url, action, method, body, retry=False)
            if error == "captcha_invalid":
                aud = str(jwt_claims(self.access_token).get("aud") or "")
                if aud and aud != CLIENT_ID:
                    raise ApiError(
                        "该凭证来自迅雷网页客户端，不能用于下载接口。"
                        "请到「账号与凭证 → 迅雷网盘」重新点「网页登录」登录一次。"
                    )
            message = (
                payload.get("error_description")
                or payload.get("message")
                or error
                or f"请求失败（HTTP {resp.status_code}）"
            )
            raise ApiError(message)
        return payload

    # -- 分享解析 -----------------------------------------------------------
    def open_session(self, link: str, pwd: str | None, credential: str) -> ShareSession:
        self.access_token = self.require_credential(credential)
        self._user_id = str(jwt_claims(self.access_token).get("sub") or "")
        parsed = parse_share(link)
        if parsed is None:
            raise ApiError("无法识别迅雷分享链接")
        passcode = (pwd or "").strip() or (parsed.pwd or "")
        page = self._share_page(parsed.share_id, passcode)
        return ShareSession(
            share_id=parsed.share_id,
            token=page.get("pass_code_token") or "",
            title=page.get("title") or "",
            extra={"passcode": passcode},
        )

    def _share_page(
        self,
        share_id: str,
        passcode: str,
        parent_id: str = "",
        pass_code_token: str = "",
        page_token: str = "",
    ) -> dict:
        if parent_id:
            url = (
                f"{PAN_BASE}/drive/v1/share/detail?"
                + urllib.parse.urlencode(
                    {
                        "share_id": share_id,
                        "parent_id": parent_id,
                        "pass_code_token": pass_code_token,
                        "limit": "100",
                        "page_token": page_token,
                        "thumbnail_size": "SIZE_SMALL",
                    }
                )
            )
            action = "GET:/drive/v1/share/detail"
        else:
            url = (
                f"{PAN_BASE}/drive/v1/share?"
                + urllib.parse.urlencode(
                    {
                        "share_id": share_id,
                        "pass_code": passcode,
                        "limit": "100",
                        "page_token": page_token,
                        "thumbnail_size": "SIZE_SMALL",
                    }
                )
            )
            action = "GET:/drive/v1/share"
        payload = self._pan_request(url, action)
        data = payload.get("data") or {}
        status = data.get("share_status")
        if status == "PASS_CODE_EMPTY":
            raise ApiError("请输入提取码")
        if status == "PASS_CODE_ERROR":
            raise ApiError("提取码错误")
        if status == "PASS_CODE_NEED":
            raise ApiError("该分享需要提取码")
        return data

    def list_files(self, session: ShareSession, dir_id: str, credential: str) -> list[PanFile]:
        files: list[PanFile] = []
        page_token = ""
        parent_id = "" if dir_id in ("", "0", None) else dir_id
        for _ in range(100):
            data = self._share_page(
                session.share_id,
                session.extra.get("passcode", ""),
                parent_id=parent_id,
                pass_code_token=session.token,
                page_token=page_token,
            )
            files.extend(self._parse_files(data.get("files") or []))
            page_token = data.get("next_page_token") or ""
            if not page_token:
                break
        return files

    @staticmethod
    def _parse_files(items: list) -> list[PanFile]:
        result = []
        for item in items:
            kind = item.get("kind") or ""
            result.append(
                PanFile(
                    fid=str(item.get("id") or ""),
                    name=item.get("name") or "",
                    size=int(item.get("size") or 0),
                    is_dir="folder" in kind,
                    parent_fid=str(item.get("parent_id") or ""),
                    modify_time=str(item.get("modified_time") or ""),
                )
            )
        return result

    # -- 转存 / 取链 ---------------------------------------------------------
    def _list_cloud(self, parent_id: str = "") -> list[PanFile]:
        url = (
            f"{PAN_BASE}/drive/v1/files?"
            + urllib.parse.urlencode(
                {"parent_id": parent_id, "limit": "100", "thumbnail_size": "SIZE_SMALL"}
            )
        )
        payload = self._pan_request(url, "GET:/drive/v1/files")
        return self._parse_files((payload.get("data") or {}).get("files") or [])

    def _ensure_temp_dir(self) -> str:
        for item in self._list_cloud():
            if item.is_dir and item.name == TEMP_DIR_NAME:
                return item.fid
        payload = self._pan_request(
            f"{PAN_BASE}/drive/v1/files",
            "POST:/drive/v1/files",
            method="POST",
            body={
                "kind": "drive#folder",
                "name": TEMP_DIR_NAME,
                "parent_id": "",
                "space": "",
            },
        )
        folder_id = (payload.get("data") or {}).get("id")
        if not folder_id:
            raise ApiError("创建临时目录失败")
        return folder_id

    def _restore(self, session: ShareSession, file: PanFile, parent_id: str) -> str:
        payload = self._pan_request(
            f"{PAN_BASE}/drive/v1/share/restore",
            "POST:/drive/v1/share/restore",
            method="POST",
            body={
                "share_id": session.share_id,
                "pass_code_token": session.token,
                "parent_id": parent_id,
                "ancestor_ids": [],
                "file_ids": [file.fid],
                "specify_parent_id": True,
            },
        )
        data = payload.get("data") or {}
        trace = ((data.get("params") or {}).get("trace_file_ids")) or ""
        if trace:
            try:
                mapping = json.loads(trace)
                new_id = mapping.get(file.fid)
                if new_id:
                    return new_id
            except ValueError:
                pass
        new_id = data.get("file_id")
        if not new_id:
            raise ApiError("转存失败：未返回新文件标识")
        return new_id

    def _file_detail(self, file_id: str) -> DownloadLink:
        url = (
            f"{PAN_BASE}/drive/v1/files/{file_id}?_magic=2021&usage=PLAY"
            "&thumbnail_size=SIZE_LARGE&with=hdr10&with=subtitle_files&with=task&with=public_share_tag"
        )
        payload = self._pan_request(url, f"GET:/drive/v1/files/{file_id}")
        data = payload.get("data") or {}
        links = data.get("links") or {}
        url_str = ((links.get("application/octet-stream") or {}).get("url")) or data.get(
            "web_content_link"
        )
        if not url_str:
            raise ApiError("未返回下载直链")
        return DownloadLink(
            url=url_str,
            filename=data.get("name") or "",
            size=int(data.get("size") or 0),
        )

    def _batch_delete(self, ids: list[str]) -> None:
        if not ids:
            return
        try:
            self._pan_request(
                f"{PAN_BASE}/drive/v1/files:batchDelete",
                "POST:/drive/v1/files:batchDelete",
                method="POST",
                body={"ids": ids, "space": ""},
            )
        except Exception:  # noqa: BLE001
            pass

    def fetch_download(
        self,
        session: ShareSession,
        file: PanFile,
        credential: str,
        log: Logger | None = None,
    ) -> DownloadLink:
        self.access_token = self.refreshed_credential or self.require_credential(credential)
        self._user_id = str(jwt_claims(self.access_token).get("sub") or self._user_id)
        self._log(log, "  转存到临时目录…")
        temp_dir = self._ensure_temp_dir()
        new_id = self._restore(session, file, temp_dir)
        self._log(log, "  获取下载直链…")
        link = self._file_detail(new_id)
        link.filename = link.filename or file.name
        self._batch_delete([new_id])
        return link

    def download_headers(self, credential: str) -> dict[str, str]:
        return {"User-Agent": APP_UA}
