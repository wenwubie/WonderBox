"""适合小屏幕的离线电子宠物。"""

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import importlib
import json
import math
import os
from pathlib import Path
import random
import sys
import tempfile
import time
import uuid

import pygame


ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "Lucky Wheel"))
from common import spi_lcd
from lucky_wheel import GPIOButtons, QUIT_HOLD_SECONDS

SAVE_FILE = Path(__file__).resolve().parent / "data" / "pets.json"
OWNER_NAMES = ("文武", "文怡然", "文焕然", "欧泽轩", "欧阳沐希")
PET_NAMES = ("团团", "泡泡", "布丁", "豆豆", "糖糖", "圆圆", "啾啾", "暖暖", "星星", "小乖", "桃桃", "乐乐")
MAX_OFFLINE_HOURS = 12


@dataclass(frozen=True)
class Species:
	key: str
	name: str
	description: str
	color: tuple[int, int, int]
	image: str = ""


SPECIES = (
	Species("capybara", "卡皮巴拉", "温柔的小伙伴", (188, 135, 101)),
	Species("dinosaur", "小恐龙", "爱冒险的宝宝", (101, 190, 149)),
	Species("pikachu", "皮卡丘", "电力满满", (242, 188, 53), "皮卡丘.png"),
	Species("eevee", "伊布", "毛茸茸的朋友", (190, 131, 79), "伊布.png"),
	Species("psyduck", "可达鸭", "呆萌小伙伴", (236, 190, 75), "可达鸭.png"),
	Species("bulbasaur", "妙蛙种子", "喜欢晒太阳", (85, 177, 152), "妙蛙种子.png"),
	Species("charmander", "小火龙", "暖暖的小伙伴", (225, 133, 80), "小火龙.png"),
	Species("teto", "重音Teto", "爱唱歌的伙伴", (211, 100, 105)),
)
SPECIES_BY_KEY = {species.key: species for species in SPECIES}
ACCESSORIES = (("none", "不戴", 0), ("flower", "小花", 5),
			   ("ribbon", "蝴蝶结", 8), ("crown", "星星皇冠", 12))
ACCESSORIES_BY_KEY = {key: (name, price) for key, name, price in ACCESSORIES}
INITIAL_STATS = {"hunger": 82.0, "happiness": 85.0, "hygiene": 88.0,
				 "energy": 88.0, "health": 100.0}
ACTIVITIES = {
	"feed": ("喂食", 10, 20 * 60),
	"play": ("玩耍", 12, 5 * 60),
	"wash": ("洗澡", 15 * 60, 30 * 60),
	"sleep": ("休息", 15 * 60, 15 * 60),
	"pat": ("摸摸", 8, 10 * 60),
	"medicine": ("照顾", 12, 30 * 60),
	"explore": ("外出", 10 * 60, 20 * 60),
	"skill": ("技能", 8, 60),
}
DAILY_TASKS = (("feed", "好好吃饭", 0, 1, 1), ("pat", "温柔摸摸", 1, 1, 1),
			   ("explore", "一起出游", 1, 2, 3))
MAX_FOOD = 99
SKILLS = {
	"capybara": (("温柔贴贴", "heart"), ("泡泡雨", "water"), ("花花祝福", "flower")),
	"dinosaur": (("蹦蹦跳", "dash"), ("勇气星星", "star"), ("小小火花", "fire")),
	"pikachu": (("电光一闪", "dash"), ("十万伏特", "electric"), ("打雷", "thunder")),
	"eevee": (("摇尾巴", "heart"), ("电光一闪", "dash"), ("高速星星", "star")),
	"psyduck": (("水枪", "water"), ("念力", "star"), ("泡泡光线", "bubbles")),
	"bulbasaur": (("藤鞭", "leaf"), ("飞叶快刀", "leaf"), ("阳光烈焰", "star")),
	"charmander": (("火花", "fire"), ("喷射火焰", "fire"), ("龙之波动", "star")),
	"teto": (("小音符", "music"), ("旋转旋律", "music"), ("心动演唱会", "heart")),
}


class SaveError(Exception):
	pass


def growth_stage(pet):
	return ("宝宝", "小伙伴", "大伙伴")[growth_level(pet) - 1]


def growth_level(pet):
	return 1 + (pet["experience"] >= 40) + (pet["experience"] >= 120)


def duration_text(seconds):
	seconds = max(0, math.ceil(seconds))
	hours, seconds = divmod(seconds, 3600)
	minutes, seconds = divmod(seconds, 60)
	if hours:
		return "%d时%d分" % (hours, minutes)
	if minutes:
		return "%d分%d秒" % (minutes, seconds) if seconds else "%d分钟" % minutes
	return "%d秒" % seconds


def prepare_pet(pet):
	legacy_sleep = "activity" not in pet and pet["sleeping"]
	pet.setdefault("food", 4)
	pet.setdefault("dirt", 0)
	pet.setdefault("cooldowns", {})
	pet.setdefault("task_days", {})
	pet.setdefault("last_pat_at", pet["updated_at"])
	pet.setdefault("activity", None)
	if legacy_sleep:
		started = float(pet["updated_at"])
		pet["activity"] = {"kind": "sleep", "started_at": started,
						   "ends_at": started + ACTIVITIES["sleep"][1]}
	if (not isinstance(pet["food"], int) or not 0 <= pet["food"] <= MAX_FOOD
			or not isinstance(pet["dirt"], int) or not 0 <= pet["dirt"] <= 3
			or not isinstance(pet["cooldowns"], dict) or not isinstance(pet["task_days"], dict)
			or not isinstance(pet["last_pat_at"], (int, float)) or not math.isfinite(pet["last_pat_at"])):
		raise ValueError("宠物养成资料不正确")
	if any(key not in ACTIVITIES or not isinstance(value, (int, float)) or not math.isfinite(value)
		   for key, value in pet["cooldowns"].items()):
		raise ValueError("宠物冷却资料不正确")
	if any(key not in {task[0] for task in DAILY_TASKS} or not isinstance(value, str)
		   for key, value in pet["task_days"].items()):
		raise ValueError("宠物任务资料不正确")
	activity = pet["activity"]
	if activity is not None:
		if (not isinstance(activity, dict) or activity.get("kind") not in ACTIVITIES
				or any(not isinstance(activity.get(key), (int, float)) or not math.isfinite(activity[key])
					   for key in ("started_at", "ends_at"))
				or activity["ends_at"] < activity["started_at"]
				or ("won" in activity and not isinstance(activity["won"], bool))
				or ("dirty" in activity and not isinstance(activity["dirty"], bool))):
			raise ValueError("宠物行动资料不正确")
		if activity["kind"] == "skill" and (not isinstance(activity.get("skill"), int)
				or not 0 <= activity["skill"] < len(SKILLS[pet["species"]])):
			raise ValueError("宠物技能资料不正确")


def local_day(timestamp):
	return datetime.fromtimestamp(timestamp).date().isoformat()


def apply_elapsed(pet, start, end):
	hours = max(0.0, (end - start) / 3600.0)
	stats = pet["stats"]
	stats["hunger"] = max(0.0, stats["hunger"] - 3.0 * hours)
	stats["happiness"] = max(0.0, stats["happiness"] - 2.0 * hours)
	stats["hygiene"] = max(0.0, stats["hygiene"] - 2.0 * hours)
	energy_change = 14.0 if pet["sleeping"] else -2.0
	stats["energy"] = max(0.0, min(100.0, stats["energy"] + energy_change * hours))
	if min(stats["hunger"], stats["hygiene"], stats["energy"]) < 20:
		stats["health"] = max(0.0, stats["health"] - 1.5 * hours)
	else:
		stats["health"] = min(100.0, stats["health"] + 0.6 * hours)
	friendship_hours = max(0.0, end - max(start, pet["last_pat_at"] + 4 * 3600)) / 3600.0
	pet["friendship"] = max(0.0, pet["friendship"] - friendship_hours)


def complete_activity(pet, activity):
	kind = activity["kind"]
	won = activity.get("won", False)
	changes = {
		"feed": ({"hunger": 25, "hygiene": -2}, 3, 1, 0, 0),
		"play": ({"happiness": 20, "energy": -8, "hunger": -6}, 6 if won else 4, 2, 3 if won else 1, 1),
		"wash": ({"hygiene": 100, "happiness": 3}, 4, 1, 0, 0),
		"sleep": ({"energy": 30}, 2, 0, 0, 0),
		"pat": ({"happiness": 12}, 2, 5, 0, 0),
		"medicine": ({"health": 25, "happiness": 4}, 2, 1, 0, 0),
		"explore": ({"happiness": 15, "energy": -18, "hunger": -18, "hygiene": -15}, 12, 2, 2, 2),
		"skill": ({"happiness": 4, "energy": -3, "hunger": -2}, 0, 1, 0, 0),
	}
	deltas, experience, friendship, stars, food = changes[kind]
	for key, value in deltas.items():
		pet["stats"][key] = max(0.0, min(100.0, pet["stats"][key] + value))
	if kind == "wash":
		pet["dirt"] = 0
	elif kind == "explore" and activity.get("dirty", False):
		pet["dirt"] = min(3, pet["dirt"] + 1)
	elif kind == "pat":
		pet["last_pat_at"] = activity["ends_at"]
	pet["sleeping"] = False
	pet["experience"] += experience
	pet["friendship"] = min(100.0, pet["friendship"] + friendship)
	pet["stars"] += stars
	pet["food"] = min(MAX_FOOD, pet["food"] + food)
	for task, _, task_food, task_stars, task_experience in DAILY_TASKS:
		if kind == task and pet["task_days"].get(task) != local_day(activity["ends_at"]):
			pet["task_days"][task] = local_day(activity["ends_at"])
			pet["food"] = min(MAX_FOOD, pet["food"] + task_food)
			pet["stars"] += task_stars
			pet["experience"] += task_experience
	pet["cooldowns"][kind] = activity["ends_at"] + ACTIVITIES[kind][2]
	pet["activity"] = None


def advance_pet(pet, now):
	prepare_pet(pet)
	updated_at = float(pet["updated_at"])
	end = max(updated_at, float(now))
	start = max(updated_at, end - MAX_OFFLINE_HOURS * 3600)
	activity = pet["activity"]
	if activity and activity["ends_at"] <= end:
		finished = activity["ends_at"]
		if finished > start:
			apply_elapsed(pet, start, finished)
		complete_activity(pet, activity)
		start = max(start, finished)
	apply_elapsed(pet, start, end)
	pet["updated_at"] = end


