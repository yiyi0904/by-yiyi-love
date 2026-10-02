"""扫码登录授权页（我们自己渲染，用于迅雷设备码登录）。"""

from __future__ import annotations


def qr_data_uri(text: str) -> str:
    """把文本生成二维码 data URI；失败返回空串。"""
    if not text:
        return ""
    try:
        import base64
        import io

        import qrcode

        image = qrcode.make(text)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
    except Exception:  # noqa: BLE001
        return ""


_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<title>亦析 · 扫码登录</title>
<style>
  html, body { height:100%; margin:0; background:#101219; color:#e9edf7;
    font-family:"Microsoft YaHei UI","Microsoft YaHei",sans-serif; }
  .wrap { max-width:620px; margin:0 auto; padding:34px 24px; text-align:center; }
  h1 { font-size:20px; margin:0 0 6px; }
  .sub { color:#98a1b8; font-size:13px; margin-bottom:22px; }
  .card { background:#171a23; border:1px solid #2b3142; border-radius:12px; padding:26px; }
  .qr { width:236px; height:236px; background:#fff; border-radius:10px; padding:10px; }
  .qr-fallback { display:flex; align-items:center; justify-content:center;
    color:#333; font-size:13px; line-height:1.6; margin:0 auto; }
  .code { margin-top:18px; font-size:15px; color:#98a1b8; }
  .code b { display:inline-block; margin-top:6px; font-size:24px; letter-spacing:2px;
    color:#4b8cff; font-family:Consolas,monospace; background:#12151d;
    border:1px solid #2b3142; border-radius:8px; padding:8px 18px; user-select:all; }
  ol { text-align:left; color:#98a1b8; font-size:13px; line-height:1.9;
    margin:22px 0 0; padding-left:22px; }
  ol b { color:#e9edf7; }
  .tip { margin-top:18px; font-size:12px; color:#6c7488; line-height:1.7; }
</style>
</head>
<body>
<div class="wrap">
  <h1>__TITLE__</h1>
  <div class="sub">__SUBTITLE__</div>
  <div class="card">
    __QR__
    <div class="code">授权码<b>__CODE__</b></div>
    <ol>
      __STEPS__
    </ol>
    <div class="tip">__TIP__</div>
  </div>
</div>
</body>
</html>
"""


def device_page(info: dict, title: str, subtitle: str, steps: str, tip: str) -> str:
    """渲染设备码授权页。"""
    code = info.get("user_code") or ""
    scan_url = (
        info.get("short_uri_complete")
        or info.get("verification_uri_complete")
        or info.get("verification_url")
        or ""
    )
    qr = qr_data_uri(scan_url)
    if qr:
        qr_block = f'<img class="qr" src="{qr}" alt="二维码"/>'
    else:
        qr_block = '<div class="qr qr-fallback">无法生成二维码<br/>请使用下方授权码</div>'
    return (
        _TEMPLATE.replace("__TITLE__", title)
        .replace("__SUBTITLE__", subtitle)
        .replace("__QR__", qr_block)
        .replace("__CODE__", code)
        .replace("__STEPS__", steps)
        .replace("__TIP__", tip)
    )
