from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import html
from html.parser import HTMLParser
import json
import re
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCALE = ROOT / "content" / "i18n" / "sw-TZ"
VOICE = "sw-TZ-RehemaNeural"
RATE = "-30%"
VERSION = "v112"

ONES = ("sifuri", "moja", "mbili", "tatu", "nne", "tano", "sita", "saba", "nane", "tisa")
TENS = {10: "kumi", 20: "ishirini", 30: "thelathini", 40: "arobaini",
        50: "hamsini", 60: "sitini", 70: "sabini", 80: "themanini", 90: "tisini"}
LETTERS = dict(zip(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    ("a", "be", "che", "de", "e", "fe", "ge", "he", "i", "je", "ke", "le",
     "me", "ne", "o", "pe", "ku", "re", "se", "te", "u", "ve", "we", "ekisi", "ye", "ze")
))
ROMAN = {"I": "ai", "V": "vi", "X": "eksi", "L": "eli", "C": "si", "D": "di", "M": "emu"}
UNITS = {"mm": "milimeta", "sm": "sentimeta", "dm": "desimeta", "km": "kilometa",
         "kg": "kilogramu", "mg": "miligramu", "ml": "mililita", "m": "meta",
         "g": "gramu", "l": "lita", "t": "tani", "sh": "shilingi", "st": "senti"}
DIGIT_WORD_VALUES = {
    "sifuri": 0, "moja": 1, "mbili": 2, "tatu": 3, "nne": 4,
    "tano": 5, "sita": 6, "saba": 7, "nane": 8, "tisa": 9,
}
SPAN_RE = re.compile(r'<span class="pdf-span" style="(?P<style>[^"]*)">(?P<text>.*?)</span>', re.S)

ROMAN_READING_ORDER_IDS = {
    "pg013_gp001_tx001",
    "pg015_gp001_tx001",
    "pg018_gp001_tx001",
    "pg021_gp001_tx001",
    "pg023_gp001_tx001",
}

BLOCK_TAGS = {
    "address", "article", "aside", "blockquote", "br", "caption", "dd", "div",
    "dl", "dt", "figcaption", "figure", "footer", "h1", "h2", "h3", "h4",
    "h5", "h6", "header", "li", "main", "p", "section", "td", "th", "tr",
}


