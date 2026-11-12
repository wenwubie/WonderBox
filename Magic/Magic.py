"""SPI LCD 塔罗占卜屋，显示与按键约定复用 common/spi_lcd.py。"""
import os
import math
import random
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(BASE_DIR))
from common import spi_lcd

if spi_lcd.is_simulate():
	spi_lcd.WINDOW_SCALE = 2

if "--landscape" in sys.argv:
	os.environ["POKEMON_PORTRAIT"] = "0"
elif spi_lcd.is_simulate() and "POKEMON_PORTRAIT" not in os.environ:
	os.environ["POKEMON_PORTRAIT"] = "1"

screen = spi_lcd.init()
import pygame  # noqa: E402

WIDTH, HEIGHT = screen.get_size()
PORTRAIT = HEIGHT > WIDTH

BG = (255, 246, 248)
INK = (83, 53, 78)
MUTED = (151, 124, 145)
PINK = (238, 137, 172)
PINK_DARK = (192, 93, 139)
LILAC = (190, 174, 226)
MINT = (157, 211, 194)
GOLD = (232, 190, 104)
PANEL = (255, 253, 250)
LINE = (242, 222, 230)
MYSTIC_BG = (18, 15, 31)
MYSTIC_PANEL = (38, 29, 52)
MYSTIC_INNER = (27, 22, 43)
MYSTIC_LINE = (113, 91, 145)
MYSTIC_GOLD = (224, 188, 120)
MYSTIC_TEXT = (245, 231, 211)
MYSTIC_MUTED = (177, 161, 190)

font_title = spi_lcd.load_font(21 if WIDTH >= 300 else 19)
font_heading = spi_lcd.load_font(17)
font_body = spi_lcd.load_font(14 if WIDTH >= 300 else 13)
font_small = spi_lcd.load_font(11 if WIDTH >= 300 else 10)

MODES = ["今日运势", "星座查询", "情感预测"]
MODE_HINTS = ["抽一张今日指引", "探索星座小档案", "看看近期桃花能量"]
TOPICS = ["性格", "感情", "事业", "关系", "天赋"]
SPIN_DURATION = 7.0
SPIN_SETTLE_SECONDS = 0.25
LOVE_PAGE_COUNT = 2
LOVE_SECTIONS_PER_PAGE = 2

