"""Mondo: il castello e la strada che porta alla foresta.

Tutto disegnato a runtime, nessun asset. Coordinate mondo: x in avanti, y=0 e'
il terreno (GROUND). La telecamera segue il cavaliere.
"""

import math
import random

import pygame

GROUND = 520.0
W, H = 960, 540

# --- castello -------------------------------------------------------------
CASTLE_X0 = -520.0     # il castello sta alle spalle, fuori schermo
CASTLE_X1 = 260.0
GATE_X0 = -140.0
GATE_X1 = 120.0
GATE_TOP = GROUND - 210.0
COURT_X1 = CASTLE_X1    # fine del cortile

# --- strada ---------------------------------------------------------------
ROAD_Y = GROUND - 6.0
PILLARS = [980.0, 1560.0, 2180.0, 2840.0, 3460.0, 4120.0, 4760.0]
FOREST_X = 4950.0
GOAL_X = 5400.0

SKY_TOP = (78, 108, 152)
SKY_BOT = (176, 178, 190)
HILL_FAR = (108, 128, 158)
HILL_MID = (92, 116, 116)
HILL_NEAR = (78, 106, 88)
GRASS = (82, 112, 68)
GRASS_D = (64, 92, 56)
ROAD = (128, 112, 84)
ROAD_D = (108, 94, 70)
STONE = (128, 124, 118)
STONE_D = (98, 94, 90)
STONE_L = (154, 150, 144)
WOOD = (96, 74, 52)


def _sky(w, h):
    s = pygame.Surface((w, h))
    for y in range(h):
        t = y / h
        s.fill((int(SKY_TOP[0] + (SKY_BOT[0] - SKY_TOP[0]) * t),
                int(SKY_TOP[1] + (SKY_BOT[1] - SKY_TOP[1]) * t),
                int(SKY_TOP[2] + (SKY_BOT[2] - SKY_TOP[2]) * t)), (0, y, w, 1))
    return s


SKY = _sky(W, H)


def draw_sky(surf):
    surf.blit(SKY, (0, 0))


def _ridge(surf, cam_x, base, amp, freq, par, col, seed):
    pts = [(-40, surf.get_height() + 10)]
    x = -40.0
    while x < surf.get_width() + 40:
        u = (x + cam_x * par) * freq + seed
        y = base - amp * (math.sin(u) * 0.6 + math.sin(u * 2.3 + 1.1) * 0.4)
        pts.append((x, y))
        x += 26
    pts.append((surf.get_width() + 40, surf.get_height() + 10))
    pygame.draw.polygon(surf, col, pts)


def draw_background(surf, cam_x):
    _ridge(surf, cam_x, 330, 46, 0.0022, 0.18, HILL_FAR, 0.0)
    _ridge(surf, cam_x, 392, 34, 0.0034, 0.34, HILL_MID, 2.1)
    # trees on the near ridge
    rng = random.Random(4)
    for i in range(46):
        bx = rng.uniform(0, 2600)
        sx = bx - cam_x * 0.52
        if sx < -40 or sx > W + 40:
            continue
        yb = 372 + rng.uniform(-8, 14)
        pygame.draw.rect(surf, (58, 74, 62), (int(sx), int(yb), 4, 26))
        pygame.draw.circle(surf, HILL_NEAR, (int(sx + 2), int(yb - 4)), 13)