class SemanticNarrationParser(HTMLParser):
    """Extract readable page content while preserving its semantic order."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.page_depth = 0
        self.skip_depth = 0
        self.list_counters: list[int] = []

    @staticmethod
    def _classes(attrs: list[tuple[str, str | None]]) -> set[str]:
        value = next((value for key, value in attrs if key == "class"), "") or ""
        return set(value.split())

    def _separator(self) -> None:
        if self.parts and self.parts[-1] != ". ":
            self.parts.append(". ")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = self._classes(attrs)
        if self.page_depth == 0 and "page-inner" in classes:
            self.page_depth = 1
            return
        if self.page_depth == 0:
            return
        self.page_depth += 1
        if self.skip_depth:
            self.skip_depth += 1
            return
        if "page-narration-hook" in classes or tag in {"script", "style", "noscript"}:
            self.skip_depth = 1
            return
        if tag == "ol":
            self.list_counters.append(0)
        elif tag == "li" and self.list_counters:
            self.list_counters[-1] += 1
            self._separator()
            self.parts.append(f"Swali namba {self.list_counters[-1]}. ")
        elif tag == "img":
            alt = next((value for key, value in attrs if key == "alt"), "") or ""
            if alt.strip():
                self._separator()
                self.parts.append(alt.strip())
                self._separator()
        elif tag in BLOCK_TAGS:
            self._separator()

    def handle_endtag(self, tag: str) -> None:
        if self.page_depth == 0:
            return
        if self.skip_depth:
            self.skip_depth -= 1
        elif tag == "ol" and self.list_counters:
            self.list_counters.pop()
            self._separator()
        elif tag in BLOCK_TAGS:
            self._separator()
        self.page_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.page_depth and not self.skip_depth and data.strip():
            self.parts.append(data.strip() + " ")

    def text(self) -> str:
        value = "".join(self.parts)
        value = re.sub(r"\s+([,.;:!?])", r"\1", value)
        value = re.sub(r"(?:\.\s*){2,}", ". ", value)
        return re.sub(r"\s+", " ", value).strip(". ")


@dataclass
class Item:
    left: float
    top: float
    width: float
    size: float
    text: str


def number_words(value: int) -> str:
    if value < 0:
        return "hasi " + number_words(-value)
    if value < 10:
        return ONES[value]
    if value < 100:
        tens, rest = divmod(value, 10)
        root = TENS[tens * 10]
        return root if rest == 0 else root + " na " + ONES[rest]
    if value < 1000:
        hundreds, rest = divmod(value, 100)
        root = "mia " + ONES[hundreds]
        return root if rest == 0 else root + " na " + number_words(rest)
    if value < 1_000_000:
        if value >= 100_000:
            lakhs, rest = divmod(value, 100_000)
            root = "laki " + number_words(lakhs)
            if rest == 0:
                return root
            if rest >= 1000:
                thousands, tail = divmod(rest, 1000)
                root += " na elfu " + number_words(thousands)
                if tail:
                    root += (" na " if tail < 100 else " ") + number_words(tail)
                return root
            return root + " na " + number_words(rest)
        thousands, rest = divmod(value, 1000)
        root = "elfu " + number_words(thousands)
        return root if rest == 0 else root + (" na " if rest < 100 else " ") + number_words(rest)
    if value < 1_000_000_000:
        millions, rest = divmod(value, 1_000_000)
        root = "milioni " + number_words(millions)
        return root if rest == 0 else root + " " + number_words(rest)
    billions, rest = divmod(value, 1_000_000_000)
    root = "bilioni " + number_words(billions)
    return root if rest == 0 else root + " " + number_words(rest)


def number_token(token: str) -> str:
    token = token.replace(",", "")
    if "." in token:
        whole, decimals = token.split(".", 1)
        return number_words(int(whole)) + " nukta " + " ".join(ONES[int(x)] for x in decimals)
    return number_words(int(token))


def fraction_words(top: int, bottom: int) -> str:
    if top == 1 and bottom == 2:
        return "nusu"
    if bottom == 4 and top in (1, 3):
        return "robo" if top == 1 else "robo tatu"
    if top == 1:
        return "sehemu moja ya " + number_words(bottom)
    return "sehemu " + number_words(top) + " za " + number_words(bottom)


def style_number(style: str, key: str, default: float = 0.0) -> float:
    found = re.search(r"(?:^|;)" + re.escape(key) + r":([\d.]+)px", style)
    return float(found.group(1)) if found else default


def split_wide(item: Item) -> list[Item]:
    item.text = item.text.replace("\t", " ")
    if not re.search(r" {2,}", item.text):
        return [item]
    total = max(len(item.text), 1)
    result = []
    for part in re.finditer(r"\S(?:.*?\S)?(?= {2,}|$)", item.text):
        text = part.group(0).strip()
        if text:
            result.append(Item(
                item.left + item.width * part.start() / total,
                item.top,
                item.width * len(part.group(0)) / total,
                item.size,
                text,
            ))
    return result or [item]


def merge_fractions(items: list[Item]) -> list[Item]:
    used: set[int] = set()
    merged: list[Item] = []
    digits = [i for i, item in enumerate(items) if re.fullmatch(r"\d+", item.text)]
    for i in digits:
        if i in used:
            continue
        top = items[i]
        best = None
        for j in digits:
            if j == i or j in used:
                continue
            bottom = items[j]
            gap = bottom.top - top.top
            size = max(top.size, bottom.size)
            centers = abs((top.left + top.width / 2) - (bottom.left + bottom.width / 2))
            if not size * 0.8 <= gap <= size * 1.55 or centers > max(1.8, size * 0.18):
                continue
            middle = (top.top + bottom.top) / 2
            has_baseline = any(
                k not in (i, j) and abs(other.top - middle) <= max(3.0, size * 0.3)
                for k, other in enumerate(items)
            )
            if size > 10.5 and not has_baseline:
                continue
            score = abs(gap - size * 1.2) + centers
            if best is None or score < best[0]:
                best = (score, j)
        if best is None:
            continue
        j = best[1]
        bottom = items[j]
        used.update((i, j))
        merged.append(Item(min(top.left, bottom.left), (top.top + bottom.top) / 2,
                           max(top.width, bottom.width), max(top.size, bottom.size),
                           top.text + "/" + bottom.text))
    merged.extend(item for i, item in enumerate(items) if i not in used)
    return merged


def compose_line(line: list[Item]) -> str:
    line.sort(key=lambda item: item.left)
    operator_values = {"=", "+", "×", "÷", "−", "-"}
    equals = [item for item in line if item.text.strip() == "="]
    if equals:
        first_equal = min(equals, key=lambda item: item.left)
        before = [item.text.strip() for item in line
                  if item.text.strip() not in operator_values and item.left < first_equal.left]
        operands = [item.text.strip() for item in line
                    if item.text.strip() not in operator_values and item.left >= first_equal.left]
        later_operators = [item.text.strip() for item in sorted(line, key=lambda item: item.left)
                           if item.text.strip() in operator_values and item is not first_equal]
        if operands and len(operands) == len(later_operators) + 1:
            tokens = before + ["=", operands[0]]
            for operator, operand in zip(later_operators, operands[1:]):
                tokens.extend((operator, operand))
            return " ".join(tokens)
    return " ".join(item.text.strip() for item in line if item.text.strip())


def page_source(data_id: str) -> str | None:
    match = re.fullmatch(r"pg(\d{3})_gp001_tx001", data_id)
    if not match:
        return None
    page = ROOT / ("pg" + match.group(1) + "_sec001.html")
    if not page.exists():
        return None
    source = page.read_text(encoding="utf-8")
    if 'class="book-page pdf-dom-page"' not in source:
        return None
    items: list[Item] = []
    for found in SPAN_RE.finditer(source):
        style = found.group("style")
        text = html.unescape(re.sub(r"<[^>]+>", "", found.group("text"))).replace("\x07", " ")
        if not text.strip():
            continue
        items.extend(split_wide(Item(style_number(style, "left"), style_number(style, "top"),
                                     style_number(style, "width"), style_number(style, "font-size", 14), text)))
    page_number = int(match.group(1))
    if 99 <= page_number <= 150 or page_number == 152:
        items = merge_fractions(items)
    items.sort(key=lambda item: (item.top, item.left))
    lines: list[list[Item]] = []
    tops: list[float] = []
    for item in items:
        tolerance = max(2.8, min(4.2, item.size * 0.3))
        choices = [(abs(item.top - top), i) for i, top in enumerate(tops) if abs(item.top - top) <= tolerance]
        if not choices:
            lines.append([item])
            tops.append(item.top)
        else:
            _, i = min(choices)
            lines[i].append(item)
            tops[i] = sum(piece.top for piece in lines[i]) / len(lines[i])
    result = []
    for _, line in sorted(zip(tops, lines), key=lambda pair: pair[0]):
        text = compose_line(line)
        text = re.sub(r"\s+([,.;:!?])", r"\1", text)
        text = re.sub(r"\(\s+", "(", text)
        text = re.sub(r"\s+\)", ")", text)
        if text:
            result.append(text)
    return ". ".join(result)


def semantic_html_source(data_id: str) -> str | None:
    match = re.fullmatch(r"pg(\d{3})_gp001_tx001", data_id)
    if not match:
        return None
    page_number = int(match.group(1))
    page = ROOT / ("index.html" if page_number == 1 else f"pg{page_number:03d}_sec001.html")
    if not page.exists():
        return None
    source = page.read_text(encoding="utf-8")
    if 'class="book-page pdf-dom-page"' in source:
        return None
    parser = SemanticNarrationParser()
    parser.feed(source)
    return parser.text() or None


def spell(match: re.Match[str]) -> str:
    return " ".join(LETTERS.get(char, char) for char in match.group(0).upper())


def spell_roman(match: re.Match[str]) -> str:
    return " ".join(ROMAN[char] for char in match.group(0).upper())


def add_pauses(value: str) -> str:
    ordinal = (r"kwanza|pili|tatu|nne|tano|sita|saba|nane|tisa|kumi|"
               r"kumi na moja|kumi na mbili|kumi na tatu|kumi na nne|kumi na tano|\d+")
    for label in ("Mfano wa", "Zoezi la"):
        value = re.sub(
            rf"(^|(?<=[.!?])\s+)({label}\s+(?:{ordinal}))\b[.:]?",
            lambda match: (match.group(1) or "") + match.group(2) + ". ",
            value,
            flags=re.I,
        )
    value = re.sub(
        rf"(^|(?<=[.!?])\s+)(Kazi ya kufanya(?: ya (?:{ordinal}))?)\b[.:]?",
        lambda match: (match.group(1) or "") + match.group(2) + ". ",
        value,
        flags=re.I,
    )
    for marker in ("Utangulizi", "Njia", "Hatua", "Zingatia"):
        value = re.sub(
            rf"(^|(?<=[.!?])\s+){marker}\b[.,:]?",
            lambda match: (match.group(1) or "") + marker + ". ",
            value,
            flags=re.I,
        )
    value = re.sub(r"\bKwa hiyo\b[,:]?", ". Kwa hiyo, ", value, flags=re.I)
    return re.sub(r"(?:\.\s*){2,}", ". ", value).lstrip(". ")


def clean_existing_narration(value: str, data_id: str = "") -> str:
    """Repair speech text without changing any visible textbook content."""
    value = html.unescape(value).replace("\x07", " ")

    # Use fluent cardinal numbering when introducing questions and recap items.
    ordinal_question_pages = {
        "pg039_gp001_tx001",
        "pg041_gp001_tx001",
    }
    use_ordinal_questions = data_id in ordinal_question_pages
    if data_id == "pg041_gp001_tx001":
        question_ordinals = {
            1: "kwanza", 2: "pili", 3: "tatu", 4: "nne", 5: "tano",
            6: "sita", 7: "saba", 8: "nane", 9: "tisa", 10: "kumi",
            11: "kumi na moja", 12: "kumi na mbili", 13: "kumi na tatu",
            14: "kumi na nne", 15: "kumi na tano", 16: "kumi na sita",
            17: "kumi na saba", 18: "kumi na nane", 19: "kumi na tisa",
            20: "ishirini", 21: "ishirini na moja", 22: "ishirini na mbili",
            23: "ishirini na tatu", 24: "ishirini na nne", 25: "ishirini na tano",
        }
        for question_number, ordinal in question_ordinals.items():
            value = re.sub(
                rf"\bSwali la {question_number}\b",
                f"Swali la {ordinal}",
                value,
                flags=re.I,
            )
    if not use_ordinal_questions:
        value = re.sub(r"\bSwali la\s+(?=\d)", "Swali namba ", value, flags=re.I)
    ordinal_to_cardinal = {
        "kwanza": "moja", "pili": "mbili", "tatu": "tatu", "nne": "nne",
        "tano": "tano", "sita": "sita", "saba": "saba", "nane": "nane",
        "tisa": "tisa", "kumi": "kumi",
    }
    for ordinal, cardinal in ordinal_to_cardinal.items():
        if not use_ordinal_questions:
            value = re.sub(
                rf"\bSwali la {ordinal}\b",
                f"Swali namba {cardinal}",
                value,
                flags=re.I,
            )
        value = re.sub(
            rf"\bNamba ya {ordinal}\b",
            f"Namba {cardinal}",
            value,
            flags=re.I,
        )

    # PDF line breaks sometimes became full stops in the middle of a phrase.
    joiners = (
        r"ya|wa|na|kwa|katika|ili|kisha|ambayo|ambalo|ambazo|yenye|zenye|"
        r"kutoka|hadi"
    )
    value = re.sub(
        rf"\b({joiners})\.\s+(?=[A-Za-zÀ-ÿ])",
        r"\1 ",
        value,
        flags=re.I,
    )
    value = re.sub(
        r"\b(Zoezi la|Mfano wa|Kazi ya kufanya ya)\s+(kumi)\.\s+na\s+"
        r"(moja|mbili|tatu|nne|tano|sita|saba|nane|tisa)\b",
        r"\1 \2 na \3",
        value,
        flags=re.I,
    )

    # Numbered steps should sound like ordered instructions, not fragments.
    step_ordinals = {
        "moja": "kwanza", "mbili": "pili", "tatu": "tatu", "nne": "nne",
        "tano": "tano", "sita": "sita", "saba": "saba", "nane": "nane",
        "tisa": "tisa", "kumi": "kumi",
    }
    for number, ordinal in step_ordinals.items():
        value = re.sub(
            rf"\bHatua\.\s*(?:ya\s+)?{number}\b[.:]?",
            f"Hatua ya {ordinal}. ",
            value,
            flags=re.I,
        )

    # An equals sign followed by a blank answer must not be spoken as an
    # unfinished phrase. The calculation itself is still narrated.
    dangling = r"sawa sawa na|jumlisha|toa|zidisha kwa|gawanya kwa"
    value = re.sub(
        rf"\s+(?:{dangling})\s*(?=[.!?](?:\s|$)|$)",
        "",
        value,
        flags=re.I,
    )
    value = re.sub(r"(?:sawa sawa na\s+){2,}", "sawa sawa na ", value, flags=re.I)
    value = re.sub(r"\bjumlisha\s+Gawanya\b", "Gawanya", value, flags=re.I)

    # Parentheses are visual grouping marks. Pauses are clearer than reading
    # raw bracket names, while the words inside the brackets are preserved.
    value = value.replace("(", ", ").replace(")", ", ")

    # In money contexts, two decimal digits are cents rather than a generic
    # decimal sequence: "shilingi 80 nukta 75" -> "... na senti 75".
    digit_words = "|".join(DIGIT_WORD_VALUES)
    money_decimal = re.compile(
        rf"(\bshilingi\b[^.!?]{{0,150}}?)\s+nukta\s+({digit_words})\s+({digit_words})\b",
        re.I,
    )

    def money_decimal_words(match: re.Match[str]) -> str:
        tens = DIGIT_WORD_VALUES[match.group(2).lower()]
        ones = DIGIT_WORD_VALUES[match.group(3).lower()]
        return match.group(1).rstrip() + " na senti " + number_words(tens * 10 + ones)

    value = money_decimal.sub(money_decimal_words, value)

    # Coordinate extraction occasionally flattened a superscript 2 or 3 into
    # an ordinary word. Restore its mathematical meaning only in an explicit
    # area or volume sentence.
    metric = r"sentimeta|milimeta|kilometa|meta"
    value = re.sub(
        rf"(\beneo\b[^.!?]{{0,180}}?\b)({metric})\s+mbili\b",
        lambda match: match.group(1) + match.group(2) + " za mraba",
        value,
        flags=re.I,
    )
    value = re.sub(
        rf"(\bujazo\b[^.!?]{{0,180}}?\b)({metric})\s+tatu\b",
        lambda match: match.group(1) + match.group(2) + " za ujazo",
        value,
        flags=re.I,
    )

    value = value.replace("?.", "?").replace("!.", "!")
    value = re.sub(r"\s+([,.;:!?])", r"\1", value)
    value = re.sub(r"(?:\.\s*){2,}", ". ", value)
    return re.sub(r"\s+", " ", value).strip()


ADT_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
ADT_LETTER_PRONUNCIATIONS = {"A": "aa", "B": "be", "C": "che", "D": "de"}
ADT_SPOKEN_ROMAN_TOKENS = {
    "ai": "I", "vi": "V", "eksi": "X", "eli": "L",
    "si": "C", "di": "D", "emu": "M",
}
ADT_ROMAN_SYMBOL_NAMES = {
    "I": "i kubwa", "V": "vi kubwa", "X": "eksi kubwa", "L": "eli kubwa",
    "C": "che kubwa", "D": "de kubwa", "M": "emu kubwa",
}


def adt_roman_to_int(token: str) -> int:
    total = 0
    previous = 0
    for character in reversed(token.upper()):
        current = ADT_ROMAN_VALUES[character]
        if current < previous:
            total -= current
        else:
            total += current
            previous = current
    return total


def adt_describe_roman(token: str) -> str:
    token = token.upper()
    groups = []
    index = 0
    while index < len(token):
        end = index + 1
        while end < len(token) and token[end] == token[index]:
            end += 1
        count = end - index
        symbol_name = ADT_ROMAN_SYMBOL_NAMES[token[index]]
        if count == 1:
            groups.append("herufi " + symbol_name + " moja")
        else:
            groups.append("herufi " + symbol_name + " mara " + number_words(count))
        index = end
    construction = ", kisha ".join(groups)
    return (
        "alama ya Kirumi inayoundwa na " + construction
        + ", yenye thamani ya " + number_words(adt_roman_to_int(token))
    )


def adt_spoken_roman_to_words(match: re.Match) -> str:
    roman = "".join(ADT_SPOKEN_ROMAN_TOKENS[token.lower()] for token in match.group(0).split())
    return adt_describe_roman(roman)


def spoken(value: str, data_id: str = "") -> str:
    value = clean_existing_narration(value, data_id)
    value = value.replace("�", " toa ")
    page_match = re.match(r"pg(\d{3})_", data_id or "")
    page_number = int(page_match.group(1)) if page_match else 0
    for option, pronunciation in ADT_LETTER_PRONUNCIATIONS.items():
        value = re.sub(
            rf"\bKipengele\s+{option.lower()}\b",
            "Kipengele " + pronunciation,
            value,
            flags=re.I,
        )
    value = re.sub(r"\bKipengele\s+si\b", "Kipengele che", value, flags=re.I)
    value = re.sub(r"\bKipengele\s+di\b", "Kipengele de", value, flags=re.I)
    if 7 <= page_number <= 26 and data_id not in PAGE_NARRATION_OVERRIDES:
        value = re.sub(r"\bili\b", "kwa ajili ya", value, flags=re.I)
        value = re.sub(
            r"\(([IVXLCDM]+)\)",
            lambda match: adt_describe_roman(match.group(1)),
            value,
        )
        value = re.sub(
            r"(?<![A-Za-z])(?:ai|vi|eksi|eli|si|di|emu)(?:\s+(?:ai|vi|eksi|eli|si|di|emu))*(?![A-Za-z])",
            adt_spoken_roman_to_words,
            value,
            flags=re.I,
        )
        value = re.sub(
            r"(?<![A-Za-z(])\b[IVXLCDM]+\b(?![A-Za-z)])",
            lambda match: adt_describe_roman(match.group(0)),
            value,
        )
    value = re.sub(
        r"\(([a-d])\)",
        lambda match: " " + ADT_LETTER_PRONUNCIATIONS[match.group(1).upper()] + " ",
        value,
        flags=re.I,
    )
    value = re.sub(
        r"(?<![A-Za-z])([A-D])(?![A-Za-z])",
        lambda match: " " + ADT_LETTER_PRONUNCIATIONS[match.group(1).upper()] + " ",
        value,
        flags=re.I,
    )
    value = value.replace("©", " atimiliki ")
    value = re.sub(
        r"(?<!\w)www\.tie\.go\.tz(?!\w)",
        "dabiliyu dabiliyu dabiliyu doti tai doti goo doti tizedi",
        value,
        flags=re.I,
    )
    value = re.sub(
        r"(?<!\w)director\.general@tie\.go\.tz(?!\w)",
        "dairecta doti genero ati tai doti goo doti tizedi",
        value,
        flags=re.I,
    )
    value = re.sub(r"\bthamani\b", "samani", value, flags=re.I)
    # Book-wide Tanzanian Swahili institution, title, and URL pronunciations.
    value = re.sub(
        r"https?://ol\.tie\.go\.tz",
        "echititipiesi fowadi slash fowadi slash oli nukta tie nukta goo nukta Tanzania",
        value,
        flags=re.I,
    )
    value = re.sub(
        r"\bol\.tie\.go\.tz\b",
        "oli nukta tie nukta goo nukta Tanzania",
        value,
        flags=re.I,
    )
    value = value.replace("//", " mkaju ")
    value = re.sub(r"(?<!\w)SQA\s*-\s*DSM(?!\w)", "SQA, Dar es Salaam", value, flags=re.I)
    value = re.sub(r"(?<!\w)UDSM(?!\w)", "yudizim", value, flags=re.I)
    value = re.sub(r"(?<!\w)UDOM(?!\w)", "yudom", value, flags=re.I)
    value = re.sub(r"(?<!\w)DUCE(?!\w)", "duse", value, flags=re.I)
    value = re.sub(r"(?<!\w)SUA(?!\w)", "sua", value, flags=re.I)
    value = re.sub(r"(?<!\w)ARU(?!\w)", "aruu", value, flags=re.I)
    value = re.sub(r"(?<!\w)TET(?!\w)", "teti", value, flags=re.I)
    value = re.sub(r"(?<!\w)Dkt\.?(?=\s|$)", "dactari", value, flags=re.I)
    value = re.sub(r"(?<!\w)Bw\.?(?=\s|$)", "Bwana", value, flags=re.I)
    value = re.sub(r"(?<!\w)Bi\.?(?=\s|$)", "bibi", value, flags=re.I)
    # Book-wide arithmetic reading order and vertical-division pronunciation.
    value = re.sub(
        r"(?<!\d)\)\s*(\d[\d,]*)\s+(\d[\d,]*)",
        lambda match: f"{match.group(2)} ÷ {match.group(1)}",
        value,
    )
    value = re.sub(
        r"(\d[\d,]*)\s*\)\s*(\d[\d,]*)",
        lambda match: f"{match.group(2)} ÷ {match.group(1)}",
        value,
    )
    value = re.sub(r"\bhatua\s+ya\s+1\b", "hatua ya kwanza", value, flags=re.I)
    value = re.sub(r"\bhatua\s+ya\s+2\b", "hatua ya pili", value, flags=re.I)
    value = re.sub(r"\bhatua\s+1\b", "hatua ya kwanza", value, flags=re.I)
    value = re.sub(r"\bhatua\s+2\b", "hatua ya pili", value, flags=re.I)
    # Pronounce referenced arithmetic steps as Swahili ordinals.
    for step_number, step_word in (
        ("3", "tatu"),
        ("4", "nne"),
        ("5", "tano"),
        ("6", "sita"),
        ("7", "saba"),
        ("8", "nane"),
        ("9", "tisa"),
        ("10", "kumi"),
    ):
        value = re.sub(
            rf"\bhatua\s+ya\s+{step_number}\b",
            f"hatua ya {step_word}",
            value,
            flags=re.I,
        )
        value = re.sub(
            rf"\bhatua\s+{step_number}\b",
            f"hatua ya {step_word}",
            value,
            flags=re.I,
        )
    value = re.sub(
        r"(?<![\d,.])\d{4,}(?![\d,.])",
        lambda match: f"{int(match.group(0)):,}",
        value,
    )
    # Normalize time and Tanzanian money notation before generic number handling.
    page_match = re.match(r"pg(\d{3})_", data_id or "")
    page_number = int(page_match.group(1)) if page_match else 0
    if 151 <= page_number <= 168:
        value = re.sub(
            r"\b(\d{1,2}):(\d{2})\b",
            lambda match: f"saa {int(match.group(1))} na dakika {int(match.group(2))}",
            value,
        )
        value = re.sub(
            r"\bsaa\s+0?(\d{1,2})(\d{2})\b",
            lambda match: f"saa {int(match.group(1))} na dakika {int(match.group(2))}",
            value,
            flags=re.IGNORECASE,
        )
    if 169 <= page_number <= 184:
        value = re.sub(
            r"\bshilingi\s+([\d,]+)\.(\d{2})\b",
            lambda match: f"shilingi {match.group(1)} na senti {match.group(2)}",
            value,
            flags=re.IGNORECASE,
        )
        value = re.sub(
            r"\)\s*sh\s+st\s+(\d+)\s+(\d+)\s+(\d+)",
            lambda match: f"sh {match.group(2)} st {match.group(3)} ÷ {match.group(1)}",
            value,
            flags=re.IGNORECASE,
        )
        value = re.sub(
            r"\)\s*sh\s+(\d+)\s+(\d+)",
            lambda match: f"sh {match.group(2)} ÷ {match.group(1)}",
            value,
            flags=re.IGNORECASE,
        )
        value = re.sub(
            r"\bsh\s*([\d,]+)\.(\d{2})\b",
            lambda match: f"shilingi {match.group(1)} na senti {match.group(2)}",
            value,
            flags=re.IGNORECASE,
        )
        value = re.sub(r"\bsh\b", "shilingi", value, flags=re.IGNORECASE)
        value = re.sub(r"\bst\b", "senti", value, flags=re.IGNORECASE)
    # Reconstruct coordinate-extracted fraction formula order.
    page_match = re.match(r"pg(\d{3})_", data_id or "")
    page_number = int(page_match.group(1)) if page_match else 0
    if 112 <= page_number <= 150:
        value = re.sub(
            r"(?:=\s*)?([×÷])\s*=\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)",
            lambda match: (
                f"{match.group(2)} ya {match.group(4)} "
                f"{match.group(1)} {match.group(3)} ya {match.group(5)} ="
            ),
            value,
        )
        value = re.sub(
            r"(?:=\s*)?([×÷])\s*=\s*(\d+)\s+(\d+)\s+(\d+)",
            lambda match: (
                f"{match.group(2)} ya {match.group(4)} "
                f"{match.group(1)} {match.group(3)} ="
            ),
            value,
        )
        value = re.sub(
            r"(?<!\d)(\d+)\s*/\s*(\d+)(?!\d)",
            lambda match: f"{match.group(1)} ya {match.group(2)}",
            value,
        )

    # Read every decimal digit separately after the decimal point.
    value = re.sub(
        r"(?<![\d.])(\d+)\.(\d+)(?![\d.])",
        lambda match: (
            f"{match.group(1)} nukta {' '.join(match.group(2))}"
        ),
        value,
    )
    value = re.sub(r"\s*×\s*=\s*", " = ", value)
    value = re.sub(
        r"\bzidisha\s+kwa\s+sawa\s+sawa\s+na\b",
        "sawa sawa na",
        value,
        flags=re.I,
    )
    value = re.sub(r"\s*×\s*", " × ", value)
    value = re.sub(r"\s*÷\s*", " ÷ ", value)
    value = re.sub(r"\s*=\s*", " = ", value)
    # Pronounce squared and cubed metric units before plain unit abbreviations.
    for area_unit, area_name in (
        ("km", "kilometa za mraba"),
        ("m", "meta skweya"),
        ("sm", "sentimeta za mraba"),
        ("mm", "milimeta za mraba"),
    ):
        value = re.sub(
            rf"(?<![A-Za-z]){area_unit}\s*(?:²|\^2)(?!\d)",
            area_name + " ",
            value,
        )
    for volume_unit, volume_name in (
        ("m", "meta za ujazo"),
        ("sm", "sentimeta za ujazo"),
        ("mm", "milimeta za ujazo"),
    ):
        value = re.sub(
            rf"(?<![A-Za-z]){volume_unit}\s*(?:³|\^3)(?!\d)",
            volume_name + " ",
            value,
        )
    # Book-wide Tanzanian Swahili metric-unit pronunciation.
    if re.search(
        r"vipimo vya.*urefu|sentimeta|kilometa|\b(?:km|hm|dam|dm|sm|mm)\b",
        value,
        flags=re.I,
    ):
        for abbreviation, pronunciation in (
            ("km", "kilometa"),
            ("hm", "hektometa"),
            ("dam", "dekameta"),
            ("dm", "desimeta"),
            ("sm", "sentimeta"),
            ("mm", "milimeta"),
            ("m", "meta"),
        ):
            value = re.sub(
                rf"(?<![A-Za-z]){abbreviation}(?![A-Za-z])",
                pronunciation + " ",
                value,
            )

    if re.search(
        r"vipimo vya.*uzani|kilogramu|miligramu|\b(?:kg|hg|dag|dg|sg|mg)\b",
        value,
        flags=re.I,
    ):
        for abbreviation, pronunciation in (
            ("kg", "kilogramu"),
            ("hg", "hektogramu"),
            ("dag", "dekagramu"),
            ("dg", "desigramu"),
            ("sg", "sentigramu"),
            ("mg", "miligramu"),
            ("g", "gramu"),
            ("t", "tani"),
        ):
            value = re.sub(
                rf"(?<![A-Za-z]){abbreviation}(?![A-Za-z])",
                pronunciation + " ",
                value,
            )

    if re.search(r"vipimo vya.*ujazo|mililita|\bmL\b", value, flags=re.I):
        value = re.sub(r"(?<![A-Za-z])mL(?![A-Za-z])", "mililita ", value)
        value = re.sub(r"(?<![A-Za-z])L(?![A-Za-z])", "lita ", value)
    value = re.sub(r"HISABATI DRS 4 PB 2024\.indd\s+\d+", " ", value, flags=re.I)
    value = re.sub(r"\b\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}\b", " ", value)
    value = re.sub(
        r"\bISBN\s*:\s*978-9912-753-61-7\b",
        "aiesibini, tisa saba nane, tisa tisa moja mbili, saba tano tatu, sita moja, saba",
        value,
        flags=re.I,
    )
    value = re.sub(r"(?<!\w)S\.\s*L\.\s*P\.?(?!\w)", "esi elo pi", value, flags=re.I)
    value = re.sub(r"(?<=\d)\s*/\s*(?=\+?\d)", " au ", value)

    # Option labels are letters, not Roman numerals. Expand them before the
    # Roman pass so (c) is spoken as "Kipengele che", never "si".
    value = re.sub(
        r"\(([a-z])\)",
        lambda match: " Kipengele " + LETTERS[match.group(1).upper()] + ". ",
        value,
        flags=re.I,
    )

    # Web addresses and email addresses must be narrated as destinations,
    # before slash and punctuation characters are interpreted as mathematics.
    value = re.sub(
        r"https?://(?:www\.)?ol\.tie\.go\.tz|(?<![\w.])ol\.tie\.go\.tz",
        "tovuti ya maktaba mtandao ya Taasisi ya Elimu Tanzania",
        value,
        flags=re.I,
    )
    value = re.sub(
        r"director\.general@tie\.go\.tz",
        "barua pepe dairekta nukta jenerali ati tai nukta goo nukta tizi",
        value,
        flags=re.I,
    )
    value = re.sub(
        r"www\.tie\.go\.tz",
        "dabiliyu dabiliyu dabiliyu nukta tai nukta goo nukta tizi",
        value,
        flags=re.I,
    )

    if re.search(r"\b(?:Kirumi|numerali)\b", value, re.I):
        value = re.sub(r"(?<![A-Za-z])[IVXLCDM]+(?![A-Za-z])", spell_roman, value)

    value = re.sub(r"\b(\d{1,2}):(\d{2})\b",
                   lambda m: "saa " + number_words(int(m.group(1))) + " na dakika " + number_words(int(m.group(2))),
                   value)

    area_names = {"sm": "sentimeta", "m": "meta", "km": "kilometa"}
    page_match = re.match(r"pg(\d{3})_", data_id)
    page_number = int(page_match.group(1)) if page_match else 0
    if 99 <= page_number <= 111:
        value = re.sub(r"\b(sm|km|m)\s*(?:\^?2|²)\b",
                       lambda m: area_names[m.group(1).lower()] + " za eneo", value, flags=re.I)
    value = re.sub(r"\b(sentimeta|kilometa|milimeta|desimeta|kilogramu|miligramu|mililita|meta|gramu|lita|tani|shilingi|senti)(?=\d)",
                   r"\1 ", value, flags=re.I)
    value = re.sub(r"(?<![A-Za-z])(mm|sm|dm|km|kg|mg|ml|sh|st|m|g|l|t)(?![A-Za-z])",
                   lambda m: " " + UNITS[m.group(1).lower()] + " ", value, flags=re.I)
    value = re.sub(r"\bkilogram\b", "kilogramu", value, flags=re.I)
    value = re.sub(
        r"\b(saa|mwaka|wiki|siku|dakika|sekunde)(?=\d)",
        r"\1 ",
        value,
        flags=re.I,
    )

    value = re.sub(r"(?<!\d)(\d+)\s+(\d+)\s*/\s*(\d+)(?!\d)",
                   lambda m: number_words(int(m.group(1))) + " na " + fraction_words(int(m.group(2)), int(m.group(3))),
                   value)
    value = re.sub(r"(?<!\d)(\d+)\s*/\s*(\d+)(?!\d)",
                   lambda m: fraction_words(int(m.group(1)), int(m.group(2))), value)

    value = value.replace("%", " asilimia ")
    value = value.replace("×", " zidisha kwa ").replace("÷", " gawanya kwa ")
    value = value.replace("+", " jumlisha ").replace("−", " toa ").replace("–", " toa ")
    value = re.sub(r"(?<=\d)\s*-\s*(?=\d)", " toa ", value)
    value = value.replace("=", " sawa sawa na ")
    value = value.replace("<", " ni ndogo kuliko ").replace(">", " ni kubwa kuliko ")
    value = value.replace("/", " gawanya kwa ")

    value = re.sub(r"(?<![\w.])\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w.])\d+(?:\.\d+)?",
                   lambda m: number_token(m.group(0)), value)
    value = re.sub(r"\b[A-Z]{1,4}\b", spell, value)
    value = re.sub(r"\d+\.\d+", lambda m: number_token(m.group(0)), value)
    value = re.sub(r"\d+", lambda m: number_words(int(m.group(0))), value)

    for pattern, replacement in ((r"\bdirector\b", "dairekta"), (r"\btie\b", "tai"),
                                 (r"\bgo\b", "goo"), (r"\btz\b", "tizi"),
                                 (r"\bwww\b", "dabiliyu. dabiliyu. dabiliyu")):
        value = re.sub(pattern, replacement, value, flags=re.I)
    value = value.replace("@", " ati ")
    value = re.sub(r"_+", " dashi ", value)
    value = re.sub(r"\s*-\s*", " dashi ", value)
    value = add_pauses(value)
    value = re.sub(
        r"\s+(?:sawa sawa na|jumlisha|toa|zidisha kwa|gawanya kwa)\s*(?=[.!?](?:\s|$)|$)",
        "",
        value,
        flags=re.I,
    )
    value = re.sub(r"\s+,", ",", value)
    value = re.sub(r",\s*", ", ", value)
    return re.sub(r"\s+", " ", value).strip()


def repair_equation_order(value: str) -> str:
    value = re.sub(
        r"urefu\s*×\s*(\d+)\s+upana\s*(\d+)\s*\+\s*×",
        r"urefu × \1 + upana × \2",
        value,
        flags=re.I,
    )
    value = re.sub(
        r"(saa\s*\d+\s*=\s*dakika\s*\d+)\s+(\d+)\s*×",
        r"\1 × \2",
        value,
        flags=re.I,
    )
    value = re.sub(
        r"(Jumlisha [^:]{1,30}:\s*)(\d+)\s+(\d+)\s*=",
        r"\1\2 + \3 =",
        value,
        flags=re.I,
    )
    value = re.sub(
        r"(Toa [^:]{1,30}:\s*)(\d+)\s+(\d+)\s*=",
        r"\1\2 − \3 =",
        value,
        flags=re.I,
    )
    unit = r"(?:mm|sm|dm|km|kg|ml|m|g|l)\s+\d+(?:\.\d+)?"
    value = re.sub(
        rf"(?P<a>{unit})\s*×\s*(?P<b>\d+)\s+(?P<c>{unit})\s*\+\s*×\s*(?P<d>\d+)",
        lambda match: (
            f"{match.group('a')} × {match.group('b')} + "
            f"{match.group('c')} × {match.group('d')}"
        ),
        value,
        flags=re.I,
    )
    value = re.sub(
        rf"=\s*(?P<a>{unit})\s+(?P<b>{unit})\s*\+",
        lambda match: f"= {match.group('a')} + {match.group('b')}",
        value,
        flags=re.I,
    )
    return value


SEMANTIC_PAGE_AUDIO = {
    "pg073_gp001_tx001": (
        "Njia. Hatua ya kwanza. Toa gramu. Gramu 550 toa gramu 750 "
        "haitoshelezi. Chukua kilogramu 1 kutoka kilogramu 200, kisha "
        "badili kilogramu 1 kuwa gramu 1000. Jumlisha gramu 1000 jumlisha "
        "gramu 550 sawa sawa na gramu 1550. Toa gramu 1550 toa gramu 750 "
        "sawa sawa na gramu 800. Andika 800 katika safu ya gramu. Safu ya "
        "kilogramu zimebaki kilogramu 199. Hatua ya pili. Toa kilogramu. "
        "Kilogramu 199 toa kilogramu 300 haitoshelezi. Chukua tani 1 kutoka "
        "tani 6, kisha badili tani 1 kuwa kilogramu 1000. Jumlisha kilogramu "
        "1000 jumlisha kilogramu 199 sawa sawa na kilogramu 1199. Toa "
        "kilogramu 1199 toa kilogramu 300 sawa sawa na kilogramu 899. "
        "Andika 899 katika safu ya kilogramu. Safu ya tani zimebaki tani 5. "
        "Hatua ya tatu. Toa tani 5 toa tani 2 sawa sawa na tani 3. Andika "
        "tani 3 katika safu ya tani. Kwa hiyo, jibu ni tani 3 kilogramu 899 "
        "gramu 800. Zoezi la nane. Hesabu ya kwanza: tani 6 kilogramu 220 "
        "toa tani 4 kilogramu 114. Hesabu ya pili: tani 26 miligramu 370 "
        "toa tani 13 miligramu 250. Hesabu ya tatu: kilogramu 14 gramu 239 "
        "toa kilogramu 12 gramu 910."
    ),
    "pg179_gp001_tx001": (
        "Mfano wa nne. Shilingi 80.75 gawanya kwa 5 sawa sawa na ngapi? "
        "Njia. Gawanya shilingi 80 na senti 75 kwa 5. Shilingi 80.75 gawanya "
        "kwa 5 sawa sawa na shilingi 16.15. Kwa hiyo, jibu ni shilingi 16.15. "
        "Zoezi la tano. 1. Shilingi 46740.60 gawanya kwa 15. 2. Shilingi "
        "45363.00 gawanya kwa 3. 3. Shilingi 24289.20 gawanya kwa 12. 4. "
        "Shilingi 45442.50 gawanya kwa 15. 5. Shilingi 3200.40 gawanya kwa 8. "
        "6. Shilingi 91000.70 gawanya kwa 7. 7. Shilingi 136005.40 gawanya "
        "kwa 5. 8. Shilingi 391560.00 gawanya kwa 13. 9. Shilingi 465600.60 "
        "gawanya kwa 4. 10. Shilingi 364500.00 gawanya kwa 10. 11. Shilingi "
        "645000.00 gawanya kwa 8. 12. Shilingi 8526.00 gawanya kwa 116. 13. "
        "Shilingi 100000.80 gawanya kwa 24. 14. Shilingi 1740.60 gawanya kwa 12."
    ),
}


PAGE_NARRATION_OVERRIDES = {
    "pg001_gp001_tx001": """
