# scraper.py
import os
import json
import requests
from bs4 import BeautifulSoup

# 创建数据和图片目录
os.makedirs("pokedex_data/images", exist_ok=True)

URL = "https://wiki.52poke.com/zh-hans/%E5%AE%9D%E5%8F%AF%E6%A2%A6%E5%88%97%E8%A1%A8%EF%BC%88%E6%8C%89%E5%85%A8%E5%9B%BD%E5%9B%BE%E9%89%B4%E7%BC%96%E5%8F%B7%EF%BC%89"
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

print("正在连接神奇宝贝百科抓取第四世代数据...")
response = requests.get(URL, headers=headers)
soup = BeautifulSoup(response.text, "html.parser")

pokemon_list = []

# 第四世代在页面中通常是第4个主表格（从#387草苗龟 到 #493阿尔宙斯）
# 我们可以直接寻找包含 #387 的表格行
tables = soup.find_all("table", {"class": "roundy"})

target_table = None
for table in tables:
    if "草苗龟" in table.text and "#387" in table.text:
        target_table = table
        break

if not target_table:
    print("未能自动定位第四世代表格，请检查网络或页面结构。")
    exit()

rows = target_table.find_all("tr")[1:] # 跳过表头
for row in rows:
    tds = row.find_all("td")
    if len(tds) < 6:
        continue
    
    # 提取基本信息
    id_str = tds[0].text.strip() # 例: #387
    name_zh = tds[2].text.strip() # 例: 草苗龟
    
    # 属性处理 (有些宝可梦单属性，有些双属性)
    types = [tds[5].text.strip()]
    if len(tds) > 6 and tds[6].get("class") and "type" in "".join(tds[6].get("class")):
        types.append(tds[6].text.strip())
    
    # 对应图片的文件命名
    img_name = f"{id_str.replace('#', '')}.png"
    img_path = f"pokedex_data/images/{img_name}"
    
    # 尝试寻找该行的图片链接 (通常维基表头或左侧会有预览图缩略图)
    img_tag = row.find("img")
    if img_tag:
        img_url = "https:" + (img_tag.get("data-url") or img_tag.get("src"))
        # 下载图片
        try:
            img_data = requests.get(img_url, headers=headers, timeout=10).content
            with open(img_path, "wb") as f:
                f.write(img_data)
        except Exception as e:
            print(f"图片 {name_zh} 下载失败: {e}")
            
    pokemon_entry = {
        "id": id_str,
        "name": name_zh,
        "types": types,
        "image_file": img_name
    }
    pokemon_list.append(pokemon_entry)
    print(f"已收集: {id_str} {name_zh} - {types}")

# 导出为清晰的 JSON 结构
with open("pokedex_data/pokemon.json", "w", encoding="utf-8") as f:
    json.dump(pokemon_list, f, ensure_ascii=False, indent=4)

print("数据抓取并整理完成！保存在 pokedex_data 目录中。")