class PetWorld:
	def __init__(self, path=SAVE_FILE, clock=time.time, rng=None):
		self.path = Path(path)
		self.clock = clock
		self.rng = rng if rng is not None else random.Random()
		self.data = self._load()

	@property
	def owners(self):
		return self.data["owners"]

	def _load(self):
		if not self.path.exists():
			return {"version": 1, "owners": []}
		try:
			data = json.loads(self.path.read_text(encoding="utf-8"))
			if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("owners"), list):
				raise ValueError("存档格式不正确")
			for owner in data["owners"]:
				if not isinstance(owner["id"], str) or not isinstance(owner["name"], str) or not isinstance(owner["pets"], list):
					raise ValueError("主人资料不正确")
				for pet in owner["pets"]:
					if (pet["species"] not in SPECIES_BY_KEY or not isinstance(pet["id"], str)
							or not isinstance(pet["name"], str) or not isinstance(pet["sleeping"], bool)
							or not isinstance(pet["accessories"], list)
							or pet["equipped"] not in pet["accessories"]
							or any(item not in ACCESSORIES_BY_KEY for item in pet["accessories"])
							or not all(isinstance(pet["stats"][key], (int, float)) for key in INITIAL_STATS)):
						raise ValueError("宠物资料不正确")
					for key in ("experience", "friendship", "stars", "updated_at"):
						if not isinstance(pet[key], (int, float)):
							raise ValueError("宠物状态不正确")
					prepare_pet(pet)
			return data
		except (OSError, ValueError, TypeError, KeyError) as error:
			raise SaveError("无法读取宠物存档，原文件没有被修改: " + str(error)) from error

	def _save(self):
		self.path.parent.mkdir(parents=True, exist_ok=True)
		temporary_path = None
		try:
			with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
											 prefix=".pets-", suffix=".tmp", delete=False) as file:
				temporary_path = Path(file.name)
				json.dump(self.data, file, ensure_ascii=False, indent=2)
				file.flush()
				os.fsync(file.fileno())
			os.replace(temporary_path, self.path)
			temporary_path = None
		finally:
			if temporary_path is not None:
				temporary_path.unlink(missing_ok=True)

	def _commit(self, change):
		previous = deepcopy(self.data)
		try:
			result = change()
			self._save()
			return result
		except Exception:
			self.data = previous
			raise

	def owner(self, owner_id):
		return next(owner for owner in self.owners if owner["id"] == owner_id)

	def pet(self, owner_id, pet_id):
		return next(pet for pet in self.owner(owner_id)["pets"] if pet["id"] == pet_id)

	def visible_pet(self, owner_id, pet_id):
		pet = deepcopy(self.pet(owner_id, pet_id))
		advance_pet(pet, self.clock())
		return pet

	def create_owner(self, name):
		name = name.strip()
		if name not in OWNER_NAMES or any(owner["name"] == name for owner in self.owners):
			raise ValueError("主人名字不在名单中或已经使用")
		def change():
			owner = {"id": uuid.uuid4().hex, "name": name, "pets": []}
			self.owners.append(owner)
			return owner["id"]
		return self._commit(change)

	def rename_owner(self, owner_id, name):
		name = name.strip()
		if name not in OWNER_NAMES or any(owner["name"] == name and owner["id"] != owner_id
										 for owner in self.owners):
			raise ValueError("主人名字不在名单中或已经使用")
		def change():
			self.owner(owner_id)["name"] = name
		return self._commit(change)

	def adopt(self, owner_id, species_key):
		if species_key not in SPECIES_BY_KEY:
			raise ValueError("没有这种宠物")
		def change():
			owner = self.owner(owner_id)
			if owner["pets"]:
				raise ValueError("每位主人只能领养一只，请先放弃当前宠物")
			base = SPECIES_BY_KEY[species_key].name
			used = {pet["name"] for pet in owner["pets"]}
			name, number = base, 2
			while name in used:
				name = "%s%d" % (base, number)
				number += 1
			pet = {"id": uuid.uuid4().hex, "species": species_key, "name": name,
				   "stats": dict(INITIAL_STATS), "sleeping": False, "experience": 0,
				   "friendship": 15, "stars": 0, "food": 4, "dirt": 0, "cooldowns": {},
				   "task_days": {}, "last_pat_at": self.clock(), "activity": None,
				   "accessories": ["none"], "equipped": "none",
				   "updated_at": self.clock()}
			owner["pets"].append(pet)
			return pet["id"]
		return self._commit(change)

	def release(self, owner_id, pet_id):
		def change():
			owner = self.owner(owner_id)
			owner["pets"].remove(self.pet(owner_id, pet_id))
		return self._commit(change)

	def retain_pet(self, owner_id, pet_id):
		def change():
			pet = self.pet(owner_id, pet_id)
			self.owner(owner_id)["pets"] = [pet]
		return self._commit(change)

	def equip(self, owner_id, pet_id, accessory):
		if accessory not in ACCESSORIES_BY_KEY:
			raise ValueError("没有这种装扮")
		def change():
			pet = self.pet(owner_id, pet_id)
			if accessory not in pet["accessories"]:
				price = ACCESSORIES_BY_KEY[accessory][1]
				if pet["stars"] < price:
					raise ValueError("星星不够，再玩一次吧")
				pet["stars"] -= price
				pet["accessories"].append(accessory)
			pet["equipped"] = accessory
		return self._commit(change)

	def rename(self, owner_id, pet_id, name):
		name = name.strip()
		if not name or len(name) > 8:
			raise ValueError("宠物名字为空或太长")
		if any(pet["name"] == name and pet["id"] != pet_id for pet in self.owner(owner_id)["pets"]):
			raise ValueError("名字已经被另一只宠物使用")
		def change():
			self.pet(owner_id, pet_id)["name"] = name
		return self._commit(change)

	def check_care(self, owner_id, pet_id, action, skill=None):
		if action not in ACTIVITIES:
			raise ValueError("没有这种照顾方式")
		pet = self.visible_pet(owner_id, pet_id)
		if pet["activity"]:
			raise ValueError("%s中，请先等候" % ACTIVITIES[pet["activity"]["kind"]][0])
		remaining = pet["cooldowns"].get(action, 0) - pet["updated_at"]
		if remaining > 0:
			raise ValueError("%s冷却 %s" % (ACTIVITIES[action][0], duration_text(remaining)))
		if action == "feed" and not pet["food"]:
			raise ValueError("食物不够，去玩耍或外出吧")
		if action == "feed" and pet["stats"]["hunger"] >= 95:
			raise ValueError("已经吃饱啦")
		if action == "explore" and (pet["stats"]["energy"] < 25 or pet["stats"]["hunger"] < 25):
			raise ValueError("先吃饱、休息再出发")
		if action == "play" and pet["stats"]["energy"] < 10:
			raise ValueError("先休息一下再玩")
		if action == "skill" and (pet["stats"]["energy"] < 10 or pet["stats"]["hunger"] < 10):
			raise ValueError("先吃饭、休息一下")
		if action == "skill":
			if not isinstance(skill, int) or not 0 <= skill < len(SKILLS[pet["species"]]):
				raise ValueError("没有这个技能")
			if growth_level(pet) <= skill:
				raise ValueError("成长到 Lv%d 解锁" % (skill + 1))

	def care(self, owner_id, pet_id, action, won=False, skill=None):
		self.check_care(owner_id, pet_id, action, skill)
		def change():
			pet = self.pet(owner_id, pet_id)
			advance_pet(pet, self.clock())
			started = pet["updated_at"]
			pet["activity"] = {"kind": action, "started_at": started,
							   "ends_at": started + ACTIVITIES[action][1]}
			if action == "feed":
				pet["food"] -= 1
			elif action == "play":
				pet["activity"]["won"] = bool(won)
			elif action == "explore":
				pet["activity"]["dirty"] = self.rng.random() < 0.75
			elif action == "skill":
				pet["activity"]["skill"] = skill
			pet["sleeping"] = action == "sleep"
		return self._commit(change)

	def finish_due(self, owner_id, pet_id):
		pet = self.pet(owner_id, pet_id)
		activity = pet.get("activity")
		if not activity or self.clock() < activity["ends_at"]:
			return None
		kind = activity["kind"]
		def change():
			advance_pet(self.pet(owner_id, pet_id), self.clock())
			return kind
		return self._commit(change)

	def cancel_activity(self, owner_id, pet_id):
		def change():
			pet = self.pet(owner_id, pet_id)
			advance_pet(pet, self.clock())
			activity = pet["activity"]
			if activity is None:
				return False
			if activity["kind"] == "feed":
				pet["food"] = min(MAX_FOOD, pet["food"] + 1)
			pet["activity"] = None
			pet["sleeping"] = False
			return True
		return self._commit(change)


HOME_ACTIONS = (("feed", "喂食"), ("play", "玩耍"), ("explore", "外出"),
				("wash", "洗澡"), ("sleep", "睡觉"), ("pat", "摸摸"),
				("skill", "技能"), ("tasks", "任务"), ("accessory", "装扮"),
				("medicine", "照顾"), ("rename", "取名"), ("pets", "伙伴"), ("stop", "结束"))
HOME_INDEX = {key: index for index, (key, _) in enumerate(HOME_ACTIONS)}


