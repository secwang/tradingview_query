import os
import time
import sys
import shutil
import webbrowser
import urllib.parse
from datetime import datetime
from playwright.sync_api import sync_playwright
from PIL import Image, ImageStat  # pip install Pillow

# ================= 配置区 =================
WATCHLIST_URL = "https://www.tradingview.com/watchlists/191753745/"
USER_DATA_DIR = os.path.abspath("tv_user_data")
BASE_DIR = os.path.abspath("TradingView_Reports")

# 自动运行模式是否隐藏窗口
HEADLESS_IN_AUTO = False 

# 核心效率配置
LOAD_WAIT_TIME = 6    # 初始等待6秒
MAX_RETRIES = 3       # 失败后最多试3次
MIN_FILE_SIZE = 25000 # 25KB

INTERVALS = {
    "Daily": "D",
    "Weekly": "W",
    "Monthly": "M",
    "Yearly": "12M"
}
# =========================================

def format_duration(seconds):
    """格式化秒数为 分:秒"""
    mins, secs = divmod(int(seconds), 60)
    return f"{mins}分{secs}秒" if mins > 0 else f"{secs}秒"

def is_image_bad(img_path):
    """通过像素分析检查图片是否为转圈或空白"""
    try:
        if not os.path.exists(img_path): return True
        if os.path.getsize(img_path) < MIN_FILE_SIZE: return True
        with Image.open(img_path) as img:
            stat = ImageStat.Stat(img.convert('L'))
            stddev = stat.stddev[0]
            if stddev < 8: return True 
        return False
    except:
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
    page.goto(WATCHLIST_URL, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_selector('[data-qa-id="column-symbol"]', timeout=30000)
    except:
        print("❌ 未能加载列表。")
        return []
    page.mouse.wheel(0, 3000)
    time.sleep(2)
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
            .card img {{ width: 100%; display: block; }}
            .card-label {{ padding: 10px; text-align: center; font-size: 13px; font-weight: 600; color: #434651; background: #f8f9fb; }}
        </style>
    </head>
    <body>
        <h1 style="text-align:center;">市场复盘报告</h1>
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
    html_template += f"<p style='text-align:center; color:#999;'>Updated: {now_str}</p></body></html>"
    
    path = os.path.join(BASE_DIR, "index.html")
    with open(path, "w", encoding="utf-8") as f: f.write(html_template)
    return path

def generate_pdf_html(symbols):
    now_full = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html_template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            @page {{ size: A4 landscape; margin: 0; }}
            * {{ box-sizing: border-box; -webkit-print-color-adjust: exact; }}
            body {{ margin: 0; padding: 0; background: #fff; width: 297mm; font-family: sans-serif; }}
            .page {{ 
                width: 297mm; height: 210mm; 
                page-break-after: always; padding: 10mm 15mm; 
                display: flex; flex-direction: column; position: relative; overflow: hidden;
            }}
            .symbol-title {{ 
                font-size: 22px; color: #2962ff; border-left: 5px solid #2962ff; 
                padding-left: 12px; margin-bottom: 10px; font-weight: bold; 
            }}
            .grid {{ display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr; gap: 10px; flex: 1; }}
            .card {{ border: 1px solid #d1d4dc; border-radius: 6px; display: flex; flex-direction: column; overflow: hidden; }}
            .card img {{ width: 100%; height: 88%; object-fit: contain; background: #fafafa; }}
            .card-label {{ height: 12%; text-align: center; font-size: 11px; background: #f8f9fb; font-weight: bold; display: flex; align-items: center; justify-content: center; border-top: 1px solid #d1d4dc; }}
            .cover {{ 
                display: flex; flex-direction: column; align-items: center; justify-content: center; 
                height: 100%; border: 2px solid #2962ff; margin: 10px; border-radius: 10px;
            }}
        </style>
    </head>
    <body>
        <!-- 封面页 -->
        <div class="page">
            <div class="cover">
                <h1 style="font-size: 48px; color: #131722; margin-bottom: 10px;">市场全景复盘报告</h1>
                <p style="font-size: 20px; color: #666; margin-bottom: 30px;">TradingView Automated Landscape Report</p>
                <div style="text-align: center; color: #999; font-size: 14px;">
                    生成时间: {now_full} <br>
                    品种总数: {len(symbols)}
                </div>
            </div>
        </div>

        <!-- 报价单页 -->
        <div class="page">
            <div class="symbol-title">实时报价概览 (Watchlist)</div>
            <div style="flex: 1; display: flex; align-items: center; justify-content: center; overflow: hidden;">
                <img src="00_Watchlist_Quotes.png" style="max-width: 95%; max-height: 90%; object-fit: contain; border: 1px solid #d1d4dc;" onerror="this.style.display='none'">
            </div>
        </div>
    """
    for symbol in symbols:
        s_id = symbol.replace(":", "_")
        html_template += f"""<div class="page">
            <div class="symbol-title">{symbol} 趋势全景</div>
            <div class="grid">"""
        for name in INTERVALS.keys():
            html_template += f'<div class="card"><img src="{s_id}/{name}.png"><div class="card-label">{name} Chart</div></div>'
        html_template += "</div></div>"
    
    html_template += "</body></html>"
    path = os.path.join(BASE_DIR, "pdf_template.html")
    with open(path, "w", encoding="utf-8") as f: f.write(html_template)
    return path

def main():
    start_all = time.time()
    args = [a.lower() for a in sys.argv]
    is_setup, need_pdf = "setup" in args, "pdf" in args

    if "clean" in args:
        if os.path.exists(USER_DATA_DIR): shutil.rmtree(USER_DATA_DIR)
        if os.path.exists(BASE_DIR): shutil.rmtree(BASE_DIR)
        print("✅ 目录已清理。"); return

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
            input("💡 [Setup] 调整好后回车...")
        
        # 1. 同步列表
        all_symbols = fetch_symbols(page)
        if not all_symbols: context.close(); return

        # 2. 截图报价单
        print("📸 正在截取报价单...")
        page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded")
        time.sleep(8)
        try:
            page.mouse.click(1850, 500)
            page.locator(".layout__area--right").screenshot(path=os.path.join(BASE_DIR, "00_Watchlist_Quotes.png"))
        except: pass

        # 3. 循环截图
        t2 = time.time()
        for i, symbol in enumerate(all_symbols):
            print(f"📸 [{i+1}/{len(all_symbols)}] 处理: {symbol}")
            s_folder = os.path.join(BASE_DIR, symbol.replace(":", "_"))
            os.makedirs(s_folder, exist_ok=True)
            
            for name, inv in INTERVALS.items():
                url = f"https://www.tradingview.com/chart/?symbol={symbol}&interval={inv}"
                save_path = os.path.join(s_folder, f"{name}.png")
                
                for attempt in range(1, MAX_RETRIES + 1):
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=60000)
                        page.wait_for_selector(".chart-container-border", timeout=20000)
                        page.mouse.click(600, 500)
                        
                        time.sleep(LOAD_WAIT_TIME * attempt) # 阶梯式等待
                        page.locator(".chart-container-border").screenshot(path=save_path)
                        
                        if not is_image_bad(save_path):
                            if attempt > 1: print(f"   ✅ 第 {attempt} 次重试抓取成功")
                            break
                        else:
                            print(f"   ⚠️ 第 {attempt} 次尝试图像异常，正在重试...")
                    except Exception as e:
                        print(f"   ❌ 第 {attempt} 次异常: {str(e)[:30]}")
        
        print(f"⏱️ 截图耗时: {format_duration(time.time()-t2)}")
        
        # 4. 报告生成
        generate_standard_html(all_symbols)
        if need_pdf:
            print("🖨️ 正在导出 PDF (包含首页和 Watchlist)...")
            pdf_html = generate_pdf_html(all_symbols)
            pdf_path = os.path.join(BASE_DIR, f"Report_{datetime.now().strftime('%m%d_%H%M')}.pdf")
            pdf_page = context.new_page()
            pdf_page.goto(f"file://{pdf_html}", wait_until="networkidle")
            time.sleep(3) # 给图片一点加载时间
            pdf_page.pdf(
                path=pdf_path, 
                format="A4", 
                landscape=True, 
                print_background=True,
                margin={"top": "0in", "bottom": "0in", "left": "0in", "right": "0in"}
            )
            print(f"🏁 PDF 已生成: {pdf_path}")
            webbrowser.open(f"file://{pdf_path}")
        else:
            print(f"🏁 Web报告已生成: {os.path.join(BASE_DIR, 'index.html')}")
            webbrowser.open(f"file://{os.path.join(BASE_DIR, 'index.html')}")

        context.close()
        print(f"✨ 总耗时: {format_duration(time.time()-start_all)}")

if __name__ == "__main__":
    main()