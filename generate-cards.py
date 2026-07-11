#!/usr/bin/env python3

# The Rules of Acquisition @ ferengi.bible
# Business card generator -- "Latinum Certificate" banknote design
# Copyright (C) 2025 Joey Parrish
# Licensed under CC0 1.0 (see LICENSE)
#
# Renders one card per Rule of Acquisition as a MakePlayingCards-ready PNG:
# a shared front plus a per-rule back, in two independent palettes (cream, dark).
# See cards/AGENTS.md for the full design record and the context behind it.
#
# Run within a virtualenv using cards/requirements.txt:
#
#     .venv/bin/python3 generate-cards.py
#
# Native deps: cairo (for Python cairosvg), plus optipng / pngcrush / pngquant
# for the --optimize stages.

import os
import sys

# On macOS, Homebrew installs libcairo under a prefix that dyld does not search
# by default, so cairocffi (under cairosvg) cannot load it. Prepend the Homebrew
# lib dirs to the dyld fallback path and re-exec once so the loader sees them.
# Only when run as the CLI: importing this module must not re-exec its host.
# (Importers that render must set DYLD_FALLBACK_LIBRARY_PATH themselves.)
if __name__ == "__main__" and sys.platform == "darwin":
    _brew_libs = "/opt/homebrew/lib:/usr/local/lib"
    _have = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
    if "/opt/homebrew/lib" not in _have and "/usr/local/lib" not in _have:
        os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = (
            _brew_libs + (":" + _have if _have else "")
        )
        os.execv(sys.executable, [sys.executable] + sys.argv)

import argparse
import math
import shutil
import subprocess
import tempfile
import time

import cairosvg
from PIL import Image, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(HERE, "cards", "fonts")
BODONI_TTF = os.path.join(FONT_DIR, "BodoniModa-VariableFont_opsz,wght.ttf")
PLEX_TTF = os.path.join(FONT_DIR, "IBMPlexMono-Regular.ttf")

# A subset of rules that get printed, so that the cards fit in a box.
from cards.printed_rules import PRINTED_RULES

# Make sure there are no duplicate rules and not too many.
MAX_PRINTED_RULES = 120
assert(len(PRINTED_RULES) == len(set(PRINTED_RULES)))
assert(len(PRINTED_RULES) <= MAX_PRINTED_RULES)


# *** Geometry ***

# UNITS_PER_INCH is the scale of the SVG coordinate system -- how many viewBox
# units make one inch. It is NOT the output resolution. The SVG declares its
# size in inches, so the renderer maps that to pixels at whatever DPI you ask
# for. The value 300 is arbitrary and unrelated to any 300 dpi. Every constant
# below is in these units, so all of them are physical measurements.
UNITS_PER_INCH = 300.0
TRIM_W, TRIM_H = 1050, 600      # 3.5 x 2 in
BLEED = 36.0                    # 0.12 in per side -> 3.74 x 2.24 in artboard (MakePlayingCards)
SAFE = 36.0                     # 0.12 in inside trim -> 3.26 x 1.76 in safe box

FRAME = dict(L=50, T=44, R=50, B=44)          # symmetric, all >= SAFE
TEXT_MAX_W = 770               # widest a rule line may set
TEXT_SIZE_MAX, TEXT_SIZE_MIN = 46, 26
LINE_RATIO = 1.22              # leading as a multiple of font size

# URL cartouche (the banknote serial). Its width follows the measured URL, with
# equal padding on both sides, so a 1- vs 3-digit number stays balanced.
CART_SIZE, CART_PAD, CART_H = 16, 14, 38

# Curves are emitted as polylines, so their sampling density is the one thing
# that genuinely depends on output resolution. It is derived, never hard-coded:
# call set_output_dpi() before building. The rosette lobe tips have a curvature
# radius of ~0.69 units (1.85 device px at 800 dpi), so a chord target below
# ~1.5 px samples finer than the feature it is drawing and buys nothing.
DEFAULT_DPI = 800
TARGET_CHORD_PX = 1.5
CURVE_STEPS_MAX = 40000

