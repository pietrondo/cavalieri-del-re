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
ATTACK_TIME = 0.40
HIT_LO, HIT_HI = 0.10, 0.27
SWORD_REACH = 72
LANCE_REACH = 112
INVULN = 0.80
MOUNT_TIME = 0.50
MOUNT_DIST = 58.0
SHIELD_TIME = 6.0

ST_HORSE, ST_FOOT, ST_DIS, ST_MOUNT, ST_DEAD, ST_WIN = (
    "horse", "foot", "dismount", "mount", "dead", "win")


def ease(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def font(size):
    return pygame.font.Font(None, size)


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
        ang, lift = self.pose()
        img, _ = sprites.render_human(self.rig, ang, (0.0, lift), dark=dark,
                                      flip=self.face < 0)
        sprites.blit(surf, img, self.rig, self.x, self.y, flip=self.face < 0)


class Horse:
    """Enough horse for a mounted actor to stand on."""

    def __init__(self, x, coat=None, trim=None):
        self.rig = sprites.make_horse_rig(coat=coat, trim=trim)
        self.x = float(x)
        self.phase = 0.0
        self.speed = 0.0
        self.face = -1
        self.y = GROUND

    def draw(self, surf, cam_x, dark=1.0):
        ang, bob = sprites.horse_pose(self.speed, self.phase, panic=0.25)
        img, _ = sprites.render_horse(self.rig, ang, (0.0, bob), dark=dark,
                                      flip=self.face < 0)
        sprites.blit(surf, img, self.rig, self.x, self.y, flip=self.face < 0)


class Guard(Actor):
    """Guardia del re (a piedi) o cavaliere nemico (in sella con lancia)."""

    def __init__(self, x, kind="foot"):
        if kind == "rider":
            super().__init__(x, sprites.make_human_rig(
                0.96, sprites.GREY, sprites.GREY_D, sprites.GREY_D,
                sprites.BLACK, weapon="none", plume=False, shield=False,
                crest=sprites.GOLD, lance=True), 7, 3.1)
            self.dmg, self.reach = 2, 92.0
            self.horse = Horse(x, coat=sprites.GREY_D, trim=sprites.GOLD)
            self.on_horse = True
        elif kind == "spear":
            super().__init__(x, sprites.make_human_rig(
                0.94, sprites.GREY, sprites.GREY_D, sprites.OCHRE,
                sprites.OCHRE_D, weapon="spear", plume=False, shield=False), 3, 2.5)
            self.dmg, self.reach, self.on_horse = 1, 70.0, False
        else:
            super().__init__(x, sprites.make_human_rig(
                0.90, sprites.GREY, sprites.GREY_D, sprites.OCHRE,
                sprites.OCHRE_D, weapon="sword", plume=False, shield=True), 4, 2.0)
            self.dmg, self.reach, self.on_horse = 1, 62.0, False
        self.kind = kind
        self.cooldown = random.uniform(0.4, 1.4)
        self.telegraph = 0.0

    @property
    def tx(self):
        return self.horse.x if self.horse else self.x

    def pose(self):
        if self.attack > 0:
            # couched lance: thrust, not slash
            ang, lift = sprites.rider_pose(self.phase, riding=1.0 if self.on_horse
                                          else 0.0, moving=0.0,
                                          reach=ease(1.0 - self.attack))
            return ang, lift
        return sprites.rider_pose(self.phase,
                                  riding=1.0 if self.on_horse else 0.0,
                                  moving=1.0, air=0.0)

    def draw(self, surf, cam_x, dark=1.0):
        if self.horse:
            self.horse.draw(surf, cam_x, dark=dark)
        ang, lift = self.pose()
        img, _ = sprites.render(self.rig, ang, root=(0.0, lift - 4),
                                dark=dark, flip=self.face < 0)
        sprites.blit(surf, img, self.rig, self.tx, self.y, flip=self.face < 0)

    def hurt(self, dmg, from_x):
        self.hp -= dmg
        self.flash = 0.18
        self.stun = 0.30
        self.x += 14 if from_x < self.tx else -14
        if self.horse:
            self.horse.x += 14 if from_x < self.tx else -14
        if self.hp <= 0:
            self.hp = 0
            self.dead = True


class Knight(Actor):
    def __init__(self, x):
        super().__init__(x, sprites.make_human_rig(1.0), 10, FOOT_SPEED)
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

    # -- mount ------------------------------------------------------------
    def toggle_mount(self):
        if self.state == ST_HORSE:
            self.state, self.st = ST_DIS, 0.0
        elif self.state == ST_FOOT and abs(self.x - self.horse.x) < 78:
            self.state, self.st = ST_MOUNT, 0.0

    def grounded(self):
        return self.y >= GROUND - 0.6

    # -- input ------------------------------------------------------------
    def update(self, dt, keys, foes):
        self.tick(dt)
        self.invuln = max(0.0, self.invuln - dt)
        self.knock = max(0.0, self.knock - dt)
        self.cooldown = max(0.0, self.cooldown - dt)
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
            return

        if self.attack > 0:
            self.attack = max(0.0, self.attack - dt / ATTACK_TIME)
            self.sword_hit(foes)

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
            self.horse.x += ax * spd
            self.horse.phase += dt * (0.9 + abs(ax) * spd * 0.30)
            self.horse.speed = abs(ax) * spd
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
        self.attack = 1.0
        self.hit_ids.clear()
        self.cooldown = 0.10
        return True

    def sword_hit(self, foes):
        if not (HIT_LO <= self.attack <= HIT_HI):
            return
        reach = LANCE_REACH if self.gallop else SWORD_REACH
        ox = self.x + self.face * reach * 0.45
        for e in foes:
            if e.dead or id(e) in self.hit_ids:
                continue
            if abs(e.tx - ox) < reach and abs(e.y - self.y) < 64:
                self.hit_ids.add(id(e))
                e.hurt(3 if self.gallop else 2, self.x)

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
        return True

    # -- pose -------------------------------------------------------------
    def pose(self):
        riding = 1.0 if self.state in (ST_HORSE, ST_MOUNT) else 0.0
        if self.state == ST_DIS:
            riding = 1.0 - min(1.0, self.st / MOUNT_TIME)
        ang, lift = sprites.rider_pose(
            self.phase, riding=riding,
            moving=0.0 if self.on_horse else 1.0,
            air=self.air,
            attack=0.0 if self.gallop else max(0.0, self.attack),
            reach=1.0 if self.gallop else 0.0)
        return ang, lift - (36 if riding > 0.5 else 0)

    def draw(self, surf, cam_x):
        self.horse.draw(surf, cam_x)
        ang, lift = self.pose()
        img, _ = sprites.render(self.rig, ang, root=(0.0, lift),
                                flip=self.face < 0)
        sprites.blit(surf, img, self.rig, self.x, self.y, flip=self.face < 0)
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
        self.parts, self.pops, self.rings = [], [], []

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

    def draw(self, surf, cam_x):
        f = font(26)
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

    while True:
        dt = min(clock.tick(FPS) / 1000.0, 1 / 30.0)
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
                        reach = LANCE_REACH if knight.gallop else SWORD_REACH
                        fx.ring(knight.x + knight.face * reach * 0.5, GROUND - 46,
                                (230, 220, 190))
                if ev.key == pygame.K_r and knight.state in (ST_DEAD, ST_WIN):
                    knight = Knight(60.0)
                    foes, kills = [], 0
                    pickups = [Pickup(x, k) for x, k in level_pickups()]
                    fx = Fx()
                    spawn_i, elapsed, intro, gate = 0, 0.0, 1.6, 0.0
                    won = False
                    banner, banner_t = "", 0.0

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

        knight.update(dt, keys, foes)

        # foes
        alive = 0
        for e in foes:
            if e.dead:
                e.dead_t += dt
                continue
            alive += 1
            e.tick(dt)
            dx = knight.x - e.tx
            if abs(dx) > 2 and e.stun <= 0:
                e.face = 1 if dx > 0 else -1
                if e.horse:
                    e.horse.face = e.face
            if e.attack > 0:
                e.attack = max(0.0, e.attack - dt / ATTACK_TIME)
                if HIT_LO <= e.attack <= HIT_HI and e.telegraph:
                    e.telegraph = 0
                    if abs(e.tx - knight.x) < e.reach and abs(e.y - knight.y) < 70:
                        if knight.take_hit(e.dmg, e.tx):
                            fx.burst(knight.x, knight.y - 48, (206, 64, 56), 12)
                            fx.pop(knight.x, knight.y - 82, "-%d" % e.dmg,
                                   (255, 130, 118))
                            fx.ring(knight.x, knight.y - 44, (200, 70, 60))
                continue
            e.telegraph = 0
            if e.stun <= 0:
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
                        e.attack, e.telegraph = 1.0, 1
                        e.cooldown = rng.uniform(1.0, 1.9)
                        fx.pop(e.tx, knight.y - 120, "!", (250, 210, 120))
            e.x = max(world.GATE_X0 - 220.0, e.x)

        kills += sum(1 for e in foes if e.dead and e.dead_t < dt * 2)
        foes = [e for e in foes if not (e.dead and e.dead_t > 3.2)]

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

        # ---- draw ----
        world.draw_sky(screen)
        world.draw_background(screen, cam_x)
        world.draw_goal(screen, cam_x, elapsed)
        world.draw_ground(screen, cam_x)
        world.draw_props(screen, cam_x)
        world.draw_castle(screen, cam_x)
        world.draw_portcullis(screen, cam_x, gate)

        for p in pickups:
            if not p.taken:
                p.draw(screen, cam_x)
        for e in sorted(foes, key=lambda g: g.y):
            if abs(e.tx - cam_x - W / 2) < W:
                e.draw(screen, cam_x, dark=0.72 if e.flash > 0 else 1.0)
        knight.draw(screen, cam_x)
        if knight.flash > 0:
            veil = pygame.Surface((W, H), pygame.SRCALPHA)
            veil.fill((255, 90, 80, int(70 * knight.flash / 0.22)))
            screen.blit(veil, (0, 0))
        fx.draw(screen, cam_x)

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
        panel = pygame.Surface((W, 104), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 175))
        screen.blit(panel, (0, 150))
        t1 = f.render("LIVELLO 1 - LA FUGA DA CASTEL ROSSO", True, (244, 226, 180))
        t2 = s.render("Le guardie del re ti cercano. Cavalca, raccogli i "
                      "provviste, scendi e combatti.", True, (226, 222, 210))
        screen.blit(t1, t1.get_rect(center=(W // 2, 184)))
        screen.blit(t2, t2.get_rect(center=(W // 2, 220)))

    if knight.state in (ST_DEAD, ST_WIN):
        veil = pygame.Surface((W, H), pygame.SRCALPHA)
        veil.fill((10, 12, 20, 165) if knight.state == ST_WIN else (44, 8, 8, 175))
        screen.blit(veil, (0, 0))
        t = f.render("FUGA RIUSCITA" if knight.state == ST_WIN else "SEI CADUTO",
                     True, (250, 226, 150) if knight.state == ST_WIN else (240, 170, 160))
        sub = s.render("Premi R per ricominciare", True, (230, 226, 210))
        screen.blit(t, t.get_rect(center=(W // 2, H // 2 - 12)))
        screen.blit(sub, sub.get_rect(center=(W // 2, H // 2 + 22)))


if __name__ == "__main__":
    run()