TAROT = [
	("愚者", "新的开始",
	 "工作学习：今天若有新任务，先问清交付内容和期限。\n人际生活：收到新邀约时，先确认时间和地点。\n行动建议：选一道新菜或新路线，今天尝试一次。",
	 "近期：新活动或朋友聚会可能带来心动，先轻松聊天，看看彼此是否愿意继续联系。\n单身：从共同兴趣聊起，合适时邀约喝咖啡；对方犹豫时，也尊重彼此节奏。\n有伴：一起尝试新餐厅或新活动，提前商量时间和花费，让新鲜感不变成压力。\n相处提醒：心动之外也留意对方是否守约、愿意倾听；感到不舒服时直接说出来。", 72),
	("魔术师", "行动力",
	 "工作学习：今天可能有展示机会，先准备三句重点。\n人际生活：需要配合时，发消息说明任务和期限。\n行动建议：选一件拖着的事，今天完成第一步。",
	 "近期：一段聊天可能因主动邀约变得亲近，观察对方是否也愿意继续交流。\n单身：先聊共同兴趣，再邀请对方喝饮料或散步；对方犹豫时尊重选择。\n有伴：想见面或需要陪伴时直接提出，约好时间，别等对方猜你在想什么。\n相处提醒：表达好感要真诚，别用夸大承诺换取回应；说到的事尽量做到。", 78),
	("女祭司", "倾听直觉",
	 "工作学习：今天收到的新信息先核对来源和日期。\n人际生活：对方回复简短时，先问清意思再判断。\n行动建议：把一个疑问写下来，今天找人确认。",
	 "近期：彼此可能还在观察，消息回复慢不等于拒绝，不必急着定义关系。\n单身：先聊生活习惯和兴趣，留意双方交流是否自在，再决定要不要见面。\n有伴：挑一个安静时间说出心事，也给对方思考空间，不必逼着立刻回答。\n相处提醒：含糊的话可以温和确认，不查手机、不用冷淡试探来寻找安全感。", 64),
	("女皇", "丰盛滋养",
	 "工作学习：今天整理桌面或资料，先处理常用的一项。\n人际生活：给今天要见的人发一句问候或感谢。\n行动建议：给自己安排一顿饭，吃饭时暂放手机。",
	 "近期：温柔而稳定的关心容易让关系升温，比刻意讨好更让人放松。\n单身：接受让自己安心的邀约，观察对方是否也会照顾你的感受。\n有伴：安排一顿饭或一次散步，聊聊最近有什么需要彼此支持的事。\n相处提醒：付出也需要回应；感到疲惫时说出需要，不必用照顾换取爱。", 86),
	("皇帝", "稳步前行",
	 "工作学习：今天事情较多时，先写下最重要的三项。\n人际生活：安排任务前，先和对方确认能否配合。\n行动建议：给第一项任务定个结束时间，先完成它。",
	 "近期：关系更看重稳定和可靠，一次守时赴约可能比漂亮的话更有分量。\n单身：留意对方是否兑现小约定，感觉合适再商量下一次见面。\n有伴：一起谈谈见面频率或生活分工，先听对方想法再做安排。\n相处提醒：可靠不等于替对方做主，涉及双方的决定要取得彼此同意。", 67),
	("教皇", "经验指引",
	 "工作学习：今天遇到不懂的问题，先查资料再请教。\n人际生活：听到建议时，问清对方经历过什么。\n行动建议：把一个具体疑问发给熟悉这件事的人。",
	 "近期：感情可能谈到生活方式和未来期待，先了解彼此看法，不必急着求一致。\n单身：朋友介绍时先聊兴趣和节奏，不因别人催促就匆忙确定关系。\n有伴：挑一个具体话题，如假期安排，听听双方期待，再一起做决定。\n相处提醒：亲友意见仅供参考，是否合适还要看你们的感受和实际相处。", 62),
	("恋人", "真心选择",
	 "工作学习：今天若要二选一，列出各自一条利弊。\n人际生活：有人征求意见时，直接说出真实想法。\n行动建议：今天给一件犹豫的事答复，别替人做主。",
	 "近期：可能出现心动或关系选择，先分清好感与真正愿意投入的程度。\n单身：想进一步认识时，可以明确邀约，也给对方自由拒绝的空间。\n有伴：说清彼此想要的陪伴方式，遇到分歧一起商量，不用靠猜。\n相处提醒：不必为了留住谁牺牲底线；彼此尊重和自在比表面热闹更重要。", 94),
	("战车", "专注突破",
	 "工作学习：今天先处理截止最近的一项，避免分心。\n人际生活：临时改计划时，提前告知受影响的人。\n行动建议：关掉消息提醒25分钟，专心完成一步。",
	 "近期：一次主动联系可能让关系向前，但双方的节奏未必完全一致。\n单身：主动邀请一次见面并确认意愿，对方没空就尊重，不连续催问。\n有伴：一起定一个近期约会计划，商量如何准备，也留出各自安排。\n相处提醒：主动和催促不同；发现对方有压力时，停下来问问真实感受。", 81),
	("力量", "柔软坚定",
	 "工作学习：遇到难题先拆出一步，今天只做这一项。\n人际生活：今天若有争执，先暂停两分钟再回复。\n行动建议：累了就离开屏幕，喝水并活动五分钟。",
	 "近期：小误会可能需要耐心化解，温和说明感受比争辩对错更有帮助。\n单身：表达好感时保持真实，不必为了获得回应改变自己的喜好。\n有伴：争执先暂停，等双方平静后各说一件在意的事，再一起找办法。\n相处提醒：温柔不等于忍耐伤害；界限被反复忽视时，寻求信任的人支持。", 77),
	("隐者", "留白沉淀",
	 "工作学习：今天留出半小时，处理一件需要专注的事。\n人际生活：暂时不想聊天时，告知对方晚点再回。\n行动建议：睡前花十分钟整理桌面或随身物品。",
	 "近期：感情节奏可能放慢，暂时没有进展也不代表以后没有机会。\n单身：想休息就不用勉强社交；遇到感兴趣的人，可先从朋友聊起。\n有伴：需要独处时说明原因，约好再联系的时间，避免对方误解。\n相处提醒：留空间和失联不同；说清自己的节奏，也询问对方的需要。", 49),
	("命运之轮", "拥抱变化",
	 "工作学习：今天可能临时调整安排，先确认新截止时间。\n人际生活：邀约有变动时，先问清新的时间地点。\n行动建议：出门前查天气和路线，备一个替代方案。",
	 "近期：生活节奏或邀约变化，可能让你与不同的人重新产生交集。\n单身：接受舒适的活动邀请，先聊兴趣，不把一次偶遇当成注定。\n有伴：计划变动时一起调整，讨论替代方案，给彼此留些弹性。\n相处提醒：缘分不是承诺；观察持续的关心和行动，比依赖巧合可靠。", 83),
	("正义", "平衡诚实",
	 "工作学习：今天提交文件前，核对数字、日期和收件人。\n人际生活：涉及费用分摊时，先讲清金额和方式。\n行动建议：今天回复一个待确认事项，留好沟通记录。",
	 "近期：双方投入和边界可能成为焦点，清楚沟通比默默计较更有帮助。\n单身：留意对方说到的事是否做到，也主动说明自己想要的相处方式。\n有伴：聊聊约会花费、时间分配或家务，找双方都能接受的办法。\n相处提醒：公平不是逐项计较；不舒服就具体说，别替对方猜答案。", 65),
	("倒吊人", "换个角度",
	 "工作学习：事情卡住时，今天换一种方法试十分钟。\n人际生活：意见不同时，先复述对方观点再表达。\n行动建议：暂停卡住的事，今天先完成另一件小事。",
	 "近期：关系可能进展较慢，等待之余也要看双方是否都愿意投入。\n单身：对方回应含糊时，可以礼貌问清意愿；没有回应就把注意力放回自己。\n有伴：僵持的问题先听对方解释，再找一个双方愿意尝试的小改变。\n相处提醒：给彼此时间不是无限期等待，要明确自己的需求和能接受的界限。", 55),
	("死神", "更新蜕变",
	 "工作学习：今天收尾一项旧任务，确认是否还缺交付。\n人际生活：不想继续的邀约，今天礼貌说清原因。\n行动建议：清理一件闲置物品，为今天腾出空间。",
	 "近期：旧的相处习惯可能需要调整，这张牌不代表一定分手或失去。\n单身：想起旧人时先想清是怀念还是想重新联系，确认边界再决定。\n有伴：把反复争吵的具体做法说出来，一起商量可尝试的新方式。\n相处提醒：改变需要双方同意；不想继续的关系，可以清楚而尊重地告别。", 59),
	("节制", "温和平衡",
	 "工作学习：今天把任务分成两段，中间休息五分钟。\n人际生活：讨论安排时，给对方两个可选时间。\n行动建议：今天按时吃一餐，随手准备一杯水。",
	 "近期：关系适合循序渐进，稳定的关心比忽冷忽热更容易建立信任。\n单身：按舒服的频率聊天和见面，不因旁人进度而催促自己。\n有伴：安排一次轻松约会，也保留各自的朋友、兴趣和独处时间。\n相处提醒：不要只靠一方迁就；定期问问彼此的感受和相处节奏。", 73),
	("恶魔", "看见牵绊",
	 "工作学习：今天处理重要任务前，先把手机调静音。\n人际生活：被要求帮忙时，先看自己是否有空。\n行动建议：今天想买非必需品，先放购物车再比较。",
	 "近期：强烈心动可能让人忽略不舒服的细节，先看相处是否让你安心。\n单身：对方过度催促或越过界限时，可以放慢并向信任的人聊聊。\n有伴：若反复因控制或猜疑争执，先说清界限，必要时寻求支持。\n相处提醒：喜欢不需要以失去自由为代价；拒绝不舒服的要求是你的权利。", 51),
	("高塔", "重整结构",
	 "工作学习：今天计划有变时，先确认什么必须按时完成。\n人际生活：突发争执时，先暂停对话再约时间沟通。\n行动建议：出门前检查电量，重要文件顺手备份。",
	 "近期：某个分歧可能被放大，但一次争执不等于关系注定结束。\n单身：对方言行反差大时，先保持距离、确认事实，不必急着投入。\n有伴：情绪激动时暂停讨论，约好平静后再谈具体问题和改变。\n相处提醒：争吵中若感到不安全，优先离开现场并联系信任的人。", 46),
	("星星", "希望回归",
	 "工作学习：今天试着重启一项卡住的事，先做十分钟。\n人际生活：给一位朋友发近况，问问对方过得如何。\n行动建议：今天记下一件已有的小进展，给自己肯定。",
	 "近期：轻松而真诚的互动，有助于慢慢恢复对感情的期待。\n单身：选择让自己舒服的社交方式，认识新人时不必拿过去比较。\n有伴：互相分享一件欣赏对方的事，也谈谈希望得到的支持。\n相处提醒：对未来抱有期待，也关注眼前的行动；信任需要慢慢建立。", 89),
	("月亮", "照见情绪",
	 "工作学习：今天遇到不确定的消息，先核实来源和时间。\n人际生活：对方语气让你困惑时，直接问一句确认。\n行动建议：今天做决定前写下已知事实，别急着猜。",
	 "近期：暧昧或回复变少可能让人多想，先确认事实，不急着猜结果。\n单身：对关系有疑问时，可以温和询问对方想法，观察是否愿意沟通。\n有伴：说清让你不安的具体事情，听听对方解释，避免冷淡试探。\n相处提醒：感受值得重视，但不等于事实；重要判断先听双方怎么说。", 58),
	("太阳", "明朗喜悦",
	 "工作学习：今天适合汇报小进展，顺便确认下一步。\n人际生活：给朋友分享一件开心事，或约一次散步。\n行动建议：今天听一首喜欢的歌，给自己一点放松。",
	 "近期：轻松的相处可能增进好感，适合一起做双方都喜欢的事。\n单身：参加感兴趣的活动，自然聊天，看看对方是否也愿意了解你。\n有伴：一起散步或吃顿饭，分享最近开心的事，也表达具体的感谢。\n相处提醒：快乐不必强撑；有烦恼也可以说，给彼此真实回应。", 96),
	("审判", "重新出发",
	 "工作学习：今天翻看一项旧记录，找出可以改进的地方。\n人际生活：有误会的话，今天发消息约个时间说清。\n行动建议：今天重试一道做错的题，或补完一件小事。",
	 "近期：旧人或未谈完的话题可能再次出现，先想清自己真正的期待。\n单身：考虑联系旧人时，回顾过去的问题是否改变，也尊重对方选择。\n有伴：选个平静时间回顾一次分歧，讨论以后怎样处理类似情况。\n相处提醒：重新开始不等于忽略旧问题；持续改变比一句承诺更重要。", 75),
	("世界", "圆满收获",
	 "工作学习：今天收尾一件事，检查是否还有遗漏。\n人际生活：给今天帮助过你的人发一句感谢。\n行动建议：完成后整理桌面，给自己十分钟休息。",
	 "近期：稳定相处可能让你更清楚双方是否合拍，适合确认共同期待。\n单身：先想好希望的关系和底线，再选择适合自己的认识方式。\n有伴：回顾近期一起完成的小事，聊聊下一次想共同体验什么。\n相处提醒：亲密和独立可以并存，欣赏默契的同时也照顾自己的生活。", 91),
]

DAILY_CARD_NAMES = {
	"愚者": "启程之门", "魔术师": "灵感火种", "女祭司": "静夜之声",
	"女皇": "丰收花园", "皇帝": "秩序之石", "教皇": "智者灯塔",
	"恋人": "抉择天平", "战车": "勇进之帆", "力量": "内心之光",
	"隐者": "宁静小径", "命运之轮": "转机之环", "正义": "公正之镜",
	"倒吊人": "暂停时刻", "死神": "蜕变之叶", "节制": "平衡之水",
	"恶魔": "清醒之钥", "高塔": "重整之锚", "星星": "希望星光",
	"月亮": "月夜之镜", "太阳": "晴日之光", "审判": "回响之钟",
	"世界": "圆满花环",
}