Hisabati. Kitabu cha Mwanafunzi. Darasa la Nne.
Maelezo ya picha ya cheti. Hiki ni Cheti cha Ithibati namba 1637 kilichotolewa na Wizara ya Elimu, Sayansi na Teknolojia ya Jamhuri ya Muungano wa Tanzania.
Jina la chapisho ni Hisabati, Kitabu cha Mwanafunzi Darasa la Nne.
Mchapishaji ni Taasisi ya Elimu Tanzania. Mwandishi ni Taasisi ya Elimu Tanzania.
Aiesibini, tisa saba nane, tisa tisa moja mbili, saba tano tatu, sita moja, saba.
Cheti kinaeleza kuwa kitabu hiki kiliidhinishwa na Wizara ya Elimu, Sayansi na Teknolojia tarehe 11 Septemba 2024 kuwa kitabu cha kiada kwa mwanafunzi wa Darasa la Nne katika elimu ya msingi nchini Tanzania, kwa kuzingatia Muhtasari wa mwaka 2023.
Sehemu ya chini ya cheti ina sahihi ya Daktari Lyabwene Mtahabwa, Kamishna wa Elimu.
Chini ya jalada limeandikwa jina la mchapishaji, Taasisi ya Elimu Tanzania.
""",
    "pg002_gp001_tx001": """
atimiliki Taasisi ya Elimu Tanzania elfu mbili na ishirini na nne.
Toleo la kwanza elfu mbili na kumi na nane. Chapa ya Pili elfu mbili na ishirini na moja. Toleo la Pili elfu mbili na ishirini na nne.
Aiesibini, tisa saba nane, tisa tisa moja mbili, saba tano tatu, sita moja, saba.
Taasisi ya Elimu Tanzania. Eneo la Mikocheni. Mia moja na thelathini na mbili Barabara ya Ali Hassan Mwinyi.
Esi elo pi elfu thelathini na tano na tisini na nne. Elfu kumi na nne mia moja na kumi na mbili Dar es Salaam.
Simu: jumlisha mbili tano tano, saba tatu tano, sifuri nne moja, moja saba sifuri; au jumlisha mbili tano tano, saba tatu tano, sifuri nne moja, moja sita nane.
Barua pepe: dairecta doti genero ati tai doti goo doti tizedi.
Tovuti: dabiliyu dabiliyu dabiliyu doti tai doti goo doti tizedi.
Haki zote zimehifadhiwa. Hairuhusiwi kunakili, kurudufu, kuchapisha, kutafsiri wala kukitoa kitabu hiki kwa namna yoyote ile bila idhini ya maandishi kutoka Taasisi ya Elimu Tanzania.
""",
    "pg003_gp001_tx001": """
Yaliyomo. Shukurani, ukurasa wa nne. Utangulizi, ukurasa wa tano. Sura ya kwanza, Namba za Kirumi, ukurasa wa saba. Sura ya pili, Kuzidisha namba nzima, ukurasa wa ishirini na saba. Sura ya tatu, Kugawanya namba nzima, ukurasa wa arobaini na mbili. Sura ya nne, Vipimo vya urefu, uzani na ujazo, ukurasa wa hamsini na tano. Sura ya tano, Mzingo wa maumbo bapa, ukurasa wa themanini na nne. Sura ya sita, Eneo la maumbo bapa, ukurasa wa tisini na tisa. Sura ya saba, Sehemu, ukurasa wa mia moja na kumi na mbili. Sura ya nane, Desimali, ukurasa wa mia moja na thelathini na mbili. Sura ya tisa, Vipimo vya muda, ukurasa wa mia moja na hamsini na moja. Sura ya kumi, Fedha ya Tanzania, ukurasa wa mia moja na sitini na tisa.
""",
    "pg004_gp001_tx001": """
Shukurani.
Taasisi ya Elimu Tanzania, Teti, inatambua na kuthamini mchango muhimu wa washiriki kutoka taasisi mbalimbali za serikali na zisizo za serikali zilizoshiriki kufanikisha uandishi wa kitabu hiki cha mwanafunzi.
Kipekee, Teti inatoa shukurani kwa Chuo Kikuu cha Dar es Salaam, Yudizim; Chuo Kikuu cha Dodoma, Yudom; Chuo Kishiriki cha Elimu Dar es Salaam, Duse; Chuo Kikuu cha Ardhi, Aruu; Chuo Kikuu cha Sokoine, Sua; Idara ya Uthibiti Ubora wa Shule, vyuo vya ualimu na shule za msingi.
Pia, Teti inatoa shukurani za dhati kwa mchango uliotolewa na wataalamu wafuatao.
Waandishi.
Mwandishi wa kwanza ni Bibi Ivy pe Bimbiga, Teti.
Mwandishi wa pili ni Bwana Jonathan he Paskali, Teti.
Mwandishi wa tatu ni Daktari Kenneth re Nzowa, Teti.
Mwandishi wa nne ni Daktari Ahmada o Ally, Aruu.
Mwandishi wa tano ni Daktari Zubeda se Mussa, Duse.
Mwandishi wa sita ni Daktari Jason me Mkenyeleye, Yudom.
Mwandishi wa saba ni Daktari Emmanuel e Sinkwembe, Yudizim.
Mwandishi wa nane ni Daktari Linus ne Kisoma, Sua.
Wahariri.
Mhariri wa kwanza ni Daktari Makungu Mwanzalima, Yudizim.
Mhariri wa pili ni Bwana Elikana e Manyilizu, esi kyu ei Dar es Salaam.
Wachoraji.
Mchoraji wa kwanza ni Bwana Fikiri aa Msimbe, Teti.
Mchoraji wa pili ni Bibi Victoria re Mwinyi.
Msanifu.
Msanifu ni Bibi Pamela se Makusi.
Mratibu.
Mratibu ni Bibi Ivy pe Bimbiga.
Vile vile, Teti inatoa shukurani kwa walimu wote wa shule za msingi na wanafunzi walioshiriki katika ujaribishaji wa kitabu hiki.
Mwisho, Teti inaishukuru Serikali ya Jamhuri ya Muungano wa Tanzania kwa kutoa fedha zilizofanikisha kazi ya uandishi na uchapishaji wa kitabu hiki.
Sahihi ya Mkurugenzi Mkuu.
Daktari Aneth aa Komba.
Mkurugenzi Mkuu.
Taasisi ya Elimu Tanzania.
""",
    "pg005_gp001_tx001": """
