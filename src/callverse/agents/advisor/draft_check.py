"""Reflection check of the advisor: every fact in a draft must come from a source.

The playbook says "quote the status, dates and amounts from the record, never from
memory" and "never promise a delivery or refund date earlier than the one in the
system". Small LLMs break this rule (DSO2: invented order numbers and promises), so
before a reply is sent, code compares the draft with its sources: the tool results,
the approved answer of the rules engine and the retrieved policy text.

- order numbers, dates and money amounts: only those found in a source;
- timings ("3 business days", "48 hours"): only those found in a source;
- never ask for a card number, security code or password; always English.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]  # fmt: skip
MONTHS = {name: number for number, name in enumerate(MONTH_NAMES, start=1)}
MONTHS.update({name[:3]: number for name, number in list(MONTHS.items())})
MONTHS["Sept"] = 9
# Capitalised on purpose: "you may 3 ..." is not a date, "3 May" is.
MONTH = "(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\b\.?"
DAY = r"(\d{1,2})(?:st|nd|rd|th)?(?!\d)"
YEAR = r"(?:,?\s+(\d{4}))?"
DAY_MONTH = re.compile(rf"\b{DAY}\s+(?:of\s+)?{MONTH}{YEAR}")
MONTH_DAY = re.compile(rf"\b{MONTH}\s+{DAY}{YEAR}")
ISO_DATE = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
SLASH_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")

AMOUNT = re.compile(r"R\$\s?(\d[\d.,]*)|\b(\d[\d.,]*)\s?(?:BRL|reais|reals)\b", re.I)

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fourteen": 14,
    "fifteen": 15, "twenty": 20, "thirty": 30, "twenty-four": 24, "forty-eight": 48,
}  # fmt: skip
TIMING = re.compile(
    r"\b(\d{1,3}|" + "|".join(sorted(NUMBER_WORDS, key=len, reverse=True)) + r")"
    r"\s+(?:more\s+|extra\s+|additional\s+|full\s+)?(business\s+|working\s+|calendar\s+)?"
    r"(day|hour|week|month)s?\b",
    re.I,
)

ORDER_NUMBER = re.compile(r"\b[0-9a-f]{32}\b", re.I)
# A relative promise ("it arrives tomorrow") is a date too, so it needs a source.
RELATIVE_DAY = re.compile(r"\b(tomorrow|tonight)\b", re.I)
FORBIDDEN = re.compile(r"\b(card number|security code|cvv|cvc|password)\b", re.I)
NEGATION = re.compile(r"\b(never|not|don't|do not|won't|will not|no need|without)\b", re.I)
# Small models drift to Portuguese (the orders, cities and names are Brazilian)
PORTUGUESE = re.compile(
    r"\b(obrigad[oa]|voc[eê]|pedido|desculp\w*|n[uú]mero|por favor|ol[aá]|n[aã]o|sua|seu|"
    r"est[aá]|entrega|reembolso|ajudar|compra)\b",
    re.I,
)


def looks_portuguese(text: str) -> bool:
    """At least three common Portuguese words: the reply is not in English."""
    return len(PORTUGUESE.findall(text)) >= 3


# ------------------------------------------------------------------ extraction
Date = tuple[int | None, int, int]  # (year or None, month, day)


def _date(year: str | int | None, month: int, day: int) -> Date | None:
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    return (int(year) if year else None, month, day)


def find_dates(text: str) -> list[tuple[str, set[Date]]]:
    """Each date written in ``text``, with its possible readings (12/03 is ambiguous)."""
    found: list[tuple[str, set[Date]]] = []
    for match in DAY_MONTH.finditer(text):
        day, month, year = match.groups()
        found.append((match.group(0), {_date(year, MONTHS[month], int(day))}))
    for match in MONTH_DAY.finditer(text):
        month, day, year = match.groups()
        found.append((match.group(0), {_date(year, MONTHS[month], int(day))}))
    for match in ISO_DATE.finditer(text):
        year, month, day = match.groups()
        found.append((match.group(0), {_date(year, int(month), int(day))}))
    for match in SLASH_DATE.finditer(text):
        first, second, year = match.groups()
        readings = {_date(year, int(second), int(first)), _date(year, int(first), int(second))}
        found.append((match.group(0), readings))
    return [(written.rstrip("."), {d for d in readings if d}) for written, readings in found if any(readings)]


def parse_amount(text: str) -> float | None:
    """'1.234,56', '1,234.56', '30', '30,00' -> float."""
    text = text.rstrip(".,")
    if "," in text and "." in text:
        decimal = "," if text.rfind(",") > text.rfind(".") else "."
        text = text.replace("." if decimal == "," else ",", "").replace(decimal, ".")
    elif "," in text:
        whole, _, cents = text.rpartition(",")
        text = f"{whole.replace(',', '')}.{cents}" if len(cents) <= 2 else text.replace(",", "")
    elif text.count(".") == 1 and len(text.rpartition(".")[2]) <= 2:
        pass  # already a decimal point
    else:
        text = text.replace(".", "")
    try:
        return float(text)
    except ValueError:
        return None


def find_amounts(text: str) -> list[tuple[str, float]]:
    """Money amounts written in ``text`` (R$ 30, 129.90 BRL, 45 reais)."""
    found = []
    for match in AMOUNT.finditer(text):
        value = parse_amount(match.group(1) or match.group(2))
        if value is not None:
            found.append((match.group(0), value))
    return found


def find_timings(text: str) -> list[tuple[str, tuple[int, str]]]:
    """Durations written in ``text``: (number, unit), business and working days alike."""
    found = []
    for match in TIMING.finditer(text):
        number, kind, unit = match.groups()
        count = NUMBER_WORDS[number.lower()] if number.lower() in NUMBER_WORDS else int(number)
        unit = unit.lower()
        if kind and kind.strip().lower() in {"business", "working"}:
            unit = f"business {unit}"
        found.append((match.group(0), (count, unit)))
    return found


# --------------------------------------------------------------------- sources
@dataclass
class Sources:
    """What the advisor may quote: facts from tools, the approved answer, the policy."""

    texts: list[str] = field(default_factory=list)
    numbers: set[float] = field(default_factory=set)
    day_counts: set[int] = field(default_factory=set)
    order_numbers: set[str] = field(default_factory=set)

    def add_result(self, value: Any, key: str = "") -> None:
        """Walk one tool result (nested dicts / lists) and keep its facts."""
        if isinstance(value, dict):
            for name, item in value.items():
                self.add_result(item, str(name))
        elif isinstance(value, (list, tuple)):
            for item in value:
                self.add_result(item, key)
        elif isinstance(value, bool) or value is None:
            return
        elif isinstance(value, (int, float)):
            self.numbers.add(float(value))
            if "day" in key:  # days_past_estimated_date, days_since_delivery
                self.day_counts.add(abs(int(value)))
        else:
            text = str(value)
            self.texts.append(text)
            self.order_numbers.update(m.lower() for m in ORDER_NUMBER.findall(text))

    @classmethod
    def collect(
        cls,
        results: Iterable[dict[str, Any]],
        texts: Iterable[str] = (),
        order_id: str | None = None,
    ) -> "Sources":
        sources = cls()
        for result in results:
            sources.add_result(result)
        for text in texts:
            if text:
                sources.texts.append(str(text))
                sources.order_numbers.update(m.lower() for m in ORDER_NUMBER.findall(str(text)))
        if order_id:
            sources.order_numbers.add(order_id.lower())
        return sources

    def dates(self) -> set[Date]:
        return {d for text in self.texts for _, readings in find_dates(text) for d in readings}

    def amounts(self) -> set[float]:
        return self.numbers | {value for text in self.texts for _, value in find_amounts(text)}

    def timings(self) -> set[tuple[int, str]]:
        written = {timing for text in self.texts for _, timing in find_timings(text)}
        return written | {(n, "day") for n in self.day_counts}


# ----------------------------------------------------------------------- check
@dataclass
class DraftCheck:
    """Result of the check: an empty list of problems means the draft can be sent."""

    problems: list[str]
    checked: dict[str, int]

    @property
    def passed(self) -> bool:
        return not self.problems


def _known_date(readings: set[Date], known: set[Date]) -> bool:
    return any(
        (month, day) == (k_month, k_day) and (year is None or k_year is None or year == k_year)
        for year, month, day in readings
        for k_year, k_month, k_day in known
    )


def check_draft(draft: str, sources: Sources) -> DraftCheck:
    """Problems of a draft reply (facts without a source, forbidden asks, language)."""
    problems: list[str] = []
    if not draft.strip():
        return DraftCheck(["The reply is empty."], {})
    dates, amounts, timings = find_dates(draft), find_amounts(draft), find_timings(draft)
    known_dates, known_amounts, known_timings = sources.dates(), sources.amounts(), sources.timings()
    for written, readings in dates:
        if not _known_date(readings, known_dates):
            problems.append(
                f"The date '{written}' is not in the order record, the approved answer or the policy."
            )
    for written, value in amounts:
        if not any(abs(value - known) < 0.01 for known in known_amounts):
            problems.append(f"The amount '{written}' is not in the order record or the policy.")
    for written, timing in timings:
        if timing not in known_timings:
            problems.append(f"The timing '{written}' is not in the approved answer or the policy.")
    for word in {w.lower() for w in RELATIVE_DAY.findall(draft)}:
        if not any(word in text.lower() for text in sources.texts):
            problems.append(f"The promise '{word}' is not in the order record or the approved answer.")
    numbers = [m.lower() for m in ORDER_NUMBER.findall(draft)]
    for number in numbers:
        if number not in sources.order_numbers:
            problems.append(f"The order number {number} is not this customer's order.")
    for sentence in re.split(r"(?<=[.!?])\s+", draft):
        if FORBIDDEN.search(sentence) and not NEGATION.search(sentence):
            problems.append("Never ask for a card number, security code or password.")
            break
    if looks_portuguese(draft):
        problems.append("The reply is not in English.")
    checked = {
        "dates": len(dates),
        "amounts": len(amounts),
        "timings": len(timings),
        "order_numbers": len(numbers),
    }
    return DraftCheck(list(dict.fromkeys(problems)), checked)
