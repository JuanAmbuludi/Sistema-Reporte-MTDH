"""Welcome illustration of the login: a grandfather and his granddaughter holding hands, drawn like the map.

Human figures with real proportions (about seven heads for him, five for her), in the flat tones of the night ramp of the
provinces and outlined in the same deep purple; a soft shade on one side of each shape gives them volume.  Behind them, a
faceted disc as pale as the empty map; under them, a gold dotted ground like the equator, and a small gold heart recalls
«El corazón de Ecuador».  Each part is a piece that assembles in turn, as the provinces do.  No data is shown before
authentication.
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
SCALE = 1.16


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


def _grandfather() -> list[list[str]]:
    """Seven heads tall, slightly bent, with a cardigan over a shirt, glasses, white hair and a cane; his right hand
    holds the girl's."""
    return [
        # Shadow on the ground and shoes.
        ['<ellipse cx="262" cy="440" rx="54" ry="5" fill="rgba(18,8,38,.35)"/>',
         _path("M226 426 C228 420 248 419 253 425 L255 435 C255 440 223 441 214 438 C210 435 216 429 226 426 Z", SHOES),
         _path("M272 426 C275 420 296 420 301 426 L305 435 C305 440 270 441 264 438 C261 434 265 429 272 426 Z", SHOES)],
        # Trousers: two legs from the hips, with the shade of the inner leg.
        [_path("M231 258 C231 292 229 330 228 362 C227 390 227 410 228 426 L254 426 C254 402 256 372 258 346 "
               "C260 322 262 302 265 284 L266 262 Z", TROUSERS),
         _path("M266 262 L268 284 C271 302 273 322 275 346 C277 372 278 402 280 426 L304 426 C303 400 301 362 299 330 "
               "C297 300 296 280 296 256 Z", TROUSERS),
         _path("M258 346 C256 372 254 402 254 426 L246 426 C247 400 250 370 254 344 C256 320 260 300 265 284 Z", SHADE, stroke=None),
         _path("M296 300 C298 330 300 362 302 400 L303 426 L297 426 C295 398 293 360 291 330 Z", SHADE, stroke=None)],
        # Shirt and cardigan, open at the neck, with its buttons, pockets and the shade of its left side.
        [_path("M249 140 L276 140 L262 198 Z", SHIRT),
         _path("M224 150 C236 141 252 139 262 139 C273 139 290 141 300 150 C307 172 307 202 303 232 L301 266 "
               "C286 270 240 270 226 266 L224 234 C219 204 218 172 224 150 Z", CARDIGAN),
         _path("M224 150 C230 146 238 143 244 142 C238 170 236 210 238 268 C234 268 229 267 226 266 L224 234 "
               "C219 204 218 172 224 150 Z", SHADE, stroke=None),
         _path("M249 142 L262 198 L262 268", stroke=INK, width=1.1),
         _path("M276 142 L262 198", stroke=INK, width=1.1),
         _path("M249 140 L276 140 L262 198 Z", SHIRT, width=1),
         _path("M251 140 L262 152 L257 159 L246 146 Z M273 140 L262 152 L267 159 L278 146 Z", HAIR_WHITE, width=.9),
         '<circle cx="266.5" cy="214" r="2.2" fill="#EFECFC" stroke="#2B164F" stroke-width=".8"/>'
         '<circle cx="266.5" cy="232" r="2.2" fill="#EFECFC" stroke="#2B164F" stroke-width=".8"/>'
         '<circle cx="266.5" cy="250" r="2.2" fill="#EFECFC" stroke="#2B164F" stroke-width=".8"/>',
         _path("M234 238 L252 238 L252 250 C246 252 240 252 234 250 Z M276 238 L294 238 L294 250 C288 252 282 252 276 250 Z",
               stroke=INK, width=.9)],
        # The arm that leans on the cane: sleeve, hand and cane with its crook.
        [_path("M226 152 C216 163 212 182 210 202 C208 218 208 234 210 248 L213 262 L229 261 C227 246 226 231 227 216 "
               "C228 198 231 180 236 166 Z", CARDIGAN),
         _path("M226 152 C216 163 212 182 210 202 C208 218 208 234 210 248 L213 262 L219 262 C216 240 216 214 219 192 "
               "C221 176 224 162 230 154 Z", SHADE, stroke=None),
         _path("M220 262 C219 250 230 246 236 254", stroke=INK, width=7.5),
         _path("M220 262 C219 250 230 246 236 254", stroke=CANE, width=4.5),
         _path("M218.5 268 L205 437", stroke=INK, width=7.5),
         _path("M218.5 268 L205 437", stroke=CANE, width=4.5),
         _path("M211 257 C208 262 208 270 212 274 C216 277 223 276 226 272 C229 267 228 261 225 257 C221 254 214 254 211 257 Z", SKIN),
         _path("M213 262 L224 262 M213 267 L224 267", stroke=INK, width=.8)],
        # The arm that reaches the girl.
        [_path("M298 152 C309 164 314 182 316 200 C318 215 323 229 331 243 L341 258 L330 266 C321 252 313 238 309 223 "
               "C305 207 301 192 296 177 Z", CARDIGAN),
         _path("M341 258 L330 266 C321 252 313 238 309 223 L314 222 C318 236 326 250 335 262 Z", SHADE, stroke=None)],
        # Neck, ears and face.
        [_path("M253 124 L271 124 L272 144 C267 149 258 149 252 144 Z", SKIN_SHADE),
         _path("M241 103 C235 100 232 107 233 113 C234 119 239 121 243 118 Z", SKIN_SHADE),
         _path("M285 103 C291 100 294 107 293 113 C292 119 287 121 283 118 Z", SKIN_SHADE),
         _path("M240 106 C240 88 250 80 263 80 C277 80 286 88 286 106 C286 118 283 126 278 131 C273 136 268 138 263 138 "
               "C257 138 251 135 247 130 C243 125 240 116 240 106 Z", SKIN),
         _path("M240 106 C240 118 243 126 247 131 C250 134 254 136 258 137 C250 129 246 119 246 106 C246 96 249 89 254 84 "
               "C246 86 240 94 240 106 Z", SHADE, stroke=None)],
        # White hair at the sides and back of the head, and bushy brows.
        [_path("M241 101 C239 91 244 84 251 82 C247 89 246 96 247 104 C245 107 242 106 241 101 Z", HAIR_WHITE, width=.9),
         _path("M285 101 C287 91 282 84 275 82 C279 89 280 96 279 104 C281 107 284 106 285 101 Z", HAIR_WHITE, width=.9),
         _path("M248 99 C251 96 256 95.5 259.5 97.5 L259 100 C255.5 98.5 251.5 99 248.5 101 Z", HAIR_WHITE, width=.7),
         _path("M267 97.5 C270.5 95.5 275.5 96 278.5 99 L278 101 C275 99 271 98.5 267.5 100 Z", HAIR_WHITE, width=.7)],
        # Glasses over smiling eyes, nose, moustache, smile and the lines of the years.
        ['<circle cx="254" cy="106.5" r="7.4" fill="rgba(255,255,255,.22)" stroke="#2B164F" stroke-width="1.4"/>'
         '<circle cx="272" cy="106.5" r="7.4" fill="rgba(255,255,255,.22)" stroke="#2B164F" stroke-width="1.4"/>',
         _path("M261.4 106 Q263 104.4 264.6 106 M246.6 105.6 L241.5 103.6 M279.4 105.6 L284.5 103.6", stroke=INK, width=1.2),
         _path("M250.6 107.4 Q254 104.2 257.4 107.4 M268.6 107.4 Q272 104.2 275.4 107.4", stroke=INK, width=1.5),
         _path("M263 108 C262 113 261 116 264 117.5", stroke=INK, width=.9),
         _path("M253 121.5 C257 118 261 118.5 263 120 C265 118.5 269 118 273 121.5 C271 125 266.5 125 263 123 "
               "C259.5 125 255 125 253 121.5 Z", HAIR_WHITE, width=.8),
         _path("M257 127.5 Q263 131 269 127.5", stroke=INK, width=1.3),
         _path("M249 117 Q250 121 253.5 123.5 M277 117 Q276 121 272.5 123.5", stroke=INK, width=.7, extra=' opacity=".55"')],
    ]