Utangulizi.
Kitabu hiki cha Hisabati kimetayarishwa mahususi kwa ajili ya mwanafunzi wa Darasa la nne, Tanzania Bara.
Kitabu hiki kimeandaliwa kulingana na Muhtasari wa Somo la Hisabati Elimu ya Msingi Darasa la Tatu hadi la Sita uliotolewa na Wizara ya Elimu, Sayansi na Teknolojia mwaka elfu mbili na ishirini na tatu.
Aidha, kitabu hiki ni toleo la pili lililoboreshwa kutoka kitabu cha Hisabati Darasa la Nne kilichochapishwa mwaka elfu mbili na kumi na nane kwa kuzingatia Muhtasari wa mwaka elfu mbili na kumi na sita.
Kitabu hiki kina sura kumi ambazo ni Namba za Kirumi, Kuzidisha namba nzima, Kugawanya namba nzima, Vipimo vya urefu, Uzani na ujazo, Mzingo wa umbo bapa, Eneo la umbo bapa, Sehemu, Desimali, Vipimo vya muda, na Fedha ya Tanzania.
Kwa kujifunza maudhui ya kitabu hiki, utakuza umahiri wa kumudu misingi ya awali ya kihisabati na kutumia stadi za kihisabati katika kufikiri kimantiki, kutafsiri na kutatua matatizo ya maisha ya kila siku.
Maudhui ya sura hizi yamewasilishwa kwa njia ya matini, michoro, picha pamoja na kazi za vitendo.
Unashauriwa kufanya kazi zote na mazoezi yote yaliyomo katika kitabu hiki, pamoja na kazi nyingine utakazopewa na mwalimu.
Hii itakuwezesha kukuza maarifa na stadi zinazokusudiwa kwa mwanafunzi.
Jifunze zaidi kupitia maktaba mtandao.
Anuani ya kwanza ni echititipiesi, mkaju, oli doti tai doti goo doti tizedi.
Au tumia oli doti tai doti goo doti tizedi.
Maelezo ya picha ya msimbo.
Sehemu ya chini ya ukurasa ina picha ya msimbo wa kiu ari wenye umbo la mraba na mpangilio wa miraba myeusi na myeupe.
Msimbo huu unaweza kuchanganuliwa kwa kamera ya simu ili kufungua maktaba mtandao ya Taasisi ya Elimu Tanzania.
Mwanafunzi anaweza kuomba msaada wa mwalimu, mzazi au mlezi kuuchanganua.
Maktaba hiyo ina nyenzo za ziada za kujifunzia.
Chini ya ukurasa limeandikwa jina la mchapishaji, Taasisi ya Elimu Tanzania.
""",
    "pg007_gp001_tx001": """
Sura ya Kwanza. Namba za Kirumi.
Utangulizi.
Katika sura hii, utajifunza kusoma na kuandika namba moja hadi elfu moja kwa Kirumi.
Namba hizo kwa Kirumi huanzia herufi ai kubwa, yenye thamani ya moja, hadi herufi emu kubwa, yenye thamani ya elfu moja.
Namba za Kirumi zinatumika katika maeneo mbalimbali kama vile kurasa za awali za vitabu na nyuso za saa.
Umahiri utakaoujenga utakuwezesha kutumia namba za Kirumi katika miktadha mbalimbali.
Sehemu ya Fikiri.
Picha inaonesha mwanafunzi akiwa ameweka kidole kwenye kidevu kama mtu anayefikiria.
Swali la kufikiria ni, maisha bila namba yangekuwaje?
Namba za Kirumi kuanzia herufi ai kubwa hadi herufi eksi kubwa.
Namba nzima zinaundwa na tarakimu kumi, ambazo ni sifuri, moja, mbili, tatu, nne, tano, sita, saba, nane na tisa.
Namba za Kirumi huandikwa kwa kutumia herufi moja au muunganiko wa herufi za alfabeti.
Soma namba katika jedwali lifuatalo.
Maelezo ya jedwali.
Jedwali lina safu tatu na mistari mitano ya namba.
Safu ya kwanza ina numerali tunazotumia kawaida.
Safu ya pili ina namna numerali hiyo inavyoandikwa kwa Kirumi.
Safu ya tatu ina namba hiyo kwa maneno.
Sasa tusome kila mstari kwa utaratibu.
Mstari wa kwanza.
Numerali ni moja.
Kwa Kirumi inaandikwa kwa herufi ai kubwa moja, yenye thamani ya moja.
Kwa maneno ni moja.
Mstari wa pili.
Numerali ni mbili.
Kwa Kirumi inaandikwa kwa herufi ai kubwa mbili zinazofuatana, yaani ai, ai.
Kila herufi ai kubwa ina thamani ya moja.
Hivyo, moja jumlisha moja, sawa sawa na mbili.
Kwa maneno ni mbili.
Mstari wa tatu.
Numerali ni tatu.
Kwa Kirumi inaandikwa kwa herufi ai kubwa tatu zinazofuatana, yaani ai, ai, ai.
Hivyo, moja jumlisha moja jumlisha moja, sawa sawa na tatu.
Kwa maneno ni tatu.
Mstari wa nne.
Numerali ni nne.
Kwa Kirumi inaandikwa kwa herufi ai kubwa ikifuatiwa na herufi vi kubwa.
Herufi ai kubwa ikiwa kabla ya herufi vi kubwa, thamani ya moja hutolewa katika tano.
Hivyo, tano toa moja, sawa sawa na nne.
Kwa maneno ni nne.
Mstari wa tano.
Numerali ni tano.
Kwa Kirumi inaandikwa kwa herufi vi kubwa moja, yenye thamani ya tano.
Kwa maneno ni tano.
Kwa hiyo, jedwali linafundisha kuwa herufi ai kubwa ina thamani ya moja, na herufi vi kubwa ina thamani ya tano.
Mpangilio wa herufi hizo ndio unaotengeneza namba moja hadi tano kwa Kirumi.
""",
    "pg008_gp001_tx001": """
Mwendelezo wa jedwali la namba za Kirumi.
Jedwali linaendelea kutoka namba sita hadi namba kumi.
Kila mstari una numerali, namna inavyoandikwa kwa Kirumi, na namba kwa maneno.
Mstari wa sita.
Numerali ni sita.
Kwa Kirumi inaandikwa kwa herufi vi kubwa ikifuatiwa na herufi ai kubwa, yaani vi, ai.
Herufi vi kubwa ina samani ya tano na herufi ai kubwa ina samani ya moja.
Hivyo, tano jumlisha moja, sawa sawa na sita.
Kwa maneno ni sita.
Mstari wa saba.
Numerali ni saba.
Kwa Kirumi inaandikwa vi, ai, ai.
Hivyo, tano jumlisha moja jumlisha moja, sawa sawa na saba.
Kwa maneno ni saba.
Mstari wa nane.
Numerali ni nane.
Kwa Kirumi inaandikwa vi, ai, ai, ai.
Hivyo, tano jumlisha moja jumlisha moja jumlisha moja, sawa sawa na nane.
Kwa maneno ni nane.
Mstari wa tisa.
Numerali ni tisa.
Kwa Kirumi inaandikwa kwa herufi ai kubwa ikifuatiwa na herufi eksi kubwa, yaani ai, eksi.
Herufi ai kubwa ikiwa kabla ya herufi eksi kubwa, samani ya moja hutolewa katika kumi.
Hivyo, kumi toa moja, sawa sawa na tisa.
Kwa maneno ni tisa.
Mstari wa kumi.
Numerali ni kumi.
Kwa Kirumi inaandikwa kwa herufi eksi kubwa moja, yenye samani ya kumi.
Kwa maneno ni kumi.
Kazi ya kufanya ya kwanza. Kubainisha namba za Kirumi.
Kazi hii ina maelekezo matatu.
Maelekezo ya kwanza.
Tumia vyanzo mbalimbali vya kuaminika vilivyomo mtandaoni, kama vile Khan Akademi, ili kujifunza vitu vinavyotumia namba za Kirumi.
Maelekezo ya pili.
Andika majina ya vitu ulivyovipata kutoka katika maelekezo ya kwanza.
Maelekezo ya tatu.
Fikiria na ujibu swali hili. Kuna umuhimu gani kwako kufanya shughuli hii?
Kuandika namba za Kirumi kuanzia herufi ai kubwa hadi herufi eksi kubwa.
Herufi ai kubwa, yenye samani ya moja, inaweza kurudiwa ili kuunda namba nyingine.
Jedwali la kwanza lina safu ya numerali na safu ya namba kwa Kirumi.
Numerali moja inaandikwa kwa Kirumi kwa herufi ai kubwa moja.
Numerali mbili inaandikwa kwa herufi ai kubwa mbili, yaani ai, ai.
Numerali tatu inaandikwa kwa herufi ai kubwa tatu, yaani ai, ai, ai.
Herufi ai kubwa haiwezi kujirudia zaidi ya mara tatu katika namba moja.
Herufi ai kubwa, vi kubwa na eksi kubwa zinatumika kuunda namba nyingine za Kirumi.
Jedwali la pili linaonyesha numerali nne hadi tisa na namna zinavyoandikwa kwa Kirumi.
Numerali nne inaandikwa ai, vi. Herufi ai kubwa iko kabla ya vi kubwa, hivyo tano toa moja, sawa sawa na nne.
Numerali tano inaandikwa vi.
Numerali sita inaandikwa vi, ai. Tano jumlisha moja, sawa sawa na sita.
Numerali saba inaandikwa vi, ai, ai. Tano jumlisha moja jumlisha moja, sawa sawa na saba.
Numerali nane inaandikwa vi, ai, ai, ai. Tano jumlisha moja jumlisha moja jumlisha moja, sawa sawa na nane.
Numerali tisa inaandikwa ai, eksi. Herufi ai kubwa iko kabla ya eksi kubwa, hivyo kumi toa moja, sawa sawa na tisa.
Kwa hiyo, herufi yenye samani ndogo ikiwekwa baada ya herufi yenye samani kubwa, samani zake hujumlishwa.
Herufi yenye samani ndogo ikiwekwa kabla ya herufi yenye samani kubwa, samani ndogo hutolewa katika samani kubwa.
""",
    "pg009_gp001_tx001": """
Namba za Kirumi. Kanuni ya kujumlisha na kutoa.
Kanuni ya kwanza.
Namba ya Kirumi yenye samani ndogo ikiandikwa kulia, yaani baada ya namba ya Kirumi yenye samani sawa au kubwa zaidi, samani za alama hizo hujumlishwa.
Mfano wa kwanza.
Andika namba zifuatazo kwa numerali za kawaida.
Kipengele aa.
Namba ya Kirumi ni ai, ai.
Hii ni herufi ai kubwa mbili zinazofuatana.
Njia.
Moja jumlisha moja, sawa sawa na mbili.
Kwa hiyo, ai, ai, ni numerali mbili.
Kipengele be.
Namba ya Kirumi ni vi, ai.
Herufi vi kubwa ina samani ya tano, na herufi ai kubwa iliyo kulia ina samani ya moja.
Njia.
Tano jumlisha moja, sawa sawa na sita.
Kwa hiyo, vi, ai, ni numerali sita.
Kipengele che.
Namba ya Kirumi ni vi, ai, ai.
Herufi vi kubwa ina samani ya tano, na herufi ai kubwa mbili zilizo kulia zina jumla ya mbili.
Njia.
Tano jumlisha mbili, sawa sawa na saba.
Kwa hiyo, vi, ai, ai, ni numerali saba.
Kipengele de.
Namba ya Kirumi ni vi, ai, ai, ai.
Herufi vi kubwa ina samani ya tano, na herufi ai kubwa tatu zilizo kulia zina jumla ya tatu.
Njia.
Tano jumlisha tatu, sawa sawa na nane.
Kwa hiyo, vi, ai, ai, ai, ni numerali nane.
Kanuni ya pili.
Namba ya Kirumi yenye samani ndogo ikiandikwa kushoto, yaani kabla ya namba ya Kirumi yenye samani kubwa, samani ndogo hutolewa katika samani kubwa.
Mfano wa pili.
Andika namba zifuatazo kwa numerali za kawaida.
Kipengele aa.
Namba ya Kirumi ni ai, vi.
Herufi ai kubwa yenye samani ya moja iko kushoto, kabla ya herufi vi kubwa yenye samani ya tano.
Njia.
Tano toa moja, sawa sawa na nne.
Kwa hiyo, ai, vi, ni numerali nne.
Kipengele be.
Namba ya Kirumi ni ai, eksi.
Herufi ai kubwa yenye samani ya moja iko kushoto, kabla ya herufi eksi kubwa yenye samani ya kumi.
Njia.
Kumi toa moja, sawa sawa na tisa.
Kwa hiyo, ai, eksi, ni numerali tisa.
Kanuni ya kukumbuka.
Alama yenye samani ndogo ikiwa kulia, baada ya alama kubwa, jumlisha.
Alama yenye samani ndogo ikiwa kushoto, kabla ya alama kubwa, toa.
""",
    "pg010_gp001_tx001": """
Zoezi la kwanza.
Zoezi hili lina maswali matano.
Swali la kwanza.
Andika namba zifuatazo za Kirumi kuanzia ndogo hadi kubwa.
Alama ya kwanza ni ai, eksi.
Alama ya pili ni vi, ai.
Alama ya tatu ni eksi.
Alama ya nne ni ai, vi.
Alama ya tano ni vi, ai, ai.
Alama ya sita ni vi.
Alama ya saba ni vi, ai, ai, ai.
Swali la pili.
Badili namba zifuatazo za Kirumi kuwa numerali za kawaida.
Vi, ai, ai; ai, vi; vi, ai; vi; vi, ai, ai, ai; na ai, eksi.
Swali la tatu.
Badili numerali tatu, sita, saba, moja, nane, nne, kumi, tisa na tano kuwa namba za Kirumi.
Swali la nne.
Jaza namba zinazokosekana katika jedwali.
Maelezo ya jedwali la zoezi.
Jedwali lina mistari miwili.
Mstari wa kwanza unaitwa Namba kwa maneno.
Una maneno sita, saba, tisa, nne na kumi.
Mstari wa pili unaitwa Namba kwa Kirumi.
Katika mstari huu, kisanduku kilicho chini ya neno nne kina alama ai, vi.
Visanduku vilivyo chini ya sita, saba, tisa na kumi havijajazwa.
Jaza kila kisanduku kwa namba sahihi ya Kirumi.
Swali la tano.
Mzazi aliwanunulia watoto viatu vyenye namba eksi, vi, na vi, ai, ai.
Andika namba za viatu hivyo kwa numerali za kawaida.
Namba za Kirumi kuanzia kumi na moja hadi ishirini.
Soma namba zifuatazo katika jedwali.
Maelezo ya jedwali.
Jedwali lina mistari mitatu.
Mstari wa kwanza una namba kwa Kirumi.
Mstari wa pili una numerali za kawaida.
Mstari wa tatu una namba kwa maneno.
Sasa tusome kila safu.
Kumi na moja.
Kwa Kirumi inaandikwa eksi, ai.
Hii ni kumi jumlisha moja, sawa sawa na kumi na moja.
Kumi na mbili.
Kwa Kirumi inaandikwa eksi, ai, ai.
Hii ni kumi jumlisha mbili, sawa sawa na kumi na mbili.
Kumi na tatu.
Kwa Kirumi inaandikwa eksi, ai, ai, ai.
Hii ni kumi jumlisha tatu, sawa sawa na kumi na tatu.
Kumi na nne.
Kwa Kirumi inaandikwa eksi, ai, vi.
Alama ai, vi ina samani ya nne.
Hivyo, kumi jumlisha nne, sawa sawa na kumi na nne.
Kumi na tano.
Kwa Kirumi inaandikwa eksi, vi.
Kumi jumlisha tano, sawa sawa na kumi na tano.
Kumi na sita.
Kwa Kirumi inaandikwa eksi, vi, ai.
Kumi jumlisha tano jumlisha moja, sawa sawa na kumi na sita.
Kumi na saba.
Kwa Kirumi inaandikwa eksi, vi, ai, ai.
Kumi jumlisha tano jumlisha mbili, sawa sawa na kumi na saba.
Kumi na nane.
Kwa Kirumi inaandikwa eksi, vi, ai, ai, ai.
Kumi jumlisha tano jumlisha tatu, sawa sawa na kumi na nane.
Kumi na tisa.
Kwa Kirumi inaandikwa eksi, ai, eksi.
Alama ai, eksi ina samani ya tisa.
Hivyo, kumi jumlisha tisa, sawa sawa na kumi na tisa.
Ishirini.
Kwa Kirumi inaandikwa eksi, eksi.
Kumi jumlisha kumi, sawa sawa na ishirini.
Mfano wa kwanza.
Andika namba zifuatazo kwa Kirumi.
Kipengele aa, numerali kumi na nne.
Kipengele be, numerali kumi na saba.
Kipengele che, numerali kumi na tisa.
Tumia jedwali la kumi na moja hadi ishirini lililo juu kupata majibu.
""",
    "pg011_gp001_tx001": """
