import json
import os
from copy import deepcopy
from pathlib import Path
import random
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

import virtual_pet


class PetWorldTests(unittest.TestCase):
	def setUp(self):
		self.directory = tempfile.TemporaryDirectory()
		self.addCleanup(self.directory.cleanup)
		self.path = Path(self.directory.name) / "pets.json"
		self.now = [1000.0]
		self.world = virtual_pet.PetWorld(self.path, clock=lambda: self.now[0])

	def test_only_requested_owner_names_are_available(self):
		expected = ("文武", "文怡然", "文燃然", "欧泽轩", "欧阳沐希")
		self.assertEqual(virtual_pet.OWNER_NAMES, expected)
		self.assertEqual(virtual_pet.PetGame(self.world).owner_names(), list(expected))
		with self.assertRaises(ValueError):
			self.world.create_owner("陌生人")

	def test_legacy_owner_can_be_renamed_without_losing_pet(self):
		owner = self.world.create_owner("文武")
		pet = self.world.adopt(owner, "capybara")
		self.world.pet(owner, pet)["experience"] = 42
		self.world.owner(owner)["name"] = "星星"
		self.world._save()
		original = self.path.read_bytes()
		restored = virtual_pet.PetWorld(self.path, clock=lambda: self.now[0])
		self.assertEqual(self.path.read_bytes(), original)
		with self.assertRaises(ValueError):
			restored.rename_owner(owner, "陌生人")
		self.assertEqual(self.path.read_bytes(), original)
		restored.rename_owner(owner, "文怡然")
		reloaded = virtual_pet.PetWorld(self.path, clock=lambda: self.now[0])
		self.assertEqual(reloaded.owner(owner)["name"], "文怡然")
		self.assertEqual(reloaded.pet(owner, pet)["experience"], 42)

	def test_failed_owner_claim_preserves_old_name_and_pet(self):
		owner = self.world.create_owner("文武")
		pet = self.world.adopt(owner, "capybara")
		self.world.owner(owner)["name"] = "星星"
		self.world._save()
		original = self.path.read_bytes()
		with patch.object(virtual_pet.os, "replace", side_effect=OSError("disk error")):
			with self.assertRaises(OSError):
				self.world.rename_owner(owner, "文武")
		self.assertEqual(self.world.owner(owner)["name"], "星星")
		self.assertEqual(self.world.pet(owner, pet)["species"], "capybara")
		self.assertEqual(self.path.read_bytes(), original)

	def test_second_adoption_requires_release(self):
		owner = self.world.create_owner("文武")
		first_pet = self.world.adopt(owner, "capybara")
		with self.assertRaises(ValueError):
			self.world.adopt(owner, "dinosaur")
		self.assertEqual([pet["id"] for pet in self.world.owner(owner)["pets"]], [first_pet])

	def test_owners_and_replacement_pets_are_saved_independently(self):
		first = self.world.create_owner("文武")
		second = self.world.create_owner("文怡然")
		capybara = self.world.adopt(first, "capybara")
		pikachu = self.world.adopt(second, "pikachu")
		self.world.care(first, capybara, "feed")
		self.world.release(first, capybara)
		dinosaur = self.world.adopt(first, "dinosaur")
		self.world.rename(first, dinosaur, "泡泡")
		restored = virtual_pet.PetWorld(self.path, clock=lambda: self.now[0])
		self.assertEqual([owner["name"] for owner in restored.owners], ["文武", "文怡然"])
		self.assertEqual(len(restored.owner(first)["pets"]), 1)
		self.assertEqual(restored.pet(first, dinosaur)["name"], "泡泡")
		self.assertEqual(restored.pet(second, pikachu)["stats"], virtual_pet.INITIAL_STATS)

	def test_legacy_pets_are_preserved_until_explicitly_retained(self):
		owner = self.world.create_owner("文武")
		first = self.world.adopt(owner, "capybara")
		legacy = deepcopy(self.world.pet(owner, first))
		legacy.update(id="legacy", species="dinosaur", name="小恐龙")
		self.world.owner(owner)["pets"].append(legacy)
		self.world._save()
		original = self.path.read_bytes()
		restored = virtual_pet.PetWorld(self.path, clock=lambda: self.now[0])
		self.assertEqual(len(restored.owner(owner)["pets"]), 2)
		self.assertEqual(self.path.read_bytes(), original)
		with self.assertRaises(ValueError):
			restored.adopt(owner, "pikachu")
		restored.retain_pet(owner, "legacy")
		self.assertEqual([pet["id"] for pet in restored.owner(owner)["pets"]], ["legacy"])
		self.assertEqual(len(virtual_pet.PetWorld(self.path).owner(owner)["pets"]), 1)

	def test_legacy_sleeping_pet_is_migrated_without_overwriting_the_save(self):
		owner = self.world.create_owner("文武")
		pet_id = self.world.adopt(owner, "capybara")
		pet = self.world.pet(owner, pet_id)
		for key in ("food", "dirt", "cooldowns", "task_days", "last_pat_at", "activity"):
			pet.pop(key)
		pet["sleeping"] = True
		self.world._save()
		original = self.path.read_bytes()
		restored = virtual_pet.PetWorld(self.path, clock=lambda: self.now[0])
		self.assertEqual(self.path.read_bytes(), original)
		self.assertEqual(restored.pet(owner, pet_id)["activity"]["kind"], "sleep")
		self.now[0] += 15 * 60
		restored.finish_due(owner, pet_id)
		self.assertFalse(restored.pet(owner, pet_id)["sleeping"])
		self.assertEqual(restored.pet(owner, pet_id)["stats"]["energy"], 100)

	def test_invalid_activity_does_not_overwrite_the_save(self):
		owner = self.world.create_owner("文武")
		pet = self.world.adopt(owner, "capybara")
		self.world.pet(owner, pet)["activity"] = {"kind": "wash", "started_at": 1000, "ends_at": "invalid"}
		self.world._save()
		original = self.path.read_bytes()
		with self.assertRaises(virtual_pet.SaveError):
			virtual_pet.PetWorld(self.path)
		self.assertEqual(self.path.read_bytes(), original)

	def test_failed_release_preserves_the_original_pet(self):
		owner = self.world.create_owner("文武")
		pet = self.world.adopt(owner, "capybara")
		original = self.path.read_bytes()
		with patch.object(virtual_pet.os, "replace", side_effect=OSError("disk error")):
			with self.assertRaises(OSError):
				self.world.release(owner, pet)
		self.assertEqual(self.world.pet(owner, pet)["species"], "capybara")
		self.assertEqual(self.path.read_bytes(), original)

	def test_bath_takes_fifteen_minutes_and_cools_down_after_completion(self):
		owner = self.world.create_owner("文武")
		pet_id = self.world.adopt(owner, "capybara")
		pet = self.world.pet(owner, pet_id)
		pet["dirt"] = 2
		pet["stats"]["hygiene"] = 35
		self.world.care(owner, pet_id, "wash")
		self.now[0] += 899
		before = self.world.visible_pet(owner, pet_id)
		self.assertEqual(before["activity"]["kind"], "wash")
		self.assertEqual(before["dirt"], 2)
		self.now[0] += 1
		self.world.finish_due(owner, pet_id)
		finished = virtual_pet.PetWorld(self.path, clock=lambda: self.now[0]).pet(owner, pet_id)
		self.assertIsNone(finished["activity"])
		self.assertEqual(finished["dirt"], 0)
		self.assertEqual(finished["stats"]["hygiene"], 100)
		with self.assertRaisesRegex(ValueError, "冷却"):
			self.world.care(owner, pet_id, "wash")
		self.now[0] += 30 * 60
		self.world.care(owner, pet_id, "wash")

	def test_care_sleep_growth_and_game_rewards(self):
		owner = self.world.create_owner("文燃然")
		pet = self.world.adopt(owner, "teto")
		self.world.care(owner, pet, "play", won=True)
		self.assertEqual(self.world.pet(owner, pet)["stars"], 0)
		self.now[0] += 12
		self.world.finish_due(owner, pet)
		self.assertEqual(self.world.pet(owner, pet)["stars"], 3)
		self.assertEqual(self.world.pet(owner, pet)["experience"], 6)
		self.world.care(owner, pet, "sleep")
		self.now[0] += 15 * 60
		self.world.finish_due(owner, pet)
		self.assertEqual(self.world.pet(owner, pet)["stats"]["energy"], 100)
		self.assertFalse(self.world.pet(owner, pet)["sleeping"])
		for _ in range(2):
			self.world.care(owner, pet, "explore")
			self.now[0] += 10 * 60
			self.world.finish_due(owner, pet)
			self.now[0] += 20 * 60
		self.assertEqual(virtual_pet.growth_stage(self.world.pet(owner, pet)), "宝宝")
		self.world.care(owner, pet, "explore")
		self.now[0] += 10 * 60
		self.world.finish_due(owner, pet)
		self.assertEqual(virtual_pet.growth_stage(self.world.pet(owner, pet)), "小伙伴")

	def test_actions_survive_restart_and_cancellation_refunds_food(self):
		owner = self.world.create_owner("文武")
		pet = self.world.adopt(owner, "capybara")
		self.world.care(owner, pet, "feed")
		self.assertEqual(self.world.pet(owner, pet)["food"], 3)
		with self.assertRaisesRegex(ValueError, "中"):
			self.world.care(owner, pet, "pat")
		self.now[0] += 5
		restored = virtual_pet.PetWorld(self.path, clock=lambda: self.now[0])
		self.assertEqual(restored.pet(owner, pet)["activity"]["kind"], "feed")
		self.assertTrue(restored.cancel_activity(owner, pet))
		self.assertEqual(restored.pet(owner, pet)["food"], 4)
		self.assertIsNone(restored.pet(owner, pet)["activity"])
		restored.care(owner, pet, "feed")
		self.now[0] += 10
		restored.finish_due(owner, pet)
		self.assertEqual(restored.pet(owner, pet)["stats"]["hunger"], 100)
		self.assertEqual(restored.pet(owner, pet)["food"], 3)
		self.assertEqual(restored.pet(owner, pet)["stars"], 1)
		with self.assertRaisesRegex(ValueError, "冷却"):
			restored.care(owner, pet, "feed")

	def test_exploration_uses_energy_and_food_meter_and_can_make_dirt(self):
		owner = self.world.create_owner("文武")
		pet = self.world.adopt(owner, "capybara")
		self.world.rng = Mock(random=Mock(return_value=0.1))
		self.world.care(owner, pet, "explore")
		self.now[0] += 10 * 60
		self.world.finish_due(owner, pet)
		returned = self.world.pet(owner, pet)
		self.assertEqual(returned["dirt"], 1)
		self.assertLess(returned["stats"]["hunger"], 65)
		self.assertLess(returned["stats"]["energy"], 71)
		self.assertEqual(returned["food"], 7)
		self.assertEqual(returned["stars"], 4)
		self.assertEqual(returned["experience"], 15)
		with self.assertRaisesRegex(ValueError, "冷却"):
			self.world.care(owner, pet, "explore")
		self.world.care(owner, pet, "wash")
		self.now[0] += 899
		self.assertEqual(self.world.visible_pet(owner, pet)["dirt"], 1)
		self.now[0] += 1
		self.world.finish_due(owner, pet)
		self.assertEqual(self.world.pet(owner, pet)["dirt"], 0)
		self.assertEqual(self.world.pet(owner, pet)["stats"]["hygiene"], 100)

	def test_offline_completion_is_awarded_once_and_cooldown_uses_finish_time(self):
		owner = self.world.create_owner("文武")
		pet = self.world.adopt(owner, "capybara")
		self.world.rng = Mock(random=Mock(return_value=0.99))
		self.world.care(owner, pet, "explore")
		self.now[0] += 60 * 60
		restored = virtual_pet.PetWorld(self.path, clock=lambda: self.now[0])
		first_view = restored.visible_pet(owner, pet)
		second_view = restored.visible_pet(owner, pet)
		self.assertEqual(first_view["food"], 7)
		self.assertEqual(second_view["food"], 7)
		self.assertEqual(first_view["dirt"], 0)
		self.assertEqual(restored.finish_due(owner, pet), "explore")
		self.assertIsNone(restored.finish_due(owner, pet))
		self.assertEqual(virtual_pet.PetWorld(self.path).pet(owner, pet)["food"], 7)
		restored.care(owner, pet, "explore")

	def test_clock_rollback_does_not_finish_or_skip_a_cooldown(self):
		owner = self.world.create_owner("文武")
		pet = self.world.adopt(owner, "capybara")
		self.world.care(owner, pet, "wash")
		self.now[0] -= 300
		self.assertIsNone(self.world.finish_due(owner, pet))
		self.assertEqual(self.world.visible_pet(owner, pet)["activity"]["kind"], "wash")
		self.now[0] = 1000 + 15 * 60
		self.world.finish_due(owner, pet)
		self.now[0] -= 300
		with self.assertRaisesRegex(ValueError, "冷却"):
			self.world.care(owner, pet, "wash")

	def test_cancel_after_completion_keeps_earned_rewards(self):
		owner = self.world.create_owner("文武")
		pet = self.world.adopt(owner, "capybara")
		self.world.care(owner, pet, "play", won=True)
		self.now[0] += 12
		self.assertFalse(self.world.cancel_activity(owner, pet))
		self.assertEqual(self.world.pet(owner, pet)["stars"], 3)
		self.assertEqual(virtual_pet.PetWorld(self.path).pet(owner, pet)["food"], 5)

	def test_empty_food_and_energy_can_be_recovered_without_waiting_for_a_new_day(self):
		owner = self.world.create_owner("文武")
		pet_id = self.world.adopt(owner, "capybara")
		pet = self.world.pet(owner, pet_id)
		pet["food"] = 0
		pet["stats"]["hunger"] = 0
		pet["stats"]["energy"] = 0
		self.world.care(owner, pet_id, "sleep")
		self.now[0] += 15 * 60
		self.world.finish_due(owner, pet_id)
		self.world.care(owner, pet_id, "play")
		self.now[0] += 12
		self.world.finish_due(owner, pet_id)
		self.assertEqual(self.world.pet(owner, pet_id)["food"], 1)
		self.world.care(owner, pet_id, "feed")
		self.now[0] += 10
		self.world.finish_due(owner, pet_id)
		self.assertGreater(self.world.pet(owner, pet_id)["stats"]["hunger"], 20)

	def test_friendship_decay_pat_cooldown_and_daily_rewards(self):
		owner = self.world.create_owner("文武")
		pet = self.world.adopt(owner, "capybara")
		self.world.pet(owner, pet)["friendship"] = 70
		self.now[0] += 3 * 3600
		self.assertEqual(self.world.visible_pet(owner, pet)["friendship"], 70)
		self.world.care(owner, pet, "pat")
		self.now[0] += 8
		self.world.finish_due(owner, pet)
		self.assertEqual(self.world.pet(owner, pet)["friendship"], 75)
		self.assertEqual(self.world.pet(owner, pet)["food"], 5)
		with self.assertRaisesRegex(ValueError, "冷却"):
			self.world.care(owner, pet, "pat")
		self.now[0] += 6 * 3600
		self.assertAlmostEqual(self.world.visible_pet(owner, pet)["friendship"], 73)
		self.world.care(owner, pet, "pat")
		self.now[0] += 8
		self.world.finish_due(owner, pet)
		self.assertEqual(self.world.pet(owner, pet)["food"], 5)
		self.now[0] += 24 * 3600
		self.world.care(owner, pet, "pat")
		self.now[0] += 8
		self.world.finish_due(owner, pet)
		self.assertEqual(self.world.pet(owner, pet)["food"], 6)

	def test_species_skills_unlock_with_growth_and_have_cooldown(self):
		owner = self.world.create_owner("文武")
		pet = self.world.adopt(owner, "pikachu")
		self.assertEqual(virtual_pet.SKILLS["pikachu"][1][0], "十万伏特")
		with self.assertRaisesRegex(ValueError, "Lv2"):
			self.world.care(owner, pet, "skill", skill=1)
		self.world.care(owner, pet, "skill", skill=0)
		self.assertEqual(self.world.pet(owner, pet)["activity"]["skill"], 0)
		self.now[0] += 8
		self.world.finish_due(owner, pet)
		self.world.pet(owner, pet)["experience"] = 40
		with self.assertRaisesRegex(ValueError, "冷却"):
			self.world.care(owner, pet, "skill", skill=1)
		self.now[0] += 60
		self.world.care(owner, pet, "skill", skill=1)
		self.now[0] += 8
		self.world.finish_due(owner, pet)
		self.now[0] += 60
		with self.assertRaisesRegex(ValueError, "Lv3"):
			self.world.care(owner, pet, "skill", skill=2)
		self.world.pet(owner, pet)["experience"] = 120
		self.world.care(owner, pet, "skill", skill=2)

	def test_long_absence_is_gentle_and_clock_rollback_is_safe(self):
		owner = self.world.create_owner("欧泽轩")
		pet = self.world.adopt(owner, "dinosaur")
		self.now[0] += 100 * 3600
		aged = self.world.visible_pet(owner, pet)
		self.assertEqual(aged["stats"]["hunger"], 46)
		self.assertEqual(aged["stats"]["health"], 100)
		self.world.care(owner, pet, "feed")
		self.now[0] += 10
		self.world.finish_due(owner, pet)
		fed = self.world.pet(owner, pet)["stats"]["hunger"]
		self.now[0] -= 200 * 3600
		self.assertEqual(self.world.visible_pet(owner, pet)["stats"]["hunger"], fed)
		self.assertEqual(len(self.world.owners[0]["pets"]), 1)

	def test_corrupt_save_is_never_overwritten(self):
		self.path.write_text("{broken", encoding="utf-8")
		with self.assertRaises(virtual_pet.SaveError):
			virtual_pet.PetWorld(self.path)
		self.assertEqual(self.path.read_text(encoding="utf-8"), "{broken")

	def test_failed_save_rolls_back_without_damaging_old_file(self):
		owner = self.world.create_owner("文武")
		original = json.loads(self.path.read_text(encoding="utf-8"))
		with patch.object(virtual_pet.os, "replace", side_effect=OSError("disk error")):
			with self.assertRaises(OSError):
				self.world.adopt(owner, "capybara")
		self.assertEqual(self.world.data, original)
		self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), original)
		self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

	def test_owner_names_are_unique_and_released_species_can_be_readopted(self):
		owner = self.world.create_owner("文武")
		with self.assertRaises(ValueError):
			self.world.create_owner("文武")
		first = self.world.adopt(owner, "capybara")
		self.world.release(owner, first)
		second = self.world.adopt(owner, "capybara")
		self.assertNotEqual(first, second)
		self.world.rename(owner, second, "泡泡")
		self.assertEqual(self.world.pet(owner, second)["name"], "泡泡")

	def test_game_stars_buy_and_reuse_accessories(self):
		owner = self.world.create_owner("文武")
		pet = self.world.adopt(owner, "capybara")
		with self.assertRaises(ValueError):
			self.world.equip(owner, pet, "flower")
		self.world.care(owner, pet, "play", won=True)
		self.now[0] += 12
		self.world.finish_due(owner, pet)
		self.now[0] += 5 * 60
		self.world.care(owner, pet, "play", won=True)
		self.now[0] += 12
		self.world.finish_due(owner, pet)
		self.world.equip(owner, pet, "flower")
		self.assertEqual(self.world.pet(owner, pet)["stars"], 1)
		self.world.equip(owner, pet, "none")
		self.world.equip(owner, pet, "flower")
		restored = virtual_pet.PetWorld(self.path)
		self.assertEqual(restored.pet(owner, pet)["equipped"], "flower")
		self.assertEqual(restored.pet(owner, pet)["stars"], 1)