DAILY_CARDS = [(DAILY_CARD_NAMES[card[0]], card[1], card[2])
				   for card in TAROT if card[0] in DAILY_CARD_NAMES] + [
	("晨露初晴", "清新整理",
	 "工作学习：今天先处理一件十分钟内能完成的小事。\n人际生活：给想联系的人发一句问候，不必等完美时机。\n行动建议：打开窗透气，整理桌面的一小块地方。"),
	("幸运微光", "留意机会",
	 "工作学习：今天留意新的通知，先确认要求和期限。\n人际生活：听到有用的信息时，可以向对方多问一句。\n行动建议：记下一个感兴趣的机会，抽空核实细节。"),
	("同行之桥", "协作互助",
	 "工作学习：今天遇到难题时，找同事或同学交换思路。\n人际生活：问问身边的人是否需要帮助，也说清你的时间。\n行动建议：选一件能一起完成的小事，商量好分工。"),
	("小憩时分", "放慢节奏",
	 "工作学习：今天安排任务时，留出一段缓冲时间。\n人际生活：不想马上答复时，可以告诉对方稍后回复。\n行动建议：离开屏幕活动五分钟，喝水并放松肩膀。"),
	("专注之窗", "减少干扰",
	 "工作学习：今天先列出一个重点，暂时关闭无关提醒。\n人际生活：需要专注时，提前告诉身边的人你的安排。\n行动建议：给自己二十五分钟，完成一件事的第一步。"),
	("细雨归心", "照顾情绪",
	 "工作学习：今天状态不佳时，先处理简单明确的任务。\n人际生活：感到烦躁时，告诉信任的人你需要一点空间。\n行动建议：写下此刻的感受，安排一件让自己放松的小事。"),
	("谨慎之铃", "核实细节",
	 "工作学习：今天提交内容前，再看一遍时间和附件。\n人际生活：转发消息前确认来源，拿不准就先问清楚。\n行动建议：检查一次钥匙、手机和出门需要的物品。"),
	("创意纸鸢", "灵感尝试",
	 "工作学习：今天遇到难题，可以先试一个不同的方法。\n人际生活：分享一个新点子，也听听别人有什么想法。\n行动建议：记录一个灵感，花十分钟尝试它的第一步。"),
	("生活星愿", "点亮日常",
	 "工作学习：今天完成一项任务后，记下自己的小进展。\n人际生活：和熟悉的人分享一件让你开心的事。\n行动建议：留十分钟给喜欢的音乐、散步或其他小爱好。"),
]


def rounded(rect, color, radius=9, border=0, border_color=None):
	pygame.draw.rect(screen, color, rect, border_radius=radius)
	if border and border_color:
		pygame.draw.rect(screen, border_color, rect, border, border_radius=radius)


