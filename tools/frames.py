"""Render real game frames headless, so the whole scene can be eyeballed.

    python tools/frames.py

Writes tools/frames.png: four camera positions across level 1, drawn with the
same calls game.py makes, with a mounted knight and a guard in shot.
"""

import os
import sys

os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

pygame.init()
import sprites  # noqa: E402
import world  # noqa: E402
import game  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 960, 540
PHASES = 7.0


def frame(cam_x, knight_x, horse_phase, guard_x_, t):
    surf = pygame.Surface((W, H))
    world.draw_sky(surf)
    world.draw_background(surf, cam_x)
    world.draw_goal(surf, cam_x, t)
    world.draw_ground(surf, cam_x)
    world.draw_props(surf, cam_x)
    world.draw_castle(surf, cam_x)
    world.draw_portcullis(surf, cam_x, 1.0)
    return surf


def main():
    # every actor is drawn in SCREEN space, like game.py does it
    horse = sprites.make_horse_rig(coat=sprites.CRIMSON_D, trim=sprites.GOLD, scale=game.HORSE_S)
    knight = sprites.make_human_rig(game.HUMAN_S)
    guard = sprites.make_human_rig(0.9 * game.HUMAN_S, sprites.GREY, sprites.GREY_D,
                                   sprites.OCHRE, sprites.OCHRE_D,
                                   weapon="sword", plume=False, shield=True)
    rider = sprites.make_human_rig(0.96 * game.HUMAN_S, sprites.GREY, sprites.GREY_D,
                                   sprites.GREY_D, sprites.BLACK, weapon="none",
                                   plume=False, shield=False,
                                   crest=sprites.GOLD, lance=True)
    ehorse = sprites.make_horse_rig(coat=sprites.GREY_D, trim=sprites.GOLD, scale=game.HORSE_S)

    cams = [-60.0, 700.0, 2400.0, 4700.0]
    strip = pygame.Surface((W, H * len(cams)))
    ground = world.GROUND
    for i, cam in enumerate(cams):
        s = frame(cam, i * 1000, i * 0.31, 0, 3.0)

        # mounted knight
        kx = cam + W * 0.38
        game.contact_shadow(s, kx - cam, ground, 48 * game.HORSE_S)
        ha, hb = sprites.horse_pose(4.0, (i * 0.31) % 1.0)
        img, _ = sprites.render_horse(horse, ha, (0.0, hb))
        sprites.blit(s, img, horse, kx - cam, ground)
        ra, rl = sprites.rider_pose((i * 0.31) % 1.0, riding=1.0, moving=1.0)
        img, _ = sprites.render_human(knight, ra, (0.0, rl - game.SEAT))
        sprites.blit(s, img, knight, kx - cam, ground)

        # an enemy rider closing in, and a guard on foot
        ex = kx + 300
        game.contact_shadow(s, ex - cam, ground, 48 * game.HORSE_S)
        eha, ehb = sprites.horse_pose(3.4, (i * 0.2) % 1.0, panic=0.3)
        img, _ = sprites.render_horse(ehorse, eha, (0.0, ehb), flip=True)
        sprites.blit(s, img, ehorse, ex - cam, ground, flip=True)
        era, erl = sprites.rider_pose((i * 0.2) % 1.0, riding=1.0, moving=1.0,
                                      reach=0.8)
        img, _ = sprites.render_human(rider, era, (0.0, erl - game.SEAT), flip=True)
        sprites.blit(s, img, rider, ex - cam, ground, flip=True)

        gx = kx - 340
        game.contact_shadow(s, gx - cam, ground, 22 * game.HUMAN_S)
        ga, gl = sprites.rider_pose((i * 0.44) % 1.0, riding=0.0, moving=1.0)
        img, _ = sprites.render_human(guard, ga, (0.0, gl))
        sprites.blit(s, img, guard, gx - cam, ground)

        for n, kind in enumerate(("heart", "shield", "gold")):
            px, py = cam + 120 + n * 90, ground - 40
            col = ((196, 54, 58), (72, 122, 196), (214, 176, 74))[n]
            pygame.draw.circle(s, (52, 44, 40), (int(px - cam), int(py)), 13)
            pygame.draw.circle(s, col, (int(px - cam), int(py)), 10)
        strip.blit(s, (0, i * H))
        pygame.draw.line(strip, (0, 0, 0), (0, i * H), (W, i * H))

    out = os.path.join(HERE, "frames.png")
    pygame.image.save(strip, out)
    print("wrote", out, "GROUND", ground, "GOAL", world.GOAL_X)

    keys = sorted(world.palette().keys())
    print("world.palette() keys:", ", ".join(keys))


if __name__ == "__main__":
    main()
