"""
Expense parser - extracts amount, category, and description from natural language text.
Localized for Malaysian Ringgit (RM).
"""

import re
from datetime import datetime

# Word-to-number mapping
WORD_NUMBERS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
    "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
    "ninety": 90,
}

MULTIPLIERS = {
    "hundred": 100,
    "thousand": 1000,
}

# Ordinal-to-number mapping (for date parsing)
ORDINAL_NUMBERS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
    "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14,
    "fifteenth": 15, "sixteenth": 16, "seventeenth": 17, "eighteenth": 18,
    "nineteenth": 19, "twentieth": 20, "twenty-first": 21, "twenty-second": 22,
    "twenty-third": 23, "twenty-fourth": 24, "twenty-fifth": 25,
    "twenty-sixth": 26, "twenty-seventh": 27, "twenty-eighth": 28,
    "twenty-ninth": 29, "thirtieth": 30, "thirty-first": 31,
}

MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# Category keywords mapping (with Malaysian context)
CATEGORY_KEYWORDS = {
    "Food & Dining": [
        "food", "lunch", "dinner", "breakfast", "meal", "restaurant", "cafe",
        "coffee", "pizza", "burger", "sushi", "snack", "eat", "ate", "dining",
        "takeout", "delivery", "brunch", "dessert", "bakery", "tea",
        "nasi", "mee", "mi", "roti", "teh", "kopi", "makan", "ayam",
        "chicken rice", "nasi lemak", "char kuey teow", "laksa", "satay",
        "mamak", "kopitiam", "hawker", "warung", "kedai makan",
        "boba", "bubble tea", "rice", "noodle", "chicken",
    ],
    "Transport": [
        "taxi", "uber", "grab", "cab", "bus", "train", "lrt", "mrt", "ktm",
        "monorail", "rapidkl", "touch n go", "tng",
        "gas", "fuel", "petrol", "minyak", "parking", "toll", "ride", "flight",
        "airline", "transport", "commute", "fare", "ewallet",
    ],
    "Groceries": [
        "grocery", "groceries", "supermarket", "market", "store",
        "jaya grocer", "village grocer", "aeon", "mydin", "giant",
        "tesco", "lotus", "99 speedmart", "speedmart",
        "vegetables", "fruits", "sayur", "buah",
    ],
    "Shopping": [
        "shopping", "clothes", "clothing", "shoes", "shopee", "lazada",
        "online", "electronics", "gadget", "purchase", "bought", "buy",
        "uniqlo", "h&m", "mr diy",
    ],
    "Entertainment": [
        "movie", "movies", "cinema", "gsc", "tgv", "netflix", "spotify",
        "subscription", "game", "gaming", "concert", "show", "ticket",
        "museum", "park", "fun", "entertainment", "hobby", "karaoke",
    ],
    "Bills & Utilities": [
        "bill", "bills", "electric", "electricity", "tnb", "water", "syabas",
        "internet", "unifi", "maxis", "celcom", "digi", "yes",
        "phone", "mobile", "wifi", "utility", "utilities", "rent", "sewa",
        "insurance", "astro",
    ],
    "Health": [
        "doctor", "hospital", "medicine", "pharmacy", "health", "medical",
        "dentist", "gym", "fitness", "wellness", "therapy", "prescription",
        "klinik", "clinic", "guardian", "watson", "watsons",
    ],
    "Education": [
        "book", "books", "course", "class", "tuition", "school", "college",
        "university", "study", "education", "learning", "tutorial",
        "tuisyen", "sekolah",
    ],
    "Other": [],
}

WORD_NUMBERS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90
}

MULTIPLIERS = {"hundred": 100, "thousand": 1000}

def words_to_number(text: str) -> float | None:
    """
    Convert word numbers to digits.
    e.g. "seven" -> 7, "twenty five" -> 25, "thirty-two" -> 32
    Only parses a simple number — does NOT handle ringgit/cents splitting.
    """
    words = text.lower().replace("-", " ").split()
    total = 0
    current = 0

    for word in words:
        if word in WORD_NUMBERS:
            current += WORD_NUMBERS[word]
        elif word in MULTIPLIERS:
            current = (1 if current == 0 else current) * MULTIPLIERS[word]
        elif word == "and":
            continue
        else:
            if current > 0:
                break

    total += current
    return total if total > 0 else None


# Subunit keywords — when these follow a number, divide by 100
SUBUNIT_KEYWORDS = {"cents", "cent", "sen"}


