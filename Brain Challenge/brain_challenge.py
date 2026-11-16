"""两人轮流限时答题的儿童头脑挑战。"""

from dataclasses import dataclass
import importlib
import itertools
import json
import math
import os
import random
import sys
import tempfile
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, "Lucky Wheel"))
wheel_support = importlib.import_module("lucky_wheel")
GPIOButtons = wheel_support.GPIOButtons
event_action = wheel_support.event_action
present_frame = wheel_support.present_frame
spi_lcd = wheel_support.spi_lcd
wrap_text = wheel_support.wrap_text

from common import ui_theme

import pygame


QUESTIONS_PER_GAME = 10
QUESTION_SECONDS = 30.0
FEEDBACK_SECONDS = 0.8
BUTTON_ACTIONS = ("K1", "K2", "K3")

FACT_QUESTIONS = (
	("一周有几天？", "7天", "5天", "10天"),
	("一年有几个季节？", "4个", "3个", "6个"),
	("哪种图形没有角？", "圆形", "三角形", "正方形"),
	("三角形有几条边？", "3条", "2条", "4条"),
	("正方形有几个角？", "4个", "3个", "5个"),
	("下雨时适合带什么？", "雨伞", "太阳镜", "围巾"),
	("看时间要用什么？", "钟表", "水杯", "积木"),
	("冰融化后变成什么？", "水", "沙子", "石头"),
	("哪一样是水果？", "苹果", "铅笔", "积木"),
	("刷牙通常用什么？", "牙刷", "画笔", "筷子"),
	("春天之后是什么季节？", "夏天", "冬天", "秋天"),
	("水结冰后是什么？", "冰块", "木块", "沙子"),
	("哪一样是文具？", "铅笔", "围巾", "水杯"),
	("周日的前一天是？", "周六", "周一", "周三"),
	("一小时有多少分钟？", "60分钟", "10分钟", "24分钟"),
	("哪种单位用来量长度？", "厘米", "分钟", "小时"),
	("红灯亮时应该怎么做？", "停下", "快跑", "闭眼"),
	("手电筒打开后可以？", "照明", "喝水", "写字"),
	("通常用什么盛水？", "水杯", "梳子", "尺子"),
	("12个月是多长时间？", "1年", "1周", "1天"),
	("一双鞋有几只？", "2只", "1只", "3只"),
	("晴朗的白天，天空通常是？", "蓝色", "黑色", "绿色"),
	("哪一种是交通工具？", "公交车", "书包", "牙刷"),
	("写错铅笔字可以用？", "橡皮", "水杯", "手套"),
	("一天有几个小时？", "24小时", "12小时", "7小时"),
	("一分钟有多少秒？", "60秒", "10秒", "24秒"),
	("一年有几个月？", "12个月", "7个月", "4个月"),
	("一米有多少厘米？", "100厘米", "10厘米", "60厘米"),
	("一元有多少角？", "10角", "5角", "12角"),
	("夏天之后是什么季节？", "秋天", "春天", "冬天"),
	("秋天之后是什么季节？", "冬天", "夏天", "春天"),
	("冬天之后是什么季节？", "春天", "秋天", "夏天"),
	("长方形有几条边？", "4条", "3条", "5条"),
	("五边形有几条边？", "5条", "4条", "6条"),
	("六边形有几条边？", "6条", "5条", "4条"),
	("圆形有几个角？", "0个", "1个", "4个"),
	("哪种图形有三个角？", "三角形", "圆形", "正方形"),
	("哪种图形有四个角？", "正方形", "圆形", "三角形"),
	("哪一种是立体形状？", "球体", "圆形", "三角形"),
	("硬币通常是什么形状？", "圆形", "三角形", "正方形"),
	("红色和黄色颜料混合后通常是？", "橙色", "绿色", "蓝色"),
	("蓝色和黄色颜料混合后通常是？", "绿色", "红色", "白色"),
	("红色和白色颜料混合后通常是？", "粉红色", "蓝色", "绿色"),
	("黑色和白色颜料混合后通常是？", "灰色", "橙色", "绿色"),
	("红色和蓝色颜料混合后通常是？", "紫色", "黄色", "绿色"),
	("草地通常是什么颜色？", "绿色", "紫色", "黑色"),
	("白雪通常是什么颜色？", "白色", "红色", "蓝色"),
	("过马路应走哪里？", "斑马线", "花坛", "草坪"),
	("洗手时通常用什么清洁？", "肥皂", "蜡笔", "积木"),
	("垃圾通常应放在哪里？", "垃圾桶", "书包", "衣柜"),
	("衣服脏了需要做什么？", "清洗", "浇水", "画画"),
	("擦干洗过的脸可以用？", "毛巾", "积木", "书本"),
	("梳头发常用什么？", "梳子", "勺子", "尺子"),
	("写字常用什么？", "铅笔", "手套", "雨伞"),
	("画直线常用什么？", "尺子", "围巾", "碗"),
	("擦桌子常用什么？", "抹布", "积木", "纸飞机"),
	("喝汤常用什么？", "勺子", "蜡笔", "手套"),
	("盛饭通常用什么？", "碗", "尺子", "画笔"),
	("想知道天气可以看什么？", "天气预报", "字典", "钟表"),
	("上学用品通常放在哪里？", "书包", "水杯", "饭碗"),
	("书通常放在哪里？", "书架", "冰箱", "水杯"),
	("吃东西前要先做什么？", "洗手", "跑步", "画画"),
	("听声音用什么？", "耳朵", "眼睛", "鼻子"),
	("看东西用什么？", "眼睛", "耳朵", "鼻子"),
	("闻味道用什么？", "鼻子", "耳朵", "眼睛"),
	("人通常用什么走路？", "双脚", "头发", "耳朵"),
	("一只手通常有几根手指？", "5根", "4根", "6根"),
	("人通常有几只眼睛？", "2只", "1只", "3只"),
	("植物通常需要什么才能生长？", "阳光", "积木", "纸张"),
	("植物一般用什么吸收水分？", "根", "花瓣", "果皮"),
	("树叶一般长在哪里？", "树枝上", "书包里", "水杯里"),
	("种子发芽后可能长成什么？", "植物", "石头", "玩具"),
	("白云一般在哪里？", "天空", "书里", "水杯里"),
	("阳光来自哪里？", "太阳", "积木", "书本"),
	("雨通常从哪里落下？", "天空", "地底", "书包"),
	("天气寒冷时，水可能变成？", "冰", "沙子", "纸"),
	("月亮一般能在哪里看到？", "天空", "抽屉", "杯底"),
	("雪一般出现在怎样的天气？", "寒冷", "炎热", "闷热"),
	("给花浇水要用什么？", "水", "积木", "纸"),
	("彩虹通常说有几种颜色？", "7种", "3种", "10种"),
	("太阳升起通常是在？", "早晨", "午夜", "深夜"),
	("午餐通常在什么时间？", "中午", "午夜", "凌晨"),
	("轮船通常在哪里行驶？", "水面", "天空", "铁轨"),
	("火车通常在哪里行驶？", "铁轨", "水面", "天空"),
	("飞机通常在哪里飞行？", "天空", "地下", "水底"),
	("公交车通常在哪里行驶？", "道路", "水底", "屋顶"),
	("自行车通常有几个轮子？", "2个", "3个", "4个"),
	("三轮车通常有几个轮子？", "3个", "2个", "4个"),
	("小汽车通常有几个轮子？", "4个", "2个", "3个"),
	("太阳系中的地球是？", "行星", "星座", "颜色"),
	("哪样能测量温度？", "温度计", "尺子", "橡皮"),
	("哪样能测量长度？", "尺子", "闹钟", "水杯"),
	("哪样可以记录声音？", "录音机", "书包", "雨伞"),
	("哪种材料通常能透过光？", "透明玻璃", "纸板", "木板"),
	("哪样在平地更容易滚动？", "圆球", "方形积木", "纸片"),
	("一封信通常用什么装？", "信封", "鞋子", "水杯"),
	("向北的相反方向是？", "南", "东", "西"),
	("太阳一般从哪边升起？", "东方", "西方", "北方"),
	("地球上有陆地和什么？", "海洋", "饼干", "书包"),
	("哪种水通常是咸的？", "海水", "雨水", "纯净水"),
	("普通书的封面通常像？", "长方形", "圆形", "三角形"),
	("天黑后用什么照亮？", "手电筒", "橡皮", "书包"),
	("雨后地上可能出现什么？", "水坑", "沙发", "书架"),
	("想把纸粘起来可以用？", "胶水", "尺子", "杯子"),
	("剪纸通常用什么工具？", "安全剪刀", "勺子", "手套"),
	("铃声通常用什么听到？", "耳朵", "鼻子", "手指"),
)

