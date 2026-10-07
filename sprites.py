"""Sprites as Python: zero image assets in this repo.

Every character is a bone hierarchy. The rest pose is authored in plain world
coordinates - feet at y=0, facing +x, y pointing down - so a rig is a list of
"where these joints are" and nothing else. Each frame:

  1. apply a pose (per-bone angle offsets) on top of the rest pose,
  2. solve forward kinematics,
  3. rasterise capsules and polygons on a 3x supersampled surface,
  4. smoothscale down, which is where the anti-aliasing comes from.

Rest angles are explicit and `Rig` asserts that every limb actually reaches its
child joint, so a bad rest pose fails loudly instead of drawing garbage.
"""

import math
from dataclasses import dataclass, field

import pygame

TAU = math.pi * 2
SS = 3  # supersampling -> anti-aliasing without a single pixel of art


def lerp(a, b, t):
    return a + (b - a) * t


def ease(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def mix_angle(a, b, t):
    return a + ((b - a + math.pi) % TAU - math.pi) * t


@dataclass
class Bone:
    """Rest-pose definition. x/y/ang are WORLD values; ang is the direction the
    bone points in the rest pose (0 = +x, pi/2 = straight down)."""

    name: str
    parent: str | None = None
    x: float = 0.0
    y: float = 0.0
    ang: float = 0.0
    length: float = 0.0
    w0: float = 0.0
    w1: float = 0.0
    color: tuple = (128, 128, 136)
    shape: str = "limb"  # limb | poly | circle
    pts: list = field(default_factory=list)
    scale: float = 1.0
    chain: bool = False   # built by Builder.limb: must reach its child's joint

    def world_tip(self):
        return (self.x + math.cos(self.ang) * self.length,
                self.y + math.sin(self.ang) * self.length)


@dataclass
class Draw:
    """A bone resolved into parent-local space: what the renderer and the FK
    solver actually work with."""

    name: str
    parent: str | None
    x: float
    y: float
    ang: float
    length: float
    w0: float
    w1: float
    color: tuple
    shape: str
    pts: list


class Rig:
    """Bones are DRAWN in list order (back to front). The `root` empty bone is
    the only parentless anchor, so draw order is free of hierarchy order."""

    def __init__(self, joints, w, h):
        rest = {j.name: j for j in joints}
        self.bones, self.map = [], {}
        for j in joints:
            if j.parent is None:
                lx, ly = j.x, j.y
            else:
                p = rest[j.parent]
                pa = self._world_ang(rest, p)
                c, s = math.cos(-pa), math.sin(-pa)
                dx, dy = j.x - p.x, j.y - p.y
                lx, ly = dx * c - dy * s, dx * s + dy * c
            b = Draw(j.name, j.parent, lx, ly, j.ang, j.length, j.w0, j.w1,
                     j.color, j.shape, j.pts)
            self.bones.append(b)
            self.map[j.name] = b
        self.w, self.h = w, h
        self._check(rest)

    @staticmethod
    def _world_ang(rest, j):
        a = j.ang
        while j.parent is not None:
            j = rest[j.parent]
            a += j.ang
        return a

    def _check(self, rest):
        """A limb must end exactly on its own CHILD joint, otherwise the FK
        solve silently detaches the limb from the body."""
        child_of = {}
        for j in rest.values():
            # only a CHAINED child sits on its parent's tip; decorations hang
            # wherever they were placed
            if j.parent is not None and j.chain:
                child_of[j.parent] = j
        for j in rest.values():
            if not j.chain:
                continue
            c = child_of.get(j.name)
            if c is None:
                continue
            tip = j.world_tip()
            assert abs(tip[0] - c.x) < 0.6 and abs(tip[1] - c.y) < 0.6, (
                "bone %r does not reach joint %r: tip %s vs %s"
                % (j.name, c.name, tuple(round(v, 2) for v in tip), (c.x, c.y)))

    def solve(self, angles=None, root=(0.0, 0.0)):
        angles = angles or {}
        t = {}
        for b in self.bones:
            a = b.ang + angles.get(b.name, 0.0)
            if b.parent is None:
                t[b.name] = (root[0] + b.x, root[1] + b.y, a)
                continue
            px, py, pa = t[b.parent]
            c, s = math.cos(pa), math.sin(pa)
            t[b.name] = (px + b.x * c - b.y * s, py + b.x * s + b.y * c, pa + a)
        return t

    def tip_of(self, name, angles=None, root=(0.0, 0.0)):
        _, _, a = self.solve(angles, root)[name]
        b = self.map[name]
        return b.length, a


# key light: from the upper left, slightly behind. Everything is lit by this
# one vector, so the whole cast reads as lit by the same source.
LIGHT = (-0.42, -0.91)
RIM = (0.55, 0.83)          # opposite: the cool bounce edge


def _tone(c, f):
    return (max(0, min(255, int(c[0] * f))),
            max(0, min(255, int(c[1] * f))),
            max(0, min(255, int(c[2] * f))))


def _tint(c, k, f):
    """Blend toward k (a 0..1 grey-blue) while scaling brightness by f."""
    return tuple(max(0, min(255, int(c[i] * f * (1 - k) + k * 232 * f)))
                 for i in range(3))


def _mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _shade_poly(surf, pts, base, outline):
    """Fill a polygon, then a light band along its lit edge and a cool dark band
    along the shadowed one. Cheap two-tone shading that follows the light."""
    n = len(pts)
    if n < 3:
        return
    cx = sum(p[0] for p in pts) / n
    cy = sum(p[1] for p in pts) / n
    proj = [(p[0] - cx) * LIGHT[0] + (p[1] - cy) * LIGHT[1] for p in pts]
    span = max(1.0, max(proj) - min(proj))
    pygame.draw.polygon(surf, outline, pts, max(1, SS // 2))
    pygame.draw.polygon(surf, _tone(base, 0.94), pts)
    for cut, col in ((0.14, _tone(base, 1.16)),
                     (0.44, _tone(base, 1.34)),
                     (-0.30, _mix(base, _tone((44, 56, 82), 0.9), 0.40))):
        sel = [(x, y) for (x, y), t in zip(pts, proj)
               if (t > span * cut if cut > 0 else t < span * cut)]
        if len(sel) >= 3:
            pygame.draw.polygon(surf, col, sel)


def _draw(surf, b, gx, gy, ga, dark, occl):
    """One bone. `occl` (0..1) darkens it when it sits behind something else -
    that is how the far legs read as far legs."""
    base = _tone(b.color, dark * (1.0 - 0.42 * occl))
    outline = _tint(b.color, 0.45, 0.50 * dark)

    if b.shape == "poly":
        c, s = math.cos(ga), math.sin(ga)
        pts = [((gx + px * c - py * s) * SS, (gy + px * s + py * c) * SS)
               for px, py in b.pts]
        _shade_poly(surf, pts, base, outline)
        return

    if b.shape == "circle":
        r = max(1.0, b.length)
        pygame.draw.circle(surf, outline, (int(gx * SS), int(gy * SS)),
                           int((r + 1.2) * SS))
        pygame.draw.circle(surf, base, (int(gx * SS), int(gy * SS)),
                           int(r * SS))
        hl = (gx + LIGHT[0] * r * 0.42, gy + LIGHT[1] * r * 0.42)
        pygame.draw.circle(surf, _tone(base, 1.22), (int(hl[0] * SS),
                                                      int(hl[1] * SS)),
                           int(r * 0.5 * SS))
        return

    ex, ey = gx + math.cos(ga) * b.length, gy + math.sin(ga) * b.length
    nx, ny = -math.sin(ga), math.cos(ga)      # the bone's own "up"
    r0, r1 = max(1.2, b.w0 / 2), max(1.0, b.w1 / 2)
    light = LIGHT[0] * nx + LIGHT[1] * ny     # >0 when the light is on this side

    def quad(r0_, r1_, slide):
        # slide shifts the cross-section toward the light
        a = slide * abs(light)
        return [
            ((gx + nx * (r0_ * math.copysign(1.0, light) + a)) * SS,
             (gy + ny * (r0_ * math.copysign(1.0, light) + a)) * SS),
            ((ex + nx * (r1_ * math.copysign(1.0, light) + a)) * SS,
             (ey + ny * (r1_ * math.copysign(1.0, light) + a)) * SS),
            ((ex - nx * (r1_ * math.copysign(1.0, light) + a)) * SS,
             (ey - ny * (r1_ * math.copysign(1.0, light) + a)) * SS),
            ((gx - nx * (r0_ * math.copysign(1.0, light) + a)) * SS,
             (gy - ny * (r0_ * math.copysign(1.0, light) + a)) * SS)]

    # 1. outline
    pygame.draw.polygon(surf, outline, quad(r0 + 1.3, r1 + 1.3, 0.0))
    pygame.draw.circle(surf, outline, (int(gx * SS), int(gy * SS)),
                       int((r0 + 1.3) * SS))
    pygame.draw.circle(surf, outline, (int(ex * SS), int(ey * SS)),
                       int((r1 + 1.3) * SS))
    # 2. base fill
    pygame.draw.polygon(surf, base, quad(r0, r1, 0.0))
    pygame.draw.circle(surf, base, (int(gx * SS), int(gy * SS)), int(r0 * SS))
    pygame.draw.circle(surf, base, (int(ex * SS), int(ey * SS)), int(r1 * SS))
    # 3. lit band on the light side, core highlight along the spine
    sign = 1.0 if light >= 0 else -1.0
    lit = 0.42 * abs(light)
    pygame.draw.polygon(surf, _tone(base, 1.16),
                        quad(r0 * lit, r1 * lit, r0 * (0.62 - lit) * sign))
    core = 0.20 * abs(light)
    pygame.draw.polygon(surf, _tone(base, 1.40),
                        quad(r0 * core, r1 * core, r0 * (0.74 - core) * sign))
    # 4. cool bounce on the shadow side
    pygame.draw.polygon(surf, _mix(base, _tone((46, 58, 84), 0.9), 0.42),
                        quad(r0 * 0.22, r1 * 0.22,
                             -r0 * (0.80 - 0.22) * sign))
    if occl > 0:
        pygame.draw.polygon(surf, _tint(b.color, 0.5, 0.34 * dark),
                            quad(r0 * 0.9, r1 * 0.9, r0 * 0.9 * sign))


def render(rig, angles=None, root=(0.0, 0.0), dark=1.0, flip=False,
           occluded=()):
    """-> (surface, transform). Inside the image the entity's feet point sits at
    (rig.w, rig.h); everything above it is headroom.

    `occluded` names bones to push back (far-side legs, the far arm): they get
    darkened and desaturated so depth reads without any real lighting.
    """
    tr = rig.solve(angles, root)
    surf = pygame.Surface((rig.w * 2 * SS, rig.h * 2 * SS), pygame.SRCALPHA)
    for b in rig.bones:
        gx, gy, ga = tr[b.name]
        _draw(surf, b, gx + rig.w, gy + rig.h, ga, dark,
              0.75 if b.name in occluded else 0.0)
    out = pygame.transform.smoothscale(surf, (rig.w * 2, rig.h * 2))
    if flip:
        out = pygame.transform.flip(out, True, False)
    return out, tr


# bones that belong to the far side of the body, per rig kind
HORSE_FAR = ("tail", "tail2", "leg_hf", "knee_hf", "hoof_hf",
             "leg_ff", "knee_ff", "hoof_ff", "cloth", "trim")
HUMAN_FAR = ("arm_f", "fa_f", "shield", "thigh_f", "shin_f", "foot_f")


def render_horse(rig, angles, root, dark=1.0, flip=False):
    return render(rig, angles, root, dark, flip, HORSE_FAR)


def render_human(rig, angles, root, dark=1.0, flip=False):
    return render(rig, angles, root, dark, flip, HUMAN_FAR)


def blit(surf, img, rig, x, y, flip=False):
    """Blit with the feet point at world (x, y)."""
    ox = x - rig.w if not flip else x + rig.w
    surf.blit(img, (int(ox), int(y - rig.h)))


# --------------------------------------------------------------------------
# Palettes
# --------------------------------------------------------------------------
STEEL = (178, 188, 202)
STEEL_D = (114, 124, 142)
CRIMSON = (176, 46, 48)
CRIMSON_D = (122, 26, 30)
GOLD = (216, 178, 76)
OCHRE = (156, 130, 68)
OCHRE_D = (116, 94, 48)
HORSE = (138, 90, 54)
HORSE_D = (100, 64, 38)
MANE = (46, 34, 28)
HOOF = (58, 52, 48)
WOOD = (124, 90, 58)
GREY = (130, 138, 154)
GREY_D = (86, 94, 108)
BLACK = (56, 58, 68)


class Builder:
    """Author a rest pose without arithmetic: limbs chain off their parent's tip,
    decorations take world coordinates. Chains cannot come out broken."""

    def __init__(self, scale=1.0):
        self.j = []
        self.scale = scale
        self.pos = {}

    def link(self, name, parent, at, ang, length, w0, w1, color):
        """A limb whose START is pinned at a world point, not at the parent's
        tip. Used for the barrel, which hangs off the root anchor."""
        x, y = at[0] + math.cos(ang) * length, at[1] + math.sin(ang) * length
        b = Bone(name, parent, at[0], at[1], ang, length, w0, w1, color, "limb",
                 scale=self.scale)
        self.j.append(b)
        self.pos[name] = (x, y)
        return self

    def limb(self, name, parent, ang, length, w0, w1, color):
        """Chain a limb onto its parent's tip. This is the only kind of bone
        that is required to reach its child - decorations may hang anywhere."""
        self.link(name, parent, self.pos[parent], ang, length, w0, w1, color)
        self.j[-1].chain = True
        return self

    def deco(self, name, parent, x, y, ang, shape, pts, color, size=0.0):
        self.j.append(Bone(name, parent, x, y, ang, size, 0, 0, color, shape,
                           pts, scale=self.scale))
        self.pos[name] = (x, y)
        return self

    def on(self, name):
        return self.pos[name]

    def build(self, w, h):
        return Rig(self.j, w, h)


def _horse(coat=None, trim=None, scale=1.0):
    """Bay warhorse. Feet y=0, withers y=-82, nose y=-92. Faces +x."""
    far, near = HORSE_D, HORSE
    b = Builder(scale)
    b.deco("root", None, 0, 0, 0.0, "circle", [], HORSE, 1.0)
    # --- behind the horse ---
    b.link("tail", "root", (-36, -72), 2.52, 22, 11, 6, MANE)
    b.limb("tail2", "tail", 2.68, 18, 6, 4, MANE)
    b.limb("tail3", "tail2", 2.80, 14, 4, 2, MANE)
    # --- far legs: the barrel covers them, so they read as depth ---
    b.link("leg_hf", "root", (-24, -58), 1.52, 26, 16, 9, far)
    b.limb("knee_hf", "leg_hf", 1.66, 24, 9, 6, far)
    b.limb("hoof_hf", "knee_hf", 1.57, 9, 9, 8, HOOF)
    b.link("leg_ff", "root", (12, -60), 1.50, 26, 16, 9, far)
    b.limb("knee_ff", "leg_ff", 1.68, 24, 9, 6, far)
    b.limb("hoof_ff", "knee_ff", 1.57, 9, 9, 8, HOOF)
    # --- barrel: deep at the girth, tucked along the belly ---
    b.link("rump", "root", (-42, -66), 0.16, 28, 35, 33, HORSE)
    b.limb("barrel", "rump", -0.06, 32, 33, 29, HORSE)
    b.limb("chest", "barrel", -0.10, 20, 29, 23, HORSE)
    # --- neck at ~45 degrees, then a long head carried forward ---
    b.limb("neck", "chest", -0.52, 28, 22, 13, HORSE)
    b.limb("crest", "neck", -0.30, 18, 13, 10, HORSE)
    b.limb("head", "crest", -0.06, 26, 15, 8, HORSE)
    hx, hy = b.on("head")
    b.deco("muzzle", "head", hx + 1, hy + 1, 0.0, "circle", [], (62, 52, 46),
           6.5)
    b.deco("nostril", "muzzle", hx + 1, hy - 1, 0.0, "circle", [], (26, 20, 18),
           1.8)
    b.deco("jaw", "head", hx - 3, hy + 5, 0.0, "poly",
           [(0, 0), (-10, -1), (-10, 5), (0, 6)], (62, 52, 46))
    b.deco("eye", "head", hx - 15, hy - 6, 0.0, "circle", [], (16, 12, 10), 2.6)
    b.deco("brow", "head", hx - 16, hy - 9, 0.0, "circle", [], (16, 12, 10), 1.9)
    b.deco("ear_a", "head", hx - 23, hy - 6, 0.0, "poly",
           [(0, 3), (-4, -11), (6, -8)], HORSE_D)
    b.deco("ear_b", "head", hx - 18, hy - 6, 0.0, "poly",
           [(0, 3), (-3, -11), (7, -7)], HORSE_D)
    b.deco("forelock", "head", hx - 25, hy - 7, 0.0, "poly",
           [(-3, 3), (4, -7), (12, -5), (5, 4)], MANE)
    nx, ny = b.on("chest")   # the mane runs along the whole neck, from the base
    b.deco("mane", "neck", nx, ny, -0.52, "poly",
           [(-2, 2), (8, -4), (22, -5), (36, -4), (46, -1),
            (36, 1), (20, 1), (-2, 4)], MANE)
    if coat:
        # caparison hangs from the saddle: over the barrel, under the near legs
        rx, ry = b.on("rump")
        cx, cy = b.on("chest")
        mx, my = (rx + cx) / 2, (ry + cy) / 2 - 14
        b.deco("cloth", "barrel", mx, my, 1.5708, "poly",
               [(-30, 0), (30, 0), (34, 26), (12, 22), (-10, 26), (-34, 22)],
               coat)
        b.deco("trim", "cloth", mx, my + 21, 1.5708, "poly",
               [(-32, -6), (32, -6), (32, 4), (-32, 4)], trim or GOLD)
    # --- near legs, in front of the barrel ---
    b.link("leg_hn", "root", (-21, -58), 1.52, 26, 17, 10, near)
    b.limb("knee_hn", "leg_hn", 1.66, 24, 10, 6, near)
    b.limb("hoof_hn", "knee_hn", 1.57, 9, 10, 9, HOOF)
    b.link("leg_fn", "root", (15, -60), 1.50, 26, 17, 10, near)
    b.limb("knee_fn", "leg_fn", 1.68, 24, 10, 6, near)
    b.limb("hoof_fn", "knee_fn", 1.57, 9, 10, 9, HOOF)
    # --- tack on top ---
    rx, ry = b.on("rump")
    bx, by = b.on("barrel")
    mx, my = (rx + bx) / 2, (ry + by) / 2 - 26
    b.deco("saddle", "barrel", mx, my, 0.0, "poly",
           [(-16, -5), (16, -5), (13, 7), (-13, 7)], (98, 66, 44))
    b.deco("cantle", "saddle", mx - 12, my - 7, 0.0, "poly",
           [(-5, 0), (5, 0), (4, 7), (-4, 7)], (98, 66, 44))
    b.deco("pommel", "saddle", mx + 14, my - 7, 0.0, "circle", [], GOLD, 4.5)
    b.deco("bridle", "head", hx - 5, hy - 2, 0.0, "poly",
           [(0, -9), (3, -9), (3, 9), (0, 9)], (62, 46, 34))
    return b


def make_horse_rig(coat=None, trim=None, scale=1.0):
    # canvas half-extents: nose ~+112, tail ~-46, withers -84, hooves 0
    return _horse(coat, trim, scale).build(int(124 * scale), int(116 * scale))


STEEL_ARM_W = (11, 8)
LEG_W = (13, 10)
SHOULDER = (1.0, -74.0)
HIP = (0.0, -52.0)


def _human(scale, steel, steel_d, cloth, cloth_d, weapon, plume, shield,
           crest, lance):
    """Knight or guard. Feet y=0, head top ~y=-90. Faces +x."""
    b = Builder(scale)
    b.deco("root", None, 0, 0, 0.0, "circle", [], cloth, 1.0)
    # --- far arm + shield, behind the body ---
    b.link("arm_f", "root", (SHOULDER[0] - 4, SHOULDER[1]), 0.98, 19,
           *STEEL_ARM_W, steel_d)
    b.limb("fa_f", "arm_f", 1.02, 18, 8, 7, steel_d)
    if shield:
        hx, hy = b.on("fa_f")
        b.deco("shield", "fa_f", hx, hy, 0.0, "circle", [], cloth_d, 12.0)
    # --- far leg, a step behind ---
    b.link("thigh_f", "root", (HIP[0] - 4, HIP[1]), 1.46, 25, *LEG_W, cloth_d)
    b.limb("shin_f", "thigh_f", 1.80, 23, 10, 7, steel_d)
    b.limb("foot_f", "shin_f", 0.10, 10, 8, 5, (58, 46, 36))
    # --- torso: short and broad, so the head is not swallowed by it ---
    b.link("torso", "root", HIP, -1.5708, 26, 15, 17, cloth)
    b.deco("tabard", "torso", HIP[0], HIP[1], 1.5708, "poly",
           [(-7, -1), (7, -1), (8, 17), (-8, 17)], cloth_d)
    b.deco("belt", "torso", HIP[0], HIP[1] - 2, 1.5708, "poly",
           [(-10, -2), (10, -2), (10, 3), (-10, 3)], (82, 64, 44))
    sx, sy = b.on("torso")
    b.deco("gorget", "torso", sx, sy - 4, 0.0, "circle", [], steel_d, 5.5)
    b.deco("neck", "torso", sx, sy - 10, 0.0, "circle", [], steel_d, 4.0)
    # a helm is roughly as wide as it is tall: big enough to read as a head
    b.link("head", "neck", (sx + 1, sy - 11), -0.08, 17, 17, 14, steel)
    hx, hy = b.on("head")
    b.deco("visor", "head", hx + 7, hy + 1, -0.08, "poly",
           [(0, -1.6), (10, -2.2), (10, 1.6), (0, 1.6)], (20, 22, 30))
    b.deco("brow", "head", hx - 7, hy - 7, -0.08, "poly",
           [(-2, 0), (14, -3), (14, 2), (-2, 2)], _tone(steel, 1.20))
    b.deco("cheek", "head", hx - 7, hy + 5, -0.08, "poly",
           [(-2, -1), (10, -1), (9, 4), (-2, 4)], _tone(steel, 0.86))
    if crest:
        b.deco("crest", "head", hx - 5, hy - 7, -0.08, "poly",
               [(-3, 0), (6, -8), (16, -11), (7, -12), (-2, -6)], crest)
    if plume:
        b.deco("plume", "head", hx - 5, hy - 7, -0.08, "poly",
               [(-3, 0), (13, -5), (21, -16), (10, -13), (0, -5)], CRIMSON)
    # --- near leg + near arm, in front ---
    b.link("thigh", "root", HIP, 1.52, 25, 14, 11, cloth_d)
    b.limb("shin", "thigh", 1.74, 23, 11, 7, steel_d)
    b.limb("foot", "shin", 0.10, 11, 9, 5, (58, 46, 36))
    b.link("arm_n", "root", (SHOULDER[0] + 3, SHOULDER[1]), 0.90, 19,
           *STEEL_ARM_W, steel)
    b.limb("fa_n", "arm_n", 1.00, 18, 8, 7, steel)
    hx, hy = b.on("fa_n")
    if lance:
        # the shaft is a child of the forearm, so it inherits the whole arm's
        # angle; COUCH_* in rider_pose flattens it back to horizontal
        b.deco("lance", "fa_n", hx, hy, 0.02, "poly",
               [(-28, -2.4), (74, -2.4), (74, 2.4), (-28, 2.4)], WOOD)
        b.deco("grip", "lance", hx + 12, hy, 0.02, "poly",
               [(-2, -7), (8, -7), (8, 7), (-2, 7)], (150, 156, 168))
        b.deco("nave", "lance", hx + 74, hy, 0.02, "poly",
               [(0, -4.4), (18, 0), (0, 4.4)], (206, 212, 224))
    elif weapon == "sword":
        b.deco("hilt", "fa_n", hx, hy, 0.26, "poly",
               [(-3, -9), (3, -9), (3, 9), (-3, 9)], (90, 70, 48))
        b.deco("blade", "fa_n", hx, hy, 0.26, "poly",
               [(1, -3), (38, -3), (45, 0), (38, 3), (1, 3)], (226, 232, 242))
        b.deco("ricasso", "fa_n", hx + 1, hy, 0.26, "poly",
               [(0, -3), (5, -3), (5, 3), (0, 3)], (176, 182, 194))
    elif weapon == "spear":
        b.deco("shaft", "fa_n", hx, hy, 0.30, "poly",
               [(-18, -1.7), (56, -1.7), (56, 1.7), (-18, 1.7)], WOOD)
        b.deco("tip", "fa_n", hx + math.cos(0.30) * 56,
               hy + math.sin(0.30) * 56, 0.30, "poly",
               [(0, -3.8), (16, 0), (0, 3.8)], (200, 206, 216))
    return b


def make_human_rig(scale=1.0, steel=STEEL, steel_d=STEEL_D, cloth=CRIMSON,
                   cloth_d=CRIMSON_D, weapon="sword", plume=True, shield=True,
                   crest=None, lance=False):
    b = _human(scale, steel, steel_d, cloth, cloth_d, weapon, plume, shield,
               crest, lance)
    # the lance needs canvas room to the right; a bare knight does not
    reach = 132 if lance else 80
    return b.build(int(max(52, reach) * scale), int(112 * scale))


# --------------------------------------------------------------------------
# Poses
# --------------------------------------------------------------------------
# rest angles, spelled out so the pose deltas below read as intent
DOWN = 1.53
ARM_DOWN = 0.92
FORE_DOWN = 1.00

_RIDE = {
    "torso": 0.34, "neck": -0.22, "head": -0.10,
    "arm_f": -0.30, "fa_f": -0.55,
    "arm_n": -0.42, "fa_n": -0.50,
    "thigh": -0.35, "shin": 0.55, "foot": 0.22,
    "thigh_f": -0.30, "shin_f": 0.50, "foot_f": 0.20,
    "plume": -0.25, "crest": -0.20,
}
_FOOT = {
    "torso": 0.06, "neck": 0.0, "head": 0.0,
    "arm_f": 0.06, "fa_f": -0.18,
    "arm_n": 0.08, "fa_n": -0.16,
    "thigh": 0.0, "shin": -0.30, "foot": 0.0,
    "thigh_f": 0.0, "shin_f": -0.26, "foot_f": 0.0,
    "plume": 0.0, "crest": 0.0,
}
LANCE_REST = 0.02
COUCH_ARM_N, COUCH_FA_N = -0.16, 0.30


def horse_pose(speed, phase, air=0.0, panic=0.0):
    """One gallop/trot cycle. Front and hind use different phase groups and all
    knees fold backward, which is what reads as a horse rather than a dog."""
    p = TAU * phase
    a = {}
    amp = min(0.80, 0.22 + speed / 230.0) * (1 - air)
    drive = 0.30 + 0.70 * min(1.0, speed / 190.0)
    gallop = min(1.0, speed / 150.0) * (1 - panic * 0.4)
    for hip, knee, hoof, off, near in (
        ("leg_hn", "knee_hn", "hoof_hn", 0.52, True),
        ("leg_hf", "knee_hf", "hoof_hf", 0.60, False),
        ("leg_fn", "knee_fn", "hoof_fn", 0.02, True),
        ("leg_ff", "knee_ff", "hoof_ff", 0.10, False),
    ):
        u = p + TAU * off
        swing = math.sin(u) * amp
        fold = (0.18 + 0.90 * max(0.0, math.sin(u - 1.0)) * drive) * (1 - air)
        a[hip] = -swing + air * (0.9 if near else -0.5)
        a[knee] = fold
        a[hoof] = -fold * 0.9
    a["body"] = -0.07 * gallop + 0.05 * math.sin(p + 0.8) * gallop
    a["chest"] = 0.05 * math.sin(p + 1.1) * gallop
    a["neck"] = (0.34 * gallop + 0.08 * math.sin(p + 1.2) + panic * 0.20)
    a["crest"] = -0.10 * gallop
    a["head"] = 0.10 * math.sin(p + 1.0) - 0.14 * gallop + panic * 0.10
    a["tail"] = 0.26 * math.sin(p * 0.5 + 0.4) - 0.08 + panic * 0.40
    a["tail2"] = 0.20 * math.sin(p * 0.5 + 1.1) + panic * 0.32
    a["mane"] = 0.05 * math.sin(p + 0.3)
    a["forelock"] = 0.06 * math.sin(p * 2 + 0.6)
    bob = -(1.0 + 3.4 * gallop) * abs(math.sin(p + 0.45)) * (1 - air)
    return a, (-5.5 * air if air else bob)


def rider_pose(phase, riding=1.0, moving=0.0, air=0.0, attack=0.0, reach=0.0):
    """Blend the mounted pose (riding=1) into an on-foot run/strike (riding=0).

    -> (angles, hip_lift). hip_lift raises the whole rider, which is how the
    mounted pose clears the horse's back.
    """
    p = TAU * phase
    a = dict(_RIDE if riding > 0.5 else _FOOT)
    sw, sw2 = math.sin(p) * moving, math.sin(p + math.pi) * moving

    if riding > 0.5:
        a["thigh"] += 0.09 * sw
        a["shin"] -= 0.13 * sw
        a["thigh_f"] += 0.09 * sw2
        a["shin_f"] -= 0.13 * sw2
        a["torso"] += 0.10 * moving
        lift = -3.0 + 0.9 * math.sin(p * 2) * moving
    else:
        # two legs, counter-phased: a run cycle, not a scissor
        a["thigh"] += 0.60 * sw
        a["shin"] -= 1.10 * max(0.0, -sw2) - 0.20 * abs(sw)
        a["foot"] += 0.26 * sw
        a["thigh_f"] += 0.55 * sw2
        a["shin_f"] -= 1.05 * max(0.0, -sw) - 0.18 * abs(sw2)
        a["foot_f"] += 0.24 * sw2
        a["torso"] += 0.05 * moving - 0.12 * air
        a["arm_f"] += 0.42 * sw2
        a["arm_n"] += -0.38 * sw
        a["fa_n"] += 0.20 * sw
        lift = -abs(math.sin(p)) * 1.9 * moving - 5.0 * air

    if reach > 0.0:
        # lance couched under the arm: the shaft's world angle is
        # arm + forearm + LANCE_REST, so both arms are aimed to flatten it.
        a["arm_n"] = lerp(a["arm_n"], COUCH_ARM_N, reach)
        a["fa_n"] = lerp(a["fa_n"], COUCH_FA_N, reach)
        a["arm_f"] = lerp(a["arm_f"], -0.34, reach)
        a["fa_f"] = lerp(a["fa_f"], 0.28, reach)
        a["torso"] += -0.06 * reach
    elif attack > 0.0:
        k = ease(1.0 - attack)  # 0 at the start of the swing, 1 when recovered
        a["arm_n"] = lerp(-1.05, 1.25, k)
        a["fa_n"] = lerp(0.75, -0.05, k)
        a["torso"] += 0.24 * math.sin(k * math.pi) * (1.0 - riding * 0.35)
        a["head"] += 0.12 * (1.0 - k)
    return a, lift