Njia.
Kipengele aa.
Kumi na nne sawa sawa na alama eksi jumlisha alama ai, vi.
Sawa sawa na alama eksi, ai, vi.
Kwa hiyo, kumi na nne kwa Kirumi ni eksi, ai, vi.
Kipengele be.
Kumi na saba sawa sawa na alama eksi jumlisha alama vi, ai, ai.
Sawa sawa na kumi na saba.
Kwa hiyo, kumi na saba kwa Kirumi ni eksi, vi, ai, ai.
Kipengele che.
Kumi na tisa sawa sawa na alama eksi jumlisha alama ai, eksi.
Sawa sawa na alama eksi, ai, eksi.
Kwa hiyo, kumi na tisa kwa Kirumi ni eksi, ai, eksi.
Mfano wa pili.
Badili namba zifuatazo kuwa numerali.
Kipengele aa, alama eksi, ai, ai.
Kipengele be, alama eksi, vi.
Kipengele che, alama eksi, vi, ai, ai, ai.
Njia.
Kipengele aa.
Alama eksi, ai, ai sawa sawa na kumi jumlisha mbili.
Sawa sawa na kumi na mbili.
Kwa hiyo, eksi, ai, ai ni numerali kumi na mbili.
Kipengele be.
Alama eksi, vi sawa sawa na kumi jumlisha tano.
Sawa sawa na kumi na tano.
Kwa hiyo, eksi, vi ni numerali kumi na tano.
Kipengele che.
Alama eksi, vi, ai, ai, ai sawa sawa na kumi jumlisha nane.
Sawa sawa na kumi na nane.
Kwa hiyo, eksi, vi, ai, ai, ai ni numerali kumi na nane.
Zoezi la pili.
Swali la kwanza.
Andika namba yenye samani kubwa katika orodha hii:
eksi, ai, ai;
eksi, ai, ai, ai;
eksi, vi;
eksi, ai, eksi;
eksi, vi, ai;
eksi, vi, ai, ai;
eksi, vi, ai, ai, ai;
na eksi, ai, vi.
Swali la pili.
Andika namba zifuatazo kwa maneno.
Kipengele aa, eksi, ai, vi.
Kipengele be, eksi, vi, ai.
Kipengele che, eksi, eksi.
Kipengele de, eksi, ai.
Kipengele e, eksi, vi.
Kipengele fe, eksi, ai, eksi.
""",
    "pg012_gp001_tx001": """
Zoezi la pili linaendelea. Swali la tatu. Kadi ziliandikwa numerali kumi na tisa, kumi na saba, kumi na tatu, kumi na sita, ishirini, kumi na nne, kumi na mbili, kumi na nane, kumi na moja na kumi na tano. Andika namba hizo kwa namba za Kirumi, kisha zipange kuanzia namba yenye samani ndogo hadi namba yenye samani kubwa. Swali la nne. Badili eksi, ai; eksi, vi, ai, ai, ai; eksi, vi; eksi, vi, ai, ai; na eksi, ai, ai kwa numerali. Swali la tano. Andika namba zinazokosekana katika kila mpangilio. Kipengele aa. Eksi; nafasi tupu; eksi, ai, vi; eksi, vi, ai; nafasi tupu; eksi, eksi. Mpangilio huu unaongezeka kwa samani sawa katika kila hatua. Jaza nafasi bila kubadilisha utaratibu huo. Kipengele be. Nafasi tupu; eksi, ai, vi; nafasi tupu; eksi, ai, ai; nafasi tupu; eksi. Mpangilio huu unapungua kwa samani sawa katika kila hatua. Jaza nafasi kwa kufuata utaratibu huo. Swali la sita. Soma uso wa saa, kisha andika muda huo kwa numerali. Maelezo ya mchoro wa saa. Saa ni ya mviringo na ina namba za Kirumi kuanzia ai hadi eksi, ai, ai. Mkono mfupi mweusi unaelekea kwenye alama eksi. Mkono mrefu mweusi unaelekea kwenye alama ai, ai. Mkono mwembamba mwekundu unaelekea juu kwenye alama eksi, ai, ai. Kwa kusoma muda, tumia mkono mfupi kuonesha saa na mkono mrefu kuonesha dakika. Kisha andika muda kwa numerali. Namba za Kirumi kuanzia ishirini na moja hadi thelathini na tatu. Maelezo ya jedwali. Jedwali lina mistari miwili. Mstari wa kwanza una numerali kuanzia ishirini na moja hadi thelathini na tatu. Mstari wa pili una namba inayolingana kwa Kirumi. Soma kila safu kutoka juu kwenda chini. Ishirini na moja ni eksi, eksi, ai. Ishirini na mbili ni eksi, eksi, ai, ai. Ishirini na tatu ni eksi, eksi, ai, ai, ai. Ishirini na nne ni eksi, eksi, ai, vi. Ishirini na tano ni eksi, eksi, vi. Ishirini na sita ni eksi, eksi, vi, ai. Ishirini na saba ni eksi, eksi, vi, ai, ai. Ishirini na nane ni eksi, eksi, vi, ai, ai, ai. Ishirini na tisa ni eksi, eksi, ai, eksi. Thelathini ni eksi eksi eksi. Thelathini na moja ni eksi eksi eksi ai. Thelathini na mbili ni eksi eksi eksi ai ai. Thelathini na tatu ni eksi eksi eksi ai ai ai.
""",
    "pg013_gp001_tx001": """
Mifano ya kubadili numerali na namba za Kirumi, kisha mwanzo wa Zoezi la tatu.
Mfano wa kwanza. Andika numerali zifuatazo kwa Kirumi.
Kipengele aa. Numerali ishirini na nne.
Njia. Andika ishirini na nne kama ishirini jumlisha nne.
Ishirini huandikwa eksi, eksi.
Nne huandikwa ai, vi, kwa sababu ai iko kabla ya vi; tano toa moja sawa sawa na nne.
Unganisha alama. Jibu ni eksi, eksi, ai, vi.
Kwa hiyo, ishirini na nne huandikwa eksi, eksi, ai, vi.
Kipengele be. Numerali thelathini na saba.
Njia. Andika thelathini na saba kama thelathini jumlisha saba.
Thelathini huandikwa eksi mara tatu.
Saba huandikwa vi, ai, ai; yaani tano jumlisha mbili.
Unganisha alama. Jibu ni eksi mara tatu, vi, ai, ai.
Kwa hiyo, thelathini na saba huandikwa eksi mara tatu, vi, ai, ai.
Kipengele che. Numerali ishirini na saba.
Njia. Andika ishirini na saba kama ishirini jumlisha saba.
Ishirini ni eksi, eksi. Saba ni vi, ai, ai.
Unganisha alama. Jibu ni eksi, eksi, vi, ai, ai.
Kwa hiyo, ishirini na saba huandikwa eksi, eksi, vi, ai, ai.
Mfano wa pili. Andika namba za Kirumi kwa numerali.
Kipengele aa. Alama ni eksi, eksi, ai.
Eksi mbili zina samani ya ishirini. Ai ina samani ya moja.
Ishirini jumlisha moja sawa sawa na ishirini na moja.
Kwa hiyo, eksi, eksi, ai ni numerali ishirini na moja.
Kipengele be. Alama ni eksi mara tatu, ai mara tatu.
Eksi tatu zina samani ya thelathini. Ai tatu zina samani ya tatu.
Thelathini jumlisha tatu sawa sawa na thelathini na tatu.
Kwa hiyo, eksi mara tatu, ai mara tatu ni numerali thelathini na tatu.
Zoezi la tatu.
Swali la kwanza. Andika numerali zifuatazo kwa Kirumi.
Kipengele aa, ishirini na tisa.
Kipengele be, ishirini na sita.
Kipengele che, thelathini na mbili.
Kipengele de, ishirini na tatu.
Tenganisha kila numerali katika makumi na mamoja, badili kila sehemu kuwa alama za Kirumi, kisha unganisha alama hizo.
Zoezi hili linaendelea katika sehemu inayofuata.
""",
    "pg014_gp001_tx001": """
Zoezi la tatu linaendelea.
Swali la pili. Andika namba zifuatazo kwa numerali.
Swali aa. Eksi eksi ai ai.
Swali be. Eksi eksi eksi ai.
Swali che. Eksi eksi eksi.
Swali de. Eksi eksi vi.
Swali la tatu. Andika namba za Kirumi zinazokosekana katika mipangilio ifuatayo.
Swali aa. Eksi eksi ai, nafasi wazi, eksi eksi ai ai ai, nafasi wazi, nafasi wazi, eksi eksi vi ai.
Swali be. Eksi eksi ai vi, nafasi wazi, eksi eksi vi ai, nafasi wazi, nafasi wazi, eksi eksi ai eksi, nafasi wazi, nafasi wazi, nafasi wazi.
Swali che. Eksi eksi eksi ai ai, nafasi wazi, eksi eksi eksi, nafasi wazi, eksi eksi vi ai ai ai, nafasi wazi, eksi eksi vi ai.
Swali de. Nafasi wazi, nafasi wazi, eksi eksi vi, nafasi wazi, eksi eksi ai ai ai, eksi eksi ai ai, nafasi wazi.
Swali la nne. Wanafunzi walipewa kadi zenye namba zifuatazo.
Jedwali lina safu ya mwanafunzi na safu za kadi zao. John ana kadi eksi eksi ai eksi. Asha ana kadi eksi eksi. Ali ana kadi eksi eksi eksi ai ai. Rose ana kadi eksi vi ai ai.
Swali aa. Je, nani alipewa kadi yenye namba ya samani kubwa?
Swali be. Andika kadi yenye namba ya samani kubwa kwa numerali.
Namba za Kirumi eksi eksi eksi ai vi hadi eli.
Soma namba zifuatazo.
Eksi eksi eksi ai vi; eksi eksi eksi vi; eksi eksi eksi vi ai; eksi eksi eksi vi ai ai; eksi eksi eksi vi ai ai ai; eksi eksi eksi ai eksi; eksi eli; eksi eli ai; eksi eli ai ai; eksi eli ai ai ai; eksi eli ai vi; eksi eli vi; eksi eli vi ai; eksi eli vi ai ai; eksi eli vi ai ai ai; eksi eli ai eksi; na eli.
Mfano wa kwanza. Andika namba zifuatazo kwa Kirumi.
Swali aa. Thelathini na nne.
Swali be. Arobaini na moja.
Swali che. Arobaini na tano.
Njia.
Swali aa. Thelathini na nne sawa sawa na eksi eksi eksi jumlisha ai vi, sawa sawa na eksi eksi eksi ai vi. Kwa hiyo, thelathini na nne ni eksi eksi eksi ai vi.
Swali be. Arobaini na moja sawa sawa na eksi eli jumlisha ai, sawa sawa na eksi eli ai. Kwa hiyo, arobaini na moja ni eksi eli ai.
Njia ya swali che inaendelea.
""",
    "pg015_gp001_tx001": """
Mfano wa kwanza unaendelea. Njia. Swali che. Arobaini na tano sawa sawa na arobaini jumlisha tano, sawa sawa na eksi eli vi. Mfano wa pili. Andika namba hizi za Kirumi kwa numerali: eksi eksi eksi vi ai ai; eksi eli ai ai ai; na eksi eli ai eksi. Njia. Swali aa. Eksi eksi eksi vi ai ai sawa sawa na thelathini jumlisha saba, sawa sawa na thelathini na saba. Swali be. Eksi eli ai ai ai sawa sawa na arobaini jumlisha tatu, sawa sawa na arobaini na tatu. Swali che. Eksi eli ai eksi sawa sawa na arobaini jumlisha tisa, sawa sawa na arobaini na tisa. Zoezi la nne.
Swali la kwanza. Andika namba zifuatazo kwa Kirumi.
Aa. Arobaini na nne.
Be. Thelathini na tisa.
Che. Thelathini na tano.
De. Arobaini na sita.
Swali la pili. Andika namba zifuatazo kwa numerali.
Aa. Eksi eksi eksi vi ai.
Be. Eksi eli vi ai ai ai.
Che. Eksi eli ai.
De. Eksi eksi eksi ai vi.
Swali la tatu. Andika namba za Kirumi zinazokosekana katika kila mfululizo ufuatao.
Aa. Eksi eksi eksi ai vi, nafasi wazi, eksi eksi eksi vi ai, nafasi wazi, nafasi wazi, eksi eksi eksi ai eksi.
Be. Eksi eksi eksi vi ai, eksi eksi eksi vi ai ai ai, nafasi wazi, eksi eli ai ai, eksi eli ai vi, nafasi wazi, nafasi wazi, nafasi wazi.
Che. Eli, nafasi wazi, eksi eli ai vi, nafasi wazi, eksi eksi eksi vi ai ai ai, eksi eksi eksi ai ai.
""",
    "pg016_gp001_tx001": """
Zoezi la nne linaendelea.
Swali la nne. Jaza namba zinazokosekana katika jedwali lifuatalo.
Mstari wa numerali. Nafasi wazi; thelathini na tisa; nafasi wazi; arobaini na sita.
Mstari wa namba kwa Kirumi. Eksi eksi eksi vi ai; nafasi wazi; eksi eli ai ai ai; nafasi wazi.
Swali la tano. Jaza namba zinazokosekana katika kila mpangilio.
Aa. Eksi eksi eksi ai ai, nafasi wazi, eksi eksi eksi vi ai, nafasi wazi, nafasi wazi.
Be. Eksi, nafasi wazi, eksi eksi, eksi eksi vi, nafasi wazi, nafasi wazi, eksi eli.
Che. Eli, nafasi wazi, nafasi wazi, nafasi wazi, eksi eksi eksi, eksi eksi vi.
De. Eksi eksi eksi vi, eksi eksi eksi vi ai ai, nafasi wazi, eksi eli ai, nafasi wazi, eksi eli vi.
Swali la sita. Panga vijiti kuonesha arobaini na nane inavyoandikwa kwa Kirumi, kisha andika namba hii.
Swali la saba. Nuru aliona bango limeandikwa namba eksi eli ai vi. Hiyo ni namba gani kwa numerali?
Swali la nane. Andika namba zifuatazo kwa maneno.
Aa. Eksi eli ai eksi.
Be. Eksi eksi eksi vi ai.
Che. Eksi eli vi.
De. Eksi eksi eksi vi ai ai.
Swali la tisa. Badili namba zifuatazo kuwa namba za Kirumi.
Aa. Arobaini na mbili.
Be. Thelathini na saba.
Che. Thelathini na tisa.
De. Arobaini na tatu.
Swali la kumi. Andika namba zifuatazo kwa maneno.
Aa. Eksi eli ai ai.
Be. Eksi eksi eksi vi ai ai ai.
Che. Eksi eksi eksi ai eksi.
De. Eksi eli vi ai ai.
""",
    "pg017_gp001_tx001": """
Namba za Kirumi eli hadi si. Soma namba zifuatazo. Jedwali linaonesha numerali, namba za Kirumi, na namba kwa maneno. Numerali hamsini. Namba ya Kirumi eli. Namba kwa maneno, hamsini. Numerali sitini. Namba ya Kirumi eli eksi. Namba kwa maneno, sitini. Numerali sabini. Namba ya Kirumi eli eksi eksi. Namba kwa maneno, sabini. Numerali themanini. Namba ya Kirumi eli eksi eksi eksi. Namba kwa maneno, themanini. Numerali tisini. Namba ya Kirumi eksi si. Namba kwa maneno, tisini. Numerali mia moja. Namba ya Kirumi si. Namba kwa maneno, mia moja. Namba ai, eksi na si ni namba pekee za Kirumi ambazo zikiandikwa kushoto kwa namba yenye samani kubwa, hupunguzwa na zikiandikwa kulia, huongezwa. Namba hizi haziwezi kujirudia zikiandikwa kushoto kwa namba kubwa. Pia, namba hizi haziwezi kujirudia zaidi ya mara tatu kwa mfululizo zikiandikwa kulia kwa namba kubwa. Namba hizi kwa numerali ni moja, kumi na mia moja. Namba ai vi na ai eksi zinawakilisha mamoja. Kwa hiyo, namba hizi zikiandikwa mbele ya namba zenye samani kubwa hujumlishwa. Soma namba katika jedwali lifuatalo.
Namba kwa Kirumi ni eli vi. Namba hiyo kwa maneno ni hamsini na tano. Kwa numerali ni hamsini na tano.
Namba kwa Kirumi ni eli ai eksi. Namba hiyo kwa maneno ni hamsini na tisa. Kwa numerali ni hamsini na tisa.
Namba kwa Kirumi ni eli eksi eksi eksi ai eksi. Namba hiyo kwa maneno ni themanini na tisa. Kwa numerali ni themanini na tisa.
Namba kwa Kirumi ni eli eksi eksi ai ai. Namba hiyo kwa maneno ni sabini na mbili. Kwa numerali ni sabini na mbili.
Namba kwa Kirumi ni eksi si ai eksi. Namba hiyo kwa maneno ni tisini na tisa. Kwa numerali ni tisini na tisa.
Namba kwa Kirumi ni eli eksi ai vi. Namba hiyo kwa maneno ni sitini na nne. Kwa numerali ni sitini na nne.
Namba kwa Kirumi ni eli vi ai ai ai. Namba hiyo kwa maneno ni hamsini na nane. Kwa numerali ni hamsini na nane.
Namba kwa Kirumi ni eli eksi ai. Namba hiyo kwa maneno ni sitini na moja. Kwa numerali ni sitini na moja.
Namba kwa Kirumi ni eli eksi eksi ai ai ai. Namba hiyo kwa maneno ni sabini na tatu. Kwa numerali ni sabini na tatu.
Namba kwa Kirumi ni eli eksi eksi eksi vi. Namba hiyo kwa maneno ni themanini na tano. Kwa numerali ni themanini na tano.
""",
    "pg018_gp001_tx001": """
