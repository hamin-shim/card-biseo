#!/usr/bin/env python3
"""카드 결제 SMS 감시 — launchd가 하루 2회(00:00, 12:00) 실행. 해당 반나절 구간 신규 거래만 반영."""

import json
import os
import re
import sqlite3
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_JSON = BASE_DIR / "data.json"
STATE_FILE = BASE_DIR / ".watch_state.json"
ENV_FILE = BASE_DIR / ".env"
DB_PATH = Path.home() / "Library/Messages/chat.db"

CARD_SENDERS = {
    "+8215888900": "삼성카드",
    "+82220008100": "삼성카드",
    "+8215881688": "KB국민카드",
    "+8215447000": "신한카드",
    "+8215880700": "롯데카드",
}

CARD_ID_MAP = {
    "삼성카드": "samsung-sfc7",
    "KB국민카드": "kb-toktok",
    "롯데카드": "lotte-dept",
    "신한카드": "shinhan-deepdream",
    "MG체크카드": "mg-better",
}

TELEGRAM_CHAT_ID = "8517100993"


def load_env():
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def tg_send(text: str):
    token = os.environ.get("BOT_TOKEN", "")
    if not token:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": text}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"[텔레그램 전송 실패] {e}")


def decode_attributed_body(blob: bytes) -> str:
    try:
        decoded = blob.decode("utf-8", errors="ignore")
        idx = decoded.find("+")
        if idx >= 0:
            raw = decoded[idx + 2:]
            parts = re.findall(r"[\uAC00-\uD7A3\u0020-\u007E\n]+", raw)
            return " ".join(p for p in parts if len(p.strip()) > 1)
    except Exception:
        pass
    return ""


def parse_sms(text: str) -> dict | None:
    m = re.search(
        r"삼성(\d+)승인\s+\S+\s+([\d,]+)원\s+\S+\s+(\d{2}/\d{2}\s+\d{2}:\d{2})\s+(.+?)\s+누적([\d,]+)원", text)
    if m:
        return {"card_name": "삼성카드", "card_last4": m.group(1),
                "amount": int(m.group(2).replace(",", "")), "merchant": m.group(4).strip(),
                "datetime_str": m.group(3), "is_foreign": False,
                "cumulative": int(m.group(5).replace(",", "")), "currency": "KRW"}

    m = re.search(
        r"삼성(\d+)해외승인\s+\S+\s+([A-Z]{3})\s+([\d.]+)\s+(\d{2}/\d{2}\s+\d{2}:\d{2})\s+(.+?)(?:\s+iI|$)", text)
    if m:
        return {"card_name": "삼성카드", "card_last4": m.group(1),
                "amount": float(m.group(3)), "merchant": m.group(5).strip(),
                "datetime_str": m.group(4), "is_foreign": True,
                "cumulative": None, "currency": m.group(2)}

    m = re.search(
        r"KB국민카드(\d+)승인\s+\S+\s+([\d,]+)원\s+\S+\s+(\d{2}/\d{2}\s+\d{2}:\d{2})\s+(.+?)\s+누적([\d,]+)원", text)
    if m:
        return {"card_name": "KB국민카드", "card_last4": m.group(1),
                "amount": int(m.group(2).replace(",", "")), "merchant": m.group(4).strip(),
                "datetime_str": m.group(3), "is_foreign": False,
                "cumulative": int(m.group(5).replace(",", "")), "currency": "KRW"}

    m = re.search(
        r"SR\s+([\d,]+)원\s+승인\s+\S+\s+(.+?)\((\S+)\)\s+\S+,\s+(\d{2}/\d{2}\s+\d{2}:\d{2})", text)
    if m:
        return {"card_name": "롯데카드", "card_last4": m.group(3),
                "amount": int(m.group(1).replace(",", "")), "merchant": m.group(2).strip(),
                "datetime_str": m.group(4), "is_foreign": False,
                "cumulative": None, "currency": "KRW"}
    return None


def half_day_window() -> tuple[datetime, datetime]:
    """현재 시각 기준 해당 반나절 구간(KST) 반환."""
    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst)
    if now_kst.hour < 12:
        start = now_kst.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now_kst.replace(hour=12, minute=0, second=0, microsecond=0)
    else:
        start = now_kst.replace(hour=12, minute=0, second=0, microsecond=0)
        end = now_kst.replace(hour=23, minute=59, second=59, microsecond=0)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def to_cocoa(dt: datetime) -> int:
    cocoa_epoch = datetime(2001, 1, 1, tzinfo=timezone.utc)
    return int((dt - cocoa_epoch).total_seconds() * 1_000_000_000)


