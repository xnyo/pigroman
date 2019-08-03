mapping = {
    "b": 1,
    "k": 1024,
    "m": 1024 * 1024,
    "g": 1024 * 1024 * 1024
}


def readable_size_to_number(s: str) -> int:
    unit = s.lower()[-1]
    if unit.isdigit():
        return int(s)
    if unit in mapping:
        return round(float(s[:-1]) * mapping[unit])
    raise ValueError("Invalid block size. Examples: 1G, 800M, 1073741824")


def number_to_readable_size(b: int) -> str:
    items = list(mapping.items())
    for (xu, x), (yu, y) in zip(items, items[1:]):
        print(b, "~", x, xu, y, yu)
        if x < b < y:
            return f"{b/x:.2f} {yu.upper() if b > x else xu.upper()}B"
    return f"{b} B"