FACT_GROUPS = (
	("水果", ("苹果", "香蕉", "梨", "葡萄", "西瓜", "草莓", "桃子", "橙子", "樱桃",
			  "柠檬", "菠萝", "芒果", "荔枝", "杨梅", "火龙果", "猕猴桃")),
	("蔬菜", ("白菜", "菠菜", "芹菜", "萝卜", "胡萝卜", "黄瓜", "南瓜", "冬瓜", "青椒",
			  "茄子", "土豆", "卷心菜", "西兰花", "莲藕", "山药", "生菜")),
	("学习用品", ("铅笔", "橡皮", "尺子", "蜡笔", "钢笔", "圆珠笔", "粉笔", "画笔", "笔盒",
				  "作业本", "画纸", "笔记本", "水彩笔", "铅笔盒", "书包")),
	("交通工具", ("汽车", "公交车", "火车", "高铁", "地铁", "轮船", "帆船", "自行车", "三轮车",
				  "摩托车", "飞机", "直升机", "小船", "卡车", "电车")),
	("衣物", ("外套", "毛衣", "衬衫", "裙子", "裤子", "短袖", "棉袄", "睡衣", "背心",
			  "围巾", "帽子", "手套", "袜子", "雨衣", "校服")),
	("乐器", ("钢琴", "吉他", "小提琴", "手鼓", "口琴", "笛子", "大提琴", "木琴", "铃鼓",
			  "小号", "三角铁", "架子鼓", "竖琴", "电子琴")),
	("图形", ("圆形", "三角形", "正方形", "长方形", "五边形", "六边形", "椭圆形",
			  "菱形", "半圆形", "梯形", "平行四边形")),
	("运动", ("跑步", "游泳", "跳绳", "足球", "篮球", "乒乓球", "羽毛球", "排球", "滑冰",
			  "骑车", "跳远", "体操", "踢毽子", "滑雪")),
)

VISUAL_SHAPES = (
	("star", "星星有几颗？"),
	("circle", "圆形有几个？"),
	("triangle", "三角形有几个？"),
	("square", "方块有几个？"),
)

THINK_QUESTIONS = (
	("排队第3位，前面有几人？", "2人", "3人", "4人"),
	("排队第5位，前面有几人？", "4人", "5人", "6人"),
	("两双手套共有几只？", "4只", "2只", "6只"),
	("一张纸对折一次有几层？", "2层", "1层", "3层"),
	("今天周一，明天是周几？", "周二", "周日", "周三"),
	("今天周五，昨天是周几？", "周四", "周六", "周三"),
	("一只手5根手指，两只有几根？", "10根", "5根", "8根"),
	("6块积木分给2人，每人一样多，有几块？", "3块", "2块", "4块"),
	("3个杯子各放1颗糖，共几颗？", "3颗", "1颗", "4颗"),
	("2个盒子各放2块积木，共几块？", "4块", "2块", "6块"),
	("比8小1的数是几？", "7", "9", "6"),
	("比5大2的数是几？", "7", "6", "8"),
	("从1数到5，一共数了几个数？", "5个", "4个", "6个"),
	("一根绳剪一刀，分成几段？", "2段", "1段", "3段"),
	("第2名的前面有几个人？", "1人", "2人", "3人"),
	("4支笔拿走1支，还剩几支？", "3支", "1支", "4支"),
	("一个盒子放3块，两个盒子共放几块？", "6块", "3块", "5块"),
	("早上起床后，接下来通常是？", "白天", "昨天", "午夜"),
	("3个小朋友每人1杯，共几杯？", "3杯", "2杯", "4杯"),
	("5个球分给5人，每人几个？", "1个", "2个", "5个"),
)

WORD_PAIRS = {
	"近义词": (
		("高兴", "开心", "难过", "生气"),
		("漂亮", "美丽", "丑陋", "狭窄"),
		("迅速", "快速", "缓慢", "迟钝"),
		("安静", "宁静", "吵闹", "喧闹"),
		("寒冷", "冰冷", "炎热", "温暖"),
		("温暖", "暖和", "寒冷", "嘈杂"),
		("害怕", "恐惧", "勇敢", "快乐"),
		("伙伴", "同伴", "敌人", "陌生人"),
		("明亮", "光亮", "黑暗", "苦涩"),
		("洁净", "干净", "肮脏", "忙碌"),
		("寻找", "寻觅", "躲藏", "休息"),
		("休息", "歇息", "奔跑", "出发"),
		("帮助", "帮忙", "拒绝", "责怪"),
		("马上", "立刻", "缓慢", "经常"),
		("突然", "忽然", "经常", "缓慢"),
		("认真", "仔细", "马虎", "热闹"),
		("广阔", "宽广", "狭窄", "细小"),
		("答复", "回答", "提问", "哭泣"),
		("记住", "牢记", "忘记", "丢失"),
		("奇怪", "古怪", "普通", "善良"),
		("错误", "差错", "正确", "迅速"),
		("许多", "很多", "少数", "迅速"),
	),
	"反义词": (
		("高", "矮", "胖", "冷"),
		("大", "小", "长", "热"),
		("多", "少", "早", "远"),
		("快", "慢", "轻", "小"),
		("前", "后", "左", "右"),
		("左", "右", "上", "下"),
		("上", "下", "前", "后"),
		("长", "短", "高", "矮"),
		("厚", "薄", "深", "浅"),
		("深", "浅", "宽", "窄"),
		("宽", "窄", "厚", "薄"),
		("轻", "重", "快", "慢"),
		("冷", "热", "高", "矮"),
		("远", "近", "早", "晚"),
		("早", "晚", "多", "少"),
		("开", "关", "里", "外"),
		("进", "出", "生", "熟"),
		("里", "外", "前", "后"),
		("明", "暗", "粗", "细"),
		("哭", "笑", "跑", "跳"),
		("黑", "白", "红", "绿"),
		("粗", "细", "大", "小"),
		("真", "假", "长", "短"),
		("对", "错", "快", "慢"),
	),
}

WORD_QUESTIONS = (
	("表示疑问的句末符号是？", "问号", "句号", "逗号"),
	("“一朵花”中的量词是？", "朵", "一", "花"),
	("“一条鱼”中的量词是？", "条", "一", "鱼"),
	("“一棵树”中的量词是？", "棵", "一", "树"),
	("形容做事很专心的词语是？", "专心致志", "东张西望", "三心二意"),
	("形容心情高兴的词语是？", "眉开眼笑", "垂头丧气", "愁眉苦脸"),
	("“东张西望”的意思接近？", "到处看", "认真听", "用力跑"),
	("“画蛇添足”指的是？", "多此一举", "团结合作", "勇敢向前"),
	("“一心一意”的意思是？", "专心", "分心", "生气"),
	("“井井有条”形容做事怎样？", "有条理", "乱糟糟", "慢吞吞"),
	("“一举两得”表示？", "做一件事有两个收获", "做两件事都失败", "只做了一半"),
	("“半途而废”的意思是？", "中途放弃", "一直坚持", "立刻出发"),
)

