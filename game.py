"""Cavalieri del Re - Livello 1: la fuga dal castello.

Il cavaliere esce dal cortile di Castel Rosso a cavallo. Le guardie del re lo
cercano per fermarlo, cavalieri nemici chiudono la strada, e lungo il cammino
ci sono sacchetti di provviste da raccogliere.

Grafica 100% procedurale: gli sprite sono Python (vedi sprites.py), nessun
asset nel repo. w con A/D (in sella: corri, Shift: galoppo), W salto,
SPAZCO attacco, E smonta/rimonta, R ricomincia.
"""

import math
import random

import pygame

import sprites
import world

W, H = 960, 540
FPS = 60
GROUND = world.GROUND

FOOT_SPEED = 2.6
HORSE_SPEED = 5.4
GALLOP_MUL = 1.55
GRAV = 0.62
JUMP_V = -13.0
ATTACK_TIME = 0.38
HIT_LO, HIT_HI = 0.25, 0.65
FINISHER_STEP = 92.0   # px/s: about 14 px across the strike window
SWORD_REACH = 78 * 1.28
LANCE_REACH = 112 * 1.42
INVULN = 0.80
MOUNT_TIME = 0.50
MOUNT_DIST = 58.0 * 1.3
SHIELD_TIME = 6.0

# Actor scale. A knight on a horse is the subject of the shot, so he is a
# third of the screen tall, not a sixth. Scaling happens in the rig geometry,
# which keeps the 3x supersampled render crisp.
HORSE_S = 1.42
HUMAN_S = 1.28
# the rider's pelvis must land on the saddle: hip(-52*HUMAN_S) + seat = saddle
SEAT = 91.0 * HORSE_S - 52.0 * HUMAN_S - 4.0

ST_HORSE, ST_FOOT, ST_DIS, ST_MOUNT, ST_DEAD, ST_WIN = (
    "horse", "foot", "dismount", "mount", "dead", "win")


