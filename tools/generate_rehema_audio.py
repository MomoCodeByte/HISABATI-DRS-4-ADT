from __future__ import annotations

import argparse
import asyncio
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

UNITS = {
    0: "sifuri", 1: "moja", 2: "mbili", 3: "tatu", 4: "nne",
    5: "tano", 6: "sita", 7: "saba", 8: "nane", 9: "tisa",
}
TENS = {
    10: "kumi", 20: "ishirini", 30: "thelathini", 40: "arobaini",
    50: "hamsini", 60: "sitini", 70: "sabini", 80: "themanini", 90: "tisini",
}


def number_to_swahili(number: int) -> str:
    if number < 10:
        return UNITS[number]
    if number < 100:
        tens, remainder = divmod(number, 10)
        base = TENS[tens * 10]
        return base if remainder == 0 else f"{base} na {UNITS[remainder]}"
    if number < 1000:
        hundreds, remainder = divmod(number, 100)
        base = f"mia {UNITS[hundreds]}"
        return base if remainder == 0 else f"{base} na {number_to_swahili(remainder)}"
    if number < 1_000_000:
        thousands, remainder = divmod(number, 1000)
        base = f"elfu {number_to_swahili(thousands)}"
        return base if remainder == 0 else f"{base} {number_to_swahili(remainder)}"
    return str(number)


def pronounce_fraction(match: re.Match[str]) -> str:
    numerator = number_to_swahili(int(match.group(1)))
    denominator = number_to_swahili(int(match.group(2)))
    return f"{numerator} ya {denominator}"


def pronounce_roman_symbol(match: re.Match[str]) -> str:
    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    token = match.group(0).upper()
    total = 0
    previous = 0
    for letter in reversed(token):
        current = values[letter]
        if current < previous:
            total -= current
        else:
            total += current
            previous = current
    return f"{number_to_swahili(total)} ya Kirumi"


def pronounce_regular_number(match: re.Match[str]) -> str:
    number = int(match.group(0).replace(",", ""))
    return number_to_swahili(number)


def add_reading_pauses(value: str) -> str:
    ordinal = (
        r"kwanza|pili|tatu|nne|tano|sita|saba|nane|tisa|kumi"
        r"|kumi na moja|kumi na mbili|kumi na tatu|kumi na nne|kumi na tano"
        r"|\d+"
    )
    value = re.sub(
        rf"\b(Mfano\s+wa\s+(?:{ordinal}))\b[.:]?",
        r". \1. ", value, flags=re.I,
    )
    value = re.sub(
        rf"\b(Zoezi\s+la\s+(?:{ordinal}))\b[.:]?",
        r". \1. ", value, flags=re.I,
    )
    value = re.sub(
        rf"\b(Kazi\s+ya\s+kufanya(?:\s+ya\s+(?:{ordinal}))?)\b[.:]?",
        r". \1. ", value, flags=re.I,
    )
    for marker in ("Utangulizi", "Njia", "Zingatia", "Fikiri"):
        value = re.sub(rf"\b{marker}\b[.:]?", f". {marker}. ", value, flags=re.I)
    value = re.sub(r"\bKwa hiyo\b[,:]?", ". Kwa hiyo, ", value, flags=re.I)
    value = re.sub(r"(?:\.\s*){2,}", ". ", value)
    return value.lstrip(". ")


def spoken_text(value: str) -> str:
    value = html.unescape(value)
    value = value.replace("\x07", " ")
    value = re.sub(r"HISABATI DRS 4 PB 2024\.indd\s+\d+", " ", value, flags=re.I)
    value = re.sub(r"\b\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}\b", " ", value)
    value = re.sub(
        r"\bISBN\s*:\s*978-9912-753-61-7\b",
        "ai es bi en, tisa saba nane dashi tisa tisa moja mbili dashi saba tano tatu dashi sita moja dashi saba",
        value,
        flags=re.I,
    )
    roman_tokens = re.findall(r"(?<![A-Za-z])[IVXLCDM]+(?![A-Za-z])", value)
    roman_context = bool(re.search(r"\b(?:Kirumi|numerali)\b", value, re.I))
    if roman_context:
        value = re.sub(r"(?<!\d)\d{1,3}(?:,\d{3})+(?!\d)|(?<!\d)\d+(?!\d)", pronounce_regular_number, value)
    if roman_context:
        value = re.sub(r"(?<![A-Za-z])[IVXLCDM]+(?![A-Za-z])", pronounce_roman_symbol, value)
    word_pronunciations = (
        (r"\bdirector\b", "dairecta"),
        (r"\btie\b", "tai"),
        (r"\bgo\b", "goo"),
        (r"\btz\b", "tizi"),
        (r"\bwww\b", "dabiliyu. dabiliyu. dabiliyu"),
    )
    for pattern, pronunciation in word_pronunciations:
        value = re.sub(pattern, pronunciation, value, flags=re.I)
    value = re.sub(r"\bthamani\b", "samani", value, flags=re.I)
    value = re.sub(r"(?<!\d)(\d+)\s*/\s*(\d+)(?!\d)", pronounce_fraction, value)
    value = value.replace("@", " ati ")
    value = re.sub(r"_+", " dashi ", value)
    value = value.replace("/", " au ").replace("-", " dashi ")
    value = value.replace("×", " kuzidisha ").replace("÷", " kugawanya ")
    value = value.replace("+", " jumlisha ").replace("=", " sawa sawa na ")
    value = add_reading_pauses(value)
    value = value.replace(",", " mkato ")
    value = re.sub(r"\s+", " ", value).strip()
    return value


