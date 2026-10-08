"""Mondo: il castello di Castel Rosso e la strada che porta alla foresta.

Tutto disegnato a runtime, nessun asset. Coordinate mondo: x in avanti,
y=0 e' il terreno (GROUND = 520). La telecamera segue il cavaliere e la
 traslazione e' applicata qui dentro, in ogni draw_*.

Piani dalla fondo allo schermo: cielo 0.0 -> montagne 0.06 -> colline 0.14
-> bosco 0.28 -> bosco 0.46 -> terreno 1.0. Nessun filtro: la resa viene da
geometria e palette, non da overlay globali.
"""

import math
import random

import pygame

GROUND = 520.0
W, H = 960, 540

# --- castello -------------------------------------------------------------
CASTLE_X0 = -520.0      # il castello sta alle spalle, fuori schermo
CASTLE_X1 = 260.0
GATE_X0, GATE_X1 = -140.0, 120.0
GATE_TOP = GROUND - 210.0
GATE_SPRING = GROUND - 132.0     # imposta dell'arco del portone
COURT_X1 = CASTLE_X1
WALL_TOP = GROUND - 300.0

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

# --- palette: dusk tardivo medievale --------------------------------------
SKY_TOP, SKY_MID, SKY_HORIZON = (26, 30, 64), (142, 88, 112), (248, 188, 124)
SKY_STOPS = [(0.00, SKY_TOP), (0.30, (74, 62, 108)), (0.55, SKY_MID),
             (0.76, (216, 126, 88)), (1.00, SKY_HORIZON)]
MOUNT, MOUNT_LIT = (56, 60, 94), (104, 106, 142)
HILL, HILL_LIT = (72, 72, 96), (146, 108, 100)
WOOD_FAR, WOOD_NEAR = (50, 60, 58), (30, 40, 38)
GRASS, GRASS_D, GRASS_L = (76, 102, 62), (52, 74, 46), (102, 126, 72)
ROAD, ROAD_D, ROAD_L = (128, 112, 84), (96, 82, 60), (158, 140, 106)
STONE, STONE_D, STONE_L = (128, 124, 118), (88, 84, 82), (164, 158, 148)
WOOD, WOOD_D = (92, 70, 50), (64, 48, 34)
LEAF, LEAF_D, LEAF_L = (52, 82, 50), (34, 58, 36), (80, 114, 62)
SLATE, SLATE_L = (56, 52, 62), (92, 88, 102)
SHADOW, WARM, GOLD = (16, 14, 22), (252, 196, 112), (222, 178, 92)
CRIMSON, CRIMSON_D = (156, 42, 46), (108, 28, 34)

_PALETTE = {
    "sky_top": SKY_TOP, "sky_mid": SKY_MID, "sky_horizon": SKY_HORIZON,
    "mountain": MOUNT, "mountain_lit": MOUNT_LIT, "hill": HILL,
    "hill_lit": HILL_LIT, "forest_far": WOOD_FAR, "forest_near": WOOD_NEAR,
    "grass": GRASS, "grass_dark": GRASS_D, "grass_light": GRASS_L,
    "road": ROAD, "road_dark": ROAD_D, "road_light": ROAD_L,
    "stone": STONE, "stone_light": STONE_L, "stone_dark": STONE_D,
    "wood": WOOD, "wood_dark": WOOD_D, "leaf": LEAF, "shadow": SHADOW,
    "warm": WARM, "gold": GOLD,
}

_DK = 1.0      # scurimento corrente: sotto 1 dentro il bosco finale

def palette():
    """Colori chiave dello sfondo: game.py li usa per overlay nemici e HUD."""
    return dict(_PALETTE)

def _tone(c, f):
    """Scala un colore. `_DK` agisce qui, cosi' ogni sfumatura derivata
    eredita lo scurimento senza ripetere il fattore in ogni funzione."""
    f *= _DK
    return (max(0, min(255, int(c[0] * f))), max(0, min(255, int(c[1] * f))),
            max(0, min(255, int(c[2] * f))))

def _mix(a, b, t):
    f = _DK
    return tuple(max(0, min(255, int((a[i] + (b[i] - a[i]) * t) * f)))
                 for i in range(3))

