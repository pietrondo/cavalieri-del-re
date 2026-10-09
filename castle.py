"""Castel Rosso: mura, torri, portone e grata.

Il castello sta alle spalle del livello, fuori schermo per quasi tutto il
gioco: e' pero' la prima cosa che si vede, quindi ha un vocabolario proprio
(archi, merlature, muratura) che nessun'altra parte della scena riusa.

Coordinate mondo: x in avanti, y=0 sul terreno (GROUND in paint.py).
"""

import math

import pygame

from paint import (GROUND, W, HILL, STONE, STONE_D, STONE_L, SLATE, SLATE_L,
                   WOOD_D, GOLD, CRIMSON, CRIMSON_D, ROAD,
                   _r, _p, _l, _c, _tone, _mix, _add_glow, _ground_shadow)

CASTLE_X0 = -520.0      # il castello sta alle spalle, fuori schermo
CASTLE_X1 = 260.0
GATE_X0, GATE_X1 = -140.0, 120.0
GATE_TOP = GROUND - 210.0
GATE_SPRING = GROUND - 132.0     # imposta dell'arco del portone
COURT_X1 = CASTLE_X1
WALL_TOP = GROUND - 300.0

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