SCIENCE_QUESTIONS = (
	("地球绕着哪颗恒星运行？", "太阳", "月亮", "北极星"),
	("月球是地球的什么？", "卫星", "恒星", "行星"),
	("太阳属于哪一类天体？", "恒星", "卫星", "行星"),
	("昼夜交替主要由什么造成？", "地球自转", "地球公转", "月球发光"),
	("地球绕太阳一周约需多久？", "一年", "一天", "一个月"),
	("月亮反射的光主要来自？", "太阳", "路灯", "火山"),
	("地球的形状更接近？", "球体", "正方体", "平面"),
	("太阳系最大的行星是？", "木星", "地球", "火星"),
	("离太阳最近的行星是？", "水星", "火星", "木星"),
	("哪颗行星有明显的光环？", "土星", "火星", "水星"),
	("哪颗行星被称为红色星球？", "火星", "金星", "海王星"),
	("地球上的季节变化与什么有关？", "公转和地轴倾斜", "月亮发光", "海水咸淡"),
	("植物主要靠什么制造养分？", "光合作用", "走路", "睡眠"),
	("光合作用需要吸收哪种气体？", "二氧化碳", "氦气", "氮气"),
	("植物光合作用通常释放什么？", "氧气", "氦气", "氮气"),
	("植物的根主要吸收什么？", "水和矿物质", "阳光和声音", "纸和积木"),
	("种子发芽一般需要什么？", "水和空气", "金属和盐", "颜料和胶水"),
	("仙人掌的刺是由什么变成的？", "叶", "根", "花"),
	("平常吃的胡萝卜主要是？", "根", "叶", "花"),
	("蚕宝宝长大后会结成什么？", "茧", "果实", "种子"),
	("青蛙的蝌蚪长大后变成？", "青蛙", "蝴蝶", "蜗牛"),
	("蜜蜂通常有几条腿？", "6条", "4条", "8条"),
	("蝴蝶属于哪一类？", "昆虫", "鱼类", "鸟类"),
	("蝙蝠用什么喂养幼崽？", "乳汁", "树叶", "沙子"),
	("鲸鱼主要用什么呼吸？", "肺", "鳃", "树叶"),
	("蜘蛛通常有几条腿？", "8条", "6条", "4条"),
	("大多数鱼主要用什么呼吸？", "鳃", "肺", "树根"),
	("哪种动物属于哺乳动物？", "海豚", "鲨鱼", "蝴蝶"),
	("蜜蜂采蜜时还能帮助植物？", "传粉", "造雨", "发光"),
	("水受冷变成冰称为？", "凝固", "蒸发", "熔化"),
	("冰受热变成水称为？", "熔化", "凝固", "沉淀"),
	("水蒸气遇冷变成小水滴是？", "液化", "凝固", "燃烧"),
	("水变成水蒸气的过程叫？", "汽化", "凝固", "结冰"),
	("空气中含量最多的气体是？", "氮气", "氧气", "二氧化碳"),
	("发出声音的物体通常在？", "振动", "发光", "融化"),
	("声音不能在什么环境中传播？", "真空", "空气", "水"),
	("人体负责泵送血液的器官是？", "心脏", "胃", "耳朵"),
	("人体主要用哪个器官呼吸？", "肺", "心脏", "骨骼"),
	("骨骼的重要作用是什么？", "支撑身体", "制造阳光", "改变天气"),
	("保护大脑的骨头是？", "颅骨", "肋骨", "腿骨"),
	("眼睛前方透明的部分叫？", "角膜", "耳廓", "指甲"),
	("磁铁最容易吸引哪种材料？", "铁", "木头", "塑料"),
	("影子通常出现在物体的哪边？", "背光的一边", "朝光的一边", "一定在上方"),
	("太阳能电池把阳光转化为？", "电能", "泥土", "冰"),
	("用放大镜观察小字会显得？", "更大", "更远", "消失"),
	("标准大气压下，水约几度沸腾？", "100度", "0度", "30度"),
	("标准大气压下，冰约几度融化？", "0度", "50度", "100度"),
	("红绿蓝三色光适当混合可得到？", "白光", "黑色", "棕色"),
	("加热通常会让水蒸发得怎样？", "更快", "停止", "变成盐"),
	("水循环中，水蒸气遇冷可能形成？", "云", "砖头", "金属"),
)

GEOGRAPHY_QUESTIONS = (
	("中国位于哪个大洲？", "亚洲", "欧洲", "南美洲"),
	("中国的首都是哪里？", "北京", "上海", "广州"),
	("中国最长的河流是？", "长江", "黄河", "珠江"),
	("长江最终流入哪片海？", "东海", "渤海", "红海"),
	("黄河最终流入哪片海？", "渤海", "红海", "地中海"),
	("万里长城位于哪个国家？", "中国", "巴西", "埃及"),
	("珠穆朗玛峰属于什么地形？", "山峰", "平原", "海峡"),
	("世界上面积最大的大洲是？", "亚洲", "欧洲", "南极洲"),
	("世界上面积最大的洋是？", "太平洋", "印度洋", "北冰洋"),
	("北极附近的大洋叫？", "北冰洋", "印度洋", "大西洋"),
	("南极大陆大部分覆盖着？", "冰雪", "沙漠植物", "热带雨林"),
	("地球表面面积更大的是？", "海洋", "陆地", "森林"),
	("赤道位于地球的什么位置？", "南北两极之间", "北极顶端", "南极顶端"),
	("地球上最长的纬线是？", "赤道", "北极点", "南极点"),
	("经线可以帮助确定什么？", "经度", "温度", "重量"),
	("纬线可以帮助确定什么？", "纬度", "声音", "重量"),
	("通常地图的上方表示？", "北", "南", "西"),
	("通常地图的下方表示？", "南", "北", "东"),
	("北朝上的地图右方表示？", "东", "西", "南"),
	("北朝上的地图左方表示？", "西", "东", "北"),
	("地图上的蓝色通常表示？", "水域", "沙漠", "道路"),
	("地图图例用来说明什么？", "符号含义", "当天温度", "纸张重量"),
	("地图比例尺表示什么？", "图上与实际距离的比例", "山峰的颜色", "城市的人口"),
	("被海水包围的较小陆地叫？", "岛屿", "半岛", "海峡"),
	("三面环水的陆地一般叫？", "半岛", "海峡", "山谷"),
	("连接两片海域的狭窄水道叫？", "海峡", "山谷", "平原"),
	("海拔是相对什么的高度？", "平均海平面", "房屋屋顶", "湖边树梢"),
	("山谷通常位于哪里？", "两山之间", "云层上方", "海洋中心"),
	("平原通常有什么特点？", "地势较平坦", "四面环水", "全是冰雪"),
	("自然界中的河水通常怎样流？", "从高处流向低处", "从低处流向高处", "只向西流"),
	("海水有规律地涨落叫？", "潮汐", "地震", "日食"),
	("沙丘主要由什么堆积而成？", "沙子", "冰块", "木头"),
	("冰川主要由什么长期积累形成？", "积雪", "树叶", "沙子"),
	("台风属于什么天气系统？", "强烈风暴", "晴天", "彩虹"),
	("天气预报里的气温常用什么单位？", "摄氏度", "厘米", "千克"),
	("赤道附近总体上比两极怎样？", "更温暖", "更寒冷", "完全一样"),
	("沿海地区靠近哪里？", "海洋", "月球", "森林顶部"),
	("世界最高峰是？", "珠穆朗玛峰", "泰山", "黄山"),
	("中国国旗上有几颗星？", "5颗", "3颗", "7颗"),
	("地球上面积最大的大陆是？", "亚欧大陆", "南极大陆", "非洲大陆"),
	("哪种能源可以不断再生？", "太阳能", "煤炭", "石油"),
	("沙漠通常缺少什么？", "降水", "阳光", "空气"),
	("地球有哪两个地理极点？", "南极和北极", "东极和西极", "上极和下极"),
	("北京在上海的大致哪个方向？", "西北", "东南", "正南"),
)

