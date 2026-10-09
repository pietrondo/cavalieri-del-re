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

