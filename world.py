"""Mondo: il cielo, i piani lontani, la strada e gli oggetti di scena.

Tutto disegnato a runtime, nessun asset. Coordinate mondo: x in avanti,
y=0 e' il terreno (GROUND in paint.py). La telecamera segue il cavaliere e la
traslazione e' applicata qui dentro, in ogni draw_*.

Piani dalla fondo allo schermo: cielo 0.0 -> montagne 0.06 -> colline 0.14
-> bosco 0.28 -> bosco 0.46 -> terreno 1.0. Nessun filtro: la resa viene da
geometria e palette, non da overlay globali.

Il vocabolario di colore e primitive sta in paint.py, il castello in castle.py:
qui resta solo la scena aperta.
"""

import math
import random

import pygame

import paint
from paint import (W, H, GROUND, SKY_STOPS, MOUNT, MOUNT_LIT, HILL, HILL_LIT,
                   WOOD_FAR, WOOD_NEAR, GRASS, GRASS_D, GRASS_L,
                   ROAD, ROAD_D, ROAD_L, STONE, STONE_D, STONE_L,
                   WOOD, WOOD_D, LEAF, LEAF_D, LEAF_L,
                   WARM, CRIMSON, CRIMSON_D,
                   _r, _p, _l, _c, _e, _tone, _mix,
                   _glow, _add_glow, _ground_shadow)
from castle import (CASTLE_X0, CASTLE_X1, GATE_X0, GATE_X1,
                    draw_castle, draw_portcullis)

# game.py e i tool parlano solo con `world`: la tela e la palette sono li'.
palette = paint.palette

# --- strada ---------------------------------------------------------------
ROAD_Y = GROUND - 6.0
ROAD_CX = (GATE_X0 + GATE_X1) * 0.5     # la strada parte dal portone
PILLARS = [980.0, 1560.0, 2180.0, 2840.0, 3460.0, 4120.0, 4760.0]
FOREST_X = 4950.0
GOAL_X = 5400.0
ROAD_X0, ROAD_X1 = GATE_X0 - 220.0, GOAL_X + 360.0
MEADOW = GROUND - 62.0       # il prato comincia sotto il bosco vicino
ROAD_TOP = GROUND - 26.0     # il bordo lontano della carreggiata
ROAD_BOT = H + 16.0          # il bordo vicino esce dal fondo dello schermo
PROP_Y = GROUND - 32.0       # gli oggetti stanno sul ciglio, dietro la strada

# --- cielo: sfumatura a 5 stop + stelle + luna + banchi di nube ----------
def _sky():
    s, rng = pygame.Surface((W, H)), random.Random(7)
    for y in range(H):
        t = y / (H - 1)
        for (t0, c0), (t1, c1) in zip(SKY_STOPS, SKY_STOPS[1:]):
            if t <= t1:
                k = 0.0 if t1 <= t0 else (t - t0) / (t1 - t0)
                _l(s, _mix(c0, c1, k), (0, y), (W, y))
                break
        else:
            _l(s, SKY_STOPS[-1][1], (0, y), (W, y))
    for _ in range(170):                    # stelle: piu' fitte in alto
        x, y = rng.uniform(0, W), rng.uniform(0, 310)
        r = rng.choice((0, 0, 1, 1, 1))
        if r:
            _c(s, _tone((236, 238, 255), 0.5 + 0.5 * (1 - y / 310)), x, y, r)
    mx, my = 762, 84                       # luna bassa a destra
    _c(s, (250, 240, 216), mx, my, 18)
    for cx, cy, cr in ((-6, -5, 4), (5, 3, 3), (-3, 6, 2)):   # crateri tenui
        _c(s, (238, 226, 200), mx + cx, my + cy, cr)
    _c(s, (252, 244, 226), mx - 5, my - 6, 6)              # lato illuminato
    s.blit(_glow(150, 146, (238, 216, 178), 3.0, 90), (mx - 75, my - 73))
    for _ in range(18):                    # banchi di nube schiacciati
        cy = rng.uniform(200, 402)
        t = (cy - 200) / 202.0
        cw, ch = rng.uniform(170, 430), 4 + 11 * t
        cx = rng.uniform(-70, W)
        col = _mix((106, 82, 116), (240, 160, 108), t)
        _e(s, _tone(col, 0.94), cx - cw / 2, cy, cw, ch)
        _e(s, _tone(col, 1.08), cx - cw * 0.3, cy - ch * 0.4,
           cw * 0.6, ch * 0.7)
    _add_glow(s, 460, 300, (250, 196, 142), 700, 400, 2.6, 80)
    return s

