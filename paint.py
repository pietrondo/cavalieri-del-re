"""La tela e il vocabolario con cui si disegna: dimensioni, quota del terreno,
palette del crepuscolo, le scorciatoie su pygame.draw e gli aloni.

Ogni modulo che disegna (world, castle, pickup) passa di qui. Tenere le
primitive in un posto solo e' quello che permette a `_DK` di scurire TUTTO
quello che esce da una scena, senza tingere una sfumatura per funzione.
"""

import math

import pygame

W, H = 960, 540
GROUND = 520.0          # y=0 e' il terreno; le costanti mondo partono da qui

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


def palette():
    """Colori chiave dello sfondo: game.py li usa per overlay nemici e HUD."""
    return dict(_PALETTE)


_DK = 1.0      # scurimento corrente: sotto 1 dentro il bosco finale


def set_dark(k):
    """Scurisce globalmente tutto quello che viene disegnato dopo."""
    global _DK
    _DK = k


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


# --- ombre proiettate: la luce arriva dall'alto a sinistra ----------------
_GSHADOWS = {}


def _ground_shadow(surf, x, y, w, h):
    """Ellisse scura schiacciata alla base: e' cio' che fa leggere gli oggetti
    appoggiati al terreno invece di galleggiare sopra."""
    w, h = max(3, int(w)), max(2, int(h))
    if (w, h) not in _GSHADOWS:
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        _e(s, (*SHADOW, 120), 0, 0, w, h)
        _e(s, (*SHADOW, 60), 1, 1, w - 2, h - 2)
        _GSHADOWS[(w, h)] = s
    surf.blit(_GSHADOWS[(w, h)], (int(x - w / 2), int(y - h / 2)))