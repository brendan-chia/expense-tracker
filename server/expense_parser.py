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

_NUMBER_WORD_PATTERN = "|".join(
    re.escape(word)
    for word in sorted(
        set(WORD_NUMBERS) | set(MULTIPLIERS),
        key=len,
        reverse=True,
    )
)
_NUMBER_WORD_SEQUENCE_PATTERN = (
    rf"(?:{_NUMBER_WORD_PATTERN})"
    rf"(?:(?:\s+and\s+|[\s-]+)(?:{_NUMBER_WORD_PATTERN}))*"
)

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

# Accept the category names users are likely to say in a correction. The
# values remain the exact labels used in the expense sheets.
_CATEGORY_ALIASES = {
    category.casefold(): category
    for category in CATEGORY_KEYWORDS
}
_CATEGORY_ALIASES.update({
    "food": "Food & Dining",
    "dining": "Food & Dining",
    "food and dining": "Food & Dining",
    "grocery": "Groceries",
    "transportation": "Transport",
    "bills": "Bills & Utilities",
    "utilities": "Bills & Utilities",
    "bills and utilities": "Bills & Utilities",
})
_CATEGORY_LABEL_PATTERN = "|".join(
    re.escape(alias)
    for alias in sorted(_CATEGORY_ALIASES, key=len, reverse=True)
)
_LAST_CORRECTION_TARGET = "__last__"

def words_to_number(text: str) -> float | None:
    """
    Convert word numbers to digits.
    e.g. "seven" -> 7, "twenty five" -> 25, "thirty-two" -> 32
    Only parses a simple number — does NOT handle ringgit/cents splitting.
    """
    words = text.lower().replace("-", " ").split()
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

    return current if current > 0 else None


def _parse_number_component(value: str) -> float | None:
    """Parse either a numeric or a word-based amount component."""
    value = value.strip()
    if re.fullmatch(r"\d+(?:[.,]\d+)?", value):
        return float(value.replace(",", "."))
    return words_to_number(value)


def extract_amount(text: str) -> float | None:
    """
    Extract a monetary amount from text.
    Supports digits (25), currency symbols (RM25), and word numbers (twenty five, seven).
    """
    normalized = text.lower().strip()

    # 0. Handle "X ringgit Y cents/sen" in either digits or words, including
    # mixed forms such as "fifteen ringgit 32 cents".
    amount_component = (
        rf"(?:\d+(?:[.,]\d+)?|{_NUMBER_WORD_SEQUENCE_PATTERN})"
    )
    ringgit_cents_match = re.search(
        rf"(?P<ringgit>{amount_component})\s*ringgit\s+"
        rf"(?:and\s+)?(?P<cents>{amount_component})\s*(?:cents?|sen)\b",
        normalized,
        re.IGNORECASE,
    )
    if ringgit_cents_match:
        ringgit_part = _parse_number_component(ringgit_cents_match.group("ringgit"))
        cents_part = _parse_number_component(ringgit_cents_match.group("cents"))
        if ringgit_part is not None and cents_part is not None:
            amount = ringgit_part + cents_part / 100
            if 0 < amount < 1000000:
                return amount

    # 1. Handle cents/sen without a ringgit value. The generic word-number
    # fallback would otherwise interpret "eighty cents" as the number 80.
    cents_digit_match = re.search(
        r"(?<![\w.,])(?P<cents>\d+(?:[.,]\d+)?)\s*(?:cents?|sen)\b",
        normalized,
        re.IGNORECASE,
    )
    if cents_digit_match:
        cents = float(cents_digit_match.group("cents").replace(",", "."))
        amount = cents / 100
        if 0 < amount < 1000000:
            return amount

    cents_word_match = re.search(
        rf"(?<![\w-])(?P<cents>{_NUMBER_WORD_SEQUENCE_PATTERN})"
        rf"\s*(?:cents?|sen)\b",
        normalized,
        re.IGNORECASE,
    )
    if cents_word_match:
        cents = words_to_number(cents_word_match.group("cents"))
        if cents is not None:
            amount = cents / 100
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


def normalize_category_name(value: str) -> str | None:
    """Return the canonical sheet label for a category name or alias."""
    normalized = re.sub(r"\s+", " ", str(value or "").strip().casefold())
    return _CATEGORY_ALIASES.get(normalized)


def _keyword_matches(text: str, keyword: str) -> bool:
    """Match a learned keyword without matching it inside another word."""
    return bool(
        re.search(
            rf"(?<!\w){re.escape(keyword.casefold())}(?!\w)",
            text,
            re.IGNORECASE,
        )
    )


