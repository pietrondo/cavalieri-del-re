"""Smoke test + sprite sheet + in-game composite.

    python tools/preview.py

Renders tools/preview.png so the rigs can be eyeballed without a window, and
asserts the rest poses are coherent (a broken chain fails here, not on screen).
"""

import os
import sys

os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

pygame.init()
import sprites  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "preview.png")


def blit_rig(sheet, img, rig, x, y, flip=False):
    sprites.blit(sheet, img, rig, x, y, flip)


def sheet_rows():
    horse = sprites.make_horse_rig(coat=sprites.CRIMSON_D, trim=sprites.GOLD)
    knight = sprites.make_human_rig(1.0)
    guard = sprites.make_human_rig(0.9, sprites.GREY, sprites.GREY_D,
                                   sprites.OCHRE, sprites.OCHRE_D,
                                   weapon="sword", plume=False, shield=True)
    rider = sprites.make_human_rig(0.96, sprites.GREY, sprites.GREY_D,
                                   sprites.GREY_D, sprites.BLACK, weapon="none",
                                   plume=False, shield=False,
                                   crest=sprites.GOLD, lance=True)
    return [
        ("horse gallop", horse, lambda ph: sprites.horse_pose(3.0, ph)),
        ("horse walk", horse, lambda ph: sprites.horse_pose(0.7, ph)),
        ("knight run", knight, lambda ph: sprites.rider_pose(ph, riding=0.0,
                                                            moving=1.0)),
        ("knight swing", knight,
         lambda ph: sprites.rider_pose(ph, riding=0.0, moving=0.0, attack=ph)),
        ("guard run", guard, lambda ph: sprites.rider_pose(ph, riding=0.0,
                                                           moving=1.0)),
        ("rider lunge", rider, lambda ph: sprites.rider_pose(ph, riding=1.0,
                                                             moving=1.0,
                                                             reach=ph)),
    ]


PHASES = [i / 8 for i in range(8)]


def demo():
    rows = sheet_rows()
    cw, ch = 190, 250
    sheet = pygame.Surface((cw * len(PHASES), ch * len(rows)))
    sheet.fill((122, 148, 178))
    f = pygame.font.Font(None, 18)
    for r, (label, rig, pose) in enumerate(rows):
        y0 = r * ch
        pygame.draw.line(sheet, (90, 112, 138), (0, y0), (sheet.get_width(), y0))
        sheet.blit(f.render(label, True, (20, 26, 40)), (4, y0 + 3))
        is_horse = rig is rows[0][1]
        for c, ph in enumerate(PHASES):
            ang, lift = pose(ph)
            fn = sprites.render_horse if is_horse else sprites.render_human
            img, _ = fn(rig, ang, (0.0, lift))
            sheet.blit(img, (c * cw + cw // 2 - rig.w,
                             y0 + ch - rig.h - 10))

    # the mounted knight, assembled the same way game.py does it
    horse = sprites.make_horse_rig(coat=sprites.CRIMSON_D, trim=sprites.GOLD)
    knight = sprites.make_human_rig(1.0)
    strip = pygame.Surface((cw * len(PHASES), ch), pygame.SRCALPHA)
    strip.fill((122, 148, 178))
    for c, ph in enumerate(PHASES):
        ha, hb = sprites.horse_pose(3.0, ph)
        ra, rlift = sprites.rider_pose(ph, riding=1.0, moving=1.0)
        base = (c * cw + cw // 2, ch - 10)
        hi, _ = sprites.render_horse(horse, ha, (0.0, hb))
        blit_rig(strip, hi, horse, base[0], base[1])
        ri, _ = sprites.render_human(knight, ra, (0.0, rlift - 36))
        blit_rig(strip, ri, knight, base[0], base[1])
    out = pygame.Surface((sheet.get_width(), sheet.get_height() + ch))
    out.blit(sheet, (0, 0))
    out.blit(strip, (0, sheet.get_height()))
    pygame.image.save(out, OUT)
    print("wrote", OUT)

    # cheap regression check: every rig solves, and the rest pose closes
    for label, rig, pose in rows:
        for ph in PHASES:
            ang, lift = pose(ph)
            tr = rig.solve(ang, (0.0, lift))
            for jn, (jx, jy, _a) in tr.items():
                assert -rig.w * 1.2 < jx < rig.w * 1.2, (label, jn, jx)
                assert -rig.h * 1.2 < jy < rig.h * 1.2, (label, jn, jy)
    print("rig bounds ok")


if __name__ == "__main__":
    demo()