def _girl() -> list[list[str]]:
    """Five heads tall, in a dress with a round collar, tights and pigtails; she holds her grandfather's hand and waves
    with the other."""
    return [
        ['<ellipse cx="392" cy="440" rx="30" ry="4" fill="rgba(18,8,38,.35)"/>',
         _path("M376 430 C377 425 389 424 392 429 L393 436 C393 440 373 440 369 438 C367 434 371 431 376 430 Z", SHOES),
         _path("M396 430 C397 425 409 424 412 429 L414 436 C414 440 395 440 393 438 C392 434 393 431 396 430 Z", SHOES)],
        [_path("M380 366 C380 390 379 410 380 431 L391 431 C391 410 391 390 391 366 Z", TIGHTS),
         _path("M395 366 C395 390 395 410 396 431 L407 431 C408 410 407 390 406 366 Z", TIGHTS),
         _path("M386 368 C386 392 386 412 386.5 431 L391 431 C391 410 391 390 391 366 Z", SHADE, stroke=None)],
        # The dress: fitted at the chest, a band at the waist and a skirt that opens.
        [_path("M374 282 C380 279 387 278 392 278 C397 278 405 279 410 282 C414 296 416 310 417 320 C422 338 426 356 429 372 "
               "C414 379 371 379 355 372 C359 356 363 338 367 320 C369 310 371 296 374 282 Z", DRESS),
         _path("M374 282 C380 279 384 278.5 386 278.5 C381 300 376 330 372 377 C366 376 360 374 355 372 C359 356 363 338 367 320 "
               "C369 310 371 296 374 282 Z", SHADE, stroke=None),
         _path("M367 316 C380 320.5 404 320.5 417 316 L418.5 325 C404 329.5 380 329.5 365.5 325 Z", DRESS_BAND),
         _path("M392 330 L392 376 M380 331 L376 376 M404 331 L408 376", stroke=INK, width=.7, extra=' opacity=".45"'),
         _path("M382.5 281 C383 289 390 291 392 285 C390 281 386.5 279.5 382.5 281 Z", HAIR_WHITE, width=.8),
         _path("M401.5 281 C401 289 394 291 392 285 C394 281 397.5 279.5 401.5 281 Z", HAIR_WHITE, width=.8)],
        # The arm that holds her grandfather's hand, and her hand inside his.
        [_path("M375 283 C368 285 365 292 367 299 L377 296 Z", DRESS),
         _path("M369 292 C361 287 352 280 346 272 L340 276 C346 286 355 296 365 302 Z", SKIN),
         _path("M369 292 C361 287 352 280 346 272 L344 274 C350 283 357 291 366 298 Z", SHADE, stroke=None),
         _path("M337 268 C334 272 336 279 342 280 C347 281 350 276 348 271 C346 267 340 265 337 268 Z", SKIN)],
        # The grandfather's hand around hers.
        [_path("M330 258 C334 253 342 255 346 261 C349 267 345 274 338 275 C332 274 328 267 330 258 Z", SKIN),
         _path("M333 263 C337 262 341 264 343 268 M332 268 C336 267 339 269 341 272", stroke=INK, width=.8)],
        # The arm that waves: sleeve, arm and an open hand.
        [_path("M409 283 C416 285 419 292 417 299 L407 296 Z", DRESS),
         _path("M413 292 C421 283 427 271 429 258 L437 260 C436 276 428 290 419 300 Z", SKIN),
         _path("M429 258 L433 259 C432 274 425 289 417 298 L415 295 C422 286 427 272 429 258 Z", SHADE, stroke=None),
         # An open hand: palm, four fingers and the thumb (each finger an outlined stroke).
         _path("M428 243.5 L426.5 236.5 M431.6 242.5 L431 234.5 M435.2 243 L435.8 235.2 M438.6 245 L440.6 238.4 M440.5 252 L445.5 248.5",
               stroke=INK, width=4.4),
         _path("M428 243.5 L426.5 236.5 M431.6 242.5 L431 234.5 M435.2 243 L435.8 235.2 M438.6 245 L440.6 238.4 M440.5 252 L445.5 248.5",
               stroke=SKIN, width=2.4),
         '<ellipse cx="433.5" cy="251" rx="7.2" ry="8.2" fill="#E4DCF7" stroke="#2B164F" stroke-width="1.1"/>'],
        # Neck and face.
        [_path("M387 265 L397 265 L398 281 C395 284 389 284 386 281 Z", SKIN_SHADE),
         _path("M374 248 C374 234 382 226 392 226 C403 226 410 234 410 248 C410 258 407 265 402 269 C399 272 395 273 392 273 "
               "C388 273 384 272 381 269 C377 265 374 258 374 248 Z", SKIN),
         _path("M374 248 C374 258 377 265 381 269 C384 271.5 387 272.5 389 273 C382 266 379 257 379 247 C379 239 382 233 386 229 "
               "C379 232 374 239 374 248 Z", SHADE, stroke=None)],
        # Hair: a fringe swept to one side and two pigtails with their ties.
        [_path("M373 246 C362 248 358 258 360 270 C361 277 366 281 370 279 C367 270 369 259 376 252 Z", GIRL_HAIR_SHADE),
         _path("M411 246 C422 248 426 258 424 270 C423 277 418 281 414 279 C417 270 415 259 408 252 Z", GIRL_HAIR_SHADE),
         _path("M372 250 C369 233 379 220 392 220 C406 220 415 232 412 250 C410 242 406 236 400 233 C396 240 386 243 378 240 "
               "C375 243 373 246 372 250 Z", GIRL_HAIR),
         _path("M381 229 C387 225 396 224 402 227", stroke=RAMP[4], width=1.6),
         f'<circle cx="372.5" cy="248" r="3.4" fill="{BLUSH}" stroke="#2B164F" stroke-width=".8"/>'
         f'<circle cx="411.5" cy="248" r="3.4" fill="{BLUSH}" stroke="#2B164F" stroke-width=".8"/>'],
        # Eyes, brows, nose, cheeks and a wide smile.
        ['<ellipse cx="385.5" cy="250.5" rx="1.9" ry="2.4" fill="#2B164F"/><ellipse cx="398.5" cy="250.5" rx="1.9" ry="2.4" fill="#2B164F"/>'
         '<circle cx="386.1" cy="249.7" r=".6" fill="#FFFFFF"/><circle cx="399.1" cy="249.7" r=".6" fill="#FFFFFF"/>',
         _path("M382 245 Q385.5 243 389 244.6 M395 244.6 Q398.5 243 402 245", stroke=GIRL_HAIR_SHADE, width=1.2),
         _path("M392 253 Q391 257 393 258", stroke=INK, width=.8),
         f'<circle cx="380.5" cy="258" r="3.3" fill="{BLUSH}" opacity=".75"/><circle cx="403.5" cy="258" r="3.3" fill="{BLUSH}" opacity=".75"/>',
         _path("M386 261 Q392 268 398 261 Q392 263.2 386 261 Z", INK, width=.9),
         _path("M387.5 261.6 Q392 263.4 396.5 261.6 L396 262.6 Q392 264 388 262.6 Z", "#FFFFFF", stroke=None)],
    ]


def _pieces() -> list[list[str]]:
    """The parts in the order they assemble: the grandfather, the girl and the heart."""
    heart = [[_path("M338 214 C330 206 322 199 322 191 C322 185 327 181 332 182 C335 182.5 337 185 338 188 Z", GOLD, width=.9),
              _path("M338 214 C346 206 354 199 354 191 C354 185 349 181 344 182 C341 182.5 339 185 338 188 Z", GOLD_SHADE, width=.9)]]
    return _grandfather() + _girl() + heart


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
            'aria-label="Ilustración: un abuelo y su nieta tomados de la mano">' + back
            + f'<g transform="translate(324 440) scale({SCALE}) translate(-324 -440)">{figures}</g></svg>')