class PetGame:
	def __init__(self, world, rng=None):
		self.world = world
		self.rng = rng if rng is not None else random.Random()
		self.view = "owners"
		self.index = 0
		self.owner_id = None
		self.pet_id = None
		self.target = None
		self.guess = None
		self.won = False
		self.notice = ""
		self.pending_action = None
		self.pending_skill = None
		self.pending_origin = "home"
		self.sync_retry_at = 0.0

	def owner_names(self):
		used = {owner["name"] for owner in self.world.owners}
		return [name for name in OWNER_NAMES if name not in used]

	def pet_names(self):
		pet = self.world.pet(self.owner_id, self.pet_id)
		used = {other["name"] for other in self.world.owner(self.owner_id)["pets"] if other["id"] != self.pet_id}
		return [pet["name"]] + [name for name in PET_NAMES if name != pet["name"] and name not in used]

	def option_count(self):
		if self.view == "owners":
			return len(self.world.owners) + bool(self.owner_names())
		if self.view in ("owner_name", "owner_migrate"):
			return len(self.owner_names())
		if self.view == "pets":
			count = len(self.world.owner(self.owner_id)["pets"])
			return count + (1 if count <= 1 else 0)
		if self.view == "rename":
			return len(self.pet_names())
		if self.view == "skills":
			return len(SKILLS[self.world.pet(self.owner_id, self.pet_id)["species"]])
		return {"adopt": len(SPECIES), "home": len(HOME_ACTIONS), "game": 3,
				"accessory": len(ACCESSORIES), "confirm_release": 2, "confirm_keep": 2,
				"confirm_action": 2, "confirm_stop": 2, "tasks": len(DAILY_TASKS),
				"result": 0}[self.view]

	def show(self, view, index=0):
		self.view = view
		self.index = index
		self.notice = ""

	def start_game(self):
		self.target = self.rng.randrange(3)
		self.guess = None
		self.show("game", 1)

	def request_activity(self, action, skill=None):
		self.world.check_care(self.owner_id, self.pet_id, action, skill)
		self.pending_action = action
		self.pending_skill = skill
		self.pending_origin = self.view
		self.show("confirm_action")

	def tick(self):
		if self.owner_id is None or self.pet_id is None or self.world.clock() < self.sync_retry_at:
			return
		pet = self.world.pet(self.owner_id, self.pet_id)
		level = growth_level(pet)
		try:
			finished = self.world.finish_due(self.owner_id, self.pet_id)
			if finished:
				new_level = growth_level(self.world.pet(self.owner_id, self.pet_id))
				self.notice = ("升到 Lv%d，解锁新技能！" % new_level if new_level > level
							   else "%s完成啦！" % ACTIVITIES[finished][0])
				self.sync_retry_at = 0.0
		except OSError as error:
			self.notice = "保存失败，请检查存储"
			self.sync_retry_at = self.world.clock() + 5
			print("宠物存档保存失败:", error)

	def back(self):
		if self.view == "owners":
			return "EXIT"
		if self.view in ("owner_name", "owner_migrate"):
			self.show("owners")
		elif self.view == "pets":
			self.show("owners")
		elif self.view in ("adopt", "home", "confirm_release", "confirm_keep"):
			self.show("pets")
		elif self.view == "confirm_action":
			self.show(self.pending_origin)
		else:
			self.show("home")
		return None

	def handle_action(self, action):
		if action == "BACK":
			return self.back()
		if not action:
			return None
		if action.startswith("CHOOSE_"):
			index = int(action[7:])
			if not 0 <= index < self.option_count():
				return None
			self.index = index
			action = "K3"
		if self.view == "result":
			if action == "K3":
				self.show("home", HOME_INDEX["play"])
			return None
		if action in ("K1", "K2"):
			count = self.option_count()
			if count:
				self.index = (self.index + (-1 if action == "K1" else 1)) % count
				self.notice = ""
			return None
		if action != "K3":
			return None
		try:
			if self.view == "owners":
				if self.index == len(self.world.owners):
					self.show("owner_name")
				else:
					owner = self.world.owners[self.index]
					if owner["name"] not in OWNER_NAMES and not self.owner_names():
						raise ValueError("五个名字已使用，旧存档仍保留")
					self.owner_id = owner["id"]
					self.pet_id = None
					self.show("pets" if owner["name"] in OWNER_NAMES else "owner_migrate")
			elif self.view in ("owner_name", "owner_migrate"):
				name = self.owner_names()[self.index]
				if self.view == "owner_migrate":
					self.world.rename_owner(self.owner_id, name)
				else:
					self.owner_id = self.world.create_owner(name)
				self.pet_id = None
				self.show("pets")
			elif self.view == "pets":
				pets = self.world.owner(self.owner_id)["pets"]
				if self.index == len(pets):
					if pets:
						self.pet_id = pets[0]["id"]
						self.show("confirm_release")
					else:
						self.show("adopt")
				else:
					self.pet_id = pets[self.index]["id"]
					self.show("confirm_keep" if len(pets) > 1 else "home")
			elif self.view in ("confirm_release", "confirm_keep"):
				if self.index == 0:
					self.show("pets")
				elif self.view == "confirm_release":
					self.world.release(self.owner_id, self.pet_id)
					self.pet_id = None
					self.show("pets")
					self.notice = "已删除，可以重新领养"
				else:
					self.world.retain_pet(self.owner_id, self.pet_id)
					self.show("home")
					self.notice = "已保留这位伙伴"
			elif self.view == "adopt":
				self.pet_id = self.world.adopt(self.owner_id, SPECIES[self.index].key)
				self.show("home")
			elif self.view == "home":
				selected = HOME_ACTIONS[self.index][0]
				if selected == "accessory":
					self.show("accessory")
				elif selected == "rename":
					self.show("rename")
				elif selected == "pets":
					self.show("pets")
				elif selected == "skill":
					self.show("skills")
				elif selected == "tasks":
					self.show("tasks")
				elif selected == "stop":
					if not self.world.visible_pet(self.owner_id, self.pet_id)["activity"]:
						raise ValueError("现在没有进行中的行动")
					self.show("confirm_stop")
				else:
					self.request_activity(selected)
			elif self.view == "skills":
				self.request_activity("skill", self.index)
			elif self.view == "tasks":
				self.request_activity(DAILY_TASKS[self.index][0])
			elif self.view == "confirm_action":
				if self.index == 0:
					self.show(self.pending_origin)
				elif self.pending_action == "play":
					self.world.check_care(self.owner_id, self.pet_id, "play")
					self.start_game()
				else:
					action = self.pending_action
					self.world.care(self.owner_id, self.pet_id, action, skill=self.pending_skill)
					self.show("home", HOME_INDEX[action])
					self.notice = "%s开始啦！" % ACTIVITIES[action][0]
			elif self.view == "confirm_stop":
				if self.index == 0:
					self.show("home", HOME_INDEX["stop"])
				else:
					cancelled = self.world.cancel_activity(self.owner_id, self.pet_id)
					self.show("home", HOME_INDEX["stop"])
					self.notice = "已结束行动" if cancelled else "行动已经完成啦"
			elif self.view == "game":
				self.guess = self.index
				self.won = self.guess == self.target
				self.world.care(self.owner_id, self.pet_id, "play", won=self.won)
				self.show("home", HOME_INDEX["play"])
				self.notice = "找到星星啦！" if self.won else "一起玩真开心！"
			elif self.view == "result":
				self.show("home", HOME_INDEX["play"])
			elif self.view == "accessory":
				self.world.equip(self.owner_id, self.pet_id, ACCESSORIES[self.index][0])
				self.show("home", HOME_INDEX["accessory"])
				self.notice = "换好啦！"
			elif self.view == "rename":
				self.world.rename(self.owner_id, self.pet_id, self.pet_names()[self.index])
				self.show("home", HOME_INDEX["rename"])
				self.notice = "名字真好听！"
		except (OSError, ValueError) as error:
			self.notice = str(error) if isinstance(error, ValueError) else "保存失败，请检查存储"
			if isinstance(error, OSError):
				print("宠物存档保存失败:", error)
		return None


INK = (54, 68, 65)
PAPER = (255, 255, 252)
JADE = (34, 120, 106)
CORAL = (193, 81, 69)
GOLD = (235, 182, 65)
SKY = (220, 245, 246)
GRASS = (183, 226, 190)
OUTLINE = (91, 71, 66)


def star_points(center, radius, inner=None):
	inner = inner if inner is not None else radius * 0.45
	return [(round(center[0] + (radius if index % 2 == 0 else inner) * math.cos(-math.pi / 2 + index * math.pi / 5)),
			 round(center[1] + (radius if index % 2 == 0 else inner) * math.sin(-math.pi / 2 + index * math.pi / 5)))
			for index in range(10)]


def outlined_ellipse(surface, color, rect, outline=OUTLINE, border=3):
	pygame.draw.ellipse(surface, outline, rect)
	pygame.draw.ellipse(surface, color, pygame.Rect(rect).inflate(-border * 2, -border * 2))


def draw_face(surface, left, right, y, sleeping=False):
	for x in (left, right):
		if sleeping:
			pygame.draw.arc(surface, OUTLINE, (x - 6, y - 2, 12, 8), math.pi, math.tau, 2)
		else:
			pygame.draw.ellipse(surface, OUTLINE, (x - 5, y - 6, 10, 13))
			pygame.draw.circle(surface, PAPER, (x - 2, y - 3), 2)
	pygame.draw.ellipse(surface, (237, 153, 151), (left - 15, y + 7, 13, 6))
	pygame.draw.ellipse(surface, (237, 153, 151), (right + 2, y + 7, 13, 6))