CURVE_TOL = TARGET_CHORD_PX * UNITS_PER_INCH / DEFAULT_DPI   # derived, not chosen
_curve_dpi = DEFAULT_DPI


def set_output_dpi(dpi, chord_px=TARGET_CHORD_PX):
    """Size curve sampling for a given output resolution. Chord tolerance moves
    inversely with dpi: tol_units = chord_px * UNITS_PER_INCH / dpi."""
    global CURVE_TOL, _curve_dpi
    CURVE_TOL, _curve_dpi = chord_px * UNITS_PER_INCH / dpi, dpi
    return CURVE_TOL


BASE_URL = "https://ferengi.bible/#"
DISCLAIMER = "NON-REFUNDABLE · TERMS SUBJECT TO CHANGE"
LABEL = "RULES OF ACQUISITION"


# *** Palettes ***

PALETTES = {
    # reversed-out lines gain on press, so they carry more weight
    "dark":  dict(bg="#241A12", ink="#C9A227", pale="#E8D48B",
                  w_hair=0.95, w_rule=2.6, w_inner=1.05, w_lathe=0.95),
    # positive lines on light stock hold much finer detail
    "cream": dict(bg="#EFE3C6", ink="#6B4E14", pale="#3E2C0C",
                  w_hair=0.55, w_rule=2.2, w_inner=0.70, w_lathe=0.60),
}

# *** Fonts ***

# cairosvg resolves fonts through fontconfig by family name; it does not fetch
# the web font an @import would name. So we point fontconfig at the bundled TTFs
# (identical family names: "Bodoni Moda", "IBM Plex Mono") and let it match.
FONTS = ('<style>'
         '.display{font-family:"Bodoni Moda","Didot",Georgia,serif}'
         '.mono{font-family:"IBM Plex Mono",ui-monospace,monospace}'
         '</style>')


def setup_fontconfig():
    """Make the bundled TTFs visible to cairosvg without installing anything
    system-wide. Writes a throwaway fontconfig config that adds cards/fonts, and
    points FONTCONFIG_FILE at it. Must run before the first cairosvg render."""
    cache = tempfile.mkdtemp(prefix="ferengi-fc-")
    conf = os.path.join(cache, "fonts.conf")
    with open(conf, "w") as f:
        f.write(
            '<?xml version="1.0"?>\n'
            '<!DOCTYPE fontconfig SYSTEM "fonts.dtd">\n'
            '<fontconfig>\n'
            f'  <dir>{FONT_DIR}</dir>\n'
            f'  <cachedir>{cache}</cachedir>\n'
            '  <include ignore_missing="yes">/opt/homebrew/etc/fonts/fonts.conf</include>\n'
            '  <include ignore_missing="yes">/usr/local/etc/fonts/fonts.conf</include>\n'
            '</fontconfig>\n'
        )
    os.environ["FONTCONFIG_FILE"] = conf


# *** Primitives ***

