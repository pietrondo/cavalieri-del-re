"""I provviste lungo la strada: cuore, scudo, oro.

Ogni tipo ha un'immagine costruita una volta sola e messa in cache, disegnata
con lo stesso vocabolario di sprites.py (contorno scuro, banda illuminata dal
lato in alto a sinistra, riverbero freddo nel lato ombra): era una coppia di
cerchi con un poligono dentro, e in mezzo a un'animazione cosi' curata sembrava
un marker di debug.
"""

import math
import random

import pygame

import world

GROUND = world.GROUND

ART = 46                      # px, tela quadrata di un provvista
_R = 15.0                     # raggio di riferimento del disegno
_C = ART / 2.0
OUTLINE = (14, 11, 18)

PICKUPS = {
    "heart": ((196, 54, 58), "vita"),
    "shield": ((72, 122, 196), "scudo 6s"),
    "gold": ((214, 176, 74), "oro"),
}


def _tone(c, f):
    return (max(0, min(255, int(c[0] * f))), max(0, min(255, int(c[1] * f))),
            max(0, min(255, int(c[2] * f))))


def _coin(s, cx, cy, r, k, col, dx=0.0, dy=0.0):
    pygame.draw.circle(s, col, (int(cx + dx), int(cy + dy)), int(r * k))


def _sil(s, kind, k, col, dx=0.0, dy=0.0):
    """La silhouette del provvista, `k` la scala. Si disegna piu' volte con
    colori diversi: contorno, corpo in ombra, banda illuminata."""
    r = _R * k
    cx, cy = _C + dx, _C + dy
    if kind == "heart":
        pygame.draw.circle(s, col, (int(cx - r * .48), int(cy - r * .28)),
                           int(r * .52))
        pygame.draw.circle(s, col, (int(cx + r * .48), int(cy - r * .28)),
                           int(r * .52))
        pygame.draw.polygon(s, col, [(cx - r * .94, cy - r * .10),
                                     (cx + r * .94, cy - r * .10), (cx, cy + r)])
    elif kind == "shield":
        pygame.draw.polygon(s, col, [(cx, cy - r), (cx + r * .84, cy - r * .56),
                                     (cx + r * .70, cy + r * .30), (cx, cy + r),
                                     (cx - r * .70, cy + r * .30),
                                     (cx - r * .84, cy - r * .56)])
    else:                       # oro: la moneta davanti
        _coin(s, cx - r * .12, cy + r * .18, r * .80, 1.0, col)


def _art(kind):
    """Immagine del provvista, costruita al primo uso e tenuta in cache."""
    a = _ART_CACHE.get(kind)
    if a is not None:
        return a
    base = PICKUPS[kind][0]
    s = pygame.Surface((ART, ART), pygame.SRCALPHA)
    if kind == "gold":
        # la moneta dietro va disegnata e contornata PRIMA di quella davanti,
        # altrimenti le due silhouette si fondono in una massa
        bx, by, br = _C + _R * .34, _C - _R * .26, _R * .66
        _coin(s, bx, by, br, 1.18, OUTLINE)
        _coin(s, bx, by, br, 1.00, _tone(base, 0.58))
        _coin(s, bx, by, br, 0.70, _tone(base, 0.86), -br * .12, -br * .16)
    _sil(s, kind, 1.20, OUTLINE)                       # contorno scuro
    _sil(s, kind, 1.00, _tone(base, 0.78))             # corpo: la parte in ombra
    _sil(s, kind, 0.82, base, -_R * .10, -_R * .22)    # banda illuminata
    _sil(s, kind, 0.34, _tone(base, 1.40), -_R * .20, -_R * .40)   # riflesso
    if kind == "shield":
        # fascia e umbone: e' quello che distingue uno scudo da un pentagono
        pygame.draw.rect(s, _tone(base, 1.16),
                         (int(_C - _R * .80), int(_C - _R * .04),
                          int(_R * 1.60), int(_R * .26)))
        pygame.draw.circle(s, OUTLINE, (int(_C), int(_C + _R * .06)),
                           int(_R * .30))
        pygame.draw.circle(s, _tone(base, 0.90),
                           (int(_C), int(_C + _R * .06)), int(_R * .25))
        pygame.draw.circle(s, _tone(base, 1.26),
                           (int(_C - _R * .05), int(_C + _R * .01)),
                           int(_R * .17))
    elif kind == "gold":
        pygame.draw.circle(s, _tone(base, 0.66),
                           (int(_C - _R * .22), int(_C + _R * .32)),
                           int(_R * .44), 2)
    pygame.draw.circle(s, (255, 244, 224), (int(_C - _R * .30), int(_C - _R * .38)),
                       max(1, int(_R * .16)))            # punto di luce
    _ART_CACHE[kind] = s
    return s


_ART_CACHE = {}


class Pickup:
    def __init__(self, x, kind):
        self.x = float(x)
        self.y = GROUND - 34.0
        self.kind = kind
        self.t = random.uniform(0, 6.0)
        self.land = 0.0
        self.taken = False

    def update(self, dt):
        self.t += dt
        self.land = min(1.0, self.land + dt * 3.5)

    def draw(self, surf, cam_x):
        col = PICKUPS[self.kind][0]
        x = int(self.x - cam_x)
        y = int(self.y + math.sin(self.t * 2.4) * 4.0 - 12 * (1 - self.land))
        # alone e ombra a terra: senza la pozza scura l'oggetto galleggia
        surf.blit(world._glow(72, 40, col, 2.2, 80), (x - 36, y - 20))
        surf.blit(world._glow(48, 16, (18, 14, 24), 1.6, 130),
                  (x - 24, int(GROUND - 6) - 8))
        surf.blit(_art(self.kind), (x - int(_C), y - int(_C)))