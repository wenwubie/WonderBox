# # import os
# # import sys
# # import pygame
# # import array
# # from evdev import InputDevice, ecodes, list_devices

# # # 1. 强制指定 Pygame 使用虚拟驱动并在内存中创建 320x240 的横屏画布
# # os.environ["PYGAME_DETECT_AVX2"] = "1"
# # os.environ["SDL_VIDEODRIVER"] = "dummy"
# # os.environ["SDL_FBDEV"] = "/dev/fb1"

# # pygame.init()
# # FB_WIDTH = 320
# # FB_HEIGHT = 240
# # screen = pygame.display.set_mode((FB_WIDTH, FB_HEIGHT))

# # # 3. 加载字体（若检测到 font.ttf 则使用，否则回退到系统英文底色字体）
# # font = pygame.font.Font("font.ttf" if os.path.exists("font.ttf") else None, 20)

# # # 定义背景颜色和文字颜色
# # BG_COLOR = (20, 40, 80)      # 深蓝色背景
# # TEXT_COLOR = (0, 255, 127)    # 绿色坐标字

# # def flush_to_fb():
# #     """将 Pygame 内存画布的内容安全、快速地灌入横屏 /dev/fb1"""
# #     try:
# #         # 获取最新的 RGB 原始字节数据
# #         raw_rgb = pygame.image.tostring(screen, "RGB")
        
# #         # 【修复越界核心】：动态计算当前 Pygame 实际输出的像素总量，防止写死 320x240 导致越界
# #         actual_pixels = len(raw_rgb) // 3
# #         rgb565_array = array.array('H', [0] * actual_pixels)

# #         # 高效转换为 16位 (RGB565)
# #         for i in range(actual_pixels):
# #             r = raw_rgb[i * 3]
# #             g = raw_rgb[i * 3 + 1]
# #             b = raw_rgb[i * 3 + 2]
            
# #             r5 = (r >> 3) & 0x1F
# #             g6 = (g >> 2) & 0x3F
# #             b5 = (b >> 3) & 0x1F
            
# #             rgb565_array[i] = (r5 << 11) | (g6 << 5) | b5

# #         # 写入物理屏幕驱动（如果实际像素多了，我们也只截取小屏需要的 320x240 字节数）
# #         bytes_to_write = rgb565_array.tobytes()
# #         max_bytes = FB_WIDTH * FB_HEIGHT * 2  # 320x240 每个像素占 2 字节
        
# #         with open("/dev/fb1", "wb") as f:
# #             f.write(bytes_to_write[:max_bytes])
            
# #     except Exception as e:
# #         print(f"投射失败: {e}")

# # # 初始显示：未点击时先刷一个干净的背景
# # screen.fill(BG_COLOR)
# # initial_text = font.render("请点击屏幕测试坐标...", True, (255, 255, 255))
# # screen.blit(initial_text, (20, 100))
# # pygame.display.flip()
# # flush_to_fb()

# # # =========================================================================
# # # 🛠️ 触摸屏参数配置与映射
# # # =========================================================================
# # # ⚠️ 注意：电阻屏直接上报的物理坐标往往是 200 到 3900 之间的硬件数值
# # # 请观察你之前程序打印出的 X/Y 最小值和最大值，填入下方进行精准像素映射。
# # TOUCH_MIN_X, TOUCH_MAX_X = 200, 3900
# # TOUCH_MIN_Y, TOUCH_MAX_Y = 200, 3900

# # touch_device = None
# # devices = [InputDevice(path) for path in list_devices()]

# # for device in devices:
# #     if "touchscreen" in device.name.lower() or "ads7846" in device.name.lower():
# #         touch_device = device
# #         print(f"✅ 成功找到电阻屏输入设备: {device.name} [{device.path}]")
# #         break

# # if touch_device is None and len(devices) > 0:
# #     touch_device = devices[0]
# #     print(f"⚠️ 未找到明确名称，尝试监听默认输入端: {touch_device.name}")