SKY = _sky()

def draw_sky(surf):
    surf.blit(SKY, (0, 0))

# --- piani di parallax: silhouette pre-calcolate e ripetute --------------
def _layer(tw, base, amp, seed, harm, col, lit, par, trees=0, th=(18, 34)):
    """Cresta periodica (sinusoidi a frequenza intera = nessuna cucitura) con
    bosco piantato sopra: tutto pre-bollito in una sola tile."""
    rng = random.Random(seed)
    waves = [(rng.uniform(0, math.tau), wgt, k) for k, wgt in harm]

    def ridge(x):
        return base - amp * sum(wgt * math.sin(math.tau * x / tw * k + p)
                                for p, wgt, k in waves)
    pts, x = [], -20.0
    while x <= tw + 20.0:
        pts.append((x, ridge(x)))
        x += 20
    s = pygame.Surface((tw, H), pygame.SRCALPHA)
    _p(s, col, pts + [(tw + 20, H + 10), (-20, H + 10)])
    if lit:                                # luce al crepuscolo sul crinale
        pygame.draw.lines(s, lit, False, [(x, y - 1) for x, y in pts], 3)
        pygame.draw.lines(s, _tone(col, 0.84), False,
                          [(x, y + 8) for x, y in pts], 7)
    for i in range(trees):
        bx = 30 + (tw - 60) * (i + rng.random() * 0.8) / trees
        by, h = ridge(bx), rng.uniform(*th)
        w = h * rng.uniform(0.3, 0.48)
        tree = [(bx - w, by + 5), (bx + w, by + 5), (bx, by - h)]
        _p(s, col, tree)
        tree[0] = (bx - w * 0.15, by + 5)      # lato illuminato della chioma
        _p(s, _tone(col, 1.2), tree)
    return s, par

# Prospettiva aerea: piu' un piano e' lontano, piu' si confonde col cielo
# all'orizzonte. Senza questa foschia le colline sembrano ritagli piatti.
HAZE = (118, 96, 124)
LAYERS = (
    _layer(1400, 318, 66, 11, [(1, .62), (2, .26), (5, .12)],
           _mix(MOUNT, HAZE, 0.34), _mix(MOUNT_LIT, HAZE, 0.22), 0.06),
    _layer(1200, 392, 42, 23, [(1, .6), (3, .3), (7, .1)],
           _mix(HILL, HAZE, 0.22), _mix(HILL_LIT, HAZE, 0.14), 0.14),
    _layer(1100, 430, 24, 31, [(1, .55), (2, .3), (6, .15)],
           _mix(WOOD_FAR, HAZE, 0.12), None,
           0.28, trees=70, th=(15, 28)),
    _layer(980, 456, 20, 47, [(1, .5), (3, .32), (8, .18)], WOOD_NEAR, None,
           0.46, trees=52, th=(24, 50)),
)

def draw_background(surf, cam_x):
    for tile, par in LAYERS:
        tw = tile.get_width()
        ox = int(cam_x * par) % tw
        surf.blit(tile, (-ox, 0))
        surf.blit(tile, (tw - ox, 0))

# --- terreno e strada -----------------------------------------------------
def _road_edge(wx):
    """Scarto del bordo stradale: bordi irregolari, funzione del mondo, quindi
    scorrono davvero col cammino."""
    return math.sin(wx * 0.0071) * 5.0 + math.sin(wx * 0.023) * 2.6 + \
        math.sin(wx * 0.061 + 2.1) * 1.4

def _road_track(surf, cam_x, k, col, dy=0.0):
    """Banda di terra battuta: `k` stringe il bordo superiore, cosi' le piste
    piu' chiare restano dentro la carreggiata."""
    top, bot, x = [], [], -80.0
    while x <= W + 80.0:
        j = _road_edge(cam_x + x)
        top.append((int(x + j * k), int(ROAD_TOP + dy + j * 0.8)))
        bot.append((int(x + j * k * 0.25), int(ROAD_BOT)))
        x += 26
    _p(surf, col, top + bot[::-1])