Mfano wa kwanza. Andika namba hizi za Kirumi kwa maneno: eli eksi vi; eli eksi eksi vi ai; eksi si ai eksi; na eli ai vi.
Njia.
Swali aa. Eli eksi vi sawa sawa na sitini jumlisha tano, sawa sawa na sitini na tano.
Swali be. Eli eksi eksi vi ai sawa sawa na sabini jumlisha sita, sawa sawa na sabini na sita.
Swali che. Eksi si ai eksi sawa sawa na tisini jumlisha tisa, sawa sawa na tisini na tisa.
Swali de. Eli ai vi sawa sawa na hamsini jumlisha nne, sawa sawa na hamsini na nne.
Mfano wa pili. Andika namba hizi kwa namba za Kirumi: hamsini na tatu, sitini na saba, hamsini na saba, na themanini na nane.
Njia.
Swali aa. Hamsini na tatu sawa sawa na hamsini jumlisha tatu, sawa sawa na eli ai ai ai.
Swali be. Sitini na saba sawa sawa na sitini jumlisha saba, sawa sawa na eli eksi vi ai ai.
Swali che na swali de yanaendelea.
""",
    "pg019_gp001_tx001": """
Mfano wa pili unaendelea.
Kipengele che. Hamsini na saba ni sawa na namba ya Kirumi eli, jumlisha namba ya Kirumi vi ai ai. Ni sawa na namba ya Kirumi eli vi ai ai. Kwa hiyo, hamsini na saba ni namba ya Kirumi eli vi ai ai.
Kipengele de. Themanini na nane ni sawa na namba ya Kirumi eli eksi eksi eksi, jumlisha namba ya Kirumi vi ai ai ai. Ni sawa na namba ya Kirumi eli eksi eksi eksi vi ai ai ai. Kwa hiyo, themanini na nane ni namba ya Kirumi eli eksi eksi eksi vi ai ai ai.
Zoezi la tano.
Swali la kwanza. Andika namba zifuatazo kwa maneno. Kipengele aa, namba ya Kirumi eli eksi vi ai ai. Kipengele be, namba ya Kirumi eksi si. Kipengele che, namba ya Kirumi eli eksi eksi eksi ai ai. Kipengele de, namba ya Kirumi eksi si vi ai ai ai.
Swali la pili. Andika namba zifuatazo kwa Kirumi. Kipengele aa, hamsini na mbili. Kipengele be, sitini na sita. Kipengele che, sabini. Kipengele de, tisini na tatu.
Swali la tatu. Andika namba zifuatazo kuanzia namba yenye thamani ndogo hadi kubwa. Namba za Kirumi ni: si; ai; eksi; eli; vi; eli eksi vi; eli eksi eksi eksi vi; eksi si vi; eli vi; na eli eksi eksi vi.
Swali la nne. Andika namba za Kirumi zinazokosekana katika mfululizo wa namba zifuatazo. Eli eksi eksi eksi, nafasi wazi; eli eksi eksi eksi ai ai, nafasi wazi; eli eksi eksi eksi ai vi, nafasi wazi.
Namba za Kirumi si hadi di. Namba si na di ni namba pekee za Kirumi zinazowakilishwa na mamia. Namba si huwakilisha mia moja na namba di huwakilisha mia tano. Namba si ikiwa kushoto mwa di, thamani yake hupungua kutoka kwa namba di; na ikiwa kulia mwa di, thamani yake inaongezwa kwa di. Namba si ikiwa kushoto mwa di lazima iwe moja, na ikiwa kulia mwa di zisizidi tatu.
Kwa mfano: kipengele aa, si di; kipengele be, di si si; kipengele che, di si si si.
""",
    "pg020_gp001_tx001": """
Ukurasa wa 20. Soma namba zifuatazo. Jedwali la kwanza.
Safu ya kwanza. Numerali mia moja. Namba kwa Kirumi, si. Namba kwa maneno, mia moja.
Safu ya pili. Numerali mia mbili. Namba kwa Kirumi, si si. Namba kwa maneno, mia mbili.
Safu ya tatu. Numerali mia tatu. Namba kwa Kirumi, si si si. Namba kwa maneno, mia tatu.
Safu ya nne. Numerali mia nne. Namba kwa Kirumi, si di. Namba kwa maneno, mia nne.
Safu ya tano. Numerali mia tano. Namba kwa Kirumi, di. Namba kwa maneno, mia tano.
Soma namba zifuatazo. Jedwali la pili lina safu tatu: Namba kwa Kirumi, Namba kwa maneno, na Numerali.
Mstari wa kwanza. Namba kwa Kirumi, si ai vi. Namba kwa maneno, mia moja na nne. Numerali, mia moja na nne.
Mstari wa pili. Namba kwa Kirumi, si eksi ai eksi. Namba kwa maneno, mia moja kumi na tisa. Numerali, mia moja kumi na tisa.
Mstari wa tatu. Namba kwa Kirumi, si eli eksi eksi vi ai. Namba kwa maneno, mia moja sabini na sita. Numerali, mia moja sabini na sita.
Mstari wa nne. Namba kwa Kirumi, si si eksi eksi ai ai. Namba kwa maneno, mia mbili ishiri na mbili. Numerali, mia mbili ishirini na mbili.
Mstari wa tano. Namba kwa Kirumi, si si si eksi eli ai ai ai. Namba kwa maneno, mia tatu arobaini na tatu. Numerali, mia tatu arobaini na tatu.
Mstari wa sita. Namba kwa Kirumi, si si eksi eksi vi. Namba kwa maneno, mia mbili ishirini na tano. Numerali, mia mbili ishirini na tano.
Mstari wa saba. Namba kwa Kirumi, si si si eksi eksi eksi vi ai ai ai. Namba kwa maneno, mia tatu thelathini na nane. Numerali, mia tatu thelathini na nane.
Mstari wa nane. Namba kwa Kirumi, si di eksi vi ai ai. Namba kwa maneno, mia nne kumi na saba. Numerali, mia nne kumi na saba.
Mstari wa tisa. Namba kwa Kirumi, si si eli ai vi. Namba kwa maneno, mia mbili hamsini na nne. Numerali, mia mbili hamsini na nne.
Mstari wa kumi. Namba kwa Kirumi, si di eksi eksi eksi ai. Namba kwa maneno, mia nne thelathini na moja. Numerali, mia nne thelathini na moja.
""",
    "pg021_gp001_tx001": """
Mfano wa kwanza. Andika namba mia mbili na tano, na mia tatu sitini na mbili, kwa namba za Kirumi.
Njia.
Swali aa. Mia mbili na tano sawa sawa na mia mbili jumlisha tano, sawa sawa na si si vi.
Swali be. Mia tatu sitini na mbili sawa sawa na mia tatu jumlisha sitini na mbili, sawa sawa na si si si eli eksi ai ai.
Mfano wa pili. Andika namba hizi za Kirumi kwa maneno: si eksi vi ai ai; na si di eksi eli vi ai.
Njia.
Swali aa. Si eksi vi ai ai ni mia moja kumi na saba.
Swali be. Si di eksi eli vi ai ni mia nne arobaini na sita.
Zoezi la sita.
Swali la kwanza. Andika namba hizi za Kirumi kwa maneno: si si si eksi eksi eksi; si si eksi ai eksi; si di eksi eli vi ai ai; na si si eksi si ai ai.
Swali la pili. Andika namba hizi zilizoandikwa kwa maneno kwa namba za Kirumi: mia nne arobaini na nne; mia moja kumi na tano; mia mbili na tisa; na mia nne hamsini na nne.
Swali la tatu. Andika namba hizi kwa namba za Kirumi: mia moja na nane; mia tatu sabini na nne; mia nne thelathini na tano; na mia nne arobaini na mbili.
Swali la nne. Umbali kati ya miji miwili ni di si eli eksi eksi vi ai ai ai kilometa. Andika umbali huo kwa numerali.
""",
    "pg022_gp001_tx001": """
Namba za Kirumi mia tano hadi elfu moja.
Alama di ina samani ya mia tano. Alama emu ina samani ya elfu moja. Alama si ikiwekwa kushoto mwa emu, samani ya si hutolewa kutoka kwa emu. Kwa hiyo, si emu ni mia tisa.
Jedwali la kwanza lina safu tatu: numerali, namba ya Kirumi, na namba kwa maneno.
Mia tano ni di. Mia sita ni di si. Mia saba ni di si si. Mia nane ni di si si si. Mia tisa ni si emu. Elfu moja ni emu.
Jedwali la pili lina mifano sita ya namba za Kirumi na numerali zake.
Di eksi ai ni mia tano kumi na moja.
Di si si eksi si ai eksi ni mia saba tisini na tisa.
Di si eli eksi eksi vi ai ni mia sita sabini na nne.
Si emu eli eksi eksi eksi ai vi ni mia tisa themanini na nne.
Di eli ni mia tano hamsini.
Di si si eksi eksi vi ai ai ai ni mia saba ishirini na nane.
Mfano wa kwanza. Andika namba hizi za Kirumi kwa numerali: si emu ai eksi; na di si si eli eksi eksi ai vi.
Njia inaendelea.
""",
    "pg023_gp001_tx001": """
Mfano wa kwanza unaendelea.
Njia.
Swali aa. Si emu ai eksi sawa sawa na mia tisa jumlisha tisa, sawa sawa na mia tisa na tisa.
Swali be. Di si si eli eksi eksi ai vi sawa sawa na mia saba jumlisha sabini na nne, sawa sawa na mia saba sabini na nne.
Mfano wa pili. Andika namba hizi kwa namba za Kirumi: mia tano sabini na sita; mia sita themanini na nane; mia nane arobaini na mbili; na mia tisa sitini na nne.
Njia.
Swali aa. Mia tano sabini na sita sawa sawa na mia tano jumlisha sabini na sita, sawa sawa na di eli eksi eksi vi ai.
Swali be. Mia sita themanini na nane sawa sawa na mia sita jumlisha themanini na nane, sawa sawa na di si eli eksi eksi eksi vi ai ai ai.
Swali che. Mia nane arobaini na mbili sawa sawa na mia nane jumlisha arobaini na mbili, sawa sawa na di si si si eksi eli ai ai.
Swali de. Mia tisa sitini na nne sawa sawa na mia tisa jumlisha sitini na nne, sawa sawa na si emu eli eksi ai vi.
""",
    "pg024_gp001_tx001": """
Kazi ya kufanya ya pili.
Tumia vyanzo vya kuaminika vya mtandaoni, kama Khan Academy, kujifunza zaidi kuhusu namba za Kirumi.
Zoezi la saba.
Swali la kwanza. Andika namba hizi za Kirumi kwa maneno: si emu eli eksi eksi ai eksi; di eli eksi eksi vi ai ai ai; si emu eksi si ai vi; na di si si si vi ai.
Swali la pili. Andika namba hizi zilizoandikwa kwa maneno kwa namba za Kirumi: mia tano hamsini na tisa; mia saba sitini na nne; mia tisa thelathini na mbili; na mia sita sitini na saba.
Swali la tatu. Andika namba hizi kwa namba za Kirumi: mia tano sabini na mbili; mia sita tisini na nane; mia saba hamsini na tano; na mia tisa kumi na sita.
Swali la nne. Karol ana kadi iliyoandikwa di eli vi ai ai. Anna ana kadi iliyoandikwa di eksi eli vi ai ai. Taja mwenye kadi yenye namba kubwa zaidi, kisha andika kila namba kwa numerali.
""",
    "pg025_gp001_tx001": """
Jikumbushe.
Numerali za desimali huundwa kwa tarakimu kumi: sifuri, moja, mbili, tatu, nne, tano, sita, saba, nane, na tisa.
Hakuna alama ya namba ya Kirumi inayowakilisha sifuri.
Alama kuu saba za namba za Kirumi ni ai, vi, eksi, eli, si, di, na emu.
Alama inaweza kurudiwa hadi mara tatu mfululizo.
Alama vi, eli, na di hazitumiki kutoa.
Alama ai, eksi, na si zinaweza kutumika kutoa.
Ai hutolewa tu kutoka kwa vi au eksi. Mifano ni ai vi, ambayo ni nne, na ai eksi, ambayo ni tisa.
Eksi hutolewa tu kutoka kwa eli au si. Mifano ni eksi eli, ambayo ni arobaini, na eksi si, ambayo ni tisini.
Si hutolewa tu kutoka kwa di au emu. Mifano ni si di, ambayo ni mia nne, na si emu, ambayo ni mia tisa.
Alama ai, eksi, na si zinaweza kurudiwa hadi mara tatu. Mifano ni ai ai ai, eksi eksi eksi, na si si si.
""",
    "pg026_gp001_tx001": """
Zoezi la marudio la namba za Kirumi.
Swali la kwanza. Andika namba hizi za Kirumi kwa maneno: si emu eksi si; di eli eksi ai vi; si emu eli eksi eksi ai; na di si eksi si vi ai ai.
Swali la pili. Andika namba hizi zilizoandikwa kwa maneno kwa namba za Kirumi: mia sita ishirini na moja; mia nane hamsini na tano; mia nane kumi na nane; na mia tisa hamsini.
Swali la tatu. Andika namba hizi za Kirumi kwa maneno: eksi si ai; si si eksi si ai ai; di si si si eli eksi eksi ai; na si emu eksi si ai eksi.
Swali la nne. Barabara ina urefu wa si emu eksi si vi ai kilometa. Andika urefu huo kwa numerali.
Swali la tano. Kadi ya kwanza ina di si vi ai. Kadi ya pili ina si emu eksi ai. Andika namba kubwa na namba ndogo kwa numerali.
Swali la sita. Jaza nafasi zilizo wazi.
Swali aa: si eksi vi, si si eksi eksi eksi, nafasi wazi, nafasi wazi, di eli eksi eksi vi, nafasi wazi, nafasi wazi, nafasi wazi.
Swali be: di si eksi ai eksi, di si eksi si ai eksi, nafasi wazi, nafasi wazi, nafasi wazi.
Swali la saba. Panga namba hizi za Kirumi kuanzia ndogo hadi kubwa: eksi si vi; eksi eli vi ai ai; si si ai eksi; si eli ai; eli eksi eksi ai ai ai; si emu vi; si emu eksi si ai ai; ai ai ai; eksi vi; na eksi si ai ai.
Swali la nane. Umbali kati ya mji E na mji F ni si emu eksi eli ai eksi kilometa. Andika umbali huo kwa numerali.
""",
    "pg085_gp001_tx001": """
Kazi ya kufanya ya kwanza. Kupima mzingo wa mstatili.
Mchoro unaonesha mstatili wenye pande mbili za urefu na pande mbili za upana.
Hatua.
1. Weka alama ya futikamba inayoonesha sifuri kwenye pembe moja ya mstatili.
2. Pima urefu wa mipaka ya mstatili hadi utakapokutana na alama ulipoanzia.
3. Soma na andika urefu wa futikamba kwenye makutano na pale ulipoanzia.
4. Pima urefu wa kila upande wa mstatili kwa kutumia rula kisha andika urefu wa kila upande.
5. Jumlisha urefu wa pande zote katika hatua ya nne.
6. Linganisha majibu ya hatua ya tatu na ya tano.
7. Je, mzunguko wa mstatili una urefu gani?
8. Urefu wa mzunguko uliopata katika hatua ya saba huitwa mzingo.
Katika kazi ya kufanya ya kwanza unajifunza kuwa, mzingo wa mstatili ni jumla ya urefu wa pande mbili za urefu na pande mbili za upana.
Mzingo wa mstatili sawa sawa na urefu jumlisha urefu jumlisha upana jumlisha upana.
Sawa sawa na mbili zidisha kwa urefu jumlisha mbili zidisha kwa upana.
Kwa hiyo, mzingo wa mstatili sawa sawa na mbili zidisha kwa urefu jumlisha mbili zidisha kwa upana.
""",
    "pg086_gp001_tx001": """