def ease(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


_FONTS = {}


def font(size):
    """Fonts are loaded from disk: build each size once, not every frame."""
    f = _FONTS.get(size)
    if f is None:
        f = _FONTS[size] = pygame.font.Font(None, size)
    return f


_SHADOWS = {}


def contact_shadow(surf, x, y, w, alpha=110):
    """Multi-layer soft contact shadow with ambient penumbra and core."""
    key = (round(w), alpha)
    if key not in _SHADOWS:
        _SHADOWS[key] = _build_shadow(w, alpha)
    s = _SHADOWS[key]
    surf.blit(s, (int(x - s.get_width() // 2), int(y - s.get_height() * 0.5)))


def _build_shadow(w, alpha):
    h = max(6, int(w * 0.36))
    sw, sh = int(w * 2.2), h + 4
    s = pygame.Surface((sw, sh), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (14, 12, 18, int(alpha * 0.45)), s.get_rect())
    core_rect = pygame.Rect(int(sw * 0.18), int(sh * 0.22), int(sw * 0.64), int(sh * 0.56))
    pygame.draw.ellipse(s, (10, 8, 14, int(alpha * 0.85)), core_rect)
    return s


_VEILS = {}


def _veil(rgba):
    """Velo a tutto schermo, costruito una volta per colore: prima veniva
    riallocato a ogni frame (960x540 di superficie nuova ogni volta)."""
    if rgba not in _VEILS:
        v = pygame.Surface((W, H), pygame.SRCALPHA)
        v.fill(rgba)
        _VEILS[rgba] = v
    return _VEILS[rgba]


# --------------------------------------------------------------------------
# Actors
# --------------------------------------------------------------------------
class Actor:
    def __init__(self, x, rig, hp, speed):
        self.x = float(x)
        self.y = GROUND
        self.rig = rig
        self.hp = hp
        self.max_hp = hp
        self.speed = speed
        self.phase = 0.0
        self.face = 1
        self.flash = 0.0
        self.stun = 0.0
        self.attack = 0.0
        self.hit_ids = set()
        self.dead = False
        self.dead_t = 0.0
        self.horse = None

    def tick(self, dt):
        self.flash = max(0.0, self.flash - dt)
        self.stun = max(0.0, self.stun - dt)

    def pose(self):
        return {}, 0.0

    def draw(self, surf, cam_x, dark=1.0):
        contact_shadow(surf, self.x - cam_x, self.y, 22 * HUMAN_S)
        ang, lift = self.pose()
        img, _ = sprites.render_human(self.rig, ang, (0.0, lift), dark=dark,
                                      flip=self.face < 0)
        sprites.blit(surf, img, self.rig, self.x - cam_x, self.y)


class Horse:
    """Enough horse for a mounted actor to stand on."""

    def __init__(self, x, coat=None, trim=None):
        self.rig = sprites.make_horse_rig(coat=coat, trim=trim, scale=HORSE_S)
        self.x = float(x)
        self.phase = 0.0
        self.speed = 0.0
        self.face = -1
        self.y = GROUND

    def draw(self, surf, cam_x, dark=1.0):
        contact_shadow(surf, self.x - cam_x, self.y, 48 * HORSE_S)
        ang, bob = sprites.horse_pose(self.speed, self.phase, panic=0.25)
        img, _ = sprites.render_horse(self.rig, ang, (0.0, bob), dark=dark,
                                      flip=self.face < 0)
        sprites.blit(surf, img, self.rig, self.x - cam_x, self.y)


class Guard(Actor):
    """Guardia del re (a piedi) o cavaliere nemico (in sella con lancia)."""

    def __init__(self, x, kind="foot"):
        if kind == "rider":
            super().__init__(x, sprites.make_human_rig(
                0.96 * HUMAN_S, sprites.GREY, sprites.GREY_D, sprites.GREY_D,
                sprites.BLACK, weapon="none", plume=False, shield=False,
                crest=sprites.GOLD, lance=True), 7, 3.1)
            self.dmg, self.reach = 2, 92.0 * HORSE_S
            self.horse = Horse(x, coat=sprites.GREY_D, trim=sprites.GOLD)
            self.on_horse = True
        elif kind == "spear":
            super().__init__(x, sprites.make_human_rig(
                0.94 * HUMAN_S, sprites.GREY, sprites.GREY_D, (58, 96, 98),
                (38, 66, 70), weapon="spear", plume=False, shield=False,
                kettle=True), 3, 2.5)
            self.dmg, self.reach, self.on_horse = 1, 70.0, False
        else:
            super().__init__(x, sprites.make_human_rig(
                0.90 * HUMAN_S, sprites.GREY, sprites.GREY_D, sprites.OCHRE,
                sprites.OCHRE_D, weapon="sword", plume=False, shield=True,
                kettle=True), 4, 2.0)
            self.dmg, self.reach, self.on_horse = 1, 62.0, False
        self.kind = kind
        self.cooldown = random.uniform(0.4, 1.4)
        self.telegraph = 0.0
        self.telegraph_max = 0.36
        # each guard starts somewhere in its stride: a column that all steps
        # in unison is what made the enemies look like a marching undead line
        self.phase = random.random()

    @property
    def tx(self):
        return self.horse.x if self.horse and self.on_horse else self.x

    def pose(self):
        if self.dead:
            return sprites.dead_pose(self.dead_t, self.on_horse)
        if self.attack > 0:
            if self.kind in ("rider", "spear"):
                ang, lift = sprites.rider_pose(self.phase, riding=1.0 if self.on_horse
                                              else 0.0, moving=0.0,
                                              reach=ease(1.0 - self.attack))
            else:
                ang, lift = sprites.rider_pose(self.phase, riding=0.0, moving=0.0,
                                              attack=self.attack)
            return ang, lift
        if self.telegraph > 0:
            u = ease(1.0 - (self.telegraph / max(0.01, self.telegraph_max)))
            if self.kind in ("rider", "spear"):
                ang, lift = sprites.rider_pose(self.phase, riding=1.0 if self.on_horse
                                              else 0.0, moving=0.0,
                                              reach=0.45 * u)
            else:
                ang, lift = sprites.rider_pose(self.phase, riding=0.0, moving=0.0,
                                              attack=0.25 * u)
            return ang, lift
        if self.stun > 0:
            # recoil: the body snaps back from the blow and comes forward again
            # as the stun wears off, instead of freezing in the idle stance
            u = min(1.0, self.stun / 0.45)
            ang, lift = sprites.rider_pose(self.phase,
                                           riding=1.0 if self.on_horse else 0.0,
                                           moving=0.0)
            ang["torso"] = ang.get("torso", 0.0) - 0.34 * u
            ang["head"] = ang.get("head", 0.0) - 0.30 * u
            ang["arm_f"] = ang.get("arm_f", 0.0) - 0.25 * u
            return ang, lift
        ang, lift = sprites.rider_pose(self.phase,
                                       riding=1.0 if self.on_horse else 0.0,
                                       moving=1.0, air=0.0)
        if not self.on_horse:
            # a living step: the torso rocks over each foot, the head follows,
            # and the sword arm's forearm stays flexed instead of locked straight
            t = math.tau * self.phase
            ang["torso"] = ang.get("torso", 0.0) + 0.07 + 0.05 * math.sin(2 * t)
            ang["head"] = ang.get("head", 0.0) + 0.05 * math.sin(2 * t + 0.8)
            ang["fa_n"] = ang.get("fa_n", 0.0) - 0.22
            lift += -2.2 * abs(math.sin(t))   # bob at every footfall
        return ang, lift

    def draw(self, surf, cam_x, dark=1.0):
        alpha = 1.0
        if self.dead and self.dead_t > 0.8:
            alpha = max(0.0, 1.0 - (self.dead_t - 0.8) / 1.0)

        if self.horse:
            h_alpha = 1.0
            if self.dead and self.dead_t > 1.2:
                h_alpha = max(0.0, 1.0 - (self.dead_t - 1.2) / 0.6)
            if h_alpha > 0:
                self.horse.draw(surf, cam_x, dark=dark)
        if not self.on_horse:
            contact_shadow(surf, self.x - cam_x, self.y, 22 * HUMAN_S,
                           alpha=int(95 * alpha))
        if alpha > 0:
            ang, lift = self.pose()
            img, _ = sprites.render_human(self.rig, ang,
                                          (0.0, lift - SEAT if self.on_horse else lift),
                                          dark=dark, flip=self.face < 0)
            if alpha < 1.0:
                img = img.copy()
                img.set_alpha(int(255 * alpha))
            sprites.blit(surf, img, self.rig, self.tx - cam_x, self.y)
            if not self.dead:
                if self.telegraph > 0:
                    t_pulse = pygame.time.get_ticks() * 0.025
                    rad = int(12 + 3 * math.sin(t_pulse))
                    wx = int(self.tx - cam_x)
                    wy = int(self.y - (105 if self.on_horse else 80))
                    halo = pygame.Surface((rad * 2 + 8, rad * 2 + 8), pygame.SRCALPHA)
                    pygame.draw.circle(halo, (255, 60, 40, 110), (rad + 4, rad + 4), rad)
                    surf.blit(halo, (wx - rad - 4, wy - rad - 4))
                    pygame.draw.circle(surf, (255, 230, 80), (wx, wy), 7)
                    pygame.draw.circle(surf, (200, 30, 20), (wx, wy), 7, 2)
                    f_warn = font(22)
                    t_warn = f_warn.render("!", True, (20, 15, 15))
                    surf.blit(t_warn, t_warn.get_rect(center=(wx, wy)))
                elif self.stun > 0:
                    st_ang = pygame.time.get_ticks() * 0.009
                    for s_i in range(3):
                        sa = st_ang + s_i * (math.tau / 3)
                        sx = int(self.tx - cam_x + math.cos(sa) * 16)
                        sy = int(self.y - (98 if self.on_horse else 74) + math.sin(sa) * 5)
                        pygame.draw.circle(surf, (255, 220, 80), (sx, sy), 3)
                        pygame.draw.circle(surf, (255, 255, 200), (sx, sy), 1)

    def hurt(self, dmg, from_x, heavy=False):
        self.hp -= dmg
        self.flash = 0.22 if heavy else 0.18
        self.stun = max(self.stun, 0.45 if heavy else 0.30)
        dist = 24 if heavy else 14
        self.x += dist if from_x < self.tx else -dist
        if self.horse:
            self.horse.x += dist if from_x < self.tx else -dist
        if self.hp <= 0:
            self.hp = 0
            self.dead = True
            if self.horse:
                self.on_horse = False
                self.horse.face = -1 if from_x < self.horse.x else 1


class Knight(Actor):
    def __init__(self, x):
        super().__init__(x, sprites.make_human_rig(HUMAN_S), 10, FOOT_SPEED)
        self.horse = Horse(x, coat=sprites.CRIMSON_D, trim=sprites.GOLD)
        self.horse.face = 1
        self.state = ST_HORSE
        self.st = 0.0
        self.on_horse = True
        self.invuln = 0.0
        self.knock = 0.0
        self.vy = 0.0
        self.air = 0.0
        self.gallop = False
        self.cooldown = 0.0
        self.shield = 0.0
        self.gold = 0
        self.combo_step = 0
        self.combo_timer = 0.0
        self.shake = 0.0

    # -- mount ------------------------------------------------------------
    def toggle_mount(self):
        if self.state == ST_HORSE:
            self.state, self.st = ST_DIS, 0.0
        elif self.state == ST_FOOT and abs(self.x - self.horse.x) < 78:
            self.state, self.st = ST_MOUNT, 0.0

    def grounded(self):
        return self.y >= GROUND - 0.6

    # -- input ------------------------------------------------------------
    def update(self, dt, keys, foes, fx=None):
        self.tick(dt)
        self.invuln = max(0.0, self.invuln - dt)
        self.knock = max(0.0, self.knock - dt)
        self.cooldown = max(0.0, self.cooldown - dt)
        self.combo_timer = max(0.0, self.combo_timer - dt)
        if self.shield > 0:
            self.shield = max(0.0, self.shield - dt)

        left = keys[pygame.K_a] or keys[pygame.K_LEFT]
        right = keys[pygame.K_d] or keys[pygame.K_RIGHT]
        up = keys[pygame.K_w] or keys[pygame.K_UP]
        shift = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        ax = (1 if right else 0) - (1 if left else 0)
        if ax:
            self.face = ax
        self.gallop = bool(shift and self.on_horse and ax and self.state == ST_HORSE)

        if self.state in (ST_DEAD, ST_WIN):
            if self.state == ST_DEAD:
                self.dead_t += dt
            return

        if self.attack > 0:
            self.attack = max(0.0, self.attack - dt / ATTACK_TIME)
            # finisher on foot: a real step into the cut during the strike, so
            # the hit zone travels with the body instead of staying behind it
            if (self.combo_step == 2 and not self.on_horse and not self.gallop
                    and HIT_LO <= self.attack <= HIT_HI and self.knock <= 0):
                self.x += self.face * FINISHER_STEP * dt
            self.sword_hit(foes, fx)

        if self.state in (ST_DIS, ST_MOUNT):
            self.st += dt
            t = min(1.0, self.st / MOUNT_TIME)
            e = ease(t)
            sign = 1.0 if self.state == ST_DIS else -1.0
            self.x = self.horse.x + MOUNT_DIST * e * sign
            self.y = GROUND - math.sin(t * math.pi) * 24
            self.horse.phase += dt * 1.2
            if t >= 1.0:
                self.state = ST_HORSE if sign < 0 else ST_FOOT
                self.on_horse = sign < 0
                self.st = 0.0
            return

        spd = HORSE_SPEED * (GALLOP_MUL if self.gallop else 1.0) \
            if self.on_horse else self.speed
        if self.knock <= 0:
            self.x += ax * spd
        self.x = max(30.0, min(self.x, world.GOAL_X + 120.0))

        if self.on_horse:
            # lock the horse to the (already clamped) rider x: moving it by
            # ax*spd on its own let it drift past the level edge the rider
            # cannot cross.
            self.horse.x = self.x
            self.horse.phase += dt * (0.9 + abs(ax) * spd * 0.30)
            self.horse.speed = abs(ax) * spd
            self.horse.face = self.face
            self.y, self.vy = GROUND, 0.0
        else:
            if up and self.grounded():
                self.vy = JUMP_V
            self.vy += GRAV
            self.y += self.vy
            if self.y >= GROUND:
                self.y, self.vy = GROUND, 0.0
            self.air = 0.0 if self.grounded() else -1.0
            self.phase += dt * (1.1 + abs(ax) * 1.5)

    # -- combat -----------------------------------------------------------
    def start_attack(self):
        if self.attack > 0 or self.cooldown > 0:
            return False
        if self.state in (ST_DEAD, ST_WIN, ST_DIS, ST_MOUNT):
            return False
        if self.combo_timer > 0:
            self.combo_step = (self.combo_step + 1) % 3
        else:
            self.combo_step = 0
        self.combo_timer = 0.52
        self.attack = 1.0
        self.hit_ids.clear()
        self.cooldown = 0.06 if self.combo_step < 2 else 0.20
        return True

    def sword_hit(self, foes, fx=None):
        if not (HIT_LO <= self.attack <= HIT_HI):
            return
        is_charge = self.gallop
        is_finisher = (self.combo_step == 2 and not is_charge)
        reach = LANCE_REACH if is_charge else (SWORD_REACH * 1.15 if is_finisher else SWORD_REACH)
        ox = self.x + self.face * reach * 0.45
        dmg_base = 4 if is_charge else (4 if is_finisher else 2)
        for e in foes:
            if e.dead or id(e) in self.hit_ids:
                continue
            if abs(e.tx - ox) < reach and abs(e.y - self.y) < 68:
                self.hit_ids.add(id(e))
                is_parry = (e.telegraph > 0) or (e.attack > 0.45)
                dmg = dmg_base + (2 if is_parry else 0)
                if is_parry:
                    e.telegraph = 0.0
                    e.attack = 0.0
                    e.stun = 0.85
                    e.hurt(dmg, self.x, heavy=True)
                    if fx:
                        fx.pop(e.tx, e.y - 100, "PARATA!", (120, 220, 255))
                        fx.ring(e.tx, e.y - 45, (130, 215, 255))
                        fx.burst(e.tx, e.y - 45, (200, 245, 255), 18)
                    self.shake = max(self.shake, 0.20)
                    if fx:
                        fx.hitstop = max(fx.hitstop, 0.09)   # la parata pesa
                else:
                    e.hurt(dmg, self.x, heavy=is_finisher or is_charge)
                    if fx:
                        fx.pop(e.tx, e.y - 75, "-%d" % dmg,
                               (255, 230, 110) if not is_finisher else (255, 190, 80))
                        fx.burst(ox, e.y - 45, (255, 220, 90),
                                 10 if not is_finisher else 18)
                        if is_finisher or is_charge:
                            fx.ring(ox, e.y - 45, (255, 210, 120))
                    self.shake = max(self.shake, 0.16 if (is_finisher or is_charge) else 0.08)
                    if fx and (is_finisher or is_charge):
                        fx.hitstop = max(fx.hitstop, 0.06)   # colpo pieno: un frame di pausa
                if e.hp <= 0 and fx:
                    fx.pop(e.tx, e.y - 95, "SCONFITTO!", (255, 180, 80))
                    fx.burst(e.tx, e.y - 40, (255, 130, 60), 16)

    def take_hit(self, dmg, from_x):
        if self.invuln > 0 or self.state in (ST_DEAD, ST_WIN):
            return False
        if self.shield > 0:
            self.shield = 0.0
            self.flash = 0.14
            return True
        self.hp -= dmg
        self.invuln = INVULN
        self.flash = 0.22
        self.knock = 0.20
        self.x += 16 if from_x < self.x else -16
        if self.hp <= 0:
            self.hp = 0
            self.state = ST_DEAD
            self.dead = True
            self.dead_t = 0.0
            if self.on_horse:
                self.on_horse = False
        return True

    # -- pose -------------------------------------------------------------
    def pose(self):
        if self.state == ST_DEAD:
            return sprites.dead_pose(self.dead_t, self.on_horse)
        riding = 1.0 if self.state == ST_HORSE else 0.0
        if self.state == ST_DIS:
            riding = 1.0 - min(1.0, self.st / MOUNT_TIME)
        elif self.state == ST_MOUNT:
            riding = min(1.0, self.st / MOUNT_TIME)
        # in the saddle the rider rides the horse's stride: same phase, and
        # sway scaled by how fast the horse is actually moving
        phase = self.horse.phase if self.on_horse else self.phase
        gait = min(1.0, self.horse.speed / HORSE_SPEED) if self.on_horse else 0.0
        ang, lift = sprites.rider_pose(
            phase, riding=riding,
            moving=gait if self.on_horse else 1.0,
            air=self.air,
            attack=0.0 if self.gallop else max(0.0, self.attack),
            reach=1.0 if self.gallop else 0.0,
            combo=self.combo_step)
        rec = min(1.0, self.knock / 0.20)     # knockback from a hit
        if rec > 0:
            ang["torso"] = ang.get("torso", 0.0) - 0.22 * rec
            ang["head"] = ang.get("head", 0.0) - 0.16 * rec
        return ang, lift - SEAT * riding

    def draw(self, surf, cam_x):
        # the horse is left behind on foot, so it can end up far off screen
        if -260 < self.horse.x - cam_x < W + 260:
            self.horse.draw(surf, cam_x)
        if not self.on_horse:
            contact_shadow(surf, self.x - cam_x, self.y, 22 * HUMAN_S)
        ang, lift = self.pose()
        img, _ = sprites.render_human(self.rig, ang, (0.0, lift),
                                      flip=self.face < 0)
        sprites.blit(surf, img, self.rig, self.x - cam_x, self.y)
        if self.shield > 0:
            bl = 0.55 + 0.45 * math.sin(pygame.time.get_ticks() * 0.012)
            halo = pygame.Surface((90, 90), pygame.SRCALPHA)
            pygame.draw.circle(halo, (110, 170, 240, int(70 * bl)), (45, 45), 42, 3)
            surf.blit(halo, (int(self.x - cam_x - 45), int(self.y - 84)))


# --------------------------------------------------------------------------
# Pickups + fx
# --------------------------------------------------------------------------
PICKUPS = {
    "heart": ((196, 54, 58), "vita"),
    "shield": ((72, 122, 196), "scudo 6s"),
    "gold": ((214, 176, 74), "oro"),
}


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
        c = PICKUPS[self.kind][0]
        x = int(self.x - cam_x)
        y = int(self.y + math.sin(self.t * 2.4) * 4.0 - 12 * (1 - self.land))
        r = int(13 * (1.0 + 0.22 * math.sin(self.t * 3.0)))
        halo = pygame.Surface((2 * r + 10, 2 * r + 10), pygame.SRCALPHA)
        pygame.draw.circle(halo, (*c, 46), (r + 5, r + 5), r + 4)
        surf.blit(halo, (x - r - 5, y - r - 5))
        pygame.draw.circle(surf, (52, 44, 40), (x, y), r)
        pygame.draw.circle(surf, c, (x, y), r - 3)
        if self.kind == "heart":
            pygame.draw.polygon(surf, (255, 216, 216), [
                (x - 6, y - 1), (x - 6, y + 4), (x, y + 8),
                (x + 6, y + 4), (x + 6, y - 1), (x, y + 3)])
        elif self.kind == "shield":
            pygame.draw.polygon(surf, (224, 236, 250), [
                (x, y - 7), (x + 6, y - 4), (x + 5, y + 4),
                (x, y + 8), (x - 5, y + 4), (x - 6, y - 4)])
        else:
            pygame.draw.circle(surf, (255, 242, 196), (x, y), r - 7)


class Fx:
    def __init__(self):
        self.parts, self.pops, self.rings, self.slashes = [], [], [], []
        self.hitstop = 0.0   # secondi di gioco congelato dopo un colpo pesante

    def burst(self, x, y, col, n=10):
        for _ in range(n):
            a = random.uniform(0, math.tau)
            s = random.uniform(1.0, 4.5)
            self.parts.append([x, y, math.cos(a) * s, math.sin(a) * s - 1.2,
                               random.uniform(0.22, 0.5), col])

    def pop(self, x, y, text, col):
        self.pops.append([x, y, text, col, 0.85])

    def ring(self, x, y, col):
        self.rings.append([x, y, 4.0, col, 0.35])

    def slash(self, x, y, face, reach, kind=0, foe=False):
        self.slashes.append([x, y, face, reach, 0.22, 0.22, kind, foe])

    def update(self, dt):
        for p in self.parts:
            p[0] += p[2] * dt * 60
            p[1] += p[3] * dt * 60
            p[3] += 0.26
            p[4] -= dt
        self.parts = [p for p in self.parts if p[4] > 0]
        for p in self.pops:
            p[1] -= 38 * dt
            p[4] -= dt
        self.pops = [p for p in self.pops if p[4] > 0]
        for r in self.rings:
            r[2] += 200 * dt
            r[4] -= dt
        self.rings = [r for r in self.rings if r[4] > 0]
        for s in self.slashes:
            s[4] -= dt
        self.slashes = [s for s in self.slashes if s[4] > 0]

    def draw(self, surf, cam_x):
        f = font(26)
        for s in self.slashes:
            x, y, face, reach, t_rem, t_max = s[:6]
            kind = s[6] if len(s) > 6 else 0
            foe = s[7] if len(s) > 7 else False
            progress = 1.0 - t_rem / t_max
            alpha = int(230 * (1.0 - progress))
            if alpha <= 0:
                continue
            r_in = reach * (0.42 if kind < 2 else 0.35)
            r_out = reach * (0.95 if kind < 2 else 1.15)
            sx = int(x - cam_x)
            sy = int(y)
            sz = int(r_out * 2 + 24)
            arc_surf = pygame.Surface((sz, sz), pygame.SRCALPHA)
            cx, cy = sz // 2, sz // 2
            pts = []
            if kind == 1:
                deg_in = range(45, -45, -5)
                deg_out = range(-40, 50, 5)
            elif kind == 2:
                deg_in = range(-65, 40, 5)
                deg_out = range(35, -70, -5)
            else:
                deg_in = range(-55, 30, 5)
                deg_out = range(25, -60, -5)

            y_squash = 0.70 if kind != 1 else 0.85
            for deg in deg_in:
                rad = math.radians(deg)
                pts.append((cx + face * math.cos(rad) * r_in, cy + math.sin(rad) * r_in * y_squash))
            for deg in deg_out:
                rad = math.radians(deg)
                pts.append((cx + face * math.cos(rad) * r_out, cy + math.sin(rad) * r_out * y_squash))

            if foe:
                fill_col = (245, 60, 60, alpha // 2)
                line_col = (255, 170, 170, alpha)
            elif kind == 1:
                fill_col = (130, 215, 255, alpha // 2)
                line_col = (235, 250, 255, alpha)
            elif kind == 2:
                fill_col = (255, 210, 80, int(alpha * 0.6))
                line_col = (255, 245, 210, alpha)
            else:
                fill_col = (220, 235, 255, alpha // 2)
                line_col = (255, 255, 255, alpha)

            if len(pts) >= 3:
                pygame.draw.polygon(arc_surf, fill_col, pts)
                inner_pts = pts[len(pts) // 4: 3 * len(pts) // 4]
                if len(inner_pts) >= 2:
                    pygame.draw.lines(arc_surf, line_col, False, inner_pts, 3 if kind < 2 else 4)
            surf.blit(arc_surf, (sx - cx, sy - cy))
        for r in self.rings:
            pygame.draw.circle(surf, r[3], (int(r[0] - cam_x), int(r[1])),
                               int(r[2]), 2)
        for p in self.parts:
            s = max(1, int(p[4] * 6))
            surf.fill(p[5], (int(p[0] - cam_x), int(p[1]), s, s))
        for p in self.pops:
            surf.blit(f.render(p[2], True, p[3]), (int(p[0] - cam_x), int(p[1])))


# --------------------------------------------------------------------------
# Level 1 script
# --------------------------------------------------------------------------
def level_plan():
    """(time, kind) spawns. Guards first, then enemy riders further down the
    road. Deterministic, so a retry is the same fight."""
    return [
        (1.8, "foot"), (2.8, "foot"), (4.2, "foot"),
        (6.0, "foot"), (7.6, "foot"),
        (9.4, "rider"), (11.0, "foot"), (12.4, "spear"),
        (14.5, "rider"), (15.8, "foot"),
        (18.0, "rider"), (19.0, "foot"), (19.8, "foot"),
        (22.5, "spear"), (23.5, "foot"),
        (26.0, "rider"), (27.2, "foot"), (28.0, "foot"),
        (30.5, "rider"), (31.5, "spear"),
        (34.0, "foot"), (35.0, "foot"),
        (38.0, "rider"), (39.0, "foot"),
    ]


def level_pickups():
    return [
        (1150.0, "heart"), (1400.0, "gold"), (1760.0, "shield"),
        (2120.0, "heart"), (2480.0, "gold"), (2860.0, "shield"),
        (3220.0, "heart"), (3560.0, "gold"), (3940.0, "shield"),
        (4300.0, "heart"), (4660.0, "gold"), (5020.0, "shield"),
    ]


def spawn_x(kind, knight_x):
    """Enemy knights come at you from ahead; guards pour out of the gate."""
    if kind == "rider":
        return knight_x + random.uniform(420, 620)
    return max(world.GATE_X1 - 40.0, knight_x - random.uniform(300, 460))


# --------------------------------------------------------------------------
# Main loop
# --------------------------------------------------------------------------
def run():
    pygame.init()
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("Cavalieri del Re - Livello 1: la fuga")
    clock = pygame.time.Clock()

    knight = Knight(60.0)
    foes = []
    pickups = [Pickup(x, k) for x, k in level_pickups()]
    fx = Fx()
    rng = random.Random(5)

    cam_x = 0.0
    elapsed = 0.0
    spawn_i = 0
    intro = 3.0
    gate = 0.0
    kills = 0
    banner = ""
    banner_t = 0.0
    won = False
    cam_shake = 0.0

    while True:
        dt = min(clock.tick(FPS) / 1000.0, 1 / 30.0)
        if fx.hitstop > 0:       # hit-stop: il mondo si ferma, la scena si ridisegna
            fx.hitstop = max(0.0, fx.hitstop - dt)
            dt = 0.0
        elapsed += dt
        keys = pygame.key.get_pressed()

        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit()
                return
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    pygame.quit()
                    return
                if ev.key == pygame.K_f:
                    pygame.display.toggle_fullscreen()
                if ev.key == pygame.K_e:
                    knight.toggle_mount()
                if ev.key in (pygame.K_SPACE, pygame.K_j):
                    if knight.start_attack():
                        reach = LANCE_REACH if knight.gallop else (SWORD_REACH * 1.15 if knight.combo_step == 2 else SWORD_REACH)
                        fx.slash(knight.x + knight.face * reach * 0.45,
                                 knight.y - (SEAT * 0.5 if knight.on_horse else 38),
                                 knight.face, reach, kind=knight.combo_step)
                        fx.ring(knight.x + knight.face * reach * 0.5, GROUND - 46,
                                (230, 220, 190) if knight.combo_step < 2 else (255, 220, 110))
                if ev.key == pygame.K_r and knight.state in (ST_DEAD, ST_WIN):
                    knight = Knight(60.0)
                    foes, kills = [], 0
                    pickups = [Pickup(x, k) for x, k in level_pickups()]
                    fx = Fx()
                    spawn_i, elapsed, intro, gate = 0, 0.0, 1.6, 0.0
                    won = False
                    banner, banner_t = "", 0.0
                    cam_shake = 0.0

        if intro > 0:
            intro -= dt
            gate = min(1.0, 1.0 - intro / 1.4)
        else:
            gate = min(1.0, gate + dt * 0.9)

        plan = level_plan()
        if spawn_i < len(plan) and elapsed > plan[spawn_i][0]:
            kind = plan[spawn_i][1]
            foes.append(Guard(spawn_x(kind, knight.x), kind))
            spawn_i += 1

        knight.update(dt, keys, foes, fx)

        # foes
        alive = 0
        for e in foes:
            if e.dead:
                e.dead_t += dt
                if e.horse:
                    e.horse.speed = 6.2
                    e.horse.x += e.horse.face * e.horse.speed
                    e.horse.phase += dt * 3.2
                continue
            alive += 1
            e.tick(dt)
            dx = knight.x - e.tx
            if abs(dx) > 2 and e.stun <= 0 and e.telegraph <= 0:
                e.face = 1 if dx > 0 else -1
                if e.horse:
                    e.horse.face = e.face
            if e.stun > 0:
                e.telegraph = 0.0
            elif e.telegraph > 0:
                e.telegraph -= dt
                if e.telegraph <= 0:
                    e.attack = 1.0
                    e.telegraph = 0.0
                    e.hit_ids.clear()
                    reach = e.reach
                    fx.slash(e.tx + e.face * reach * 0.45,
                             e.y - (SEAT * 0.5 if e.on_horse else 38),
                             e.face, reach, kind=0, foe=True)
            elif e.attack > 0:
                e.attack = max(0.0, e.attack - dt / ATTACK_TIME)
                if HIT_LO <= e.attack <= HIT_HI and id(knight) not in e.hit_ids:
                    if abs(e.tx - knight.x) < e.reach and abs(e.y - knight.y) < 70:
                        e.hit_ids.add(id(knight))
                        if knight.take_hit(e.dmg, e.tx):
                            fx.burst(knight.x, knight.y - 48, (206, 64, 56), 14)
                            fx.pop(knight.x, knight.y - 82, "-%d" % e.dmg,
                                   (255, 130, 118))
                            fx.ring(knight.x, knight.y - 44, (200, 70, 60))
                            cam_shake = max(cam_shake, 0.18)
            else:
                e.hit_ids.clear()
                if abs(dx) > e.reach * 0.8:
                    e.x += e.face * e.speed
                    if e.horse:
                        e.horse.x += e.face * e.speed
                        e.horse.phase += dt * (0.9 + e.speed * 0.3)
                        e.horse.speed = e.speed
                    e.phase += dt * (1.0 + e.speed * 0.4)
                else:
                    e.cooldown -= dt
                    if e.cooldown <= 0:
                        e.telegraph = 0.40 if e.kind == "spear" else 0.34
                        e.telegraph_max = e.telegraph
                        e.cooldown = rng.uniform(1.2, 2.0)
            e.x = max(world.GATE_X0 - 220.0, e.x)

        kills += sum(1 for e in foes if e.dead and e.dead_t < dt * 2)
        foes = [e for e in foes if not (e.dead and e.dead_t >= 1.8)]

        # pickups
        for p in pickups:
            if p.taken:
                continue
            p.update(dt)
            if abs(p.x - knight.x) < 44 and abs(p.y - knight.y) < 96:
                p.taken = True
                if p.kind == "heart":
                    knight.hp = min(knight.max_hp, knight.hp + 4)
                    label, col = "+4 vita", (140, 220, 140)
                elif p.kind == "shield":
                    knight.shield = SHIELD_TIME
                    label, col = "scudo!", (130, 190, 255)
                else:
                    knight.gold += 25
                    label, col = "+25 oro", (250, 216, 130)
                fx.pop(p.x, p.y - 20, label, col)
                fx.burst(p.x, p.y, PICKUPS[p.kind][0], 14)

        if knight.x >= world.GOAL_X and knight.state == ST_HORSE and not won:
            won = True
            knight.state = ST_WIN
            banner, banner_t = "FUGA RIUSCITA", 3.0

        banner_t = max(0.0, banner_t - dt)
        fx.update(dt)

        cam_x += ((knight.x - W * 0.38) - cam_x) * min(1.0, dt * 6)
        cam_x = max(-120.0, min(cam_x, world.GOAL_X + 120.0 - W * 0.3))

        if getattr(knight, "shake", 0.0) > 0:
            cam_shake = max(cam_shake, knight.shake)
            knight.shake = 0.0
        cam_shake = max(0.0, cam_shake - dt)
        shake_ox = random.uniform(-1.0, 1.0) * (cam_shake * 42.0) if cam_shake > 0 else 0.0
        draw_cam = cam_x + shake_ox

        # ---- draw ----
        world.draw_sky(screen)
        world.draw_background(screen, draw_cam)
        world.draw_goal(screen, draw_cam, elapsed)
        world.draw_ground(screen, draw_cam)
        world.draw_props(screen, draw_cam)
        world.draw_castle(screen, draw_cam)
        world.draw_portcullis(screen, draw_cam, gate)

        for p in pickups:
            if not p.taken:
                p.draw(screen, draw_cam)
        for e in sorted(foes, key=lambda g: g.y):
            if abs(e.tx - draw_cam - W / 2) < W / 2 + 160:  # cull off-screen
                e.draw(screen, draw_cam, dark=0.72 if e.flash > 0 else 1.0)
        knight.draw(screen, draw_cam)
        if knight.flash > 0:
            screen.blit(_veil((255, 90, 80, int(70 * knight.flash / 0.22))), (0, 0))
        fx.draw(screen, draw_cam)

        draw_hud(screen, knight, alive, kills, banner, banner_t, intro)
        pygame.display.flip()


def draw_hud(screen, knight, alive, kills, banner, banner_t, intro):
    f, s = font(30), font(22)
    # hearts
    for i in range(knight.max_hp):
        x, y = 24 + i * 21, 22
        full = i < knight.hp
        col = (206, 58, 58) if full else (66, 48, 50)
        pygame.draw.circle(screen, (32, 26, 28), (x + 7, y + 7), 9)
        pygame.draw.circle(screen, col, (x + 7, y + 7), 7)
    if knight.shield > 0:
        pygame.draw.circle(screen, (120, 180, 250), (24 + knight.max_hp * 21 + 12,
                                                     29), 8, 2)
        pygame.draw.circle(screen, (120, 180, 250),
                           (24 + knight.max_hp * 21 + 12, 29), 4)
    info = s.render("Guardie: %d  uccisi: %d  oro: %d" % (alive, kills,
                                                           knight.gold),
                    True, (238, 234, 224))
    screen.blit(info, (24, 46))
    hint = ("E: scendi a terra" if knight.on_horse
            else "E: rimonta (vicino al cavallo)")
    if knight.state in (ST_DEAD, ST_WIN):
        hint = "R: ricomincia"
    screen.blit(s.render(hint, True, (226, 220, 200)), (24, 68))
    if knight.combo_timer > 0 and knight.state not in (ST_DEAD, ST_WIN):
        combo_names = ["1: FENDENTE", "2: ASCENDENTE", "3: AFFONDO!"]
        c_str = f"COMBO {combo_names[knight.combo_step % 3]}"
        col = (255, 230, 100) if knight.combo_step == 2 else (200, 230, 255)
        c_surf = s.render(c_str, True, col)
        screen.blit(c_surf, (24, 90))
    ctrl = s.render("A/D muovi  W salta  SPAZCO attacca  SHIFT galoppo  "
                    "E cavalca  F schermo", True, (196, 196, 190))
    screen.blit(ctrl, (24, H - 26))

    # progress bar toward the forest
    prog = max(0.0, min(1.0, knight.x / world.GOAL_X))
    pygame.draw.rect(screen, (40, 38, 40), (W - 236, 24, 212, 12), 1)
    pygame.draw.rect(screen, (196, 176, 96), (W - 236, 24, int(210 * prog), 12))
    screen.blit(s.render("FUGA", True, (238, 234, 224)), (W - 236, 6))

    if banner_t > 0:
        img = f.render(banner, True, (252, 226, 150))
        screen.blit(img, img.get_rect(center=(W // 2, 120)))

    if intro > 0:
        screen.blit(_veil((0, 0, 0, 175))
                    .subsurface((0, 0, W, 104)), (0, 150))
        t1 = f.render("LIVELLO 1 - LA FUGA DA CASTEL ROSSO", True, (244, 226, 180))
        t2 = s.render("Le guardie del re ti cercano. Cavalca, raccogli i "
                      "provviste, scendi e combatti.", True, (226, 222, 210))
        screen.blit(t1, t1.get_rect(center=(W // 2, 184)))
        screen.blit(t2, t2.get_rect(center=(W // 2, 220)))

    if knight.state in (ST_DEAD, ST_WIN):
        screen.blit(_veil((10, 12, 20, 165) if knight.state == ST_WIN
                          else (44, 8, 8, 175)), (0, 0))
        t = f.render("FUGA RIUSCITA" if knight.state == ST_WIN else "SEI CADUTO",
                     True, (250, 226, 150) if knight.state == ST_WIN else (240, 170, 160))
        sub = s.render("Premi R per ricominciare", True, (230, 226, 210))
        screen.blit(t, t.get_rect(center=(W // 2, H // 2 - 12)))
        screen.blit(sub, sub.get_rect(center=(W // 2, H // 2 + 22)))


if __name__ == "__main__":
    run()