def mix(c1, c2, t):
    a = [int(c1[i:i+2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i+2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(a[i] + (b[i]-a[i])*t):02x}" for i in range(3))


def _path(pts, close=True):
    return "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in pts) + (" Z" if close else "")


def _arc_steps(fn, n_probe=600):
    """Pick a uniform step count that keeps the WORST chord under CURVE_TOL.

    Parametric speed varies along these curves (lobe tips are traversed much
    faster than the valleys), so sizing from mean arc length under-samples the
    tips. We probe for the maximum local speed and size from that.
    """
    probe = [fn(i / n_probe) for i in range(n_probe + 1)]
    max_speed = max(math.dist(probe[i], probe[i+1]) for i in range(n_probe)) * n_probe
    return max(n_probe, min(CURVE_STEPS_MAX, int(max_speed / CURVE_TOL) + 1))


def _rose(cx, cy, R, lobes=34, depth=0.10, harm=0.035, phase=0.0, steps=None):
    def f(u):
        t = 2 * math.pi * u
        r = R * (1 + depth*math.cos(lobes*t + phase) + harm*math.cos(2*lobes*t - phase))
        return (cx + r*math.cos(t), cy + r*math.sin(t))
    n = steps or _arc_steps(f)
    return [f(i / n) for i in range(n + 1)]


def rosette(cx, cy, R, rings, stroke, w):
    out = []
    for k in range(rings):
        out.append(f'<path d="{_path(_rose(cx, cy, R*(1-k*0.16), lobes=max(34-k*4,12), depth=0.10+k*0.02, phase=k*0.36))}"'
                   f' fill="none" stroke="{stroke}" stroke-width="{w}" stroke-linejoin="round"/>')
    out.append(f'<circle cx="{cx}" cy="{cy}" r="{R*0.05:.1f}" fill="{stroke}"/>')
    return "\n".join(out)


def lathe(x0, x1, cy, amp, freq, lines, stroke, w, taper=True):
    out, span = [], x1 - x0
    for k in range(lines):
        ph = k * (2*math.pi/lines)

        def f(t, ph=ph):
            env = math.sin(math.pi*t) if taper else 1.0
            y = cy + amp*env*math.sin(freq*t*2*math.pi + ph) \
                   + amp*0.35*env*math.sin(freq*2.7*t*2*math.pi - ph)
            return (x0 + span*t, y)
        n = _arc_steps(f)
        pts = [f(i / n) for i in range(n + 1)]
        out.append(f'<path d="{_path(pts, False)}" fill="none" stroke="{stroke}" stroke-width="{w}"/>')
    return "\n".join(out)


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# *** Text Fitting ***

# Exact metrics via Pillow. Bodoni Moda for the rule body, IBM Plex Mono for the
# wordmark; both measured from the bundled TTFs so wrap and fit match the render.
_FONT_CACHE = {}


def _pil_font(ttf, size):
    key = (ttf, round(size * 4))
    f = _FONT_CACHE.get(key)
    if f is None:
        f = ImageFont.truetype(ttf, round(size * 4))
        _FONT_CACHE[key] = f
    return f


def measure(s, size, ttf, letter_spacing=0.0):
    w = _pil_font(ttf, size).getlength(s) / 4.0
    if letter_spacing and len(s) > 1:
        w += letter_spacing * (len(s) - 1)
    return w


def text_width(s, size):
    return measure(s, size, BODONI_TTF)


def fit_size(lines):
    size = TEXT_SIZE_MAX
    while size > TEXT_SIZE_MIN and max(text_width(line, size) for line in lines) > TEXT_MAX_W:
        size -= 1
    return size


# *** Line Breaking ***

# Chooses WHERE a rule wraps; fit_size then chooses the point size.
def balance(text, max_chars_per_line, initial_leftovers=0):
    # If it fits on one line, we're done.
    if len(text) <= max_chars_per_line:
        return [text]

    # Split the text into words.
    words = text.split(' ')

    # Count the number of lines we should need.
    num_lines = 1
    accumulated_len = -1
    for word in words:
        accumulated_len += len(word) + 1
        if accumulated_len > max_chars_per_line:
            accumulated_len = len(word)
            num_lines += 1

    # Compute our ideal line length.
    ideal_line_len = math.ceil(len(text) / num_lines)
    lines = []
    current_line = ''
    leftovers = initial_leftovers

    for word in words:
        # This line can be the ideal length + any letter not used from previous
        # lines, up to the hard maximum line length.
        this_line_max_len = min(ideal_line_len + leftovers, max_chars_per_line)

        # If this word would overflow the line, stop and store a line of words.
        if len(current_line) + len(word) > this_line_max_len:
            leftovers = this_line_max_len - len(current_line)
            lines.append(current_line)
            current_line = ''

        # Add to the current line.
        if current_line:
            current_line += ' '
        current_line += word

    if current_line:
        lines.append(current_line)

    if len(lines) > num_lines:
        # If we ended up with too many lines, try again with one more extra
        # character allocated to the first line.
        if initial_leftovers < max_chars_per_line:
            return balance(text, max_chars_per_line, initial_leftovers + 1)
        else:
            raise RuntimeError('Line overflow! ' + repr(text))

    return lines


# *** Back ***

def build_svg(number, lines, palette="dark", guides=False):
    """Return SVG source for one rule's back."""
    P = PALETTES[palette]
    bg, ink, pale = P["bg"], P["ink"], P["pale"]
    faint = mix(bg, ink, 0.16)
    L, T, R, B = FRAME["L"], FRAME["T"], FRAME["R"], FRAME["B"]
    fx, fy = L, T
    fw, fh = TRIM_W - L - R, TRIM_H - T - B

    s = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"'
         f' viewBox="{-BLEED} {-BLEED} {TRIM_W+2*BLEED} {TRIM_H+2*BLEED}"'
         f' width="{(TRIM_W+2*BLEED)/UNITS_PER_INCH:.3f}in" height="{(TRIM_H+2*BLEED)/UNITS_PER_INCH:.3f}in">',
         FONTS,
         f'<rect x="{-BLEED}" y="{-BLEED}" width="{TRIM_W+2*BLEED}" height="{TRIM_H+2*BLEED}" fill="{bg}"/>']

    for cy in range(-30, TRIM_H + 60, 46):
        s.append(lathe(-BLEED, TRIM_W+BLEED, cy, 11, 9, 3, faint, P["w_hair"], taper=False))

    s.append(f'<rect x="{fx}" y="{fy}" width="{fw}" height="{fh}" fill="none" stroke="{ink}" stroke-width="{P["w_rule"]}"/>')
    s.append(f'<rect x="{fx+6}" y="{fy+6}" width="{fw-12}" height="{fh-12}" fill="none" stroke="{ink}" stroke-width="{P["w_inner"]}"/>')
    s.append(lathe(fx+40, fx+fw-40, fy+30, 9, 11, 6, ink, P["w_lathe"]))
    s.append(lathe(fx+40, fx+fw-40, fy+fh-30, 9, 11, 6, ink, P["w_lathe"]))
    s.append(rosette(L+54, TRIM_H-B-60, 62, 6, ink, P["w_lathe"]))
    s.append(rosette(TRIM_W-R-52, T+52, 38, 5, ink, P["w_lathe"]))

    s.append(f'<text class="mono" transform="translate({L-9},{TRIM_H*0.46}) rotate(-90)" text-anchor="middle"'
             f' font-size="8.5" letter-spacing="1.5" fill="{ink}">{DISCLAIMER}</text>')
    s.append(f'<text class="mono" x="{fx+fw-34}" y="{fy+fh-62}" text-anchor="end" font-size="15"'
             f' letter-spacing="3" fill="{ink}">{LABEL}</text>')

    if number is not None:
        url = f"{BASE_URL}{number}"
        # Size the cartouche to the measured URL so the left/right margins stay
        # balanced regardless of the number's digit count (IBM Plex Mono, 16).
        box_w = measure(url, CART_SIZE, PLEX_TTF) + 2 * CART_PAD
        s.append(f'<a href="{url}" target="_blank"><g transform="translate({fx+34},{fy+68})">')
        s.append(f'<rect x="0" y="0" width="{box_w:.1f}" height="{CART_H}" fill="{bg}" stroke="{ink}" stroke-width="{P["w_inner"]}"/>')
        s.append(f'<rect x="3" y="3" width="{box_w-6:.1f}" height="{CART_H-6}" fill="none" stroke="{ink}" stroke-width="{P["w_hair"]}"/>')
        s.append(f'<text class="mono" x="{CART_PAD}" y="25" font-size="{CART_SIZE}" fill="{pale}">'
                 f'<tspan fill="{ink}">{BASE_URL}</tspan>'
                 f'<tspan fill="{pale}" font-weight="500">{number}</tspan></text>')
        s.append('</g></a>')

    if lines:
        size = fit_size(lines)
        ls = size * LINE_RATIO
        cy = TRIM_H / 2
        first = cy + 0.33*size - (len(lines)-1) * ls / 2
        for i, line in enumerate(lines):
            last = (i == len(lines) - 1)
            s.append(f'<text class="display" x="{TRIM_W/2+14}" y="{first + i*ls:.1f}" text-anchor="middle"'
                     f' font-size="{size}" font-weight="{600 if last else 400}"'
                     f' fill="{ink if last else pale}">{esc(line)}</text>')

    if guides:
        s.append(f'<rect x="{-BLEED}" y="{-BLEED}" width="{TRIM_W+2*BLEED}" height="{TRIM_H+2*BLEED}" fill="none" stroke="#00A0FF" stroke-width="1.6" stroke-dasharray="8 6"/>')
        s.append(f'<rect x="0" y="0" width="{TRIM_W}" height="{TRIM_H}" fill="none" stroke="#FF2D9B" stroke-width="1.6"/>')
        s.append(f'<rect x="{SAFE}" y="{SAFE}" width="{TRIM_W-2*SAFE}" height="{TRIM_H-2*SAFE}" fill="none" stroke="#00E5C0" stroke-width="1.6" stroke-dasharray="12 6"/>')

    s.append('</svg>')
    return "\n".join(s)


# *** Front ***

# The face all cards share. The border is symmetric (same as the back), but the
# large/small rosettes are swapped left-to-right, so after duplex printing (flip
# on the long edge) the large rosette lands on the same physical edge as the
# back's. The differently sized rosettes read as a watermark, not a mistake.
TITLE = "RULES OF ACQUISITION"
EYEBROW = "FERENGI COMMERCE AUTHORITY"
SITE = "https://ferengi.bible/"

# The wordmark is flanked by two rules. The gap between the text and each rule is
# derived from the measured half-width of the wordmark plus a margin expressed in
# ems of the wordmark's own size, so nothing overlaps regardless of the string.
WORDMARK_SIZE = 17
WORDMARK_LS = 2
WORDMARK_MARGIN_EM = 0.6
WORDMARK_RULE_LEN = 150


def build_front_svg(palette="dark", guides=False):
    P = PALETTES[palette]
    bg, ink, pale = P["bg"], P["ink"], P["pale"]
    faint = mix(bg, ink, 0.16)      # background lathe field
    medallion = mix(bg, ink, 0.30)  # watermark rosette behind the title

    L, T, R, B = FRAME["L"], FRAME["T"], FRAME["R"], FRAME["B"]   # symmetric; only rosettes swap
    fx, fy = L, T
    fw, fh = TRIM_W - L - R, TRIM_H - T - B
    cx, cy = TRIM_W / 2, TRIM_H / 2

    s = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"'
         f' viewBox="{-BLEED} {-BLEED} {TRIM_W+2*BLEED} {TRIM_H+2*BLEED}"'
         f' width="{(TRIM_W+2*BLEED)/UNITS_PER_INCH:.3f}in" height="{(TRIM_H+2*BLEED)/UNITS_PER_INCH:.3f}in">',
         FONTS,
         f'<rect x="{-BLEED}" y="{-BLEED}" width="{TRIM_W+2*BLEED}" height="{TRIM_H+2*BLEED}" fill="{bg}"/>']

    for y in range(-30, TRIM_H + 60, 46):
        s.append(lathe(-BLEED, TRIM_W+BLEED, y, 11, 9, 3, faint, P["w_hair"], taper=False))

    # watermark medallion -- the banknote portrait vignette, with no portrait
    s.append(rosette(cx, cy, 150, 9, medallion, P["w_lathe"]))

    s.append(f'<rect x="{fx}" y="{fy}" width="{fw}" height="{fh}" fill="none" stroke="{ink}" stroke-width="{P["w_rule"]}"/>')
    s.append(f'<rect x="{fx+6}" y="{fy+6}" width="{fw-12}" height="{fh-12}" fill="none" stroke="{ink}" stroke-width="{P["w_inner"]}"/>')
    s.append(lathe(fx+40, fx+fw-40, fy+30, 9, 11, 6, ink, P["w_lathe"]))
    s.append(lathe(fx+40, fx+fw-40, fy+fh-30, 9, 11, 6, ink, P["w_lathe"]))

    # rosettes swapped l-to-r vs the back: large bottom-right, small top-left
    s.append(rosette(TRIM_W-R-54, TRIM_H-B-60, 62, 6, ink, P["w_lathe"]))
    s.append(rosette(L+52, T+52, 38, 5, ink, P["w_lathe"]))

    # microtype up the right border, reading top to bottom
    s.append(f'<text class="mono" transform="translate({TRIM_W-R+9},{TRIM_H*0.48}) rotate(90)" text-anchor="middle"'
             f' font-size="8.5" letter-spacing="1.5" fill="{ink}">{DISCLAIMER}</text>')

    s.append(f'<text class="mono" x="{cx}" y="{cy-86:.0f}" text-anchor="middle" font-size="12"'
             f' letter-spacing="6" fill="{ink}">{EYEBROW}</text>')
    s.append(f'<text class="display" x="{cx}" y="{cy+22:.0f}" text-anchor="middle" font-size="64"'
             f' font-weight="600" fill="{pale}">{TITLE}</text>')

    # rule / wordmark / rule -- gap derived from the measured wordmark width
    half = measure(SITE, WORDMARK_SIZE, PLEX_TTF, WORDMARK_LS) / 2
    gap = half + WORDMARK_MARGIN_EM * WORDMARK_SIZE
    ry = cy + 72
    s.append(f'<line x1="{cx-gap-WORDMARK_RULE_LEN:.1f}" y1="{ry}" x2="{cx-gap:.1f}" y2="{ry}" stroke="{ink}" stroke-width="{P["w_inner"]}"/>')
    s.append(f'<line x1="{cx+gap:.1f}" y1="{ry}" x2="{cx+gap+WORDMARK_RULE_LEN:.1f}" y2="{ry}" stroke="{ink}" stroke-width="{P["w_inner"]}"/>')
    s.append(f'<text class="mono" x="{cx}" y="{cy+77:.0f}" text-anchor="middle" font-size="{WORDMARK_SIZE}"'
             f' letter-spacing="{WORDMARK_LS}" fill="{ink}">{esc(SITE)}</text>')

    if guides:
        s.append(f'<rect x="{-BLEED}" y="{-BLEED}" width="{TRIM_W+2*BLEED}" height="{TRIM_H+2*BLEED}" fill="none" stroke="#00A0FF" stroke-width="1.6" stroke-dasharray="8 6"/>')
        s.append(f'<rect x="0" y="0" width="{TRIM_W}" height="{TRIM_H}" fill="none" stroke="#FF2D9B" stroke-width="1.6"/>')
        s.append(f'<rect x="{SAFE}" y="{SAFE}" width="{TRIM_W-2*SAFE}" height="{TRIM_H-2*SAFE}" fill="none" stroke="#00E5C0" stroke-width="1.6" stroke-dasharray="12 6"/>')

    s.append('</svg>')
    return "\n".join(s)


