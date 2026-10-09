"""Le pose: passo del cavallo, sella del cavaliere, spada, lancia, caduta.

Una pose e' solo una tabella di scostamenti di angolo sulle ossa: nessun
disegno, nessuna geometria. Il sistema scheletro fa il resto.
"""

import math

from bones import TAU, ease, lerp


# --------------------------------------------------------------------------
# Poses
# --------------------------------------------------------------------------
# rest angles, spelled out so the pose deltas below read as intent
DOWN = 1.53
ARM_DOWN = 0.92
FORE_DOWN = 1.00

_RIDE = {
    "torso": 0.05, "neck": -0.12, "head": -0.06,
    "arm_f": -0.30, "fa_f": -0.55,
    # mounted sword carried forward at a slight up angle. Do NOT raise this arm
    # like the on-foot carry: the enemy rider's lance hangs off the same bones,
    # and a raised arm points the lance up over the shoulder and off the canvas.
    "arm_n": -0.35, "fa_n": -0.22, "hand": 0.00,
    "thigh": -0.35, "shin": 0.55, "foot": 0.22,
    "thigh_f": -0.30, "shin_f": 0.50, "foot_f": 0.20,
    "plume": -0.25, "crest": -0.20,
}
_FOOT = {
    "torso": 0.06, "neck": 0.0, "head": 0.0,
    "arm_f": 0.06, "fa_f": -0.18,
    "arm_n": -0.88, "fa_n": -0.30, "hand": 0.00,
    "thigh": 0.0, "shin": 0.0, "foot": 0.0,
    "thigh_f": 0.0, "shin_f": 0.0, "foot_f": 0.0,
    "plume": 0.0, "crest": 0.0,
}
LANCE_REST = 0.02
COUCH_ARM_N, COUCH_FA_N = -0.16, 0.30


def horse_pose(speed, phase, air=0.0, panic=0.0):
    """Four offset leg cycles: hind push, suspension, fore reach and gather."""
    p = TAU * phase
    a = {}
    motion = min(1.0, max(0.0, speed) / 7.0) * (1 - air)
    gallop = min(1.0, max(0.0, speed) / 6.0) * (1 - panic * 0.4)
    # Rotary gallop, one stride = one cycle: the forelegs strike together
    # (lead pair), the hindlegs follow as a pair ~0.36 later, then the
    # suspension phase. The old offsets put the hind pair 0.18 apart, so the
    # gait looked like a trot with extra bounce.
    for hip, knee, hoof, off, hind in (
        ("leg_fn", "knee_fn", "hoof_fn", 0.00, False),
        ("leg_ff", "knee_ff", "hoof_ff", 0.08, False),
        ("leg_hn", "knee_hn", "hoof_hn", 0.38, True),
        ("leg_hf", "knee_hf", "hoof_hf", 0.46, True),
    ):
        u = p + TAU * off
        swing = math.sin(u)
        gather = max(0.0, math.cos(u - 0.55))
        stance = max(0.0, -math.cos(u - 0.55))
        if hind:
            # Hind leg: drive backward, tuck forward under belly with articulated hock and hoof
            a[hip] = motion * (-0.66 * swing + 0.12)
            a[knee] = motion * (-0.70 * gather + 0.12 * stance)
            a[hoof] = motion * (0.22 * swing - 0.32 * gather + 0.10 * stance)
        else:
            # Foreleg: reach forward, fold carpus cleanly during recovery, cushion impact on stance
            a[hip] = motion * (-0.60 * swing - 0.10)
            a[knee] = motion * (0.62 * gather + 0.08 * stance)
            a[hoof] = motion * (0.22 * swing - 0.30 * gather - 0.08 * stance)
        if air:
            a[hip] += air * (0.45 if hind else -0.5)
            a[knee] += air * (-0.35 if hind else 0.55)
    a["rump"] = -0.07 * gallop + 0.05 * math.sin(p + 0.8) * gallop
    a["chest"] = 0.05 * math.sin(p + 1.1) * gallop
    a["neck"] = (0.16 * gallop + 0.06 * math.sin(p + 1.2) * motion + panic * 0.20)
    a["crest"] = -0.10 * gallop
    a["head"] = 0.10 * math.sin(p + 1.0) - 0.14 * gallop + panic * 0.10
    a["tail"] = 0.26 * math.sin(p * 0.5 + 0.4) - 0.08 + panic * 0.40
    a["tail2"] = 0.20 * math.sin(p * 0.5 + 1.1) + panic * 0.32
    a["mane"] = 0.05 * math.sin(p + 0.3)
    a["forelock"] = 0.06 * math.sin(p * 2 + 0.6)
    bob = -3.2 * gallop * abs(math.sin(p + 0.45)) * (1 - air)
    return a, (-5.5 * air if air else bob)