# # if touch_device is None:
# #     print("❌ 未检测到任何输入设备，请检查触控引脚！")
# #     sys.exit()

# # print("👉 监听已开启，现在请点击屏幕，坐标将实时呈现在 SPI 屏上...")
# # print("按 Ctrl+C 可退出测试程序。")

# # # 8. 主循环：监听触控事件，实时映射并在对应的像素点刷写屏幕
# # raw_x = 0
# # raw_y = 0

# # try:
# #     for event in touch_device.read_loop():
# #         if event.type == ecodes.EV_ABS:
# #             if event.code == ecodes.ABS_X:
# #                 raw_x = event.value
# #             elif event.code == ecodes.ABS_Y:
# #                 raw_y = event.value
                
# #         elif event.type == ecodes.EV_SYN:
# #             # 只有在获取到有效的硬件物理坐标时才进行渲染
# #             if raw_x != 0 and raw_y != 0:
# #                 # 【等比例映射公式】：将硬件触控电压范围转换到 320x240 的屏幕像素坐标
# #                 pixel_x = int((raw_x - TOUCH_MIN_X) * FB_WIDTH / (TOUCH_MAX_X - TOUCH_MIN_X))
# #                 pixel_y = int((raw_y - TOUCH_MIN_Y) * FB_HEIGHT / (TOUCH_MAX_Y - TOUCH_MIN_Y))
                
# #                 # 边界限定，防止计算出的像素点超出 320x240 画面范围
# #                 pixel_x = max(0, min(pixel_x, FB_WIDTH))
# #                 pixel_y = max(0, min(pixel_y, FB_HEIGHT))
                
# #                 print(f"🎯 硬件物理坐标: ({raw_x}, {raw_y}) -> 转换像素坐标: ({pixel_x}, {pixel_y})")
                
# #                 # 【清除其它位置】：用背景色重新填满画布，直接把上一次的数据抹掉
# #                 screen.fill(BG_COLOR)
                
# #                 # 创建新的坐标文字
# #                 coord_text = font.render(f"({pixel_x}, {pixel_y})", True, TEXT_COLOR)
                
# #                 # 限制文字贴图位置，防止字体的右侧或下方超出物理屏幕
# #                 # 文字稍微向右上角偏移一点 (x+10, y-25)，避免被触控笔或手指挡住
# #                 blit_x = max(5, min(pixel_x + 10, FB_WIDTH - 80))
# #                 blit_y = max(5, min(pixel_y - 25, FB_HEIGHT - 25))
                
# #                 # 将文字贴在计算出的全新像素位置上
# #                 screen.blit(coord_text, (blit_x, blit_y))
                
# #                 # 刷新 Pygame 内存画布，并整体投射到底层硬件 /dev/fb1
# #                 pygame.display.flip()
# #                 flush_to_fb()

# # except KeyboardInterrupt:
# #     print("\n程序已安全退出。")
# #     pygame.quit()
# #     sys.exit()



# import os
# import sys
# import pygame
# import array
# from evdev import InputDevice, ecodes, list_devices

# # 1. 强制指定 Pygame 使用虚拟驱动并在内存中创建 320x240 的横屏画布
# os.environ["PYGAME_DETECT_AVX2"] = "1"
# os.environ["SDL_VIDEODRIVER"] = "dummy"
# os.environ["SDL_FBDEV"] = "/dev/fb1"

# pygame.init()
# FB_WIDTH = 320
# FB_HEIGHT = 240
# screen = pygame.display.set_mode((FB_WIDTH, FB_HEIGHT))

# # 定义颜色
# BG_COLOR = (20, 40, 80)       # 深蓝色背景
# DOT_COLOR = (255, 69, 0)      # 橙红色圆点（非常醒目）

