from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCALE = ROOT / "content" / "i18n" / "sw-TZ"
AUDIO = LOCALE / "audio"
FFPROBE = Path(r"C:\Users\Jacqueline\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg.Essentials_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-essentials_build\bin\ffprobe.exe")
sys.path.insert(0, str(ROOT / "tools"))
import generate_rehema_audio_v16 as v16


def duration(path: Path) -> float:
    result = subprocess.run(
        [str(FFPROBE), "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def approximate_boundaries(text: str, seconds: float) -> list[dict[str, object]]:
    raw = re.findall(r"\S+", text)
    words = []
    weights = []
    for token in raw:
        clean = token.strip(".,;:!?()[]{}")
        if not clean:
            continue
        pause = 4 if token.endswith((".", "?", "!")) else 2 if token.endswith((",", ";", ":")) else 0
        words.append(clean)
        weights.append(max(2, len(clean)) + pause)
    total = sum(weights) or 1
    cursor = 0.0
    result = []
    for word, weight in zip(words, weights):
        start = cursor
        cursor += seconds * weight / total
        result.append({"word": word, "start": round(start, 4), "end": round(cursor, 4)})
    return result


def main() -> None:
    audios_path = LOCALE / "audios.json"
    texts_path = LOCALE / "texts.json"
    timecodes_path = LOCALE / "timecode" / "timecode_output.json"
    audios = json.loads(audios_path.read_text(encoding="utf-8"))
    texts = json.loads(texts_path.read_text(encoding="utf-8"))
    timecodes = json.loads(timecodes_path.read_text(encoding="utf-8"))
    ids = [key for key in audios if not key.startswith("qz") and key in texts]
    missing = []
    files = {}
    for key in ids:
        path = AUDIO / f"{key}-rehema-v16.mp3"
        if not path.exists() or path.stat().st_size <= 1000:
            missing.append(key)
        else:
            files[key] = path
    if missing:
        raise RuntimeError("Missing V16 audio: " + ", ".join(missing))

    with ThreadPoolExecutor(max_workers=8) as executor:
        lengths = dict(zip(files, executor.map(duration, files.values())))

    exact_ids = {key for key in ids if audios.get(key, "").endswith("-rehema-v16.mp3")}
    for key in ids:
        filename = f"{key}-rehema-v16.mp3"
        audios[key] = filename
        if key not in exact_ids:
            text = v16.spoken(v16.source_text(key, texts), key)
            boundaries = approximate_boundaries(text, lengths[key])
            timecodes[key] = {"timecodes": [{"word_timestamps": boundaries}]}

    audios_path.write_text(json.dumps(audios, ensure_ascii=False, indent=2), encoding="utf-8")
    timecodes_path.write_text(json.dumps(timecodes, ensure_ascii=False, indent=2), encoding="utf-8")
    report = {
        "voice": v16.VOICE,
        "rate": v16.RATE,
        "version": v16.VERSION,
        "audioFiles": len(ids),
        "spatialPageNarration": True,
        "exactTimecodes": len(exact_ids),
        "durationWeightedTimecodes": len(ids) - len(exact_ids),
    }
    (ROOT / "content" / "rehema-audio-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()