# Sword cuts, one keyframe table per combo. Values are ADDITIVE offsets per
# bone, keyed by swing progress k = 1 - attack: 0 is the first frame of the
# cut, 1 the moment it has recovered. Every table starts and ends neutral,
# so each cut grows out of, and settles back into, the raised carry pose in
# _FOOT. arm_n/fa_n already carry the +0.96/+0.14 that compensates that raised
# base, so the absolute swing is the same as when the base was a low guard.
# `hand` is the wrist pivot (see _human): it swings the whole sword so the
# blade leads the cut instead of staying rigid on the forearm.
SWORD_CUTS = {
    0: (  # fendente discendente: guardia alta, taglio diagonale in avanti
        (0.00, {}),
        (0.30, {"arm_n": -0.14, "fa_n": 0.69, "hand": -0.35,
                "arm_f": 0.30, "fa_f": -0.15, "torso": -0.14, "head": -0.10}),
        (0.66, {"arm_n": 1.24, "fa_n": -0.51, "hand": 0.35,
                "arm_f": -0.40, "fa_f": 0.28, "torso": 0.30, "head": 0.14}),
        (1.00, {}),
    ),
    1: (  # fendente ascendente: carica in basso, risalita larga
        (0.00, {}),
        (0.30, {"arm_n": 1.28, "fa_n": -0.06, "hand": 0.25,
                "arm_f": 0.25, "fa_f": -0.10, "torso": 0.16, "head": 0.06}),
        (0.66, {"arm_n": 0.24, "fa_n": -0.01, "hand": -0.20,
                "arm_f": -0.35, "fa_f": 0.25, "torso": -0.18, "head": -0.10}),
        (1.00, {}),
    ),
    2: (  # affondo finisher: camera al fianco, stoccata in avanti
        (0.00, {}),
        (0.30, {"arm_n": 0.71, "fa_n": 0.64, "hand": -0.15,
                "arm_f": 0.30, "fa_f": -0.20, "torso": -0.16, "head": -0.10}),
        (0.66, {"arm_n": 0.36, "fa_n": -0.81, "hand": 0.85,
                "arm_f": -0.50, "fa_f": 0.30, "torso": 0.34, "head": 0.10}),
        (1.00, {}),
    ),
}


def _cut_offsets(k, keys):
    """Piecewise-eased additive bone offsets at swing progress k in [0, 1]."""
    for (k0, a0), (k1, a1) in zip(keys, keys[1:]):
        if k <= k1:
            u = ease((k - k0) / max(1e-6, k1 - k0))
            return {n: lerp(a0.get(n, 0.0), a1.get(n, 0.0), u)
                    for n in a0.keys() | a1.keys()}
    return {}