async def synthesize(data_id: str, text: str, semaphore: asyncio.Semaphore) -> tuple[str, list[dict[str, object]]]:
    output = LOCALE / "audio" / f"{data_id}-rehema-v15.mp3"
    temporary = output.with_name(f".{data_id}.{uuid.uuid4().hex}.part.mp3")
    async with semaphore:
        for attempt in range(1, 5):
            boundaries: list[dict[str, object]] = []
            try:
                communicate = edge_tts.Communicate(text, VOICE, rate=RATE, boundary="WordBoundary")
                with temporary.open("wb") as stream:
                    async for chunk in communicate.stream():
                        if chunk["type"] == "audio":
                            stream.write(chunk["data"])
                        elif chunk["type"] == "WordBoundary":
                            start = float(chunk.get("offset", 0)) / 10_000_000
                            duration = float(chunk.get("duration", 0)) / 10_000_000
                            boundaries.append({
                                "word": chunk.get("text", ""),
                                "start": round(start, 4),
                                "end": round(start + duration, 4),
                            })
                if temporary.stat().st_size <= 1000:
                    raise RuntimeError("TTS returned invalid audio")
                temporary.replace(output)
                return output.name, boundaries
            except Exception:
                temporary.unlink(missing_ok=True)
                if attempt == 4:
                    raise
                await asyncio.sleep(attempt * 2)
    raise RuntimeError(f"Failed to synthesize {data_id}")


async def run(
    workers: int,
    requested_ids: set[str] | None = None,
    contains: str | None = None,
    skip_quizzes: bool = False,
) -> None:
    texts = json.loads((LOCALE / "texts.json").read_text(encoding="utf-8"))
    audios = json.loads((LOCALE / "audios.json").read_text(encoding="utf-8"))
    ids = [data_id for data_id in audios if data_id in texts and spoken_text(texts[data_id])]
    if requested_ids is not None:
        ids = [data_id for data_id in ids if data_id in requested_ids]
    if contains is not None:
        ids = [data_id for data_id in ids if contains in texts[data_id]]
    if skip_quizzes:
        ids = [data_id for data_id in ids if not data_id.startswith("qz")]
    semaphore = asyncio.Semaphore(workers)
    completed = 0
    timecodes_path = LOCALE / "timecode" / "timecode_output.json"
    timecodes: dict[str, object] = json.loads(timecodes_path.read_text(encoding="utf-8"))

    async def one(data_id: str) -> tuple[str, str, list[dict[str, object]]]:
        nonlocal completed
        filename, boundaries = await synthesize(data_id, spoken_text(texts[data_id]), semaphore)
        completed += 1
        if completed % 20 == 0 or completed == len(ids):
            print(f"Rehema {completed}/{len(ids)}", flush=True)
        return data_id, filename, boundaries

    results = await asyncio.gather(*(one(data_id) for data_id in ids))
    for data_id, filename, boundaries in results:
        audios[data_id] = filename
        timecodes[data_id] = {"timecodes": [{"word_timestamps": boundaries}]}

    (LOCALE / "audios.json").write_text(json.dumps(audios, ensure_ascii=False, indent=2), encoding="utf-8")
    timecodes_path.write_text(
        json.dumps(timecodes, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    report = {"voice": VOICE, "rate": RATE, "audioFiles": len(results)}
    (ROOT / "content" / "rehema-audio-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--ids", type=str)
    parser.add_argument("--contains", type=str)
    parser.add_argument("--skip-quizzes", action="store_true")
    args = parser.parse_args()
    requested_ids = set(args.ids.split(",")) if args.ids else None
    asyncio.run(run(args.workers, requested_ids, args.contains, args.skip_quizzes))


if __name__ == "__main__":
    dependency = ROOT.parent / ".task-deps" / "edge-tts"
    if dependency.exists():
        sys.path.insert(0, str(dependency))
    import edge_tts

    main()
