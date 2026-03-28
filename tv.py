import os
import time
import sys
import shutil
import webbrowser
import urllib.parse
from datetime import datetime
from playwright.sync_api import sync_playwright
from PIL import Image, ImageStat  # 用于检查图片质量

# ================= 配置区 =================
WATCHLIST_URL = "https://www.tradingview.com/watchlists/191753745/"
USER_DATA_DIR = os.path.abspath("tv_user_data")
BASE_DIR = os.path.abspath("TradingView_Reports")

# 强制不隐藏窗口，确保 WebGL 稳定
HEADLESS_IN_AUTO = False 

# 基础配置
LOAD_WAIT_TIME = 12   # 初始等待时间 (秒)
MAX_RETRIES = 3       # 每个图层最多尝试 3 次
MIN_FILE_SIZE = 30000 # 最小文件大小 (30KB)，小于此值判定为坏图

INTERVALS = {
    "Daily": "D",
    "Weekly": "W",
    "Monthly": "M",
    "Yearly": "12M"
}
# =========================================

def format_duration(seconds):
    mins, secs = divmod(int(seconds), 60)
    return f"{mins}分{secs}秒" if mins > 0 else f"{secs}秒"

def is_image_bad(img_path):
    """
    检查图片是否异常：
    1. 文件太小 (通常是没加载出来)
    2. 颜色太单一 (标准差太低通常是全白、全黑或只有一个加载圆圈)
    """
    try:
        if not os.path.exists(img_path): return True
        # 1. 检查文件大小
        if os.path.getsize(img_path) < MIN_FILE_SIZE:
            return True 
        
        # 2. 检查颜色分布 (标准差)
        with Image.open(img_path) as img:
            # 转换为灰度图计算像素分布
            stat = ImageStat.Stat(img.convert('L'))
            stddev = stat.stddev[0]
            # 标准差 < 8 通常意味着图片几乎是纯色的（空白或只有极少量像素）
            if stddev < 8:
                return True
        return False
    except Exception as e:
        print(f"   ⚠️ 图片分析出错: {e}")
        return True

def parse_tv_symbol(href):
    if not href: return None
    parsed = urllib.parse.urlparse(href)
    path_parts = [p for p in parsed.path.split('/') if p]
    if len(path_parts) < 2: return None
    ticker_part = path_parts[1]
    query_params = urllib.parse.parse_qs(parsed.query)
    if 'exchange' in query_params:
        return f"{query_params['exchange'][0]}:{ticker_part}"
    if "-" in ticker_part:
        return ticker_part.replace("-", ":", 1)
    return f"TVC:{ticker_part}"

def fetch_symbols(page):
    print(f"📡 正在同步 Watchlist 列表...")
    page.goto(WATCHLIST_URL, wait_until="domcontentloaded", timeout=90000)
    try:
        page.wait_for_selector('[data-qa-id="column-symbol"]', timeout=45000)
    except:
        print("❌ 未能加载列表，请检查网络。")
        return []
    page.mouse.wheel(0, 5000)
    time.sleep(3)
    links = page.query_selector_all('[data-qa-id="column-symbol"] a')
    symbols = []
    for link in links:
        href = link.get_attribute("href")
        sym = parse_tv_symbol(href)
        if sym and sym not in symbols: symbols.append(sym)
    return symbols