class PetGameTests(unittest.TestCase):
	def setUp(self):
		self.directory = tempfile.TemporaryDirectory()
		self.addCleanup(self.directory.cleanup)
		self.now = [1000.0]
		self.world = virtual_pet.PetWorld(Path(self.directory.name) / "pets.json", clock=lambda: self.now[0])
		self.game = virtual_pet.PetGame(self.world, random.Random(3))

	def test_legacy_owner_is_claimed_only_after_a_name_is_chosen(self):
		owner = self.world.create_owner("文武")
		pet = self.world.adopt(owner, "capybara")
		self.world.pet(owner, pet)["experience"] = 42
		self.world.owner(owner)["name"] = "星星"
		self.world._save()
		original = self.world.path.read_bytes()
		game = self.game
		game.handle_action("K3")
		self.assertEqual(game.view, "owner_migrate")
		game.handle_action("BACK")
		self.assertEqual(self.world.path.read_bytes(), original)
		game.handle_action("K3")
		game.handle_action("CHOOSE_4")
		self.assertEqual(game.view, "pets")
		self.assertEqual(self.world.owner(owner)["name"], "欧阳沐希")
		self.assertEqual(self.world.pet(owner, pet)["experience"], 42)
		self.assertEqual(virtual_pet.PetWorld(self.world.path).owner(owner)["name"], "欧阳沐希")

	def test_full_name_list_does_not_offer_an_extra_owner(self):
		for name in virtual_pet.OWNER_NAMES:
			self.world.create_owner(name)
		game = self.game
		self.assertEqual(game.owner_names(), [])
		self.assertEqual(game.option_count(), 5)
		game.handle_action("CHOOSE_4")
		self.assertEqual(game.view, "pets")
		self.assertEqual(self.world.owner(game.owner_id)["name"], "欧阳沐希")

	def test_legacy_owner_is_preserved_when_all_five_names_are_taken(self):
		for name in virtual_pet.OWNER_NAMES:
			self.world.create_owner(name)
		self.world.owners.append({"id": "legacy", "name": "星星", "pets": []})
		self.world._save()
		original = self.world.path.read_bytes()
		self.game.handle_action("CHOOSE_5")
		self.assertEqual(self.game.view, "owners")
		self.assertIn("旧存档仍保留", self.game.notice)
		self.assertEqual(self.world.path.read_bytes(), original)

	def test_adopt_play_rename_and_switch_owner(self):
		game = self.game
		game.handle_action("K3")
		self.assertEqual(game.view, "owner_name")
		game.handle_action("K3")
		first_owner = game.owner_id
		game.handle_action("K3")
		self.assertEqual(game.view, "adopt")
		game.handle_action("K3")
		first_pet = game.pet_id
		self.assertEqual(game.view, "home")
		game.handle_action("CHOOSE_%d" % virtual_pet.HOME_INDEX["play"])
		self.assertEqual(game.view, "confirm_action")
		game.handle_action("CHOOSE_1")
		self.assertEqual(game.view, "game")
		game.handle_action("CHOOSE_%d" % game.target)
		self.assertEqual(game.view, "home")
		self.assertEqual(self.world.pet(first_owner, first_pet)["stars"], 0)
		self.now[0] += 12
		game.tick()
		self.assertEqual(self.world.pet(first_owner, first_pet)["stars"], 3)
		game.handle_action("CHOOSE_%d" % virtual_pet.HOME_INDEX["rename"])
		game.handle_action("K2")
		game.handle_action("K3")
		self.assertEqual(self.world.pet(first_owner, first_pet)["name"], "团团")
		game.handle_action("BACK")
		game.handle_action("K2")
		game.handle_action("K3")
		self.assertEqual(game.view, "confirm_release")
		game.handle_action("K3")
		self.assertEqual(self.world.pet(first_owner, first_pet)["name"], "团团")
		game.handle_action("K2")
		game.handle_action("K3")
		game.handle_action("K2")
		game.handle_action("K3")
		self.assertEqual(len(self.world.owner(first_owner)["pets"]), 0)
		game.handle_action("K3")
		game.handle_action("K2")
		game.handle_action("K3")
		self.assertEqual(self.world.pet(first_owner, game.pet_id)["species"], "dinosaur")
		game.handle_action("BACK")
		game.handle_action("BACK")
		game.handle_action("K1")
		game.handle_action("K3")
		game.handle_action("K3")
		self.assertNotEqual(first_owner, game.owner_id)
		self.assertEqual(len(self.world.owners), 2)
		self.assertEqual(len(self.world.owner(game.owner_id)["pets"]), 0)
		self.assertIsNone(game.pet_id)
		game.handle_action("K1")
		game.handle_action("K3")
		game.handle_action("CHOOSE_2")
		self.assertEqual(game.view, "home")
		self.assertEqual(self.world.pet(game.owner_id, game.pet_id)["species"], "pikachu")
		self.assertEqual(len(self.world.owner(first_owner)["pets"]), 1)

	def test_legacy_selection_requires_confirmation_and_can_be_cancelled(self):
		owner = self.world.create_owner("文武")
		first = self.world.adopt(owner, "capybara")
		legacy = deepcopy(self.world.pet(owner, first))
		legacy.update(id="legacy", species="dinosaur", name="小恐龙")
		self.world.owner(owner)["pets"].append(legacy)
		self.world._save()
		game = self.game
		game.handle_action("K3")
		game.handle_action("CHOOSE_1")
		self.assertEqual(game.view, "confirm_keep")
		game.handle_action("K3")
		self.assertEqual(len(self.world.owner(owner)["pets"]), 2)
		game.handle_action("CHOOSE_1")
		game.handle_action("K2")
		game.handle_action("K3")
		self.assertEqual(game.view, "home")
		self.assertEqual([pet["id"] for pet in self.world.owner(owner)["pets"]], ["legacy"])

	def test_cannot_buy_with_insufficient_stars_and_can_go_back(self):
		game = self.game
		for _ in range(4):
			game.handle_action("K3")
		game.handle_action("CHOOSE_%d" % virtual_pet.HOME_INDEX["accessory"])
		game.handle_action("K2")
		game.handle_action("K3")
		self.assertEqual(game.view, "accessory")
		self.assertIn("星星不够", game.notice)
		game.handle_action("BACK")
		game.handle_action("BACK")
		game.handle_action("BACK")
		self.assertEqual(game.handle_action("BACK"), "EXIT")

	def test_bath_requires_confirmation_and_completes_on_tick(self):
		game = self.game
		for _ in range(4):
			game.handle_action("K3")
		self.world.pet(game.owner_id, game.pet_id)["dirt"] = 1
		game.handle_action("CHOOSE_%d" % virtual_pet.HOME_INDEX["wash"])
		self.assertEqual(game.view, "confirm_action")
		game.handle_action("K3")
		self.assertIsNone(self.world.pet(game.owner_id, game.pet_id)["activity"])
		game.handle_action("CHOOSE_%d" % virtual_pet.HOME_INDEX["wash"])
		game.handle_action("CHOOSE_1")
		activity = self.world.pet(game.owner_id, game.pet_id)["activity"]
		self.assertEqual(activity["ends_at"] - activity["started_at"], 15 * 60)
		self.now[0] += 899
		game.tick()
		self.assertEqual(self.world.pet(game.owner_id, game.pet_id)["dirt"], 1)
		self.now[0] += 1
		game.tick()
		self.assertEqual(self.world.pet(game.owner_id, game.pet_id)["dirt"], 0)
		self.assertIn("完成", game.notice)
		self.assertIsNone(virtual_pet.PetWorld(self.world.path).pet(game.owner_id, game.pet_id)["activity"])

	def test_cancel_action_requires_confirmation_and_refunds_food(self):
		game = self.game
		for _ in range(4):
			game.handle_action("K3")
		game.handle_action("CHOOSE_%d" % virtual_pet.HOME_INDEX["feed"])
		game.handle_action("CHOOSE_1")
		self.assertEqual(self.world.pet(game.owner_id, game.pet_id)["food"], 3)
		game.handle_action("CHOOSE_%d" % virtual_pet.HOME_INDEX["stop"])
		game.handle_action("K3")
		self.assertIsNotNone(self.world.pet(game.owner_id, game.pet_id)["activity"])
		game.handle_action("CHOOSE_%d" % virtual_pet.HOME_INDEX["stop"])
		game.handle_action("CHOOSE_1")
		self.assertEqual(self.world.pet(game.owner_id, game.pet_id)["food"], 4)
		self.assertIsNone(self.world.pet(game.owner_id, game.pet_id)["activity"])

	def test_skills_and_tasks_start_their_selected_activities(self):
		game = self.game
		for _ in range(4):
			game.handle_action("K3")
		game.handle_action("CHOOSE_%d" % virtual_pet.HOME_INDEX["skill"])
		game.handle_action("CHOOSE_1")
		self.assertEqual(game.view, "skills")
		self.assertIn("Lv2", game.notice)
		self.world.pet(game.owner_id, game.pet_id)["experience"] = 40
		game.handle_action("CHOOSE_1")
		self.assertEqual(game.view, "confirm_action")
		game.handle_action("CHOOSE_1")
		self.assertEqual(self.world.pet(game.owner_id, game.pet_id)["activity"]["skill"], 1)
		self.now[0] += 8
		game.tick()
		game.handle_action("CHOOSE_%d" % virtual_pet.HOME_INDEX["tasks"])
		game.handle_action("CHOOSE_1")
		self.assertEqual(game.pending_action, "pat")
		game.handle_action("CHOOSE_1")
		self.now[0] += 8
		game.tick()
		self.assertEqual(self.world.pet(game.owner_id, game.pet_id)["food"], 5)

	def test_failed_completion_save_retries_without_duplicating_rewards(self):
		game = self.game
		for _ in range(4):
			game.handle_action("K3")
		self.world.care(game.owner_id, game.pet_id, "play", won=True)
		self.now[0] += 12
		with patch.object(virtual_pet.os, "replace", side_effect=OSError("disk error")), patch("builtins.print"):
			game.tick()
		self.assertIn("保存失败", game.notice)
		self.assertEqual(self.world.pet(game.owner_id, game.pet_id)["stars"], 0)
		self.now[0] += 5
		game.tick()
		game.tick()
		self.assertEqual(self.world.pet(game.owner_id, game.pet_id)["stars"], 3)
		self.assertEqual(self.world.pet(game.owner_id, game.pet_id)["food"], 5)


