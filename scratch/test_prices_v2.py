import re
import sys
from decimal import Decimal, InvalidOperation

# Force UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

def _parse_price(raw: str):
    if not raw:
        return None, None, False

    lower = raw.lower().strip()
    
    # Improved free check: use word boundaries
    free_patterns = [r'\bбесплатно\b', r'\bfree\b', r'\bgratuit\b', r'\b0\s*mdl\b']
    for p in free_patterns:
        if re.search(p, lower):
            return Decimal("0"), None, True

    # Improved regex for numbers, handling thousand separators (space or \u202f)
    # This finds numbers like "1 200", "500", "100.50", "100,50"
    num_pattern = r"(\d+(?:[\s\u202f]\d{3})*(?:[.,]\d+)?)"
    numbers = re.findall(num_pattern, raw)
    
    decimals = []
    for n in numbers:
        # Clean up the number string
        cleaned = n.replace("\u202f", "").replace(" ", "").replace(",", ".").strip()
        if not cleaned:
            continue
        try:
            val = Decimal(cleaned)
            # Skip suspiciously small numbers that aren't 0 (like "1" in "1 event")
            # though in price strings they are usually real.
            decimals.append(val)
        except InvalidOperation:
            pass

    if not decimals:
        return None, None, False
    
    if len(decimals) == 1:
        return decimals[0], None, False
    
    # Sort just in case? Usually the first is lower, the last is higher.
    # But let's take first and last as they appear.
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
    "от 1 200 до 2 500 MDL",
]

for tc in test_cases:
    res = _parse_price(tc)
    print(f"'{tc}' -> {res}")
