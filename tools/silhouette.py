"""Silhouette / value-contrast sheet: the readability check the cast lacks.

    python tools/silhouette.py

Renders each actor at GAME scale in four ways, as the character-design
checklist requires:

  colour      - what the game shows
  silhouette  - filled solid, so only the SHAPE can be judged
  grayscale   - value contrast, to catch two parts of the same lightness
  thumbnail   - the silhouette at 32px tall: it must still read there

A shape that fails the silhouette or the thumbnail row is the reason an
actor "non si capisce".
"""

import os
import sys

os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

pygame.init()
import game  # noqa: E402
import sprites  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "silhouette.png")
THUMB_H = 32


def compose(items, pad=8):
    """items = [(img, rig)] whose feet sit at (rig.w, rig.h) in the image.
    Returns one surface with every item's feet at the same point."""
    w = 2 * max(rig.w for _i, rig in items) + 2 * pad
    h = 2 * max(rig.h for _i, rig in items) + 2 * pad
    out = pygame.Surface((w, h), pygame.SRCALPHA)
    fx, fy = w // 2, h - pad
    for img, rig in items:
        out.blit(img, (fx - rig.w, fy - rig.h))
    return out


def horse_rider(coat, trim, human_kw, horse_face=1, phase=0.3):
    horse = sprites.make_horse_rig(coat=coat, trim=trim, scale=game.HORSE_S)
    rider = sprites.make_human_rig(game.HUMAN_S, **human_kw)
    ha, hb = sprites.horse_pose(3.0, phase)
    hi, _ = sprites.render_horse(horse, ha, (0.0, hb), flip=horse_face < 0)
    ra, rl = sprites.rider_pose(0.25, riding=1.0, moving=1.0)
    ri, _ = sprites.render_human(rider, ra, (0.0, rl - game.SEAT),
                                 flip=horse_face < 0)
    return compose([(hi, horse), (ri, rider)])


def on_foot(rig_kw):
    rig = sprites.make_human_rig(game.HUMAN_S, **rig_kw)
    ang, lift = sprites.rider_pose(0.25, riding=0.0, moving=1.0)
    img, _ = sprites.render_human(rig, ang, (0.0, lift))
    return compose([(img, rig)])


def black(img):
    s = img.copy()
    s.fill((0, 0, 0, 255), special_flags=pygame.BLEND_RGBA_MULT)
    return s


def thumb(img):
    w = max(1, int(img.get_width() * THUMB_H / img.get_height()))
    return pygame.transform.smoothscale(img, (w, THUMB_H))


def main():
    knight = dict()
    guard = dict(steel=sprites.GREY, steel_d=sprites.GREY_D,
                 cloth=sprites.OCHRE, cloth_d=sprites.OCHRE_D,
                 plume=False)
    lancer = dict(steel=sprites.GREY, steel_d=sprites.GREY_D,
                  cloth=sprites.GREY_D, cloth_d=sprites.BLACK, weapon="none",
                  plume=False, shield=False, crest=sprites.GOLD, lance=True)
    cast = [
        ("cavaliere a cavallo", horse_rider(sprites.CRIMSON_D, sprites.GOLD,
                                            knight)),
        ("cavaliere a piedi", on_foot(knight)),
        ("guardia", on_foot(guard)),
        ("cavaliere nemico", horse_rider(sprites.GREY_D, sprites.GREY, lancer,
                                         horse_face=-1)),
    ]

    rows = ["colore", "silhouette", "grigi", "thumb 32px"]
    # size the cells to the actual actors: a rig can grow its canvas, and fixed
    # cells would crop it.
    CW = max(img.get_width() for _l, img in cast) + 24
    CH = max(img.get_height() for _l, img in cast) + 28
    sheet = pygame.Surface((CW * len(cast), CH * len(rows)))
    sheet.fill((238, 238, 240))
    f = pygame.font.Font(None, 18)
    for c, (label, img) in enumerate(cast):
        variants = [img, black(img), pygame.transform.grayscale(img),
                    thumb(black(img))]
        for r, var in enumerate(variants):
            cell = pygame.Rect(c * CW, r * CH, CW, CH)
            if r in (1, 3):
                pygame.draw.rect(sheet, (214, 216, 222), cell)
            sheet.blit(var, (cell.x + (CW - var.get_width()) // 2,
                             cell.y + (CH - var.get_height()) // 2))
        sheet.blit(f.render(label, True, (30, 30, 40)), (c * CW + 4, 3))
    pygame.image.save(sheet, OUT)
    print("wrote", OUT, sheet.get_size())


if __name__ == "__main__":
    main()