def rider_pose(phase, riding=1.0, moving=0.0, air=0.0, attack=0.0, reach=0.0, combo=0):
    """Blend the mounted pose (riding=1) into an on-foot run/strike (riding=0).

    -> (angles, hip_lift). hip_lift raises the whole rider, which is how the
    mounted pose clears the horse's back.
    """
    p = TAU * phase
    riding = max(0.0, min(1.0, riding))
    a = {name: lerp(_FOOT[name], _RIDE[name], riding) for name in _RIDE}
    sw, cw = math.sin(p) * moving, math.cos(p) * moving
    sw2, cw2 = math.sin(p + math.pi) * moving, math.cos(p + math.pi) * moving

    # Blend the motion as well as the rest stance. Articulated knee flexion,
    # plantarflexion push-off and dorsiflexion recovery.
    foot_motion = {
        "thigh": -0.55 * sw,
        "shin": (0.85 * max(0.0, sw) + 0.25 * max(0.0, -cw) * max(0.0, -sw)) * moving,
        "foot": (0.30 * max(0.0, -sw) - 0.25 * max(0.0, sw)) * moving,
        "thigh_f": -0.55 * sw2,
        "shin_f": (0.85 * max(0.0, sw2) + 0.25 * max(0.0, -cw2) * max(0.0, -sw2)) * moving,
        "foot_f": (0.30 * max(0.0, -sw2) - 0.25 * max(0.0, sw2)) * moving,
        "torso": 0.05 * moving - 0.12 * air,
        "arm_f": 0.42 * sw2,
        "arm_n": -0.38 * sw,
        "fa_n": 0.20 * sw,
    }
    ride_motion = {
        "thigh": 0.09 * sw,
        "shin": -0.13 * sw,
        "thigh_f": 0.09 * sw2,
        "shin_f": -0.13 * sw2,
        "torso": 0.10 * moving,
    }
    for name in foot_motion.keys() | ride_motion.keys():
        a[name] += lerp(foot_motion.get(name, 0.0),
                        ride_motion.get(name, 0.0), riding)
    foot_lift = -0.5 * (1.0 - math.cos(p * 2)) * 2.2 * moving - 5.0 * air
    ride_lift = -3.0 + 0.9 * math.sin(p * 2) * moving
    lift = lerp(foot_lift, ride_lift, riding)

    if reach > 0.0:
        # lance couched under the arm: the shaft's world angle is
        # arm + forearm + LANCE_REST, so both arms are aimed to flatten it.
        a["arm_n"] = lerp(a["arm_n"], COUCH_ARM_N, reach)
        a["fa_n"] = lerp(a["fa_n"], COUCH_FA_N, reach)
        a["arm_f"] = lerp(a["arm_f"], -0.34, reach)
        a["fa_f"] = lerp(a["fa_f"], 0.28, reach)
        a["torso"] += -0.06 * reach
    elif attack > 0.0:
        # The cut is a chain of additive offsets that starts and ends neutral,
        # so it grows out of the walk/ride base and settles back into it. The
        # footfall's own arm swing is damped out while the blade is in flight,
        # or the running figure wobbles through the swing.
        # NB: k is left LINEAR here. _cut_offsets already eases each segment, so
        # easing k too doubled the peak angular rate and the strike strobed.
        k = 1.0 - attack  # 0 at the start of the swing, 1 when recovered
        damp = ease(min(1.0, min(k, 1.0 - k) / 0.12)) * (1.0 - riding)
        lead = 1.0 - riding * 0.35   # a rider leaning over the saddle leads less
        for name in ("arm_n", "fa_n", "arm_f"):
            a[name] = a.get(name, 0.0) - foot_motion.get(name, 0.0) * damp
        for name, off in _cut_offsets(k, SWORD_CUTS[combo % 3]).items():
            a[name] = a.get(name, 0.0) + off * (lead if name in ("torso", "head") else 1.0)

    # plume and crest ride the stride: a dead-still one looks painted on
    swing = 0.35 + 0.65 * moving
    a["plume"] = a.get("plume", 0.0) + 0.06 * math.sin(p * 2.0 + 0.6) * swing
    a["crest"] = a.get("crest", 0.0) + 0.05 * math.sin(p * 2.0 + 1.1) * swing
    return a, lift


def dead_pose(progress, on_horse=False):
    """Death collapse: actor falls back, knees buckle, body rests on the ground."""
    p = ease(min(1.0, progress / 0.55))
    a = {
        "torso": lerp(0.06, -1.15, p),
        "neck": lerp(0.0, -0.25, p),
        "head": lerp(0.0, -0.45, p),
        "arm_n": lerp(0.08, 0.82, p),
        "fa_n": lerp(-0.16, 0.28, p),
        "arm_f": lerp(0.06, 0.68, p),
        "fa_f": lerp(-0.18, 0.22, p),
        "thigh": lerp(0.0, 0.48, p),
        "shin": lerp(-0.30, -1.05, p),
        "foot": lerp(0.0, 0.30, p),
        "thigh_f": lerp(0.0, 0.32, p),
        "shin_f": lerp(-0.26, -0.92, p),
        "foot_f": lerp(0.0, 0.25, p),
        "plume": lerp(0.0, -0.40, p),
        "crest": lerp(0.0, -0.30, p),
    }
    lift = 25.0 * p
    return a, lift
