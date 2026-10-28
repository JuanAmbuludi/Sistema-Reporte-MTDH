"""Welcome illustration of the login: a pregnant woman in profile, drawn like the map.

A figure with life-like proportions in the flat tones of the night ramp of the provinces, outlined in the same deep purple;
a soft shade on the side away from the light gives it volume.  Behind her, a faceted disc as pale as the empty map; under
her, a gold dotted ground like the equator.  Each part is a piece that assembles in turn, as the provinces do.  No data is
shown before authentication.
"""
from __future__ import annotations

from functools import lru_cache
import math

from src import theme

INK = theme.MORADO_900
RAMP = theme.NIGHT_SEQUENTIAL          # "#4E3680" … "#EFECFC"
SKIN, SKIN_SHADE = "#E4DCF7", "#C9BCEB"
HAIR_WHITE = RAMP[7]
CARDIGAN, CARDIGAN_SHADE = RAMP[3], RAMP[2]
SHIRT = RAMP[7]
TROUSERS, TROUSERS_SHADE = RAMP[1], RAMP[0]
SHOES = "#3F2A6B"
CANE = RAMP[5]
DRESS, DRESS_SHADE, DRESS_BAND = RAMP[4], RAMP[3], RAMP[2]
TIGHTS = RAMP[6]
GIRL_HAIR, GIRL_HAIR_SHADE = RAMP[2], RAMP[1]
BLUSH = theme.FUCSIA_300
GOLD, GOLD_SHADE = theme.ORO, "#E3A90B"
SHADE = "rgba(43,22,79,.20)"           # the side away from the light, over any tone
SCALE = 1.0


def _path(d: str, fill: str = "none", *, stroke: str | None = INK, width: float = 1.1, extra: str = "") -> str:
    line = f' stroke="{stroke}" stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round"' if stroke else ""
    return f'<path d="{d}" fill="{fill}"{line}{extra}/>'


