# Business cards -- design record

Context for anyone (human or agent) picking up the card generator. This is the
*final state* plus the *input context* that is not obvious from the code, not a
full history. The generator is `../generate-cards.py`; it reads `../rules.txt`
(the same source the website uses) and writes card PNGs under `cards/<palette>/`.

## What this is

A deck of business cards, one per Ferengi Rule of Acquisition. Each card has a
shared **front** and a per-rule **back** carrying the rule text and a deep link
(`https://ferengi.bible/#NN`). The deliverable is PNGs that could be uploaded to
MakePlayingCards.com, and (see "Storage", below) served from this repo so people
can print their own via `cards/#readme`.

## Running it

Needs the project virtualenv (carries `cairosvg` + `Pillow`), plus native tools:

```bash
.venv/bin/python3 generate-cards.py               # both palettes, full set
.venv/bin/python3 generate-cards.py --only 62     # one rule, quick iteration
.venv/bin/python3 generate-cards.py --guides      # generate a proof image
.venv/bin/python3 generate-cards.py --benchmark   # size/time of optimize levels
```

- **Python deps** live in `.venv` (gitignored): `cairosvg`, `Pillow`. Create
  with `python3 -m venv .venv` then
  `.venv/bin/pip install -r cards/requirements.txt` (pinned versions).
- **Native deps**: `cairo` (for cairosvg), and `optipng`, `pngcrush`, and
  `pngquant` for the `--optimize` levels.
- **macOS / libcairo:** dyld does not search `/opt/homebrew/lib`, so cairocffi
  can't find libcairo. The script self-heals: when run as the CLI it sets
  `DYLD_FALLBACK_LIBRARY_PATH` and re-execs once. If you *import* the module to
  reuse its functions, set that env var yourself first, or rendering fails.
