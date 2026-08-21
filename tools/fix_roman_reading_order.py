from __future__ import annotations

import html
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEXTS = ROOT / "content" / "i18n" / "sw-TZ" / "texts.json"

CORRECTIONS = {
    "pg013_gp001_tx001": "Mfano wa kwanza. Andika namba zifuatazo kwa Kirumi. Kipengele a, 24. Kipengele b, 37. Kipengele c, 27. Njia. Kipengele a. 24 = XX + IV. = XXIV. Kwa hiyo, 24 ni XXIV. Kipengele b. 37 = XXX + VII. = XXXVII. Kwa hiyo, 37 ni XXXVII. Kipengele c. 27 = XX + VII. = XXVII. Kwa hiyo, 27 ni XXVII. Mfano wa pili. Andika namba zifuatazo kwa numerali. Kipengele a, XXI. Kipengele b, XXXIII. Njia. Kipengele a. XXI = 20 + 1. = 21. Kwa hiyo, XXI ni 21. Kipengele b. XXXIII = 30 + 3. = 33. Kwa hiyo, XXXIII ni 33. Zoezi la tatu. Swali namba moja. Andika namba zifuatazo kwa Kirumi. Kipengele a, 29. Kipengele b, 26. Kipengele c, 32. Kipengele d, 23.",
    "pg015_gp001_tx001": "Kipengele c. 45 = XL + V. = XLV. Kwa hiyo, 45 ni XLV. Mfano wa pili. Andika namba zifuatazo kwa numerali. Kipengele a, XXXVII. Kipengele b, XLIII. Kipengele c, XLIX. Njia. Kipengele a. XXXVII = 30 + 7. = 37. Kwa hiyo, XXXVII ni 37. Kipengele b. XLIII = 40 + 3. = 43. Kwa hiyo, XLIII ni 43. Kipengele c. XLIX = 40 + 9. = 49. Kwa hiyo, XLIX ni 49. Zoezi la nne. Swali namba moja. Andika namba zifuatazo kwa Kirumi. Kipengele a, 44. Kipengele b, 39. Kipengele c, 35. Kipengele d, 46. Swali namba mbili. Andika namba zifuatazo kwa numerali. Kipengele a, XXXVI. Kipengele b, XLVIII. Kipengele c, XLI. Kipengele d, XXXIV. Swali namba tatu. Andika namba za Kirumi zinazokosekana katika kila mfululizo ufuatao. Kipengele a, XXXIV, ____, XXXVI, ____, ____, XXXIX. Kipengele b, XXXVI, XXXVIII, ____, XLII, XLIV, ____, ____, ____. Kipengele c, L, ____, XLIV, ____, XXXVIII, XXXII.",
    "pg018_gp001_tx001": "Mfano wa kwanza. Andika namba zifuatazo kwa maneno. Kipengele a, LXV. Kipengele b, LXXVI. Kipengele c, XCIX. Kipengele d, LIV. Njia. Kipengele a. LXV = 60 + 5. = 65. Kwa hiyo, namba LXV ni sitini na tano. Kipengele b. LXXVI = 70 + 6. = 76. Kwa hiyo, namba LXXVI ni sabini na sita. Kipengele c. XCIX = 90 + 9. = 99. Kwa hiyo, namba XCIX ni tisini na tisa. Kipengele d. LIV = 50 + 4. = 54. Kwa hiyo, namba LIV ni hamsini na nne. Mfano wa pili. Andika namba zifuatazo kwa Kirumi. Kipengele a, 53. Kipengele b, 67. Kipengele c, 57. Kipengele d, 88. Njia. Kipengele a. 53 = L + III. = LIII. Kwa hiyo, 53 ni LIII. Kipengele b. 67 = LX + VII. = LXVII. Kwa hiyo, 67 ni LXVII.",
    "pg021_gp001_tx001": "Mfano wa kwanza. Andika namba zifuatazo kwa Kirumi. Kipengele a, 205. Kipengele b, 362. Njia. Kipengele a. 205 = CC + V. = CCV. Kwa hiyo, 205 ni CCV. Kipengele b. 362 = CCC + LXII. = CCCLXII. Kwa hiyo, 362 ni CCCLXII. Mfano wa pili. Andika namba zifuatazo kwa maneno. Kipengele a, CXVII. Kipengele b, CDXLVI. Njia. Kipengele a. CXVII, mia moja kumi na saba. Kipengele b. CDXLVI, mia nne arobaini na sita. Zoezi la sita. Swali namba moja. Andika namba zifuatazo kwa maneno. Kipengele a, CCCXXX. Kipengele b, CCXIX. Kipengele c, CDXLVII. Kipengele d, CCXCII. Swali namba mbili. Andika namba zifuatazo kwa Kirumi. Kipengele a, mia nne arobaini na nne. Kipengele b, mia moja kumi na tano. Kipengele c, mia mbili na tisa. Kipengele d, mia nne hamsini na nne. Swali namba tatu. Badili namba zifuatazo kuwa namba za Kirumi. Kipengele a, 108. Kipengele b, 374. Kipengele c, 435. Kipengele d, 442. Swali namba nne. Umbali kati ya Mji A na Mji B ni kilometa CDLXXVIII. Andika umbali huo kwa numerali.",
    "pg023_gp001_tx001": "Njia. Kipengele a. CMIX = 900 + 9. = 909. Kwa hiyo, CMIX ni 909. Kipengele b. DCCLXXIV = 700 + 74. = 774. Kwa hiyo, DCCLXXIV ni 774. Mfano wa pili. Andika namba zifuatazo kwa Kirumi. Kipengele a, 576. Kipengele b, 688. Kipengele c, 842. Kipengele d, 964. Njia. Kipengele a. 576 = D + LXXVI. = DLXXVI. Kwa hiyo, 576 ni DLXXVI. Kipengele b. 688 = DC + LXXXVIII. = DCLXXXVIII. Kwa hiyo, 688 ni DCLXXXVIII. Kipengele c. 842 = DCCC + XLII. = DCCCXLII. Kwa hiyo, 842 ni DCCCXLII. Kipengele d. 964 = CM + LXIV. = CMLXIV. Kwa hiyo, 964 ni CMLXIV.",
}


def main() -> None:
    texts = json.loads(TEXTS.read_text(encoding="utf-8"))
    texts.update(CORRECTIONS)
    TEXTS.write_text(json.dumps(texts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for data_id, corrected in CORRECTIONS.items():
        page = ROOT / f"{data_id[:5]}_sec001.html"
        source = page.read_text(encoding="utf-8")
        pattern = rf'(<p class="sr-only" data-id="{re.escape(data_id)}">).*?(</p>)'
        updated, count = re.subn(pattern, rf"\g<1>{html.escape(corrected)}\g<2>", source, count=1)
        if count != 1:
            raise RuntimeError(f"Could not update {data_id} in {page.name}")
        page.write_text(updated, encoding="utf-8")

    print(f"Corrected {len(CORRECTIONS)} Roman-numeral reading blocks")


if __name__ == "__main__":
    main()