SAFETY_QUESTIONS = (
	("在中国遇到火灾可拨打？", "119", "110", "120"),
	("在中国需要紧急医疗救助可拨？", "120", "119", "114"),
	("在中国遇到紧急治安问题可拨？", "110", "120", "114"),
	("发现火灾时应先做什么？", "尽快撤离并求助", "躲进衣柜", "乘电梯下楼"),
	("安全通道可通行时，火灾应走？", "楼梯", "电梯", "窗外"),
	("遇到浓烟时应怎样撤离？", "低姿前行", "直立奔跑", "躲在柜里"),
	("闻到燃气味，离开现场后应？", "联系大人或求助", "点火查看", "返回开灯"),
	("过马路时红灯亮了应？", "停下等待", "立刻冲过去", "闭眼走"),
	("过马路应优先走哪里？", "人行横道", "机动车道中间", "道路护栏"),
	("通过路口时要注意？", "观察来往车辆", "低头玩手机", "追逐打闹"),
	("乘坐汽车时应系好什么？", "安全带", "围巾", "鞋带"),
	("汽车行驶时应坐在哪里？", "座位上", "车窗外", "驾驶员腿上"),
	("骑车上路要遵守什么？", "交通规则", "只看手机", "随意逆行"),
	("上下楼梯时应怎样？", "扶好扶手", "在楼梯上追跑", "从扶手滑下"),
	("地面湿滑时应怎样走？", "慢慢走", "快速奔跑", "闭眼跳跃"),
	("发现破损电线应怎样？", "远离并告诉大人", "用手触摸", "往上泼水"),
	("手湿时使用电器应怎样？", "先擦干手", "直接插电", "往插座泼水"),
	("不能向插座里塞什么？", "回形针", "电器插头", "安全插座盖"),
	("小朋友想用剪刀应？", "在大人指导下使用", "拿着跑", "对着别人挥"),
	("不认识的药品可以随便吃吗？", "不可以", "可以", "只吃一点可以"),
	("生病需要吃药时应？", "听医生和大人的安排", "自己随便选", "把药当糖吃"),
	("看到不明液体应该？", "不碰并告诉大人", "先尝一口", "倒在身上"),
	("陌生人要带你走，应该？", "拒绝并找可信的大人", "马上跟着走", "不告诉家人"),
	("和家人走散后应找谁帮忙？", "工作人员或警察", "随便跟陌生人走", "自己躲起来"),
	("个人住址和密码应怎样？", "谨慎保管", "随便告诉陌生人", "贴在公共墙上"),
	("网络上陌生人索要密码应？", "拒绝并告诉大人", "立刻发送", "发给所有人"),
	("游泳时小朋友应该？", "有大人看护", "独自下水", "在深水区打闹"),
	("看到有人落水应？", "呼叫大人并求助", "自己立刻跳水", "假装没看见"),
	("水边玩耍时应注意？", "远离危险水域", "在岸边追逐", "独自下水"),
	("雷雨时较安全的地方是？", "安全的室内", "孤立的大树下", "空旷的山顶"),
	("阳台护栏附近应该？", "不攀爬护栏", "站在护栏上", "向外探身"),
	("窗户旁应避免什么？", "攀爬窗台", "坐在安全处", "请大人关窗"),
	("玩具很小时，应注意？", "不要放入口中", "塞进鼻子", "边跑边咬"),
	("吃东西前应该做什么？", "洗手", "摸插座", "在楼梯上跑"),
	("食物已经变质应？", "不要食用", "尝一口判断", "继续食用"),
	("使用热水时应怎样？", "请大人帮助", "把水泼向自己", "闭眼端热水"),
	("发现有人受伤应？", "及时告诉大人", "独自离开", "强行拖动"),
	("听到紧急疏散提示应？", "听从指引有序撤离", "推挤奔跑", "返回拿玩具"),
	("公共场所逃生时应注意？", "寻找安全出口", "堵住出口", "逆人流奔跑"),
	("发现可疑危险物品应？", "远离并告诉大人", "捡起来拆开", "藏进书包"),
	("小朋友想用刀具时应？", "请大人帮助", "拿着追跑", "抛向空中"),
	("乘公交车时应等车怎样？", "停稳后再上下", "行驶时跳上", "在车前追跑"),
	("放风筝时要远离哪里？", "电线", "空旷草地", "公园步道"),
	("使用头盔时应怎样？", "戴好并系牢", "只拿在手里", "遮住眼睛"),
)

LOGIC_QUESTIONS = (
	("盒里只有红球，摸出的一定是？", "红球", "蓝球", "黄球"),
	("卡片是红色或蓝色，不是红色，是？", "蓝色", "红色", "黄色"),
	("3张卡片仅1张有星星，至少翻几张保证能看到？", "3张", "1张", "2张"),
	("袋里有足够多红蓝球，摸几球一定有两个同色？", "3个", "2个", "1个"),
	("所有三角卡都是红色，一张三角卡是？", "红色", "蓝色", "绿色"),
	("大于6、小于9的偶数是？", "8", "7", "9"),
	("比3大、比5小的整数是？", "4", "3", "5"),
	("3个连续整数中间是4，最小的是？", "3", "4", "5"),
	("3人两两握手一次，共握几次？", "3次", "2次", "6次"),
	("一根绳子剪两刀，最多几段？", "3段", "2段", "4段"),
	("4枚硬币排成一行，相邻之间有几个间隔？", "3个", "4个", "5个"),
	("3盏灯亮着，关掉1盏还亮几盏？", "2盏", "1盏", "3盏"),
	("时钟连续敲3下，中间有几个间隔？", "2个", "3个", "1个"),
	("红黄蓝卡各1张，拿走红黄还剩？", "蓝卡", "红卡", "黄卡"),
	("三个不同数中，最大的比最小的？", "大", "小", "相等"),
)


@dataclass(frozen=True)
class Question:
	category: str
	prompt: str
	choices: tuple
	answer: int
	visual: tuple = ()


@dataclass(frozen=True)
class AnswerRecord:
	choice: int | None
	correct: bool
	elapsed_centiseconds: int


@dataclass(frozen=True)
class QuestionSpec:
	category: str
	prompt: str
	correct: str
	wrong_choices: tuple = ()
	visual: tuple = ()
	family: str = ""

	@property
	def identity(self):
		return json.dumps((self.category, self.prompt, sorted(self.visual)),
						  ensure_ascii=False, separators=(",", ":"))


