"""
Яндекс.Метрика API client — посещаемость сайта (визиты/пользователи/просмотры).

В отличие от Яндекс.Вебмастера (индексация, ИКС, поисковые запросы) — это
реальный трафик на сайт, как Google Analytics. Метрика и Вебмастер — разные
продукты Яндекса, но один и тот же OAuth-токен может иметь доступ к обоим,
если при создании приложения на oauth.yandex.ru отмечены оба scope.

Использование:
    from modules.yandex_metrika import ym_resolve_counter_id, ym_stat_totals

    counter_id = ym_resolve_counter_id("kuskusgrooming.ru")
    totals = ym_stat_totals(counter_id, "2026-08-01", "2026-08-14")

ENV:
    YANDEX_METRIKA_TOKEN — OAuth access_token со scope metrika:read.
        Если не задан — используется YANDEX_WEBMASTER_TOKEN (частый случай:
        одно OAuth-приложение с правами на оба продукта).
    YANDEX_METRIKA_COUNTER_ID — id счётчика Метрики. Если не задан —
        резолвится автоматически по домену через список счётчиков токена.

Docs: https://yandex.ru/dev/metrika/doc/api2/api_v1/intro.html
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import requests

log = logging.getLogger(__name__)

API_BASE = "https://api-metrika.yandex.net"

METRICS = "ym:s:visits,ym:s:users,ym:s:pageviews"
METRIC_KEYS = ("visits", "users", "pageviews")


def _token() -> str:
    t = (
        os.environ.get("YANDEX_METRIKA_TOKEN", "").strip()
        or os.environ.get("YANDEX_WEBMASTER_TOKEN", "").strip()
    )
    if not t:
        raise RuntimeError(
            "YANDEX_METRIKA_TOKEN (или YANDEX_WEBMASTER_TOKEN) не задан. "
            "Нужен OAuth-токен со scope metrika:read (oauth.yandex.ru)."
        )
    return t


def _headers() -> dict:
    return {"Authorization": f"OAuth {_token()}"}


def _get(path: str, params: Optional[dict] = None) -> dict:
    r = requests.get(f"{API_BASE}{path}", headers=_headers(), params=params or {}, timeout=20)
    r.raise_for_status()
    return r.json()


def ym_list_counters() -> list[dict]:
    """Список счётчиков, доступных этому токену (свои + с правом просмотра)."""
    data = _get("/management/v1/counters")
    return data.get("counters", [])


def ym_resolve_counter_id(domain: str) -> int:
    """Найти counter_id по домену сайта. YANDEX_METRIKA_COUNTER_ID в env — приоритет."""
    env_id = os.environ.get("YANDEX_METRIKA_COUNTER_ID", "").strip()
    if env_id:
        return int(env_id)
    domain = domain.lower()
    for c in ym_list_counters():
        site = (c.get("site") or "").lower()
        if domain in site:
            return c["id"]
    raise RuntimeError(
        f"Счётчик Метрики для {domain} не найден среди доступных токену. "
        "Задай YANDEX_METRIKA_COUNTER_ID явно."
    )


def ym_stat_totals(counter_id: int, date_from: str, date_to: str) -> dict:
    """Суммарные визиты/пользователи/просмотры за период (без разбивки по дням)."""
    data = _get(
        "/stat/v1/data",
        params={"ids": counter_id, "metrics": METRICS, "date1": date_from, "date2": date_to},
    )
    totals = data.get("totals") or []
    return {k: int(v) for k, v in zip(METRIC_KEYS, totals)}


def ym_stat_by_day(counter_id: int, date_from: str, date_to: str) -> list[dict]:
    """Визиты по дням (dimension ym:s:date), отсортировано по возрастанию даты."""
    data = _get(
        "/stat/v1/data",
        params={
            "ids": counter_id,
            "metrics": METRICS,
            "dimensions": "ym:s:date",
            "date1": date_from,
            "date2": date_to,
            "sort": "ym:s:date",
        },
    )
    out = []
    for row in data.get("data", []):
        date = row["dimensions"][0]["name"]
        values = {k: int(v) for k, v in zip(METRIC_KEYS, row["metrics"])}
        values["date"] = date
        out.append(values)
    return out


if __name__ == "__main__":
    # Smoke-test.
    import datetime as dt

    logging.basicConfig(level=logging.INFO)

    print("→ Список счётчиков, доступных токену:")
    for c in ym_list_counters():
        print(f"  {c['id']:>10}  {c.get('site', '?'):30}  {c.get('name', '')}")

    domain = os.environ.get("SEO_SITE_DOMAIN", "").strip()
    if domain:
        counter_id = ym_resolve_counter_id(domain)
        yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
        week_ago = (dt.date.today() - dt.timedelta(days=7)).isoformat()
        print(f"\n→ Визиты {domain} (counter_id={counter_id}) за {week_ago}..{yesterday}:")
        print(" ", ym_stat_totals(counter_id, week_ago, yesterday))