# *** Render ***
def render_png(svg_src, out_path, dpi):
    if dpi > _curve_dpi:
        print(f"warning: geometry sampled for {_curve_dpi} dpi but rendering at {dpi}; "
              f"call set_output_dpi({dpi}) first or curves may facet", file=sys.stderr)
    w = round((TRIM_W + 2*BLEED) / UNITS_PER_INCH * dpi)
    h = round((TRIM_H + 2*BLEED) / UNITS_PER_INCH * dpi)
    cairosvg.svg2png(bytestring=svg_src.encode(), write_to=out_path, output_width=w, output_height=h)
    Image.open(out_path).save(out_path, dpi=(dpi, dpi))
    return w, h


# *** Optimize ***

# Lossless levels shrink the PNG without touching a pixel; "pal" is a lossy
# palette reduction to test the size/quality tradeoff on the guilloche gradients.
OPTIMIZE_LEVELS = ("none", "fast", "brute", "pal")
# Benchmarked at 800 dpi: "brute" (pngcrush -brute) lands byte-identical to
# "fast" at ~20x the time -- useless on continuous-tone guilloche. "pal" (256-
# color quantize) roughly halves the file with no visible banding on either
# palette, so it is the default. See cards/AGENTS.md for the numbers.
DEFAULT_OPTIMIZE = "pal"