# Scorciatoie: pygame.draw con coordinate float. Il colore passa da `_dk`, che
# e' `_tone` a fattore 1: cosi' `_DK` scurisce TUTTO quello che disegna un
# oggetto e nel bosco finale non serve tingere ogni sfumatura a mano.
def _dk(c):
    return c if _DK >= 0.999 else _tone(c, 1.0)

def _r(s, c, x, y, w, h):
    pygame.draw.rect(s, _dk(c), (int(x), int(y), int(w), int(h)))

def _p(s, c, pts):
    pygame.draw.polygon(s, _dk(c), pts)

def _l(s, c, a, b, w=1):
    pygame.draw.line(s, _dk(c), a, b, w)

def _c(s, c, x, y, r):
    pygame.draw.circle(s, _dk(c), (int(x), int(y)), max(1, int(r)))

def _e(s, c, x, y, w, h):
    pygame.draw.ellipse(s, _dk(c), (int(x), int(y), int(w), int(h)))

_GLOWS = {}

def _glow(w, h, col, power=2.0, alpha=180, additive=False):
    """Alone radiale morbido, costruito una volta sola e messo in cache.

    `pygame.draw` non sfuma: l'alone e' calcolato per pixel su una griglia 1:4
    e interpolato con smoothscale. In additivo il colore va premoltiplicato per
    l'alpha, altrimenti si sommano pieni e l'alone satura in bianco.
    """
    key = (w, h, col, power, alpha, additive)
    if key in _GLOWS:
        return _GLOWS[key]
    lw, lh = max(6, w // 4), max(6, h // 4)
    lo = pygame.Surface((lw, lh), pygame.SRCALPHA)
    cx, cy = (lw - 1) * 0.5, (lh - 1) * 0.5
    for y in range(lh):
        ny = (y - cy) / cy
        for x in range(lw):
            nx = (x - cx) / cx
            d = math.sqrt(nx * nx + ny * ny)
            if d >= 1.0:
                continue
            a = alpha * (1.0 - d) ** power
            lo.set_at((x, y), (int(col[0] * a / 255), int(col[1] * a / 255),
                               int(col[2] * a / 255), 255) if additive
                      else (*col, int(a)))
    _GLOWS[key] = s = pygame.transform.smoothscale(lo, (w, h))
    return s

def _add_glow(surf, w, h, col, x, y, power=2.0, alpha=150):
    """Alone additivo (sorgente di luce): il colore si somma allo sfondo."""
    surf.blit(_glow(w, h, col, power, alpha, True),
              (int(x - w / 2), int(y - h / 2)),
              special_flags=pygame.BLEND_RGBA_ADD)

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

# --- ombre proiettate: la luce arriva dall'alto a sinistra ----------------
_SHADOWS = {}

def _ground_shadow(surf, x, y, w, h):
    """Ellisse scura schiacciata alla base: e' cio' che fa leggere gli oggetti
    appoggiati al terreno invece di galleggiare sopra."""
    w, h = max(3, int(w)), max(2, int(h))
    if (w, h) not in _SHADOWS:
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        _e(s, (*SHADOW, 120), 0, 0, w, h)
        _e(s, (*SHADOW, 60), 1, 1, w - 2, h - 2)
        _SHADOWS[(w, h)] = s
    surf.blit(_SHADOWS[(w, h)], (int(x - w / 2), int(y - h / 2)))

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

def _tufts():
    """Ciuffi d'erba pre-generati: come i ciottoli, scorrono col mondo."""
    rng, out, x = random.Random(13), [], 0.0
    while x < ROAD_X1:
        x += rng.uniform(9, 26)
        out.append((x, rng.uniform(0, 1), rng.uniform(0.7, 1.3)))
    return out

TUFTS = _tufts()

def _draw_tufts(surf, cam_x):
    """Tre fili a ventaglio per ciuffo, due toni: il prato ha una grana."""
    for wx, t, k in TUFTS:
        sx = wx - cam_x
        if not -20 < sx < W + 20:
            continue
        base = MEADOW + 15 + t * 4.0
        h = (3.0 + t * 4.0) * k
        col = GRASS_L if t > 0.6 else GRASS_D
        for lean in (-0.45, 0.0, 0.45):
            _l(surf, col, (sx, base), (sx + lean * h, base - h), 1)

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
    _r(surf, GRASS, 0, MEADOW + 14, W, H)
    _draw_tufts(surf, cam_x)
    _road_track(surf, cam_x, 1.4, _mix(GRASS_D, ROAD_D, 0.45), -4.0)  # orlo
    _road_track(surf, cam_x, 1.0, ROAD_D)
    _road_track(surf, cam_x, 1.0, ROAD, dy=1.0)
    _road_track(surf, cam_x, 0.45, ROAD_L, dy=3.0)  # centro piu' chiaro
    cx = W * 0.5 + math.sin(cam_x * 0.0011) * 70.0
    for side in (-1, 1):          # due solchi: la carreggiata in prospettiva
        prev, x = None, -60.0
        while x <= W + 60.0:
            t = min(1.0, x / (W * 1.15))
            j = _road_edge(cam_x + x) * 1.2
            p = (int(cx + side * (70.0 + 300.0 * t) + j),
                 int(ROAD_TOP + 3 + (H + 10 - ROAD_TOP) * t))
            if prev:
                _l(surf, _tone(ROAD_D, 0.84), prev, p, 5)
            prev, x = p, x + 34
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

# --- archi, merlature e muratura: il vocabolario del castello --------------
def _arch(cx, cy, r, seg=16, top=True):
    a0, a1 = (math.pi, math.tau) if top else (0.0, math.pi)
    return [(cx + math.cos(a0 + (a1 - a0) * i / seg) * r,
             cy + math.sin(a0 + (a1 - a0) * i / seg) * r)
            for i in range(seg + 1)]

def _lit_window(surf, cx, spring, w, h, lit=True, glow=True):
    """Finestra ad arco: telaio in pietra, crociera, luce dall'interno."""
    r = w / 2.0
    for k, col in ((r + 5, STONE_D), (r, (238, 190, 108) if lit
                                      else (36, 30, 28))):
        base = (cx - k - (5 if k > r else 0), spring + h)
        _p(surf, col, [(base[0], base[1]), (cx + k, base[1])]
           + _arch(cx, spring, k)[::-1])
    if lit:
        _p(surf, (252, 228, 170),
           [(cx - r + 2, spring + h), (cx - r * 0.1, spring + h)]
           + _arch(cx, spring, r * 0.62)[::-1])
    _l(surf, STONE_D, (cx - r, spring + h * 0.5),
       (cx + r, spring + h * 0.5), 3)
    _l(surf, STONE_D, (cx, spring - r + 1), (cx, spring + h), 3)
    if lit and glow:
        _add_glow(surf, 132, 132, (255, 198, 112), cx, spring + h * 0.4,
                  2.4, 90)

def _banner(surf, x, y, h=76, w=13):
    """Bandierina appesa alla merlatura, con il volo inferiore mozzato."""
    _r(surf, (74, 62, 54), x - w, y, w * 2, 6)
    left, right = x - w + 2, x + w - 2
    _p(surf, CRIMSON, [(left, y + h), (right, y + h), (right, y + h - 16),
                       (x + w * 0.2, y + h - 26), (left, y + h - 12)])
    _p(surf, CRIMSON_D, [(x + 2, y + 6), (right, y + 6), (right, y + h - 3),
                         (x + 2, y + h - 20)])
    _p(surf, GOLD, [(left + 2, y + 16), (right - 3, y + 12),
                    (right - 3, y + 22), (left + 2, y + 26)])

def _merlons(surf, x0, x1, y, w=30, gap=15, h=26):
    x = x0
    while x < x1:
        _r(surf, STONE, x, y - h, w, h + 2)
        _r(surf, STONE_L, x, y - h, w, 5)
        _r(surf, _tone(STONE, 0.72), x + w - 5, y - h, 5, h + 2)
        x += w + gap

def _masonry(surf, x0, x1, y0, y1, row=30, bw=64):
    """Corsi di pietre sfalsati, tracciati solo nella parte visibile."""
    y, r = y0, 0
    while y < y1:
        _l(surf, STONE_D, (x0, y), (x1, y))
        x = x0 - (bw // 2 if r % 2 else 0)
        while x < x1:
            _l(surf, STONE_D, (x, y), (x, min(y + row, y1)))
            x += bw
        y, r = y + row, r + 1

def _tower(surf, cx, h, roof, wide=52.0):
    """Torre di guardia: fusto rastremato, corona merlata, tetto, finestre."""
    base, top = GROUND + 8.0, GROUND - h

    def shaft(k):                              # sezione del fusto al livello k
        return [(cx - wide, base + (top - base) * k),
                (cx + wide, base + (top - base) * k)]
    _p(surf, STONE, shaft(0) + shaft(1)[::-1])
    _p(surf, _tone(STONE, 1.10),
       [(cx - wide, base), (cx - wide * 0.3, base)] + shaft(1)[1:2]
       + [(cx - wide * 0.3 + 8, top), (cx - wide + 8, top)])
    _r(surf, _tone(STONE, 0.68), cx + wide * 0.34, top, wide * 0.62, h + 8)
    _masonry(surf, cx - wide, cx + wide - 8, top + 8, base - 6)
    _r(surf, STONE, cx - wide - 9, top - 20, wide * 2 + 18, 24)   # corona
    _merlons(surf, cx - wide - 9, cx + wide + 9, top - 18, 22, 10, 22)
    ry = top - 18 - roof                                     # tetto a piramide
    _p(surf, SLATE, [(cx - wide - 13, ry + 22), (cx + wide + 13, ry + 22),
                     (cx, ry)])
    _p(surf, SLATE_L, [(cx - wide - 13, ry + 22), (cx, ry + 22), (cx, ry)])
    _l(surf, (66, 62, 72), (cx, ry), (cx, ry - 20), 4)          # puntale
    _c(surf, GOLD, cx, ry - 22, 4)
    _lit_window(surf, cx, base - h * 0.62, 24, 32)
    _lit_window(surf, cx, base - h * 0.32, 22, 30, lit=False)

def _gate(surf, cam_x, gcx):
    """Portone ad arco a tutto sesto: voussoir, stipiti, pavimento, torce."""
    r = (GATE_X1 - GATE_X0) * 0.5
    v = lambda a, rad: (gcx + math.cos(a) * rad,
                        GATE_SPRING + math.sin(a) * rad)  # anello dell'arco
    _p(surf, (34, 29, 27), [(gcx - r, GROUND + 6), (gcx + r, GROUND + 6)]
       + _arch(gcx, GATE_SPRING, r)[::-1])
    for col, k in (((52, 42, 36), 1.0), (_tone(ROAD, 0.9), 0.55)):
        _p(surf, col, [(gcx - r * k, GROUND + 6), (gcx + r * k, GROUND + 6),
                       (gcx + r * (k - 0.05), GROUND - 16),
                       (gcx - r * (k - 0.05), GROUND - 16)])
    for i in range(11):                       # chiave di volta
        a0 = math.pi + math.pi * i / 11.0
        a1 = math.pi + math.pi * (i + 1) / 11.0
        _p(surf, STONE_L if i % 2 else STONE,
           [v(a0, r + 16), v(a1, r + 16), v(a1, r), v(a0, r)])
        _l(surf, STONE_D, v(a0, r + 16), v(a0, r), 2)
    for side in (-1, 1):                      # stipiti dell'arco
        _r(surf, STONE_L, gcx + side * r - (11 if side > 0 else 0),
           GATE_SPRING, 11, GROUND + 6 - GATE_SPRING)
    _add_glow(surf, 300, 250, (255, 176, 92), gcx, GROUND - 130, 2.2, 80)
    for bx in (GATE_X0 + 30, GATE_X1 - 30):   # torce accese nel portico
        sx = bx - cam_x
        _r(surf, WOOD_D, sx - 3, GROUND - 78, 6, 40)
        _c(surf, (234, 154, 62), sx, GROUND - 82, 8)
        _c(surf, (252, 216, 140), sx, GROUND - 84, 4)
        _add_glow(surf, 104, 104, (255, 168, 84), sx, GROUND - 82, 2.4, 120)
        _ground_shadow(surf, sx + 6, GROUND + 2, 40, 11)

def draw_castle(surf, cam_x):
    """Mura di Castel Rosso, disegnate in spazio mondo."""
    wx, ww = CASTLE_X0 - cam_x, CASTLE_X1 - CASTLE_X0
    if wx > W + 120 or wx + ww < -120:
        return
    ty = WALL_TOP
    ix0, ix1 = max(wx, -60), min(wx + ww, W + 60)
    rock = [(wx - 110, GROUND + 16), (wx - 24, GROUND - 58),
            (wx + ww + 34, GROUND - 58), (wx + ww + 130, GROUND + 16)]
    _p(surf, _mix((80, 76, 74), HILL, 0.35), rock)      # scoglio di fondazione
    _p(surf, (58, 54, 56), [rock[0], rock[1], (wx - 8, GROUND - 14),
                            (wx - 46, GROUND + 16)])
    _r(surf, STONE, wx, ty, ww, GROUND - ty)           # cortina muraria
    _masonry(surf, ix0, ix1, ty + 14, GROUND - 22)
    _r(surf, STONE_L, ix0, ty, ix1 - ix0, 10)
    _r(surf, _tone(STONE, 0.66), ix0, GROUND - 22, ix1 - ix0, 8)
    _merlons(surf, ix0 + 2, ix1 - 2, ty + 2, 32, 16, 26)
    for k in range(4):                                 # feritoie sulla cortina
        bx = CASTLE_X0 + 190 + k * 190 - cam_x
        if ix0 - 20 < bx < ix1 + 20:
            _r(surf, (34, 28, 26), bx - 4, ty + 54, 8, 26)
            _r(surf, STONE_L, bx - 6, ty + 52, 12, 4)
    _banner(surf, CASTLE_X0 + 320 - cam_x, ty + 4, 84)
    _banner(surf, CASTLE_X1 - 70 - cam_x, ty + 4, 64)
    _tower(surf, CASTLE_X0 + 96 - cam_x, 372, 82, 56.0)
    _tower(surf, CASTLE_X1 - 54 - cam_x, 340, 70, 50.0)
    gx0, gx1 = GATE_X0 - cam_x, GATE_X1 - cam_x    # corpo di guardia
    gcx, top = (gx0 + gx1) * 0.5, GROUND - 350.0
    gw = (gx1 - gx0) * 0.5 + 40.0
    _r(surf, STONE, gcx - gw, top, gw * 2, GROUND + 10 - top)
    _r(surf, _tone(STONE, 1.10), gcx - gw, top, gw * 2, 12)
    _masonry(surf, gcx - gw, gcx + gw, top + 16, GROUND - 18)
    _merlons(surf, gcx - gw, gcx + gw, top + 4, 30, 14, 28)
    _lit_window(surf, gcx, top + 46, 26, 34)
    _banner(surf, gx0 + 30, top + 6, 92, 15)
    _banner(surf, gx1 - 30, top + 6, 92, 15)
    _gate(surf, cam_x, gcx)

def draw_portcullis(surf, cam_x, openness):
    """Grata di ferro che si alza all'inizio del livello."""
    gx0, gx1 = int(GATE_X0 - cam_x) + 4, int(GATE_X1 - cam_x) - 4
    gh = int(GROUND - GATE_TOP) - 40
    lift = int(gh * openness)
    if lift >= gh - 4 or gx1 < -20 or gx0 > W + 20:
        return
    top = int(GROUND - lift) - 2
    for x in range(gx0, gx1, 22):
        _r(surf, (44, 42, 44), x, top, 6, gh)
        _r(surf, (78, 76, 80), x, top, 2, gh)
        _r(surf, (32, 30, 32), x + 4, top, 2, gh)
    for i in range(1, 5):
        y = top + i * gh // 5
        _r(surf, (58, 56, 58), gx0, y, gx1 - gx0, 5)
        _r(surf, (88, 86, 90), gx0, y, gx1 - gx0, 2)

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
    global _DK
    for kind, x, s, tone, dark in PROPS:
        sx = x - cam_x
        if sx < -120 or sx > W + 120:
            continue
        _ground_shadow(surf, sx + 10 * s, PROP_Y + 2, SHADOW_W[kind] * s,
                       SHADOW_W[kind] * 0.3 * s)
        _DK = 0.46 if dark else 1.0      # nel bosco chiuso tutto e' piu' scuro
        _SHAPES[kind](surf, sx, s, tone)
    _DK = 1.0

# --- uscita: muro di foresta e svolta di luce sulla strada -----------------
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
    k = (26 + 16 * glow) / 255.0
    beam = pygame.Surface((360, 320), pygame.SRCALPHA)
    _p(beam, (int(WARM[0] * k), int(WARM[1] * k), int(WARM[2] * k), 255),
       [(168, 0), (198, 0), (330, 320), (34, 320)])
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
