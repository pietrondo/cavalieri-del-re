"""Regression tests for the speed work: caches must return the same pixels
they would have drawn, and the hit-stop must freeze time without breaking."""

import os
import sys
import unittest

os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame

import game
import sprites

pygame.init()
pygame.display.set_mode((1, 1))


class PoseCacheTests(unittest.TestCase):
    def test_angles_within_one_step_share_one_cache_entry(self):
        rig = sprites.make_human_rig(game.HUMAN_S)
        ang, lift = sprites.rider_pose(0.3, riding=0.0, moving=1.0)
        step = sprites.ANGLE_STEP
        ang = {k: round(v / step) * step for k, v in ang.items()}  # on the grid
        a, _ = sprites.render_human(rig, ang, (0.0, lift))
        nudged = {k: v + sprites.ANGLE_STEP * 0.1 for k, v in ang.items()}
        b, _ = sprites.render_human(rig, nudged, (0.0, lift))
        self.assertIs(a, b)   # same snapped pose: no second rasterisation

    def test_cache_stays_bounded(self):
        rig = sprites.make_human_rig(game.HUMAN_S)
        for i in range(sprites._CACHE_MAX + 50):
            sprites.render(rig, {"thigh": i * 0.05}, (0.0, 0.0))
        self.assertLessEqual(len(sprites._RENDER_CACHE), sprites._CACHE_MAX)


class FontAndShadowCacheTests(unittest.TestCase):
    def test_font_is_built_once_per_size(self):
        self.assertIs(game.font(22), game.font(22))

    def test_contact_shadow_surface_is_reused(self):
        surf = pygame.Surface((64, 64))
        game.contact_shadow(surf, 32, 32, 20)
        game.contact_shadow(surf, 40, 32, 20)
        self.assertEqual(len([k for k in game._SHADOWS if k[0] == 20]), 1)


class HitStopTests(unittest.TestCase):
    def test_fx_starts_without_hitstop(self):
        self.assertEqual(game.Fx().hitstop, 0.0)

    def test_heavy_hit_sets_hitstop_and_parry_sets_it_too(self):
        knight = game.Knight(0.0)
        knight.attack = 0.5
        knight.combo_step = 2          # finisher: a heavy hit
        knight.gallop = False
        foe = game.Guard(knight.x + 40)
        fx = game.Fx()
        knight.sword_hit([foe], fx)
        self.assertGreater(fx.hitstop, 0.0)


class HitReactionTests(unittest.TestCase):
    """Regression: a stunned guard froze in its idle stance and a struck knight
    showed no reaction at all."""

    def test_stunned_guard_recoils_then_recovers(self):
        g = game.Guard(100.0)
        g.stun = 0.45
        hit = g.pose()[0]["torso"]
        g.stun = 0.0
        idle = g.pose()[0]["torso"]
        self.assertLess(hit, idle)

    def test_knight_leans_back_on_knockback(self):
        k = game.Knight(100.0)
        k.knock = 0.0
        rest = k.pose()[0]["torso"]
        k.knock = 0.20
        self.assertLess(k.pose()[0]["torso"], rest)


class FinisherStepTests(unittest.TestCase):
    """Regression: the finisher swung at a hit zone the body had already left."""

    def _knight(self):
        from collections import defaultdict
        k = game.Knight(100.0)
        k.on_horse = False
        k.combo_step = 2
        k.gallop = False
        return k, defaultdict(bool)

    def test_finisher_steps_forward_during_the_strike(self):
        k, keys = self._knight()
        k.attack = 0.5
        before = k.x
        k.update(0.05, keys, [])
        self.assertGreater(k.x, before)

    def test_no_step_outside_the_strike_window(self):
        k, keys = self._knight()
        k.attack = 0.9
        before = k.x
        k.update(0.05, keys, [])
        self.assertEqual(k.x, before)


class GuardGaitTests(unittest.TestCase):
    """Regression: every enemy started at phase 0 and marched in unison."""

    def test_guards_do_not_start_in_unison(self):
        phases = {round(game.Guard(100.0 + i * 30).phase, 3) for i in range(8)}
        self.assertGreater(len(phases), 1)

    def test_guards_walk_at_different_paces(self):
        speeds = {round(game.Guard(100.0 + i * 30).speed, 3) for i in range(8)}
        self.assertGreater(len(speeds), 1)


if __name__ == "__main__":
    unittest.main()


class RiderGaitTests(unittest.TestCase):
    """Regression: a mounted rider was frozen in the saddle, because the sway
    was multiplied by a `moving` flag that is always 0 while riding."""

    def test_mounted_rider_sways_with_the_stride(self):
        poses = [sprites.rider_pose(p / 8.0, riding=1.0, moving=1.0)[0]
                 for p in range(8)]
        thighs = {round(a["thigh"], 3) for a in poses}
        self.assertGreater(len(thighs), 1)

    def test_standing_horse_gives_no_rider_sway(self):
        still = [sprites.rider_pose(p / 8.0, riding=1.0, moving=0.0)[0]
                 for p in range(8)]
        self.assertEqual(len({round(a["thigh"], 3) for a in still}), 1)