def _pebbles():
    """Ciottoli pre-generati sulla strada: scorrono col mondo."""
    rng, out, x = random.Random(5), [], ROAD_X0
    while x < ROAD_X1:
        x += rng.uniform(20, 54)
        out.append((x, ROAD_TOP + 4 + rng.random() * (H + 8 - ROAD_TOP),
                    rng.random(), rng.random(), rng.random()))
    return out

PEBBLES = _pebbles()
MEADOW_ROWS = [(MEADOW + i * 2.0, _mix(GRASS_D, GRASS_L, (i / 8.0) ** 1.3))
               for i in range(9)]
# il prato non e' un riempimento unico: scende in ombra verso il bordo inferiore
GRASS_ROWS = [(MEADOW + 14 + i * 7.0, _mix(GRASS, GRASS_D, (i / 9.0) ** 1.3))
              for i in range(int((H - MEADOW - 14) / 7.0) + 1)]

STONE_DARK_GREY = (92, 96, 104)

def _tufts():
    """Ciuffi d'erba pre-generati: come i ciottoli, scorrono col mondo."""
    rng, out, x = random.Random(13), [], 0.0
    while x < ROAD_X1:
        x += rng.uniform(9, 26)
        out.append((x, rng.uniform(0, 1), rng.uniform(0.7, 1.3)))
    return out

TUFTS = _tufts()

# fascia che i ciuffi possono occupare sopra la strada, per non invaderla
TUFT_BAND = 15.0


def _draw_tufts(surf, cam_x):
    """Tre fili a ventaglio per ciuffo, due toni: il prato ha una grana."""
    for wx, t, k in TUFTS:
        sx = wx - cam_x
        if not -20 < sx < W + 20:
            continue
        base = MEADOW + 15 + t * TUFT_BAND
        h = (3.0 + t * 4.0) * k
        col = GRASS_L if t > 0.6 else GRASS_D
        for lean in (-0.45, 0.0, 0.45):
            _l(surf, col, (sx, base), (sx + lean * h, base - h), 1)


def _grit():
    """Grana della carreggiata: pezzetti di terra chiara e scura, come i
    ciottoli scorrono col mondo e crescono verso il bordo vicino."""
    rng, out, x = random.Random(41), [], ROAD_X0
    while x < ROAD_X1:
        x += rng.uniform(6, 24)
        out.append((x, rng.random(), rng.uniform(0.5, 1.7), rng.random()))
    return out


GRIT = _grit()


def _draw_grit(surf, cam_x):
    for wx, t, k, light in GRIT:
        sx = wx - cam_x
        if not -8 < sx < W + 8:
            continue
        wy = ROAD_TOP + 7 + t * (H + 6 - ROAD_TOP)
        col = _tone(ROAD_L, 1.14) if light > 0.5 else _tone(ROAD_D, 0.84)
        _l(surf, col, (sx, wy), (sx + 3.0 * k, wy - 0.6 * k), 1)


def _fringe():
    """Ciuffi sul ciglio della strada. Il bordo della carreggiata e' una
    poligono e si legge come un taglio netto: questi lo dissolvono nell'erba."""
    rng, out, x = random.Random(61), [], ROAD_X0
    while x < ROAD_X1:
        x += rng.uniform(7, 20)
        out.append((x, rng.uniform(0.5, 1.5), rng.random()))
    return out


FRINGE = _fringe()


def _draw_fringe(surf, cam_x):
    for wx, k, t in FRINGE:
        sx = wx - cam_x
        if not -12 < sx < W + 12:
            continue
        y = ROAD_TOP + _road_edge(wx) * 0.8 - 1.0
        h = (4.0 + t * 5.0) * k
        col = GRASS_L if t > 0.55 else GRASS_D
        for lean in (-0.55, 0.05, 0.6):
            _l(surf, col, (sx, y), (sx + lean * h, y - h), 1)

_STONES = []
_rng_s, _x_s = random.Random(29), 0.0
while _x_s < ROAD_X1:
    _x_s += _rng_s.uniform(60, 150)
    _STONES.append((_x_s, _rng_s.uniform(0.6, 1.4), _rng_s.uniform(0, 1)))