def generate_standard_html(symbols):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    html_template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>复盘报告</title>
        <style>
            body {{ font-family: -apple-system, sans-serif; background: #f2f4f7; color: #131722; margin: 0; padding: 20px; }}
            .nav {{ position: sticky; top: 0; background: rgba(255, 255, 255, 0.9); backdrop-filter: blur(8px); padding: 12px; z-index: 100; border-bottom: 1px solid #d1d4dc; margin-bottom: 30px; text-align: center; }}
            .nav a {{ color: #2962ff; margin: 0 10px; text-decoration: none; font-size: 13px; font-weight: bold; padding: 5px 10px; border-radius: 4px; }}
            .symbol-section {{ margin-bottom: 40px; padding: 25px; border-radius: 12px; background: #fff; border: 1px solid #e0e3eb; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }}
            .symbol-title {{ font-size: 22px; margin-bottom: 20px; border-left: 6px solid #2962ff; padding-left: 15px; font-weight: bold; }}
            .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(600px, 1fr)); gap: 20px; }}
            .card {{ background: #fff; border-radius: 8px; overflow: hidden; border: 1px solid #e0e3eb; }}
            .card img {{ width: 100%; display: block; cursor: pointer; }}
            .card-label {{ padding: 10px; text-align: center; font-size: 13px; font-weight: 600; color: #434651; background: #f8f9fb; }}
        </style>
    </head>
    <body>
        <h1 style="text-align:center;">市场全景复盘报告</h1>
        <div class="nav">
            <a href="#watchlist_quotes">📋 报价单</a>
            {" ".join([f'<a href="#{s.replace(":", "_")}">{s.split(":")[-1]}</a>' for s in symbols])}
        </div>
        <div style="text-align:center; margin-bottom:40px;">
            <img id="watchlist_quotes" src="00_Watchlist_Quotes.png" style="max-width:800px; border:1px solid #ddd;" onerror="this.style.display='none'">
        </div>
    """
    for symbol in symbols:
        s_id = symbol.replace(":", "_")
        html_template += f'<div class="symbol-section" id="{s_id}"><div class="symbol-title">{symbol}</div><div class="grid">'
        for name in INTERVALS.keys():
            html_template += f'<div class="card"><img src="{s_id}/{name}.png" onclick="window.open(this.src)"><div class="card-label">{name}</div></div>'
        html_template += "</div></div>"
    html_template += f"<p style='text-align:center; color:#999;'>更新时间: {now_str}</p></body></html>"
    
    path = os.path.join(BASE_DIR, "index.html")
    with open(path, "w", encoding="utf-8") as f: f.write(html_template)
    return path

def main():
    start_all = time.time()
    args = [a.lower() for a in sys.argv]
    
    if "clean" in args:
        if os.path.exists(USER_DATA_DIR): shutil.rmtree(USER_DATA_DIR)
        if os.path.exists(BASE_DIR): shutil.rmtree(BASE_DIR)
        print("✅ 缓存目录已清理。"); return

    is_setup = "setup" in args
    if not os.path.exists(BASE_DIR): os.makedirs(BASE_DIR)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            USER_DATA_DIR, headless=HEADLESS_IN_AUTO, 
            args=['--disable-blink-features=AutomationControlled'],
            viewport={'width': 1920, 'height': 1080}, device_scale_factor=2
        )
        page = context.pages[0] if context.pages else context.new_page()
        
        if is_setup:
            page.goto("https://www.tradingview.com/", wait_until="domcontentloaded")
            input("💡 [Setup模式] 请登录并调整好图表布局，完成后在此按回车继续...")
        
        # 1. 获取列表
        all_symbols = fetch_symbols(page)
        if not all_symbols: 
            print("❌ 未获取到品种，程序终止。")
            context.close()
            return

        # 2. 截图报价单
        print("📸 正在截取报价单...")
        page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded")
        time.sleep(8)
        try:
            page.mouse.click(1850, 500)
            page.locator(".layout__area--right").screenshot(path=os.path.join(BASE_DIR, "00_Watchlist_Quotes.png"))
        except: pass

        # 3. 品种循环截图 (带质量自检重试)
        t2 = time.time()
        for i, symbol in enumerate(all_symbols):
            print(f"📸 [{i+1}/{len(all_symbols)}] 处理品种: {symbol}")
            s_folder = os.path.join(BASE_DIR, symbol.replace(":", "_"))
            os.makedirs(s_folder, exist_ok=True)
            
            for name, inv in INTERVALS.items():
                url = f"https://www.tradingview.com/chart/?symbol={symbol}&interval={inv}"
                save_path = os.path.join(s_folder, f"{name}.png")
                
                # --- 重试逻辑开始 ---
                for attempt in range(1, MAX_RETRIES + 1):
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=60000)
                        page.wait_for_selector(".chart-container-border", timeout=30000)
                        
                        # 物理唤醒：点击图表中心并稍微等待渲染
                        page.mouse.click(600, 500)
                        
                        # 阶梯式等待时间 (第一次12s, 第二次17s, 第三次22s)
                        current_wait = LOAD_WAIT_TIME + (attempt - 1) * 5
                        time.sleep(current_wait)
                        
                        # 执行截图
                        page.locator(".chart-container-border").screenshot(path=save_path)
                        
                        # 检查图片是否合格
                        if not is_image_bad(save_path):
                            if attempt > 1: print(f"   ✅ 第 {attempt} 次重试成功")
                            break # 图片合格，跳出重试循环
                        else:
                            print(f"   ⚠️ 第 {attempt} 次截图质量差(转圈或空白)，正在重试...")
                            if attempt == MAX_RETRIES:
                                print(f"   ❌ 已达到最大重试次数，可能网络确实太慢。")
                    except Exception as e:
                        print(f"   ❌ 第 {attempt} 次尝试异常: {str(e)[:40]}")
                # --- 重试逻辑结束 ---
            
        print(f"⏱️ 截图任务完成，耗时: {format_duration(time.time()-t2)}")
        context.close()

    # 4. 报告生成
    web_path = generate_standard_html(all_symbols)
    print(f"🏁 【全部完成】总运行耗时: {format_duration(time.time()-start_all)}")
    webbrowser.open(f"file://{web_path}")

if __name__ == "__main__":
    main()