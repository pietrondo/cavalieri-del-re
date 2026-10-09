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

import functools
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


@functools.lru_cache(maxsize=8192)
def _tone(c, f):
    return (max(0, min(255, int(c[0] * f))),
            max(0, min(255, int(c[1] * f))),
            max(0, min(255, int(c[2] * f))))


def _tint(c, k, f):
    """Blend toward k (a 0..1 grey-blue) while scaling brightness by f."""
    return tuple(max(0, min(255, int(c[i] * f * (1 - k) + k * 232 * f)))
                 for i in range(3))


@functools.lru_cache(maxsize=8192)
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
    for cut, col in ((0.14, _tone(base, 1.10)),
                     (0.44, _tone(base, 1.18)),
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
    internal_starts = {"barrel", "chest", "crest", "head", "fa_n", "fa_f",
                       "knee_hn", "knee_hf", "knee_fn", "knee_ff",
                       "shin", "shin_f", "tail2", "tail3"}
    internal_ends = {"rump", "barrel", "neck", "crest", "arm_n", "arm_f",
                     "leg_hn", "leg_hf", "leg_fn", "leg_ff",
                     "thigh", "thigh_f", "tail", "tail2"}
    if b.name not in internal_starts:
        pygame.draw.circle(surf, outline, (int(gx * SS), int(gy * SS)),
                           int((r0 + ow) * SS))
    if b.name not in internal_ends:
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


_RENDER_CACHE = {}
_CACHE_MAX = 768
# Angles are snapped to this step before the cache lookup. 0.02 rad is ~1 px at
# the tip of a limb: invisible on screen, but it turns a continuous animation
# into a finite set of poses, so the cache actually gets hits.
ANGLE_STEP = 0.02


def clear_cache():
    _RENDER_CACHE.clear()


def render(rig, angles=None, root=(0.0, 0.0), dark=1.0, flip=False,
           occluded=()):
    """-> (surface, transform). Inside the image the entity's feet point sits at
    (rig.w, rig.h); everything above it is headroom.

    `occluded` names bones to push back (far-side legs, the far arm): they get
    darkened and desaturated so depth reads without any real lighting.
    """
    if angles:
        angles = {k: round(v / ANGLE_STEP) * ANGLE_STEP for k, v in angles.items()}
        ka = tuple(sorted(angles.items()))
    else:
        ka = ()
    kr = (round(root[0], 1), round(root[1], 1))
    key = (id(rig), ka, kr, round(dark, 2), flip, occluded)
    hit = _RENDER_CACHE.get(key)
    if hit is not None:
        return hit

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
    res = (_contour(out), tr)
    if len(_RENDER_CACHE) >= _CACHE_MAX:
        _RENDER_CACHE.clear()
    _RENDER_CACHE[key] = res
    return res


CONTOUR_R = 1  # px of dark ring added around the whole silhouette
# the silhouette copied and subtracted back out along this vector leaves a
# crescent on the lower-right: the side the dusk horizon is on
RIM_OFF = (-2, -1)
RIM_WARM = (255, 148, 88)


def _contour(img):
    """A single dark ring around the whole figure, so the cast separates from
    the background. The per-bone outline still separates limbs from each other;
    this one is only for the outer edge, which per-bone outlines cannot give.

    On top of it, a warm crescent on the horizon side. Shading inside a bone is
    built from one fixed cool key light; without the dusk coming back off the
    sky the cast reads as a cut-out laid on the road instead of standing in it.
    """
    halo = img.copy()
    halo.fill((10, 9, 15, 255), special_flags=pygame.BLEND_RGBA_MULT)
    out = pygame.Surface(img.get_size(), pygame.SRCALPHA)
    r = CONTOUR_R
    for dx, dy in ((-r, 0), (r, 0), (0, -r), (0, r)):
        out.blit(halo, (dx, dy))
    out.blit(img, (0, 0))
    rim = img.copy()
    rim.blit(img, RIM_OFF, special_flags=pygame.BLEND_RGBA_SUB)
    rim.fill((*RIM_WARM, 255), special_flags=pygame.BLEND_RGBA_MULT)
    out.blit(rim, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
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


def _ell(rx, ry, n=12, y0=0.0):
    """Points of an ellipse centred on (0, y0): smooth shading on a bone."""
    return [(rx * math.cos(math.tau * i / n), y0 + ry * math.sin(math.tau * i / n))
            for i in range(n)]


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
    b.limb("knee_hf", "leg_hf", 1.25, 32.5, 10, 6, far)
    b.limb("hoof_hf", "knee_hf", 0.20, 11, 10, 5, HOOF)
    b.link("leg_ff", "root", (22, -60), 1.27, 28, 18, 11, far)
    b.limb("knee_ff", "leg_ff", 1.78, 34, 10, 6, far)
    b.limb("hoof_ff", "knee_ff", 0.12, 11, 10, 5, HOOF)
    # --- barrel: deep enough that the legs do not read as stilts ---
    b.link("rump", "root", (-56, -69), 0.08, 31, 38, 40, HORSE)
    b.limb("barrel", "rump", -0.04, 42, 40, 37, HORSE)
    b.limb("chest", "barrel", -0.12, 25, 37, 30, HORSE)
    rx, ry = b.on("rump")
    cx, cy = b.on("chest")
    b.deco("croup_curve", "rump", rx + 4, ry - 2, 0.0, "poly",
           _ell(11, 9), _tone(HORSE, 1.12))
    b.deco("flank_shade", "barrel", rx + 30, ry + 10, 0.0, "poly",
           _ell(12, 7), _tone(HORSE, 0.86))
    b.deco("chest_contour", "chest", cx + 6, cy + 2, 0.0, "poly",
           _ell(9, 11), _tone(HORSE, 1.08))
    # volume: luce lungo il dorso, ombra sotto la pancia. Senza, il busto e'
    # un cilindro di un colore solo.
    mx_, my_ = (rx + cx) / 2, (ry + cy) / 2
    b.deco("back_hi", "barrel", mx_, my_ - 15, 0.0, "poly",
           _ell(24, 4), _tone(HORSE, 1.24))
    b.deco("belly_shade", "barrel", mx_, my_ + 17, 0.0, "poly",
           _ell(26, 5), _tone(HORSE, 0.72))
    # --- neck rises thick from the chest and tapers to a small head ---
    b.limb("neck", "chest", -0.87, 35, 28, 15, HORSE)
    b.limb("crest", "neck", -0.48, 14, 17, 12, HORSE)
    b.limb("head", "crest", 0.46, 27, 19, 12, HORSE)
    hx, hy = b.on("head")
    b.deco("muzzle", "head", hx + 1, hy + 3, 0.0, "circle", [], (70, 52, 44), 7.0)
    b.deco("muzzle_lip", "head", hx + 3, hy + 5, 0.0, "poly",
           [(-3, -2), (4, -2), (3, 2), (-3, 2)], (48, 34, 28))
    b.deco("nostril", "muzzle", hx + 5, hy + 1, 0.0, "circle", [], (20, 15, 13), 1.8)
    b.deco("jaw", "head", hx - 10, hy + 5, 0.0, "poly",
           [(-8, -3), (9, -4), (13, 3), (1, 8), (-8, 5)], HORSE_D)
    b.deco("jaw_hi", "head", hx - 8, hy + 3, 0.0, "poly",
           [(-5, -2), (7, -3), (10, 2), (0, 5), (-5, 3)], _tone(HORSE, 1.15))
    b.deco("eye", "head", hx - 11, hy - 7, 0.0, "circle", [], (18, 14, 12), 2.8)
    b.deco("eye_shine", "head", hx - 10, hy - 8, 0.0, "circle", [], (255, 255, 255), 0.9)
    b.deco("brow", "head", hx - 12, hy - 9, 0.0, "circle", [], (185, 122, 76), 2.0)
    b.deco("ear_a", "head", hx - 21, hy - 10, 0.0, "poly",
           [(-3, 3), (-7, -14), (2, -10), (6, 2)], HORSE_D)
    b.deco("ear_a_in", "head", hx - 20, hy - 11, 0.0, "poly",
           [(-2, 2), (-5, -11), (0, -8), (4, 1)], (148, 98, 65))
    b.deco("ear_b", "head", hx - 16, hy - 10, 0.0, "poly",
           [(-3, 3), (-5, -12), (3, -9), (5, 2)], HORSE_D)
    b.deco("forelock", "head", hx - 21, hy - 8, 0.0, "poly",
           [(-7, 3), (-5, -7), (6, -5), (14, 2), (4, 0)], MANE)
    b.deco("forelock_hi", "head", hx - 20, hy - 9, 0.0, "poly",
           [(-4, 2), (-3, -5), (4, -4), (10, 1), (2, 0)], (55, 45, 52))
    nx, ny = b.on("chest")   # the mane runs along the whole neck, from the base
    b.deco("mane", "neck", nx, ny, -0.80, "poly",
           [(-2, 2), (10, -6), (25, -7), (35, -5), (42, -2),
            (36, 1), (22, 3), (-2, 4)], MANE)
    b.deco("mane_tufts", "neck", nx + 8, ny - 6, -0.80, "poly",
           [(0, 0), (6, -4), (12, 0), (18, -4), (24, 0), (18, 3), (6, 3)], (45, 36, 42))
    if coat:
        # caparison: scalloped heraldic trappings with badge and gold trim
        rx, ry = b.on("rump")
        cx, cy = b.on("chest")
        mx, my = (rx + cx) / 2, (ry + cy) / 2 - 12
        b.deco("cloth", "barrel", mx, my, 0.06, "poly",
               [(-39, -3), (39, -3), (36, 16), (12, 13), (-12, 16), (-39, 15)],
               coat)
        b.deco("trim", "cloth", mx, my + 13, 0.06, "poly",
               [(-37, -3), (37, -3), (37, 3), (-37, 3)], trim or GOLD)
        b.deco("fringe", "cloth", mx, my + 16, 0.06, "poly",
               [(-34, 0), (34, 0), (32, 4), (-32, 4)], _tone(trim or GOLD, 1.20))
        b.deco("coat_badge_h", "cloth", mx - 16, my + 6, 0.06, "poly",
               [(-5, -1.5), (5, -1.5), (5, 1.5), (-5, 1.5)], trim or GOLD)
        b.deco("coat_badge_v", "cloth", mx - 16, my + 6, 0.06, "poly",
               [(-1.5, -5), (1.5, -5), (1.5, 5), (-1.5, 5)], trim or GOLD)
    # --- near legs, in front of the barrel ---
    b.link("leg_hn", "root", (-36, -57), 2.02, 29, 20, 12, near)
    b.limb("knee_hn", "leg_hn", 1.25, 32.5, 10, 6, near)
    b.limb("hoof_hn", "knee_hn", 0.20, 11, 11, 5, HOOF)
    b.link("leg_fn", "root", (30, -60), 1.27, 28, 19, 11, near)
    b.limb("knee_fn", "leg_fn", 1.78, 34, 10, 6, near)
    b.limb("hoof_fn", "knee_fn", 0.12, 11, 11, 5, HOOF)
    for hname in ("hoof_hn", "hoof_hf", "hoof_fn", "hoof_ff"):
        hx_, hy_ = b.on(hname)
        b.deco(f"shoe_{hname}", hname, hx_ + 1, hy_ + 3, 0.0, "poly",
               [(-4, 0), (4, 0), (5, 2.5), (-4, 2.5)], (175, 182, 192))
    # --- tack on top ---
    rx, ry = b.on("rump")
    bx, by = b.on("barrel")
    mx, my = (rx + bx) / 2, (ry + by) / 2 - 26
    b.deco("saddle_pad", "barrel", mx, my + 3, 0.0, "poly",
           [(-19, -2), (19, -2), (17, 10), (-17, 10)], (55, 40, 30))
    b.deco("saddle", "barrel", mx, my, 0.0, "poly",
           [(-16, -5), (16, -5), (13, 7), (-13, 7)], (108, 72, 46))
    b.deco("cantle", "saddle", mx - 12, my - 7, 0.0, "poly",
           [(-5, 0), (5, 0), (4, 7), (-4, 7)], (88, 58, 38))
    b.deco("cantle_gold", "saddle", mx - 12, my - 8, 0.0, "poly",
           [(-4, 0), (4, 0), (3, 2), (-3, 2)], GOLD)
    b.deco("pommel", "saddle", mx + 14, my - 7, 0.0, "circle", [], GOLD, 4.5)
    b.deco("pommel_stud", "saddle", mx + 14, my - 7, 0.0, "circle", [], (180, 25, 30), 2.0)
    b.deco("stirrup_strap", "barrel", mx + 2, my + 6, 0.0, "poly",
           [(-1.5, 0), (1.5, 0), (1.5, 20), (-1.5, 20)], (65, 46, 32))
    b.deco("stirrup_iron", "barrel", mx + 2, my + 25, 0.0, "poly",
           [(-3.5, 0), (3.5, 0), (3.5, 5), (-3.5, 5)], (190, 195, 205))
    b.deco("bridle", "head", hx - 5, hy - 2, 0.0, "poly",
           [(0, -9), (3, -9), (3, 9), (0, 9)], (62, 46, 34))
    b.deco("bridle_brow", "head", hx - 13, hy - 7, 0.0, "poly",
           [(-2, -2), (8, 0), (8, 2), (-2, 0)], (62, 46, 34))
    b.deco("bit", "head", hx - 4, hy + 5, 0.0, "circle", [], GOLD, 2.5)
    return b


def make_horse_rig(coat=None, trim=None, scale=1.0):
    # Canvas headroom also covers the nose during the forward gallop phase.
    return _horse(coat, trim, scale).build(int(145 * scale), int(145 * scale))


STEEL_ARM_W = (13, 9)
LEG_W = (14, 11)
SHOULDER = (1.0, -78.0)
HIP = (0.0, -52.0)


def _human(scale, steel, steel_d, cloth, cloth_d, weapon, plume, shield,
           crest, lance, kettle=False):
    """Knight or guard. Feet y=0, head top ~y=-90. Faces +x."""
    b = Builder(scale)
    b.deco("root", None, 0, 0, 0.0, "circle", [], cloth, 1.0)
    # --- cape, streaming back from the shoulders: a silhouette cue and the
    # heraldic colour in one shape. Drawn before everything else, so it sits
    # behind the body.
    cx0, cy0 = SHOULDER[0] - 6, SHOULDER[1] + 4
    b.deco("cape_back", "root", cx0, cy0, 0.0, "poly",
           [(5, -2), (-8, -4), (-20, 2), (-30, 13), (-36, 24), (-27, 19),
            (-24, 30), (-15, 21), (-10, 25), (-3, 12), (5, 8)],
           _tone(cloth_d, 0.92))
    b.deco("cape_fold", "root", cx0 - 9, cy0 + 8, 0.0, "poly",
           [(-1, -2), (-10, 2), (-18, 10), (-12, 11), (-4, 5)], _tone(cloth_d, 1.16))
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
    b.deco("belt", "torso", HIP[0], HIP[1] - 3, 1.5708, "poly",
           [(-10, -2), (10, -2), (10, 2), (-10, 2)], (70, 52, 36))
    b.deco("buckle", "torso", HIP[0] + 1, HIP[1] - 3, 1.5708, "poly",
           [(-3, -2.5), (3, -2.5), (3, 2.5), (-3, 2.5)], GOLD)
    # Fauld and hanging tassets protecting the thighs
    b.deco("fauld", "torso", HIP[0], HIP[1] - 1, 1.5708, "poly",
           [(-9, -2), (9, -2), (9, 3), (-9, 3)], steel_d)
    b.deco("tasset_n", "torso", HIP[0] + 2, HIP[1] + 2, 1.5708, "poly",
           [(-4, 0), (5, 0), (4, 8), (-4, 8)], steel)
    b.deco("tasset_rivet", "torso", HIP[0] + 2, HIP[1] + 4, 1.5708, "circle", [], GOLD, 1.4)
    sx, sy = b.on("torso")
    # Gleaming steel cuirass with central tapul ridge and highlight
    b.deco("cuirass", "torso", sx, sy + 6, 0.0, "poly",
           [(-9, -6), (9, -6), (8, 9), (-8, 9)], steel)
    b.deco("cuirass_ridge", "torso", sx + 1, sy + 6, 0.0, "poly",
           [(-1, -6), (2, -6), (2, 9), (-1, 9)], _tone(steel, 1.30))
    b.deco("cuirass_glint", "torso", sx + 3, sy + 4, 0.0, "poly",
           [(-2, -3), (3, -3), (2, 3), (-2, 2)], _tone(steel, 1.45))
    b.deco("gorget", "torso", sx, sy - 4, 0.0, "circle", [], steel_d, 5.5)
    b.deco("neck", "torso", sx, sy - 10, 0.0, "circle", [], steel_d, 4.0)
    # Helm: Bascinet/Sallet with beaked snout and flared occipital tail
    b.link("head", "neck", (sx + 1, sy - 11), -1.28, 18, 19, 15, steel)
    hx, hy = b.on("head")
    b.deco("helm_brow", "head", hx - 1, hy + 4, 0.0, "poly",
           [(-8, -2), (9, -3), (10, 0), (-8, 1)], _tone(steel, 1.28))
    # Slanted, sinister ocular slit
    b.deco("visor", "head", hx + 1, hy + 7, 0.0, "poly",
           [(-6, -1), (9, -2), (9, 1), (-6, 1.5)], (16, 18, 26))
    # Beaked snout prow (central deflective keel of visor)
    b.deco("visor_prow", "head", hx + 6, hy + 9, 0.0, "poly",
           [(0, -3), (6, 0), (1, 5), (-4, 2)], _tone(steel, 1.18))
    b.deco("visor_prow_sh", "head", hx + 6, hy + 11, 0.0, "poly",
           [(1, 3), (6, -2), (0, -2)], _tone(steel_d, 0.92))
    if kettle:
        # kettle hat: a flat brim and a dark band, so a foot guard's head reads
        # as a different helm from the knight's sallet before any colour is seen
        b.deco("kettle_brim", "head", hx + 1, hy - 1, 0.0, "poly",
               [(-11, -4), (12, -4), (13, -1), (-11, -1)], _tone(steel_d, 0.9))
        b.deco("kettle_band", "head", hx - 2, hy - 3, 0.0, "poly",
               [(-7, -1), (8, -1), (8, 1), (-7, 1)], (40, 38, 46))
    # Flared neck guard protecting nape
    b.deco("helm_tail", "head", hx - 8, hy + 6, 0.0, "poly",
           [(-2, -1), (-6, 6), (-3, 8), (2, 3)], _tone(steel, 1.08))
    # Ventilation rosettes
    b.deco("breathe", "head", hx + 4, hy + 13, 0.0, "poly",
           [(-1, -1), (2, -1), (2, 1), (-1, 1)], (22, 24, 32))
    b.deco("breathe2", "head", hx + 7, hy + 12, 0.0, "poly",
           [(-1, -1), (1, -1), (1, 1), (-1, 1)], (22, 24, 32))
    if crest:
        # Grand heraldic winged crest
        b.deco("crest", "head", hx - 4, hy - 2, 0.0, "poly",
               [(-3, 2), (4, -8), (14, -18), (17, -23), (10, -19), (2, -10), (-5, -4)], crest)
        b.deco("crest_hi", "head", hx - 2, hy - 4, 0.0, "poly",
               [(-1, 0), (5, -7), (12, -15), (14, -20), (8, -16), (2, -9), (-2, -3)], _tone(crest, 1.25))
    if plume:
        # Multi-tiered flowing plumage
        b.deco("plume", "head", hx - 4, hy - 2, 0.0, "poly",
               [(0, 3), (12, -4), (27, -13), (33, -27), (20, -22), (8, -11), (-5, 0)], CRIMSON_D)
        b.deco("plume_mid", "head", hx - 3, hy - 4, 0.0, "poly",
               [(2, 1), (12, -6), (24, -15), (29, -25), (19, -20), (9, -10), (-2, -1)], CRIMSON)
        b.deco("plume_hi", "head", hx - 1, hy - 6, 0.0, "poly",
               [(3, -1), (11, -8), (21, -16), (25, -23), (16, -19), (8, -10), (0, -2)], (244, 95, 95))
        b.deco("plume_socket", "head", hx - 5, hy - 1, 0.0, "poly",
               [(-2, 0), (2, -4), (5, -1), (0, 2)], GOLD)
    # --- near leg + near arm, in front ---
    b.link("thigh", "root", HIP, 1.52, 25, 14, 11, cloth_d)
    b.limb("shin", "thigh", 1.74, 23, 11, 7, steel_d)
    b.limb("foot", "shin", 0.10, 11, 9, 5, (58, 46, 36))
    # Sabaton armored shoe and spur
    fx_, fy_ = b.on("shin")
    b.deco("sabaton", "shin", fx_ + 3, fy_ + 7, 0.0, "poly",
           [(-3, -2), (7, -1), (11, 2), (-2, 2)], steel_d)
    b.deco("spur", "shin", fx_ - 4, fy_ + 8, 0.0, "poly",
           [(-3, -1), (0, -2), (0, 2), (-3, 1)], GOLD)
    b.link("arm_n", "root", (SHOULDER[0] + 3, SHOULDER[1]), 0.90, 19,
           *STEEL_ARM_W, steel)
    b.limb("fa_n", "arm_n", 1.00, 18, 8, 7, steel)
    # Layered fluted pauldrons over shoulders
    b.deco("pauldron_n", "torso", SHOULDER[0] + 3, SHOULDER[1] + 2, 0.0,
           "poly", [(-6, -6), (6, -6), (8, 4), (0, 8), (-7, 4)], steel)
    b.deco("pauldron_rim", "torso", SHOULDER[0] + 3, SHOULDER[1] + 1, 0.0,
           "poly", [(-5, -5), (5, -5), (6, -2), (-5, -2)], _tone(steel, 1.25))
    b.deco("pauldron_f", "torso", SHOULDER[0] - 6, SHOULDER[1] + 2, 0.0,
           "poly", [(-5, -5), (5, -5), (6, 3), (0, 7), (-6, 3)], steel_d)
    # Armored couter on the elbow
    ex_, ey_ = b.on("arm_n")
    b.deco("couter", "arm_n", ex_ + 1, ey_, 0.0, "poly",
           [(-4, -4), (4, -4), (6, 2), (-2, 5)], _tone(steel, 1.15))
    hx, hy = b.on("fa_n")
    if lance:
        b.deco("lance", "fa_n", hx, hy, 0.02, "poly",
               [(-28, -2.4), (74, -2.4), (74, 2.4), (-28, 2.4)], WOOD)
        b.deco("lance_stripes", "fa_n", hx + 24, hy, 0.02, "poly",
               [(0, -2.4), (32, -2.4), (32, 2.4), (0, 2.4)], (210, 165, 75))
        b.deco("vamplate", "fa_n", hx + 12, hy, 0.02, "poly",
               [(-4, -9), (5, -9), (7, 9), (-2, 9)], steel)
        b.deco("vamplate_rim", "fa_n", hx + 14, hy, 0.02, "poly",
               [(0, -9), (3, -9), (3, 9), (0, 9)], GOLD)
        b.deco("nave", "lance", hx + 74, hy, 0.02, "poly",
               [(0, -4.8), (20, 0), (0, 4.8)], (225, 230, 240))
        b.deco("nave_edge", "lance", hx + 74, hy, 0.02, "poly",
               [(0, -4.8), (20, 0), (6, 0)], (255, 255, 255))
    elif weapon == "sword":
        # The whole sword hangs off `hand`, the wrist pivot at the forearm's
        # tip: rotating `hand` swings the blade around the wrist, so a cut can
        # lead with the edge instead of dragging the blade rigid on the arm.
        # `hand` is declared first so FK resolves it before its children.
        b.deco("hand", "fa_n", hx, hy, 0.26, "circle", [],
               _tone(steel_d, 0.85), 5.0)
        b.deco("pommel", "hand", hx - 5, hy, 0.26, "circle", [],
               GOLD, 3.6)
        b.deco("pommel_gem", "hand", hx - 5, hy, 0.26, "circle", [],
               (180, 28, 34), 1.8)
        b.deco("hilt", "hand", hx, hy, 0.26, "poly",
               [(-3, -2), (3, -2), (3, 2), (-3, 2)], (85, 62, 42))
        b.deco("grip_wire", "hand", hx, hy, 0.26, "poly",
               [(-1, -2), (1, -2), (1, 2), (-1, 2)], GOLD)
        b.deco("guard", "hand", hx + 1, hy, 0.26, "poly",
               [(-2, -11), (3, -11), (3, 11), (-2, 11)],
               GOLD if (plume or crest) else STEEL)
        b.deco("blade", "hand", hx, hy, 0.26, "poly",
               [(2, -3.2), (42, -2.6), (50, 0), (42, 2.6), (2, 3.2)], (240, 244, 252))
        b.deco("fuller", "hand", hx + 2, hy, 0.26, "poly",
               [(0, -0.9), (32, -0.7), (32, 0.7), (0, 0.9)], (168, 176, 190))
        b.deco("blade_edge", "hand", hx, hy, 0.26, "poly",
               [(2, -3.2), (42, -2.6), (50, 0), (42, -1.2), (2, -1.8)], (255, 255, 255))
        b.deco("ricasso", "hand", hx + 1, hy, 0.26, "poly",
               [(0, -3), (5, -3), (5, 3), (0, 3)], (195, 200, 210))
        b.deco("cuff", "fa_n", hx - 3, hy, 0.26, "poly",
               [(-2, -4), (2, -4), (2, 4), (-2, 4)], steel)
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
                   crest=None, lance=False, kettle=False):
    b = _human(scale, steel, steel_d, cloth, cloth_d, weapon, plume, shield,
               crest, lance, kettle)
    # the lance needs canvas room to the right; the plume room above. The
    # sword/spear need a little more than they used to, now that the cut swings
    # the weapon further forward at full extension.
    reach = 150 if lance else 116
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
    # mounted sword carried forward at a slight up angle. Do NOT raise this arm
    # like the on-foot carry: the enemy rider's lance hangs off the same bones,
    # and a raised arm points the lance up over the shoulder and off the canvas.
    "arm_n": -0.35, "fa_n": -0.22, "hand": 0.00,
    "thigh": -0.35, "shin": 0.55, "foot": 0.22,
    "thigh_f": -0.30, "shin_f": 0.50, "foot_f": 0.20,
    "plume": -0.25, "crest": -0.20,
}
_FOOT = {
    "torso": 0.06, "neck": 0.0, "head": 0.0,
    "arm_f": 0.06, "fa_f": -0.18,
    "arm_n": -0.88, "fa_n": -0.30, "hand": 0.00,
    "thigh": 0.0, "shin": 0.0, "foot": 0.0,
    "thigh_f": 0.0, "shin_f": 0.0, "foot_f": 0.0,
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
    # Rotary gallop, one stride = one cycle: the forelegs strike together
    # (lead pair), the hindlegs follow as a pair ~0.36 later, then the
    # suspension phase. The old offsets put the hind pair 0.18 apart, so the
    # gait looked like a trot with extra bounce.
    for hip, knee, hoof, off, hind in (
        ("leg_fn", "knee_fn", "hoof_fn", 0.00, False),
        ("leg_ff", "knee_ff", "hoof_ff", 0.08, False),
        ("leg_hn", "knee_hn", "hoof_hn", 0.38, True),
        ("leg_hf", "knee_hf", "hoof_hf", 0.46, True),
    ):
        u = p + TAU * off
        swing = math.sin(u)
        gather = max(0.0, math.cos(u - 0.55))
        stance = max(0.0, -math.cos(u - 0.55))
        if hind:
            # Hind leg: drive backward, tuck forward under belly with articulated hock and hoof
            a[hip] = motion * (-0.66 * swing + 0.12)
            a[knee] = motion * (-0.70 * gather + 0.12 * stance)
            a[hoof] = motion * (0.22 * swing - 0.32 * gather + 0.10 * stance)
        else:
            # Foreleg: reach forward, fold carpus cleanly during recovery, cushion impact on stance
            a[hip] = motion * (-0.60 * swing - 0.10)
            a[knee] = motion * (0.62 * gather + 0.08 * stance)
            a[hoof] = motion * (0.22 * swing - 0.30 * gather - 0.08 * stance)
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


# Sword cuts, one keyframe table per combo. Values are ADDITIVE offsets per
# bone, keyed by swing progress k = 1 - attack: 0 is the first frame of the
# cut, 1 the moment it has recovered. Every table starts and ends neutral,
# so each cut grows out of, and settles back into, the raised carry pose in
# _FOOT. arm_n/fa_n already carry the +0.96/+0.14 that compensates that raised
# base, so the absolute swing is the same as when the base was a low guard.
# `hand` is the wrist pivot (see _human): it swings the whole sword so the
# blade leads the cut instead of staying rigid on the forearm.
SWORD_CUTS = {
    0: (  # fendente discendente: guardia alta, taglio diagonale in avanti
        (0.00, {}),
        (0.30, {"arm_n": -0.14, "fa_n": 0.69, "hand": -0.35,
                "arm_f": 0.30, "fa_f": -0.15, "torso": -0.14, "head": -0.10}),
        (0.66, {"arm_n": 1.24, "fa_n": -0.51, "hand": 0.35,
                "arm_f": -0.40, "fa_f": 0.28, "torso": 0.30, "head": 0.14}),
        (1.00, {}),
    ),
    1: (  # fendente ascendente: carica in basso, risalita larga
        (0.00, {}),
        (0.30, {"arm_n": 1.28, "fa_n": -0.06, "hand": 0.25,
                "arm_f": 0.25, "fa_f": -0.10, "torso": 0.16, "head": 0.06}),
        (0.66, {"arm_n": 0.24, "fa_n": -0.01, "hand": -0.20,
                "arm_f": -0.35, "fa_f": 0.25, "torso": -0.18, "head": -0.10}),
        (1.00, {}),
    ),
    2: (  # affondo finisher: camera al fianco, stoccata in avanti
        (0.00, {}),
        (0.30, {"arm_n": 0.71, "fa_n": 0.64, "hand": -0.15,
                "arm_f": 0.30, "fa_f": -0.20, "torso": -0.16, "head": -0.10}),
        (0.66, {"arm_n": 0.36, "fa_n": -0.81, "hand": 0.85,
                "arm_f": -0.50, "fa_f": 0.30, "torso": 0.34, "head": 0.10}),
        (1.00, {}),
    ),
}


def _cut_offsets(k, keys):
    """Piecewise-eased additive bone offsets at swing progress k in [0, 1]."""
    for (k0, a0), (k1, a1) in zip(keys, keys[1:]):
        if k <= k1:
            u = ease((k - k0) / max(1e-6, k1 - k0))
            return {n: lerp(a0.get(n, 0.0), a1.get(n, 0.0), u)
                    for n in a0.keys() | a1.keys()}
    return {}


def rider_pose(phase, riding=1.0, moving=0.0, air=0.0, attack=0.0, reach=0.0, combo=0):
    """Blend the mounted pose (riding=1) into an on-foot run/strike (riding=0).

    -> (angles, hip_lift). hip_lift raises the whole rider, which is how the
    mounted pose clears the horse's back.
    """
    p = TAU * phase
    riding = max(0.0, min(1.0, riding))
    a = {name: lerp(_FOOT[name], _RIDE[name], riding) for name in _RIDE}
    sw, cw = math.sin(p) * moving, math.cos(p) * moving
    sw2, cw2 = math.sin(p + math.pi) * moving, math.cos(p + math.pi) * moving

    # Blend the motion as well as the rest stance. Articulated knee flexion,
    # plantarflexion push-off and dorsiflexion recovery.
    foot_motion = {
        "thigh": -0.55 * sw,
        "shin": (0.85 * max(0.0, sw) + 0.25 * max(0.0, -cw) * max(0.0, -sw)) * moving,
        "foot": (0.30 * max(0.0, -sw) - 0.25 * max(0.0, sw)) * moving,
        "thigh_f": -0.55 * sw2,
        "shin_f": (0.85 * max(0.0, sw2) + 0.25 * max(0.0, -cw2) * max(0.0, -sw2)) * moving,
        "foot_f": (0.30 * max(0.0, -sw2) - 0.25 * max(0.0, sw2)) * moving,
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
    foot_lift = -0.5 * (1.0 - math.cos(p * 2)) * 2.2 * moving - 5.0 * air
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
        # The cut is a chain of additive offsets that starts and ends neutral,
        # so it grows out of the walk/ride base and settles back into it. The
        # footfall's own arm swing is damped out while the blade is in flight,
        # or the running figure wobbles through the swing.
        # NB: k is left LINEAR here. _cut_offsets already eases each segment, so
        # easing k too doubled the peak angular rate and the strike strobed.
        k = 1.0 - attack  # 0 at the start of the swing, 1 when recovered
        damp = ease(min(1.0, min(k, 1.0 - k) / 0.12)) * (1.0 - riding)
        lead = 1.0 - riding * 0.35   # a rider leaning over the saddle leads less
        for name in ("arm_n", "fa_n", "arm_f"):
            a[name] = a.get(name, 0.0) - foot_motion.get(name, 0.0) * damp
        for name, off in _cut_offsets(k, SWORD_CUTS[combo % 3]).items():
            a[name] = a.get(name, 0.0) + off * (lead if name in ("torso", "head") else 1.0)

    # plume and crest ride the stride: a dead-still one looks painted on
    swing = 0.35 + 0.65 * moving
    a["plume"] = a.get("plume", 0.0) + 0.06 * math.sin(p * 2.0 + 0.6) * swing
    a["crest"] = a.get("crest", 0.0) + 0.05 * math.sin(p * 2.0 + 1.1) * swing
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
