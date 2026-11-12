# -*- coding: utf-8 -*-
"""爬取 52poke 百科第四世代宝可梦资料（白金版本）。

数据来源：
    - 列表页: 宝可梦列表（按全国图鉴编号）
    - 详情页: 每只宝可梦的图像、属性、获得方式
    - 招式页: {名字}/第四世代招式表 子页面
    - 属性相克页: 全属性攻击/防御倍率表(修正为第四世代规则)

输出:
    pokedex_data/pokemon_platinum.json
    pokedex_data/type_chart.json   (属性相克: 攻击属性 -> {防御属性: 倍率})
    pokedex_data/images/{编号}.png
    pokedex_data/cache/*.html   (HTML 缓存, 支持断点续爬)

用法:
    python crawl_pokemon_platinum.py            # 全量 #001-#493(断点续爬, 已完成自动跳过)
    python crawl_pokemon_platinum.py --limit 3  # 只抓前 3 只(测试)
    python crawl_pokemon_platinum.py --no-cache # 忽略缓存强制重新抓
    python crawl_pokemon_platinum.py --skip-images  # 不下载图片
"""
import argparse
import json
import os
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

BASE = "https://wiki.52poke.com"
LIST_URL = BASE + "/zh-hans/%E5%AE%9D%E5%8F%AF%E6%A2%A6%E5%88%97%E8%A1%A8%EF%BC%88%E6%8C%89%E5%85%A8%E5%9B%BD%E5%9B%BE%E9%89%B4%E7%BC%96%E5%8F%B7%EF%BC%89"
TYPE_CHART_URL = BASE + "/zh-hans/%E5%B1%9E%E6%80%A7%E7%9B%B8%E5%85%8B"  # 属性相克
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}

DATA_DIR = "pokedex_data"
IMG_DIR = os.path.join(DATA_DIR, "images")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
OUTPUT_JSON = os.path.join(DATA_DIR, "pokemon_platinum.json")
TYPE_CHART_JSON = os.path.join(DATA_DIR, "type_chart.json")

DELAY = 0.3  # 每次请求间隔(秒), 礼貌爬取
RETRIES = 3

session = requests.Session()
session.headers.update(HEADERS)


# 第四世代属性修正: 52poke 列表页显示的是当前世代属性,
# 妖精属性是第六世代才引入的, 下面这 19 只是"原妖精系"宝可梦,
# 按全国图鉴编号给出它们在白金版中的真实属性
GEN4_TYPE_FIX = {
    35: ["一般"], 36: ["一般"],                     # 皮皮/皮可西
    39: ["一般"], 40: ["一般"],                      # 胖丁/胖可丁
    122: ["超能力"],                                # 魔墙人偶
    173: ["一般"], 174: ["一般"],                    # 皮宝宝/宝宝丁
    175: ["一般"], 176: ["一般", "飞行"],             # 波克比/波克基古
    183: ["水"], 184: ["水"],                        # 玛力露/玛力露丽
    209: ["一般"], 210: ["一般"],                     # 布卢/布卢皇
    298: ["一般"],                                   # 露力丽
    280: ["超能力"], 281: ["超能力"], 282: ["超能力"],  # 拉鲁拉丝/奇鲁莉安/沙奈朵
    303: ["钢"],                                    # 大嘴娃
    439: ["超能力"],                                # 魔尼尼
    468: ["一般", "飞行"],                           # 波克基斯
}

# 属性相克表: 全部 18 个属性(含第六世代的妖精)
ALL_TYPES = [
    "一般", "格斗", "飞行", "毒", "地面", "岩石", "虫", "幽灵", "钢",
    "火", "水", "草", "电", "超能力", "冰", "龙", "恶", "妖精",
]

