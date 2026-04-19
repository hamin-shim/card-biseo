#!/usr/bin/env python3
"""카드 승인 SMS MCP 서버 — macOS Messages DB(chat.db) 읽기"""

import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

DB_PATH = Path.home() / "Library/Messages/chat.db"

# 카드사 발신번호 → 카드사명 (승인 문자 전용)
CARD_SENDERS = {
    "+8215888900": "삼성카드",
    "+82220008100": "삼성카드",   # 해외승인
    "+8215881688": "KB국민카드",
    "+8215447000": "신한카드",
    "+8215880700": "롯데카드",
}

def decode_attributed_body(blob: bytes) -> str:
    """NSAttributedString BLOB에서 순수 텍스트 추출."""
    try:
        decoded = blob.decode("utf-8", errors="ignore")
        idx = decoded.find("+")
        if idx >= 0:
            raw = decoded[idx + 2:]
            parts = re.findall(r"[\uAC00-\uD7A3\u0020-\u007E\n]+", raw)
            return " ".join(p for p in parts if len(p.strip()) > 1)
        return ""
    except Exception:
        return ""


def _parse_samsung(text: str) -> Optional[dict]:
    """삼성카드 국내/해외 승인 파싱."""
    # 국내: 삼성7056승인 심*민 4,910원 일시불 10/04 17:15 지에스더프레 누적804,173원
    m = re.search(
        r"삼성(\d+)승인\s+\S+\s+([\d,]+)원\s+\S+\s+(\d{2}/\d{2}\s+\d{2}:\d{2})\s+(.+?)\s+누적([\d,]+)원",
        text,
    )
    if m:
        return {
            "card_name": "삼성카드",
            "card_last4": m.group(1),
            "amount": int(m.group(2).replace(",", "")),
            "merchant": m.group(4).strip(),
            "datetime_str": m.group(3),
            "is_foreign": False,
            "cumulative": int(m.group(5).replace(",", "")),
            "currency": "KRW",
        }
    # 해외: 삼성7056해외승인 심*민 USD 22.00 04/16 22:54 OPENAI*CHATGPTSUBSCR
    m = re.search(
        r"삼성(\d+)해외승인\s+\S+\s+([A-Z]{3})\s+([\d.]+)\s+(\d{2}/\d{2}\s+\d{2}:\d{2})\s+(.+?)(?:\s+iI|$)",
        text,
    )
    if m:
        return {
            "card_name": "삼성카드",
            "card_last4": m.group(1),
            "amount": float(m.group(3)),
            "merchant": m.group(5).strip(),
            "datetime_str": m.group(4),
            "is_foreign": True,
            "cumulative": None,
            "currency": m.group(2),
        }
    return None


def _parse_kb(text: str) -> Optional[dict]:
    """KB국민카드 승인 파싱.
    KB국민카드1000승인 심*민님 143,500원 일시불 04/16 10:49 (주)비바리퍼블리카 누적209,910원
    """
    m = re.search(
        r"KB국민카드(\d+)승인\s+\S+\s+([\d,]+)원\s+\S+\s+(\d{2}/\d{2}\s+\d{2}:\d{2})\s+(.+?)\s+누적([\d,]+)원",
        text,
    )
    if m:
        return {
            "card_name": "KB국민카드",
            "card_last4": m.group(1),
            "amount": int(m.group(2).replace(",", "")),
            "merchant": m.group(4).strip(),
            "datetime_str": m.group(3),
            "is_foreign": False,
            "cumulative": int(m.group(5).replace(",", "")),
            "currency": "KRW",
        }
    return None


