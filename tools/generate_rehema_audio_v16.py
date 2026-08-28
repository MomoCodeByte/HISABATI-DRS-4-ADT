from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import html
import json
import re
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCALE = ROOT / "content" / "i18n" / "sw-TZ"
VOICE = "sw-TZ-RehemaNeural"
RATE = "-30%"
VERSION = "v16"

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
SPAN_RE = re.compile(r'<span class="pdf-span" style="(?P<style>[^"]*)">(?P<text>.*?)</span>', re.S)


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


def spell(match: re.Match[str]) -> str:
    return " ".join(LETTERS.get(char, char) for char in match.group(0).upper())


def spell_roman(match: re.Match[str]) -> str:
    return " ".join(ROMAN[char] for char in match.group(0).upper())


def add_pauses(value: str) -> str:
    ordinal = (r"kwanza|pili|tatu|nne|tano|sita|saba|nane|tisa|kumi|"
               r"kumi na moja|kumi na mbili|kumi na tatu|kumi na nne|kumi na tano|\d+")
    for label in ("Mfano wa", "Zoezi la"):
        value = re.sub(rf"\b({label}\s+(?:{ordinal}))\b[.:]?", r". \1. ", value, flags=re.I)
    value = re.sub(rf"\b(Kazi ya kufanya(?: ya (?:{ordinal}))?)\b[.:]?", r". \1. ", value, flags=re.I)
    for marker in ("Utangulizi", "Njia", "Hatua", "Zingatia", "Fikiri"):
        value = re.sub(rf"\b{marker}\b[.:]?", ". " + marker + ". ", value, flags=re.I)
    value = re.sub(r"\bKwa hiyo\b[,:]?", ". Kwa hiyo, ", value, flags=re.I)
    return re.sub(r"(?:\.\s*){2,}", ". ", value).lstrip(". ")


def spoken(value: str, data_id: str = "") -> str:
    value = html.unescape(value).replace("\x07", " ").replace("�", " toa ")
    value = re.sub(r"HISABATI DRS 4 PB 2024\.indd\s+\d+", " ", value, flags=re.I)
    value = re.sub(r"\b\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}\b", " ", value)
    value = re.sub(r"\bISBN\s*:\s*978-9912-753-61-7\b", "namba ya kitabu", value, flags=re.I)

    if re.search(r"\b(?:Kirumi|numerali)\b", value, re.I):
        value = re.sub(r"(?<![A-Za-z])[IVXLCDM]+(?![A-Za-z])", spell_roman, value, flags=re.I)

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


def source_text(data_id: str, texts: dict[str, str]) -> str:
    if data_id in SEMANTIC_PAGE_AUDIO:
        return SEMANTIC_PAGE_AUDIO[data_id]
    value = page_source(data_id) or texts[data_id]
    if data_id == "pg115_gp001_tx001" and "Chunguza mchoro ufuatao." in value:
        value = value.split("Chunguza mchoro ufuatao.", 1)[0]
        value += (
            "Chunguza mchoro ufuatao. "
            "Mchoro unaonesha sehemu sawa kuanzia nusu, sehemu moja ya tatu, "
            "robo, hadi sehemu moja ya kumi na mbili."
        )
    return repair_equation_order(value)


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
