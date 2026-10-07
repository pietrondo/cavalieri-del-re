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
OUTLINE_W = 2.0  # outline thickness, in supersampled units: ~0.7px on screen


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
                lx, ly, la = j.x, j.y, j.ang
            else:
                # Rest angles are authored ABSOLUTE (see Bone.ang). solve() adds
                # a bone's angle to its parent's, so store the LOCAL delta here
                # or every chained bone renders rotated by its parent's angle.
                p = rest[j.parent]
                pa = p.ang
                c, s = math.cos(-pa), math.sin(-pa)
                dx, dy = j.x - p.x, j.y - p.y
                lx, ly = dx * c - dy * s, dx * s + dy * c
                la = j.ang - pa
            b = Draw(j.name, j.parent, lx, ly, la, j.length, j.w0, j.w1,
                     j.color, j.shape, j.pts)
            self.bones.append(b)
            self.map[j.name] = b
        self.w, self.h = w, h
        self._check(rest)

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
    pygame.draw.polygon(surf, outline, pts, int(OUTLINE_W * SS * 0.6))
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
    # a dark outline in the limb's own hue: without it a limb is a smear of the
    # same colour as the body next to it, and the figure stops reading.
    outline = _tone(_mix(b.color, (16, 14, 22), 0.74), dark)

    if b.shape == "poly":
        c, s = math.cos(ga), math.sin(ga)
        pts = [((gx + px * c - py * s) * SS, (gy + px * s + py * c) * SS)
               for px, py in b.pts]
        _shade_poly(surf, pts, base, outline)
        return

    if b.shape == "circle":
        r = max(1.0, b.length)
        pygame.draw.circle(surf, outline, (int(gx * SS), int(gy * SS)),
                           int((r + OUTLINE_W) * SS))
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
    ow = OUTLINE_W
    pygame.draw.polygon(surf, outline, quad(r0 + ow, r1 + ow, 0.0))
    pygame.draw.circle(surf, outline, (int(gx * SS), int(gy * SS)),
                       int((r0 + ow) * SS))
    pygame.draw.circle(surf, outline, (int(ex * SS), int(ey * SS)),
                       int((r1 + ow) * SS))
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
    # Most geometry is above the feet anchor. Keep enough room for hooves and
    # airborne poses below it, instead of supersampling an empty lower half.
    ground_pad = max(24, int(rig.h * .18))
    out_h = rig.h + ground_pad
    surf = pygame.Surface((rig.w * 2 * SS, out_h * SS), pygame.SRCALPHA)
    for b in rig.bones:
        if b.name == "root":
            continue  # FK anchor, not a visible piece of the character.
        gx, gy, ga = tr[b.name]
        _draw(surf, b, gx + rig.w, gy + rig.h, ga, dark,
              0.75 if b.name in occluded else 0.0)
    out = pygame.transform.smoothscale(surf, (rig.w * 2, out_h))
    if flip:
        out = pygame.transform.flip(out, True, False)
    return _contour(out), tr


CONTOUR_R = 1  # px of dark ring added around the whole silhouette


def _contour(img):
    """A single dark ring around the whole figure, so the cast separates from
    the background. The per-bone outline still separates limbs from each other;
    this one is only for the outer edge, which per-bone outlines cannot give."""
    halo = img.copy()
    halo.fill((10, 9, 15, 255), special_flags=pygame.BLEND_RGBA_MULT)
    out = pygame.Surface(img.get_size(), pygame.SRCALPHA)
    r = CONTOUR_R
    for dx, dy in ((-r, 0), (r, 0), (0, -r), (0, r)):
        out.blit(halo, (dx, dy))
    out.blit(img, (0, 0))
    return out


# bones that belong to the far side of the body, per rig kind
HORSE_FAR = ("tail", "tail2", "leg_hf", "knee_hf", "hoof_hf",
             "leg_ff", "knee_ff", "hoof_ff", "cloth", "trim")
HUMAN_FAR = ("arm_f", "fa_f", "shield", "thigh_f", "shin_f", "foot_f")


def render_horse(rig, angles, root, dark=1.0, flip=False):
    return render(rig, angles, root, dark, flip, HORSE_FAR)