# def flush_to_fb():
#     """采用更兼容的 16位 像素投射方式，彻底解决越界问题"""
#     try:
#         # 强制将内存画布转为 RGB 格式字节流
#         raw_rgb = pygame.image.tostring(screen, "RGB")
#         actual_pixels = len(raw_rgb) // 3
        
#         # 建立容量匹配的数组
#         rgb565_array = array.array('H', [0] * actual_pixels)

#         # 转换为 16位 (RGB565)
#         for i in range(actual_pixels):
#             r = raw_rgb[i * 3]
#             g = raw_rgb[i * 3 + 1]
#             b = raw_rgb[i * 3 + 2]
            
#             r5 = (r >> 3) & 0x1F
#             g6 = (g >> 2) & 0x3F
#             b5 = (b >> 3) & 0x1F
            
#             rgb565_array[i] = (r5 << 11) | (g6 << 5) | b5

#         # 严格截取物理屏幕大小的字节数写入驱动
#         max_bytes = FB_WIDTH * FB_HEIGHT * 2  
#         with open("/dev/fb1", "wb") as f:
#             f.write(rgb565_array.tobytes()[:max_bytes])
#     except Exception as e:
#         print(f"投射失败: {e}")

# # 初始显示：刷一个干净的背景
# screen.fill(BG_COLOR)
# pygame.display.flip()
# flush_to_fb()

# # =========================================================================
# # 🛠️ 触摸屏参数配置与映射（用于校准）
# # =========================================================================
# # 💡 电阻屏常见物理最大/最小值，如果点击偏移严重，待会我们需要修改这里的映射逻辑
# TOUCH_MIN_X, TOUCH_MAX_X = 200, 3900
# TOUCH_MIN_Y, TOUCH_MAX_Y = 200, 3900

# touch_device = None
# devices = [InputDevice(path) for path in list_devices()]

# for device in devices:
#     if "touchscreen" in device.name.lower() or "ads7846" in device.name.lower():
#         touch_device = device
#         print(f"✅ 成功找到电阻屏输入设备: {device.name} [{device.path}]")
#         break

# if touch_device is None and len(devices) > 0:
#     touch_device = devices[0]
#     print(f"⚠️ 未找到明确名称，尝试监听默认输入端: {touch_device.name}")

# if touch_device is None:
#     print("❌ 未检测到任何输入设备，请检查触控引脚！")
#     sys.exit()

# print("👉 监听已开启，现在请点击屏幕，圆点将显示在对应像素上...")
# print("按 Ctrl+C 可退出测试程序。")

# raw_x = 0
# raw_y = 0

# try:
#     for event in touch_device.read_loop():
#         if event.type == ecodes.EV_ABS:
#             if event.code == ecodes.ABS_X:
#                 raw_x = event.value
#             elif event.code == ecodes.ABS_Y:
#                 raw_y = event.value
                
#         elif event.type == ecodes.EV_SYN:
#             if raw_x != 0 and raw_y != 0:
#                 # 1. 基础映射公式：转换到 320x240 的屏幕像素坐标
#                 pixel_x = int((raw_x - TOUCH_MIN_X) * FB_WIDTH / (TOUCH_MAX_X - TOUCH_MIN_X))
#                 pixel_y = int((raw_y - TOUCH_MIN_Y) * FB_HEIGHT / (TOUCH_MAX_Y - TOUCH_MIN_Y))
                
#                 # 2. 边界限定
#                 pixel_x = max(0, min(pixel_x, FB_WIDTH))
#                 pixel_y = max(0, min(pixel_y, FB_HEIGHT))
                
#                 print(f"🎯 硬件坐标: ({raw_x}, {raw_y}) -> 转换像素坐标: ({pixel_x}, {pixel_y})")
                
#                 # 3. 清除其它位置（重新涂满背景色）
#                 screen.fill(BG_COLOR)
                
#                 # 4. 在当前计算出的像素点位置，画一个半径为 8 像素的实心圆点
#                 pygame.draw.circle(screen, DOT_COLOR, (pixel_x, pixel_y), 8)
                