def extract_amount(text: str) -> float | None:
    """
    Extract a monetary amount from text.
    Supports digits (25), currency symbols (RM25), word numbers (twenty five, seven),
    and subunit keywords (eighty cents → 0.80, fifty sen → 0.50).
    """
    normalized = text.lower().strip()

    # 0. Handle "X ringgit Y cents/sen" pattern (digits) — e.g. "15 ringgit 32 cents"
    ringgit_cents_digits = re.search(
        r"(\d+)\s*ringgit\s+(?:and\s+)?(\d{1,2})\s*(?:cents?|sen)", normalized, re.IGNORECASE
    )
    if ringgit_cents_digits:
        amount = int(ringgit_cents_digits.group(1)) + int(ringgit_cents_digits.group(2)) / 100
        if 0 < amount < 1000000:
            return amount

    # 1. Handle "X ringgit (and) Y cents/sen" with word numbers
    #    e.g. "fifteen ringgit thirty-two cents", "one ringgit and fifty sen"
    ringgit_word_match = re.search(
        r"(.+?)\s*ringgit\s+(?:and\s+)?(.+?)\s*(?:cents?|sen)", normalized, re.IGNORECASE
    )
    if ringgit_word_match:
        ringgit_part = words_to_number(ringgit_word_match.group(1).strip())
        cents_part = words_to_number(ringgit_word_match.group(2).strip())
        if ringgit_part is not None and cents_part is not None:
            amount = ringgit_part + cents_part / 100
            if 0 < amount < 1000000:
                return amount

    # 1b. Handle standalone "X cents/sen" with digits — e.g. "80 cents", "50 sen"
    subunit_digit_match = re.search(
        r"(\d+)\s*(?:cents?|sen)\b", normalized, re.IGNORECASE
    )
    if subunit_digit_match:
        amount = int(subunit_digit_match.group(1)) / 100
        if 0 < amount < 1000000:
            return amount

    # 1c. Handle standalone "X cents/sen" with word numbers — e.g. "eighty cents", "fifty sen"
    #     Build a pattern that matches word-numbers followed by cents/sen
    _word_num_names = "|".join(sorted(WORD_NUMBERS.keys(), key=len, reverse=True))
    subunit_word_match = re.search(
        rf"((?:(?:{_word_num_names})(?:\s+|-)?)+)\s*(?:cents?|sen)\b",
        normalized, re.IGNORECASE,
    )
    if subunit_word_match:
        num = words_to_number(subunit_word_match.group(1).strip())
        if num is not None:
            amount = num / 100
            if 0 < amount < 1000000:
                return amount

    # 2. Try digit-based patterns (specific contexts only, NO catch-all yet)
    patterns = [
        r"rm\s?(\d+(?:[.,]\d{1,2})?)",                                          # RM25 or RM25.50
        r"\$\s?(\d+(?:[.,]\d{1,2})?)",                                          # $25 or $25.50
        r"(\d+(?:[.,]\d{1,2})?)\s*(?:ringgit|rm|dollars?|bucks?|usd)",          # 25 ringgit
        r"(?:spent|paid|cost|costs|was|for|bayar|belanja)\s+(?:rm\s?)?(\d+(?:[.,]\d{1,2})?)",  # spent 25
        r"(\d+(?:[.,]\d{1,2})?)\s*(?:for|on|untuk)\s",                          # 25 for/on
    ]

    for pattern in patterns:
        match = re.search(pattern, normalized, re.IGNORECASE)
        if match:
            amount = float(match.group(1).replace(",", "."))
            if 0 < amount < 1000000:
                return amount

    # 3. Try word-based numbers ("seven ringgit", "twenty five")
    word_patterns = [
        r"(?:spent|paid|bayar|belanja)\s+(.+?)\s*(?:ringgit|rm|dollars?|on|for|$)",
        r"(.+?)\s*(?:ringgit|rm)",
        r"(?:spent|paid|bayar|belanja)\s+(.+?)(?:\s+on|\s+for|\s*$)",
    ]

    for pattern in word_patterns:
        match = re.search(pattern, normalized, re.IGNORECASE)
        if match:
            num = words_to_number(match.group(1).strip())
            if num and 0 < num < 1000000:
                return num

    # 4. Scan whole text for word numbers
    num = words_to_number(normalized)
    if num and 0 < num < 1000000:
        return num

    # 5. Last resort: any bare number that is NOT part of a date (skip 11th, 2nd, etc.)
    for match in re.finditer(r"(\d+(?:[.,]\d{1,2})?)", normalized):
        # Skip if followed by st/nd/rd/th (ordinal = date)
        end_pos = match.end()
        suffix = normalized[end_pos:end_pos + 2]
        if suffix in ("st", "nd", "rd", "th"):
            continue
        amount = float(match.group(1).replace(",", "."))
        if 0 < amount < 1000000:
            return amount

    return None


def detect_category(text: str) -> str:
    """Detect the expense category based on keywords in the text."""
    lower = text.lower()

    for category, keywords in CATEGORY_KEYWORDS.items():
        if category == "Other":
            continue
        for keyword in keywords:
            if keyword in lower:
                return category

    return "Other"


def clean_description(text: str) -> str:
    """Clean up the description text."""
    cleaned = re.sub(r"[.!?,;]+$", "", text).strip()
    return cleaned[:200]  # Cap at 200 chars


