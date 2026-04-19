#!/usr/bin/env python3
"""
텔레그램 봇에서 결제 메시지를 가져옵니다.
사용법: python fetch_telegram.py
"""

import os
import json
import urllib.request
import urllib.parse
from pathlib import Path

# .env 파일에서 토큰 읽기
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip())

BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    raise SystemExit('BOT_TOKEN이 없습니다. .env 파일을 확인하세요.')

def tg_get(method, **params):
    url = f'https://api.telegram.org/bot{BOT_TOKEN}/{method}'
    if params:
        url += '?' + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url) as r:
        return json.loads(r.read())

# 최근 100개 메시지 가져오기
result = tg_get('getUpdates', limit=100, allowed_updates='message')

if not result.get('ok'):
    raise SystemExit(f'Telegram API 오류: {result}')

updates = result.get('result', [])
messages = []

for update in updates:
    msg = update.get('message') or update.get('channel_post')
    if not msg:
        continue
    text = msg.get('text') or msg.get('caption') or ''
    if not text.strip():
        continue
    messages.append({
        'date': msg.get('date'),
        'text': text,
        'from': msg.get('forward_origin', {}).get('sender_user_name')
               or msg.get('from', {}).get('username', ''),
    })

# telegram_raw.json 에 저장 (Claude가 읽을 파일)
out = Path(__file__).parent / 'telegram_raw.json'
out.write_text(json.dumps(messages, ensure_ascii=False, indent=2))

print(f'✅ {len(messages)}개 메시지 저장됨 → telegram_raw.json')
print()
for m in messages[-10:]:  # 최근 10개 출력
    import datetime
    dt = datetime.datetime.fromtimestamp(m['date']).strftime('%m/%d %H:%M')
    preview = m['text'][:80].replace('\n', ' ')
    print(f'  [{dt}] {preview}')