class PetArtTests(unittest.TestCase):
	def test_teto_has_a_distinct_face_and_sleep_expression(self):
		pygame.init()
		art = virtual_pet.PetArt()
		awake = pygame.Surface((160, 160), pygame.SRCALPHA)
		asleep = pygame.Surface((160, 160), pygame.SRCALPHA)
		with patch.object(virtual_pet, "draw_face", wraps=virtual_pet.draw_face) as generic_face:
			art.teto(awake, False)
			art.teto(asleep, True)
			generic_face.assert_not_called()
		self.assertFalse(pygame.image.tobytes(awake, "RGBA") == pygame.image.tobytes(asleep, "RGBA"))

	def test_teto_accessories_do_not_cover_eyes(self):
		pygame.init()
		art = virtual_pet.PetArt()
		species = virtual_pet.SPECIES_BY_KEY["teto"]
		for size in (72, 120, 160):
			sprite_size = size - 8
			sprite_rect = pygame.Rect(0, 0, sprite_size, sprite_size)
			sprite_rect.center = (size // 2, size // 2)
			eyes = pygame.Rect(sprite_rect.left + sprite_size * 58 // 160,
							   sprite_rect.top + sprite_size * 58 // 160,
							   (sprite_size * 47 + 159) // 160,
							   (sprite_size * 23 + 159) // 160)
			plain = pygame.Surface((size, size), pygame.SRCALPHA)
			art.draw(plain, species, plain.get_rect(), 1.0)
			for accessory in ("flower", "ribbon", "crown"):
				with self.subTest(size=size, accessory=accessory):
					dressed = pygame.Surface((size, size), pygame.SRCALPHA)
					art.draw(dressed, species, dressed.get_rect(), 1.0, accessory=accessory)
					self.assertEqual(pygame.image.tobytes(plain.subsurface(eyes), "RGBA"),
									 pygame.image.tobytes(dressed.subsurface(eyes), "RGBA"))

	def test_each_species_and_accessory_renders_on_a_small_surface(self):
		pygame.init()
		art = virtual_pet.PetArt()
		for species in virtual_pet.SPECIES:
			for sleeping, accessory in ((False, "none"), (True, "flower"), (False, "ribbon"), (False, "crown")):
				with self.subTest(species=species.name, sleeping=sleeping, accessory=accessory):
					surface = pygame.Surface((120, 120), pygame.SRCALPHA)
					art.draw(surface, species, surface.get_rect(), 1.0, sleeping, accessory)
					self.assertGreater(surface.get_bounding_rect().width, 40)
					self.assertGreater(surface.get_bounding_rect().height, 40)

	def test_new_species_have_distinct_local_motion(self):
		pygame.init()
		art = virtual_pet.PetArt()
		for key in ("capybara", "dinosaur", "ninetales", "fire_snake", "shinx",
					"rayquaza", "lucario", "pachirisu", "buneary"):
			with self.subTest(species=key):
				species = virtual_pet.SPECIES_BY_KEY[key]
				frames = []
				for now in (0.25, 0.85):
					surface = pygame.Surface((140, 140), pygame.SRCALPHA)
					art.draw_species_motion(surface, species, surface.get_rect().inflate(-20, -20),
									   now, None, 0)
					frames.append(pygame.image.tobytes(surface, "RGBA"))
				self.assertNotEqual(frames[0], frames[1])

	def test_each_activity_moves_the_pet_itself(self):
		pygame.init()
		art = virtual_pet.PetArt()
		missing = []
		for species in virtual_pet.SPECIES:
			activities = [{"kind": kind} for kind in virtual_pet.ACTIVITIES if kind != "skill"]
			activities.extend({"kind": "skill", "skill": index} for index in range(len(virtual_pet.SKILLS[species.key])))
			for activity in activities:
				sleeping = activity["kind"] == "sleep"
				frames, idle_frames = [], []
				for now in (1.15, 1.42, 1.69):
					moving = pygame.Surface((120, 120), pygame.SRCALPHA)
					idle = pygame.Surface((120, 120), pygame.SRCALPHA)
					with patch.object(art, "draw_effect"):
						art.draw(moving, species, moving.get_rect(), now, sleeping, "flower", activity)
						art.draw(idle, species, idle.get_rect(), now, sleeping, "flower")
					frames.append(pygame.image.tobytes(moving, "RGBA"))
					idle_frames.append(pygame.image.tobytes(idle, "RGBA"))
				if len(set(frames)) < 2 or frames == idle_frames:
					missing.append((species.key, activity))
		self.assertFalse(missing, "宠物本体没有动作: %s" % missing)

	def test_teto_moves_her_arms_during_interactions(self):
		pygame.init()
		art = virtual_pet.PetArt()
		species = virtual_pet.SPECIES_BY_KEY["teto"]
		for kind in ("feed", "play", "explore", "wash", "pat", "medicine", "skill"):
			with self.subTest(kind=kind):
				frames = []
				activity = {"kind": kind}
				if kind == "skill":
					activity["skill"] = 0
				with patch.object(art, "animated_pose", side_effect=lambda image, *args: (image, 0, 0)), \
					 patch.object(art, "draw_effect"):
					for now in (0.5, 2.5):
						surface = pygame.Surface((160, 160), pygame.SRCALPHA)
						art.draw(surface, species, surface.get_rect(), now, activity=activity)
						frames.append(pygame.image.tobytes(surface, "RGBA"))
				self.assertFalse(frames[0] == frames[1])

	def test_each_action_and_skill_effect_has_animated_pixels(self):
		pygame.init()
		art = virtual_pet.PetArt()
		effects = ("feed", "play", "explore", "wash", "sleep", "pat", "medicine",
				   "heart", "water", "bubbles", "flower", "dash", "star", "fire", "electric",
				   "thunder", "leaf", "music")
		self.assertLessEqual({effect for skills in virtual_pet.SKILLS.values() for _, effect in skills}, set(effects))
		for effect in effects:
			with self.subTest(effect=effect):
				first = pygame.Surface((120, 120), pygame.SRCALPHA)
				second = pygame.Surface((120, 120), pygame.SRCALPHA)
				art.draw_effect(first, effect, first.get_rect(), 1.0)
				art.draw_effect(second, effect, second.get_rect(), 1.4)
				self.assertGreater(first.get_bounding_rect().width, 0)
				self.assertFalse(pygame.image.tobytes(first, "RGBA") == pygame.image.tobytes(second, "RGBA"), effect)

	def test_interactions_are_visually_distinct_from_skill_effects(self):
		pygame.init()
		art = virtual_pet.PetArt()
		for action, skill in (("play", "star"), ("pat", "heart"), ("wash", "bubbles")):
			with self.subTest(action=action):
				action_surface = pygame.Surface((120, 120), pygame.SRCALPHA)
				skill_surface = pygame.Surface((120, 120), pygame.SRCALPHA)
				art.draw_effect(action_surface, action, action_surface.get_rect(), 1.0)
				art.draw_effect(skill_surface, skill, skill_surface.get_rect(), 1.0)
				self.assertFalse(pygame.image.tobytes(action_surface, "RGBA") ==
								 pygame.image.tobytes(skill_surface, "RGBA"))

	def test_exploration_trails_are_behind_the_pet(self):
		pygame.init()
		art = virtual_pet.PetArt()
		species = virtual_pet.SPECIES_BY_KEY["dinosaur"]
		body = pygame.Surface((112, 112), pygame.SRCALPHA)
		body.fill((200, 80, 90, 255))
		for activity in ({"kind": "explore"}, {"kind": "skill", "skill": 0}):
			with self.subTest(activity=activity):
				surface = pygame.Surface((120, 120), pygame.SRCALPHA)
				with patch.object(art, "sprite", return_value=body), \
					 patch.object(art, "animated_pose", side_effect=lambda image, *args: (image, 0, 0)), \
					 patch.object(art, "draw_effect", side_effect=lambda target, effect, rect, now, variant: target.fill((30, 180, 160), rect)):
					art.draw(surface, species, surface.get_rect(), 1.0, activity=activity)
				self.assertEqual(surface.get_at((60, 60))[:3], (200, 80, 90))

	def test_related_skills_have_distinct_visuals(self):
		pygame.init()
		art = virtual_pet.PetArt()
		for species in ("bulbasaur", "charmander", "teto"):
			with self.subTest(species=species):
				first = pygame.Surface((120, 120), pygame.SRCALPHA)
				second = pygame.Surface((120, 120), pygame.SRCALPHA)
				first_effect = virtual_pet.SKILLS[species][0][1]
				second_effect = virtual_pet.SKILLS[species][1][1]
				art.draw_effect(first, first_effect, first.get_rect(), 1.0, variant=0)
				art.draw_effect(second, second_effect, second.get_rect(), 1.0, variant=1)
				self.assertFalse(pygame.image.tobytes(first, "RGBA") == pygame.image.tobytes(second, "RGBA"))

	def test_all_species_render_every_skill(self):
		pygame.init()
		art = virtual_pet.PetArt()
		for species in virtual_pet.SPECIES:
			for skill in range(len(virtual_pet.SKILLS[species.key])):
				with self.subTest(species=species.key, skill=skill):
					surface = pygame.Surface((120, 120), pygame.SRCALPHA)
					art.draw(surface, species, surface.get_rect(), 1.0,
							 activity={"kind": "skill", "skill": skill}, dirt=2)
					self.assertGreater(surface.get_bounding_rect().width, 40)

	def test_dirt_changes_the_pet_sprite(self):
		pygame.init()
		art = virtual_pet.PetArt()
		clean = pygame.Surface((120, 120), pygame.SRCALPHA)
		dirty = pygame.Surface((120, 120), pygame.SRCALPHA)
		art.draw(clean, virtual_pet.SPECIES[0], clean.get_rect(), 1.0)
		art.draw(dirty, virtual_pet.SPECIES[0], dirty.get_rect(), 1.0, dirt=2)
		self.assertFalse(pygame.image.tobytes(clean, "RGBA") == pygame.image.tobytes(dirty, "RGBA"))


class PetDisplayTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		pygame.init()

	def test_park_shows_multiple_pets_and_home_shows_one_larger_pet(self):
		with tempfile.TemporaryDirectory() as directory:
			path = Path(directory) / "pets.json"
			world = virtual_pet.PetWorld(path, clock=lambda: 1000.0)
			owner = world.create_owner("文武")
			pet = world.adopt(owner, "dinosaur")
			original = path.read_bytes()
			game = virtual_pet.PetGame(world)
			game.owner_id, game.pet_id = owner, pet
			for size in ((240, 320), (320, 240)):
				with patch.object(virtual_pet.spi_lcd, "_pygame", pygame):
					display = virtual_pet.PetDisplay(pygame.Surface(size))
					with self.subTest(size=size), patch.object(display.art, "draw", wraps=display.art.draw) as draw:
						game.show("owners")
						display.draw(game, now=1.0)
						self.assertGreaterEqual(len(draw.call_args_list), 3)
						self.assertGreaterEqual(len({call.args[1].key for call in draw.call_args_list}), 3)
						park_bounds = pygame.Rect((0, 0), display.selection_scene.size)
						for call in draw.call_args_list:
							self.assertTrue(park_bounds.contains(call.args[2]))
						draw.reset_mock()
						game.show("home")
						display.draw(game, now=1.0)
						self.assertEqual(len(draw.call_args_list), 1)
						self.assertEqual(draw.call_args.args[1].key, "dinosaur")
						pet_area = draw.call_args.args[2]
						self.assertTrue(pygame.Rect((0, 0), display.home_scene.size).contains(pet_area))
						self.assertGreaterEqual(pet_area.width, round(min(display.home_scene.size) * 0.8))
			self.assertEqual(path.read_bytes(), original)

	def test_park_companions_move_and_home_keeps_active_pet_effects(self):
		with tempfile.TemporaryDirectory() as directory:
			world = virtual_pet.PetWorld(Path(directory) / "pets.json", clock=lambda: 1000.0)
			owner = world.create_owner("文武")
			pet = world.adopt(owner, "dinosaur")
			world.pet(owner, pet)["dirt"] = 1
			world.care(owner, pet, "wash")
			game = virtual_pet.PetGame(world)
			game.owner_id, game.pet_id = owner, pet
			for size in ((240, 320), (320, 240)):
				with self.subTest(size=size), patch.object(virtual_pet.spi_lcd, "_pygame", pygame):
					display = virtual_pet.PetDisplay(pygame.Surface(size))
					with patch.object(display.art, "draw", wraps=display.art.draw) as draw:
						game.show("owners")
						display.draw(game, now=1.0)
						first = [call.args[2].copy() for call in draw.call_args_list[:2]]
						draw.reset_mock()
						display.draw(game, now=3.0)
						self.assertNotEqual(first, [call.args[2] for call in draw.call_args_list[:2]])
						draw.reset_mock()
						game.show("home")
						display.draw(game, now=1.0)
						self.assertEqual(len(draw.call_args_list), 1)
						self.assertEqual(draw.call_args.args[1].key, "dinosaur")
						self.assertEqual(draw.call_args.kwargs["activity"]["kind"], "wash")
						self.assertEqual(draw.call_args.kwargs["dirt"], 1)

	def test_confirmed_activities_animate_only_the_current_pet(self):
		with tempfile.TemporaryDirectory() as directory:
			world = virtual_pet.PetWorld(Path(directory) / "pets.json", clock=lambda: 1000.0)
			owner = world.create_owner("文武")
			game = virtual_pet.PetGame(world, random.Random(7))
			game.owner_id = owner
			for species in ("capybara", "pikachu", "teto"):
				game.pet_id = world.adopt(owner, species)
				for kind in virtual_pet.ACTIVITIES:
					with self.subTest(species=species, activity=kind):
						game.show("home")
						game.handle_action("CHOOSE_%d" % virtual_pet.HOME_INDEX[kind])
						if kind == "skill":
							game.handle_action("CHOOSE_0")
						self.assertEqual(game.view, "confirm_action")
						game.handle_action("CHOOSE_1")
						if kind == "play":
							self.assertEqual(game.view, "game")
							game.handle_action("CHOOSE_1")
						self.assertEqual(game.view, "home")
						self.assertEqual(world.pet(owner, game.pet_id)["activity"]["kind"], kind)
						for size in ((240, 320), (320, 240)):
							with patch.object(virtual_pet.spi_lcd, "_pygame", pygame):
								screen = pygame.Surface(size)
								display = virtual_pet.PetDisplay(screen)
								with patch.object(display.art, "draw", wraps=display.art.draw) as draw:
									display.draw(game, now=1.15)
									first = pygame.image.tobytes(screen.subsurface(display.home_scene), "RGB")
									self.assertEqual(len(draw.call_args_list), 1)
									self.assertEqual(draw.call_args.args[1].key, species)
									self.assertEqual(draw.call_args.kwargs["activity"]["kind"], kind)
									display.draw(game, now=1.42)
									self.assertFalse(first == pygame.image.tobytes(screen.subsurface(display.home_scene), "RGB"))
						game.handle_action("CHOOSE_%d" % virtual_pet.HOME_INDEX["stop"])
						self.assertEqual(game.view, "confirm_stop")
						game.handle_action("CHOOSE_1")
						self.assertIsNone(world.pet(owner, game.pet_id)["activity"])
				world.release(owner, game.pet_id)

	def test_legacy_owner_is_shown_as_a_record_not_an_extra_name(self):
		with tempfile.TemporaryDirectory() as directory:
			world = virtual_pet.PetWorld(Path(directory) / "pets.json", clock=lambda: 1000.0)
			owner = world.create_owner("文武")
			world.adopt(owner, "capybara")
			world.owner(owner)["name"] = "星星"
			game = virtual_pet.PetGame(world)
			with patch.object(virtual_pet.spi_lcd, "_pygame", pygame):
				display = virtual_pet.PetDisplay(pygame.Surface((240, 320)))
				self.assertEqual(display.selection_items(game)[1][0], ("旧存档1", "1只"))
				game.handle_action("K3")
				self.assertEqual([name for name, _ in display.selection_items(game)[1]], list(virtual_pet.OWNER_NAMES))

	def test_single_pet_can_be_deleted_only_after_confirmation(self):
		with tempfile.TemporaryDirectory() as directory:
			path = Path(directory) / "pets.json"
			world = virtual_pet.PetWorld(path, clock=lambda: 1000.0)
			owner = world.create_owner("文武")
			pet = world.adopt(owner, "capybara")
			game = virtual_pet.PetGame(world)
			game.owner_id, game.pet_id = owner, pet
			game.show("pets")
			with patch.object(virtual_pet.spi_lcd, "_pygame", pygame):
				display = virtual_pet.PetDisplay(pygame.Surface((240, 320)))
				self.assertEqual(display.selection_items(game)[1][-1][0], "删除宠物")
				game.handle_action("CHOOSE_1")
				self.assertEqual(display.selection_items(game),
								 ("删除后无法恢复", [("取消", ""), ("确认删除", "")]))
				game.handle_action("K3")
				self.assertEqual(world.pet(owner, pet)["species"], "capybara")
				game.handle_action("CHOOSE_1")
				game.handle_action("CHOOSE_1")
				self.assertEqual(world.owner(owner)["pets"], [])
				self.assertEqual(virtual_pet.PetWorld(path).owner(owner)["pets"], [])

	def test_button_text_contrast_and_visible_growth(self):
		def luminance(color):
			channels = [channel / 255.0 for channel in color]
			linear = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
					  for channel in channels]
			return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
		for background, foreground in ((virtual_pet.CORAL, virtual_pet.PAPER),
									   (virtual_pet.JADE, virtual_pet.PAPER),
									   (virtual_pet.GOLD, virtual_pet.INK),
									   ((219, 228, 223), (83, 92, 89))):
			lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
			self.assertGreaterEqual((lighter + 0.05) / (darker + 0.05), 4.5)
		with patch.object(virtual_pet.spi_lcd, "_pygame", pygame):
			display = virtual_pet.PetDisplay(pygame.Surface((240, 320)))
			with patch.object(display.art, "draw") as draw:
				display.scene(display.home_scene, virtual_pet.SPECIES[0], 1.0, stage="宝宝")
				baby_size = draw.call_args.args[2].width
				display.scene(display.home_scene, virtual_pet.SPECIES[0], 1.0, stage="大伙伴")
				self.assertGreater(draw.call_args.args[2].width, baby_size)

	def test_home_gives_the_pet_more_room_without_overlapping_controls(self):
		for size in ((240, 320), (320, 240)):
			with self.subTest(size=size), patch.object(virtual_pet.spi_lcd, "_pygame", pygame):
				display = virtual_pet.PetDisplay(pygame.Surface(size))
				self.assertFalse(display.home_scene.colliderect(display.stat_area))
				self.assertFalse(display.home_scene.colliderect(display.action_area))
				self.assertFalse(display.stat_area.colliderect(display.action_area))
				self.assertLessEqual(display.action_area.bottom, display.footer_top)
				with patch.object(display.art, "draw") as draw:
					display.scene(display.home_scene, virtual_pet.SPECIES[0], 1.0, stage="宝宝")
					self.assertGreaterEqual(draw.call_args.args[2].width, 120)

	def test_home_shows_game_result_and_remaining_time(self):
		with tempfile.TemporaryDirectory() as directory:
			world = virtual_pet.PetWorld(Path(directory) / "pets.json", clock=lambda: 1000.0)
			owner = world.create_owner("文武")
			pet = world.adopt(owner, "capybara")
			world.care(owner, pet, "play", won=True)
			game = virtual_pet.PetGame(world)
			game.owner_id, game.pet_id = owner, pet
			game.show("home", virtual_pet.HOME_INDEX["play"])
			for size in ((240, 320), (320, 240)):
				with self.subTest(size=size), patch.object(virtual_pet.spi_lcd, "_pygame", pygame):
					display = virtual_pet.PetDisplay(pygame.Surface(size))
					with patch.object(display, "scene") as scene, patch.object(display, "text", wraps=display.text) as text:
						display.draw_home(game, 1.0)
						labels = [call.args[0] for call in text.call_args_list] if display.portrait else [scene.call_args.args[5]]
						self.assertTrue(any("猜中" in label and "12秒" in label for label in labels))

	def test_portrait_status_does_not_cover_the_pet(self):
		with tempfile.TemporaryDirectory() as directory:
			world = virtual_pet.PetWorld(Path(directory) / "pets.json", clock=lambda: 1000.0)
			owner = world.create_owner("文武")
			pet = world.adopt(owner, "teto")
			world.care(owner, pet, "play", won=True)
			game = virtual_pet.PetGame(world)
			game.owner_id, game.pet_id = owner, pet
			game.show("home", virtual_pet.HOME_INDEX["play"])
			with patch.object(virtual_pet.spi_lcd, "_pygame", pygame):
				display = virtual_pet.PetDisplay(pygame.Surface((240, 320)))
				with patch.object(display, "scene", wraps=display.scene) as scene, \
					 patch.object(display, "text", wraps=display.text) as text:
					display.draw_home(game, 1.0)
					self.assertEqual(scene.call_args.args[5], "")
					labels = [call.args[0] for call in text.call_args_list]
					self.assertTrue(any("猜中" in label and "12秒" in label for label in labels))

	def test_all_views_fit_both_screen_orientations(self):
		with tempfile.TemporaryDirectory() as directory:
			world = virtual_pet.PetWorld(Path(directory) / "pets.json", clock=lambda: 1000.0)
			owner = world.create_owner("文武")
			pet = world.adopt(owner, "capybara")
			for size in ((240, 320), (320, 240)):
				with self.subTest(size=size), patch.object(virtual_pet.spi_lcd, "_pygame", pygame):
					screen = pygame.Surface(size)
					display = virtual_pet.PetDisplay(screen)
					game = virtual_pet.PetGame(world, random.Random(7))
					game.owner_id, game.pet_id = owner, pet
					for view in ("owners", "owner_name", "owner_migrate", "pets", "adopt", "home", "rename", "accessory",
								 "confirm_release", "confirm_keep", "confirm_action", "confirm_stop", "skills",
								 "tasks", "game", "result"):
						game.view = view
						game.index = 0
						game.pending_action = "wash"
						game.guess, game.target = 0, 1
						display.draw(game, now=1.0)
						for rect, _ in display.click_targets:
							self.assertTrue(screen.get_rect().contains(rect), (view, rect))
							self.assertLessEqual(rect.bottom, display.footer_top)
						for index, (rect, _) in enumerate(display.click_targets):
							self.assertFalse(any(rect.colliderect(other) for other, _ in display.click_targets[index + 1:]))
					display.draw_error()

	def test_every_species_and_home_action_renders_in_both_orientations(self):
		with tempfile.TemporaryDirectory() as directory:
			world = virtual_pet.PetWorld(Path(directory) / "pets.json", clock=lambda: 1000.0)
			owner = world.create_owner("文武")
			for size in ((240, 320), (320, 240)):
				with self.subTest(size=size), patch.object(virtual_pet.spi_lcd, "_pygame", pygame):
					display = virtual_pet.PetDisplay(pygame.Surface(size))
					game = virtual_pet.PetGame(world)
					for index, species in enumerate(virtual_pet.SPECIES):
						pet_id = world.adopt(owner, species.key)
						game.owner_id, game.pet_id = owner, pet_id
						game.show("adopt", index)
						display.draw(game, now=1.0)
						for action in range(len(virtual_pet.HOME_ACTIONS)):
							game.show("home", action)
							display.draw(game, now=1.0)
							self.assertEqual(len(display.click_targets), 3)
						world.release(owner, pet_id)

	def test_mouse_and_keyboard_map_to_the_visible_options(self):
		with tempfile.TemporaryDirectory() as directory:
			world = virtual_pet.PetWorld(Path(directory) / "pets.json")
			game = virtual_pet.PetGame(world)
			with patch.object(virtual_pet.spi_lcd, "_pygame", pygame):
				display = virtual_pet.PetDisplay(pygame.Surface((240, 320)))
				display.draw(game, now=1.0)
				rect, action = display.click_targets[0]
				event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=rect.center)
				with patch.object(virtual_pet.spi_lcd, "mouse_position", return_value=rect.center):
					self.assertEqual(virtual_pet.event_action(event, display), action)
				self.assertEqual(virtual_pet.event_action(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_3), display), "K3")
				self.assertEqual(virtual_pet.event_action(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_BACKSPACE), display), "BACK")

	def test_simulated_main_creates_an_owner_and_pet(self):
		pygame.display.set_mode((480, 640))
		screen = pygame.Surface((240, 320))
		down = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_3)
		up = pygame.event.Event(pygame.KEYUP, key=pygame.K_3)
		next_down = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_2)
		next_up = pygame.event.Event(pygame.KEYUP, key=pygame.K_2)
		quit_event = pygame.event.Event(pygame.QUIT)
		events = iter(([down, up], [down, up], [down, up], [down, up], [down, up],
					   [next_down, next_up], [down, up], [quit_event]))
		frames = []
		with tempfile.TemporaryDirectory() as directory:
			world = virtual_pet.PetWorld(Path(directory) / "pets.json", clock=lambda: 1000.0)
			with patch.object(virtual_pet.spi_lcd, "_pygame", pygame), \
					patch.object(virtual_pet.spi_lcd, "is_simulate", return_value=True), \
					patch.object(virtual_pet.spi_lcd, "init", return_value=screen), \
					patch.object(virtual_pet.spi_lcd, "present", return_value=True) as present, \
					patch.object(virtual_pet, "PetWorld", return_value=world), \
					patch.object(virtual_pet.PetDisplay, "draw", autospec=True,
								 side_effect=lambda display, game: frames.append(game.view)), \
					patch.object(pygame.event, "get", side_effect=lambda: next(events)), \
					patch.object(pygame.time, "Clock"), patch.object(pygame, "quit"), patch("builtins.print"):
				virtual_pet.main()
			self.assertEqual(frames, ["owner_name", "pets", "adopt", "home", "confirm_action", "confirm_action", "home"])
			self.assertEqual(world.owners[0]["pets"][0]["species"], "capybara")
			self.assertEqual(world.owners[0]["pets"][0]["activity"]["kind"], "feed")
			self.assertEqual(world.owners[0]["pets"][0]["food"], 3)
			present.assert_called_with(poll_events=False)

	def test_gpio_back_and_cleanup(self):
		screen = pygame.Surface((240, 320))
		buttons = Mock()
		buttons.poll.side_effect = (("K3",), ("QUIT",), ("QUIT",))
		frames = []
		importer = SimpleNamespace(import_module=Mock(return_value=Mock()))
		with tempfile.TemporaryDirectory() as directory:
			world = virtual_pet.PetWorld(Path(directory) / "pets.json")
			with patch.object(virtual_pet.spi_lcd, "_pygame", pygame), \
					patch.object(virtual_pet.spi_lcd, "is_simulate", return_value=False), \
					patch.object(virtual_pet.spi_lcd, "init", return_value=screen), \
					patch.object(virtual_pet.spi_lcd, "present", return_value=True), \
					patch.object(virtual_pet, "importlib", importer), \
					patch.object(virtual_pet, "GPIOButtons", return_value=buttons), \
					patch.object(virtual_pet, "PetWorld", return_value=world), \
					patch.object(virtual_pet.PetDisplay, "draw", autospec=True,
								 side_effect=lambda display, game: frames.append(game.view)), \
					patch.object(pygame.time, "Clock"), patch.object(pygame, "quit"), patch("builtins.print"):
				virtual_pet.main()
		self.assertEqual(frames, ["owner_name", "owners"])
		buttons.cleanup.assert_called_once()

	def test_long_press_returns_without_feeding(self):
		now = [0.0]
		hold = virtual_pet.spi_lcd.SimulatedHold("K3", "BACK", 1.0, clock=lambda: now[0])
		with tempfile.TemporaryDirectory() as directory:
			world = virtual_pet.PetWorld(Path(directory) / "pets.json", clock=lambda: 1000.0)
			owner = world.create_owner("文武")
			pet = world.adopt(owner, "capybara")
			game = virtual_pet.PetGame(world)
			game.owner_id, game.pet_id = owner, pet
			game.show("home")
			with patch.object(virtual_pet.spi_lcd, "_pygame", pygame):
				display = virtual_pet.PetDisplay(pygame.Surface((240, 320)))
				down = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_3)
				up = pygame.event.Event(pygame.KEYUP, key=pygame.K_3)
				self.assertIsNone(hold.process_event(down, virtual_pet.event_action(down, display)))
				now[0] = 1.1
				game.handle_action(hold.poll())
				self.assertIsNone(hold.process_event(up, virtual_pet.event_action(up, display)))
			self.assertEqual(game.view, "pets")
			self.assertEqual(world.pet(owner, pet)["stats"]["hunger"], virtual_pet.INITIAL_STATS["hunger"])

	def test_gpio_release_near_hold_threshold_does_not_confirm_feeding(self):
		cases = ((1.005, "home", "K3", "confirm_action"),
				 (1.015, "home", "QUIT", "pets"),
				 (1.015, "confirm_action", "QUIT", "home"))
		for released, initial_view, expected_action, expected_view in cases:
			with self.subTest(released=released, initial_view=initial_view), tempfile.TemporaryDirectory() as directory:
				world = virtual_pet.PetWorld(Path(directory) / "pets.json", clock=lambda: 1000.0)
				game = virtual_pet.PetGame(world)
				game.owner_id = world.create_owner("文武")
				game.pet_id = world.adopt(game.owner_id, "capybara")
				game.show("home", virtual_pet.HOME_INDEX["feed"])
				if initial_view == "confirm_action":
					game.handle_action("K3")
				self.assertEqual(game.view, initial_view)
				gpio = Mock(LOW=0)
				now, level = 0.0, 1
				gpio.input.side_effect = lambda pin: level if pin == 24 else 1
				buttons = virtual_pet.GPIOButtons(gpio, clock=lambda: now)
				seen = []
				for now, level in ((0.01, 0), (0.05, 0), (1.0, 0), (released, 1), (1.10, 1), (1.20, 1)):
					for action in buttons.poll():
						seen.append(action)
						game.handle_action("BACK" if action == "QUIT" else action)
				self.assertEqual(seen, [expected_action])
				self.assertEqual(game.view, expected_view)
				self.assertIsNone(world.pet(game.owner_id, game.pet_id)["activity"])

	def test_corrupt_save_displays_error_without_overwriting(self):
		pygame.display.set_mode((480, 640))
		screen = pygame.Surface((240, 320))
		down = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_3)
		up = pygame.event.Event(pygame.KEYUP, key=pygame.K_3)
		events = iter(([], [down, up]))
		with tempfile.TemporaryDirectory() as directory:
			path = Path(directory) / "pets.json"
			path.write_text("{broken", encoding="utf-8")
			constructor = virtual_pet.PetWorld
			with patch.object(virtual_pet.spi_lcd, "_pygame", pygame), \
					patch.object(virtual_pet.spi_lcd, "is_simulate", return_value=True), \
					patch.object(virtual_pet.spi_lcd, "init", return_value=screen), \
					patch.object(virtual_pet.spi_lcd, "present", return_value=True), \
					patch.object(virtual_pet, "PetWorld", side_effect=lambda: constructor(path)), \
					patch.object(virtual_pet.PetDisplay, "draw_error", autospec=True) as error_screen, \
					patch.object(pygame.event, "get", side_effect=lambda: next(events)), \
					patch.object(pygame.time, "Clock"), patch.object(pygame, "quit"), patch("builtins.print"):
				virtual_pet.main()
			error_screen.assert_called_once()
			self.assertEqual(path.read_text(encoding="utf-8"), "{broken")


if __name__ == "__main__":
	unittest.main()