class QuestionHistory:
	def __init__(self, path=None):
		self.path = path
		self.seen = {}
		self.counter = 0
		self.warned = False
		if path is not None:
			try:
				with open(path, encoding="utf-8") as source:
					data = json.load(source)
				entries = data.get("seen", {}) if isinstance(data, dict) else {}
				if isinstance(entries, dict):
					self.seen = {key: value for key, value in entries.items()
								 if isinstance(key, str) and isinstance(value, int) and value > 0}
					self.counter = max(self.seen.values(), default=0)
			except (OSError, ValueError):
				pass

	def select(self, rng, candidates, count):
		groups = {}
		for question in candidates:
			groups.setdefault(question.category, []).append(question)
		unseen_counts = {}
		category_sizes = {}
		for category, group in groups.items():
			category_sizes[category] = len(group)
			unseen_counts[category] = sum(not self.seen.get(question.identity, 0) for question in group)
			rng.shuffle(group)
			group.sort(key=lambda question: self.seen.get(question.identity, 0), reverse=True)
		selected = []
		categories = set()
		families = set()
		while len(selected) < count:
			available = []
			for allow_category, allow_family in ((False, False), (True, False), (False, True), (True, True)):
				for category, group in groups.items():
					if not allow_category and category in categories:
						continue
					for index in range(len(group) - 1, -1, -1):
						question = group[index]
						if not allow_family and (question.family or category) in families:
							continue
						available.append((self.seen.get(question.identity, 0), category, index))
						break
				if available:
					break
			if not available:
				break
			oldest = min(age for age, _, _ in available)
			choices = [(category, index) for age, category, index in available if age == oldest]
			if oldest == 0:
				most_remaining = max(unseen_counts[name] / category_sizes[name] for name, _ in choices)
				choices = [(name, index) for name, index in choices
						   if unseen_counts[name] / category_sizes[name] == most_remaining]
			category, index = rng.choice(choices)
			if oldest == 0:
				unseen_counts[category] -= 1
			question = groups[category].pop(index)
			selected.append(question)
			categories.add(category)
			families.add(question.family or category)
		for question in selected:
			self.counter += 1
			self.seen[question.identity] = self.counter
		return selected

	def save(self):
		if self.path is None:
			return
		temporary_path = None
		try:
			directory = os.path.dirname(os.path.abspath(self.path))
			os.makedirs(directory, exist_ok=True)
			with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=directory, delete=False) as output:
				temporary_path = output.name
				json.dump({"seen": self.seen}, output, ensure_ascii=False)
			for attempt in range(4):
				try:
					os.replace(temporary_path, self.path)
					break
				except PermissionError:
					if attempt == 3:
						raise
					time.sleep(0.02 * (2 ** attempt))
		except OSError:
			if temporary_path is not None:
				try:
					os.remove(temporary_path)
				except OSError:
					pass
			if not self.warned:
				print("题目历史无法保存；本次游戏内仍会尽量避免重复。")
				self.warned = True


def default_history_path():
	if os.name == "nt":
		directory = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
	else:
		directory = os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
	return os.path.join(directory, "WonderBox", "brain_challenge_history.json")


def make_question(rng, category, prompt, correct, wrong_choices, visual=()):
	choices = [str(correct)] + [str(choice) for choice in wrong_choices]
	rng.shuffle(choices)
	return Question(category, prompt, tuple(choices), choices.index(str(correct)), tuple(visual))


def number_question(rng, category, prompt, answer, visual=()):
	nearby = [number for number in range(max(0, answer - 3), answer + 4) if number != answer]
	return make_question(rng, category, prompt, answer, rng.sample(nearby, 2), visual)


def build_question_bank():
	bank = {category: [] for category in (
		"算一算", "找规律", "看图形", "小常识", "动脑筋", "词语乐园",
		"时间日历", "方向空间", "逻辑推理", "科学发现", "自然地理", "安全守护",
	)}
	identities = set()

	def add(category, prompt, correct, wrong_choices=(), visual=(), family=""):
		spec = QuestionSpec(category, prompt, str(correct), tuple(wrong_choices), tuple(visual), family)
		if spec.identity not in identities:
			identities.add(spec.identity)
			bank[category].append(spec)

	for first in range(1, 21):
		for second in range(1, 21):
			if first + second <= 20:
				add("算一算", "%d + %d = ？" % (first, second), first + second, family="addition")
			if first >= second:
				add("算一算", "%d - %d = ？" % (first, second), first - second, family="subtraction")
	for start in range(1, 11):
		for step in range(1, 5):
			prompt = "%d、%d、%d、？" % (start, start + step, start + step * 2)
			if start + step * 3 <= 20:
				add("找规律", prompt, start + step * 3)
	for start in range(4, 21):
		for step in range(1, 5):
			if start - step * 3 >= 0:
				prompt = "%d、%d、%d、？" % (start, start - step, start - step * 2)
				add("找规律", prompt, start - step * 3)
	for first in range(1, 10):
		for second in range(1, 10):
			if first != second:
				add("找规律", "%d、%d、%d、%d、？" % (first, second, first, second), first)
				add("找规律", "%d、%d、%d、%d、%d、？" %
					(first, second, first, second, first), second)
	for start in range(1, 9):
		for step in range(1, 4):
			prompt = "%d、%d、？、%d" % (start, start + step, start + step * 3)
			add("找规律", prompt, start + step * 2)
	for shape, prompt in VISUAL_SHAPES:
		for other_shape, _ in VISUAL_SHAPES:
			if other_shape == shape:
				continue
			for count in range(1, 7):
				for other_count in range(1, 4):
					visual = (shape,) * count + (other_shape,) * other_count
					add("看图形", prompt, count, visual=visual)
	shared_families = {
		"周日的前一天是？": "weekday",
		"今天周一，明天是周几？": "weekday",
		"今天周五，昨天是周几？": "weekday",
		"比8小1的数是几？": "subtraction",
		"比5大2的数是几？": "addition",
		"4支笔拿走1支，还剩几支？": "subtraction",
		"向北的相反方向是？": "direction",
		"一根绳剪一刀，分成几段？": "rope_segments",
		"一根绳子剪两刀，最多几段？": "rope_segments",
		"红灯亮时应该怎么做？": "red_light",
		"过马路时红灯亮了应？": "red_light",
		"过马路应走哪里？": "crosswalk",
		"过马路应优先走哪里？": "crosswalk",
		"吃东西前要先做什么？": "wash_before_eating",
		"吃东西前应该做什么？": "wash_before_eating",
		"太阳系中的地球是？": "celestial_type",
		"太阳属于哪一类天体？": "celestial_type",
		"月球是地球的什么？": "celestial_type",
		"水结冰后是什么？": "water_freezes",
		"水受冷变成冰称为？": "water_freezes",
		"冰融化后变成什么？": "ice_melts",
		"冰受热变成水称为？": "ice_melts",
	}
	for category, entries in (("小常识", FACT_QUESTIONS), ("动脑筋", THINK_QUESTIONS)):
		for prompt, correct, wrong_first, wrong_second in entries:
			add(category, prompt, correct, (wrong_first, wrong_second), family=shared_families.get(prompt, ""))
	for group_index, (category, items) in enumerate(FACT_GROUPS):
		other_groups = [name for name, _ in FACT_GROUPS if name != category]
		for item_index, item in enumerate(items):
			first = (group_index + item_index) % len(other_groups)
			second = (first + 3) % len(other_groups)
			add("小常识", "%s属于哪一类？" % item, category,
				(other_groups[first], other_groups[second]))
	for month in range(1, 13):
		for direction, label in ((1, "下"), (-1, "上")):
			answer = (month - 1 + direction) % 12 + 1
			other = (month - 1 + direction * 2) % 12 + 1
			add("小常识", "%d月的%s个月是？" % (month, label), "%d月" % answer,
				("%d月" % month, "%d月" % other))
	for position in range(2, 11):
		add("动脑筋", "排队第%d位，前面有几人？" % position, position - 1)
	for total in range(3, 11):
		for position in range(1, total + 1):
			add("动脑筋", "%d人排队，排第%d，后面几人？" % (total, position), total - position)
	for number in range(1, 13):
		for difference in range(1, 4):
			add("动脑筋", "比%d大%d的数是几？" % (number, difference), number + difference, family="addition")
			if number >= difference:
				add("动脑筋", "比%d小%d的数是几？" % (number, difference), number - difference, family="subtraction")
	items = (("积木", "块"), ("贴纸", "张"), ("糖果", "颗"))
	for boxes in range(2, 5):
		for amount in range(1, 6):
			for item, unit in items:
				prompt = "%d盒%s，每盒%d%s，共几%s？" % (boxes, item, amount, unit, unit)
				add("动脑筋", prompt, boxes * amount)
	for people in range(2, 5):
		for amount in range(1, 5):
			for item, unit in items:
				prompt = "%d%s%s平均分%d人，每人几%s？" % (people * amount, unit, item, people, unit)
				add("动脑筋", prompt, amount)
	days = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
	for index, day in enumerate(days):
		for direction, label in ((1, "明天"), (-1, "昨天")):
			correct = days[(index + direction) % len(days)]
			other = days[(index + direction * 2) % len(days)]
			add("动脑筋", "今天%s，%s是周几？" % (day, label), correct, (day, other), family="weekday")
	for relation, pairs in WORD_PAIRS.items():
		for first, second, wrong_first, wrong_second in pairs:
			for word, answer in ((first, second), (second, first)):
				add("词语乐园", "“%s”的%s是？" % (word, relation), answer,
					(wrong_first, wrong_second))
	for category, entries in (("词语乐园", WORD_QUESTIONS), ("逻辑推理", LOGIC_QUESTIONS),
							  ("科学发现", SCIENCE_QUESTIONS), ("自然地理", GEOGRAPHY_QUESTIONS),
							  ("安全守护", SAFETY_QUESTIONS)):
		for prompt, correct, wrong_first, wrong_second in entries:
			add(category, prompt, correct, (wrong_first, wrong_second), family=shared_families.get(prompt, ""))
	for hour in range(1, 13):
		for direction, label in ((1, "过"), (-1, "往前拨")):
			for amount in range(1, 5):
				answer = (hour - 1 + direction * amount) % 12 + 1
				other = (hour - 1 + direction * (amount + 1)) % 12 + 1
				add("时间日历", "钟表%d时，%s%d小时是？" % (hour, label, amount),
					"%d时" % answer, ("%d时" % hour, "%d时" % other))
		next_hour = hour % 12 + 1
		add("时间日历", "%d时30分，过半小时是？" % hour, "%d时整" % next_hour,
			("%d时整" % hour, "%d时30分" % next_hour))
	for index, day in enumerate(days):
		for amount in range(2, 5):
			answer = days[(index + amount) % len(days)]
			other = days[(index + amount + 1) % len(days)]
			add("时间日历", "今天%s，再过%d天是？" % (day, amount), answer, (day, other), family="weekday")
	directions = ("北", "东", "南", "西")
	for index, direction in enumerate(directions):
		for label, offset in (("左转", -1), ("右转", 1), ("转身", 2)):
			answer = directions[(index + offset) % 4]
			wrong = tuple(item for item in directions if item != answer)[:2]
			add("方向空间", "面向%s，%s后面向哪边？" % (direction, label), answer, wrong, family="direction")
		for first_label, first_offset in (("左转", -1), ("右转", 1)):
			for second_label, second_offset in (("左转", -1), ("右转", 1)):
				answer = directions[(index + first_offset + second_offset) % 4]
				wrong = tuple(item for item in directions if item != answer)[:2]
				add("方向空间", "面向%s，先%s再%s，面向哪边？" %
					(direction, first_label, second_label), answer, wrong, family="direction")
		for distance in range(2, 5):
			for back in range(1, distance):
				opposite = directions[(index + 2) % 4]
				add("方向空间", "向%s走%d步，再向%s走%d步，在起点哪边？" %
					(direction, distance, opposite, back), direction,
					(opposite, directions[(index + 1) % 4]), family="direction")
	for horizontal in ("东", "西"):
		for vertical in ("北", "南"):
			answer = horizontal + vertical
			wrong = tuple(item for item in ("东北", "西北", "东南", "西南") if item != answer)[:2]
			for first_steps in range(1, 4):
				for second_steps in range(1, 3):
					add("方向空间", "向%s走%d步，再向%s走%d步，在起点哪边？" %
						(horizontal, first_steps, vertical, second_steps), answer, wrong, family="direction")
	positions = (("左", "右"), ("右", "左"), ("上", "下"), ("下", "上"))
	for first, second in (("书", "水杯"), ("球", "盒子"), ("笔", "橡皮"), ("花", "树"),
						  ("猫", "椅子"), ("灯", "桌子"), ("帽子", "书包"), ("钟", "画")):
		for position, opposite in positions:
			wrong = tuple(item for item, _ in positions if item != opposite)[:2]
			add("方向空间", "%s在%s的%s边，%s在%s的哪边？" %
				(first, second, position, second, first), opposite, wrong, family="direction")
	for names in (("小明", "小红", "小华"), ("小林", "小东", "小雨"), ("小丽", "小刚", "小芳")):
		for first, middle, last in itertools.permutations(names):
			for statement, first_question, last_question in (
				("%s比%s高，%s比%s高", "谁最高？", "谁最矮？"),
				("%s在%s前面，%s在%s前面", "三人中谁最前？", "三人中谁最后？"),
				("%s比%s早到，%s比%s早到", "谁最早到？", "谁最晚到？"),
			):
				prefix = statement % (first, middle, middle, last)
				add("逻辑推理", prefix + "，" + first_question, first, (middle, last))
				add("逻辑推理", prefix + "，" + last_question, last, (first, middle))
	return {category: tuple(questions) for category, questions in bank.items()}