def _parse_lotte(text: str) -> Optional[dict]:
    """롯데카드 승인 파싱.
    SR 94,200원 승인 심*민 롯데백화점(3*4*) 일시불, 04/15 20:02
    """
    m = re.search(
        r"SR\s+([\d,]+)원\s+승인\s+\S+\s+(.+?)\((\S+)\)\s+\S+,\s+(\d{2}/\d{2}\s+\d{2}:\d{2})",
        text,
    )
    if m:
        return {
            "card_name": "롯데카드",
            "card_last4": m.group(3),
            "amount": int(m.group(1).replace(",", "")),
            "merchant": m.group(2).strip(),
            "datetime_str": m.group(4),
            "is_foreign": False,
            "cumulative": None,
            "currency": "KRW",
        }
    return None


def _parse_shinhan(text: str) -> Optional[dict]:
    """신한카드 승인 파싱 (패턴 미확인 — 확장 예정)."""
    return None


PARSERS = [_parse_samsung, _parse_kb, _parse_lotte]


def parse_sms(text: str) -> Optional[dict]:
    for parser in PARSERS:
        result = parser(text)
        if result:
            return result
    return None


def get_card_messages(days: int = 30) -> list[dict]:
    """chat.db에서 카드사 승인 SMS를 조회해 파싱된 리스트 반환."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Messages DB 없음: {DB_PATH}")

    # macOS 코코아 기준시각(2001-01-01)을 Unix timestamp로 변환
    cocoa_epoch = datetime(2001, 1, 1, tzinfo=timezone.utc)
    cutoff_cocoa = (
        datetime.now(timezone.utc) - timedelta(days=days) - cocoa_epoch
    ).total_seconds() * 1_000_000_000  # nanoseconds

    placeholders = ",".join("?" * len(CARD_SENDERS))
    query = f"""
        SELECT h.id, m.text, m.attributedBody, m.date
        FROM message m
        JOIN handle h ON m.handle_id = h.ROWID
        WHERE h.id IN ({placeholders})
          AND m.date >= ?
        ORDER BY m.date DESC
    """

    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute(query, list(CARD_SENDERS.keys()) + [cutoff_cocoa]).fetchall()
    conn.close()

    results = []
    for sender, text, ab, cocoa_ts in rows:
        body = text or (decode_attributed_body(bytes(ab)) if ab else "")
        parsed = parse_sms(body)
        if not parsed:
            continue

        # cocoa timestamp → KST datetime string
        try:
            dt_utc = cocoa_epoch + timedelta(microseconds=cocoa_ts / 1000)
            kst = dt_utc + timedelta(hours=9)
            parsed["received_at"] = kst.strftime("%Y-%m-%d %H:%M")
        except Exception:
            parsed["received_at"] = None

        parsed["sender"] = sender
        results.append(parsed)

    return results


mcp = FastMCP("card-sms")


@mcp.tool()
def get_card_transactions(days: int = 30) -> list[dict]:
    """최근 N일간 카드 승인 SMS를 파싱해 거래 목록 반환.

    Args:
        days: 조회 기간 (기본 30일)

    Returns:
        거래 목록. 각 항목: card_name, card_last4, amount, currency,
        merchant, datetime_str, is_foreign, cumulative, received_at
    """
    try:
        return get_card_messages(days)
    except FileNotFoundError as e:
        return [{"error": str(e)}]


@mcp.tool()
def get_card_summary(days: int = 30) -> dict:
    """최근 N일간 카드별 사용 요약 반환.

    Args:
        days: 조회 기간 (기본 30일)

    Returns:
        카드별 총 사용액, 거래 건수
    """
    try:
        txns = get_card_messages(days)
    except FileNotFoundError as e:
        return {"error": str(e)}

    summary: dict[str, dict] = {}
    for t in txns:
        name = t["card_name"]
        if name not in summary:
            summary[name] = {"total_krw": 0, "count": 0, "foreign_count": 0}
        if not t["is_foreign"] and t["currency"] == "KRW":
            summary[name]["total_krw"] += t["amount"]
        summary[name]["count"] += 1
        if t["is_foreign"]:
            summary[name]["foreign_count"] += 1

    return {"period_days": days, "by_card": summary, "total_transactions": len(txns)}


if __name__ == "__main__":
    mcp.run(transport="stdio")
