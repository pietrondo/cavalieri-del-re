"""Sprites as Python: zero image assets in this repo.

Questo e' solo la porta d'ingresso: il sistema sta in tre pezzi, perche' da solo
faceva quasi mille righe.

    bones.py  il meccanismo: Bone, Rig, FK, rasterizzazione, cache, luci
    rigs.py   i due scheletri del gioco: cavallo e cavaliere
    poses.py  le pose: passo, sella, spada, lancia, caduta

Ogni personaggio e' una gerarchia di ossa. La posa di riposo e' scritta in
coordinate mondo semplici - piedi a y=0, rivolto verso +x, y punta in giu' -
quindi un rig e' una lista di "dove stanno queste giunzioni" e nient'altro.
Ogni frame:

  1. si applica una posa (scostamenti di angolo per osso) sulla posa di riposo,
  2. si risolve la cinematica diretta,
  3. si rasterizzano capsule e poligoni su una superficie sopraccampionata 3x,
  4. si smoothscala, ed e' da li' che viene l'antialiasing.

Gli angoli di riposo sono espliciti e `Rig` verifica che ogni arto arrivi
davvero alla giunzione figlia: una posa di riposo sbagliata falla rumorosamente
invece di disegnare spazzatura.
"""

from bones import (ANGLE_STEP, CONTOUR_R, LIGHT, OUTLINE_W, RIM, SS, TAU,
                   Bone, Draw, Rig, blit, clear_cache, lerp, mix_angle, render,
                   render_horse, render_human, _CACHE_MAX, _RENDER_CACHE)
from poses import dead_pose, horse_pose, rider_pose
from rigs import (BLACK, CRIMSON, CRIMSON_D, GOLD, GREY, GREY_D, HORSE,
                  HORSE_D, HOOF, MANE, OCHRE, OCHRE_D, STEEL, STEEL_D, WOOD,
                  Builder, make_horse_rig, make_human_rig)