def render_human(rig, angles, root, dark=1.0, flip=False):
    return render(rig, angles, root, dark, flip, HUMAN_FAR)


def blit(surf, img, rig, x, y):
    """Blit with the feet point at world (x, y). render() mirrors the image
    about its own centre, so the feet stay at x=rig.w and the offset is the
    same whichever way the sprite faces."""
    surf.blit(img, (int(x - rig.w), int(y - rig.h)))


# --------------------------------------------------------------------------
# Palettes
# --------------------------------------------------------------------------
STEEL = (178, 188, 202)
STEEL_D = (114, 124, 142)
CRIMSON = (196, 62, 62)
CRIMSON_D = (122, 26, 30)
GOLD = (216, 178, 76)
OCHRE = (156, 130, 68)
OCHRE_D = (116, 94, 48)
HORSE = (126, 78, 48)
HORSE_D = (83, 49, 32)
MANE = (40, 30, 24)
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
        s = self.scale
        x, y = at[0] + math.cos(ang) * length, at[1] + math.sin(ang) * length
        # the scale applies to the GEOMETRY (positions, lengths, thickness),
        # never to the canvas: scaling the rendered image would blur it.
        b = Bone(name, parent, at[0] * s, at[1] * s, ang, length * s,
                 w0 * s, w1 * s, color, "limb", scale=s)
        self.j.append(b)
        self.pos[name] = (x, y)      # kept UNSCALED for chaining
        return self

    def limb(self, name, parent, ang, length, w0, w1, color):
        """Chain a limb onto its parent's tip. This is the only kind of bone
        that is required to reach its child - decorations may hang anywhere."""
        self.link(name, parent, self.pos[parent], ang, length, w0, w1, color)
        self.j[-1].chain = True
        return self

    def deco(self, name, parent, x, y, ang, shape, pts, color, size=0.0):
        s = self.scale
        self.j.append(Bone(name, parent, x * s, y * s, ang, size * s, 0, 0,
                           color, shape, [(px * s, py * s) for px, py in pts],
                           scale=s))
        self.pos[name] = (x, y)
        return self

    def on(self, name):
        return self.pos[name]

    def build(self, w, h):
        return Rig(self.j, w, h)