def draw_ground(surf, cam_x):
    pygame.draw.rect(surf, GRASS, (0, GROUND, W, H - GROUND))
    # the road: a strip of packed earth leaving the gate
    x0 = GATE_X0 - 80
    x1 = FOREST_X + 200
    sx0 = int(x0 - cam_x)
    sx1 = int(x1 - cam_x)
    pygame.draw.polygon(surf, ROAD, [
        (sx0, GROUND + 4), (sx1, GROUND + 4),
        (sx1 + 240, H + 10), (sx0 - 240, H + 10)])
    for i in range(0, int(x1 - x0), 30):
        sx = x0 + i - cam_x
        if -20 < sx < W + 20:
            pygame.draw.line(surf, ROAD_D, (sx, GROUND + 8), (sx - 9, H))
    # tufts of grass
    rng = random.Random(9)
    for _ in range(90):
        bx = rng.uniform(-200, FOREST_X + 400)
        sx = bx - cam_x
        if -10 < sx < W + 10 and abs(bx - (x0 + x1) / 2) > 0:
            if abs(sx) < W:
                if not (GATE_X0 - 120 < bx < GATE_X1 + 200):
                    pygame.draw.line(surf, GRASS_D,
                                     (sx, GROUND), (sx + 3, GROUND - 9))