Mfano wa kwanza. Tafuta mzingo wa mstatili ufuatao.
Mstatili una urefu wa sentimeta mia moja na upana wa sentimeta arobaini.
Njia.
Mzingo wa mstatili sawa sawa na urefu jumlisha upana jumlisha urefu jumlisha upana.
Sawa sawa na sentimeta mia moja jumlisha sentimeta arobaini jumlisha sentimeta mia moja jumlisha sentimeta arobaini.
Sawa sawa na sentimeta mia mbili themanini.
Au, mstatili una pande mbili zenye urefu unaolingana na pande mbili zenye upana unaolingana.
Mzingo sawa sawa na mbili zidisha kwa urefu jumlisha mbili zidisha kwa upana.
Mzingo sawa sawa na sentimeta mia moja zidisha kwa mbili jumlisha sentimeta arobaini zidisha kwa mbili.
Sawa sawa na sentimeta mia mbili jumlisha sentimeta themanini.
Sawa sawa na sentimeta mia mbili themanini.
Kwa hiyo, mzingo wa mstatili huo ni sentimeta mia mbili themanini.
Mfano wa pili. Tafuta mzingo wa mstatili wenye urefu wa meta kumi na tatu na upana wa meta kumi na moja.
Njia. Urefu sawa sawa na meta kumi na tatu, upana sawa sawa na meta kumi na moja.
Mzingo sawa sawa na mbili zidisha kwa urefu jumlisha mbili zidisha kwa upana.
Sawa sawa na meta kumi na tatu zidisha kwa mbili jumlisha meta kumi na moja zidisha kwa mbili.
Sawa sawa na meta ishirini na sita jumlisha meta ishirini na mbili.
Sawa sawa na meta arobaini na nane.
Kwa hiyo, mzingo wa mstatili huo ni meta arobaini na nane.
""",
    "pg089_gp001_tx001": """
Mfano wa pili. Urefu wa upande mmoja wa bustani yenye umbo la mraba ni meta kumi na tatu. Tafuta mzingo wa bustani hiyo.
Njia. Urefu wa bustani sawa sawa na meta kumi na tatu.
Mzingo wa bustani sawa sawa na upande mmoja zidisha kwa nne.
Mzingo wa bustani sawa sawa na meta kumi na tatu zidisha kwa nne.
Sawa sawa na meta hamsini na mbili.
Kwa hiyo, mzingo wa bustani ni meta hamsini na mbili.
Zoezi la pili.
1. Tafuta mzingo wa kila umbo katika maumbo yafuatayo.
Kipengele a, mraba wenye upande wa sentimeta arobaini na tano.
Kipengele b, mraba wenye upande wa meta thelathini na mbili.
Kipengele c, mraba wenye upande wa meta ishirini na moja.
Kipengele d, mraba wenye upande wa sentimeta arobaini.
2. Tafuta mzingo wa mraba wenye urefu wa meta kumi na nane.
3. Upande mmoja wa mraba ni sentimeta thelathini na saba. Tafuta mzingo wake.
""",
    "pg102_gp001_tx001": """
Zoezi la kwanza.
1. Tafuta eneo la kila umbo katika maumbo yafuatayo.
Kipengele a, mstatili wenye urefu wa meta ishirini na upana wa meta nne.
Kipengele b, mstatili wenye urefu wa sentimeta kumi na nane na upana wa sentimeta nane.
Kipengele c, mstatili wenye urefu wa sentimeta arobaini na upana wa sentimeta kumi na tano.
Kipengele d, mstatili wenye urefu wa meta thelathini na tisa na upana wa meta kumi na saba.
2. Mstatili una urefu wa sentimeta kumi na upana sentimeta tisa. Tafuta eneo la mstatili huo.
3. Uso wa meza ya mwalimu una urefu wa sentimeta themanini na upana wa sentimeta sitini. Tafuta eneo la uso wa meza hiyo.
4. Chumba cha darasa kina urefu wa meta saba na upana wa meta sita. Tafuta eneo la sakafu ya darasa hilo.
5. Juma ana kiwanja chenye urefu wa meta thelathini na tano na upana meta ishirini na sita. Tafuta eneo la kiwanja hicho.
6. Bustani ina urefu wa meta kumi na tano na upana wa meta nane. Tafuta eneo la bustani hiyo.
""",
    "pg115_gp001_tx001": """
3. Andika sehemu zenye thamani sawa kwa kila kipengele.
Kipengele a: mbili ya tatu, moja ya mbili, nne ya sita, na tano ya kumi.
Kipengele b: moja ya nne, moja ya tatu, nne ya kumi na mbili, na tano ya ishirini.
Kipengele c: sita ya nane, moja ya tano, tatu ya nne, na tano ya ishirini na tano.
Kipengele d: moja ya nne, moja ya sita, moja ya nane, ishirini na tano ya mia moja, mbili ya kumi na sita, na tatu ya kumi na nane.
Sehemu zenye thamani tofauti.
Sehemu zenye thamani tofauti zinaweza kubainishwa kwa kutumia chati ya sehemu. Chunguza mchoro ufuatao.
Chati inaanza na kitu kizima kimoja. Mistari inayofuata inaonesha nusu mbili, theluthi tatu, robo nne, sehemu tano za tano, sehemu sita za sita, sehemu saba za saba, sehemu nane za nane, sehemu tisa za tisa, sehemu kumi za kumi, sehemu kumi na moja za kumi na moja, na sehemu kumi na mbili za kumi na mbili.
""",
    "pg127_gp001_tx001": """
Kugawanya sehemu zenye asili tofauti.
Sehemu hugawanywa kwa sehemu, kwanza kwa kubadili asili kuwa kiasi na kiasi kuwa asili ya sehemu inayogawanya. Kisha zidisha sehemu kwa sehemu. Vilevile, sehemu inaweza kugawanywa kwa kutumia mchoro.
Mfano wa kwanza. Tatu ya nane gawanya kwa nne ya sita.
Hatua ya kwanza. Badili kiasi na asili ya sehemu nne ya sita inayogawanya; inakuwa sita ya nne.
Hatua ya pili. Zidisha: tatu ya nane zidisha kwa sita ya nne sawa sawa na kumi na nane ya thelathini na mbili. Sawa sawa na tisa ya kumi na sita.
Kwa hiyo, jibu ni tisa ya kumi na sita.
Mfano wa pili. Tumia mchoro kutafuta thamani ya mbili ya tano gawanya kwa moja ya kumi.
Hatua ya kwanza. Onesha mbili ya tano kwenye mchoro kwa kuchora visanduku vitano vinavyolingana. Kisha paka rangi kwenye visanduku viwili kama ilivyooneshwa kwenye mchoro.
""",
    "pg133_gp001_tx001": """
Umbo hili limegawanywa katika sehemu kumi zilizo sawa. Kila sehemu inawakilisha moja ya kumi ya umbo zima.
Sehemu iliyotiwa kivuli ni moja ya kumi na huandikwa sifuri nukta moja katika desimali.
Namba sifuri nukta moja hupatikana baada ya kugawanya moja kwa kumi.
Desimali zinazoweza kupatikana kutokana na mchoro huo ni:
Sehemu moja ya kumi ni sifuri nukta moja.
Mbili ya kumi ni sifuri nukta mbili.
Tatu ya kumi ni sifuri nukta tatu.
Nne ya kumi ni sifuri nukta nne.
Tano ya kumi ni sifuri nukta tano.
Sita ya kumi ni sifuri nukta sita.
Saba ya kumi ni sifuri nukta saba.
Nane ya kumi ni sifuri nukta nane.
Tisa ya kumi ni sifuri nukta tisa.
Katika desimali, nukta inatenganisha namba nzima na namba ambayo ni sehemu ya kumi.
Kusoma desimali. Desimali zina nafasi moja au zaidi. Desimali husomwa kutoka kushoto kuelekea kulia.
Sifuri nukta saba. Moja nukta nane. Ishirini na tano nukta sita. Mia mbili hamsini nukta moja.
Desimali zenye nafasi mbili zinaweza kufafanuliwa kwa kutumia mchoro unaofuata.
""",
    "pg137_gp001_tx001": """
Kubadili sehemu kuwa desimali. Desimali hupatikana kwa kugawanya kiasi kwa asili ya sehemu.
Mfano wa kwanza. Badili sita ya kumi kuwa desimali.
Hatua ya kwanza. Gawanya kiasi kwa asili: sita gawanya kwa kumi, haitoshelezi. Andika sifuri juu ya sita katika nafasi ya jibu kisha weka nukta.
Hatua ya pili. Zidisha: sifuri zidisha kwa kumi sawa sawa na sifuri. Andika sifuri chini ya sita kisha toa: sita toa sifuri sawa sawa na sita.
Hatua ya tatu. Andika sifuri mbele ya sita katika kigawanye na kuwa sitini, kisha gawanya: sitini gawanya kwa kumi sawa sawa na sita. Andika sita sehemu ya jibu baada ya nukta.
Hatua ya nne. Zidisha: sita zidisha kwa kumi sawa sawa na sitini. Andika sitini chini ya sitini kisha toa: sitini toa sitini sawa sawa na sifuri.
Kwa hiyo, sita ya kumi sawa sawa na sifuri nukta sita.
Mfano wa pili. Badili moja ya mbili kuwa desimali.
Hatua ya kwanza. Gawanya moja kwa mbili, haitoshelezi. Andika sifuri juu ya moja katika nafasi ya jibu kisha weka nukta.
Hatua ya pili. Sifuri zidisha kwa mbili sawa sawa na sifuri. Andika sifuri chini ya moja kisha toa: moja toa sifuri sawa sawa na moja.
Hatua ya tatu. Andika sifuri mbele ya moja katika kigawanye na kuwa kumi, kisha gawanya: kumi gawanya kwa mbili sawa sawa na tano. Andika tano baada ya nukta.
Hatua ya nne. Tano zidisha kwa mbili sawa sawa na kumi. Kumi toa kumi sawa sawa na sifuri.
Kwa hiyo, moja ya mbili sawa sawa na sifuri nukta tano.
""",
    "pg138_gp001_tx001": """
Mfano wa tatu. Badili moja ya mia moja kuwa desimali.
Hatua ya kwanza. Gawanya moja kwa mia moja, haitoshelezi. Andika sifuri juu ya moja kwenye nafasi ya jibu kisha weka nukta.
Hatua ya pili. Sifuri zidisha kwa mia moja sawa sawa na sifuri. Andika sifuri chini ya moja kisha toa: moja toa sifuri sawa sawa na moja.
Hatua ya tatu. Andika sifuri mbele ya moja ili kupata kumi, kisha gawanya kumi kwa mia moja. Haitoshelezi. Andika sifuri kulia kwa nukta, kisha weka sifuri mbele ya kumi ili kupata mia moja.
Hatua ya nne. Gawanya mia moja kwa mia moja ili kupata moja. Andika moja katika nafasi ya jibu kupata sifuri nukta sifuri moja.
Hatua ya tano. Moja zidisha kwa mia moja sawa sawa na mia moja. Mia moja toa mia moja sawa sawa na sifuri.
Kwa hiyo, moja ya mia moja sawa sawa na sifuri nukta sifuri moja.
Zoezi la tatu. Badili sehemu zifuatazo kuwa desimali.
1. Kipengele a, tatu ya kumi. Kipengele b, nane ya kumi. Kipengele c, saba ya kumi. Kipengele d, kumi na mbili ya kumi.
2. Kipengele a, moja ya tano. Kipengele b, mbili ya tano. Kipengele c, tatu ya mbili. Kipengele d, saba ya tano.
3. Kipengele a, tatu ya mia moja. Kipengele b, kumi na tano ya mia moja. Kipengele c, sabini na sita ya mia moja. Kipengele d, themanini na tatu ya mia moja.
4. Kipengele a, moja ya ishirini na tano. Kipengele b, moja ya nne. Kipengele c, tatu ya nne. Kipengele d, tano ya nne.
5. Kipengele a, sita ya mia moja. Kipengele b, mia moja nane ya mia moja. Kipengele c, mia moja sabini na sita ya mia moja. Kipengele d, ishirini na saba ya mia moja.
""",
    "pg152_gp001_tx001": (
        "Uhusiano wa vipimo vya muda. Mwaka mmoja ni wiki hamsini na mbili. Mwaka mmoja ni miezi kumi na miwili. "
        "Mwaka mrefu una siku mia tatu sitini na sita. Mwaka mfupi una siku mia tatu sitini na tano. "
        "Kugawanya hutumika wakati wa kubadili kipimo kidogo kwenda kikubwa, na kuzidisha hutumika wakati wa kubadili kipimo kikubwa kwenda kidogo. "
        "Mfano wa kwanza. Kuna dakika ngapi katika sekunde mia saba ishirini? Njia. Dakika moja ni sekunde sitini. "
        "Sekunde mia saba ishirini gawanya kwa sitini, sawa sawa na dakika kumi na mbili. "
        "Kwa hiyo, kuna dakika kumi na mbili katika sekunde mia saba ishirini. "
        "Mfano wa pili. Mwanafunzi hutumia dakika kumi na tano kutoka nyumbani kwenda shuleni. Badili muda huo kuwa katika saa. "
        "Njia. Saa moja ni dakika sitini. Dakika kumi na tano gawanya kwa sitini, sawa sawa na sehemu kumi na tano ya sitini ya saa. "
        "Kwa hiyo, dakika kumi na tano ni sawa na sehemu kumi na tano ya sitini ya saa. "
        "Mfano wa tatu. Kuna dakika ngapi katika saa sabini na mbili? Njia. Saa moja ni dakika sitini. "
        "Saa sabini na mbili zidisha kwa sitini, sawa sawa na dakika elfu nne mia tatu ishirini. "
        "Kwa hiyo, kuna dakika elfu nne mia tatu ishirini katika saa sabini na mbili."
    ),
    "pg171_gp001_tx001": (
        "Kuzidisha fedha katika shilingi na senti. Fedha ya Tanzania katika shilingi na senti inaweza kuzidishwa kwa namba nzima. "
        "Tendo la kuzidisha linafanyika kuanzia upande wa senti kuelekea upande wa shilingi. "
        "Uhusiano wa shilingi na senti hutumika wakati wa kubadili kiasi cha senti kuwa shilingi. "
        "Kumbuka kuwa senti huandikwa kwa tarakimu mbili, pia shilingi moja ni sawa na senti mia moja. "
        "Mfano wa kwanza. Zidisha shilingi hamsini na senti tano kwa sita. "
        "Hatua ya kwanza. Zidisha senti tano kwa sita. Senti tano zidisha kwa sita, sawa sawa na senti thelathini. "
        "Andika thelathini katika nafasi ya senti. "
        "Hatua ya pili. Zidisha shilingi hamsini kwa sita. Shilingi hamsini zidisha kwa sita, sawa sawa na shilingi mia tatu. "
        "Andika mia tatu katika nafasi ya shilingi. "
        "Kwa hiyo, jibu ni shilingi mia tatu na senti thelathini, au shilingi mia tatu nukta senti thelathini."
    ),
}

PAGE_NARRATION_OVERRIDES.update({
    "pg043_gp001_tx001": """
