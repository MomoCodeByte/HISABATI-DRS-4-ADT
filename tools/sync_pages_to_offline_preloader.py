from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRELOADER = ROOT / "assets" / "offline-preloader.js"


def main() -> None:
    source = PRELOADER.read_text(encoding="utf-8")
    resources = (
        ("./content/pages.json", ROOT / "content" / "pages.json"),
        ("./content/i18n/sw-TZ/texts.json", ROOT / "content" / "i18n" / "sw-TZ" / "texts.json"),
        ("./content/i18n/sw-TZ/audios.json", ROOT / "content" / "i18n" / "sw-TZ" / "audios.json"),
    )
    for key, path in resources:
        data = (
            json.loads(path.read_text(encoding="utf-8"))
            if path.suffix == ".json"
            else path.read_text(encoding="utf-8")
        )
        next_key_pattern = r',"\./[^\"]+":'
        pattern = re.escape(json.dumps(key)) + r":.*?(?=" + next_key_pattern + r")"
        replacement = json.dumps(key) + ":" + json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        source, count = re.subn(pattern, lambda _match: replacement, source, count=1)
        if count != 1:
            raise RuntimeError(f"Could not locate embedded {key}")
        print(f"Embedded {key}: {len(data)} entries")
    PRELOADER.write_text(source, encoding="utf-8")


if __name__ == "__main__":
    main()
