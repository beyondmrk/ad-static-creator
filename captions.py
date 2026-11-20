"""Caption layout rules for localized video ads.

Captions that run almost frame-wide get cut when Meta shows the ad as a Reel. So: at most 3 words a
line, a bigger font that stays readable on a phone, and every caption inside the Reels safe zone. Every video renderer lays its captions out through this module; `check` refuses a line
over the limit, so a renderer cannot quietly draw a wide caption again.

Reels safe zone (Meta, 9:16): keep text out of the outer 6% left/right, the top 14% and the bottom 35%.
"""
import math

MAX_WORDS = 3
SIDE, TOP, BOTTOM = 0.06, 0.14, 0.35
SIZE, MIN_SIZE = 0.075, 0.06  # caption font size as a share of frame width (54 / 43 px at 720 wide)


def is_word(tok):
    return any(ch.isalnum() for ch in tok)


def word_count(line):
    return sum(is_word(t) for t in line.split())


def chunk(text, max_words=MAX_WORDS):
    """Split text into lines of <= max_words words, balanced (4 words -> 2+2, not 3+1).
    Emoji and punctuation-only tokens ride on the line before them. Explicit newlines are kept."""
    out = []
    for para in text.split("\n"):
        toks = para.split()
        groups = []  # each word with its trailing non-word tokens
        for t in toks:
            if is_word(t) or not groups:
                groups.append([t])
            else:
                groups[-1].append(t)
        n = sum(1 for g in groups if is_word(g[0]))
        if not n:
            if para.strip():
                out.append(para.strip())
            continue
        lines = math.ceil(n / max_words)
        base, extra = divmod(n, lines)
        i = 0
        for k in range(lines):
            take = base + (1 if k < extra else 0)
            out.append(" ".join(t for g in groups[i:i + take] for t in g))
            i += take
    return check(out, max_words)


def check(lines, max_words=MAX_WORDS):
    bad = [l for l in lines if word_count(l) > max_words]
    if bad:
        raise ValueError(f"caption line over {max_words} words (Reels cut-off rule): {bad}")
    return lines


def safe_zone(w, h):
    return (w * SIDE, h * TOP, w * (1 - SIDE), h * (1 - BOTTOM))


def size(w):
    return int(round(w * SIZE))


def fit_size(lines, width_of, w, pad=0):
    """Largest font size from SIZE down to MIN_SIZE at which every line (plus 2*pad) fits the safe width.
    width_of(size, line) -> rendered px width."""
    max_w = w * (1 - 2 * SIDE) - 2 * pad
    s = size(w)
    while s > int(w * MIN_SIZE) and max(width_of(s, l) for l in lines) > max_w:
        s -= 1
    return s


def layout(text, width_of, w, pad=0):
    """(font size, lines) for a caption: 3 words a line at the biggest size that fits the safe width.
    A line that won't fit even at MIN_SIZE (a long word) drops to 2, then 1 word a line, back at full size."""
    max_w = w * (1 - 2 * SIDE) - 2 * pad
    for n in range(MAX_WORDS, 0, -1):
        lines = chunk(text, n)
        s = fit_size(lines, width_of, w, pad)
        if max(width_of(s, l) for l in lines) <= max_w or n == 1:
            return s, lines


def avoid(box, taken, w, h, gap=12):
    """Move box vertically off every rect in `taken` (below first, else above), staying in the safe zone."""
    x0, y0, x1, y1 = box
    hit = [t for t in taken if not (x1 <= t[0] or x0 >= t[2] or y1 + gap <= t[1] or y0 - gap >= t[3])]
    if not hit:
        return box
    _, sy0, _, sy1 = safe_zone(w, h)
    bh = y1 - y0
    below, above = max(t[3] for t in hit) + gap, min(t[1] for t in hit) - gap
    if below + bh <= sy1:
        return x0, below, x1, below + bh
    if above - bh >= sy0:
        return x0, above - bh, x1, above
    return x0, sy1 - bh, x1, sy1


def clamp_box(box, w, h):
    """Shift (x0, y0, x1, y1) inside the safe zone without resizing it; centre it on an axis it overfills."""
    x0, y0, x1, y1 = box
    sx0, sy0, sx1, sy1 = safe_zone(w, h)
    def axis(a0, a1, s0, s1):
        if a1 - a0 >= s1 - s0:
            c = (s0 + s1) / 2
            return c - (a1 - a0) / 2, c + (a1 - a0) / 2
        if a0 < s0:
            return s0, s0 + (a1 - a0)
        if a1 > s1:
            return s1 - (a1 - a0), s1
        return a0, a1
    x0, x1 = axis(x0, x1, sx0, sx1)
    y0, y1 = axis(y0, y1, sy0, sy1)
    return x0, y0, x1, y1