def _horse(coat=None, trim=None, scale=1.0):
    """Bay warhorse. Feet y=0, back (withers) y~-84, muzzle forward. Faces +x."""
    # legs are a value darker than the barrel on purpose: same-colour legs melt
    # into the body and the whole horse reads as one stone.
    far, near = _tone(HORSE, 0.58), HORSE_D
    b = Builder(scale)
    b.deco("root", None, 0, 0, 0.0, "circle", [], HORSE, 1.0)
    # --- behind the horse ---
    b.link("tail", "root", (-52, -74), 2.45, 18, 13, 9, HORSE_D)
    b.limb("tail2", "tail", 2.10, 22, 9, 6, MANE)
    b.limb("tail3", "tail2", 1.85, 22, 6, 3, MANE)
    # --- far legs: the barrel covers them, so they read as depth ---
    b.link("leg_hf", "root", (-42, -57), 2.02, 29, 19, 11, far)
    b.limb("knee_hf", "leg_hf", 1.25, 32.5, 11, 7, far)
    b.limb("hoof_hf", "knee_hf", 0.20, 11, 10, 5, HOOF)
    b.link("leg_ff", "root", (22, -60), 1.27, 28, 18, 11, far)
    b.limb("knee_ff", "leg_ff", 1.78, 34, 10, 7, far)
    b.limb("hoof_ff", "knee_ff", 0.12, 11, 10, 5, HOOF)
    # --- barrel: deep enough that the legs do not read as stilts ---
    b.link("rump", "root", (-56, -69), 0.08, 31, 38, 40, HORSE)
    b.limb("barrel", "rump", -0.04, 42, 40, 37, HORSE)
    b.limb("chest", "barrel", -0.12, 25, 37, 30, HORSE)
    # --- neck rises thick from the chest and tapers to a small head ---
    b.limb("neck", "chest", -0.87, 35, 28, 15, HORSE)
    b.limb("crest", "neck", -0.48, 14, 17, 12, HORSE)
    b.limb("head", "crest", 0.46, 24, 16, 11, HORSE)
    hx, hy = b.on("head")
    b.deco("muzzle", "head", hx + 1, hy + 3, 0.0, "circle", [], (80, 62, 53),
           7.0)
    b.deco("nostril", "muzzle", hx + 5, hy + 1, 0.0, "circle", [], (26, 20, 18),
           1.6)
    b.deco("jaw", "head", hx - 10, hy + 5, 0.0, "poly",
           [(-8, -3), (9, -4), (13, 3), (1, 8), (-8, 5)], HORSE_D)
    b.deco("eye", "head", hx - 11, hy - 7, 0.0, "circle", [], (16, 12, 10), 2.5)
    b.deco("brow", "head", hx - 12, hy - 9, 0.0, "circle", [], (176, 117, 72), 1.8)
    b.deco("ear_a", "head", hx - 21, hy - 10, 0.0, "poly",
           [(-3, 3), (-6, -13), (2, -9), (6, 2)], HORSE_D)
    b.deco("ear_b", "head", hx - 16, hy - 10, 0.0, "poly",
           [(-3, 3), (-4, -11), (3, -8), (5, 2)], HORSE_D)
    b.deco("forelock", "head", hx - 21, hy - 8, 0.0, "poly",
           [(-7, 3), (-5, -6), (5, -4), (12, 2), (3, 0)], MANE)
    nx, ny = b.on("chest")   # the mane runs along the whole neck, from the base
    b.deco("mane", "neck", nx, ny, -0.80, "poly",
           [(-2, 2), (10, -5), (24, -6), (34, -4), (40, -1),
            (34, 1), (22, 2), (-2, 4)], MANE)
    if coat:
        # caparison: a blanket lying on the back, not a skirt over the legs
        rx, ry = b.on("rump")
        cx, cy = b.on("chest")
        mx, my = (rx + cx) / 2, (ry + cy) / 2 - 12
        b.deco("cloth", "barrel", mx, my, 0.06, "poly",
               [(-38, -3), (38, -3), (35, 15), (12, 12), (-12, 15), (-38, 14)],
               coat)
        b.deco("trim", "cloth", mx, my + 12, 0.06, "poly",
               [(-36, -3), (36, -3), (36, 3), (-36, 3)], trim or GOLD)
    # --- near legs, in front of the barrel ---
    b.link("leg_hn", "root", (-36, -57), 2.02, 29, 20, 12, near)
    b.limb("knee_hn", "leg_hn", 1.25, 32.5, 12, 7, near)
    b.limb("hoof_hn", "knee_hn", 0.20, 11, 11, 5, HOOF)
    b.link("leg_fn", "root", (30, -60), 1.27, 28, 19, 11, near)
    b.limb("knee_fn", "leg_fn", 1.78, 34, 11, 7, near)
    b.limb("hoof_fn", "knee_fn", 0.12, 11, 11, 5, HOOF)
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
    # Canvas headroom also covers the nose during the forward gallop phase.
    return _horse(coat, trim, scale).build(int(145 * scale), int(145 * scale))


