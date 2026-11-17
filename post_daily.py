#!/usr/bin/env python3
"""Ежедневный пост IThub Bingo в канал. Только стандартная библиотека Python 3.

Запуск: BOT_TOKEN=... CHANNEL=@your_channel APP_LINK=https://t.me/YOUR_BOT/bingo python3 post_daily.py
Cron (утро по Москве): CRON_TZ=Europe/Moscow
                       0 8 * * * BOT_TOKEN=... CHANNEL=@your_channel APP_LINK=... python3 /opt/bingo/post_daily.py
Бот должен быть администратором канала с правом публикации.
"""
import json, os, urllib.request

TOKEN = os.environ["BOT_TOKEN"]
CHANNEL = os.environ.get("CHANNEL", "@your_channel")
APP_LINK = os.environ.get("APP_LINK", "https://t.me/YOUR_BOT/bingo")
TEXT = ("🎯 IThub Bingo\n\n"
        "Новая карточка на сегодня уже готова. Отмечай то, что случилось с тобой, "
        "и узнавай по пути IT-факты и термины.\n\n"
        "Собрал(а) линию? Жми «Поделиться» и показывай друзьям 💜")

data = json.dumps({
    "chat_id": CHANNEL,
    "text": TEXT,
    "reply_markup": {"inline_keyboard": [[{"text": "Играть", "url": APP_LINK}]]},
}).encode()
req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                             data=data, headers={"Content-Type": "application/json"})
print(urllib.request.urlopen(req, timeout=20).read().decode())