QUESTION_BANK = build_question_bank()


def build_questions(rng, history=None):
	history = history if history is not None else QuestionHistory()
	questions = []
	candidates = (spec for group in QUESTION_BANK.values() for spec in group)
	for spec in history.select(rng, candidates, QUESTIONS_PER_GAME):
		visual = list(spec.visual)
		rng.shuffle(visual)
		if spec.wrong_choices:
			question = make_question(rng, spec.category, spec.prompt, spec.correct, spec.wrong_choices, visual)
		else:
			question = number_question(rng, spec.category, spec.prompt, int(spec.correct), visual)
		questions.append(question)
	rng.shuffle(questions)
	history.save()
	return questions


class BrainGame:
	def __init__(self, rng=None, history=None):
		self.rng = rng if rng is not None else random.Random()
		self.history = history if history is not None else QuestionHistory()
		self.start()

	@property
	def question(self):
		return self.questions[self.index]

	@property
	def scores(self):
		return [sum(record.correct for record in player) for player in self.answers]

	@property
	def times(self):
		return [sum(record.elapsed_centiseconds for record in player) for player in self.answers]

	@property
	def winner(self):
		first = (self.scores[0], -self.times[0])
		second = (self.scores[1], -self.times[1])
		return None if first == second else 0 if first > second else 1

	def start(self):
		self.questions = build_questions(self.rng, self.history)
		self.answers = [[], []]
		self.active_player = 0
		self.index = 0
		self.phase = "ready"
		self.elapsed = 0.0
		self.feedback_elapsed = 0.0
		self.k3_pending = None

	def prepare_question(self):
		self.phase = "answer"
		self.elapsed = 0.0
		self.feedback_elapsed = 0.0

	def finish_answer(self, choice):
		record = AnswerRecord(choice, choice == self.question.answer,
							  round(min(self.elapsed, QUESTION_SECONDS) * 100))
		self.answers[self.active_player].append(record)
		self.phase = "feedback"
		self.feedback_elapsed = 0.0

	def advance(self):
		if self.index + 1 < len(self.questions):
			self.index += 1
			self.prepare_question()
		elif self.active_player == 0:
			self.active_player = 1
			self.index = 0
			self.phase = "ready"
		else:
			self.phase = "finished"

	def handle_action(self, action):
		context = (self.phase, self.active_player, self.index)
		if action == "K3_CANCEL":
			self.k3_pending = None
			return
		if action == "K3_DOWN":
			if self.k3_pending is None:
				self.k3_pending = context
			return
		if action == "K3" and self.k3_pending is not None:
			pending = self.k3_pending
			self.k3_pending = None
			if pending != context:
				return
		if self.phase == "ready" and action == "K3":
			self.prepare_question()
		elif self.phase == "answer" and action in BUTTON_ACTIONS:
			self.finish_answer(BUTTON_ACTIONS.index(action))
		elif self.phase == "finished" and action == "K3":
			self.start()

	def update(self, elapsed):
		elapsed = max(0.0, elapsed)
		if self.phase == "answer":
			if self.k3_pending == (self.phase, self.active_player, self.index):
				return
			self.elapsed = min(QUESTION_SECONDS, self.elapsed + elapsed)
			if self.elapsed >= QUESTION_SECONDS:
				self.finish_answer(None)
		elif self.phase == "feedback":
			self.feedback_elapsed += elapsed
			if self.feedback_elapsed >= FEEDBACK_SECONDS:
				self.advance()