STEEL_ARM_W = (13, 9)
LEG_W = (14, 11)
SHOULDER = (1.0, -78.0)
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
        # a rim + boss, so it reads as a shield and not as a plain ball
        hx, hy = b.on("fa_f")
        b.deco("shield_rim", "fa_f", hx, hy, 0.0, "poly",
               [(-12, -14), (9, -12), (12, 3), (2, 20), (-11, 7)],
               (52, 34, 34))
        b.deco("shield", "fa_f", hx, hy, 0.0, "poly",
               [(-9, -11), (7, -10), (9, 3), (2, 16), (-8, 6)], cloth_d)
        b.deco("boss", "fa_f", hx, hy, 0.0, "circle", [], _tone(steel, 0.9),
               4.0)
    # --- far leg, a step behind ---
    b.link("thigh_f", "root", (HIP[0] - 4, HIP[1]), 1.46, 25, *LEG_W, cloth_d)
    b.limb("shin_f", "thigh_f", 1.80, 23, 10, 7, steel_d)
    b.limb("foot_f", "shin_f", 0.10, 10, 8, 5, (58, 46, 36))
    # --- torso: narrow hips, broad shoulders, so the head is not swallowed ---
    b.link("torso", "root", HIP, -1.5708, 30, 14, 18, cloth)
    b.deco("tabard", "torso", HIP[0], HIP[1], 1.5708, "poly",
           [(-7, -1), (7, -1), (8, 17), (-8, 17)], cloth_d)
    b.deco("belt", "torso", HIP[0], HIP[1] - 2, 1.5708, "poly",
           [(-10, -2), (10, -2), (10, 3), (-10, 3)], (82, 64, 44))
    sx, sy = b.on("torso")
    b.deco("gorget", "torso", sx, sy - 4, 0.0, "circle", [], steel_d, 5.5)
    b.deco("neck", "torso", sx, sy - 10, 0.0, "circle", [], steel_d, 4.0)
    # a helm is roughly as wide as it is tall: big enough to read as a head
    b.link("head", "neck", (sx + 1, sy - 11), -1.28, 17, 18, 14, steel)
    hx, hy = b.on("head")
    # the helm must read as a HEAD, so the face stays light: a short eye slit
    # at the FRONT and a small breath slit. A slit as long as the helm, or a
    # big dark visor, turns the head into a black box.
    b.deco("visor", "head", hx + 1, hy + 8, 0.0, "poly",
           [(-7, -2), (8, -2), (8, 1), (-7, 1)], (18, 20, 28))
    b.deco("breathe", "head", hx + 2, hy + 14, 0.0, "poly",
           [(-2, -2), (2, -2), (3, 4), (-2, 4)], (26, 28, 36))
    b.deco("brow", "head", hx, hy + 3, 0.0, "poly",
           [(-6, 0), (7, -2), (9, 1), (-6, 3)], _tone(steel, 1.20))
    if crest:
        b.deco("crest", "head", hx - 4, hy - 1, 0.0, "poly",
               [(-3, 2), (2, -8), (12, -11), (5, -12), (-5, -5)], crest)
    if plume:
        # the plume is the knight's landmark: in silhouette it must break the
        # head shape, otherwise a rider is just a bump on the horse's back.
        b.deco("plume", "head", hx - 5, hy - 1, 0.0, "poly",
               [(0, 2), (11, -5), (25, -12), (31, -24), (19, -20),
                (7, -10), (-4, -1)], CRIMSON)
    # --- near leg + near arm, in front ---
    b.link("thigh", "root", HIP, 1.52, 25, 14, 11, cloth_d)
    b.limb("shin", "thigh", 1.74, 23, 11, 7, steel_d)
    b.limb("foot", "shin", 0.10, 11, 9, 5, (58, 46, 36))
    b.link("arm_n", "root", (SHOULDER[0] + 3, SHOULDER[1]), 0.90, 19,
           *STEEL_ARM_W, steel)
    b.limb("fa_n", "arm_n", 1.00, 18, 8, 7, steel)
    # pauldrons, drawn last so they sit over the shoulders: without them the
    # arms leave the body at a bare joint and the figure looks like a stick.
    b.deco("pauldron_n", "torso", SHOULDER[0] + 3, SHOULDER[1] + 2, 0.0,
           "circle", [], steel, 7.0)
    b.deco("pauldron_f", "torso", SHOULDER[0] - 6, SHOULDER[1] + 2, 0.0,
           "circle", [], steel_d, 6.5)
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
        b.deco("pommel", "fa_n", hx - 5, hy, 0.26, "circle", [],
               GOLD, 3.2)
        b.deco("hilt", "fa_n", hx, hy, 0.26, "poly",
               [(-3, -2), (3, -2), (3, 2), (-3, 2)], (90, 70, 48))
        b.deco("guard", "fa_n", hx + 1, hy, 0.26, "poly",
               [(-2, -10), (3, -10), (3, 10), (-2, 10)],
               GOLD if (plume or crest) else STEEL)
        b.deco("blade", "fa_n", hx, hy, 0.26, "poly",
               [(2, -3.2), (40, -3.2), (48, 0), (40, 3.2), (2, 3.2)], (236, 240, 248))
        b.deco("fuller", "fa_n", hx + 2, hy, 0.26, "poly",
               [(0, -0.8), (30, -0.8), (30, 0.8), (0, 0.8)], (172, 180, 194))
        b.deco("ricasso", "fa_n", hx + 1, hy, 0.26, "poly",
               [(0, -3), (5, -3), (5, 3), (0, 3)], (188, 194, 204))
        b.deco("hand", "fa_n", hx, hy, 0.26, "circle", [],
               _tone(steel_d, 0.85), 5.0)
    elif weapon == "spear":
        b.deco("shaft", "fa_n", hx, hy, 0.30, "poly",
               [(-18, -1.7), (56, -1.7), (56, 1.7), (-18, 1.7)], WOOD)
        b.deco("tip", "fa_n", hx + math.cos(0.30) * 56,
               hy + math.sin(0.30) * 56, 0.30, "poly",
               [(0, -3.8), (16, 0), (0, 3.8)], (200, 206, 216))
        b.deco("hand", "fa_n", hx, hy, 0.30, "circle", [],
               _tone(steel_d, 0.85), 5.0)
    return b