def fetch_transactions(start_utc: datetime, end_utc: datetime) -> list[dict]:
    if not DB_PATH.exists():
        print(f"[오류] Messages DB 없음: {DB_PATH}")
        return []

    cocoa_epoch = datetime(2001, 1, 1, tzinfo=timezone.utc)
    placeholders = ",".join("?" * len(CARD_SENDERS))
    query = f"""
        SELECT h.id, m.text, m.attributedBody, m.date
        FROM message m JOIN handle h ON m.handle_id = h.ROWID
        WHERE h.id IN ({placeholders}) AND m.date >= ? AND m.date <= ?
        ORDER BY m.date ASC
    """
    try:
        conn = sqlite3.connect(str(DB_PATH))
        rows = conn.execute(query, list(CARD_SENDERS.keys()) + [to_cocoa(start_utc), to_cocoa(end_utc)]).fetchall()
        conn.close()
    except Exception as e:
        print(f"[DB 오류] {e}")
        return []

    results = []
    for sender, text, ab, cocoa_ts in rows:
        body = text or (decode_attributed_body(bytes(ab)) if ab else "")
        parsed = parse_sms(body)
        if not parsed:
            continue
        try:
            kst = timezone(timedelta(hours=9))
            dt_kst = (cocoa_epoch + timedelta(microseconds=cocoa_ts / 1000)).astimezone(kst)
            parsed["received_at"] = dt_kst.strftime("%Y-%m-%d %H:%M")
            parsed["date"] = dt_kst.strftime("%Y-%m-%d")
        except Exception:
            parsed["received_at"] = None
            parsed["date"] = datetime.now().strftime("%Y-%m-%d")
        parsed["cocoa_ts"] = cocoa_ts
        results.append(parsed)
    return results


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"seen_keys": []}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False))


def update_data_json(txn: dict):
    data = json.loads(DATA_JSON.read_text()) if DATA_JSON.exists() else {"이번달사용": [], "지난달실적": {}, "이번달혜택사용": {}}
    card_id = CARD_ID_MAP.get(txn["card_name"], txn["card_name"])
    is_foreign = txn.get("is_foreign", False)
    currency = txn.get("currency", "KRW")

    if is_foreign:
        # 해외결제: amount를 원화 합계에서 제외하기 위해 0 저장, memo에 외화 금액 기록
        amount = 0
        category = "해외결제"
        memo = f"{txn['merchant']} ({currency} {txn['amount']}) (자동감지)"
    else:
        amount = int(txn["amount"])
        category = "기타"
        memo = f"{txn['merchant']} (자동감지)"
        if txn.get("cumulative"):
            memo += f" / 누적 {txn['cumulative']:,}원"

    data.setdefault("이번달사용", []).append({
        "date": txn["date"], "cardId": card_id,
        "amount": amount, "category": category, "memo": memo,
    })
    DATA_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def git_push_data_json():
    import subprocess
    try:
        subprocess.run(["git", "add", "data.json"], cwd=BASE_DIR, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "data: 카드 결제 자동 반영"], cwd=BASE_DIR, check=True, capture_output=True)
        subprocess.run(["git", "push"], cwd=BASE_DIR, check=True, capture_output=True)
        print("  [git push 완료]")
    except subprocess.CalledProcessError as e:
        print(f"  [git push 실패] {e.stderr.decode() if e.stderr else e}")


def make_notification(txn: dict) -> str:
    amt_str = f"{txn['currency']} {txn['amount']}" if txn.get("is_foreign") else f"{int(txn['amount']):,}원"
    msg = f"✅ {txn['card_name']} 결제 반영됨\n금액: {amt_str}\n가맹점: {txn['merchant']}"
    if txn.get("received_at"):
        msg += f"\n시각: {txn['received_at']}"
    return msg


def main():
    load_env()
    start_utc, end_utc = half_day_window()
    kst = timezone(timedelta(hours=9))
    print(f"[{datetime.now(kst):%Y-%m-%d %H:%M}] 구간 확인: {start_utc.astimezone(kst):%H:%M} ~ {end_utc.astimezone(kst):%H:%M}")

    state = load_state()
    seen_keys = set(state.get("seen_keys", []))

    txns = fetch_transactions(start_utc, end_utc)
    new_count = 0

    for txn in txns:
        key = f"{txn['card_name']}|{txn['amount']}|{txn['merchant']}|{txn['datetime_str']}"
        if key in seen_keys:
            continue
        print(f"  [신규] {txn['card_name']} {int(txn['amount']):,} {txn['merchant']}")
        update_data_json(txn)
        tg_send(make_notification(txn))
        seen_keys.add(key)
        new_count += 1

    save_state({"seen_keys": list(seen_keys)[-500:]})
    if new_count > 0:
        git_push_data_json()
    else:
        kst = timezone(timedelta(hours=9))
        now_str = datetime.now(kst).strftime("%m/%d %H:%M")
        tg_send(f"📋 [{now_str}] 새 결제 내역 없음 (0건)")
    print(f"  완료: {len(txns)}건 조회, {new_count}건 신규 반영")


if __name__ == "__main__":
    main()