def centered(text, font, color, y):
	image = font.render(text, True, color)
	screen.blit(image, ((WIDTH - image.get_width()) // 2, y))


def wrap_lines(text, font, max_width):
	lines, line = [], ""
	for char in text:
		if line and font.size(line + char)[0] > max_width:
			if char in "，。！？、；：）》】」』":
				lines.append(line + char)
				line = ""
				continue
			lines.append(line)
			line = char
		else:
			line += char
	if line:
		lines.append(line)
	return lines


def draw_wrapped(text, x, y, max_width, font=font_body, color=INK, line_gap=4, max_lines=None):
	lines = wrap_lines(text, font, max_width)
	if max_lines is not None:
		lines = lines[:max_lines]
	for line in lines:
		screen.blit(font.render(line, True, color), (x, y))
		y += font.get_linesize() + line_gap
	return y


ZODIAC = [
	("白羊座", "03.21-04.19",
	 "你热情坦率，对感兴趣的事常愿意先行动；遇到挑战时，你的勇气也能鼓舞身边的人。你重视自主和效率，但着急时可能忽略细节，或让直话显得太冲。决定前停一停，确认目标和他人的想法，行动会更稳。",
	 "你倾向于直接表达好感，喜欢有活力、有回应的相处，也愿意为重视的人主动付出。单身时可以从共同活动了解彼此，不必急着确认关系。有伴时，别把不同意见当成拒绝；先听完对方的感受，再商量各自需要的空间。",
	 "你面对新任务有冲劲，适合在需要开局、尝试和快速响应的事情上发挥。你的决断能推动进度，但赶时间时容易低估准备和收尾。开始前列出目标与期限，完成后请伙伴帮你检查细节，也记得分享功劳。",
	 "你交朋友时热情直接，朋友有困难时常愿意主动帮忙。直率是优点，但话说得太快可能让人感到被催促，先听清对方需要什么。\n合拍：狮子、射手。共同的热情和探索欲容易带来话题，也要轮流决定。\n需磨合：巨蟹、摩羯。细心和规划能补足你的冲劲；节奏可能不同，先沟通感受和期限。",
	 "你擅长迈出第一步，在不确定的情况下也愿意尝试。启动活动、提出初步方案或鼓励伙伴行动时，这份魄力很有价值。留意别把速度当成唯一标准：给自己设一个检查点，让热情和耐心一起发挥作用。"),
	("金牛座", "04.20-05.20",
	 "你看重稳定和生活中的踏实感，愿意耐心经营喜欢的人与事。你的可靠和坚持让计划有机会慢慢开花；但面对突发变化，你可能更想守住熟悉的方式。先弄清变化的影响，再试一个小调整，不必勉强自己立刻适应。",
	 "你重视信任、陪伴和说到做到，常用实际行动表达关心。单身时慢慢观察对方是否尊重你的节奏；有伴时，除了照顾日常，也可以说出自己的期待。安全感不等于控制，给彼此留些选择和独处的空间。",
	 "你擅长持续投入，重视品质、资源和可执行的步骤，适合负责需要耐心积累的任务。坚持能带来稳定成果，但不愿调整旧方法时可能错过更省力的选择。先小范围试验新方案，再根据结果决定是否推广。",
	 "你重视守信，朋友遇到难题时，你往往会提供实际帮助。只是坚持自己的安排时，也别忽略别人对变化和自由的需要。\n合拍：处女、摩羯。你们常欣赏可靠和务实，也可以给计划留些弹性。\n需磨合：狮子、水瓶。热情和新点子能带来启发；变化的节奏可能不同，先谈好安排。",
	 "你有把想法做成具体成果的耐心，也善于发现品质和舒适度上的细节。预算整理、长期练习或打磨作品时，你的稳定投入很有帮助。遇到瓶颈时，不妨请人提供新视角，再决定哪些部分值得坚持。"),
	("双子座", "05.21-06.20",
	 "你好奇、善于交流，常能很快接触新信息，并从不同角度理解一件事。灵活让你适应变化，也可能让你同时追逐太多想法。兴趣转移或选择困难时，先写下最重要的一件事，给它一个完成时间。",
	 "你容易被有趣的对话和共同探索吸引，也希望关系里保有新鲜感。单身时不妨多了解对方的习惯和期待；有伴时，除了分享新发现，也要回应对方的情绪。计划改变时提前说明，能让你的自由和可靠并存。",
	 "你善于搜集信息、表达观点和连接不同的人，适合需要沟通或尝试新方法的任务。点子多是优势，但同时开太多项目会分散精力。把灵感记下来，先完成一项可交付的成果，再安排下一项。",
	 "你容易打开话题，能让不同圈子的人加入交流。熟络之外也要留意倾听和守住隐私，答应朋友的事记得跟进。\n合拍：天秤、水瓶。你们容易在交流和新观点中找到乐趣，也要留心实际行动。\n需磨合：处女、双鱼。细致与共情能补充你的点子；关注点可能不同，先确认对方的感受。",
	 "你擅长把零散的信息串成新想法，也能用轻松的表达让复杂话题更容易理解。做分享、采访或创意讨论时，你的灵活很有用。把最有价值的点子整理成简短步骤，能避免灵感停留在聊天里。"),
	("巨蟹座", "06.21-07.22",
	 "你细腻、有同理心，重视熟悉的人和环境，常能注意到别人没有说出的情绪。你的体贴让人安心，但气氛变化也可能影响你的心情。感到不安时，先分清事实和猜测，再给自己一点恢复的时间。",
	 "你期待稳定回应和被理解，建立信任后愿意认真照顾对方。单身时可以慢慢认识，不必为了安全感过早承诺；有伴时，直接说出希望得到的陪伴。关心不必靠猜，边界和需求都值得被双方尊重。",
	 "你有耐心，也善于留意团队的感受和容易被遗漏的细节，适合需要协作和持续照顾的任务。你的责任心可能让你承担过多。接手前确认分工、期限和可用精力，有困难时及早请求支持。",
	 "你愿意记住朋友的喜好，也能在别人低落时提供温柔的陪伴。照顾他人之余，请允许自己拒绝超出能力的请求。\n合拍：天蝎、双鱼。你们重视情感交流，适合慢慢建立信任，也要说清各自界限。\n需磨合：白羊、天秤。行动和协调能带来支持；表达方式可能不同，先说出感受和需要。",
	 "你善于察觉情绪与环境中的变化，也能通过细节营造安心的氛围。组织聚会、协调合作或陪伴朋友时，这份观察力很珍贵。别把照顾所有人当成自己的责任，先问自己还有多少精力。"),
	("狮子座", "07.23-08.22",
	 "你热情、慷慨，喜欢表达自己，也愿意在重要时刻站出来。被认可会让你更有动力，你的自信也能带动他人；但太在意面子或坚持自己的方式时，可能忽略别人的声音。倾听并接受反馈，不会减少你的光彩。",
	 "你喜欢真诚而热烈的回应，愿意表达欣赏，也希望自己被重视。单身时可以自然展现好感，同时尊重对方的节奏；有伴时，记得询问彼此需要怎样的关心。意见不同时，先理解对方，不必急着争输赢。",
	 "你乐于展示成果、组织伙伴和推进计划，热情能为团队带来动力。需要留意的是，主见太强时可能压过其他人的建议。讨论前明确目标，给伙伴发言的时间，并共同确认细节，让大家都能发挥长处。",
	 "你大方讲义气，喜欢把快乐分享给朋友，也期待被尊重和欣赏。关心别人时先问问对方需要陪伴还是建议。\n合拍：白羊、射手。共同的热情让你们容易一起行动，也要分享关注和决定权。\n需磨合：金牛、天蝎。耐心和专注能帮助你的计划；各有坚持时，先谈分工和底线。",
	 "你有感染他人的热情，也敢于把想法呈现出来。主持分享、组织活动或鼓励伙伴时，你能让现场更有凝聚力。让别人也有被看见的机会，并把准备工作做到位，你的表达会更有力量。"),
	("处女座", "08.23-09.22",
	 "你观察细致，喜欢把复杂的事情整理清楚，也愿意认真改进不足。你的分析力和责任感令人放心；不过标准太高时，你可能反复检查，甚至对自己过于苛刻。先完成必要部分，再决定哪些细节值得继续打磨。",
	 "你可能通过记住习惯、提供帮助来表达关心，也重视对方是否可靠。单身时不必用完美清单衡量每个人；有伴时，多说欣赏和自己的感受。想提出建议前，先确认对方是需要解决办法，还是只想被倾听。",
	 "你擅长分析、整理和发现流程中的遗漏，能为任务建立清楚的标准。认真是优势，但过度修改可能挤占时间。开始前列出最重要的要求，约定交付节点和修改次数，也给自己保留休息空间。",
	 "你愿意给朋友具体帮助，观察细节让你的建议常有实用价值。指出问题前先询问对方是否需要，并记得肯定对方的努力。\n合拍：金牛、摩羯。你们通常重视可靠和计划，也要给变化留出空间。\n需磨合：双子、射手。新想法能拓展你的视野；做事节奏可能不同，先约定关键步骤。",
	 "你善于发现细节之间的联系，并把混乱的信息整理成可执行的清单。检查方案、规划流程或学习新技能时，你能靠耐心积累优势。给每项任务设一个完成标准，让细致服务于目标，而不是无限延长任务。"),
	("天秤座", "09.23-10.22",
	 "你重视公平与和谐，愿意从不同立场思考，也常留意人与环境中的美感。你的协调能力能缓和分歧；但考虑太多人的感受时，可能迟迟不表达自己的选择。先想清最重要的条件，再给决定设个期限。",
	 "你欣赏平等交流、体贴和相互尊重，也愿意经营相处中的仪式感。单身时留意自己的真实喜好，不必一味迎合；有伴时，及时说出不舒服的地方。温和不等于回避分歧，坦诚讨论才能找到双方接受的方式。",
	 "你擅长沟通协调，能看见方案对不同人的影响，也愿意寻找共同点。反复比较可能拖慢决定。讨论前列出各方需求和你的判断标准，约定决定时间；必要时接受方案不必同时满足所有人。",
	 "你愿意倾听双方，常能让讨论重新回到共同的问题上。照顾气氛的同时，也要说出你的立场，不必答应每个请求。\n合拍：双子、水瓶。交流和不同观点容易激发灵感，也要把约定落实。\n需磨合：巨蟹、摩羯。体贴与务实能补充你的视角；关注点可能不同，先说清需要和安排。",
	 "你善于比较观点、寻找平衡，也能注意到表达和空间里的美感。协调分工、整理展示或讨论方案时，你的视角很有价值。先列出不可妥协的条件，再做选择，能让你的周全变成实际进展。"),
	("天蝎座", "10.23-11.21",
	 "你对在意的事情投入而专注，喜欢弄清背后的原因，也重视信任和真实。你的坚持能帮助你深入解决问题；但不确定时，过度猜测可能让你更紧张。先核实信息，允许自己暂时没有答案。",
	 "你看重忠诚和深入交流，建立信任可能需要时间，一旦认定便愿意认真投入。单身时可以边观察边表达界限；有伴时，把不安说出来，不用试探或查验来寻求安全感。亲密也需要尊重彼此的隐私和空间。",
	 "你善于追查线索、专注研究和处理复杂问题，面对困难时往往愿意坚持。过度独自承担或不愿分享进度，可能让合作变得吃力。把目标拆成阶段，及时同步发现，并邀请伙伴提出不同看法。",
	 "你珍惜值得信任的朋友，愿意认真守护承诺，也希望对方同样坦诚。出现隔阂时，先问清事实，别让猜测代替沟通。\n合拍：巨蟹、双鱼。你们常重视情感深度，也要尊重彼此空间。\n需磨合：狮子、水瓶。热情和新观点能带来启发；对主导权或独处的期待不同，先谈边界。",
	 "你擅长深入探索，也有耐心追踪问题的来龙去脉。研究资料、梳理复杂线索或制定长期计划时，你的专注能发挥作用。记得给自己设检查点，分享阶段成果，避免因执着于一个解释而错过其他可能。"),
	("射手座", "11.22-12.21",
	 "你乐观好奇，喜欢探索新体验和不同观点，也重视自由与成长。你的开阔视角能给人带来鼓励；不过太快追逐下一个目标时，可能忽略细节或承诺。出发前确认时间和资源，让热情有更稳的落点。",
	 "你喜欢轻松坦诚的交流，也需要个人空间和共同体验。单身时可从共同兴趣开始，留意双方期待是否一致；有伴时，提前商量行程与相处时间。直率很珍贵，说敏感话题时也给对方表达感受的机会。",
	 "你喜欢学习、尝试和看到事情更大的可能，适合在探索新方法或跨领域合作时发挥。点子远大时，执行细节和收尾可能被落下。把目标拆成小步骤，确认期限与预算，并为检查和交付留出时间。",
	 "你乐于分享见闻，能给朋友带来新鲜视角和轻松气氛。坦率之外也留意措辞，答应邀约前先确认时间和精力。\n合拍：白羊、狮子。你们容易被行动和探索吸引，也要顾及彼此的节奏。\n需磨合：处女、双鱼。细心和体贴能补充你的想法；计划或语气的偏好不同，先商量再行动。",
	 "你善于发现新的方向，并能从学习和经历中提炼灵感。探索新主题、分享见闻或设计体验时，你的开放心态很有帮助。挑一个想法做小规模尝试，完成后回顾效果，让创意不止停留在远景。"),
	("摩羯座", "12.22-01.19",
	 "你务实、有责任感，重视长期目标，习惯用计划和行动建立安全感。你的自律让人安心，但压力大时可能过于严厉，或把困难都揽给自己。允许计划调整，也允许自己休息，成果不必只靠硬撑。",
	 "你可能慢热，更愿意用守约和实际支持表达在意。单身时不必急着表现得无懈可击，可以逐渐分享真实想法；有伴时，除了安排事务，也主动表达欣赏和情绪。让对方知道你的需要，亲近不只靠承担责任。",
	 "你善于制定计划、跟进进度和坚持长期目标，能把抽象任务拆成可执行的步骤。高标准有助于保持质量，却也可能让你不愿求助。先排出优先级，合理分工，并把休息和复盘放进日程。",
	 "你常以可靠和守信赢得朋友的信任，也愿意在关键时刻提供实际支持。不必总扮演解决问题的人，分享感受也是亲近。\n合拍：金牛、处女。你们通常重视稳定和责任，也要接纳不同想法。\n需磨合：白羊、天秤。行动力和协调能带来新思路；决定节奏可能不同，先确认目标和期限。",
	 "你擅长把远期目标变成阶段计划，并靠持续投入积累成果。安排项目、建立习惯或管理资源时，你的耐心和组织力很有用。定期回看进展，也听听新建议，能让坚持更灵活。"),
	("水瓶座", "01.20-02.18",
	 "你独立、好奇，喜欢从不同角度看问题，也愿意尊重人与人之间的差异。你的新观点能打开思路；但太专注想法或独处时，别人可能不清楚你的感受。解释自己的想法，也适时回应身边人的情绪。",
	 "你欣赏平等交流和思想上的共鸣，也需要保留个人空间。单身时可以从朋友式相处慢慢认识；有伴时，提前说清独处与陪伴的需求。讨论问题时，别只分析对错，也问问对方此刻希望得到什么支持。",
	 "你善于提出新点子，愿意尝试不同方法，也能连接跨领域的观点。创意需要伙伴理解和配合，过于抽象可能让推进变慢。把想法画成步骤，先做一个小实验，并定期同步结果和下一步。",
	 "你尊重差异，愿意认识有不同想法的人，也珍惜彼此独立。需要安静时提前说一声，避免朋友把你的沉默误解为疏远。\n合拍：双子、天秤。交流与新观点容易带来共鸣，也要留意落实约定。\n需磨合：金牛、天蝎。耐心与专注能帮助想法落地；对改变或距离的期待不同，先谈边界。",
	 "你擅长跳出惯例，把看似无关的想法联系起来，也能关注群体中的不同需求。构思方案、改进工具或组织讨论时，你的视角能带来新可能。用具体例子解释，并先验证一个小步骤，让想法更容易被采用。"),
	("双鱼座", "02.19-03.20",
	 "你想象丰富、感受细腻，容易留意别人的情绪，也有温柔和浪漫的一面。你的共情能让人感到被理解；但太投入别人的需要时，你可能忽略自己的界限。先辨认自己的感受，再决定能提供多少帮助。",
	 "你重视温柔互动和情感共鸣，容易被细节与真诚打动。单身时慢慢观察对方的行动，不必只凭想象判断；有伴时，直接表达期待和不舒服的地方。关系里既可以体谅别人，也可以坚持自己的边界。",
	 "你善于感受需求、发挥想象和寻找有意义的表达，在创意或协作任务中能提供独特视角。面对琐碎步骤或压力时，计划可能变得模糊。把灵感记下来，拆成小任务，确认期限，遇到困难及时求助。",
	 "你愿意倾听和陪伴，常能察觉朋友情绪里的细微变化。帮助别人前先看看自己的精力，拒绝不合理的请求并不代表冷漠。\n合拍：巨蟹、天蝎。你们重视情感交流，也要直接说出各自的需要。\n需磨合：双子、射手。点子和行动力能带来启发；说话方式可能不同，先表达感受再确认。",
	 "你有丰富的想象力，也能从细节中捕捉情绪。写故事、设计体验或倾听他人时，你的感受力能带来温柔的创意。把想法变成一个小作品，再请信任的人给反馈，能帮助灵感逐步落地。"),
]


def draw_background():
	screen.fill(BG)


def draw_mystic_background():
	screen.fill(MYSTIC_BG)
	pygame.draw.line(screen, (47, 37, 64), (8, 48), (WIDTH - 8, 48), 1)


def draw_header(title, subtitle=None):
	draw_background()
	centered(title, font_title, INK, 8)
	if subtitle:
		centered(subtitle, font_small, MUTED, 33)


def footer_button_rects():
	margin, gap, height = 5, 4, 18
	button_width = (WIDTH - margin * 2 - gap * 2) // 3
	y = HEIGHT - height - 2
	return [pygame.Rect(margin + index * (button_width + gap), y, button_width, height)
			for index in range(3)]


def draw_footer(labels, dark=False):
	pygame.draw.line(screen, LINE, (5, HEIGHT - 23), (WIDTH - 5, HEIGHT - 23), 1)
	if dark:
		pygame.draw.line(screen, MYSTIC_LINE, (5, HEIGHT - 23), (WIDTH - 5, HEIGHT - 23), 1)
	for index, (label, rect) in enumerate(zip(labels, footer_button_rects())):
		color = ((65, 48, 80) if index == 0 else MYSTIC_PANEL) if dark else \
			((255, 236, 243) if index == 0 else PANEL)
		border = MYSTIC_LINE if dark else LINE
		text_color = MYSTIC_GOLD if dark and index == 0 else MYSTIC_MUTED if dark else \
			(PINK_DARK if index == 0 else MUTED)
		rounded(rect, color, 5, 1, border)
		image = font_small.render(label, True, text_color)
		screen.blit(image, (rect.centerx - image.get_width() // 2,
						rect.centery - image.get_height() // 2))


def draw_moon(x, y, color=GOLD):
	pygame.draw.circle(screen, color, (x, y), 11)
	pygame.draw.circle(screen, PANEL, (x + 5, y - 4), 10)
	pygame.draw.circle(screen, PINK, (x + 15, y - 10), 2)
	pygame.draw.circle(screen, LILAC, (x - 14, y - 9), 2)


def draw_card_back(rect, selected=False, dark=False, rotation=0):
	x, y, w, h = rect
	card = pygame.Surface((w, h), pygame.SRCALPHA)
	base = MYSTIC_PANEL if dark else PANEL
	inner = MYSTIC_INNER if dark else (250, 229, 238)
	border = MYSTIC_GOLD if dark and selected else MYSTIC_LINE if dark else PINK if selected else LINE
	accent = MYSTIC_GOLD if dark else PINK_DARK
	pygame.draw.rect(card, base, (0, 0, w, h), border_radius=6)
	pygame.draw.rect(card, border, (0, 0, w, h), 2 if selected else 1, border_radius=6)
	pygame.draw.rect(card, inner, (4, 4, w - 8, h - 8), 1, border_radius=4)
	cx, cy = w // 2, h // 2
	pygame.draw.circle(card, accent, (cx, cy), max(5, min(w, h) // 4), 1)
	pygame.draw.circle(card, accent, (cx, cy), max(2, min(w, h) // 12))
	pygame.draw.line(card, accent, (cx, cy - h // 3), (cx, cy + h // 3), 1)
	pygame.draw.line(card, accent, (cx - w // 3, cy), (cx + w // 3, cy), 1)
	rotated = pygame.transform.rotate(card, rotation)
	screen.blit(rotated, rotated.get_rect(center=(x + w // 2, y + h // 2)))


def draw_tarot_face(rect, card, dark=False):
	x, y, w, h = rect
	base = MYSTIC_PANEL if dark else PANEL
	inner = MYSTIC_INNER if dark else (255, 241, 238)
	border = MYSTIC_GOLD if dark else GOLD
	ink = MYSTIC_TEXT if dark else INK
	accent = MYSTIC_GOLD if dark else PINK
	rounded(rect, base, 8, 2, border)
	rounded((x + 5, y + 5, w - 10, h - 10), inner, 5, 1, border if dark else LINE)
	cx, cy = x + w // 2, y + int(h * 0.40)
	pygame.draw.circle(screen, (48, 38, 63) if dark else (255, 251, 242), (cx, cy), max(12, min(w, h) // 4))
	pygame.draw.circle(screen, accent, (cx, cy), max(11, min(w, h) // 4), 1)
	if dark:
		pygame.draw.circle(screen, MYSTIC_GOLD, (cx, cy), max(5, min(w, h) // 9), 1)
		pygame.draw.polygon(screen, MYSTIC_GOLD, ((cx, cy - 13), (cx + 4, cy - 3), (cx, cy + 8), (cx - 4, cy - 3)), 1)
		pygame.draw.circle(screen, MYSTIC_GOLD, (cx - 13, cy + 14), 2)
		pygame.draw.circle(screen, MYSTIC_GOLD, (cx + 14, cy + 13), 2)
	else:
		heart_radius = max(4, min(w, h) // 11)
		pygame.draw.circle(screen, PINK, (cx - heart_radius, cy - heart_radius // 2), heart_radius)
		pygame.draw.circle(screen, PINK, (cx + heart_radius, cy - heart_radius // 2), heart_radius)
		pygame.draw.polygon(screen, PINK, ((cx - heart_radius * 2, cy),
										 (cx + heart_radius * 2, cy), (cx, cy + heart_radius * 2)))
		pygame.draw.circle(screen, LILAC, (cx - 14, cy + 14), 3)
		pygame.draw.circle(screen, MINT, (cx + 15, cy + 14), 3)
	label = font_small.render(card[0], True, ink)
	screen.blit(label, (cx - label.get_width() // 2, y + h - 25))


def draw_home(selected):
	draw_header("星愿占卜屋", "给今天一点温柔的小提示")
	if PORTRAIT:
		tile_h, gap, top = 48, 6, 58
		for index, (name, hint) in enumerate(zip(MODES, MODE_HINTS)):
			y = top + index * (tile_h + gap)
			color = (255, 236, 243) if index == selected else PANEL
			rounded((10, y, WIDTH - 20, tile_h), color, 10, 2 if index == selected else 1,
					PINK if index == selected else LINE)
			pygame.draw.circle(screen, (255, 222, 234), (34, y + tile_h // 2), 14)
			pygame.draw.circle(screen, PINK_DARK, (34, y + tile_h // 2), 4)
			screen.blit(font_heading.render(name, True, INK), (58, y + 3))
			screen.blit(font_small.render(hint, True, MUTED), (58, y + 26))
	else:
		gap = 8
		tile_w = (WIDTH - 28 - gap * 2) // 3
		for index, (name, hint) in enumerate(zip(MODES, MODE_HINTS)):
			x = 6 + index * (tile_w + gap)
			color = (255, 236, 243) if index == selected else PANEL
			rounded((x, 65, tile_w, 122), color, 10, 2 if index == selected else 1,
					PINK if index == selected else LINE)
			pygame.draw.circle(screen, (255, 222, 234), (x + tile_w // 2, 94), 17)
			if index == 1:
				draw_moon(x + tile_w // 2, 94, GOLD)
			else:
				pygame.draw.circle(screen, PINK_DARK, (x + tile_w // 2, 94), 5)
				pygame.draw.circle(screen, GOLD, (x + tile_w // 2, 94), 10, 1)
			label = font_heading.render(name, True, INK)
			screen.blit(label, (x + (tile_w - label.get_width()) // 2, 121))
			for line_index, line in enumerate(wrap_lines(hint, font_small, tile_w - 8)[:2]):
				image = font_small.render(line, True, MUTED)
				screen.blit(image, (x + (tile_w - image.get_width()) // 2, 147 + line_index * 14))
	draw_footer(("K1 开始", "K2 上一项", "K3 下一项"))


def card_scroll_position(start, direction, steps, elapsed, duration):
	progress = max(0.0, min(1.0, elapsed / duration))
	return start + direction * steps * (1 - (1 - progress) ** 2)


def draw_oracle_wheel(center, radius, angle, dark):
	cx, cy = center
	line = MYSTIC_LINE if dark else (230, 199, 157)
	accent = MYSTIC_GOLD if dark else PINK_DARK
	fill = MYSTIC_PANEL if dark else (255, 249, 246)
	pygame.draw.circle(screen, (29, 23, 43) if dark else (255, 251, 247), center, radius + 5)
	for ring in (radius, radius - 7, radius - 15):
		pygame.draw.circle(screen, line, center, ring, 1)
	for index in range(16):
		theta = angle + math.tau * index / 16
		inner = radius - (12 if index % 4 == 0 else 6)
		start = (int(cx + math.cos(theta) * inner), int(cy + math.sin(theta) * inner))
		end = (int(cx + math.cos(theta) * (radius - 2)), int(cy + math.sin(theta) * (radius - 2)))
		pygame.draw.line(screen, accent if index % 4 == 0 else line, start, end, 1)
		if index % 2 == 0:
			dot = (int(cx + math.cos(theta) * (radius - 17)),
				   int(cy + math.sin(theta) * (radius - 17)))
			pygame.draw.circle(screen, accent, dot, 2 if index % 4 == 0 else 1)
	marker = (int(cx + math.cos(angle) * (radius - 3)),
			  int(cy + math.sin(angle) * (radius - 3)))
	pygame.draw.circle(screen, accent, marker, 3)
	pygame.draw.circle(screen, fill, center, radius - 19)
	pygame.draw.circle(screen, accent, center, radius - 19, 1)
	direction_x, direction_y = math.cos(angle), math.sin(angle)
	scale = 3
	layer_size = (radius + 5) * 2
	layer_center = layer_size // 2
	pointer = pygame.Surface((layer_size * scale, layer_size * scale), pygame.SRCALPHA)

	def point(forward, sideways=0):
		return (round((layer_center + forward * direction_x - sideways * direction_y) * scale),
				round((layer_center + forward * direction_y + sideways * direction_x) * scale))

	shaft_edge = (145, 105, 110) if dark else (192, 93, 139)
	shaft_color = (250, 219, 161) if dark else (255, 217, 199)
	gem_color = (129, 92, 155) if dark else (220, 118, 161)
	highlight = (255, 246, 218)
	halo = (171, 132, 207, 70) if dark else (243, 151, 185, 75)
	for forward, sideways, size in ((radius * 0.15, -radius * 0.31, 2.5),
									(-radius * 0.22, radius * 0.28, 1.5)):
		star_x, star_y = point(forward, sideways)
		star_size = round(size * scale)
		pygame.draw.line(pointer, accent, (star_x - star_size, star_y),
						 (star_x + star_size, star_y), scale)
		pygame.draw.line(pointer, accent, (star_x, star_y - star_size),
						 (star_x, star_y + star_size), scale)

	orb_radius = max(6, round(radius * 0.16))
	head_distance = radius - orb_radius - 7
	tail = point(-radius * 0.3)
	head = point(head_distance)
	shaft_radius = max(3, radius // 14)
	pygame.draw.line(pointer, shaft_edge, tail, head, (shaft_radius + 1) * 2 * scale)
	pygame.draw.circle(pointer, shaft_edge, tail, (shaft_radius + 1) * scale)
	pygame.draw.line(pointer, shaft_color, tail, head, shaft_radius * 2 * scale)
	pygame.draw.circle(pointer, shaft_color, tail, shaft_radius * scale)
	pygame.draw.line(pointer, highlight, point(-radius * 0.22, -shaft_radius * 0.4),
					 point(head_distance - orb_radius, -shaft_radius * 0.4), scale)

	tail_radius = max(4, radius // 10)
	pygame.draw.circle(pointer, shaft_edge, tail, (tail_radius + 1) * scale)
	pygame.draw.circle(pointer, shaft_color, tail, tail_radius * scale)
	pygame.draw.circle(pointer, gem_color, tail, (tail_radius - 2) * scale)
	pygame.draw.circle(pointer, halo, head, (orb_radius + 3) * scale)
	pygame.draw.circle(pointer, shaft_edge, head, (orb_radius + 1) * scale)
	pygame.draw.circle(pointer, shaft_color, head, orb_radius * scale)
	pygame.draw.circle(pointer, gem_color, head, (orb_radius - 2) * scale)
	moon_radius = max(2, orb_radius // 2 - 1)
	pygame.draw.circle(pointer, highlight, point(head_distance - 0.5, 0.5), moon_radius * scale)
	pygame.draw.circle(pointer, gem_color, point(head_distance + 1.5, -1), moon_radius * scale)
	pygame.draw.circle(pointer, highlight, point(head_distance + orb_radius * 0.35,
												-orb_radius * 0.35), scale)

	pivot_radius = max(5, radius // 9)
	pygame.draw.circle(pointer, shaft_edge, point(0), (pivot_radius + 1) * scale)
	pygame.draw.circle(pointer, shaft_color, point(0), pivot_radius * scale)
	pygame.draw.circle(pointer, gem_color, point(0), (pivot_radius - 2) * scale)
	pygame.draw.circle(pointer, highlight, point(-pivot_radius * 0.25, -pivot_radius * 0.25), scale)
	screen.blit(pygame.transform.smoothscale(pointer, (layer_size, layer_size)),
				(cx - layer_center, cy - layer_center))


def draw_shuffle(mode, elapsed, card, scroll_position, spin_duration, stop_position):
	dark = mode == "daily"
	if dark:
		draw_mystic_background()
		centered("今日运势 · 星轮启示", font_title, MYSTIC_TEXT, 8)
		centered("让直觉带你找到那张牌", font_small, MYSTIC_MUTED, 33)
	else:
		draw_header("桃花星轮正在感应", "跟随光点，看看心意停在哪里")

	card_w, card_h = (72, 132) if PORTRAIT else (62, 98)
	spacing = card_w + 8
	row_top = HEIGHT - 23 - int(card_h * 0.74)
	wheel_radius = min(max(24, int(HEIGHT * 0.16)), max(24, (row_top - 74) // 2))
	wheel_center = (WIDTH // 2, max(int(HEIGHT * 0.285), wheel_radius + 55))
	wheel_angle = math.pi / 2 + (scroll_position - stop_position) * spacing / wheel_radius
	draw_oracle_wheel(wheel_center, wheel_radius, wheel_angle, dark)

	nearest_slot = math.floor(scroll_position + 0.5)

	reveal_start = spin_duration + SPIN_SETTLE_SECONDS
	revealing = elapsed >= reveal_start
	lift_progress = min(1.0, max(0.0, (elapsed - reveal_start) / 0.82))
	eased = 1 - (1 - lift_progress) ** 3
	previous_clip = screen.get_clip()
	screen.set_clip((0, 0, WIDTH, HEIGHT - 23))
	if not revealing:
		accent = MYSTIC_GOLD if dark else PINK_DARK
		pygame.draw.polygon(screen, accent, ((WIDTH // 2 - 4, row_top - 9),
										 (WIDTH // 2 + 4, row_top - 9), (WIDTH // 2, row_top - 4)))
	visible_radius = (WIDTH / 2 + card_w / 2) / spacing
	first_slot = math.floor(scroll_position - visible_radius)
	last_slot = math.ceil(scroll_position + visible_radius)
	for slot in range(first_slot, last_slot + 1):
		center_x = round(WIDTH / 2 + (slot - scroll_position) * spacing)
		if center_x + card_w // 2 <= 0 or center_x - card_w // 2 >= WIDTH:
			continue
		if revealing and slot == nearest_slot:
			continue
		rect = (center_x - card_w // 2, row_top, card_w, card_h)
		draw_card_back(rect, slot == nearest_slot and not revealing, dark)

	if revealing:
		desired_height = card_h + (14 if PORTRAIT else 0)
		desired_width = card_w + (10 if PORTRAIT else 8)
		wheel_bottom = wheel_center[1] + wheel_radius + 5
		reveal_height = min(desired_height, HEIGHT - 26 - wheel_bottom - 6)
		reveal_width = round(desired_width * reveal_height / desired_height)
		target_y = wheel_bottom + 6 + reveal_height // 2
		center_x = WIDTH // 2
		origin_y = row_top + card_h // 2
		center_y = int(origin_y + (target_y - origin_y) * eased)
		moving_w = int(card_w + (reveal_width - card_w) * eased)
		moving_h = int(card_h + (reveal_height - card_h) * eased)
		rect = (center_x - moving_w // 2, center_y - moving_h // 2, moving_w, moving_h)
		if lift_progress < 0.65:
			draw_card_back(rect, True, dark)
		elif lift_progress < 0.82:
			edge_color = MYSTIC_GOLD if dark else PINK
			pygame.draw.line(screen, MYSTIC_LINE if dark else LINE,
						 (center_x + 1, rect[1] + 5), (center_x + 1, rect[1] + moving_h - 5), 1)
			pygame.draw.line(screen, edge_color, (center_x, rect[1] + 5),
						 (center_x, rect[1] + moving_h - 5), 1)
		else:
			draw_tarot_face(rect, card, dark)

	screen.set_clip(previous_clip)
	labels = ("正在选牌", "K2 返回", "正在选牌") if not revealing else \
		("正在揭牌", "K2 返回", "正在揭牌")
	draw_footer(labels, dark)


def draw_love_result(card, page):
	draw_background()
	pygame.draw.rect(screen, (255, 232, 241), (0, 0, WIDTH, 48))
	centered("桃花情感指引", font_title, INK, 8)
	centered("缘分 · 心动 · 相处", font_small, PINK_DARK, 33)
	pygame.draw.line(screen, LINE, (8, 48), (WIDTH - 8, 48), 1)
	if WIDTH >= 300:
		rect = (12, 55, 74, 104)
		text_x, text_y, max_w = 96, 88, WIDTH - 108
	else:
		rect = (12, 54, 60, 84)
		text_x, text_y, max_w = 12, 156, WIDTH - 24
	draw_tarot_face(rect, card)
	page_label = font_small.render("%d / %d" % (page + 1, LOVE_PAGE_COUNT), True, PINK_DARK)
	if WIDTH >= 300:
		screen.blit(font_heading.render(card[0] + " · " + card[1], True, PINK_DARK), (text_x, 59))
		screen.blit(page_label, (WIDTH - 12 - page_label.get_width(), 64))
		for label, font, color, y in (("合拍指数", font_small, MUTED, 161),
								   (str(card[4]) + "%", font_heading, PINK_DARK, 174),
								   ("仅供趣味参考", font_small, MUTED, 201)):
			image = font.render(label, True, color)
			screen.blit(image, (rect[0] + (rect[2] - image.get_width()) // 2, y))
		bar_x, bar_y, bar_width = rect[0] + 4, 195, rect[2] - 8
	else:
		screen.blit(font_heading.render(card[0], True, PINK_DARK), (84, 57))
		screen.blit(page_label, (WIDTH - 12 - page_label.get_width(), 62))
		screen.blit(font_small.render("关键词：" + card[1], True, MUTED), (84, 80))
		screen.blit(font_small.render("合拍指数", True, MUTED), (84, 105))
		score = font_heading.render(str(card[4]) + "%", True, PINK_DARK)
		screen.blit(score, (WIDTH - 12 - score.get_width(), 99))
		screen.blit(font_small.render("仅供趣味参考", True, MUTED), (84, 128))
		bar_x, bar_y, bar_width = 84, 120, WIDTH - 96
		pygame.draw.line(screen, LINE, (12, 147), (WIDTH - 12, 147), 1)
	rounded((bar_x, bar_y, bar_width, 5), (245, 215, 225), 2)
	rounded((bar_x, bar_y, max(2, bar_width * card[4] // 100), 5), PINK, 2)
	sections = card[3].split("\n")
	start = page * LOVE_SECTIONS_PER_PAGE
	for paragraph in sections[start:start + LOVE_SECTIONS_PER_PAGE]:
		section_y = text_y
		text_y = draw_wrapped(paragraph, text_x, text_y, max_w - font_body.size("。")[0],
							  font_body, INK, 2)
		label = paragraph.split("：", 1)[0] + "："
		screen.blit(font_body.render(label, True, PINK_DARK), (text_x, section_y))
		text_y += 4
	draw_footer(("K1 再抽", "K2 返回", "K3 下一页" if page == 0 else "K3 上一页"))


def draw_result(mode, card, page=0):
	if mode == "love":
		draw_love_result(card, page)
		return
	draw_mystic_background()
	centered("今日运势指引", font_title, MYSTIC_TEXT, 8)
	centered("今天的建议 · 仅供趣味参考", font_small, MYSTIC_MUTED, 33)
	if WIDTH >= 300:
		rect = (12, 55, 74, 104)
		text_x, text_y, max_w = 96, 88, WIDTH - 108
	else:
		rect = (12, 54, 60, 84)
		text_x, text_y, max_w = 12, 156, WIDTH - 24
	draw_tarot_face(rect, card, True)
	if WIDTH >= 300:
		screen.blit(font_heading.render(card[0] + " · " + card[1], True, MYSTIC_GOLD), (text_x, 59))
	else:
		screen.blit(font_heading.render(card[0], True, MYSTIC_GOLD), (84, 60))
		screen.blit(font_small.render("关键词：" + card[1], True, MYSTIC_MUTED), (84, 88))
		pygame.draw.line(screen, MYSTIC_LINE, (12, 147), (WIDTH - 12, 147), 1)
	for paragraph in card[2].split("\n"):
		text_y = draw_wrapped(paragraph, text_x, text_y, max_w - font_body.size("。")[0],
							  font_body, MYSTIC_TEXT, 2)
		text_y += 2
	draw_footer(("K1 再抽", "K2 返回", "K3 再抽"), True)


def zodiac_pages(index, topic):
	text = ZODIAC[index][topic + 2]
	max_width = WIDTH - 36 - font_body.size("。")[0]
	line_height = font_body.get_linesize() + 2
	lines_per_page = max(1, (HEIGHT - 32 - 131 - font_body.get_height()) // line_height + 1)
	pages, current_page = [], []
	for paragraph in text.split("\n"):
		lines = wrap_lines(paragraph, font_body, max_width)
		if current_page and len(current_page) + len(lines) > lines_per_page:
			pages.append(current_page)
			current_page = []
		while len(lines) > lines_per_page:
			split_at = lines_per_page
			if len(lines) - split_at == 1 and split_at > 1:
				split_at -= 1
			pages.append(lines[:split_at])
			lines = lines[split_at:]
		current_page.extend(lines)
	if current_page:
		pages.append(current_page)
	return pages


def draw_zodiac(index, topic, page):
	sign = ZODIAC[index]
	pages = zodiac_pages(index, topic)
	draw_header("星座小档案", "太阳星座 · 仅供趣味")
	rounded((9, 52, WIDTH - 18, HEIGHT - 80), PANEL, 8, 1, LINE)
	screen.blit(font_title.render(sign[0], True, PINK_DARK), (18, 56))
	date = font_small.render("约 " + sign[1], True, MUTED)
	screen.blit(date, (WIDTH - date.get_width() - 18, 62))
	topic_w = (WIDTH - 44) // len(TOPICS)
	for i, label in enumerate(TOPICS):
		x = 17 + i * (topic_w + 3)
		active = i == topic
		rounded((x, 82, topic_w, 21), (255, 232, 240) if active else (250, 246, 247),
				7, 1 if active else 0, PINK if active else None)
		image = font_small.render(label, True, PINK_DARK if active else MUTED)
		screen.blit(image, (x + (topic_w - image.get_width()) // 2, 86))
	heading = ("性格特点", "感情相处", "工作学习", "人际关系", "你的天赋")[topic]
	screen.blit(font_heading.render(heading, True, INK), (18, 108))
	page_label = font_small.render("%d/%d" % (page + 1, len(pages)), True, MUTED)
	screen.blit(page_label, (WIDTH - 18 - page_label.get_width(), 113))
	text_y = 131
	for line in pages[page]:
		color = PINK_DARK if line.startswith(("合拍：", "需磨合：")) else INK
		screen.blit(font_body.render(line, True, color), (18, text_y))
		text_y += font_body.get_linesize() + 2
	draw_footer(("K1 下一页" if page + 1 < len(pages) else "K1 换主题", "K2 下星座", "K3 返回"))


def render(state):
	view = state["view"]
	if view == "home":
		draw_home(state["menu"])
	elif view == "shuffle":
		draw_shuffle(state["mode"], state["elapsed"], state["card"],
				 state["scroll_position"], state["spin_duration"],
				 state["scroll_start"] + state["scroll_direction"] * state["scroll_steps"])
	elif view == "result":
		draw_result(state["mode"], state["card"], state.get("love_page", 0))
	elif view == "zodiac":
		draw_zodiac(state["sign"], state["topic"], state.get("zodiac_page", 0))
	return spi_lcd.present()


def start_draw(state, mode):
	cards = DAILY_CARDS if mode == "daily" else TAROT
	card_count = len(cards)
	selected = random.randrange(card_count)
	pointer = random.randrange(card_count)
	direction = random.choice((-1, 1))
	steps = card_count + ((selected - pointer) * direction) % card_count
	state.update({"view": "shuffle", "mode": mode, "pointer": pointer,
				  "elapsed": 0.0, "spin_duration": SPIN_DURATION, "selected": selected,
				  "scroll_start": pointer, "scroll_direction": direction,
				  "scroll_steps": steps, "scroll_position": float(pointer), "card_count": card_count,
				  "card": cards[selected], "love_page": 0})


def handle_action(action, state):
	if action == "BACK":
		state["view"] = "home"
	elif state["view"] == "home":
		if action == "K2":
			state["menu"] = (state["menu"] - 1) % len(MODES)
		elif action == "K3":
			state["menu"] = (state["menu"] + 1) % len(MODES)
		elif action == "K1":
			if state["menu"] == 1:
				state.update({"view": "zodiac", "sign": 0, "topic": 0, "zodiac_page": 0})
			else:
				start_draw(state, "daily" if state["menu"] == 0 else "love")
	elif state["view"] == "zodiac":
		if action == "K1":
			page = state.get("zodiac_page", 0) + 1
			if page < len(zodiac_pages(state["sign"], state["topic"])):
				state["zodiac_page"] = page
			else:
				state["topic"] = (state["topic"] + 1) % len(TOPICS)
				state["zodiac_page"] = 0
		elif action == "K2":
			state["sign"] = (state["sign"] + 1) % len(ZODIAC)
			state["topic"] = 0
			state["zodiac_page"] = 0
		elif action == "K3":
			state["view"] = "home"
	elif state["view"] == "result":
		if action == "K2":
			state["view"] = "home"
		elif action == "K3" and state["mode"] == "love":
			state["love_page"] = (state.get("love_page", 0) + 1) % LOVE_PAGE_COUNT
		elif action in ("K1", "K3"):
			start_draw(state, state["mode"])
	elif state["view"] == "shuffle" and action == "K2":
		state["view"] = "home"


BUTTONS = {"K1": 18, "K2": 23, "K3": 24}
gpio = None
try:
	import RPi.GPIO as GPIO  # type: ignore[import-not-found]

	GPIO.setmode(GPIO.BCM)
	for pin in BUTTONS.values():
		GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
	gpio = GPIO
except Exception as error:
	print("GPIO 不可用（%s），使用键盘模拟：1/2/3=K1/K2/K3，Backspace=返回。" % error)

button_state = {name: {"down": False, "since": 0.0, "long": False} for name in BUTTONS}
LONG_PRESS_SECONDS = 0.8


def poll_gpio():
	now = time.monotonic()
	actions = []
	for name, pin in BUTTONS.items():
		pressed = gpio.input(pin) == gpio.LOW
		current = button_state[name]
		if pressed and not current["down"]:
			current.update({"down": True, "since": now, "long": False})
			if name != "K1":
				actions.append(name)
		elif pressed and name == "K1" and not current["long"] and now - current["since"] >= LONG_PRESS_SECONDS:
			current["long"] = True
			actions.append("BACK")
		elif not pressed and current["down"]:
			if name == "K1" and not current["long"]:
				actions.append("K1")
			current["down"] = False
	return actions


def mouse_button_at(window_position):
	if not spi_lcd.is_simulate():
		return None
	window = pygame.display.get_surface()
	if window is None:
		return None
	logical_position = (
		window_position[0] * WIDTH / window.get_width(),
		window_position[1] * HEIGHT / window.get_height(),
	)
	for name, rect in zip(("K1", "K2", "K3"), footer_button_rects()):
		if rect.collidepoint(logical_position):
			return name
	return None


state = {"view": "home", "menu": 0, "sign": 0, "topic": 0,
		 "mode": "daily", "pointer": 0, "elapsed": 0.0, "spin_duration": SPIN_DURATION,
		 "scroll_start": 0, "scroll_direction": 1, "scroll_steps": len(DAILY_CARDS),
		 "scroll_position": 0.0,
		 "selected": 0, "card": DAILY_CARDS[0], "card_count": len(DAILY_CARDS), "love_page": 0}
clock = pygame.time.Clock()
running = True
print("星愿占卜屋已启动。K1 确认，K2/K3 选择；长按 K1 返回菜单。")

try:
	while running:
		dt = clock.tick(30) / 1000.0
		actions = []
		if gpio is None:
			for event in pygame.event.get():
				if event.type == pygame.QUIT:
					running = False
				elif event.type == pygame.KEYDOWN:
					if event.key in (pygame.K_ESCAPE, pygame.K_q):
						running = False
					elif event.key in (pygame.K_BACKSPACE, pygame.K_0):
						actions.append("BACK")
					elif event.key == pygame.K_1:
						actions.append("K1")
					elif event.key == pygame.K_2:
						actions.append("K2")
					elif event.key == pygame.K_3:
						actions.append("K3")
				elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
					name = mouse_button_at(event.pos)
					if name:
						actions.append(name)
		else:
			actions = poll_gpio()

		for action in actions:
			handle_action(action, state)

		if state["view"] == "shuffle":
			state["elapsed"] += dt
			state["scroll_position"] = card_scroll_position(
				state["scroll_start"], state["scroll_direction"], state["scroll_steps"],
				state["elapsed"], state["spin_duration"])
			state["pointer"] = math.floor(state["scroll_position"] + 0.5) % state["card_count"]
			if state["elapsed"] >= state["spin_duration"] + SPIN_SETTLE_SECONDS + 1.25:
				state["view"] = "result"

		running = render(state) and running
finally:
	if gpio is not None:
		gpio.cleanup()
	pygame.quit()