def make_human_rig(scale=1.0, steel=STEEL, steel_d=STEEL_D, cloth=CRIMSON,
                   cloth_d=CRIMSON_D, weapon="sword", plume=True, shield=True,
                   crest=None, lance=False):
    b = _human(scale, steel, steel_d, cloth, cloth_d, weapon, plume, shield,
               crest, lance)
    # the lance needs canvas room to the right; the plume room above
    reach = 150 if lance else 110
    return b.build(int(max(52, reach) * scale), int(205 * scale))


# --------------------------------------------------------------------------
# Poses
# --------------------------------------------------------------------------
# rest angles, spelled out so the pose deltas below read as intent
DOWN = 1.53
ARM_DOWN = 0.92
FORE_DOWN = 1.00

_RIDE = {
    "torso": 0.05, "neck": -0.12, "head": -0.06,
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
    """Four offset leg cycles: hind push, suspension, fore reach and gather."""
    p = TAU * phase
    a = {}
    motion = min(1.0, max(0.0, speed) / 7.0) * (1 - air)
    gallop = min(1.0, max(0.0, speed) / 6.0) * (1 - panic * 0.4)
    for hip, knee, hoof, off, hind in (
        ("leg_hn", "knee_hn", "hoof_hn", 0.54, True),
        ("leg_hf", "knee_hf", "hoof_hf", 0.72, True),
        ("leg_fn", "knee_fn", "hoof_fn", 0.00, False),
        ("leg_ff", "knee_ff", "hoof_ff", 0.18, False),
    ):
        u = p + TAU * off
        swing = math.sin(u)
        gather = max(0.0, math.cos(u - 0.55))
        a[hip] = motion * (-0.72 * swing + (0.13 if hind else -0.10))
        a[knee] = motion * ((-0.80 if hind else 0.95) * gather)
        a[hoof] = motion * (0.20 * swing - 0.28 * gather)
        if air:
            a[hip] += air * (0.45 if hind else -0.5)
            a[knee] += air * (-0.35 if hind else 0.55)
    a["rump"] = -0.07 * gallop + 0.05 * math.sin(p + 0.8) * gallop
    a["chest"] = 0.05 * math.sin(p + 1.1) * gallop
    a["neck"] = (0.16 * gallop + 0.06 * math.sin(p + 1.2) * motion + panic * 0.20)
    a["crest"] = -0.10 * gallop
    a["head"] = 0.10 * math.sin(p + 1.0) - 0.14 * gallop + panic * 0.10
    a["tail"] = 0.26 * math.sin(p * 0.5 + 0.4) - 0.08 + panic * 0.40
    a["tail2"] = 0.20 * math.sin(p * 0.5 + 1.1) + panic * 0.32
    a["mane"] = 0.05 * math.sin(p + 0.3)
    a["forelock"] = 0.06 * math.sin(p * 2 + 0.6)
    bob = -3.2 * gallop * abs(math.sin(p + 0.45)) * (1 - air)
    return a, (-5.5 * air if air else bob)


def rider_pose(phase, riding=1.0, moving=0.0, air=0.0, attack=0.0, reach=0.0):
    """Blend the mounted pose (riding=1) into an on-foot run/strike (riding=0).

    -> (angles, hip_lift). hip_lift raises the whole rider, which is how the
    mounted pose clears the horse's back.
    """
    p = TAU * phase
    riding = max(0.0, min(1.0, riding))
    a = {name: lerp(_FOOT[name], _RIDE[name], riding) for name in _RIDE}
    sw, sw2 = math.sin(p) * moving, math.sin(p + math.pi) * moving

    # Blend the motion as well as the rest stance. A threshold here made the
    # feet jump midway through mount/dismount despite the interpolated seat.
    foot_motion = {
        "thigh": 0.60 * sw,
        "shin": -1.10 * max(0.0, -sw2) - 0.20 * abs(sw),
        "foot": 0.26 * sw,
        "thigh_f": 0.55 * sw2,
        "shin_f": -1.05 * max(0.0, -sw) - 0.18 * abs(sw2),
        "foot_f": 0.24 * sw2,
        "torso": 0.05 * moving - 0.12 * air,
        "arm_f": 0.42 * sw2,
        "arm_n": -0.38 * sw,
        "fa_n": 0.20 * sw,
    }
    ride_motion = {
        "thigh": 0.09 * sw,
        "shin": -0.13 * sw,
        "thigh_f": 0.09 * sw2,
        "shin_f": -0.13 * sw2,
        "torso": 0.10 * moving,
    }
    for name in foot_motion.keys() | ride_motion.keys():
        a[name] += lerp(foot_motion.get(name, 0.0),
                        ride_motion.get(name, 0.0), riding)
    foot_lift = -abs(math.sin(p)) * 1.9 * moving - 5.0 * air
    ride_lift = -3.0 + 0.9 * math.sin(p * 2) * moving
    lift = lerp(foot_lift, ride_lift, riding)

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
        base_arm = a["arm_n"]
        base_fa = a["fa_n"]
        if k < 0.28:
            u = ease(k / 0.28)
            # Windup: sword raised up and back ready to strike
            a["arm_n"] = lerp(base_arm, -1.35, u)
            a["fa_n"] = lerp(base_fa, 0.40, u)
            a["torso"] += lerp(0.0, -0.10, u)
            a["head"] += lerp(0.0, -0.06, u)
        elif k < 0.68:
            u = ease((k - 0.28) / 0.40)
            # Forward horizontal slash through enemy chest/torso
            a["arm_n"] = lerp(-1.35, -0.28, u)
            a["fa_n"] = lerp(0.40, 0.15, u)
            a["torso"] += lerp(-0.10, 0.20, u) * (1.0 - riding * 0.35)
            a["head"] += lerp(-0.06, 0.10, u)
        else:
            u = ease((k - 0.68) / 0.32)
            # Recovery: smoothly return to ready stance
            a["arm_n"] = lerp(-0.28, base_arm, u)
            a["fa_n"] = lerp(0.15, base_fa, u)
            a["torso"] += lerp(0.20, 0.0, u) * (1.0 - riding * 0.35)
            a["head"] += lerp(0.10, 0.0, u)
    return a, lift


def dead_pose(progress, on_horse=False):
    """Death collapse: actor falls back, knees buckle, body rests on the ground."""
    p = ease(min(1.0, progress / 0.55))
    a = {
        "torso": lerp(0.06, -1.15, p),
        "neck": lerp(0.0, -0.25, p),
        "head": lerp(0.0, -0.45, p),
        "arm_n": lerp(0.08, 0.82, p),
        "fa_n": lerp(-0.16, 0.28, p),
        "arm_f": lerp(0.06, 0.68, p),
        "fa_f": lerp(-0.18, 0.22, p),
        "thigh": lerp(0.0, 0.48, p),
        "shin": lerp(-0.30, -1.05, p),
        "foot": lerp(0.0, 0.30, p),
        "thigh_f": lerp(0.0, 0.32, p),
        "shin_f": lerp(-0.26, -0.92, p),
        "foot_f": lerp(0.0, 0.25, p),
        "plume": lerp(0.0, -0.40, p),
        "crest": lerp(0.0, -0.30, p),
    }
    lift = 25.0 * p
    return a, lift
