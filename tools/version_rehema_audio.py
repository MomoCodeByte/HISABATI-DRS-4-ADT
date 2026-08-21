from __future__ import annotations

import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCALE = ROOT / "content" / "i18n" / "sw-TZ"
AUDIO = LOCALE / "audio"


def main() -> None:
    mapping_path = LOCALE / "audios.json"
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    updated: dict[str, str] = {}
    for data_id, filename in mapping.items():
        source = AUDIO / filename
        target_name = f"{data_id}-rehema.mp3"
        target = AUDIO / target_name
        if source.resolve() != target.resolve():
            shutil.copyfile(source, target)
        updated[data_id] = target_name
    mapping_path.write_text(
        json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Versioned Rehema audio mappings: {len(updated)}")


if __name__ == "__main__":
    main()