def _disc(cx: float, cy: float, radius: float) -> list[str]:
    """A low-poly disc behind the figures, pale as the empty provinces: an inner hexagon and an irregular rim of twelve
    points, joined in triangles."""
    rim_scale = [1.0, .95, 1.03, .96, 1.04, .94, 1.02, .97, 1.05, .95, 1.01, .96]
    inner = [(cx + radius * .52 * math.cos(math.radians(-60 + 60 * k)), cy + radius * .52 * math.sin(math.radians(-60 + 60 * k)))
             for k in range(6)]
    rim = [(cx + radius * s * math.cos(math.radians(-90 + 30 * k)), cy + radius * s * math.sin(math.radians(-90 + 30 * k)))
           for k, s in enumerate(rim_scale)]
    tones = ["rgba(255,255,255,.05)", "rgba(255,255,255,.085)", "rgba(255,255,255,.065)"]
    triangles = [((cx, cy), inner[k], inner[(k + 1) % 6]) for k in range(6)]
    for k in range(6):
        a, b = inner[k], inner[(k + 1) % 6]
        o1, o2, o3 = rim[(2 * k + 1) % 12], rim[(2 * k + 2) % 12], rim[(2 * k + 3) % 12]
        triangles += [(a, o1, o2), (a, o2, b), (b, o2, o3)]
    return [_path("M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in tri) + " Z", tones[i % 3], stroke="rgba(255,255,255,.08)", width=.7)
            for i, tri in enumerate(triangles)]


def _pieces() -> list[list[str]]:
    """A pregnant woman in profile, life-like proportions (seven and a half heads), her hands around her belly: hair with a
    bun, face, neck, a fitted dress whose belly catches the light, arms, legs and shoes."""
    return [
        ['<ellipse cx="318" cy="440" rx="58" ry="5" fill="rgba(18,8,38,.35)"/>',
         _path("M298 428 L306 428 C308 434 318 435 326 437 C328 440 300 441 296 439 Z", SHOES),
         _path("M326 428 L334 428 C338 433 350 434 358 436 C360 440 330 441 324 439 Z", SHOES)],
        [_path("M300 410 C299 416 299 422 299 429 L307 429 C307 422 308 416 309 410 Z", SKIN),
         _path("M327 410 C327 416 327 422 327 429 L335 429 C334 422 334 416 334 410 Z", SKIN)],
        # The dress: back, shoulders, chest, the belly and a skirt that falls to the calves.
        [_path("M283 140 C292 135 306 133 317 138 C326 146 336 156 341 168 C343 178 340 186 338 192 C352 200 372 216 379 238 "
               "C384 258 374 278 352 292 C344 298 342 306 341 330 C340 356 341 384 344 411 C326 415 306 415 289 412 "
               "C288 386 287 360 284 334 C281 312 276 290 275 268 C275 252 282 236 284 220 C285 196 278 172 279 156 "
               "C279 150 280 144 283 140 Z", DRESS),
         _path("M283 140 C281 150 279 160 279 172 C280 192 285 206 284 222 C282 238 275 252 275 268 C276 290 281 312 284 334 "
               "C287 360 288 386 289 412 C294 413 298 413 302 413 C299 380 296 340 292 300 C290 280 289 262 292 246 "
               "C296 226 296 204 292 182 C290 166 290 152 293 140 Z", SHADE, stroke=None),
         _path("M339 192 C352 200 372 216 379 238 C384 258 374 278 352 292 C358 272 360 252 356 234 C352 216 346 202 339 192 Z",
               RAMP[5], stroke=None),
         _path("M318 188 C326 191 333 191 339 189", stroke=INK, width=.9),
         _path("M346 300 C344 340 346 380 350 410 M318 300 C318 340 320 380 322 413 M300 330 C301 360 302 390 303 413",
               stroke=INK, width=.7, extra=' opacity=".4"')],
        # Neck and face in profile: brow, nose, lips and chin.
        [_path("M290 104 C291 114 291 124 289 136 C298 140 310 140 318 137 C316 128 315 120 316 113 Z", SKIN_SHADE),
         _path("M296 52 C310 50 322 58 325 70 C326 75 326 79 325 82 C329 86 333 90 334 93 C332 95 329 95 327 96 "
               "C329 98 329 99 327 100.5 C328 102 328 104 326 105.5 C325 107 326 110 325 112 C321 117 313 118 306 116 "
               "C298 113 292 108 288 102 C283 94 282 80 286 66 C288 58 291 54 296 52 Z", SKIN),
         _path("M319 80 C320.5 79 322.5 79 323.5 80.5", stroke=INK, width=1.2),
         _path("M316 75.5 C318.5 73.5 322 73.5 324.5 75", stroke=GIRL_HAIR_SHADE, width=1.3),
         _path("M327 100.5 C325 101.4 323.5 101.4 322.5 101", stroke=INK, width=.9),
         '<circle cx="315" cy="98" r="3.2" fill="#E6A3C5" opacity=".55"/>'],
        # Hair gathered in a bun, with the line of the ear.
        [_path("M296 50 C284 50 274 58 272 72 C271 85 275 97 284 105 C288 101 292 97 296 95 C298 87 301 79 306 73 "
               "C311 67 317 63 322 61 C316 53 306 49 296 50 Z", GIRL_HAIR),
         '<circle cx="268" cy="66" r="14.5" fill="#795DB9" stroke="#2B164F" stroke-width="1.1"/>',
         _path("M258 60 C264 56 272 58 276 64 M260 72 C266 70 272 72 276 76", stroke=GIRL_HAIR_SHADE, width=1.1),
         _path("M282 70 C290 66 298 64 306 66", stroke=RAMP[4], width=1.4),
         _path("M298 86 C302 84 305 87 305 92 C305 97 302 99 299 98", SKIN_SHADE, width=.9)],
        # The near arm, its hand under the belly, and the far hand resting on top of it.
        [_path("M296 144 C291 168 292 196 297 214 C301 227 316 237 333 250 C341 256 347 261 351 266 L359 261 C351 251 339 240 325 228 "
               "C316 220 312 210 312 196 C312 176 314 156 313 142 Z", SKIN),
         _path("M296 144 C291 168 292 196 297 214 C300 222 306 228 314 234 C306 224 302 214 301 200 C300 182 301 162 303 146 Z",
               SHADE, stroke=None),
         _path("M349 262 C356 266 365 268 373 266 C377 264 377 260 373 259 C367 260 360 259 355 256 Z", SKIN),
         _path("M351 203 C358 200 367 205 373 213 C375 217 371 219 367 217 C361 213 355 211 349 210 Z", SKIN),
         _path("M358 206 C362 207 366 210 369 214 M356 209 C360 210 364 213 366 216", stroke=INK, width=.7)],
    ]


@lru_cache(maxsize=1)
def illustration() -> str:
    """The illustration on a single line (safe for Markdown), in the viewBox of the login map."""
    def piece(index: int, parts: list[str]) -> str:
        return f'<g class="lf-piece" style="--d:{index * 0.06:.2f}s">{"".join(parts)}</g>'
    disc = _disc(324, 236, 200)   # its lowest point rests on the ground
    ground = ('<line x1="70" y1="440.5" x2="590" y2="440.5" stroke="#F8C018" stroke-width="1.3" stroke-dasharray="2 6" '
              'stroke-linecap="round" opacity=".85"/>')
    back = "".join(piece(i, [facet]) for i, facet in enumerate(disc)) + piece(len(disc), [ground])
    figures = "".join(piece(len(disc) + 1 + i, parts) for i, parts in enumerate(_pieces()))
    # The figures are drawn standing on the ground at (324, 440) and shown a little larger, to fill the place of the map.
    return ('<svg class="lf-art" viewBox="0 0 640 464" role="img" preserveAspectRatio="xMidYMid meet" '
            'aria-label="Ilustración: una mujer embarazada">' + back
            + f'<g transform="translate(324 440) scale({SCALE}) translate(-324 -440)">{figures}</g></svg>')
