"""I due scheletri del gioco: il cavallo e il cavaliere.

Un rig e' la posa di riposo, in coordinate mondo semplici: piedi a y=0, si
guarda verso +x, y punta in giu'. `Builder` incatena le ossa al tip del genitore
invece di fare aritmetica a mano, cos' una catena non puo' uscire rotta.
"""

import math

from bones import TAU, Bone, Rig, _tone


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