def detect_category(
    text: str,
    learned_categories: dict[str, str] | None = None,
) -> str:
    """Detect a category, preferring user-learned mappings over defaults."""
    lower = text.casefold()

    # User corrections are checked first. Longer phrases win, so a learned
    # mapping for "protein shake" beats one for the shorter word "shake".
    learned_matches = []
    for keyword, category in (learned_categories or {}).items():
        keyword = re.sub(r"\s+", " ", str(keyword or "").strip())
        canonical_category = normalize_category_name(category)
        if keyword and canonical_category and _keyword_matches(lower, keyword):
            learned_matches.append((len(keyword), canonical_category))
    if learned_matches:
        return max(learned_matches, key=lambda item: item[0])[1]

    for category, keywords in CATEGORY_KEYWORDS.items():
        if category == "Other":
            continue
        for keyword in keywords:
            if keyword in lower:
                return category

    return "Other"


def _clean_correction_target(target: str) -> str:
    """Normalize the item phrase extracted from a category correction."""
    target = re.sub(r"[.!?,;:]+", " ", target.casefold())
    target = re.sub(r"^\s*(?:actually|please)\s*,?\s*", "", target)
    target = re.sub(r"^\s*(?:the|my)\s+", "", target)
    target = re.sub(
        r"\s+(?:expense|entry|purchase|item|transaction)\s*$",
        "",
        target,
    )
    target = re.sub(r"\s+", " ", target).strip()

    if re.fullmatch(
        r"(?:that|this|it|last|latest|previous|prior|most recent)"
        r"(?:\s+(?:one|expense|entry|purchase))?",
        target,
    ):
        return _LAST_CORRECTION_TARGET
    return target[:100]


def _split_correction_targets(target: str) -> list[str]:
    """Return separate item keywords from a correction target.

    Users commonly correct a list of items in one message, for example
    ``"rice, curry paste should be groceries"``.  Keeping those items as
    separate keywords lets the learning sheet store one reusable rule per
    item and lets an existing expense match either item.
    """
    parts = re.split(r"\s*(?:[,;]|\band\b)\s*", target, flags=re.IGNORECASE)
    keywords: list[str] = []
    for part in parts:
        keyword = _clean_correction_target(part)
        if keyword and keyword not in keywords:
            keywords.append(keyword)
    return keywords


def parse_category_correction(text: str) -> dict | None:
    """Parse a user correction such as "bread should be groceries".

    Returns ``{"keywords": [...], "category": ...}``, or ``None`` when the
    message is not an unambiguous correction. ``__last__`` is used when the
    user says "that" or "the last expense" instead of naming an item.
    """
    if not isinstance(text, str) or not text.strip():
        return None

    patterns = (
        rf"^(?P<target>.+?)\s+"
        rf"(?:should\s+(?:be|go\s+under)|belongs?\s+(?:in|under|to)|"
        rf"goes?\s+under|is)\s+(?:the\s+)?"
        rf"(?P<category>{_CATEGORY_LABEL_PATTERN})[.!?\s]*$",
        rf"^(?:please\s+)?(?:change|correct|recategorize|reclassify)\s+"
        rf"(?:the\s+)?(?P<target>.+?)\s+(?:to|as|into)\s+"
        rf"(?P<category>{_CATEGORY_LABEL_PATTERN})[.!?\s]*$",
        rf"^(?:please\s+)?set\s+(?:the\s+)?(?P<target>.+?)\s+"
        rf"category\s+to\s+(?P<category>{_CATEGORY_LABEL_PATTERN})[.!?\s]*$",
    )
    normalized = text.casefold().strip()

    for pattern in patterns:
        match = re.match(pattern, normalized, re.IGNORECASE)
        if not match:
            continue

        target = _split_correction_targets(match.group("target"))
        category = normalize_category_name(match.group("category"))
        if target and category:
            # A pronoun refers to one existing expense and cannot be turned
            # into a useful future keyword mapping.  Do not mix it with a
            # comma-separated list of real keywords.
            if _LAST_CORRECTION_TARGET in target and len(target) != 1:
                continue
            return {"keywords": target, "category": category}

    return None


def clean_description(text: str) -> str:
    """Clean up the description text."""
    cleaned = re.sub(r"[.!?,;]+$", "", text).strip()
    return cleaned[:200]  # Cap at 200 chars


def _format_date_parts(
    day_text: str,
    month_text: str,
    year_text: str | None,
    default_year: int,
) -> str | None:
    """Validate date words and return the sheet's date format."""
    try:
        day = ORDINAL_NUMBERS.get(day_text)
        if day is None:
            day = int(re.sub(r"(st|nd|rd|th)$", "", day_text))
    except ValueError:
        return None

    month = MONTH_NAMES.get(month_text)
    if not day or not month:
        return None

    year = int(year_text) if year_text else default_year
    try:
        date_value = datetime(year, month, day)
    except ValueError:
        return None
    return f"{date_value.day}-{date_value.month}-{date_value.year}"