def draw_castle(surf, cam_x):
    """Mura del castello, disegnate in spazio mondo."""
    top = GROUND - 300.0
    wx = int(CASTLE_X0 - cam_x)
    ww = int(CASTLE_X1 - CASTLE_X0)
    if wx > W or wx + ww < 0:
        return
    ty = int(top)
    h = int(GROUND - top)
    # cliff the castle sits on
    pygame.draw.polygon(surf, (92, 88, 82), [
        (wx - 60, GROUND + 10), (wx + 30, GROUND - 40),
        (wx + ww - 30, GROUND - 40), (wx + ww + 60, GROUND + 10)])
    # masonry
    pygame.draw.rect(surf, STONE, (wx, ty, ww, h))
    row, y, r = 36, ty, 0
    while y < GROUND:
        x = wx - (66 if r % 2 else 0)
        while x < wx + ww:
            pygame.draw.line(surf, STONE_D, (x, y), (x, min(y + row, int(GROUND))))
            x += 66
        pygame.draw.line(surf, STONE_D, (wx, y), (wx + ww, y))
        y += row
        r += 1
    # crenellations
    x = wx
    while x < wx + ww:
        pygame.draw.rect(surf, STONE, (x, ty - 28, 38, 30))
        pygame.draw.rect(surf, STONE_L, (x, ty - 28, 38, 4))
        x += 62
    # gatehouse
    gx0, gx1 = int(GATE_X0 - cam_x), int(GATE_X1 - cam_x)
    gt = int(GATE_TOP)
    gh = int(GROUND - GATE_TOP)
    pygame.draw.rect(surf, STONE, (gx0 - 26, gt - 46, gx1 - gx0 + 52, gh + 46))
    for x in range(gx0 - 26, gx1 - gx0 + gx0 + 26, 62):
        pygame.draw.rect(surf, STONE, (x, gt - 74, 38, 30))
    pygame.draw.rect(surf, (32, 28, 26), (gx0, gt, gx1 - gx0, gh))
    # arched opening
    pygame.draw.rect(surf, (26, 23, 22), (gx0, gt + 46, gx1 - gx0, gh - 46))
    pygame.draw.circle(surf, (26, 23, 22), ((gx0 + gx1) // 2, gt + 46),
                       (gx1 - gx0) // 2)
    # torchlight inside
    pygame.draw.circle(surf, (226, 150, 60), (gx0 + 14, int(GROUND) - 40), 7)
    pygame.draw.circle(surf, (250, 206, 120), (gx1 - 14, int(GROUND) - 40), 7)
    # banners
    for bx in (CASTLE_X0 + 90, CASTLE_X1 - 120):
        sx = int(bx - cam_x)
        pygame.draw.rect(surf, (60, 46, 36), (sx - 2, ty + 20, 5, 90))
        pygame.draw.polygon(surf, (150, 40, 44), [
            (sx + 3, ty + 20), (sx + 3, ty + 104),
            (sx + 34, ty + 92), (sx + 3, ty + 78)])


def draw_portcullis(surf, cam_x, openness):
    """Grata che si alza all'inizio del livello."""
    gx0, gx1 = int(GATE_X0 - cam_x) + 4, int(GATE_X1 - cam_x) - 4
    gh = int(GROUND - GATE_TOP) - 40
    lift = int(gh * openness)
    if lift >= gh - 4:
        return
    top = int(GROUND - lift) - 2
    for x in range(gx0, gx1, 22):
        pygame.draw.rect(surf, (48, 46, 48), (x, top, 5, gh))
    for i in range(1, 4):
        pygame.draw.rect(surf, (64, 62, 64), (gx0, top + i * gh // 4,
                                              gx1 - gx0, 4))


# --- props ----------------------------------------------------------------
def _props():
    rng = random.Random(21)
    items = []
    for x in PILLARS:
        items.append(("pillar", x))
    for _ in range(160):
        x = rng.uniform(-400, FOREST_X + 300)
        if CASTLE_X0 - 60 < x < CASTLE_X1 + 60 or GATE_X0 - 140 < x < GATE_X1 + 240:
            continue
        items.append((rng.choice(("tree", "rock", "bush")), x))
    for i in range(70):
        items.append(("tree", FOREST_X + rng.uniform(0, 700)))
    return items


PROPS = _props()


def draw_props(surf, cam_x):
    for kind, x in PROPS:
        sx = int(x - cam_x)
        if sx < -70 or sx > W + 70:
            continue
        if kind == "tree":
            h = 44 if x < FOREST_X else 62
            pygame.draw.rect(surf, WOOD, (sx - 5, GROUND - h * 0.6, 10, h * 0.6))
            for i in range(3):
                pygame.draw.circle(
                    surf, (46, 82, 52) if x < FOREST_X else (38, 70, 48),
                    (sx + int(math.sin(i * 2.1 + x) * 12), GROUND - h - i * 12),
                    int(h * 0.42) - i * 4)
        elif kind == "bush":
            pygame.draw.circle(surf, (62, 92, 56), (sx, GROUND - 10), 14)
            pygame.draw.circle(surf, (72, 104, 62), (sx + 10, GROUND - 8), 10)
        elif kind == "rock":
            pygame.draw.rect(surf, (120, 116, 110), (sx - 9, GROUND - 11, 19, 11))
        else:
            _pillar(surf, sx)


def _pillar(surf, sx):
    top = GROUND - 250
    pygame.draw.rect(surf, STONE, (sx - 16, top, 32, GROUND - top))
    pygame.draw.rect(surf, STONE_L, (sx - 16, top, 32, 6))
    pygame.draw.rect(surf, STONE, (sx - 24, top - 18, 48, 20))
    pygame.draw.rect(surf, STONE_D, (sx + 4, top, 6, GROUND - top))
    for i in range(4):
        pygame.draw.rect(surf, STONE_D, (sx - 16, top + 40 + i * 52, 32, 3))
    # tattered banner
    pygame.draw.rect(surf, (104, 44, 44), (sx - 22, top + 12, 8, 44))


def draw_goal(surf, cam_x, t):
    """The road into the forest: the end of level 1."""
    sx = int(GOAL_X - cam_x)
    if sx < -120 or sx > W + 120:
        return
    # forest wall
    for i in range(30):
        x = sx - 260 + i * 18
        pygame.draw.rect(surf, (34, 62, 42), (x, GROUND - 210, 20, 210))
    pygame.draw.rect(surf, (44, 76, 50), (sx - 260, GROUND - 60, 520, 60))
    # two stone markers flanking the way out
    for bx in (sx - 34, sx + 34):
        pygame.draw.rect(surf, STONE, (bx - 10, GROUND - 70, 20, 70))
        pygame.draw.rect(surf, STONE_L, (bx - 10, GROUND - 70, 20, 5))
    glow = 0.5 + 0.5 * math.sin(t * 2.0)
    halo = pygame.Surface((200, 200), pygame.SRCALPHA)
    pygame.draw.circle(halo, (250, 226, 150, int(40 + 40 * glow)), (100, 100), 90)
    surf.blit(halo, (sx - 100, int(GROUND - 90)))