def _draw_stones(surf, cam_x):
    """Sassi piatti nella fascia del prato: stilizzati, come i ciottoli della
    strada. Chiaro in cima, scuro alla base, scorrono col mondo."""
    for wx, k, t in _STONES:
        sx = wx - cam_x
        if not -30 < sx < W + 30:
            continue
        y = MEADOW + 19 + t * 3.0
        rw, rh = 5.0 * k, 2.6 * k
        _e(surf, _tone(STONE_DARK_GREY, 0.8), sx - rw, y - rh * 0.4, rw * 2, rh * 1.6)
        _e(surf, _tone(STONE_DARK_GREY, 1.25), sx - rw * 0.7, y - rh * 1.1,
           rw * 1.2, rh * 1.1)


_VIGNETTE = None

def _vignette():
    """Ombra di crepuscolo in basso: stacca i personaggi dal terreno."""
    s = pygame.Surface((W, 120), pygame.SRCALPHA)
    for y in range(120):
        a = int(70 * (y / 119.0) ** 2)
        pygame.draw.line(s, (12, 10, 20, a), (0, y), (W, y))
    return s

def draw_ground(surf, cam_x):
    """Prato, strada in prospettiva, ciottoli e la luce dell'uscita."""
    _r(surf, _mix(GRASS_D, HILL, 0.45), 0, MEADOW - 8, W, 12)
    for y, col in MEADOW_ROWS:                     # il verde scende al terreno
        _r(surf, col, 0, y, W, 3)
    for y, col in GRASS_ROWS:                     # e il prato ha ombra in fondo
        _r(surf, col, 0, y, W, 8)
    _draw_tufts(surf, cam_x)
    _draw_stones(surf, cam_x)
    _road_track(surf, cam_x, 1.4, _mix(GRASS_D, ROAD_D, 0.45), -4.0)  # orlo
    _road_track(surf, cam_x, 1.0, ROAD_D)
    _road_track(surf, cam_x, 1.0, ROAD, dy=1.0)
    _road_track(surf, cam_x, 0.45, _mix(ROAD_L, ROAD, 0.4), dy=3.0)  # centro, meno chiaro
    cx = W * 0.5 + math.sin(cam_x * 0.0011) * 70.0
    for side in (-1, 1):          # due solchi: la carreggiata in prospettiva
        prev, x = None, -60.0
        while x <= W + 60.0:
            t = min(1.0, x / (W * 1.15))
            j = _road_edge(cam_x + x) * 1.2
            p = (int(cx + side * (70.0 + 300.0 * t) + j),
                 int(ROAD_TOP + 3 + (H + 10 - ROAD_TOP) * t))
            if prev:
                _l(surf, _tone(ROAD_D, 0.74), prev, p, 6)  # solchi piu' marcati
            prev, x = p, x + 34
    _draw_grit(surf, cam_x)
    _draw_fringe(surf, cam_x)
    for wx, wy, t, off, lit in PEBBLES:     # ciottoli: grandi in primo piano
        sx = wx - cam_x                   # e piccoli in lontananza
        if -20 < sx < W + 20:
            r = (1.3 + t * 2.6) * (0.75 + lit * 0.45)
            col = _tone(ROAD_L, 1.16) if lit > 0.5 else _tone(ROAD, 0.78)
            _e(surf, col, sx + off * 6.0 - r, wy - r * 0.6, r * 2, r * 1.2)
    sx = GOAL_X - cam_x
    if -240 < sx < W + 240:
        _add_glow(surf, 420, 110, WARM, sx, ROAD_TOP + 34, 1.8, 110)
    global _VIGNETTE
    if _VIGNETTE is None:
        _VIGNETTE = _vignette()
    surf.blit(_VIGNETTE, (0, H - 120))