- **Fonts:** cairosvg resolves fonts through fontconfig by family name; it does
  NOT fetch a web font. `setup_fontconfig()` writes a throwaway fontconfig
  config that adds `cards/fonts/` so the bundled TTFs ("Bodoni Moda", "IBM Plex
  Mono") are found. Nothing is installed system-wide.

## The aesthetic, and why

Design thesis, from the DS9 production record rather than generic "sci-fi":

> **Ferengi design is greed wearing the costume of officialdom.** Excess
> ornament deployed to look legitimate.

So the reference object is styled like a banknote.  Consequences, all
intentional -- do not "fix" them:

- **Guilloche engraving**: rose-curve rosettes and interlaced sine "lathe"
  ribbons, the way anti-counterfeiting engraving looks.
- **A serial number**: the rule's URL in a banknote-style cartouche.
- **Microtype**: a tiny disclaimer up the border,
  `NON-REFUNDABLE · TERMS SUBJECT TO CHANGE`. That is part of the joke.
- **Rosettes as watermark**: the two rosettes are deliberately different sizes
  (one large, one small), which reads like banknote watermarking. The borders
  themselves are **symmetric** -- an earlier lopsided-border idea looked like a
  mistake and was removed. Keep the borders symmetric.
- **Front/back mirroring**: the front shares the back's symmetric border, but the
  large and small rosettes are swapped left-to-right, so after duplex printing
  (long-edge flip) the large rosette lands on the same physical edge as the
  back's. Preserve that swap if you touch the front.

## Print spec (verified against MakePlayingCards; do not drift)

| | inches | design units | px @ 800 dpi |
|---|---|---|---|
| Artboard (bleed) | 3.74 x 2.24 | 1122 x 672 | 2992 x 1792 |
| Trim | 3.5 x 2 | 1050 x 600 | 2800 x 1600 |
| Safe box | 3.26 x 1.76 | 978 x 528 | 2608 x 1408 |

Bleed is **0.12 in per side, not 1/8 in** (`BLEED = SAFE = 36.0` units). 1/8 in
gives a 3.75 x 2.25 artboard, 8 px too large per dimension at 800 dpi, and MPC
scales/clips it.

**Printing conditions: regular CMYK, no foil.** This drove real decisions:
- **Reversed hairlines gain** (dark ink spreads into light lines), so the dark
  palette's strokes are heavier. Do not thin them.
- **Opacity screens drop out.** The faint background field is a *solid blended
  tint* via `mix()`, not a 10% alpha. Never reintroduce `opacity` on fine lines.
- **CMYK gold isn't gold** -- `#C9A227` on dark umber reads brown, not metal.
  Hence the cream palette, which looks like an actual engraved bearer bond.

## Code architecture

Everything is in `generate-cards.py`. Key ideas:

- **Unit system.** `UNITS_PER_INCH = 300.0` is the scale of the SVG coordinate
  system (units per inch), **not** the output DPI. The SVG declares its size in
  inches; the renderer maps to pixels at `--dpi`. So every geometry constant is
  a physical measurement that scales with DPI automatically. `font-size="46"`
  means 46/300 in. The `300` is arbitrary; it could be 1000. (It shares a value
  with a plausible DPI, which is confusing but harmless.)
- **Curve sampling is the one genuine DPI dependency.** Curves are emitted as
  polylines. `CURVE_TOL = TARGET_CHORD_PX * UNITS_PER_INCH / dpi`; call
  `set_output_dpi(dpi)` before building. `_arc_steps()` probes for the *maximum*
  local parametric speed (rose-curve lobe tips are traversed far faster than
  valleys) and sizes from that, so the worst chord -- not the mean -- stays
  under tolerance. Don't simplify it back to a fixed step count or mean arc
  length; both under-sample the tips as DPI rises. `TARGET_CHORD_PX = 1.5` is
  ~1.85 device px at 800 dpi, matched to the lobe-tip curvature radius; finer
  sampling draws detail the paper can't hold.
- **Text.** `balance()` (the project's own balanced line-breaker, carried over
  from the old ImageMagick generator) chooses *where* a rule wraps; `fit_size()`
  then shrinks the point size until the widest line fits `TEXT_MAX_W`. Two jobs,
  two functions. `--wrap` sets the balancer's max chars/line (default 28) and is
  the main knob for tuning breaks by eye. Metrics are exact via Pillow against
  the bundled TTFs. If `balance()` breaks ever look wrong on a specific rule,
  the intended fallback is per-rule manual line breaks.
- **Two-color flow:** the last line of a rule takes the accent color (`ink`) and
  weight 600; every line above it is `pale` at 400. This generalizes to any line
  count -- body reads clean, final clause turns gold. (Note `pale` is the
  higher-contrast reading color and `ink` is the themed accent, in both
  palettes.)

## Palettes

```
dark:  bg #241A12  ink #C9A227  pale #E8D48B   (heavier strokes; reversed lines gain)
cream: bg #EFE3C6  ink #6B4E14  pale #3E2C0C   (finer strokes; positive lines hold)
```

Stroke weights are per-palette (`w_hair`, `w_rule`, `w_inner`, `w_lathe`) and
are **not** interchangeable; the dark values exist to survive dot gain. There is
no "default" palette -- both are built as peers into `cards/dark/` and
`cards/cream/`.

## Fonts

- Bodoni Moda (display) + IBM Plex Mono (mono), bundled in `cards/fonts/`.
- **Bodoni Moda ships only as a Regular variable font** (no static bold). The
  600-weight title/accent lines therefore render as *synthetic* bold via
  cairo/fontconfig. It reads fine, but if you ever want true weight contrast,
  add a static Bodoni SemiBold and select it by family name.

## Optimization (benchmarked at 800 dpi)

`--optimize` levels: `none`, `fast`, `brute`, `pal`. Findings on this content:

| level | tool chain | ~size vs raw | ~time/img | notes |
|---|---|---|---|---|
| fast  | optipng -o2 | ~0.95 MB (lossless) | ~3 s | best lossless |
| brute | pngcrush -brute + optipng -o7 | **byte-identical to fast** | ~65 s | useless here; kept for completeness |
| pal   | pngquant (256) + optipng -o2 | **~0.55 MB** | ~5 s | **default** |

`pal` roughly halves the file with **no visible banding** on either palette
(checked at 1:1 on the cream background field and the dark rosette; pngquant
picks ~200-256 colors on its own). `optipng -o7` after quantizing gains nothing
over `-o2`, so `pal` uses `-o2`. Full set (133 rules x 2 palettes + 2 fronts,
~268 images) is roughly **138 MB** at `pal`.

## Output layout

```
cards/cream/front.png        cards/dark/front.png
cards/cream/backs/NNN.png    cards/dark/backs/NNN.png
cards/preview/{cream,dark}-{front,back}.png   (downscaled, for cards/README.md)
```

## Storage

The full set at `pal` is ~138 MB (cream 69 MB + dark 68 MB + previews). Decided:
**commit the loose PNGs to the repo.** The pipeline is byte-deterministic
(verified), so re-running only churns cards that actually change. The site does
**not** serve them -- `publish.yaml` strips `cards/cream` and `cards/dark` from
the Pages artifact; the print-your-own flow is browsed from the GitHub repo, and
`cards/README.md` links there. (No Git LFS: Pages would serve pointer files.)

## Known limitations / would-be-welcome

1. **URL cartouche width now follows the measured URL** (`CART_PAD` on each
   side), so 1- vs 3-digit numbers stay balanced and a longer number/domain
   grows the box instead of overflowing. It grows rightward from a fixed left
   edge; a pathologically long string could still reach the frame, but nothing
   in range does.
2. **No automated safe-zone / chord audit.** Geometry is currently trusted by
   eye (`--guides` overlays bleed/trim/safe). A bounding-box audit over every
   element (test with the *longest* rule, whose text extent depends on
   `fit_size`) would be welcome before a print run.
3. **Corner radius unverified** against the real MPC template. The large rosette
   sits ~0.14 in from trim; if MPC rounds corners aggressively, check it.
4. **Cream contrast unproofed on paper.** The engraving color may want a nudge
   once physically printed. Nobody has seen a proof.
5. **The URL appears on both faces** (`https://ferengi.bible/` wordmark on the
   front, deep link on the back). Defensible (brand vs. deep link); drop the
   front wordmark if you'd rather the two flanking rules meet as one.
