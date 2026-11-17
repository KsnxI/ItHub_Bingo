#!/usr/bin/env python3
"""Ежедневный генератор карточек IThub Bingo. Только стандартная библиотека, Python 3.9+.

Что делает при каждом запуске:
  1. забирает свежую версию репозитория (если вы правили pool.json на GitHub);
  2. если задан ANTHROPIC_API_KEY, просит Claude придумать новые клетки и добавляет их в базу;
  3. собирает карточку на завтра (с --today ещё и на сегодня) из наименее недавно использованных клеток;
  4. кладёт её в daily/ГГГГ-ММ-ДД.json, коммитит и пушит. GitHub Pages сам обновит сайт за 1-2 минуты.

Запуск вручную:  python3 generate.py --today
Переменные окружения: REPO_DIR, ANTHROPIC_API_KEY, MODEL, BOT_TOKEN, ADMIN_ID (необязательные, см. код).
"""
import glob, json, os, random, subprocess, sys, urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

REPO = os.environ.get("REPO_DIR", "/opt/bingo/repo")
TZ = ZoneInfo(os.environ.get("TZ_NAME", "Europe/Moscow"))
KEY = os.environ.get("ANTHROPIC_API_KEY")
MODEL = os.environ.get("MODEL", "claude-sonnet-5-5")
BOT, ADMIN = os.environ.get("BOT_TOKEN"), os.environ.get("ADMIN_ID")
POOL = f"{REPO}/pool.json"
PENDING = os.path.join(os.path.dirname(REPO.rstrip("/")), "pending_facts.json")   # лежит рядом с репозиторием, на GitHub не попадает
SIZE = {"memes": 14, "facts": 6, "terms": 4}   # состав карточки: 24 клетки


def git(*a, check=True):
    return subprocess.run(["git", "-C", REPO, *a], check=check, capture_output=True, text=True)


def tell_admin(text):
    print(text)
    if not (BOT and ADMIN):
        return
    try:
        req = urllib.request.Request(f"https://api.telegram.org/bot{BOT}/sendMessage",
                                     json.dumps({"chat_id": ADMIN, "text": text[:4000]}).encode(),
                                     {"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=20)
    except Exception as e:
        print("Не удалось написать админу:", e)


def ask_claude(pool):
    have = pool["memes"][-80:] + [t[0] for t in pool["terms"]] + [f[0] for f in pool["facts"]]
    prompt = (
        "Ты редактор студенческого IT-канала колледжа. Аудитория: студенты, которые только учатся. "
        "Верни СТРОГО JSON без пояснений и без markdown:\n"
        '{"memes": [6 строк], "terms": [["название","объяснение"], ... 3 штуки], "facts": [["название","текст"], ... 2 штуки]}\n'
        "Правила:\n"
        "- memes: до 28 символов, ситуации из студенческой IT-жизни, про которые можно сказать «это было со мной». "
        "Добрый юмор, без политики, без мата, без насмешек над людьми и конкретными преподавателями.\n"
        "- terms: базовые термины для новичков. Название до 14 символов, объяснение до 130 символов простыми словами.\n"
        "- facts: только проверяемые факты из истории IT с указанием года. Название до 22 символов, текст до 170 символов. "
        "Если не уверен в факте на 100%, не включай его.\n"
        "- Не повторяй и не перефразируй уже существующее: " + "; ".join(have)
    )
    body = json.dumps({"model": MODEL, "max_tokens": 1500,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", body, {
        "x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    text = json.load(urllib.request.urlopen(req, timeout=90))["content"][0]["text"]
    return json.loads(text[text.find("{"): text.rfind("}") + 1])


def grow(pool):
    """Добавляет новые клетки в базу. Мемы и термины идут сразу, факты ждут проверки человеком."""
    if not KEY:
        return
    try:
        new = ask_claude(pool)
    except Exception as e:
        print("Генерация пропущена:", e)
        return
    have = {m.lower() for m in pool["memes"]} | {x[0].lower() for k in ("terms", "facts") for x in pool[k]}
    added = 0
    for m in new.get("memes", []):
        if isinstance(m, str) and 3 <= len(m) <= 30 and m.lower() not in have:
            pool["memes"].append(m); have.add(m.lower()); added += 1
    for t in new.get("terms", []):
        if isinstance(t, list) and len(t) == 2 and len(t[0]) <= 16 and len(t[1]) <= 160 and t[0].lower() not in have:
            pool["terms"].append(t); have.add(t[0].lower()); added += 1
    facts = [f for f in new.get("facts", []) if isinstance(f, list) and len(f) == 2
             and len(f[0]) <= 24 and len(f[1]) <= 200 and f[0].lower() not in have]
    if facts:
        json.dump(facts, open(PENDING, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        tell_admin("IThub Bingo: новые факты на проверку. Проверьте по источникам и, если всё верно, "
                   "добавьте в раздел facts файла pool.json на GitHub:\n\n" +
                   "\n\n".join(f"{a}\n{b}" for a, b in facts))
    print("В базу добавлено клеток:", added)


def pick(pool, kind, n, day):
    """Берёт n клеток, которые не использовались дольше всего, чтобы всё успевало ротироваться."""
    name = (lambda x: x) if kind == "memes" else (lambda x: x[0])
    items = pool[kind][:]
    random.shuffle(items)
    items.sort(key=lambda x: pool["last_used"].get(name(x), ""))
    chosen = items[:n]
    for x in chosen:
        pool["last_used"][name(x)] = day
    return chosen


def make_card(pool, day):
    cells = [{"t": m} for m in pick(pool, "memes", SIZE["memes"], day)]
    cells += [{"t": t, "n": n} for t, n in pick(pool, "facts", SIZE["facts"], day)]
    cells += [{"t": t, "n": n} for t, n in pick(pool, "terms", SIZE["terms"], day)]
    random.shuffle(cells)
    return cells


def main():
    git("pull", "--rebase", check=False)
    pool = json.load(open(POOL, encoding="utf-8"))
    pool.setdefault("last_used", {})
    grow(pool)
    today = datetime.now(TZ).date()
    days = ([today] if "--today" in sys.argv else []) + [today + timedelta(days=1)]
    os.makedirs(f"{REPO}/daily", exist_ok=True)
    for d in days:
        path = f"{REPO}/daily/{d.isoformat()}.json"
        if os.path.exists(path):          # повторный запуск не меняет уже выпущенную карточку
            continue
        card = {"date": d.isoformat(), "cells": make_card(pool, d.isoformat())}
        json.dump(card, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    for old in sorted(glob.glob(f"{REPO}/daily/*.json"))[:-14]:   # храним последние 14 дней
        os.remove(old)
    json.dump(pool, open(POOL, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    git("add", "-A")
    if git("diff", "--cached", "--quiet", check=False).returncode:
        git("commit", "-m", f"cards {days[-1]}")
        git("push")
        print("Карточки опубликованы:", ", ".join(d.isoformat() for d in days))
    else:
        print("Изменений нет")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        tell_admin(f"IThub Bingo: generate.py упал: {e}")
        raise