# 第四世代相克修正: 百科页面展示的是当前世代规则, 与白金版不同之处:
#   1. 钢属性招式打 火/水/电: 第四世代为 ½, 第六世代起为 1
#   2. 钢属性防御 幽灵/恶: 第四世代为 ½, 第六世代起为 1
GEN4_CHART_FIX = {
    "钢": {"火": 0.5, "水": 0.5, "电": 0.5},
    "幽灵": {"钢": 0.5},
    "恶": {"钢": 0.5},
}


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------
class NotFoundError(RuntimeError):
    """页面不存在(404), 不重试。"""


def fetch(url, cache_name=None, use_cache=True):
    """GET 页面, 优先使用缓存。返回 HTML 文本。"""
    cache_path = os.path.join(CACHE_DIR, cache_name) if cache_name else None
    if cache_path and use_cache and os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            return f.read()

    last_err = None
    for i in range(RETRIES):
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 404:
                raise NotFoundError(f"页面不存在(404): {url}")
            r.raise_for_status()
            r.encoding = "utf-8"
            if cache_path:
                with open(cache_path, "w", encoding="utf-8") as f:
                    f.write(r.text)
            time.sleep(DELAY)
            return r.text
        except NotFoundError:
            raise                 # 404 不重试
        except Exception as e:
            last_err = e
            wait = 2 * (i + 1)
            print(f"    请求失败({e}), {wait}s 后重试 {i + 1}/{RETRIES}")
            time.sleep(wait)
    raise RuntimeError(f"多次重试仍失败: {url} ({last_err})")