_st = ui_theme.style()  # 全局界面风格
BACKGROUND = _st["bg"]
INK = _st["text"]
MUTED = _st["sub"]
HEADER = _st["hint_bg"]
PAPER = _st["panel"]
LINE = _st["deco"]
GOLD = (246, 191, 67)   # 固定金色(奖励)
PLAYER_COLORS = ((218, 91, 73), (45, 129, 175))
ANSWER_COLORS = ((218, 91, 73), (50, 151, 137), (72, 131, 190))
CATEGORY_COLORS = {
	"算一算": (219, 111, 76),
	"找规律": (153, 111, 177),
	"看图形": (43, 146, 151),
	"小常识": (92, 151, 96),
	"动脑筋": (192, 139, 54),
	"词语乐园": (151, 92, 116),
	"时间日历": (50, 124, 160),
	"方向空间": (180, 107, 54),
	"逻辑推理": (128, 99, 164),
	"科学发现": (46, 135, 109),
	"自然地理": (58, 122, 160),
	"安全守护": (188, 87, 78),
}


def draw_star(screen, center, radius, color):
	points = []
	for index in range(10):
		angle = -math.pi / 2 + index * math.pi / 5
		distance = radius if index % 2 == 0 else radius * 0.46
		points.append((round(center[0] + math.cos(angle) * distance),
					   round(center[1] + math.sin(angle) * distance)))
	pygame.draw.polygon(screen, color, points)


def format_time(centiseconds):
	seconds, fraction = divmod(centiseconds, 100)
	return "%d.%02d" % (seconds, fraction)


