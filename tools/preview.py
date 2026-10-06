"""Preview: renders a sprite sheet so the rigs can be eyeballed headless.

    python tools/preview.py
"""

import os
import sys

os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

pygame.init()
import sprites  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def cell(sheet, cx, cy, cw, ch, img, rig, ground_off=0):
    x = cx + cw // 2 - rig.w
    y = cy + ch - rig.h + ground_off
    sheet.blit(img, (x, y))
    pygame.draw.line(sheet, (40, 50, 70), (cx, cy + ch - rig.h + 6),
                     (cx + 40, cy + ch - rig.h + 6))


def demo():
    horse = sprites.make_horse_rig(coat=sprites.CRIMSON_D, trim=sprites.GOLD)
    knight = sprites.make_human_rig(1.0)
    guard = sprites.make_human_rig(0.9, sprites.GREY, sprites.GREY_D,
                                   sprites.OCHRE, sprites.OCHRE_D,
                                   weapon="sword", plume=False, shield=True)
    rider = sprites.make_human_rig(0.96, sprites.GREY, sprites.GREY_D,
                                   sprites.GREY_D, sprites.BLACK, weapon="none",
                                   plume=False, shield=False,
                                   crest=sprites.GOLD, lance=True)

    rows = [
        ("horse gallop", horse, lambda ph: sprites.horse_pose(3.0, ph)),
        ("horse walk", horse, lambda ph: sprites.horse_pose(0.8, ph)),
        ("knight mounted", knight, lambda ph: sprites.rider_pose(ph, riding=1.0,
                                                                moving=1.0)),
        ("knight run", knight, lambda ph: sprites.rider_pose(ph, riding=0.0,
                                                            moving=1.0)),
        ("knight swing", knight,
         lambda ph: sprites.rider_pose(ph, riding=0.0, moving=0.0, attack=ph)),
        ("knight lunge", knight, lambda ph: sprites.rider_pose(ph, riding=0.0,
                                                              moving=1.0,
                                                              reach=ph)),
        ("guard run", guard, lambda ph: sprites.rider_pose(ph, riding=0.0,
                                                           moving=1.0)),
        ("rider lunge", rider, lambda ph: sprites.rider_pose(ph, riding=1.0,
                                                             moving=1.0,
                                                             reach=ph)),
    ]
    phases = [0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875]
    cw, ch = 190, 250
    cols = len(phases)
    sheet = pygame.Surface((cw * cols, ch * len(rows)))
    sheet.fill((122, 148, 178))
    f = pygame.font.Font(None, 18)
    for r, (label, rig, pose) in enumerate(rows):
        y0 = r * ch
        pygame.draw.line(sheet, (90, 112, 138), (0, y0), (sheet.get_width(), y0))
        sheet.blit(f.render(label, True, (20, 26, 40)), (4, y0 + 3))
        for c, ph in enumerate(phases):
            ang, lift = pose(ph)
            if rig is horse:
                img, _ = sprites.render_horse(rig, ang, (0.0, lift))
            else:
                img, _ = sprites.render_human(rig, ang, (0.0, lift))
            cell(sheet, c * cw, y0, cw, ch, img, rig)
    out = os.path.join(HERE, "preview.png")
    pygame.image.save(sheet, out)
    print("wrote", out)

    # cheapest possible regression check: every rig solves and stays on canvas
    for name, rig, pose in rows:
        for ph in phases:
            ang, lift = pose(ph)
            tr = rig.solve(ang, (0.0, lift))
            for jn, (jx, jy, _ja) in tr.items():
                assert -rig.w < jx < rig.w * 1.6, (name, jn, jx)
                assert -rig.h * 1.4 < jy < rig.h * 1.2, (name, jn, jy)
    ang, lift = sprites.rider_pose(0.3, riding=1.0, moving=1.0)
    assert lift < 0, lift
    print("rig bounds ok")


if __name__ == "__main__":
    demo()