def clean(text):
    """清理单元格文本: 去掉 [详] 标记和多余空白。"""
    text = text.replace("[详]", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def cell_text(td):
    return clean(td.get_text(" ", strip=True))


# ---------------------------------------------------------------------------
# 第一步: 列表页 -> 基本信息清单
# ---------------------------------------------------------------------------
def crawl_list():
    print("== 抓取列表页, 全国图鉴 #001-#493 ==")
    html = fetch(LIST_URL, cache_name="list.html")
    soup = BeautifulSoup(html, "html.parser")

    # 扫描所有世代表格, 收集 #001-#493, 按编号去重(形态/重复行只留第一条)
    pokemons = []
    seen = set()
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            tds = row.find_all("td")
            if len(tds) < 8:
                continue
            id_text = cell_text(tds[0])
            m = re.match(r"#(\d{3,})", id_text)
            if not m:
                continue
            dex_id = int(m.group(1))
            if not (1 <= dex_id <= 493) or dex_id in seen:
                continue

            # 列布局: 编号 | 图像链接 | (空) | 中文 | 日文 | 英文 | 属性1 | 属性2
            name_zh = cell_text(tds[3]).rstrip(" *").strip()
            name_ja = cell_text(tds[4]).rstrip(" *").strip()
            name_en = cell_text(tds[5]).rstrip(" *").strip()
            if not name_zh:
                continue

            # 属性: 过滤模板残留 '[[{{{6}}}...' 和空单元格
            types = []
            for td in tds[6:8]:
                t = cell_text(td)
                if t and "{{{" not in t and "[[" not in t and t not in types:
                    types.append(t)

            # 详情页链接(在图像列的 <a> 里)
            detail_path = None
            a = tds[1].find("a", href=True)
            if a:
                detail_path = a["href"]

            # 属性修正为第四世代(白金版)实际属性
            if dex_id in GEN4_TYPE_FIX:
                types = list(GEN4_TYPE_FIX[dex_id])
            elif "妖精" in types:
                # 兜底: 发现未收录的妖精系老宝可梦, 提醒补全 GEN4_TYPE_FIX
                print(f"    警告: #{dex_id:03d} {name_zh} 含妖精属性但不在修正表中! {types}")

            seen.add(dex_id)
            pokemons.append(
                {
                    "id": dex_id,
                    "name_zh": name_zh,
                    "name_ja": name_ja,
                    "name_en": name_en,
                    "types": types,
                    "detail_path": detail_path,
                }
            )

    print(f"   共找到 {len(pokemons)} 只宝可梦 (应为 493)")
    return pokemons


# ---------------------------------------------------------------------------
# 第二步: 详情页 -> 图像 + 白金版获得方式
# ---------------------------------------------------------------------------
def find_main_image(soup, dex_id):
    """在 infobox 中寻找主图像, 返回原图 URL。

    主图文件名固定为 "3 位编号 + 英文名", 如 002Ivysaur.png / 387Turtwig.png。
    先精确匹配(编号+纯英文名), 再放宽(允许 形态/后缀), 避免误抓
    以相同数字开头的其他文件(如 #1 误抓 1026Browt.png)。
    """
    exact = re.compile(r"/thumb/[0-9a-f]/[0-9a-f]{2}/%03d[A-Za-z]+\.png/" % dex_id, re.I)
    loose = re.compile(r"/thumb/[0-9a-f]/[0-9a-f]{2}/%03d[A-Za-z][^/]*?\.png/" % dex_id, re.I)
    for pat in (exact, loose):
        for img in soup.find_all("img"):
            src = img.get("src", "")
            m = pat.search(src)
            if m:
                # .../thumb/5/5c/387Turtwig.png/300px-...  ->  .../5/5c/387Turtwig.png
                return "https:" + re.sub(r"/thumb/([^/]+/[^/]+/[^/]+\.png)/[^/]+$", r"/\1", src)
    return None


def parse_platinum_locations(soup):
    """解析'获得方式'主表, 返回白金版相关行 [{location, method, notes}]。"""
    # 定位 h3 '获得方式'
    h3 = None
    for h in soup.find_all("h3"):
        if "获得方式" in h.get_text(" ", strip=True):
            h3 = h
            break
    if h3 is None:
        return []

    # 在 h3 与下一个 h3/h4 之间找主表(表头含 '游戏版本')
    node = h3
    table = None
    while node is not None:
        node = node.find_next()
        if node is None:
            break
        nm = getattr(node, "name", None)
        if nm in ("h2", "h3", "h4"):
            break
        if nm == "table" and "游戏版本" in node.get_text(" ", strip=True):
            table = node
            break
    if table is None:
        return []

    results = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue
        # 版本列可能在 td[0] 或 td[1](宝可梦列 rowspan 时), 逐个检查
        for offset in (0, 1):
            if offset >= len(tds) - 2:
                continue
            version = cell_text(tds[offset])
            if "白金" in version and len(version) <= 20:
                location = cell_text(tds[offset + 1])
                method = cell_text(tds[offset + 2]) if offset + 2 < len(tds) else ""
                notes = cell_text(tds[offset + 3]) if offset + 3 < len(tds) else ""
                results.append(
                    {
                        "location": location,
                        "method": method,
                        "notes": notes,
                    }
                )
                break
    return results


def crawl_detail(pokemon):
    dex_id = pokemon["id"]
    if not pokemon.get("detail_path"):
        print(f"    #{dex_id:03d} 无详情页链接, 跳过详情抓取")
        return None, []

    url = BASE + pokemon["detail_path"]
    html = fetch(url, cache_name=f"{dex_id:03d}_main.html")
    soup = BeautifulSoup(html, "html.parser")

    img_url = find_main_image(soup, dex_id)
    locations = parse_platinum_locations(soup)
    return img_url, locations


# ---------------------------------------------------------------------------
# 第三步: 第四世代招式表子页 -> 可学会招式
# ---------------------------------------------------------------------------
def parse_gen4_moves(soup):
    """解析'可学会的招式'表。

    两种表头布局:
      普通:  等級 | (空图标列) | 招式 | 屬性 | 分類 | 威力 | 命中 | ＰＰ | ...
      分版本: D P | Pt HG SS | 招式 | 屬性 | 分類 | 威力 | 命中 | ＰＰ | ...
    分版本布局中等级按 DP / Pt(HGSS) 分列, 白金版取 Pt 列。
    通过表头行中 '招式' 列的索引来对齐数据列, 两种布局通用。
    """
    h4 = None
    for h in soup.find_all("h4"):
        if "可学会的招式" in h.get_text(" ", strip=True):
            h4 = h
            break
    if h4 is None:
        return None

    # 在 h4 与下一个标题之间找升级招式主表(含 属性/屬性 + 威力 + 招式)
    node = h4
    table = None
    while node is not None:
        node = node.find_next()
        if node is None:
            break
        nm = getattr(node, "name", None)
        if nm in ("h2", "h3", "h4"):
            break
        if nm == "table":
            txt = node.get_text(" ", strip=True)
            if ("屬性" in txt or "属性" in txt) and "威力" in txt and "招式" in txt:
                table = node
                break
    if table is None:
        return None

    # 从表头行确定列索引
    move_idx = None       # '招式' 列
    level_idx = None      # '等級' 列(普通布局)
    pt_level_idx = None   # 'Pt' 列(分版本布局)
    for tr in table.find_all("tr"):
        ths = tr.find_all("th")
        if not ths:
            continue
        texts = [cell_text(th) for th in ths]
        joined = " ".join(texts)
        if ("屬性" not in joined and "属性" not in joined) or "威力" not in joined:
            continue  # 跳过世代切换 tab 行
        for i, t in enumerate(texts):
            if "招式" in t and "学习器" not in t and "教授" not in t:
                move_idx = i
            if "等級" in t or "等级" in t:
                level_idx = i
            if re.search(r"\bPt\b", t):
                pt_level_idx = i
        break

    if move_idx is None:
        return None
    # 白金版等级列: 分版本表优先 Pt 列, 否则用普通等級列
    use_level_idx = pt_level_idx if pt_level_idx is not None else level_idx
    if use_level_idx is None:
        use_level_idx = 0

    moves = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < move_idx + 6:
            continue
        cells = [cell_text(td) for td in tds]
        name = cells[move_idx]
        if not name:
            continue
        raw_level = cells[use_level_idx] if use_level_idx < len(cells) else ""
        compact = re.sub(r"\s+", "", raw_level)
        if "Pt" in compact:
            # 等级格内嵌版本标签: "18 Pt HG SS" -> 白金版适用, 剔除标签取数字
            level = clean(re.sub(r"(D\s*P|Pt|HG\s*SS)", " ", raw_level)) or "—"
        elif "HGSS" in compact or "DP" in compact:
            # "18 D P" / "20 HG SS" 为 DP 或 HGSS 专属等级, 白金版不适用
            continue
        else:
            level = raw_level
        moves.append(
            {
                "level": level,
                "name": name,
                "type": cells[move_idx + 1],
                "category": cells[move_idx + 2],
                "power": cells[move_idx + 3],
                "accuracy": cells[move_idx + 4],
                "pp": cells[move_idx + 5],
            }
        )
    return moves


def crawl_moves(pokemon):
    dex_id = pokemon["id"]
    if not pokemon.get("detail_path"):
        return None
    # 子页 URL: /wiki/草苗龟/第四世代招式表
    moves_path = pokemon["detail_path"] + "/第四世代招式表"
    url = BASE + moves_path
    html = fetch(url, cache_name=f"{dex_id:03d}_moves4.html")
    soup = BeautifulSoup(html, "html.parser")
    return parse_gen4_moves(soup)


# ---------------------------------------------------------------------------
# 图片下载
# ---------------------------------------------------------------------------
def download_image(pokemon, img_url):
    """图片按宝可梦中文名存储, 如 images/草苗龟.png"""
    dex_id = pokemon["id"]
    if not img_url:
        print(f"    #{dex_id:03d} 未找到主图 URL")
        return None
    img_name = pokemon["name_zh"] + ".png"
    out_path = os.path.join(IMG_DIR, img_name)
    if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
        return out_path

    last_err = None
    img_headers = dict(HEADERS)
    img_headers["Referer"] = BASE + "/"  # s1.52poke.com 有防盗链, 需带 Referer
    for i in range(RETRIES):
        try:
            r = session.get(img_url, timeout=60, headers=img_headers)
            r.raise_for_status()
            with open(out_path, "wb") as f:
                f.write(r.content)
            time.sleep(DELAY)
            return out_path
        except Exception as e:
            last_err = e
            time.sleep(2 * (i + 1))
    print(f"    #{dex_id:03d} 图片下载失败: {last_err}")
    return None


# ---------------------------------------------------------------------------
# 第零步: 属性相克页 -> 攻击/防御倍率表(修正为第四世代)
# ---------------------------------------------------------------------------
def parse_mult(text):
    """解析倍率单元格: '2×' -> 2.0, '1 ⁄ 2 ×' -> 0.5, '0×' -> 0.0。失败返回 None。"""
    s = text.replace("⁄", "/").replace("\u00a0", " ")
    m = re.search(r"(\d+)\s*/\s*(\d+)", s)          # 分数 1/2
    if m:
        return int(m.group(1)) / int(m.group(2))
    m = re.search(r"(\d+(?:\.\d+)?)\s*×", s)       # 2× / 0×
    if m:
        return float(m.group(1))
    return None


def parse_type_chart(soup):
    """解析属性相克大表。

    页面表格结构(HTML rowspan 不展开, 按文本特征鲁棒解析):
      表头行: 18 个防御方属性名
      数据行: 攻击方属性名 + 18 个倍率单元格(两端可能重复攻击方名)
    返回 (defenders, chart): defenders 为防御方属性顺序列表,
    chart 为 {攻击方: {防御方: 倍率}}。
    """
    defenders = None
    chart = {}
    for tr in soup.find_all("tr"):
        cells = [clean(c.get_text(" ", strip=True)) for c in tr.find_all(["th", "td"])]
        type_names = [c for c in cells if c in ALL_TYPES]
        mults = [m for m in (parse_mult(c) for c in cells) if m is not None]

        if defenders is None:
            # 表头行: 一整行属性名(18 个)
            if len(type_names) >= len(ALL_TYPES):
                defenders = type_names[: len(ALL_TYPES)]
            continue

        if len(mults) >= len(defenders) and type_names:
            attacker = type_names[0]               # 左端攻击方属性
            if attacker not in chart:
                chart[attacker] = dict(zip(defenders, mults[: len(defenders)]))

    if len(chart) != len(ALL_TYPES):
        raise RuntimeError(f"相克表解析不完整: 只解析到 {len(chart)}/{len(ALL_TYPES)} 个攻击属性")
    return defenders, chart


def crawl_type_chart(use_cache=True):
    """抓取属性相克页 -> 修正为第四世代规则 -> 写入 type_chart.json。"""
    print("== 抓取属性相克表 ==")
    html = fetch(TYPE_CHART_URL, cache_name="type_chart.html", use_cache=use_cache)
    soup = BeautifulSoup(html, "html.parser")
    defenders, chart = parse_type_chart(soup)

    # 第四世代(白金)没有妖精属性, 从攻防两侧剔除
    types = [t for t in defenders if t != "妖精"]
    attack = {
        atk: {d: v for d, v in row.items() if d != "妖精"}
        for atk, row in chart.items()
        if atk != "妖精"
    }
    # 修正为第四世代规则(详见 GEN4_CHART_FIX 注释)
    for atk, fixes in GEN4_CHART_FIX.items():
        attack[atk].update(fixes)

    # 自检: 应有 17x17 倍率, 且取值只可能为 0/0.5/1/2
    for atk, row in attack.items():
        if len(row) != len(types) or any(v not in (0.0, 0.5, 1.0, 2.0) for v in row.values()):
            raise RuntimeError(f"相克表自检失败: 攻击属性[{atk}] 数据异常")
    spot = attack["电"]["地面"]
    assert spot == 0.0, f"自检失败: 电打地面应为 0, 实际 {spot}"

    data = {"gen": 4, "types": types, "attack": attack}
    with open(TYPE_CHART_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"   已写入 {TYPE_CHART_JSON} ({len(types)} 属性 x {len(types)} 属性, 第四世代规则)")
    return data


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="爬取第四世代(白金)宝可梦资料")
    parser.add_argument("--limit", type=int, default=0, help="只抓前 N 只(测试)")
    parser.add_argument("--no-cache", action="store_true", help="忽略 HTML 缓存")
    parser.add_argument("--skip-images", action="store_true", help="不下载图片")
    parser.add_argument("--only-id", type=int, default=0, help="只抓指定编号")
    args = parser.parse_args()

    os.makedirs(IMG_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)

    # 属性相克表(独立于宝可梦列表, 有缓存, 便宜)
    try:
        crawl_type_chart(use_cache=not args.no_cache)
    except Exception as e:
        print(f"   属性相克表抓取失败({e}), 继续抓宝可梦数据")

    # 断点续爬: 读取已有结果
    done = {}
    if os.path.exists(OUTPUT_JSON):
        try:
            with open(OUTPUT_JSON, encoding="utf-8") as f:
                for item in json.load(f):
                    done[item["id"]] = item
        except Exception:
            pass

    pokemons = crawl_list()
    if args.only_id:
        pokemons = [p for p in pokemons if p["id"] == args.only_id]
    if args.limit:
        pokemons = pokemons[: args.limit]

    print(f"== 开始抓取 {len(pokemons)} 只宝可梦详情/招式 ==")
    results = []
    for i, p in enumerate(pokemons, 1):
        dex_id = p["id"]
        tag = f"[{i}/{len(pokemons)}] #{dex_id:03d} {p['name_zh']}"

        old = done.get(dex_id)
        if old and old.get("moves") is not None and (args.skip_images or old.get("image")):
            print(f"{tag} 已完成, 跳过")
            results.append(old)
            continue

        print(f"{tag} 抓取中...")
        entry = {
            "id": dex_id,
            "name_zh": p["name_zh"],
            "name_ja": p["name_ja"],
            "name_en": p["name_en"],
            "types": p["types"],
        }

        try:
            img_url, locations = crawl_detail(p)
            entry["image_url"] = img_url
            entry["platinum_locations"] = locations
            if not locations:
                print(f"    未找到白金版获得方式(可能在白金中不可自然获得)")

            if not args.skip_images:
                path = download_image(p, img_url)
                entry["image"] = path.split(os.sep)[-1] if path else None
            else:
                entry["image"] = None

            moves = crawl_moves(p)
            if moves is None:
                print(f"    警告: 未找到第四世代招式表")
                entry["moves"] = []
            else:
                entry["moves"] = moves
        except NotFoundError as e:
            # 招式子页等页面不存在: 记为空, 下次不再重试
            print(f"    页面不存在: {e}")
            entry.setdefault("platinum_locations", [])
            entry.setdefault("moves", [])
            entry.setdefault("image", None)
            entry.setdefault("image_url", None)
        except Exception as e:
            print(f"    抓取失败: {e}, 记录为不完整条目")
            entry.setdefault("platinum_locations", [])
            entry.setdefault("moves", None)
            entry.setdefault("image", None)

        results.append(entry)

        # 每只都增量保存, 中断可续
        all_results = [r if r["id"] != dex_id else entry for r in done.values()]
        merged = sorted(
            {r["id"]: r for r in list(done.values()) + results}.values(),
            key=lambda x: x["id"],
        )
        with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)

    # 最终输出
    merged = sorted({r["id"]: r for r in list(done.values()) + results}.values(), key=lambda x: x["id"])
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    complete = sum(1 for r in merged if r.get("moves"))
    n_img = len([f for f in os.listdir(IMG_DIR) if f.endswith(".png")]) if os.path.isdir(IMG_DIR) else 0
    print()
    print(f"== 完成: 共 {len(merged)} 只, 招式完整 {complete} 只, 图片 {n_img} 张 ==")
    print(f"JSON: {OUTPUT_JSON}")
    print(f"图片: {IMG_DIR}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n用户中断, 已保存的进度不会丢失, 重跑可续。")
        sys.exit(1)