# Which external tools each level needs. A level whose tools are missing is
# unavailable; the benchmark skips it and the pipeline errors clearly.
LEVEL_TOOLS = {"fast": ["optipng"], "brute": ["pngcrush", "optipng"], "pal": ["pngquant", "optipng"]}


def level_available(level):
    return all(shutil.which(t) for t in LEVEL_TOOLS.get(level, []))


def _run_quiet(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def optimize_png(path, level):
    if level == "none":
        return
    if not level_available(level):
        missing = [t for t in LEVEL_TOOLS[level] if not shutil.which(t)]
        raise RuntimeError(f"optimize level {level!r} needs missing tool(s): {', '.join(missing)}")
    if level == "fast":
        _run_quiet(["optipng", "-quiet", "-o2", path])
        return
    tmp = path + ".opt"
    if level == "pal":
        _run_quiet(["pngquant", "--force", "--skip-if-larger", "--output", tmp, "--", path])
        if os.path.exists(tmp):
            os.replace(tmp, path)
        _run_quiet(["optipng", "-quiet", "-o2", path])   # o7 gains ~nothing on a paletted image
    else:  # brute, lossless
        _run_quiet(["pngcrush", "-q", "-rem", "allb", "-brute", "-reduce", path, tmp])
        if os.path.exists(tmp):
            os.replace(tmp, path)
        _run_quiet(["optipng", "-quiet", "-o7", path])


# *** Previews ***

# Small downscaled images for cards/README.md. Not print assets; just proofs.
PREVIEW_W = 700
PREVIEW_RULE = 62   # a two-line rule, shows the two-color accent flow


def make_preview(src_png, dst_png):
    img = Image.open(src_png).convert("RGB")
    h = round(img.height * PREVIEW_W / img.width)
    img.resize((PREVIEW_W, h), Image.LANCZOS).save(dst_png)
    optimize_png(dst_png, "fast")


# *** Data ***

def load_rules():
    """Read rules.txt (tab-separated number<TAB>text) into [(number, text), ...]."""
    all_rules = []
    all_numbers = set()

    with open(os.path.join(HERE, "rules.txt")) as f:
        for line in f.read().strip().split("\n"):
            number_str, text = line.split("\t")
            number = int(number_str)
            all_rules.append((number, text))
            all_numbers.add(number)

    # Make sure all the rules in PRINTED_RULES are valid
    for number in PRINTED_RULES:
        assert(number in all_numbers)

    # Now filter the rules
    keepers = set(PRINTED_RULES)
    out = list(filter(lambda t: t[0] in keepers, all_rules))
    assert(len(out) <= MAX_PRINTED_RULES)
    return out


# *** Benchmark ***

def run_benchmark(dpi, wrap):
    """Render one front + one back per palette raw, then time and measure each
    optimize level on copies. Used to pick DEFAULT_OPTIMIZE."""
    scratch = tempfile.mkdtemp(prefix="ferengi-bench-")
    rules = dict(load_rules())
    sample_n = PREVIEW_RULE if PREVIEW_RULE in rules else sorted(rules)[0]
    samples = []
    for pal in sorted(PALETTES):
        fpath = os.path.join(scratch, f"front-{pal}.png")
        render_png(build_front_svg(pal), fpath, dpi)
        samples.append((f"front/{pal}", fpath))
        bpath = os.path.join(scratch, f"back-{pal}.png")
        render_png(build_svg(sample_n, balance(rules[sample_n], wrap), pal), bpath, dpi)
        samples.append((f"back-{sample_n}/{pal}", bpath))

    levels = [lvl for lvl in OPTIMIZE_LEVELS[1:] if level_available(lvl)]
    skipped = [lvl for lvl in OPTIMIZE_LEVELS[1:] if lvl not in levels]
    print(f"benchmark @ {dpi} dpi  (sizes in KB, time in s)")
    if skipped:
        print(f"skipped (missing tools): {', '.join(skipped)}")
    header = f'\n{"sample":16} {"raw":>8}'
    for lvl in levels:
        header += f' {lvl:>10} {"("+lvl+" s)":>10}'
    print(header)
    for name, raw in samples:
        print(f'{name:16} {os.path.getsize(raw)/1024:8.0f}', end="", flush=True)
        for lvl in levels:
            work = raw + f".{lvl}.png"
            shutil.copy(raw, work)
            t0 = time.perf_counter()
            optimize_png(work, lvl)
            dt = time.perf_counter() - t0
            print(f' {os.path.getsize(work)/1024:10.0f} {dt:10.1f}', end="", flush=True)
        print()
    print(f"\n(scratch: {scratch})")


# *** CLI ***

def main():
    ap = argparse.ArgumentParser(description="Render Rules of Acquisition business cards.")
    ap.add_argument("--palette", choices=sorted(PALETTES),
                    help="only build this palette (default: build both)")
    ap.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    ap.add_argument("--wrap", type=int, default=30, metavar="CHARS",
                    help="max characters per line handed to the balancer (default 28)")
    ap.add_argument("--optimize", choices=OPTIMIZE_LEVELS, default=DEFAULT_OPTIMIZE)
    ap.add_argument("--only", metavar="NUMS",
                    help="comma-separated rule numbers, for quick iteration")
    ap.add_argument("--guides", action="store_true", help="overlay bleed/trim/safe guides")
    ap.add_argument("--svg", action="store_true", help="also write the intermediate SVG (debug)")
    ap.add_argument("--benchmark", action="store_true",
                    help="measure optimize levels on a small sample and exit")
    a = ap.parse_args()

    setup_fontconfig()
    set_output_dpi(a.dpi)

    if a.benchmark:
        run_benchmark(a.dpi, a.wrap)
        return

    rules = load_rules()
    if a.only:
        want = {int(x) for x in a.only.split(",")}
        rules = [r for r in rules if r[0] in want]
    palettes = [a.palette] if a.palette else sorted(PALETTES)

    for pal in palettes:
        out = os.path.join(HERE, "cards", pal)
        backs = os.path.join(out, "backs")
        os.makedirs(backs, exist_ok=True)

        front_svg = build_front_svg(pal, guides=a.guides)
        front_png = os.path.join(out, "front.png")
        if a.svg:
            open(os.path.join(out, "front.svg"), "w").write(front_svg)
        render_png(front_svg, front_png, a.dpi)
        optimize_png(front_png, a.optimize)
        print(f"[{pal}] front -> {os.path.relpath(front_png, HERE)}")

        for number, text in rules:
            lines = balance(text, a.wrap)
            svg = build_svg(number, lines, pal, guides=a.guides)
            png = os.path.join(backs, f"{number:03d}.png")
            if a.svg:
                open(os.path.join(backs, f"{number:03d}.svg"), "w").write(svg)
            render_png(svg, png, a.dpi)
            optimize_png(png, a.optimize)
            print(f"\r[{pal}] rule {number:>3}  {len(lines)} line(s)   ", end="", flush=True)
        print()

    # previews for the README (only meaningful when we built the full set)
    if not a.only:
        preview_dir = os.path.join(HERE, "cards", "preview")
        os.makedirs(preview_dir, exist_ok=True)
        rules_by_n = dict(load_rules())
        sample_n = PREVIEW_RULE if PREVIEW_RULE in rules_by_n else sorted(rules_by_n)[0]
        for pal in palettes:
            make_preview(os.path.join(HERE, "cards", pal, "front.png"),
                         os.path.join(preview_dir, f"{pal}-front.png"))
            make_preview(os.path.join(HERE, "cards", pal, "backs", f"{sample_n:03d}.png"),
                         os.path.join(preview_dir, f"{pal}-back.png"))
        print(f"previews -> {os.path.relpath(preview_dir, HERE)}")


if __name__ == "__main__":
    main()