# --- oggetti di scena: generati UNA volta a livello di modulo (seed fisso) -
def _make_props():
    rng = random.Random(20240)
    items = [("pillar", x, 1.0, rng.random(), 0) for x in PILLARS]
    items += [("cairn", FOREST_X - 40, 0.95, rng.random(), 0),
              ("cairn", GOAL_X + 150, 0.8, rng.random(), 0)]
    # lungo la strada, lontano dal castello
    x = -460.0
    while x < FOREST_X - 60:
        x += rng.uniform(48, 116)
        if CASTLE_X0 - 100 < x < CASTLE_X1 + 100:
            continue
        roll = rng.random()
        kind = ("pine" if roll < 0.20 else "oak" if roll < 0.36 else
                "bush" if roll < 0.58 else "rock" if roll < 0.74 else
                "snag" if roll < 0.86 else "tuft")   # varieta' di forme e toni
        items.append((kind, x, rng.uniform(0.8, 1.35), rng.random(), 0))
    x = FOREST_X - 40.0
    for _ in range(230):                    # bosco fitto oltre FOREST_X
        x += rng.uniform(22, 78)
        # il bosco si chiude: alberi piu' alti e piu' radi ai bordi
        near = abs(x - GOAL_X) < 320.0
        items.append((rng.choice(("pine", "pine", "oak", "snag", "snag")), x,
                      rng.uniform(1.3, 2.2) if near else rng.uniform(0.9, 1.6),
                      rng.random(), 1))
        if rng.random() < 0.45:
            items.append(("bush", x + rng.uniform(-26, 26),
                          rng.uniform(0.7, 1.1), rng.random(), 1))
    items.sort(key=lambda it: it[1])
    return items

PROPS = _make_props()
SHADOW_W = {"oak": 52, "pine": 36, "snag": 20, "bush": 32, "rock": 32,
            "tuft": 20, "pillar": 48, "cairn": 42}

def _oak(surf, sx, s, tone):
    """Chioma a lobi sovrapposti con lato illuminato: niente cerchio unico."""
    h, lean = 84 * s, math.sin(sx * 0.05) * 3.0
    base = (LEAF, _mix(LEAF, LEAF_D, 0.5),
            _mix(LEAF, GRASS_D, 0.45))[min(2, int(tone * 3))]
    _p(surf, WOOD_D, [(sx - 6 * s, PROP_Y), (sx + 6 * s, PROP_Y),
                      (sx + 3 * s + lean, PROP_Y - h * 0.56),
                      (sx - 3 * s + lean, PROP_Y - h * 0.56)])
    _l(surf, WOOD, (sx, PROP_Y - h * 0.44),
       (sx - 15 * s + lean, PROP_Y - h * 0.68), int(3 * s))
    _l(surf, _tone(WOOD, 1.15), (sx + 1, PROP_Y - h * 0.3),
       (sx + 13 * s + lean, PROP_Y - h * 0.58), int(2 * s))
    lobes = ((0, -0.88, 30), (-20 * s, -0.7, 22), (18 * s, -0.74, 24),
             (-9 * s, -0.52, 19), (11 * s, -0.54, 17))
    for i, (dx, dy, r) in enumerate(lobes):
        _c(surf, base if i % 2 else _tone(base, 1.14), sx + dx,
           PROP_Y + dy * s, r * s)
    _c(surf, LEAF_L, sx - 10 * s, PROP_Y - h * 0.94, 15 * s)
    _c(surf, _tone(base, 0.76), sx + 13 * s, PROP_Y - h * 0.5, 13 * s)

def _pine(surf, sx, s, tone):
    """Abete a rami sovrapposti, chioma fredda e profonda."""
    h = 104 * s
    _r(surf, WOOD_D, sx - 4 * s, PROP_Y - h * 0.3, 8 * s, h * 0.3)
    base = LEAF_D if tone > 0.5 else _mix(LEAF_D, WOOD_FAR, 0.45)
    for k in range(4):
        f = k / 3.0
        y, rw = -h * (0.26 + f * 0.62), (32 - 22 * f) * s
        _p(surf, base if k % 2 else _tone(base, 1.16),
           [(sx - rw, PROP_Y + y), (sx + rw, PROP_Y + y),
            (sx, PROP_Y + y - 36 * s)])