class BrainDisplay:
	def __init__(self, screen):
		self.screen = screen
		self.width, self.height = screen.get_size()
		self.portrait = self.height > self.width
		self.title_font = spi_lcd.load_font(20)
		self.heading_font = spi_lcd.load_font(19)
		self.prompt_fonts = [spi_lcd.load_font(size) for size in (28, 24, 21, 19, 17, 15, 13, 11)]
		self.option_fonts = [spi_lcd.load_font(size) for size in (18, 16, 15, 14, 13, 12, 11, 10, 9)]
		self.small_font = spi_lcd.load_font(12)
		self.status_font = spi_lcd.load_font(13)
		self.button_font = spi_lcd.load_font(13)
		self.number_font = spi_lcd.load_font(15)
		score_width = (self.width - 76) // 2
		self.scores = (pygame.Rect(9, 35, score_width, 24),
					   pygame.Rect(self.width - score_width - 9, 35, score_width, 24))
		margin, gap, button_height = 7, 5, 26
		button_width = (self.width - margin * 2 - gap * 2) // 3
		self.buttons = [pygame.Rect(margin + index * (button_width + gap),
									self.height - button_height - 6, button_width, button_height)
						for index in range(3)]
		if self.portrait:
			self.category_y = 65
			self.prompt_rect = pygame.Rect(10, 84, self.width - 20, 42)
			self.visual_rect = pygame.Rect(10, 128, self.width - 20, 27)
			self.options = [pygame.Rect(9, 158 + index * 35, self.width - 18, 31)
							for index in range(3)]
			self.status_y = 272
		else:
			self.category_y = 61
			self.prompt_rect = pygame.Rect(10, 79, 150, 55)
			self.visual_rect = pygame.Rect(10, 137, 150, 33)
			self.options = [pygame.Rect(174, 64 + index * 37, self.width - 184, 32)
							for index in range(3)]
			self.status_y = 187

	def centered(self, value, font, color, center):
		image = font.render(value, True, color)
		rect = image.get_rect(center=center)
		self.screen.blit(image, rect)
		return rect

	def draw_header(self, game):
		pygame.draw.rect(self.screen, HEADER, (0, 0, self.width, 31))
		self.screen.blit(self.title_font.render("头脑挑战", True, ui_theme.readable(HEADER)), (10, 4))
		label = "%d / %d" % (game.index + 1, len(game.questions)) if game.phase in ("answer", "feedback") else "10题"
		badge = pygame.Rect(self.width - 60, 5, 51, 21)
		pygame.draw.rect(self.screen, GOLD, badge, border_radius=5)
		self.centered(label, self.small_font, ui_theme.pick(GOLD, INK), badge.center)
		for index, rect in enumerate(self.scores):
			pygame.draw.rect(self.screen, PLAYER_COLORS[index], rect, border_radius=6)
			if game.active_player == index and game.phase in ("ready", "answer", "feedback"):
				pygame.draw.rect(self.screen, GOLD, rect, 2, border_radius=6)
			self.centered("玩家%d" % (index + 1), self.status_font,
						  ui_theme.readable(PLAYER_COLORS[index]), rect.center)
		if game.phase == "answer":
			remaining = max(0, math.ceil(QUESTION_SECONDS - game.elapsed))
			color = PLAYER_COLORS[0] if remaining <= 5 else HEADER
			pygame.draw.circle(self.screen, color, (self.width // 2, 47), 13)
			self.centered(str(remaining), self.number_font, ui_theme.readable(color), (self.width // 2, 47))
		else:
			self.centered("VS", self.small_font, MUTED, (self.width // 2, 47))

	def draw_prompt(self, question):
		color = CATEGORY_COLORS[question.category]
		image = self.small_font.render(question.category, True, PAPER)
		badge = image.get_rect(topleft=(15, self.category_y + 3)).inflate(10, 6)
		pygame.draw.rect(self.screen, color, badge, border_radius=4)
		self.screen.blit(image, image.get_rect(center=badge.center))
		prompt_rect = self.prompt_rect if question.visual else self.prompt_rect.union(self.visual_rect)
		for font in self.prompt_fonts:
			width = prompt_rect.width - font.size("？")[0]
			lines = wrap_text(question.prompt, font, width)
			if (len(lines) * font.get_linesize() <= prompt_rect.height and
					all(font.size(line)[0] <= prompt_rect.width for line in lines) and
					all(not line.startswith(("，", "。", "？", "！", "、")) for line in lines)):
				break
		top = prompt_rect.y + (prompt_rect.height - len(lines) * font.get_linesize()) // 2
		for index, line in enumerate(lines):
			image = font.render(line, True, INK)
			rect = image.get_rect(centerx=prompt_rect.centerx, top=top + index * font.get_linesize())
			self.screen.blit(image, rect)
		if question.visual:
			self.draw_visual(question.visual)

	def draw_visual(self, visual):
		columns = min(len(visual), 9 if self.portrait else 5)
		rows = math.ceil(len(visual) / columns)
		spacing = min(24, self.visual_rect.width // columns)
		for index, shape in enumerate(visual):
			row, column = divmod(index, columns)
			row_count = min(columns, len(visual) - row * columns)
			x = self.visual_rect.centerx + round((column - (row_count - 1) / 2) * spacing)
			y = self.visual_rect.centery + round((row - (rows - 1) / 2) * 15)
			if shape == "star":
				draw_star(self.screen, (x, y), 7, (238, 171, 49))
			elif shape == "circle":
				pygame.draw.circle(self.screen, (80, 174, 175), (x, y), 6)
			elif shape == "triangle":
				pygame.draw.polygon(self.screen, (224, 108, 91),
									((x, y - 7), (x - 7, y + 6), (x + 7, y + 6)))
			elif shape == "square":
				pygame.draw.rect(self.screen, (91, 137, 196), (x - 6, y - 6, 13, 13), border_radius=2)

	def layout_option(self, value, rect):
		for font in self.option_fonts:
			lines = wrap_text(value, font, rect.width - 40)
			if (len(lines) * font.get_linesize() <= rect.height - 4 and
					all(font.size(line)[0] <= rect.width - 40 for line in lines)):
				return font, lines
		return font, lines

	def draw_options(self, game):
		for index, rect in enumerate(self.options):
			selected = game.phase == "feedback" and game.answers[game.active_player][-1].choice == index
			fill = (255, 242, 197) if selected else PAPER
			pygame.draw.rect(self.screen, fill, rect, border_radius=5)
			pygame.draw.rect(self.screen, LINE, rect, 1, border_radius=5)
			badge_center = (rect.x + 17, rect.centery)
			pygame.draw.circle(self.screen, ANSWER_COLORS[index], badge_center, 10)
			self.centered(str(index + 1), self.number_font,
						  ui_theme.readable(ANSWER_COLORS[index]), badge_center)
			font, lines = self.layout_option(game.question.choices[index], rect)
			top = rect.centery - len(lines) * font.get_linesize() // 2
			for line_index, line in enumerate(lines):
				text = font.render(line, True, ui_theme.pick(fill, INK))
				self.screen.blit(text, (rect.x + 34, top + line_index * font.get_linesize()))

	def status(self, game):
		if game.phase == "answer":
			remaining = max(0, math.ceil(QUESTION_SECONDS - game.elapsed))
			return "剩余 %d秒  用时 %s秒" % (remaining, format_time(round(game.elapsed * 100)))
		record = game.answers[game.active_player][-1]
		label = "超时" if record.choice is None else "已记录"
		return "%s  %s秒" % (label, format_time(record.elapsed_centiseconds))

	def draw_ready(self, game):
		center_x = self.width // 2
		heading_y = 103 if self.portrait else 80
		clock_y = 169 if self.portrait else 132
		self.centered("玩家%d，请准备" % (game.active_player + 1), self.heading_font,
					  PLAYER_COLORS[game.active_player], (center_x, heading_y))
		pygame.draw.circle(self.screen, LINE, (center_x, clock_y), 32, 4)
		pygame.draw.circle(self.screen, PAPER, (center_x, clock_y), 25)
		self.centered("%d" % QUESTION_SECONDS, self.heading_font, ui_theme.pick(PAPER, MUTED), (center_x, clock_y))
		self.centered("每题限时 %d 秒" % QUESTION_SECONDS, self.status_font, MUTED,
					  (center_x, 229 if self.portrait else 181))

	def draw_finished(self, game):
		winner = game.winner
		message = "平局！" if winner is None else "玩家%d 获胜！" % (winner + 1)
		self.centered("比赛结果", self.heading_font, INK,
					  (self.width // 2, 77 if self.portrait else 75))
		self.centered(message, self.heading_font, INK,
					  (self.width // 2, 105 if self.portrait else 98))
		width = (self.width - 30) // 2
		for index in range(2):
			rect = pygame.Rect(10 + index * (width + 10), 127 if self.portrait else 113,
							   width, 119 if self.portrait else 76)
			pygame.draw.rect(self.screen, PAPER, rect, border_radius=6)
			pygame.draw.rect(self.screen, PLAYER_COLORS[index], rect, 2, border_radius=6)
			if self.portrait:
				positions = (rect.y + 17, rect.y + 46, rect.y + 72, rect.y + 99)
			else:
				positions = (rect.y + 12, rect.y + 29, rect.y + 46, rect.y + 62)
			self.centered("玩家%d" % (index + 1), self.status_font, PLAYER_COLORS[index],
						  (rect.centerx, positions[0]))
			percent = round(game.scores[index] * 100 / len(game.questions))
			self.centered("正确率 %d%%" % percent, self.status_font, INK, (rect.centerx, positions[1]))
			self.centered("答对 %d / %d" % (game.scores[index], len(game.questions)),
						  self.small_font, MUTED, (rect.centerx, positions[2]))
			self.centered("用时 %s秒" % format_time(game.times[index]),
						  self.status_font, INK, (rect.centerx, positions[3]))
		if winner is None:
			reason = "正确率和用时相同"
		elif game.scores[0] == game.scores[1]:
			reason = "正确率相同，用时更短"
		else:
			reason = "正确率更高"
		self.centered(reason, self.small_font, MUTED,
					  (self.width // 2, 265 if self.portrait else 197))

	def draw_buttons(self, game):
		if game.phase == "answer":
			labels = ("选1", "选2", "选3")
			enabled = (True, True, True)
		elif game.phase == "ready":
			labels = ("选1", "选2", "开始")
			enabled = (False, False, True)
		elif game.phase == "finished":
			labels = ("选1", "选2", "再玩")
			enabled = (False, False, True)
		else:
			labels = ("选1", "选2", "选3")
			enabled = (False, False, False)
		for index, rect in enumerate(self.buttons):
			color = ANSWER_COLORS[index] if enabled[index] else (214, 225, 219)
			text_color = ui_theme.readable(ANSWER_COLORS[index]) if enabled[index] else (83, 92, 89)
			pygame.draw.rect(self.screen, color, rect, border_radius=5)
			self.centered(labels[index], self.button_font, text_color, rect.center)

	def draw(self, game):
		self.screen.fill(BACKGROUND)
		self.draw_header(game)
		if game.phase == "finished":
			self.draw_finished(game)
		elif game.phase == "ready":
			self.draw_ready(game)
		else:
			self.draw_prompt(game.question)
			self.draw_options(game)
			self.centered(self.status(game), self.status_font, INK, (self.width // 2, self.status_y))
		self.draw_buttons(game)


class TimedGPIOButtons(GPIOButtons):
	def poll(self):
		was_down = self.states["K3"]["down"]
		actions = super().poll()
		if not was_down and self.states["K3"]["down"]:
			actions.append("K3_DOWN")
		return actions


def action_from_event(event, display, game):
	action = event_action(event, display)
	if action is not None:
		return action
	if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
		window = pygame.display.get_surface()
		if window is not None:
			position = (event.pos[0] * display.width / window.get_width(),
						event.pos[1] * display.height / window.get_height())
			if game.phase == "answer":
				for index, rect in enumerate(display.options):
					if rect.collidepoint(position):
						return BUTTON_ACTIONS[index]
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
		if not spi_lcd.is_simulate():
			try:
				gpio = importlib.import_module("RPi.GPIO")
				buttons = TimedGPIOButtons(gpio)
			except Exception as error:
				raise RuntimeError("GPIO 初始化失败，请检查 RPi.GPIO 和按键连接。") from error
		else:
			pygame.display.set_caption("头脑挑战")
		display = BrainDisplay(screen)
		game = BrainGame(history=QuestionHistory(default_history_path()))
		hold = spi_lcd.SimulatedHold("K3", "QUIT", wheel_support.QUIT_HOLD_SECONDS)
		clock = pygame.time.Clock()
		running = True
		exit_hint = "按 Esc 退出" if buttons is None else "长按 K3 退出"
		print("头脑挑战已启动：两人轮流答题，K3 开始，K1、K2、K3 选择答案；%s。" % exit_hint)
		while running:
			elapsed = clock.tick(30) / 1000.0
			previous_phase = game.phase
			game.update(elapsed)
			accept_input = game.phase == previous_phase
			if buttons is None:
				actions = []
				for event in pygame.event.get():
					action = action_from_event(event, display, game)
					if event.type == pygame.WINDOWFOCUSLOST and hold.source is not None:
						actions.append("K3_CANCEL")
					if action == "K3" and hold.source is None:
						actions.append("K3_DOWN")
					actions.append(hold.process_event(event, action))
				actions.append(hold.poll())
			else:
				actions = buttons.poll()
			for action in actions:
				if action == "QUIT":
					running = False
					break
				if accept_input:
					previous_phase = game.phase
					game.handle_action(action)
					accept_input = game.phase == previous_phase
				elif action == "K3_DOWN":
					game.k3_pending = (None, None, None)
				elif action in ("K3", "K3_CANCEL"):
					game.k3_pending = None
			if not running:
				break
			display.draw(game)
			present_frame(screen)
	finally:
		if buttons is not None:
			buttons.cleanup()
		pygame.quit()


if __name__ == "__main__":
	main()
