import sys

import spi_lcd

# 覆盖开关（不改则沿用 spi_lcd.py 顶部的 SIMULATE_DISPLAY / 自动检测）
# spi_lcd.SIMULATE_DISPLAY = True   # 强制本机窗口
# spi_lcd.SIMULATE_DISPLAY = False  # 强制树莓派 /dev/fb1

screen = spi_lcd.init()
import pygame  # noqa: E402  必须在 spi_lcd.init() 之后，环境变量才生效

screen.fill((20, 40, 80))
font = spi_lcd.load_font(24)

text1 = font.render("Hello Raspberry Pi!", True, (255, 255, 255))
text2 = font.render("宝可梦图鉴屏幕测试", True, (255, 215, 0))
text3 = font.render("SPI 驱动运行正常", True, (0, 255, 127))

screen.blit(text1, (20, 40))
screen.blit(text2, (20, 100))
screen.blit(text3, (20, 160))

if not spi_lcd.present():
    pygame.quit()
    sys.exit()

print("画面已输出。按 Esc / 关闭窗口，或 Ctrl+C 退出。")

try:
    while spi_lcd.idle(100):
        pass
except KeyboardInterrupt:
    pass
finally:
    pygame.quit()
    sys.exit()
