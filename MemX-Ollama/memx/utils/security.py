import re

SENSITIVE_PATTERNS = {
    "phone": re.compile(r'1[3-9]\d{9}'),
    "id_card": re.compile(r'\d{17}[\dXx]'),
    "email": re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
}

def desensitize(text: str) -> str:
    if not text:
        return text
    for pattern in SENSITIVE_PATTERNS.values():
        text = pattern.sub('***', text)
    return text
