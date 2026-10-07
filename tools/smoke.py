"""Headless smoke test: drives the knight across level 1 and checks the
invariant that broke silently - every actor must be drawn in SCREEN space,
so its blit position has to follow the camera.

    python tools/smoke.py
"""

import os
import sys

os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

pygame.init()
import game  # noqa: E402
import sprites  # noqa: E402

BLITS = []
W_BOUND = 700.0   # the game's own cull keeps draws well inside this
_real_blit = sprites.blit


def _spy_blit(surf, img, rig, x, y, flip=False):
    BLITS.append(x)
    return _real_blit(surf, img, rig, x, y, flip)


sprites.blit = _spy_blit


def main():
    screen = pygame.display.set_mode((game.W, game.H))
    knight = game.Knight(60.0)
    foes = [game.Guard(400.0), game.Guard(900.0, "rider"),
            game.Guard(1200.0, "spear")]
    pickups = [game.Pickup(x, k) for x, k in game.level_pickups()]

    keys = {k: False for k in (pygame.K_a, pygame.K_d, pygame.K_LEFT,
                               pygame.K_RIGHT, pygame.K_w, pygame.K_UP,
                               pygame.K_LSHIFT, pygame.K_RSHIFT)}
    keys[pygame.K_d] = keys[pygame.K_RSHIFT] = True

    dt = 1 / 60
    cam = 0.0
    offscreen = 0
    for step in range(1400):
        if step == 200:
            knight.toggle_mount()        # dismount mid-run
        if step == 400:
            knight.toggle_mount()        # and get back on
        if step % 37 == 0:
            knight.start_attack()
        knight.update(dt, keys, foes)
        for e in foes:
            e.tick(dt)
            # stand in for the spawner: foes are always placed relative to the
            # player, they never sit at a fixed world x
            if abs(e.tx - knight.x) > 1500:
                e.x = knight.x + 600 if e.horse else knight.x - 400
                if e.horse:
                    e.horse.x = e.x

        cam += ((knight.x - game.W * 0.38) - cam) * min(1.0, dt * 6)
        cam = max(-120.0, min(cam, game.world.GOAL_X + 120.0 - game.W * 0.3))

        BLITS.clear()
        for p in pickups:
            p.update(dt)
        knight.draw(screen, cam)
        for e in foes:
            # the same cull game.py applies, so a foe that fell behind is not
            # drawn at all instead of being drawn off screen
            if abs(e.tx - cam - game.W / 2) < game.W:
                e.draw(screen, cam)

        # The cull above bounds a foe's screen x to (-W/2, 3W/2); a draw in
        # WORLD space instead lands thousands of pixels out, which is what
        # this bound is here to catch.
        for bx in BLITS:
            if not (-W_BOUND < bx < game.W + W_BOUND):
                offscreen += 1

    assert knight.x > 500, "the knight never moved (x=%r)" % knight.x
    assert offscreen == 0, ("%d actor blits landed off screen: the draws are "
                            "not in screen space" % offscreen)
    assert knight.hp > 0, "the knight died during a scripted run"
    print("smoke ok: knight reached x=%.0f, hp=%d, %d draws all on screen"
          % (knight.x, knight.hp, 1400))


if __name__ == "__main__":
    main()