def _snag(surf, sx, s, tone):
    """Albero morto: tronco e rami nudi, chiari contro il cielo."""
    h, col = 72 * s, _mix(WOOD_D, STONE_D, 0.4)
    _p(surf, col, [(sx - 5 * s, PROP_Y), (sx + 5 * s, PROP_Y),
                   (sx + 2 * s, PROP_Y - h), (sx - 3 * s, PROP_Y - h)])
    _p(surf, _tone(col, 1.2), [(sx - 5 * s, PROP_Y), (sx - 2 * s, PROP_Y),
                               (sx - 3 * s, PROP_Y - h)])
    for dx, dy, L in ((-1, -0.78, 0.5), (1, -0.66, 0.44), (-1, -0.5, 0.32)):
        x2, y2 = sx + dx * 24 * s, -h * (dy + L * 0.7)
        _l(surf, col, (sx, PROP_Y - h * dy), (x2, PROP_Y + y2), int(3 * s))
        _l(surf, _tone(col, 1.3), (x2, PROP_Y + y2),
           (x2 + dx * 10 * s, PROP_Y + y2 - 12 * s), int(2 * s))

def _bush(surf, sx, s, tone):
    base = _mix(LEAF, LEAF_D, 0.3 + tone * 0.55)
    for dx, dy, r in ((-11, -9, 13), (9, -7, 11), (0, -16, 12), (3, -4, 9)):
        _c(surf, base if dx else _tone(base, 1.16), sx + dx * s,
           PROP_Y + dy * s, r * s)
    _c(surf, _tone(base, 1.32), sx - 8 * s, PROP_Y - 19 * s, 6 * s)

def _rock(surf, sx, s, tone):
    """Masso con faccia illuminata e ombra portata: mai un rettangolo."""
    w = 14 * s

    def shape(pts):
        return [(sx + px * w, PROP_Y + py * w * 1.5) for px, py in pts]
    col = _mix(STONE_D, STONE, 0.35 + tone * 0.55)
    _p(surf, _tone(col, 0.7), shape(((-1.05, 0), (-0.85, -0.62), (-0.3, -0.95),
                                     (0.45, -0.88), (1.0, -0.45), (1.1, 0))))
    _p(surf, col, shape(((-0.85, -0.62), (-0.3, -0.95), (0.45, -0.88),
                         (0.2, -0.4), (-0.7, -0.3))))
    _p(surf, _tone(col, 1.24), shape(((-0.76, -0.66), (-0.3, -0.92),
                                       (0.08, -0.6))))
    _l(surf, _tone(col, 0.58), shape(((-0.2, -0.88),))[0],
       shape(((0.36, -0.4),))[0], 2)

def _tuft(surf, sx, s, tone):
    for k in range(7):
        dx = (k - 3) * 3.4 * s
        col = GRASS_L if (k + tone * 5) % 2 else GRASS_D
        _l(surf, col, (sx + dx, PROP_Y),
           (sx + dx * 2.2, PROP_Y - (13 + (k % 3) * 6) * s), 2)

def _cairn(surf, sx, s, tone):
    y = PROP_Y
    for k, r in enumerate((20, 17, 13, 9)):
        col = _mix(STONE_D, STONE, 0.3 + 0.2 * ((k + tone * 4) % 3))
        _e(surf, col, sx - r * s, y - r * 0.85 * s, r * 2 * s, r * 1.15 * s)
        _e(surf, _tone(col, 1.22), sx - r * s, y - r * 0.85 * s, r * 2 * s,
           r * 0.4 * s)
        y -= r * 0.95 * s

def _pillar(surf, sx, s, tone):
    """Cippo miliare: base, fusto, capitello, croce spezzata e drappo."""
    h, w = 240 * s, 15 * s
    _p(surf, _tone(STONE_D, 0.88),
       [(sx - w - 7 * s, PROP_Y + 4), (sx + w + 7 * s, PROP_Y + 4),
        (sx + w, PROP_Y - 18 * s), (sx - w, PROP_Y - 18 * s)])
    _r(surf, STONE, sx - w, PROP_Y - h, w * 2, h - 18 * s)
    _r(surf, STONE_L, sx - w, PROP_Y - h, w * 0.85, h - 18 * s)
    _r(surf, _tone(STONE, 0.72), sx + w * 0.45, PROP_Y - h,
       w * 0.55, h - 18 * s)
    for k in range(1, 6):
        y = PROP_Y - h * k / 5.0
        _l(surf, STONE_D, (sx - w, y), (sx + w, y), 3)
    cap = (sx - w - 6 * s, PROP_Y - h - 15 * s, w * 2 + 12 * s)
    _r(surf, STONE_L, cap[0], cap[1], cap[2], 17 * s)   # capitello
    _r(surf, _tone(STONE_L, 1.12), cap[0], cap[1], cap[2], 5)
    iron = (86, 82, 88)
    _r(surf, iron, sx - 3 * s, PROP_Y - h - 48 * s, 6 * s, 36 * s)
    _r(surf, iron, sx - 15 * s, PROP_Y - h - 42 * s, 26 * s, 6 * s)
    _l(surf, STONE_D, (sx - w, PROP_Y - h * 0.7),
       (sx + w, PROP_Y - h * 0.64), 2)
    _r(surf, (CRIMSON, CRIMSON_D)[tone > 0.5], sx + w * 0.15,
       PROP_Y - h - 12 * s, 10 * s, 58 * s)