class PetArt:
	def __init__(self):
		self.cache = {}

	def sprite(self, species, size, sleeping=False, gesture=0):
		key = (species.key, size, bool(sleeping), gesture)
		if key in self.cache:
			return self.cache[key]
		if species.image:
			path = ROOT_DIR / "Pokemon" / "pokedex_data" / "images" / species.image
			try:
				image = pygame.image.load(str(path))
				result = pygame.transform.smoothscale(image, (size, size))
				self.cache[key] = result
				return result
			except (OSError, pygame.error) as error:
				print("宠物图片不可用:", path, error)
		canvas = pygame.Surface((160, 160), pygame.SRCALPHA)
		if species.key == "capybara":
			self.capybara(canvas, sleeping)
		elif species.key == "teto":
			self.teto(canvas, sleeping, gesture)
		else:
			self.dinosaur(canvas, sleeping)
		result = pygame.transform.smoothscale(canvas, (size, size))
		self.cache[key] = result
		return result

	def capybara(self, canvas, sleeping):
		outlined_ellipse(canvas, (177, 123, 92), (32, 75, 105, 61))
		for x in (42, 107):
			outlined_ellipse(canvas, (153, 103, 78), (x, 118, 24, 22))
		outlined_ellipse(canvas, (180, 129, 99), (43, 38, 18, 19), border=2)
		outlined_ellipse(canvas, (180, 129, 99), (104, 38, 18, 19), border=2)
		outlined_ellipse(canvas, (199, 151, 114), (26, 44, 115, 86))
		outlined_ellipse(canvas, (219, 175, 139), (54, 83, 58, 34), border=2)
		draw_face(canvas, 55, 111, 77, sleeping)
		pygame.draw.ellipse(canvas, OUTLINE, (69, 92, 6, 4))
		pygame.draw.ellipse(canvas, OUTLINE, (91, 92, 6, 4))
		pygame.draw.arc(canvas, OUTLINE, (76, 93, 14, 11), math.pi, math.tau, 2)
		pygame.draw.circle(canvas, (233, 164, 64), (85, 43), 15)
		pygame.draw.ellipse(canvas, (105, 168, 112), (82, 25, 13, 8))
		pygame.draw.line(canvas, (135, 101, 66), (85, 29), (85, 35), 2)

	def dinosaur(self, canvas, sleeping):
		pygame.draw.polygon(canvas, OUTLINE, ((48, 101), (14, 95), (23, 126), (51, 132)))
		pygame.draw.polygon(canvas, (89, 170, 132), ((44, 104), (20, 100), (27, 122), (47, 127)))
		for x, y in ((109, 67), (119, 81), (121, 97)):
			pygame.draw.polygon(canvas, (60, 135, 105), ((x, y + 14), (x + 8, y - 3), (x + 15, y + 15)))
		outlined_ellipse(canvas, (105, 192, 153), (42, 76, 85, 66))
		outlined_ellipse(canvas, (216, 240, 198), (67, 94, 40, 43), border=2)
		for x in (49, 102):
			outlined_ellipse(canvas, (91, 176, 139), (x, 123, 24, 18))
		outlined_ellipse(canvas, (112, 203, 163), (33, 30, 101, 82))
		draw_face(canvas, 60, 108, 70, sleeping)
		pygame.draw.arc(canvas, OUTLINE, (75, 77, 20, 13), math.pi, math.tau, 2)
		pygame.draw.ellipse(canvas, (139, 218, 180), (50, 37, 30, 10))

	def teto(self, canvas, sleeping, gesture=0):
		hair_outline = (112, 43, 61)
		hair_base = (202, 70, 91)
		hair_light = (238, 110, 125)
		clothes_outline = (73, 67, 76)
		skin = (255, 226, 205)
		drill = pygame.Surface((44, 88), pygame.SRCALPHA)
		pygame.draw.polygon(drill, hair_outline, ((36, 2), (20, 1), (6, 4), (2, 9), (4, 17),
															 (3, 23), (6, 31), (7, 37), (9, 44), (12, 51),
															 (14, 58), (18, 66), (21, 72), (25, 82), (28, 86),
															 (31, 82), (30, 76), (33, 70), (32, 63), (35, 57),
															 (34, 50), (37, 43), (36, 36), (39, 29), (38, 22),
															 (41, 15), (40, 8)))
		pygame.draw.polygon(drill, hair_base, ((34, 4), (20, 3), (8, 6), (5, 11), (7, 18),
													   (6, 24), (9, 32), (10, 39), (13, 46), (15, 53),
													   (18, 60), (21, 68), (25, 76), (28, 81), (29, 74),
													   (31, 68), (30, 62), (33, 55), (32, 49), (35, 42),
													   (34, 35), (37, 28), (36, 21), (38, 14), (37, 8)))
		pygame.draw.ellipse(drill, (123, 45, 64), (5, 4, 33, 11))
		pygame.draw.arc(drill, hair_light, (6, 5, 31, 9), math.pi, math.tau, 2)
		for top, left, right in ((14, 5, 38), (26, 7, 36), (38, 10, 34),
								 (50, 13, 32), (62, 17, 30), (73, 21, 28)):
			pygame.draw.polygon(drill, hair_light, ((left, top), (right, top - 4),
															 (right - 1, top + 3), (left + 3, top + 8)))
			pygame.draw.line(drill, (160, 49, 72), (left + 4, top + 8), (right - 1, top + 3), 2)
		canvas.blit(drill, (5, 25))
		canvas.blit(pygame.transform.flip(drill, True, False), (111, 25))
		pygame.draw.ellipse(canvas, hair_outline, (37, 17, 86, 81))
		pygame.draw.ellipse(canvas, hair_base, (40, 19, 80, 76))
		for leg_x in (65, 85):
			pygame.draw.rect(canvas, (194, 148, 143), (leg_x, 125, 14, 25), border_radius=5)
			pygame.draw.rect(canvas, skin, (leg_x + 2, 126, 10, 23), border_radius=4)
			pygame.draw.rect(canvas, (55, 55, 65), (leg_x - 1, 143, 16, 13), border_radius=4)
			pygame.draw.rect(canvas, (202, 70, 91), (leg_x, 143, 14, 3), border_radius=1)
			pygame.draw.line(canvas, (220, 215, 205), (leg_x + 4, 148), (leg_x + 10, 151), 1)
			pygame.draw.line(canvas, (220, 215, 205), (leg_x + 10, 148), (leg_x + 4, 151), 1)
		pygame.draw.polygon(canvas, clothes_outline, ((59, 111), (101, 111), (110, 130), (106, 135),
																 (53, 135), (49, 130)))
		pygame.draw.polygon(canvas, (171, 168, 177), ((61, 114), (99, 114), (107, 129), (104, 132),
																 (55, 132), (52, 129)))
		pygame.draw.polygon(canvas, (201, 69, 89), ((52, 128), (108, 128), (106, 134), (54, 134)))
		pygame.draw.polygon(canvas, (62, 59, 68), ((54, 134), (106, 134), (104, 137), (99, 135),
																 (94, 137), (89, 135), (84, 137), (79, 135),
																 (74, 137), (69, 135), (64, 137), (59, 135), (56, 137)))
		for pleat_x in (64, 76, 88, 99):
			pygame.draw.line(canvas, (117, 112, 122), (pleat_x, 116), (pleat_x - 2, 128), 1)
		for side in (-1, 1):
			shoulder = 80 + side * 22
			hand_x = 80 + side * (43 if gesture == side else 35)
			hand_y = 87 if gesture == side else 111
			pygame.draw.line(canvas, clothes_outline, (shoulder, 96), (hand_x, hand_y), 13)
			pygame.draw.line(canvas, (172, 168, 178), (shoulder, 96), (hand_x, hand_y), 9)
			pygame.draw.line(canvas, (199, 67, 87), (hand_x - 3, hand_y - 4), (hand_x + 3, hand_y + 1), 3)
			pygame.draw.circle(canvas, clothes_outline, (hand_x, hand_y + 2), 6)
			pygame.draw.circle(canvas, skin, (hand_x, hand_y + 1), 4)
		pygame.draw.polygon(canvas, clothes_outline, ((59, 89), (101, 89), (105, 98), (101, 118),
																 (59, 118), (55, 98)))
		pygame.draw.polygon(canvas, (187, 184, 192), ((61, 91), (99, 91), (102, 98), (99, 116),
																 (61, 116), (58, 98)))
		pygame.draw.polygon(canvas, (126, 122, 132), ((62, 91), (79, 98), (98, 91), (95, 102), (80, 107), (65, 102)))
		pygame.draw.line(canvas, (200, 66, 87), (95, 96), (88, 116), 3)
		pygame.draw.line(canvas, (80, 78, 86), (65, 113), (95, 94), 3)
		for button in ((70, 103), (76, 111), (91, 104), (87, 112)):
			pygame.draw.circle(canvas, (216, 180, 94), button, 2)
		pygame.draw.rect(canvas, skin, (73, 82, 14, 15), border_radius=5)
		pygame.draw.ellipse(canvas, hair_outline, (46, 28, 68, 69))
		pygame.draw.ellipse(canvas, skin, (48, 30, 64, 64))
		pygame.draw.ellipse(canvas, (255, 234, 218), (53, 34, 54, 55))
		pygame.draw.polygon(canvas, hair_outline, ((41, 49), (43, 34), (51, 23), (65, 19),
															 (82, 19), (94, 20), (109, 27), (118, 38),
															 (119, 53), (112, 61), (105, 54), (98, 43),
															 (94, 53), (86, 60), (80, 49), (77, 39),
															 (69, 50), (59, 56), (52, 51), (47, 62), (41, 61)))
		pygame.draw.polygon(canvas, hair_base, ((43, 48), (46, 34), (53, 25), (66, 21),
													   (81, 21), (93, 22), (107, 29), (115, 39),
													   (117, 51), (112, 57), (105, 51), (98, 38),
													   (92, 50), (86, 56), (81, 45), (78, 34),
													   (69, 47), (59, 53), (52, 47), (46, 58), (43, 58)))
		pygame.draw.lines(canvas, hair_light, False, ((48, 39), (54, 29), (65, 25), (75, 24)), 3)
		pygame.draw.lines(canvas, (237, 114, 127), False, ((87, 24), (95, 29), (99, 36)), 2)
		pygame.draw.lines(canvas, (160, 49, 72), False, ((79, 25), (76, 33), (78, 42), (84, 53)), 1)
		pygame.draw.lines(canvas, hair_outline, False, ((79, 21), (74, 15), (74, 9), (78, 5), (84, 5), (89, 8)), 3)
		pygame.draw.lines(canvas, hair_light, False, ((79, 19), (76, 14), (76, 9), (80, 7), (85, 7)), 1)
		pygame.draw.polygon(canvas, hair_outline, ((46, 48), (52, 51), (52, 72), (56, 90), (48, 86), (43, 72)))
		pygame.draw.polygon(canvas, hair_base, ((46, 51), (50, 53), (50, 73), (53, 86), (49, 83), (45, 71)))
		pygame.draw.polygon(canvas, hair_outline, ((114, 48), (108, 51), (108, 72), (104, 90), (112, 86), (117, 72)))
		pygame.draw.polygon(canvas, hair_base, ((114, 51), (110, 53), (110, 73), (107, 86), (111, 83), (115, 71)))
		for eye_x in (58, 86):
			if sleeping:
				pygame.draw.arc(canvas, (100, 57, 69), (eye_x, 65, 17, 9), math.pi, math.tau, 2)
			else:
				pygame.draw.ellipse(canvas, (89, 47, 59), (eye_x, 58, 18, 23))
				pygame.draw.ellipse(canvas, (255, 250, 243), (eye_x + 1, 59, 16, 21))
				pygame.draw.ellipse(canvas, (190, 56, 78), (eye_x + 4, 60, 11, 19))
				pygame.draw.ellipse(canvas, (103, 40, 58), (eye_x + 7, 62, 6, 13))
				pygame.draw.circle(canvas, (255, 255, 255), (eye_x + 7, 63), 2)
				pygame.draw.circle(canvas, (255, 219, 217), (eye_x + 12, 74), 1)
			pygame.draw.ellipse(canvas, (246, 170, 167), (eye_x - 3, 80, 13, 5))
		pygame.draw.lines(canvas, (127, 69, 73), False, ((76, 84), (78, 86), (81, 87), (84, 86), (86, 84)), 1)
		pygame.draw.polygon(canvas, (119, 109, 116), ((108, 22), (103, 12), (104, 5), (110, 9), (115, 21)))
		pygame.draw.polygon(canvas, (255, 255, 248), ((109, 20), (105, 12), (106, 7), (110, 10), (113, 20)))
		pygame.draw.polygon(canvas, (119, 109, 116), ((112, 20), (119, 8), (127, 4), (126, 15), (117, 25)))
		pygame.draw.polygon(canvas, (255, 255, 248), ((114, 20), (120, 10), (125, 7), (124, 14), (117, 22)))
		pygame.draw.circle(canvas, (232, 224, 218), (113, 21), 3)

	def draw_accessory(self, surface, key, center, size, species_key=None):
		if key == "none":
			return
		if species_key == "teto":
			x = center[0] - size // 10
			y = center[1] - size // 3
		else:
			x = center[0] + size // 4
			y = center[1] - size // 5
		radius = max(4, size // 13)
		if key == "flower":
			for dx, dy in ((-radius, 0), (radius, 0), (0, -radius), (0, radius)):
				pygame.draw.circle(surface, (244, 139, 155), (x + dx // 2, y + dy // 2), radius // 2 + 1)
			pygame.draw.circle(surface, (255, 214, 86), (x, y), radius // 2)
		elif key == "ribbon":
			pygame.draw.polygon(surface, (232, 107, 130), ((x, y), (x - radius * 2, y - radius),
																				 (x - radius * 2, y + radius)))
			pygame.draw.polygon(surface, (232, 107, 130), ((x, y), (x + radius * 2, y - radius),
																				 (x + radius * 2, y + radius)))
			pygame.draw.circle(surface, (255, 224, 169), (x, y), max(2, radius // 2))
		else:
			points = ((x - radius * 2, y + radius), (x - radius * 2, y - radius), (x - radius, y),
					  (x, y - radius * 2), (x + radius, y), (x + radius * 2, y - radius),
					  (x + radius * 2, y + radius))
			pygame.draw.polygon(surface, (243, 181, 54), points)
			pygame.draw.polygon(surface, (164, 111, 49), points, 2)

	def draw_effect(self, surface, effect, rect, now, variant=0):
		width = rect.width
		center_x, center_y = rect.center
		motion = math.sin(now * 4)
		if effect == "feed":
			bowl = pygame.Rect(center_x + width // 5, rect.bottom - width // 5, width // 4, width // 9)
			pygame.draw.ellipse(surface, (198, 104, 76), bowl.inflate(4, 4))
			pygame.draw.ellipse(surface, (252, 208, 124), bowl)
			pygame.draw.circle(surface, (226, 151, 70), (bowl.centerx, bowl.y - 5 - round((motion + 1) * 5)), 3)
			progress = (math.sin(now * 3) + 1) / 2
			spoon_x = round(bowl.centerx * (1 - progress) + (center_x + width // 8) * progress)
			spoon_y = round(bowl.y * (1 - progress) + (center_y + width // 14) * progress)
			pygame.draw.line(surface, (105, 139, 142), (spoon_x, spoon_y),
							 (min(rect.right - 2, spoon_x + max(6, width // 10)), spoon_y - max(4, width // 14)), 2)
			pygame.draw.ellipse(surface, (247, 234, 213), (spoon_x - 3, spoon_y - 2, 7, 5))
			pygame.draw.circle(surface, (223, 151, 77), (spoon_x, spoon_y - 1), 2)
		elif effect in ("wash", "water", "bubbles"):
			for index in range(6):
				position_x = rect.left + width // 8 + (index * 23 + round(motion * 4)) % max(1, width * 3 // 4)
				if effect == "wash":
					position_x = center_x + (-1 if index % 2 == 0 else 1) * width * 2 // 5 + round(motion * 3)
				position_y = rect.bottom - 5 - (round(now * 18) + index * 19) % max(1, rect.height - 12)
				radius = max(3, width // 18 + index % 2)
				if effect in ("wash", "bubbles"):
					pygame.draw.circle(surface, (234, 255, 255) if effect == "wash" else (173, 228, 245),
									   (position_x, position_y), radius)
					pygame.draw.circle(surface, (114, 195, 220), (position_x, position_y), radius, 1)
				else:
					pygame.draw.ellipse(surface, (87, 181, 223), (position_x, position_y, radius + 1, radius * 2))
			if effect == "wash":
				sponge = pygame.Rect(0, 0, max(10, width // 7), max(7, width // 11))
				sponge.center = (rect.right - width // 6, center_y + round(math.sin(now * 6) * width / 10))
				pygame.draw.rect(surface, (185, 140, 62), sponge.inflate(2, 2), border_radius=3)
				pygame.draw.rect(surface, (251, 211, 105), sponge, border_radius=3)
				for offset in (-4, 0, 4):
					pygame.draw.circle(surface, PAPER, (sponge.centerx + offset, sponge.top), 2)
		elif effect in ("pat", "heart"):
			for index in range(3):
				position_x = center_x + (index - 1) * width // 4 + round(motion * 3)
				if effect == "pat":
					position_x = center_x + (-1 if index % 2 == 0 else 1) * width * 3 // 8
				position_y = rect.bottom - 8 - (round(now * 15) + index * 23) % max(1, rect.height - 15)
				radius = max(3, width // 21)
				pygame.draw.circle(surface, (238, 112, 142), (position_x - radius, position_y), radius)
				pygame.draw.circle(surface, (238, 112, 142), (position_x + radius, position_y), radius)
				pygame.draw.polygon(surface, (238, 112, 142), ((position_x - radius * 2, position_y),
																	   (position_x + radius * 2, position_y),
																	   (position_x, position_y + radius * 2)))
			if effect == "pat":
				hand = pygame.Rect(0, 0, max(12, width // 6), max(8, width // 12))
				hand.center = (center_x + width // 5 + round(math.sin(now * 4.5) * width / 25),
							   rect.top + width // 4 + round((motion + 1) * 2))
				sleeve_end = (min(rect.right - 1, hand.right + max(8, width // 10)), hand.top - max(3, width // 18))
				pygame.draw.line(surface, (99, 147, 151), hand.center, sleeve_end, max(7, width // 10))
				pygame.draw.line(surface, (151, 207, 204), hand.center, sleeve_end, max(5, width // 12))
				pygame.draw.ellipse(surface, (166, 119, 105), hand.inflate(2, 2))
				pygame.draw.ellipse(surface, (255, 221, 193), hand)
				for index in range(3):
					pygame.draw.line(surface, (214, 166, 148), (hand.left + 3 + index * 3, hand.top + 2),
									 (hand.left + 3 + index * 3, hand.top + 4), 1)
		elif effect in ("play", "star"):
			for index in range(4):
				angle = now * 2 + index * math.tau / 4
				position = (center_x + round(math.cos(angle) * width * 0.38),
							center_y + round(math.sin(angle) * rect.height * 0.35))
				pygame.draw.polygon(surface, (255, 193, 64), star_points(position, max(4, width // 16)))
			if effect == "play":
				radius = max(5, width // 12)
				ball_x = rect.left + radius + 2 + round((motion + 1) * width / 30)
				ball_y = rect.bottom - radius - 4 - round(abs(math.sin(now * 5)) * width / 8)
				pygame.draw.circle(surface, (194, 109, 84), (ball_x, ball_y), radius + 1)
				pygame.draw.circle(surface, (251, 193, 89), (ball_x, ball_y), radius)
				pygame.draw.arc(surface, (250, 247, 226), (ball_x - radius + 2, ball_y - radius + 2,
																		 radius * 2 - 4, radius * 2 - 4), 0, math.pi, 2)
		elif effect in ("explore", "dash"):
			for index in range(3):
				position_y = rect.centery + index * max(5, width // 10)
				position_x = rect.left + (round(now * 32) + index * 13) % max(1, width // 3)
				pygame.draw.line(surface, (125, 193, 169), (position_x, position_y),
								 (position_x + max(8, width // 6), position_y), 3)
		elif effect == "sleep":
			for index in range(2):
				position_x = rect.right - width // 5 + index * 7
				position_y = rect.top + width // 5 - (round(now * 7) + index * 9) % max(1, width // 4)
				pygame.draw.lines(surface, (71, 151, 151), False,
								  ((position_x, position_y), (position_x + 7, position_y),
								   (position_x, position_y + 7), (position_x + 7, position_y + 7)), 2)
		elif effect == "medicine":
			for index in range(2):
				position_x = center_x + (-1 if index == 0 else 1) * width // 3
				position_y = center_y - width // 6 + round(math.sin(now * 3 + index) * 8)
				pygame.draw.line(surface, (230, 112, 111), (position_x - 5, position_y), (position_x + 5, position_y), 3)
				pygame.draw.line(surface, (230, 112, 111), (position_x, position_y - 5), (position_x, position_y + 5), 3)
			kit = pygame.Rect(0, 0, max(14, width // 6), max(11, width // 9))
			kit.midbottom = (rect.right - width // 8, rect.bottom - 5)
			pygame.draw.rect(surface, (152, 177, 164), kit.inflate(2, 2), border_radius=3)
			pygame.draw.rect(surface, PAPER, kit, border_radius=2)
			pygame.draw.line(surface, (222, 106, 104), (kit.centerx - 3, kit.centery), (kit.centerx + 3, kit.centery), 2)
			pygame.draw.line(surface, (222, 106, 104), (kit.centerx, kit.centery - 3), (kit.centerx, kit.centery + 3), 2)
		elif effect == "electric":
			for side in (-1, 1):
				position_x = center_x + side * width // 3 + round(motion * 3)
				position_y = center_y - width // 4 + round(math.cos(now * 3) * 5)
				pygame.draw.lines(surface, (252, 194, 44), False,
								  ((position_x, position_y), (position_x - side * 6, position_y + 10),
								   (position_x + side * 3, position_y + 10), (position_x - side * 5, position_y + 22)), 4)
		elif effect == "thunder":
			position_x = rect.right - width // 4 + round(math.sin(now * 5) * 5)
			position_y = rect.top + width // 10
			points = ((position_x, position_y), (position_x - 12, position_y + 23),
					  (position_x - 2, position_y + 23), (position_x - 14, position_y + 43),
					  (position_x + 14, position_y + 17), (position_x + 4, position_y + 17),
					  (position_x + 12, position_y))
			pygame.draw.polygon(surface, (255, 207, 54), points)
			pygame.draw.polygon(surface, (224, 152, 38), points, 2)
		elif effect == "fire":
			for index in range(7 if variant else 4):
				position_x = center_x + width // 3 + round(math.sin(now * 5 + index) * 5)
				position_y = rect.bottom - 8 - (round(now * 23) + index * 15) % max(1, rect.height // 2)
				radius = max(3, width // 14 - index % 3)
				pygame.draw.circle(surface, (238, 100, 65), (position_x, position_y), radius)
				pygame.draw.circle(surface, (255, 203, 87), (position_x, position_y + 1), max(2, radius // 2))
		elif effect == "leaf":
			for index in range(6 if variant else 4):
				position_x = rect.left + (round(now * 25) + index * 23) % max(1, width)
				position_y = rect.top + width // 5 + index * width // 7 + round(motion * 3)
				pygame.draw.ellipse(surface, (90, 177, 108), (position_x, position_y, 11, 6))
				pygame.draw.line(surface, (220, 244, 179), (position_x + 2, position_y + 4), (position_x + 9, position_y + 1), 1)
		elif effect == "music":
			for index in range(5 if variant else 3):
				position_x = rect.left + width // 6 + index * width // (5 if variant else 3)
				position_y = rect.top + width // 3 + round(math.sin(now * 3 + index) * 9)
				color = ((211, 98, 134), (80, 157, 184), (222, 159, 67))[index % 3]
				pygame.draw.ellipse(surface, color, (position_x, position_y, 8, 5))
				pygame.draw.line(surface, color, (position_x + 7, position_y + 2), (position_x + 7, position_y - 9), 2)
				pygame.draw.line(surface, color, (position_x + 7, position_y - 9), (position_x + 12, position_y - 6), 2)
		elif effect == "flower":
			for index in range(3):
				position_x = rect.left + (round(now * 14) + index * 29) % max(1, width)
				position_y = rect.top + width // 5 + index * width // 4 + round(motion * 3)
				for offset_x, offset_y in ((-3, 0), (3, 0), (0, -3), (0, 3)):
					pygame.draw.circle(surface, (244, 145, 161), (position_x + offset_x, position_y + offset_y), 3)
				pygame.draw.circle(surface, (255, 218, 91), (position_x, position_y), 2)

	def animated_pose(self, image, kind, effect, now, variant):
		if not kind:
			return image, 0, 0
		size = image.get_width()
		sway, bob = 0, 0
		if kind == "sleep":
			breath = math.sin(now * 2.0)
			width = max(1, round(size * (0.98 + breath * 0.02)))
			height = max(1, round(size * (0.94 + breath * 0.04)))
			image = pygame.transform.smoothscale(image, (width, height))
			return image, 0, (size - height) // 2
		if kind == "feed":
			motion = math.sin(now * 5.5)
			angle = -4 - motion * 5
			bob = round((motion + 1) * min(3, size // 30))
		elif kind == "play":
			motion = math.sin(now * 5)
			angle = motion * 9
			bob = -round(abs(motion) * min(10, size // 10))
		elif kind == "explore" or effect == "dash":
			motion = math.sin(now * 6)
			angle = motion * 8
			sway = round(motion * min(7, size // 12))
			bob = -round(abs(motion) * min(4, size // 25))
		elif kind == "wash":
			motion = math.sin(now * 9)
			angle = motion * 8
			sway = round(motion * min(4, size // 25))
		elif kind == "pat":
			motion = math.sin(now * 4.5)
			angle = 4 + motion * 5
			sway = round(motion * min(3, size // 30))
		elif kind == "medicine":
			motion = math.sin(now * 3)
			angle = motion * 5
			bob = -round((motion + 1) * min(2, size // 40))
		elif effect in ("music", "heart", "flower"):
			motion = math.sin(now * 4.5)
			angle = motion * (7 + min(variant * 2, 4))
			bob = -round(abs(motion) * min(5, size // 20))
		else:
			motion = math.sin(now * 7)
			angle = motion * (6 + variant)
			bob = -round(abs(motion) * min(4, size // 25))
		return pygame.transform.rotozoom(image, angle, 0.92), sway, bob

	def draw(self, surface, species, rect, now, sleeping=False, accessory="none", activity=None, dirt=0):
		size = max(24, min(rect.width, rect.height) - 8)
		blink = sleeping or now % 4.0 < 0.12
		kind = activity["kind"] if activity else None
		effect = kind
		variant = 0
		if kind == "skill":
			variant = activity["skill"]
			effect = SKILLS[species.key][variant][1]
		gesture = 0
		if species.key == "teto" and kind and kind != "sleep":
			if math.sin(now * 5) >= 0:
				gesture = 1
			elif kind in ("play", "explore", "skill"):
				gesture = -1
		image = self.sprite(species, size, blink, gesture)
		if accessory != "none" or dirt:
			image = image.copy()
			center = (size // 2, size // 2)
			for index in range(min(3, dirt)):
				position = (center[0] + (-1 if index % 2 == 0 else 1) * (size // 6 + index * 2),
							center[1] + size // 7 + index * max(3, size // 14))
				pygame.draw.ellipse(image, (139, 102, 74), (position[0], position[1], max(5, size // 9), max(4, size // 13)))
				pygame.draw.circle(image, (184, 137, 95), (position[0] + 3, position[1] + 2), max(1, size // 40))
			self.draw_accessory(image, accessory, center, size, species.key)
		image, sway, action_bob = self.animated_pose(image, kind, effect, now, variant)
		bob = 0 if sleeping else round(math.sin(now * 3.2) * 2)
		center = (rect.centerx + sway, rect.centery + bob + action_bob)
		image_rect = image.get_rect(center=center)
		image_rect.clamp_ip(surface.get_rect())
		if effect in ("explore", "dash"):
			self.draw_effect(surface, effect, rect, now, variant)
		surface.blit(image, image_rect)
		if effect and effect not in ("explore", "dash"):
			self.draw_effect(surface, effect, rect, now, variant)


class PetDisplay:
	def __init__(self, screen):
		self.screen = screen
		self.width, self.height = screen.get_size()
		self.portrait = self.height > self.width
		self.footer_top = self.height - 27
		self.title_font = spi_lcd.load_font(18)
		self.title_font.set_bold(True)
		self.name_font = spi_lcd.load_font(15)
		self.small_font = spi_lcd.load_font(11)
		self.button_font = spi_lcd.load_font(12)
		self.fit_fonts = [spi_lcd.load_font(size) for size in (15, 14, 13, 12, 11, 10)]
		self.art = PetArt()
		self.click_targets = []
		self.buttons = [pygame.Rect(index * self.width // 3, self.footer_top,
									(index + 1) * self.width // 3 - index * self.width // 3, 27)
						for index in range(3)]
		if self.portrait:
			self.selection_scene = pygame.Rect(10, 43, self.width - 20, 132)
			self.list_area = pygame.Rect(10, 180, self.width - 20, 104)
			self.home_scene = pygame.Rect(10, 59, self.width - 20, 136)
			self.stat_area = pygame.Rect(10, 199, self.width - 20, 43)
			self.action_area = pygame.Rect(10, 246, self.width - 20, 39)
		else:
			self.selection_scene = pygame.Rect(8, 42, 136, 160)
			self.list_area = pygame.Rect(152, 42, self.width - 160, 158)
			self.home_scene = pygame.Rect(8, 42, 143, 160)
			self.stat_area = pygame.Rect(161, 65, self.width - 171, 91)
			self.action_area = pygame.Rect(159, 163, self.width - 169, 41)

	def text(self, value, font, color, position):
		self.screen.blit(font.render(str(value), True, color), position)

	def centered(self, value, font, color, center):
		image = font.render(str(value), True, color)
		self.screen.blit(image, image.get_rect(center=center))

	def fit(self, value, width, fonts=None):
		fonts = self.fit_fonts if fonts is None else fonts
		for font in fonts:
			if font.size(value)[0] <= width:
				return font, value
		font = fonts[-1]
		while value and font.size(value + "…")[0] > width:
			value = value[:-1]
		return font, value + "…"

	def header(self, game):
		self.text("宠物乐园", self.title_font, INK, (10, 7))
		if game is not None and game.owner_id and game.view not in ("owners", "owner_name", "owner_migrate"):
			status = game.world.owner(game.owner_id)["name"]
		else:
			status = "一起长大"
		image = self.small_font.render(status, True, JADE)
		self.screen.blit(image, (self.width - image.get_width() - 10, 14))
		pygame.draw.line(self.screen, (183, 219, 208), (10, 34), (self.width - 10, 34))

	def footer(self, labels, enabled=(True, True, True)):
		pygame.draw.rect(self.screen, (218, 237, 228), (0, self.footer_top, self.width, 27))
		colors = ((CORAL, PAPER), (JADE, PAPER), (GOLD, INK))
		for index, (label, rect) in enumerate(zip(labels, self.buttons)):
			color, foreground = colors[index] if enabled[index] else ((219, 228, 223), (83, 92, 89))
			button = rect.inflate(-5, -6)
			pygame.draw.rect(self.screen, color, button, border_radius=4)
			self.centered(label, self.button_font, foreground, button.center)

	def park_background(self, scene):
		width, height = scene.get_size()
		horizon = round(height * (0.50 if width >= height else 0.42))
		scene.fill((186, 233, 240))
		pygame.draw.circle(scene, (255, 222, 125), (width - 18, 17), 10)
		for cloud_x, cloud_y in ((width // 4, 12), (width * 3 // 5, 20)):
			pygame.draw.ellipse(scene, (248, 255, 253), (cloud_x - 12, cloud_y, 27, 9))
			pygame.draw.ellipse(scene, (248, 255, 253), (cloud_x - 5, cloud_y - 5, 14, 14))
		pygame.draw.ellipse(scene, (149, 207, 174), (-width // 4, horizon - 22, width, 54))
		pygame.draw.ellipse(scene, (169, 220, 183), (width // 3, horizon - 19, width, 54))
		pygame.draw.rect(scene, (187, 228, 177), (0, horizon, width, height - horizon))
		pygame.draw.polygon(scene, (236, 225, 179), ((width * 46 // 100, horizon + 4),
																 (width * 55 // 100, horizon + 4),
																 (width * 76 // 100, height),
																 (width * 24 // 100, height)))
		fence_y = horizon + 5
		for y in (fence_y, fence_y + 7):
			pygame.draw.line(scene, (237, 245, 220), (0, y), (width, y), 3)
		for x in range(5, width, 16):
			pygame.draw.line(scene, (250, 249, 229), (x, fence_y - 4), (x, fence_y + 11), 3)
		tree_x = max(18, width // 9)
		pygame.draw.rect(scene, (157, 111, 81), (tree_x - 4, horizon - 20, 8, 24), border_radius=3)
		for offset_x, offset_y, radius in ((-9, -22, 12), (8, -23, 12), (0, -31, 14)):
			pygame.draw.circle(scene, (99, 180, 130), (tree_x + offset_x, horizon + offset_y), radius)
		pygame.draw.circle(scene, (143, 211, 157), (tree_x - 4, horizon - 32), 5)
		house_width = max(31, min(48, width // 4))
		house_height = max(25, min(35, height // 4))
		house = pygame.Rect(width - house_width - 12, horizon - house_height + 3, house_width, house_height)
		pygame.draw.rect(scene, (255, 242, 205), house, border_radius=3)
		pygame.draw.polygon(scene, (224, 122, 103), ((house.left - 4, house.top + 2),
															 (house.centerx, house.top - 13),
															 (house.right + 4, house.top + 2)))
		pygame.draw.rect(scene, (116, 182, 170), (house.centerx - 5, house.bottom - 15, 10, 15), border_radius=4)
		pygame.draw.circle(scene, (255, 213, 105), (house.centerx + 2, house.bottom - 8), 1)
		for index, x in enumerate(range(8, width, 24)):
			y = height - 8 - (index % 2) * 5
			pygame.draw.line(scene, (110, 178, 115), (x, y + 3), (x, y - 3), 1)
			pygame.draw.circle(scene, ((247, 158, 168), (250, 245, 220), (251, 210, 105))[index % 3], (x, y - 3), 2)

	def scene(self, rect, species, now, sleeping=False, accessory="none", message="", stage=None, activity=None, dirt=0,
			  park=False):
		scene = pygame.Surface(rect.size)
		width, height = rect.size
		if park:
			self.park_background(scene)
		else:
			scene.fill(SKY)
			pygame.draw.circle(scene, (255, 224, 131), (width - 24, 21), 11)
			pygame.draw.ellipse(scene, (246, 255, 253), (12, 14, 37, 12))
			pygame.draw.ellipse(scene, (246, 255, 253), (21, 8, 20, 18))
			pygame.draw.ellipse(scene, (209, 239, 218), (-width // 3, height - 46, width, 70))
			pygame.draw.ellipse(scene, GRASS, (width // 4, height - 42, width, 68))
			pygame.draw.ellipse(scene, (158, 207, 165), (width // 2 - 46, height - 20, 92, 12))
		factor = {"宝宝": 0.90, "小伙伴": 0.95, "大伙伴": 1.0}.get(stage, 1.0)
		if park:
			if width >= height:
				pet_size = round(min(width * 0.38, height * 0.77) * factor)
				friend_size = round(min(width * 0.23, pet_size * 0.62))
				friend_centers = ((round(width * 0.18), height - friend_size // 2 - 6),
								  (round(width * 0.82), height - friend_size // 2 - 6))
			else:
				pet_size = round(min(width * 0.58, height * 0.5) * factor)
				friend_size = round(min(width * 0.30, height * 0.24))
				friend_centers = ((round(width * 0.22), round(height * 0.37)),
								  (round(width * 0.78), round(height * 0.37)))
			friends = [SPECIES_BY_KEY[key] for key in ("capybara", "pikachu", "dinosaur") if key != species.key]
			for index, (friend, center) in enumerate(zip(friends, friend_centers)):
				friend_area = pygame.Rect(0, 0, friend_size, friend_size)
				friend_area.center = (center[0] + round(math.sin(now * 0.9 + index) * 2), center[1])
				pygame.draw.ellipse(scene, (144, 196, 146), (friend_area.centerx - friend_size // 3,
																 friend_area.bottom - 8, friend_size * 2 // 3, 7))
				self.art.draw(scene, friend, friend_area, now + index * 0.5)
		else:
			pet_size = round(min(width - 8, height - 2) * factor)
		pet_area = pygame.Rect(0, 0, pet_size, pet_size)
		pet_area.centerx = width // 2
		pet_area.bottom = height - 3
		if park:
			pygame.draw.ellipse(scene, (144, 196, 146), (pet_area.centerx - pet_size // 3,
															 pet_area.bottom - 8, pet_size * 2 // 3, 7))
		self.art.draw(scene, species, pet_area, now, sleeping, accessory, activity=activity, dirt=dirt)
		if message:
			font, label = self.fit(message, width - 18)
			image = font.render(label, True, INK)
			background = image.get_rect(topleft=(7, 5)).inflate(8, 5)
			pygame.draw.rect(scene, PAPER, background, border_radius=5)
			scene.blit(image, (7, 5))
		if sleeping:
			image = self.small_font.render("Z z", True, JADE)
			scene.blit(image, (width - image.get_width() - 10, 6))
		self.screen.blit(scene, rect.topleft)

	def selection_items(self, game):
		if game.view == "owners":
			legacy_number = 0
			items = []
			for owner in game.world.owners:
				name = owner["name"]
				if name not in OWNER_NAMES:
					legacy_number += 1
					name = "旧存档%d" % legacy_number
				items.append((name, "%d只" % len(owner["pets"])))
			if game.owner_names():
				items.append(("新增主人", "+"))
			return "选择主人", items
		if game.view == "owner_name":
			return "主人叫什么", [(name, "") for name in game.owner_names()]
		if game.view == "owner_migrate":
			return "为旧存档选择主人", [(name, "") for name in game.owner_names()]
		if game.view == "pets":
			pets = game.world.owner(game.owner_id)["pets"]
			items = [(pet["name"], growth_stage(pet)) for pet in pets]
			if len(pets) > 1:
				return "旧档：选择保留一只", items
			items.append(("删除宠物", "需确认") if pets else ("领养伙伴", "+"))
			return "我的伙伴", items
		if game.view == "confirm_release":
			return "删除后无法恢复", [("取消", ""), ("确认删除", "")]
		if game.view == "confirm_keep":
			return "其他伙伴无法恢复", [("取消", ""), ("确认保留", "")]
		if game.view == "confirm_action":
			name, duration, cooldown = ACTIVITIES[game.pending_action]
			if game.pending_action == "skill":
				pet = game.world.pet(game.owner_id, game.pet_id)
				name = SKILLS[pet["species"]][game.pending_skill][0]
			return "%s %s" % (name, duration_text(duration)), [
				("取消", ""), ("开始", "冷却%s" % duration_text(cooldown))]
		if game.view == "confirm_stop":
			return "中止后没有奖励", [("继续行动", ""), ("确认结束", "")]
		if game.view == "skills":
			pet = game.world.visible_pet(game.owner_id, game.pet_id)
			items = [(name, "已解锁" if growth_level(pet) > index else "Lv%d解锁" % (index + 1))
					 for index, (name, _) in enumerate(SKILLS[pet["species"]])]
			return "技能 · Lv%d" % growth_level(pet), items
		if game.view == "tasks":
			pet = game.world.visible_pet(game.owner_id, game.pet_id)
			today = local_day(pet["updated_at"])
			items = [(name, "已完成" if pet["task_days"].get(key) == today
					  else ("%s%d星" % ("%d食 " % food if food else "", stars)))
					 for key, name, food, stars, _ in DAILY_TASKS]
			return "今日任务 · 自动领奖", items
		if game.view == "adopt":
			return "选择新伙伴", [(species.name, "") for species in SPECIES]
		if game.view == "rename":
			return "给伙伴取名", [(name, "") for name in game.pet_names()]
		pet = game.world.pet(game.owner_id, game.pet_id)
		items = [(name, "已拥有" if key in pet["accessories"] else "%d星" % price)
				 for key, name, price in ACCESSORIES]
		return "装扮 · %d星" % pet["stars"], items

	def selection_preview(self, game):
		if game.view == "adopt":
			return SPECIES[game.index], False, "none", SPECIES[game.index].description
		if game.view == "owners" and game.index < len(game.world.owners):
			pets = game.world.owners[game.index]["pets"]
			if pets:
				pet = pets[0]
				return SPECIES_BY_KEY[pet["species"]], pet["sleeping"], pet["equipped"], ""
		if game.view == "pets":
			pets = game.world.owner(game.owner_id)["pets"]
			if game.index < len(pets):
				pet = pets[game.index]
				return SPECIES_BY_KEY[pet["species"]], pet["sleeping"], pet["equipped"], ""
		if game.view == "owner_migrate":
			pets = game.world.owner(game.owner_id)["pets"]
			if pets:
				pet = pets[0]
				return SPECIES_BY_KEY[pet["species"]], pet["sleeping"], pet["equipped"], "认领旧伙伴"
			return SPECIES[0], False, "none", "认领旧存档"
		if game.view in ("confirm_release", "confirm_keep"):
			pet = game.world.visible_pet(game.owner_id, game.pet_id)
			message = ("删除" if game.view == "confirm_release" else "只保留") + pet["name"] + "？"
			return SPECIES_BY_KEY[pet["species"]], pet["sleeping"], pet["equipped"], message
		if game.view in ("rename", "accessory", "confirm_action", "confirm_stop", "skills", "tasks"):
			pet = game.world.visible_pet(game.owner_id, game.pet_id)
			accessory = ACCESSORIES[game.index][0] if game.view == "accessory" else pet["equipped"]
			message = ""
			if game.view == "confirm_action":
				message = "开始%s？" % ACTIVITIES[game.pending_action][0]
			elif game.view == "confirm_stop":
				message = "要结束当前行动吗？"
			return SPECIES_BY_KEY[pet["species"]], pet["sleeping"], accessory, message
		return SPECIES[0], False, "none", ""

	def draw_selection(self, game, now):
		species, sleeping, accessory, message = self.selection_preview(game)
		self.scene(self.selection_scene, species, now, sleeping, accessory, game.notice or message,
				   park=game.view == "owners")
		title, items = self.selection_items(game)
		self.text(title, self.small_font, JADE, self.list_area.topleft)
		start = max(0, min(game.index - 1, len(items) - 3))
		row_top = self.list_area.y + 17
		row_height = (self.list_area.height - 17 - 8) // 3
		for visible, index in enumerate(range(start, min(start + 3, len(items)))):
			label, detail = items[index]
			rect = pygame.Rect(self.list_area.x, row_top + visible * (row_height + 4),
							   self.list_area.width, row_height)
			selected = index == game.index
			pygame.draw.rect(self.screen, (223, 244, 228) if selected else PAPER, rect, border_radius=5)
			pygame.draw.rect(self.screen, JADE if selected else (190, 219, 204), rect,
							 2 if selected else 1, border_radius=5)
			pygame.draw.circle(self.screen, (234, 155, 110) if selected else (176, 206, 189),
							   (rect.x + 12, rect.centery), 4)
			detail_image = self.small_font.render(detail, True, (95, 116, 105))
			available = rect.width - 32 - detail_image.get_width()
			font, shown = self.fit(label, available)
			image = font.render(shown, True, INK)
			self.screen.blit(image, image.get_rect(midleft=(rect.x + 22, rect.centery)))
			self.screen.blit(detail_image, detail_image.get_rect(midright=(rect.right - 8, rect.centery)))
			self.click_targets.append((rect, "CHOOSE_%d" % index))
		self.footer(("上一项", "下一项", "确定"), (len(items) > 1, len(items) > 1, True))

	def stat_bars(self, pet, message=""):
		stats = pet["stats"]
		values = (("饱腹", stats["hunger"], (225, 148, 77)),
				  ("开心", stats["happiness"], (220, 115, 128)),
				  ("清洁", stats["hygiene"], (100, 166, 199)),
				  ("精力", stats["energy"], (117, 170, 102)),
				  ("健康", stats["health"], (206, 102, 98)),
				  ("亲密", pet["friendship"], (166, 119, 178)))
		for index, (label, value, color) in enumerate(values):
			if self.portrait:
				cell_width = self.stat_area.width // 3
				x = self.stat_area.x + (index % 3) * cell_width
				y = self.stat_area.y + (index // 3) * 15
				bar_width = cell_width - 32
			else:
				x = self.stat_area.x
				y = self.stat_area.y + index * 14
				bar_width = self.stat_area.width - 34
			self.text(label, self.small_font, INK, (x, y))
			bar = pygame.Rect(x + 27, y + 4, bar_width, 7)
			pygame.draw.rect(self.screen, (211, 227, 216), bar, border_radius=3)
			fill = bar.copy()
			fill.width = max(0, min(bar.width, round(bar.width * value / 100)))
			if fill.width:
				pygame.draw.rect(self.screen, color, fill, border_radius=3)
		target = 40 if pet["experience"] < 40 else 120 if pet["experience"] < 120 else None
		growth = "成长 %d/%d" % (pet["experience"], target) if target else "成长 %d · 满级" % pet["experience"]
		growth_y = self.stat_area.y + (30 if self.portrait else 84)
		growth_font = self.small_font
		if self.portrait and message:
			growth_font, growth = self.fit(growth, self.stat_area.width // 2, (self.small_font,))
		self.text(growth, growth_font, JADE, (self.stat_area.x, growth_y))
		if self.portrait and message:
			available = self.stat_area.width - growth_font.size(growth)[0] - 8
			font, label = self.fit(message, available, (self.small_font,))
			self.text(label, font, INK, (self.stat_area.right - font.size(label)[0], growth_y))

	def action_icon(self, key, center, background):
		x, y = center
		if key == "feed":
			pygame.draw.ellipse(self.screen, (230, 160, 85), (x - 11, y, 22, 10))
			pygame.draw.ellipse(self.screen, (249, 218, 149), (x - 9, y - 3, 18, 8))
		elif key == "play":
			pygame.draw.polygon(self.screen, (230, 157, 71), star_points((x, y + 2), 11))
		elif key == "wash":
			pygame.draw.polygon(self.screen, (109, 182, 209), ((x, y - 9), (x - 8, y + 3), (x + 8, y + 3)))
			pygame.draw.circle(self.screen, (109, 182, 209), (x, y + 3), 8)
		elif key == "sleep":
			pygame.draw.circle(self.screen, (235, 185, 71), (x, y + 1), 10)
			pygame.draw.circle(self.screen, background, (x + 5, y - 3), 8)
		elif key == "pat":
			pygame.draw.circle(self.screen, (226, 122, 132), (x - 5, y - 2), 6)
			pygame.draw.circle(self.screen, (226, 122, 132), (x + 5, y - 2), 6)
			pygame.draw.polygon(self.screen, (226, 122, 132), ((x - 11, y), (x + 11, y), (x, y + 11)))
		elif key == "medicine":
			pygame.draw.rect(self.screen, (226, 125, 118), (x - 3, y - 9, 6, 20), border_radius=2)
			pygame.draw.rect(self.screen, (226, 125, 118), (x - 10, y - 2, 20, 6), border_radius=2)
		elif key == "accessory":
			for dx, dy in ((-5, 0), (5, 0), (0, -5), (0, 5)):
				pygame.draw.circle(self.screen, (235, 145, 161), (x + dx, y + dy), 5)
			pygame.draw.circle(self.screen, (249, 202, 86), (x, y), 4)
		elif key == "rename":
			pygame.draw.line(self.screen, (99, 153, 183), (x - 7, y + 8), (x + 6, y - 7), 6)
			pygame.draw.line(self.screen, (242, 179, 130), (x - 8, y + 9), (x - 5, y + 6), 4)
		elif key == "explore":
			pygame.draw.circle(self.screen, (239, 179, 74), (x + 6, y - 6), 5)
			pygame.draw.polygon(self.screen, (100, 177, 130), ((x - 11, y + 8), (x - 3, y - 5), (x + 7, y + 8)))
		elif key == "skill":
			pygame.draw.polygon(self.screen, (235, 174, 64), star_points((x, y), 11))
		elif key == "tasks":
			pygame.draw.rect(self.screen, (102, 163, 183), (x - 9, y - 10, 18, 21), 2, border_radius=2)
			for offset in (-4, 2, 8):
				pygame.draw.line(self.screen, (102, 163, 183), (x - 5, y + offset), (x + 5, y + offset), 2)
		elif key == "stop":
			pygame.draw.rect(self.screen, (198, 112, 101), (x - 8, y - 8, 16, 16), border_radius=2)
		else:
			pygame.draw.circle(self.screen, (121, 177, 152), (x - 5, y - 3), 6)
			pygame.draw.circle(self.screen, (213, 147, 132), (x + 6, y - 3), 6)
			pygame.draw.ellipse(self.screen, (121, 177, 152), (x - 13, y + 3, 15, 10))
			pygame.draw.ellipse(self.screen, (213, 147, 132), (x, y + 3, 15, 10))

	def draw_home(self, game, now):
		pet = game.world.visible_pet(game.owner_id, game.pet_id)
		species = SPECIES_BY_KEY[pet["species"]]
		stage = growth_stage(pet)
		if self.portrait:
			name_position = (10, 39)
			stars_position = (self.width - 12, 47)
		else:
			name_position = (self.stat_area.x, 40)
			stars_position = (self.width - 10, 48)
		stars = self.small_font.render("食%d ★%d" % (pet["food"], pet["stars"]), True, (166, 111, 44))
		name_width = stars_position[0] - name_position[0] - stars.get_width() - 8
		font, name = self.fit("%s Lv%d · %s" % (pet["name"], growth_level(pet), stage), name_width)
		self.text(name, font, INK, name_position)
		self.screen.blit(stars, stars.get_rect(midright=stars_position))
		activity = pet["activity"]
		selected = HOME_ACTIONS[game.index][0]
		remaining = pet["cooldowns"].get(selected, 0) - pet["updated_at"]
		if activity:
			label = ACTIVITIES[activity["kind"]][0]
			if activity["kind"] == "skill":
				label = SKILLS[pet["species"]][activity["skill"]][0]
			elif activity["kind"] == "play":
				label = "猜中·玩耍" if activity.get("won") else "差一点·玩耍"
			message = "%s中 %s" % (label, duration_text(activity["ends_at"] - pet["updated_at"]))
		elif game.notice:
			message = game.notice
		elif remaining > 0:
			message = "%s冷却 %s" % (ACTIVITIES[selected][0], duration_text(remaining))
		elif pet["dirt"]:
			message = "身上有泥点啦"
		elif pet["stats"]["hunger"] < 35:
			message = "肚子有点饿啦"
		elif pet["stats"]["hygiene"] < 35:
			message = "想洗个香香澡"
		elif pet["stats"]["happiness"] < 35:
			message = "陪我一起玩吧"
		else:
			message = "今天也要开心呀"
		self.scene(self.home_scene, species, now, pet["sleeping"], pet["equipped"], "" if self.portrait else message, stage,
				   activity=activity, dirt=pet["dirt"])
		self.stat_bars(pet, message if self.portrait else "")
		gap = 4
		width = (self.action_area.width - 2 * gap) // 3
		for position, offset in enumerate((-1, 0, 1)):
			index = (game.index + offset) % len(HOME_ACTIONS)
			key, label = HOME_ACTIONS[index]
			rect = pygame.Rect(self.action_area.x + position * (width + gap), self.action_area.y,
							   width, self.action_area.height)
			selected = offset == 0
			background = (255, 244, 210) if selected else PAPER
			pygame.draw.rect(self.screen, background, rect, border_radius=5)
			pygame.draw.rect(self.screen, (222, 164, 83) if selected else (192, 220, 205), rect,
							 2 if selected else 1, border_radius=5)
			icon_y = rect.y + (13 if rect.height > 43 else 10)
			self.action_icon(key, (rect.centerx, icon_y), background)
			self.centered(label, self.small_font, INK, (rect.centerx, rect.bottom - 9))
			self.click_targets.append((rect, "CHOOSE_%d" % index))
		self.footer(("上一项", "下一项", "执行"))

	def gift(self, rect, selected, opened, color):
		if selected:
			pygame.draw.rect(self.screen, JADE, rect.inflate(8, 8), 2, border_radius=6)
		body = rect.inflate(-7, -13)
		body.y += 7
		pygame.draw.rect(self.screen, color, body, border_radius=4)
		pygame.draw.rect(self.screen, (255, 236, 201), (body.centerx - 3, body.y, 6, body.height))
		pygame.draw.rect(self.screen, color, (body.x - 3, body.y - 5, body.width + 6, 8), border_radius=3)
		pygame.draw.ellipse(self.screen, color, (body.centerx - 13, body.y - 14, 13, 10), 3)
		pygame.draw.ellipse(self.screen, color, (body.centerx, body.y - 14, 13, 10), 3)
		if opened:
			pygame.draw.polygon(self.screen, (255, 227, 111), star_points(body.center, 13))

	def draw_game(self, game):
		self.centered("猜猜星星藏在哪？", self.name_font, INK, (self.width // 2, 60))
		size = 55 if self.portrait else 48
		gap = 16 if self.portrait else 22
		top = 105 if self.portrait else 87
		left = (self.width - size * 3 - gap * 2) // 2
		for index, color in enumerate(((226, 126, 117), (106, 184, 159), (232, 179, 83))):
			rect = pygame.Rect(left + index * (size + gap), top, size, size)
			self.gift(rect, game.index == index if game.view == "game" else game.guess == index,
					  game.view == "result" and game.target == index, color)
			if game.view == "game":
				self.click_targets.append((rect.inflate(8, 8), "CHOOSE_%d" % index))
		if game.view == "result":
			self.centered("找到啦！ +3星" if game.won else "再试试！ +1星", self.name_font, JADE,
						  (self.width // 2, 201 if self.portrait else 162))
			self.footer(("再玩", "无功能", "返回"), (True, False, True))
		else:
			self.centered(game.notice or "选一个礼物", self.small_font, CORAL if game.notice else (95, 116, 105),
						  (self.width // 2, 196 if self.portrait else 160))
			self.footer(("左选", "右选", "打开"))

	def draw_error(self):
		self.screen.fill((237, 247, 241))
		self.header(None)
		self.centered("宠物存档无法读取", self.name_font, CORAL, (self.width // 2, self.height // 2 - 15))
		self.centered("原存档未修改，请检查文件", self.small_font, INK, (self.width // 2, self.height // 2 + 10))
		self.footer(("无功能", "无功能", "返回"), (False, False, True))

	def draw(self, game, now=None):
		now = time.monotonic() if now is None else now
		self.click_targets = []
		self.screen.fill((237, 247, 241))
		self.header(game)
		if game.view == "home":
			self.draw_home(game, now)
		elif game.view in ("game", "result"):
			self.draw_game(game)
		else:
			self.draw_selection(game, now)


def event_action(event, display):
	if event.type == pygame.QUIT:
		return "EXIT"
	if event.type == pygame.KEYDOWN:
		if event.key in (pygame.K_ESCAPE, pygame.K_q):
			return "EXIT"
		if event.key == pygame.K_BACKSPACE:
			return "BACK"
		return {pygame.K_1: "K1", pygame.K_2: "K2", pygame.K_3: "K3",
				pygame.K_KP1: "K1", pygame.K_KP2: "K2", pygame.K_KP3: "K3"}.get(event.key)
	position = spi_lcd.mouse_position(event)
	if position is None:
		return None
	for action, rect in zip(("K1", "K2", "K3"), display.buttons):
		if rect.collidepoint(position):
			return action
	for rect, action in display.click_targets:
		if rect.collidepoint(position):
			return action
	return None


def main():
	if spi_lcd.is_simulate():
		spi_lcd.WINDOW_SCALE = 2
		if "--landscape" in sys.argv:
			os.environ["POKEMON_PORTRAIT"] = "0"
		elif "--portrait" in sys.argv:
			os.environ["POKEMON_PORTRAIT"] = "1"
		else:
			os.environ.setdefault("POKEMON_PORTRAIT", "1")
	screen = spi_lcd.init()
	buttons = None
	try:
		if spi_lcd.is_simulate():
			pygame.display.set_caption("宠物乐园")
		else:
			try:
				buttons = GPIOButtons(importlib.import_module("RPi.GPIO"))
			except Exception as error:
				raise RuntimeError("GPIO 初始化失败，请检查 RPi.GPIO 和按键连接。") from error
		display = PetDisplay(screen)
		try:
			game = PetGame(PetWorld())
		except SaveError as error:
			print(error)
			game = None
		hold = spi_lcd.SimulatedHold("K3", "BACK", QUIT_HOLD_SECONDS)
		clock = pygame.time.Clock()
		running = True
		print("宠物乐园已启动：K1/K2 选择，K3 确定，长按 K3 返回。")
		while running:
			clock.tick(25)
			if buttons is None:
				actions = [hold.process_event(event, event_action(event, display)) for event in pygame.event.get()]
				actions.append(hold.poll())
			else:
				actions = ["BACK" if action == "QUIT" else action for action in buttons.poll()]
			for action in actions:
				if action == "EXIT" or (game is None and action in ("BACK", "K3")):
					running = False
					break
				if game is not None and action:
					previous = game.view
					if game.handle_action(action) == "EXIT":
						running = False
						break
					if game.view != previous:
						break
			if not running:
				break
			if game is None:
				display.draw_error()
			else:
				game.tick()
				display.draw(game)
			if not spi_lcd.present(poll_events=False):
				break
	finally:
		if buttons is not None:
			buttons.cleanup()
		pygame.quit()


if __name__ == "__main__":
	main()