Mfano wa pili. Mia mbili arobaini na tano gawanya kwa tano sawa sawa na arobaini na tisa.
Hatua ya kwanza. Gawanya mbili kwa tano, haitoshelezi.
Hatua ya pili. Chukua ishirini na nne gawanya kwa tano, unapata nne baki nne. Andika nne katika nafasi ya makumi. Badili nne iliyobaki kuwa mamoja arobaini.
Hatua ya tatu. Jumlisha mamoja: arobaini jumlisha tano sawa sawa na arobaini na tano. Gawanya arobaini na tano kwa tano, unapata tisa. Andika tisa katika nafasi ya mamoja kulia kwa nne.
Kwa hiyo, mia mbili arobaini na tano gawanya kwa tano sawa sawa na arobaini na tisa.
Mfano wa tatu. Mia mbili themanini na nne gawanya kwa mbili sawa sawa na mia moja arobaini na mbili.
Njia. Hatua ya kwanza. Gawanya mbili kwa mbili, unapata moja. Andika moja katika nafasi ya mamia.
Hatua ya pili. Gawanya nane kwa mbili, unapata nne. Andika nne katika nafasi ya makumi kulia kwa moja.
Hatua ya tatu. Gawanya nne kwa mbili, unapata mbili. Andika mbili katika nafasi ya mamoja kulia kwa nne.
Kwa hiyo, jibu ni mia moja arobaini na mbili.
Mfano wa nne. Mia tatu themanini na nne gawanya kwa kumi na mbili sawa sawa na thelathini na mbili.
Njia. Hatua ya kwanza. Gawanya tatu kwa kumi na mbili, haitoshelezi. Hivyo, chukua thelathini na nane gawanya kwa kumi na mbili, unapata tatu baki mbili. Andika tatu katika nafasi ya makumi.
""",
    "pg106_gp001_tx001": """
Katika Kazi ya kufanya ya pili umejifunza kuwa eneo la pembetatu linapatikana kwa kuhesabu idadi ya miraba midogo. Hivyo, eneo la pembetatu hupatikana kwa kuchukua nusu ya eneo la mraba au mstatili. Kwa hiyo, eneo la pembetatu ni sawa na nusu zidisha kwa kitako zidisha kwa kimo. Mfano wa kwanza. Tafuta eneo la pembetatu pi, kyu, aa. Maelezo ya mchoro. Mchoro unaonyesha pembetatu pi, kyu, aa. Herufi pi iko juu kushoto, kyu iko chini kushoto, na aa iko chini kulia. Upande kyu, pi umesimama wima na ndio kimo. Upande kyu, aa umelala kwa mlalo na ndio kitako. Upande pi, aa ni mstari wa mteremko unaofunga pembetatu. Alama ndogo ya mraba kwenye kona ya kyu inaonyesha pembe ya nyuzi 90 kati ya kimo na kitako. Kimo kyu, pi kina urefu wa sentimeta 7, na kitako kyu, aa kina urefu wa sentimeta 10. Njia. Kitako kyu, aa ni sawa na sentimeta 10. Kimo kyu, pi ni sawa na sentimeta 7. Eneo la pembetatu ni sawa na nusu zidisha kwa kitako zidisha kwa kimo. Ni sawa na nusu zidisha kwa sentimeta 10 zidisha kwa sentimeta 7. Ni sawa na sentimeta skwea 35. Kwa hiyo, eneo la pembetatu pi, kyu, aa ni sentimeta skwea 35.
""",
    "pg107_gp001_tx001": """
Mfano wa pili. Ikiwa kimo cha pembetatu ni meta 15 na kitako chake ni meta 30, tafuta eneo la pembetatu. Njia. Kimo cha pembetatu ni sawa na meta 15. Kitako cha pembetatu ni sawa na meta 30. Eneo la pembetatu ni sawa na nusu zidisha kwa kitako zidisha kwa kimo. Ni sawa na nusu zidisha kwa meta 30 zidisha kwa meta 15. Ni sawa na meta skweya 225. Kwa hiyo, eneo la pembetatu ni meta skweya 225. Mfano wa tatu. Tafuta eneo la pembetatu kei, eli, emu. Maelezo ya mchoro. Mchoro unaonyesha pembetatu kei, eli, emu. Herufi kei iko chini kushoto, emu iko chini kulia, na eli iko juu. Mstari wa kimo unatoka eli hadi eni kwenye kitako. Kitako kei, emu kina urefu wa sentimeta 26, na kimo eli, eni kina urefu wa sentimeta 12. Njia. Kitako kei, emu ni sawa na sentimeta 26. Kimo eli, eni ni sawa na sentimeta 12. Eneo la pembetatu kei, eli, emu ni sawa na nusu zidisha kwa kitako zidisha kwa kimo. Ni sawa na nusu zidisha kwa sentimeta 26 zidisha kwa sentimeta 12.
""",
    "pg108_gp001_tx001": """
Mfano wa tatu unaendelea. Sentimeta 26 zidisha kwa sentimeta 12, kisha gawanya kwa 2. Sentimeta 26 zidisha kwa sentimeta 12 ni sentimeta skwea 312. Sentimeta skwea 312 gawanya kwa 2 ni sentimeta skwea 156. Kwa hiyo, eneo la pembetatu kei, eli, emu ni sentimeta skwea 156. Zoezi la tatu. Swali la kwanza. Tafuta eneo la kila umbo katika maumbo yafuatayo. Kipengele aa. Maelezo ya mchoro. Kuna pembetatu bi, di, si. Herufi bi iko juu kushoto, di iko chini kushoto, na si iko chini kulia. Upande bi, di umesimama wima na una urefu wa sentimeta 14. Upande di, si umelala kwa mlalo na una urefu wa sentimeta 18. Alama ya mraba kwenye kona ya di inaonyesha pembe ya nyuzi 90. Hivyo, kitako di, si ni sentimeta 18 na kimo bi, di ni sentimeta 14. Kipengele be. Maelezo ya mchoro. Kuna pembetatu zedi, eli, emu iliyogeuzwa kuelekea chini. Herufi zedi iko juu kushoto, eli iko juu kulia, na emu iko chini katikati. Upande zedi, eli ni kitako cha juu chenye urefu wa sentimeta 24. Mstari wa nukta kutoka kwenye kitako hadi emu ni kimo cha sentimeta 19, na una alama ya pembe ya nyuzi 90. Kipengele se. Maelezo ya mchoro. Kuna pembetatu aa, esi, ti. Herufi aa iko juu kushoto, esi iko juu kulia, na ti iko chini kushoto. Upande aa, esi umelala kwa mlalo na una urefu wa meta 10. Upande aa, ti umesimama wima na una urefu wa meta 10. Alama ya mraba kwenye kona ya aa inaonyesha pembe ya nyuzi 90. Kipengele de. Maelezo ya mchoro. Kuna pembetatu emu, eli, eni inayochongoka upande wa kulia. Herufi emu iko juu kushoto, eli iko chini kushoto, na eni iko upande wa kulia. Upande emu, eli umesimama wima na una urefu wa sentimeta 5. Mstari wa mlalo kutoka upande emu, eli hadi eni ni kimo cha sentimeta 20 na una alama ya pembe ya nyuzi 90. Swali la pili. Uso wa meza ya pembetatu una kimo cha meta 6 na kitako cha meta 3. Tafuta eneo la meza hiyo. Swali la tatu. Tafuta eneo la alama ya barabarani yenye umbo la pembetatu, ikiwa kitako chake ni sentimeta 40 na kimo chake ni sentimeta 55.
""",
    "pg183_gp001_tx001": """
Kazi ya kufanya. Kujifunza miamala ya fedha ya Tanzania kwa njia ya masomo ya mtandaoni.

Maelezo. Tumia huduma na masomo ya mtandaoni kujifunza zaidi namna ya kuzidisha na kugawanya fedha ya Tanzania.

Jikumbushe mambo matatu. Kwanza, unapotenga shilingi na senti katika tarakimu, senti huandikwa kwa tarakimu mbili. Pili, unapozidisha fedha, anza na senti kisha shilingi. Tatu, unapogawanya fedha, anza na shilingi kisha senti.

Zoezi la marudio.

Swali la kwanza. Shilingi mia saba sitini na nne mara sita.

Swali la pili. Shilingi elfu tano mia sita sabini na tano na senti thelathini na tisa mara nane.

Swali la tatu. Shilingi mia moja tisini na senti tisini mara tisa.

Swali la nne. Shilingi elfu arobaini na tano mia tatu thelathini na senti themanini mara ishirini na nane.

Swali la tano. Shilingi elfu tatu mia tano mara tisa.

Swali la sita. Shilingi elfu thelathini na tisa mia nane hamsini na senti sabini na saba mara sabini na tisa.

Swali la saba. Shilingi mia moja tisini na nane na senti tisini na sita mara sitini na tisa.

Swali la nane. Shilingi elfu sitini na saba mia sita sabini na nane na senti hamsini na mbili gawanya kwa ishirini na sita.

Swali la tisa. Shilingi elfu arobaini na tano mia tatu sitini na senti tisini na sita gawanya kwa sita.
""",
    "pg184_gp001_tx001": """
Zoezi la marudio linaendelea.

Swali namba kumi. Shilingi elfu kumi na mbili mia nne gawanya kwa nne.

Swali namba kumi na moja. Shilingi elfu sabini na tano mia tano gawanya kwa ishirini.

Swali namba kumi na mbili. Shilingi elfu arobaini na nne mia mbili themanini na nne na senti kumi na nne gawanya kwa kumi na nane.

Swali namba kumi na tatu. Shilingi elfu tisini na tano mia nne sitini na senti thelathini na saba gawanya kwa kumi na tisa.

Swali namba kumi na nne. Shilingi elfu saba mia sita hamsini na tatu na senti sitini na mbili gawanya kwa kumi na tatu.

Swali namba kumi na tano. Shilingi elfu kumi na tisa na saba na senti sitini na sita gawanya kwa kumi na nne.

Swali namba kumi na sita. Daftari moja linauzwa kwa bei ya shilingi mia tano na senti thelathini. Je, ni kiasi gani cha fedha kinachohitajika kununua madaftari nane ya aina hiyo?

Swali namba kumi na saba. Mpira unauzwa kwa bei ya shilingi elfu nane na senti ishirini na tano. Itagharimu kiasi gani cha fedha kununua mipira minne ya aina hiyo?

Swali namba kumi na nane. Kiasi cha shilingi elfu moja mia mbili na senti sabini na tano kilitumika kununua kalamu tatu zenye bei sawa. Je, kalamu moja iliuzwa kwa shilingi ngapi?

Swali namba kumi na tisa. Mwanafunzi alinunua madaftari tisa kwa shilingi elfu moja mia nane na tisa na senti arobaini na tano. Je, daftari moja liligharimu kiasi gani cha fedha ikiwa madaftari yote yalinunuliwa kwa bei sawa?

Swali namba ishirini. Mshahara wa mtumishi ni shilingi laki saba sabini na tano elfu mia tatu hamsini na tano na senti ishirini na tatu kwa mwezi. Ni kiasi gani cha mshahara mtumishi huyo hupokea kwa mwaka?

Swali namba ishirini na moja. Ndani ya pakiti moja kuna penseli kumi na mbili. Ikiwa penseli moja inagharimu shilingi mia nne hamsini na senti ishirini na tano, je, pakiti nane za penseli za aina hiyo zitagharimu kiasi gani cha fedha?

Swali namba ishirini na mbili. Mkulima aliuza magunia tisini na nane ya mahindi. Ikiwa aliuza kila gunia kwa bei ya shilingi elfu tisini na nane mia tano na senti arobaini na tano, je, alipata jumla ya kiasi gani cha fedha?
""",
})


def source_text(data_id: str, texts: dict[str, str]) -> str:
    page_match = re.fullmatch(r"pg(\d{3})_gp001_tx001", data_id)
    page_number = int(page_match.group(1)) if page_match else 0
    if 1 <= page_number <= 185:
        page = ROOT / ("index.html" if page_number == 1 else f"pg{page_number:03d}_sec001.html")
        source = page.read_text(encoding="utf-8")
        hook = re.search(
            r'<div class="page-narration-hook"[^>]*>(.*?)</div>',
            source,
            re.S,
        )
        if hook:
            narration = html.unescape(re.sub(r"<[^>]+>", "", hook.group(1)))
            return re.sub(r"\s+", " ", narration).strip()
    if data_id in PAGE_NARRATION_OVERRIDES:
        return PAGE_NARRATION_OVERRIDES[data_id]
    if data_id in SEMANTIC_PAGE_AUDIO:
        return SEMANTIC_PAGE_AUDIO[data_id]
    # Preserve narration that has already been manually reviewed. Rebuilding
    # every page from PDF coordinates can scramble equations, tables and
    # multi-column exercises. Fall back to page extraction only when a text
    # entry is genuinely absent.
    value = texts.get(data_id) or page_source(data_id) or semantic_html_source(data_id) or ""
    if data_id == "pg115_gp001_tx001" and "Chunguza mchoro ufuatao." in value:
        value = value.split("Chunguza mchoro ufuatao.", 1)[0]
        value += (
            "Chunguza mchoro ufuatao. "
            "Mchoro unaonesha sehemu sawa kuanzia nusu, sehemu moja ya tatu, "
            "robo, hadi sehemu moja ya kumi na mbili."
        )
    return repair_equation_order(clean_existing_narration(value, data_id))


async def synthesize(data_id: str, text: str, gate: asyncio.Semaphore):
    output = LOCALE / "audio" / f"{data_id}-rehema-{VERSION}.mp3"
    temporary = output.with_name(f".{data_id}.{uuid.uuid4().hex}.part.mp3")
    async with gate:
        for attempt in range(1, 5):
            boundaries = []
            try:
                communicate = edge_tts.Communicate(text, VOICE, rate=RATE, boundary="WordBoundary")
                with temporary.open("wb") as stream:
                    async for chunk in communicate.stream():
                        if chunk["type"] == "audio":
                            stream.write(chunk["data"])
                        elif chunk["type"] == "WordBoundary":
                            start = float(chunk.get("offset", 0)) / 10_000_000
                            duration = float(chunk.get("duration", 0)) / 10_000_000
                            boundaries.append({"word": chunk.get("text", ""), "start": round(start, 4),
                                               "end": round(start + duration, 4)})
                if temporary.stat().st_size <= 1000:
                    raise RuntimeError("TTS returned invalid audio")
                temporary.replace(output)
                return output.name, boundaries
            except Exception:
                temporary.unlink(missing_ok=True)
                if attempt == 4:
                    raise
                await asyncio.sleep(attempt * 2)


async def run(workers: int, requested: set[str] | None, skip_quizzes: bool):
    texts = json.loads((LOCALE / "texts.json").read_text(encoding="utf-8"))
    audios = json.loads((LOCALE / "audios.json").read_text(encoding="utf-8"))
    ids = [key for key in audios if key in texts and spoken(source_text(key, texts), key)]
    if requested:
        ids = [key for key in ids if key in requested]
    if skip_quizzes:
        ids = [key for key in ids if not key.startswith("qz")]
    gate = asyncio.Semaphore(workers)
    done = 0

    async def one(key: str):
        nonlocal done
        narration = spoken(source_text(key, texts), key)
        filename, boundaries = await synthesize(key, narration, gate)
        done += 1
        if done % 10 == 0 or done == len(ids):
            print(f"Rehema {VERSION} {done}/{len(ids)}", flush=True)
        return key, filename, boundaries, narration

    results = await asyncio.gather(*(one(key) for key in ids))
    timecodes_path = LOCALE / "timecode" / "timecode_output.json"
    timecodes = json.loads(timecodes_path.read_text(encoding="utf-8"))
    for key, filename, boundaries, narration in results:
        audios[key] = filename
        texts[key] = narration
        timecodes[key] = {"timecodes": [{"word_timestamps": boundaries}]}
    (LOCALE / "audios.json").write_text(json.dumps(audios, ensure_ascii=False, indent=2), encoding="utf-8")
    (LOCALE / "texts.json").write_text(json.dumps(texts, ensure_ascii=False, indent=2), encoding="utf-8")
    timecodes_path.write_text(json.dumps(timecodes, ensure_ascii=False, indent=2), encoding="utf-8")
    versioned_audio_count = sum(
        1 for filename in audios.values()
        if filename.endswith(f"-rehema-{VERSION}.mp3")
    )
    report = {
        "voice": VOICE,
        "rate": RATE,
        "version": VERSION,
        "audioFiles": versioned_audio_count,
        "regeneratedAudioFiles": len(results),
        "spatialPageNarration": True,
    }
    (ROOT / "content" / "rehema-audio-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--ids")
    parser.add_argument("--skip-quizzes", action="store_true")
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    requested = set(args.ids.split(",")) if args.ids else None
    if args.preview:
        texts = json.loads((LOCALE / "texts.json").read_text(encoding="utf-8"))
        ids = requested or {"pg025_gp001_tx001", "pg086_gp001_tx001",
                            "pg106_gp001_tx001", "pg115_gp001_tx001"}
        for key in sorted(ids):
            print("--- " + key + " ---")
            print(spoken(source_text(key, texts), key))
        return
    asyncio.run(run(args.workers, requested, args.skip_quizzes))


if __name__ == "__main__":
    dependency = ROOT.parent / ".task-deps" / "edge-tts"
    if dependency.exists():
        sys.path.insert(0, str(dependency))
    import edge_tts
    main()






