_SHAPES = {"oak": _oak, "pine": _pine, "snag": _snag, "bush": _bush,
           "rock": _rock, "tuft": _tuft, "pillar": _pillar, "cairn": _cairn}

def draw_props(surf, cam_x):
    for kind, x, s, tone, dark in PROPS:
        sx = x - cam_x
        if sx < -120 or sx > W + 120:
            continue
        _ground_shadow(surf, sx + 10 * s, PROP_Y + 2, SHADOW_W[kind] * s,
                       SHADOW_W[kind] * 0.3 * s)
        paint.set_dark(0.46 if dark else 1.0)   # nel bosco chiuso e' piu' scuro
        _SHAPES[kind](surf, sx, s, tone)
    paint.set_dark(1.0)

# --- uscita: muro di foresta e svolta di luce sulla strada -----------------
_BEAMS = {}


def _beam(k):
    """Fascio di luce premoltiplicato per un livello di brillantezza k."""
    key = round(k, 4)
    if key not in _BEAMS:
        beam = pygame.Surface((360, 320), pygame.SRCALPHA)
        _p(beam, (int(WARM[0] * k), int(WARM[1] * k), int(WARM[2] * k), 255),
           [(168, 0), (198, 0), (330, 320), (34, 320)])
        _BEAMS[key] = beam
    return _BEAMS[key]


def draw_goal(surf, cam_x, t):
    """La strada entra nel bosco: muro di foresta e svolta di luce."""
    sx = GOAL_X - cam_x
    if sx < -560 or sx > W + 560:
        return
    for col, hh, rr, off, base in (((22, 34, 30), 236, 52, 0, PROP_Y - 8),
                                   ((30, 44, 38), 176, 42, 27, PROP_Y + 2)):
        x = int(sx - 480 + off)
        while x < sx + 520:              # due file di chiome scure e fitte
            h, y = hh + math.sin(x * 0.013) * 15, GROUND + base
            _p(surf, col, [(x - rr, y + 4), (x + rr, y + 4), (x, y - h)])
            _p(surf, _tone(col, 1.24), [(x - rr, y + 4),
                                        (x - rr * 0.15, y + 4), (x, y - h)])
            x += int(rr * 1.3)
        _r(surf, _tone(col, 0.7), sx - 490, GROUND + base - 22, 1020, 26)
    glow = 0.5 + 0.5 * math.sin(t * 1.6)     # raggio di luce pulsante
    # il fascio e' additivo: il colore va premoltiplicato per l'alpha, se no
    # BLEND_RGBA_ADD somma il colore pieno e il raggio diventa una lancia
    k = round((26 + 16 * glow) / 2.0) * 2.0 / 255.0   # 2 livelli: cache hit
    beam = _beam(k)
    surf.blit(beam, (int(sx - 180), int(GROUND - 320)),
              special_flags=pygame.BLEND_RGBA_ADD)
    _add_glow(surf, 320, 300, (255, 216, 152), sx, PROP_Y - 150, 2.0,
              int(70 + 30 * glow))
    for bx in (GOAL_X - 100, GOAL_X + 100):  # cippi ai lati dell'uscita
        sxx = int(bx - cam_x)
        _ground_shadow(surf, sxx + 6, PROP_Y + 1, 34, 10)
        _r(surf, STONE, sxx - 11, PROP_Y - 76, 22, 76)
        _r(surf, STONE_L, sxx - 11, PROP_Y - 76, 22, 6)
        _r(surf, _tone(STONE, 0.7), sxx + 2, PROP_Y - 76, 9, 76)