def extract_date(text: str) -> str:
    """
    Extract a date from natural language text.
    Supports formats like:
      - "sixth February" / "6th February" / "6 February"
      - "February sixth" / "February 6th" / "February 6"
      - "6/2", "6-2" (the year defaults to the current year)
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
            return f"{dt.day}-{dt.month}-{dt.year}"
        except ValueError:
            pass

    # 1b. Try day/month without a year — e.g. "13/8" means 13 August
    #     in the current year. The boundary prevents this from partially
    #     matching a date that includes an explicit year.
    short_date_match = re.search(r"(\d{1,2})[/\-](\d{1,2})(?![/\-]\d)", lower)
    if short_date_match:
        day = int(short_date_match.group(1))
        month = int(short_date_match.group(2))
        try:
            dt = datetime(now.year, month, day)
            return f"{dt.day}-{dt.month}-{dt.year}"
        except ValueError:
            pass

    # 2. Try "ordinal/number month" — e.g. "sixth February", "6th February", "6 February"
    #    An optional year lets the bot route the expense to the right year tab.
    #    Build ordinal pattern
    ordinal_words = "|".join(ORDINAL_NUMBERS.keys())
    month_words = "|".join(MONTH_NAMES.keys())

    # Pattern: "sixth February" or "6th February" or "6th of February" or "6 Feb"
    match = re.search(
        rf"({ordinal_words}|\d{{1,2}}(?:st|nd|rd|th)?)\s+(?:of\s+)?({month_words})"
        rf"(?:\s*,?\s*(\d{{4}}))?",
        lower
    )
    if match:
        parsed_date = _format_date_parts(
            match.group(1).strip(),
            match.group(2).strip(),
            match.group(3),
            now.year,
        )
        if parsed_date:
            return parsed_date

    # Pattern: "February sixth" or "February 6th" or "February of 6th" or "Feb 6"
    match = re.search(
        rf"({month_words})\s+(?:of\s+)?({ordinal_words}|\d{{1,2}}(?:st|nd|rd|th)?)"
        rf"(?:\s*,?\s*(\d{{4}}))?",
        lower
    )
    if match:
        parsed_date = _format_date_parts(
            match.group(2).strip(),
            match.group(1).strip(),
            match.group(3),
            now.year,
        )
        if parsed_date:
            return parsed_date

    # 3. Default to today
    return f"{now.day}-{now.month}-{now.year}"


def parse_expense(
    text: str,
    learned_categories: dict[str, str] | None = None,
) -> dict:
    """
    Parse a natural language string into an expense object.

    Args:
        text: The raw text (from voice transcription or typed input).

    Returns:
        Dict with keys: amount, category, description, date.
    """
    amount = extract_amount(text)
    category = detect_category(text, learned_categories=learned_categories)
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
    r"\bget\s+rid\s+of\b",
    r"\bcancel\b.*\bexpense\b",
    r"\bcancel\b.*\b(entry|record|transaction|purchase)\b",
    r"\berase\b",
    r"\bscratch that\b",
    r"\bthat was wrong\b",
    r"\bdelete that\b",
    r"\bremove that\b",
    r"\bdelete last\b",
    r"\bremove last\b",
    r"\bundo last\b",
]

# Speech-to-text may call an expense an "entry", "transaction", or even a
# "response". These words describe the record being removed; they are not a
# search term. Keeping them here also makes phrases such as "remove the most
# recent response" resolve to the latest expense instead of a keyword search.
_DELETE_FILLER_WORDS = re.compile(
    r"\b(?:delete|remove|undo|erase|cancel|revert|rollback|scratch|"
    r"get|rid|of|the|last|latest|most|recent|previous|prior|newest|"
    r"just|now|my|our|an|a|that|this|one|thing|please|could|can|would|"
    r"you|i|me|for|from|the|bot|assistant|response|responses|message|"
    r"messages|expense|expenses|entry|entries|log|logs|record|records|"
    r"transaction|transactions|purchase|purchases|item|items|payment|"
    r"payments|spending|spent|was|wrong)\b",
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
    # Voice transcription can occasionally return an unexpected null or
    # non-string value. Treat that as an ordinary, unrecognised message so it
    # never crashes the message handler.
    if not isinstance(text, str):
        return None

    lower = text.lower().strip()
    if not lower:
        return None

    # Check if any delete trigger phrase is present
    is_delete = any(re.search(p, lower) for p in _DELETE_TRIGGER_PHRASES)
    if not is_delete:
        return None

    # Try to extract a meaningful keyword (what to delete).
    # Strip common filler words and pull what's left.
    stripped = _DELETE_FILLER_WORDS.sub("", lower)
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
