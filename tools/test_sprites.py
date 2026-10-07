"""Geometry checks for the procedural character rigs."""

import math
import os
import sys
import unittest
from unittest.mock import patch

os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame

import game
import sprites

pygame.init()


class SpriteRigTests(unittest.TestCase):
    def test_rest_hooves_meet_ground_anchor(self):
        for scale in (1.0, game.HORSE_S):
            rig = sprites.make_horse_rig(scale=scale)
            tr = rig.solve()
            for side in ("hn", "hf", "fn", "ff"):
                self.assertAlmostEqual(tr[f"hoof_{side}"][1], 0,
                                       delta=1.5 * scale)

    def test_horse_chains_and_render_bounds(self):
        for rig in (sprites.make_horse_rig(),
                    sprites.make_horse_rig(sprites.CRIMSON_D, sprites.GOLD),
                    sprites.make_horse_rig(scale=game.HORSE_S)):
            for speed in (0, 2.5, 8.0):
                for phase in (0, .25, .5, .75):
                    angles, bob = sprites.horse_pose(speed, phase)
                    tr = rig.solve(angles, (0, bob))
                    for x, y, angle in tr.values():
                        self.assertTrue(all(map(math.isfinite, (x, y, angle))))
                    for side in ("hn", "hf", "fn", "ff"):
                        upper = rig.map[f"leg_{side}"]
                        lower = tr[f"knee_{side}"]
                        start = tr[f"leg_{side}"]
                        tip = (start[0] + upper.length * math.cos(start[2]),
                               start[1] + upper.length * math.sin(start[2]))
                        self.assertAlmostEqual(tip[0], lower[0], delta=.7)
                        self.assertAlmostEqual(tip[1], lower[1], delta=.7)
                    img, _ = sprites.render_horse(rig, angles, (0, bob))
                    bounds = img.get_bounding_rect()
                    self.assertGreaterEqual(bounds.left, 2)
                    self.assertGreaterEqual(bounds.top, 2)
                    self.assertLess(bounds.right, img.get_width() - 2)
                    self.assertLess(bounds.bottom, img.get_height() - 2)
                    head = tr["head"]
                    tip = (head[0] + rig.map["head"].length * math.cos(head[2]),
                           head[1] + rig.map["head"].length * math.sin(head[2]))
                    self.assertLess(math.dist(tip, tr["muzzle"][:2]),
                                    14 * rig.map["head"].length / 24)

    def test_gallop_has_distinct_reach_gather_push(self):
        rig = sprites.make_horse_rig()
        paths = {}
        for name in ("hn", "hf", "fn", "ff"):
            paths[name] = []
            for phase in (0, .25, .5, .75):
                angles, _ = sprites.horse_pose(8.0, phase)
                tr = rig.solve(angles)
                hoof = tr[f"hoof_{name}"]
                hip = tr[f"leg_{name}"]
                paths[name].append(hoof[0] - hip[0])
            self.assertGreater(max(paths[name]) - min(paths[name]), 30,
                               (name, paths[name]))
        self.assertGreater(max(abs(a-b) for a, b in zip(paths["hn"],
                            paths["hf"])), 10)
        self.assertGreater(max(abs(a-b) for a, b in zip(paths["fn"],
                            paths["ff"])), 10)

    def test_root_anchor_does_not_draw_as_ground_dot(self):
        rig = sprites.make_horse_rig()
        angles, _ = sprites.horse_pose(0, 0)
        image, _ = sprites.render_horse(rig, angles, (0, 0))
        self.assertEqual(image.get_at((rig.w, rig.h)).a, 0)

    def test_human_variants_have_connected_poses(self):
        variants = ({},
                    dict(weapon="sword", plume=False, shield=True),
                    dict(weapon="spear", plume=False, shield=False),
                    dict(weapon="none", plume=False, shield=False,
                         crest=sprites.GOLD, lance=True))
        for kwargs in variants:
            rig = sprites.make_human_rig(game.HUMAN_S, **kwargs)
            for riding, attack, reach in ((0, 0, 0), (0, .6, 0),
                                          (1, 0, 0), (1, 0, 1)):
                angles, lift = sprites.rider_pose(.25, riding=riding,
                                                  moving=1, attack=attack,
                                                  reach=reach)
                tr = rig.solve(angles, (0, lift))
                for joint in tr.values():
                    self.assertTrue(all(map(math.isfinite, joint)))
                for parent, child in (("arm_n", "fa_n"), ("thigh", "shin"),
                                      ("shin", "foot"), ("thigh_f", "shin_f")):
                    start, end = tr[parent], tr[child]
                    length = rig.map[parent].length
                    self.assertAlmostEqual(math.dist(start[:2], end[:2]),
                                           length, delta=.7)
                weapon = ("lance" if kwargs.get("lance") else
                          "shaft" if kwargs.get("weapon") == "spear" else
                          "hilt")
                forearm = tr["fa_n"]
                hand_tip = (forearm[0] + rig.map["fa_n"].length * math.cos(forearm[2]),
                            forearm[1] + rig.map["fa_n"].length * math.sin(forearm[2]))
                self.assertLess(math.dist(hand_tip, tr[weapon][:2]),
                                2 * game.HUMAN_S)
                for flip in (False, True):
                    img, _ = sprites.render_human(rig, angles, (0, lift),
                                                   flip=flip)
                    bounds = img.get_bounding_rect()
                    self.assertGreater(bounds.left, 0)
                    self.assertGreater(bounds.top, 0)
                    self.assertLess(bounds.right, img.get_width())
                    self.assertLess(bounds.bottom, img.get_height())
                    self.assertLessEqual(img.get_height(),
                                         rig.h + int(rig.h * .2) + 3)
                    if riding:
                        mounted, _ = sprites.render_human(
                            rig, angles, (0, lift - game.SEAT), flip=flip)
                        self.assertGreater(mounted.get_bounding_rect().top, 0)
            still_angles, still_lift = sprites.rider_pose(0, riding=0,
                                                          moving=0)
            still = rig.solve(still_angles, (0, still_lift))
            for foot in ("foot", "foot_f"):
                self.assertLess(abs(still[foot][1]), 6 * game.HUMAN_S)

    def test_mounted_enemy_uses_shared_seat(self):
        guard = game.Guard(400, kind="rider")
        guard.face = -1
        surf = pygame.Surface((800, 600))
        _, lift = guard.pose()
        roots = []
        original = sprites.render_human

        def record(rig, angles, root, **kwargs):
            roots.append(root)
            return original(rig, angles, root, **kwargs)

        with patch.object(sprites, "render_human", side_effect=record):
            guard.draw(surf, 0)
        self.assertEqual(len(roots), 1)
        self.assertAlmostEqual(roots[0][1], lift - game.SEAT)

    def test_mounted_pelvis_meets_saddle(self):
        horse = sprites.make_horse_rig(scale=game.HORSE_S)
        saddle = horse.solve()["saddle"]
        for scale in (game.HUMAN_S, .96 * game.HUMAN_S):
            human = sprites.make_human_rig(scale)
            angles, lift = sprites.rider_pose(0, riding=1)
            pelvis = human.solve(angles, (0, lift - game.SEAT))["torso"]
            self.assertLess(abs(pelvis[1] - saddle[1]), 13)
            self.assertLess(abs(pelvis[0] - saddle[0]), 15)

    def test_dismount_pose_does_not_jump_at_midpoint(self):
        knight = game.Knight(400)
        knight.state = game.ST_DIS
        roots = []
        for progress in (.49, .51):
            knight.st = progress * game.MOUNT_TIME
            angles, lift = knight.pose()
            roots.append(knight.rig.solve(angles, (0, lift))["torso"][1])
        self.assertLess(abs(roots[0] - roots[1]), 8)

    def test_mid_transition_limb_motion_is_continuous(self):
        rig = sprites.make_human_rig(game.HUMAN_S)
        for phase in (0, .25, .5, .75):
            poses = []
            for riding in (.49, .51):
                angles, lift = sprites.rider_pose(phase, riding=riding,
                                                  moving=1)
                poses.append(rig.solve(angles, (0, lift - game.SEAT * riding)))
            for joint in ("foot", "foot_f", "fa_n", "fa_f", "head"):
                self.assertLess(math.dist(poses[0][joint][:2],
                                          poses[1][joint][:2]), 8,
                                (phase, joint))

    def test_remount_pose_starts_on_foot(self):
        knight = game.Knight(400)
        knight.state = game.ST_FOOT
        foot_angles, foot_lift = knight.pose()
        knight.state = game.ST_MOUNT
        knight.st = 0
        mount_angles, mount_lift = knight.pose()
        self.assertAlmostEqual(foot_lift, mount_lift, delta=2)
        self.assertAlmostEqual(foot_angles["thigh"], mount_angles["thigh"],
                               delta=.1)

    def test_preview_mounted_figures_use_game_seat(self):
        from tools import preview
        roots = []
        original = sprites.render_human

        def record(rig, angles, root, **kwargs):
            roots.append(root[1])
            return original(rig, angles, root, **kwargs)

        cast = preview.rigs()
        sheet = pygame.Surface((preview.CW, preview.CH))
        for row in ("hero mounted", "enemy mounted"):
            for facing in (1, -1):
                for phase in preview.PHASES:
                    roots.clear()
                    with patch.object(sprites, "render_human", side_effect=record):
                        preview.draw_cell(sheet, cast, row, phase, facing,
                                          preview.CW // 2, preview.CH - 14)
                    _, lift = sprites.rider_pose(phase, riding=1.0, moving=1.0,
                                                  reach=phase if row == "enemy mounted" else 0)
                    self.assertEqual(len(roots), 1)
                    self.assertAlmostEqual(roots[0], lift - game.SEAT)


if __name__ == "__main__":
    unittest.main()