def extract_date(text: str) -> str:
    """
    Extract a date from natural language text.
    Supports formats like:
      - "sixth February" / "6th February" / "6 February"
      - "February sixth" / "February 6th" / "February 6"
      - "6/2/2026", "6-2-2026"
    Returns date in d-m-yyyy format. Defaults to today if no date found.
    """
    lower = text.lower().strip()
    now = datetime.now()

    # 1. Try digit date formats: 6/2/2026 or 6-2-2026
    date_format_match = re.search(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", lower)
    if date_format_match:
        day = int(date_format_match.group(1))
        month = int(date_format_match.group(2))
        year = int(date_format_match.group(3))
        try:
            dt = datetime(year, month, day)
            return dt.strftime("%-d-%-m-%Y").replace("%-d", str(dt.day)).replace("%-m", str(dt.month))
        except ValueError:
            pass

    # 2. Try "ordinal/number month" — e.g. "sixth February", "6th February", "6 February"
    #    Build ordinal pattern
    ordinal_words = "|".join(ORDINAL_NUMBERS.keys())
    month_words = "|".join(MONTH_NAMES.keys())

    # Pattern: "sixth February" or "6th February" or "6th of February" or "6 Feb"
    match = re.search(
        rf"({ordinal_words}|\d{{1,2}}(?:st|nd|rd|th)?)\s+(?:of\s+)?({month_words})",
        lower
    )
    if match:
        day_str = match.group(1).strip()
        month_str = match.group(2).strip()
        day = ORDINAL_NUMBERS.get(day_str) or int(re.sub(r"(st|nd|rd|th)$", "", day_str))
        month = MONTH_NAMES.get(month_str)
        if day and month:
            year = now.year
            try:
                dt = datetime(year, month, day)
                return f"{dt.day}-{dt.month}-{dt.year}"
            except ValueError:
                pass

    # Pattern: "February sixth" or "February 6th" or "February of 6th" or "Feb 6"
    match = re.search(
        rf"({month_words})\s+(?:of\s+)?({ordinal_words}|\d{{1,2}}(?:st|nd|rd|th)?)",
        lower
    )
    if match:
        month_str = match.group(1).strip()
        day_str = match.group(2).strip()
        day = ORDINAL_NUMBERS.get(day_str) or int(re.sub(r"(st|nd|rd|th)$", "", day_str))
        month = MONTH_NAMES.get(month_str)
        if day and month:
            year = now.year
            try:
                dt = datetime(year, month, day)
                return f"{dt.day}-{dt.month}-{dt.year}"
            except ValueError:
                pass

    # 3. Default to today
    return f"{now.day}-{now.month}-{now.year}"


def parse_expense(text: str) -> dict:
    """
    Parse a natural language string into an expense object.

    Args:
        text: The raw text (from voice transcription or typed input).

    Returns:
        Dict with keys: amount, category, description, date.
    """
    amount = extract_amount(text)
    category = detect_category(text)
    description = clean_description(text)
    date = extract_date(text)

    return {
        "amount": amount,
        "category": category,
        "description": description,
        "date": date,
    }


# -------------------------------------------------------------------
# Delete intent detection
# -------------------------------------------------------------------

_DELETE_TRIGGER_PHRASES = [
    r"\bdelete\b",
    r"\bremove\b",
    r"\bundo\b",
    r"\bcancel\b.*\bexpense\b",
    r"\berase\b",
    r"\bscratch that\b",
    r"\bthat was wrong\b",
    r"\bdelete that\b",
    r"\bremove that\b",
    r"\bdelete last\b",
    r"\bremove last\b",
    r"\bundo last\b",
]

_LAST_INDICATORS = re.compile(
    r"\b(last|latest|recent|that|previous|just now)\b",
    re.IGNORECASE,
)


def parse_delete_intent(text: str) -> dict | None:
    """
    Detect if `text` is a deletion request.

    Returns a dict describing what to delete, or None if no delete intent found.

    Return schema:
        {
            "mode": "last"           # delete the most recent expense
                  | "search",        # delete by matching keyword
            "keyword": str | None,   # keyword extracted from the user's words
            "category": str | None,  # category inferred from the keyword
        }
    """
    lower = text.lower().strip()

    # Check if any delete trigger phrase is present
    is_delete = any(re.search(p, lower) for p in _DELETE_TRIGGER_PHRASES)
    if not is_delete:
        return None

    # Determine if user says "last" / "recent" / "that" (no specific keyword)
    has_last_indicator = bool(_LAST_INDICATORS.search(lower))

    # Try to extract a meaningful keyword (what to delete).
    # Strip common filler words and pull what's left.
    stripped = re.sub(
        r"\b(delete|remove|undo|erase|cancel|the|last|latest|recent|previous|my|an|a|that|expense|entry|log|record|just|now)\b",
        "",
        lower,
        flags=re.IGNORECASE,
    )
    # Remove punctuation and tidy up whitespace — a lone "." must not count as a keyword
    stripped = re.sub(r"[^a-z0-9 ]", "", stripped)
    stripped = re.sub(r"\s+", " ", stripped).strip()

    if stripped:
        # Infer category from whatever the user described
        inferred_category = detect_category(stripped)
        return {
            "mode": "search",
            "keyword": stripped,
            "category": inferred_category,
        }

    # Nothing specific left → delete most recent by date
    return {
        "mode": "last",
        "keyword": None,
        "category": None,
    }
