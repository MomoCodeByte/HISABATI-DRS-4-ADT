from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCALE = ROOT / "content" / "i18n" / "sw-TZ"
AUDIO = LOCALE / "audio"


def main() -> None:
    mapping_path = LOCALE / "audios.json"
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    missing: list[str] = []
    for data_id in mapping:
        filename = f"{data_id}-rehema-v7.mp3"
        path = AUDIO / filename
        if not path.exists() or path.stat().st_size <= 1000:
            missing.append(data_id)
            continue
        mapping[data_id] = filename
    if missing:
        raise RuntimeError(f"Missing or invalid V7 audio: {', '.join(missing)}")
    mapping_path.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Adopted Rehema V7 audio: {len(mapping)}")


if __name__ == "__main__":
    main()
