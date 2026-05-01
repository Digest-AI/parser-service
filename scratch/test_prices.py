import re
import sys
from decimal import Decimal, InvalidOperation

# Force UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

def _parse_price(raw: str):
    if not raw:
        return None, None, False

    lower = raw.lower()
    free_words = ["бесплатно", "free", "gratuit", "0 mdl"]
    for w in free_words:
        if w in lower:
            print(f"DEBUG: Matched free word '{w}' in '{lower}'")
            return Decimal("0"), None, True

    # Current regex
    # The regex [\d\s]+ captures digits AND spaces. 
    # If the string is "от 100 MDL", it might match " 100 "
    numbers = re.findall(r"[\d\s]+(?:[.,]\d+)?", raw)
    print(f"DEBUG: raw='{raw}', findall={numbers}")
    decimals = []
    for n in numbers:
        cleaned = n.replace("\u202f", "").replace(" ", "").replace(",", ".").strip()
        if not cleaned:
            continue
        try:
            decimals.append(Decimal(cleaned))
        except InvalidOperation:
            pass

    if not decimals:
        return None, None, False
    if len(decimals) == 1:
        return decimals[0], None, False
    return decimals[0], decimals[-1], False

test_cases = [
    "500 MDL",
    "от 100 MDL",
    "от 100 до 500",
    "100 - 500 MDL",
    "от 200 MDL",
    "150 MDL",
    "Бесплатно",
    "Bilete de la 150 MDL",
    "Preț: 200 - 1000 MDL",
    "1 200 MDL",
]

for tc in test_cases:
    print(f"Testing: '{tc}'")
    res = _parse_price(tc)
    print(f"Result: {res}\n")