#                 # 5. 刷新画布并投射
#                 pygame.display.flip()
#                 flush_to_fb()

# except KeyboardInterrupt:
#     print("\n程序已安全退出。")
#     pygame.quit()
#     sys.exit()



import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "common"))

import spi_lcd

screen = spi_lcd.init()
import pygame  # noqa: E402

FB_WIDTH = spi_lcd.FB_WIDTH
FB_HEIGHT = spi_lcd.FB_HEIGHT

BG_COLOR = (20, 40, 80)
DOT_COLOR = (255, 69, 0)


def draw_dot(pixel_x, pixel_y, extra=""):
    pixel_x = max(0, min(pixel_x, FB_WIDTH))
    pixel_y = max(0, min(pixel_y, FB_HEIGHT))
    print(f"🎯 {extra}像素坐标: ({pixel_x}, {pixel_y})")
    screen.fill(BG_COLOR)
    pygame.draw.circle(screen, DOT_COLOR, (pixel_x, pixel_y), 8)
    return spi_lcd.present()


screen.fill(BG_COLOR)
if not spi_lcd.present():
    pygame.quit()
    sys.exit()

# =========================================================================
# 本机模拟：鼠标点击窗口即可画点（坐标已换算回 320x240）
# =========================================================================
if spi_lcd.is_simulate():
    print("👉 本机模拟：在窗口里点击，圆点会画在对应 320x240 像素上。Esc 退出。")
    try:
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    mx, my = event.pos
                    pixel_x = mx // spi_lcd.WINDOW_SCALE
                    pixel_y = my // spi_lcd.WINDOW_SCALE
                    if not draw_dot(pixel_x, pixel_y, "鼠标 -> "):
                        running = False
            pygame.time.wait(16)
    except KeyboardInterrupt:
        pass
    finally:
        pygame.quit()
        sys.exit()

# =========================================================================
# 树莓派真机：电阻屏 evdev
# =========================================================================
from evdev import InputDevice, ecodes, list_devices  # noqa: E402

TOUCH_MIN_X, TOUCH_MAX_X = 200, 3900
TOUCH_MIN_Y, TOUCH_MAX_Y = 200, 3900

touch_device = None
devices = [InputDevice(path) for path in list_devices()]

for device in devices:
    if "touchscreen" in device.name.lower() or "ads7846" in device.name.lower():
        touch_device = device
        print(f"✅ 成功找到电阻屏输入设备: {device.name} [{device.path}]")
        break

if touch_device is None and len(devices) > 0:
    touch_device = devices[0]
    print(f"⚠️ 未找到明确名称，尝试监听默认输入端: {touch_device.name}")

if touch_device is None:
    print("❌ 未检测到任何输入设备，请检查触控引脚！")
    sys.exit()

print("👉 监听已开启，现在请点击屏幕...")
print("按 Ctrl+C 可退出测试程序。")

raw_x = 0
raw_y = 0

try:
    for event in touch_device.read_loop():
        if event.type == ecodes.EV_ABS:
            if event.code == ecodes.ABS_X:
                raw_x = event.value
            elif event.code == ecodes.ABS_Y:
                raw_y = event.value

        elif event.type == ecodes.EV_SYN:
            if raw_x != 0 and raw_y != 0:
                pixel_x = int((raw_x - TOUCH_MIN_X) * FB_WIDTH / (TOUCH_MAX_X - TOUCH_MIN_X))
                pixel_y = int((raw_y - TOUCH_MIN_Y) * FB_HEIGHT / (TOUCH_MAX_Y - TOUCH_MIN_Y))
                pixel_x = FB_WIDTH - pixel_x
                pixel_y = FB_HEIGHT - pixel_y
                if not draw_dot(pixel_x, pixel_y, f"硬件 ({raw_x}, {raw_y}) -> "):
                    break
except KeyboardInterrupt:
    print("\n程序已安全退出。")
finally:
    pygame.quit()
    sys.exit()

