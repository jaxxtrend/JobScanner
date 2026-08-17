"""Extract salary figures and convert to RUB using CBR daily rates."""

from __future__ import annotations

import logging
import re
from functools import lru_cache

import requests

log = logging.getLogger(__name__)


def get_dynamic_exchange_rates() -> dict[str, float]:
    url = "https://www.cbr-xml-daily.ru/daily_json.js"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    data = response.json()

    def get_rate(code: str) -> float:
        if code not in data["Valute"]:
            raise KeyError(f"CBR daily JSON has no currency {code}")
        val = data["Valute"][code]["Value"]
        nom = data["Valute"][code]["Nominal"]
        return val / nom

    usd = get_rate("USD")
    eur = get_rate("EUR")
    kzt = get_rate("KZT")
    gbp = get_rate("GBP")
    return {
        "RUB": 1, "₽": 1, "R": 1, "РУБ": 1,
        "USD": usd, "$": usd, "DOLLAR": usd, "ДОЛЛАР": usd,
        "EUR": eur, "€": eur, "EURO": eur, "ЕВРО": eur,
        "KZT": kzt, "ТЕНГЕ": kzt,
        "GBP": gbp, "£": gbp, "ФУНТ": gbp,
    }


@lru_cache(maxsize=1)
def _get_exchange_rates() -> dict[str, float] | None:
    try:
        rates = get_dynamic_exchange_rates()
        log.info("Loaded CBR exchange rates")
        return rates
    except (requests.RequestException, KeyError, ValueError) as exc:
        log.error("CBR exchange rates unavailable: %s", exc)
        return None


def detect_currency(text: str) -> str:
    text_lc = text.lower()
    if any(w in text_lc for w in ["usd", "доллар", "$"]):
        return "USD"
    if any(w in text_lc for w in ["eur", "евро", "€"]):
        return "EUR"
    if any(w in text_lc for w in ["gbp", "фунт", "£"]):
        return "GBP"
    if any(w in text_lc for w in ["kzt", "тенге"]):
        return "KZT"
    if any(re.search(w, text_lc) for w in [r"₽", r"руб", r"\bр\.", r"\bр\s"]):
        return "RUB"
    return "RUB"


_COUNT_SUFFIX = (
    r"(?:%|roles?|positions?|months?|years?|days?|weeks?|hours?|"
    r"people|employees?|staff|posted|hires?|vacancies|openings|"
    r"ваканс(?:ий|ии|ия)?|месяц(?:ев|а)?|год(?:а|ов)?|лет|дней|день|"
    r"час(?:ов|а)?|людей|сотрудник(?:ов|а)?)"
)


def _is_non_salary_number(text: str, num_str: str) -> bool:
    num = re.sub(r"\s", "", (num_str or "").strip())
    if not num:
        return False
    n = re.escape(num)
    if re.search(rf"(?i)\d+\s*%\s*(?:of\s+)?{n}\b", text):
        return True
    if re.search(rf"(?i)\b{n}\s*{_COUNT_SUFFIX}", text):
        return True
    return False


def extract_salary(text: str) -> int | None:
    if not text:
        return None

    text_clean = re.sub(r"\(https?://.*?\)", "", text, flags=re.DOTALL)
    text_clean = re.sub(r"\[.*?\]", "", text_clean, flags=re.DOTALL)
    text_clean = re.sub(r"https?://\S+", "", text_clean)

    default_currency = detect_currency(text_clean)
    rates = _get_exchange_rates()

    curr_p = r"(?:₽|RUB|р\.|руб|KZT|USD|\$|EUR|€|GBP|£)"
    letter = r"a-zA-Zа-яА-ЯёЁ"
    num_p = rf"(?<![{letter}])(\d[\d\s.,]*)"
    suf_p = r"(k|K|к|К|тыс|т\.р\.)?"
    sep_p = r"(?:[-–—~]|до|от)"
    pattern = rf"(?i)({curr_p})?\s*{num_p}\s*{suf_p}\s*(?:{sep_p}\s*({curr_p})?\s*{num_p}\s*{suf_p})?\s*({curr_p})?"
    matches = re.findall(pattern, text_clean)
    salaries_rub: list[float] = []

    is_salary_context = bool(re.search(
        r"(?i)\b(?:вилка|зарплата|зп|salary|compensation|оклад|gross|net|ставка)\b",
        text_clean,
    ))

    def clean_val(val_str: str | None) -> float | None:
        if not val_str:
            return None
        val_str = val_str.strip().replace(" ", "")
        if re.search(r"[,.]\d{3}$", val_str):
            val_str = val_str.replace(",", "").replace(".", "")
        else:
            val_str = val_str.replace(",", ".")
        try:
            return float(re.sub(r"[^\d.]", "", val_str))
        except ValueError:
            return None

    for match in matches:
        _c1, n1, s1, _c2, n2, s2, _c3 = match
        v1 = clean_val(n1)
        if v1 is None:
            continue
        if _is_non_salary_number(text_clean, n1):
            continue

        mult1 = 1000 if s1 and any(s in s1.lower() for s in ["k", "к", "тыс", "т.р."]) else 1
        v1 *= mult1

        v2 = clean_val(n2)
        if v2 is not None:
            if _is_non_salary_number(text_clean, n2):
                v2 = None
            else:
                mult2 = 1000 if s2 and any(s in s2.lower() for s in ["k", "к", "тыс", "т.р."]) else 1
                if mult1 == 1000 and mult2 == 1 and v2 < 1000:
                    v2 *= 1000
                elif mult2 == 1000 and mult1 == 1 and v1 < 1000:
                    v1 *= 1000
                else:
                    v2 *= mult2

        has_explicit_currency = any([_c1, _c2, _c3])
        if not has_explicit_currency and not is_salary_context:
            if v1 > 500000:
                continue
            if v1 > 100000 and default_currency != "RUB":
                continue
            if v1 < 10000:
                continue

        if 2020 <= v1 <= 2030 and v2 is None:
            continue
        if v1 < 100:
            continue

        curr = (_c1 or _c2 or _c3 or default_currency).upper()
        rub_aliases = {"RUB", "₽", "R", "РУБ"}
        if rates is None:
            if curr not in rub_aliases:
                continue
            rate = 1.0
        else:
            rate = rates.get(curr)
            if rate is None:
                continue

        final_val = (v1 + v2) / 2 if v2 else v1
        if curr in ("USD", "EUR", "GBP", "$", "€") and final_val > 10000:
            final_val = final_val / 12
        salaries_rub.append(final_val * rate)

    if not salaries_rub:
        return None
    return int(round(sum(salaries_rub) / len(salaries_rub)))
