import os
import time
import sys
import shutil
import webbrowser
import urllib.parse
from datetime import datetime
from playwright.sync_api import sync_playwright

# ================= 配置区 =================
WATCHLIST_URL = "https://www.tradingview.com/watchlists/191753745/"
USER_DATA_DIR = os.path.abspath("tv_user_data")
BASE_DIR = os.path.abspath("TradingView_Reports")

# 强制不隐藏窗口，以便观察和确保渲染
HEADLESS_IN_AUTO = False 

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

def scan_local_cache():
    symbols = []
    if not os.path.exists(BASE_DIR): return []
    for entry in os.listdir(BASE_DIR):
        full_path = os.path.join(BASE_DIR, entry)
        if os.path.isdir(full_path) and "_" in entry:
            symbols.append(entry.replace("_", ":"))
    return sorted(symbols)

def wait_for_chart_ready(page, timeout=45000):
    """
    【核心改进】确保图表加载完成的函数
    1. 等待图表容器出现
    2. 等待价格坐标轴(Price Axis)渲染出数字
    3. 等待左上角图例(Legend)渲染出价格
    """
    try:
        # 等待主框架可见
        page.wait_for_selector(".chart-container-border", state="visible", timeout=timeout)
        
        # 关键：检查价格坐标轴是否有文字（有文字 = 数据已下发并渲染）
        # 我们检查右侧价格轴容器是否包含内容
        page.wait_for_function("""
            () => {
                const axis = document.querySelector('.price-axis-root');
                return axis && axis.innerText.trim().length > 0;
            }
        """, timeout=timeout)

        # 关键：检查左上角指标/价格图例是否有数值
        page.wait_for_selector(".legend-item-alias", state="visible", timeout=timeout)

        # 模拟鼠标微动，触发 WebGL 强制重绘，防止空白
        page.mouse.move(200, 200)
        time.sleep(0.5)
        page.mouse.move(202, 202)
        
        # 给渲染留 1.5 秒的最后稳定期
        time.sleep(1.5)
        return True
    except Exception as e:
        print(f"   ⚠️ 图表加载检测超时或异常: {str(e)[:50]}")
        return False

def fetch_symbols(page):
    print(f"📡 正在同步 Watchlist 列表...")
    page.goto(WATCHLIST_URL, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_selector('[data-qa-id="column-symbol"]', timeout=30000)
    except:
        print("❌ 未能加载列表，请检查网络或是否需要登录。")
        return []
    
    # 滚动一下确保懒加载列表全部出来
    page.mouse.wheel(0, 5000)
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
        <title>复盘报告 (Web)</title>
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
        <h1 style="text-align:center;">市场复盘报告 (Web滚动版)</h1>
        <div class="nav">
            <a href="#watchlist_quotes">📋 报价单概览</a>
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

def main():
    start_all = time.time()
    args = [a.lower() for a in sys.argv]
    
    if "clean" in args:
        if os.path.exists(USER_DATA_DIR): shutil.rmtree(USER_DATA_DIR)
        if os.path.exists(BASE_DIR): shutil.rmtree(BASE_DIR)
        print("✅ 缓存与报告目录已清理。"); return

    is_setup, need_pdf, use_cache = "setup" in args, "pdf" in args, "--cache" in args
    if not os.path.exists(BASE_DIR): os.makedirs(BASE_DIR)

    if use_cache:
        print("📦 正在从本地缓存读取品种...")
        all_symbols = scan_local_cache()
    else:
        with sync_playwright() as p:
            # 即使不是 Setup，也保持 Headless=False，确保 WebGL 稳定渲染
            context = p.chromium.launch_persistent_context(
                USER_DATA_DIR, 
                headless=HEADLESS_IN_AUTO, 
                args=['--disable-blink-features=AutomationControlled'],
                viewport={'width': 1920, 'height': 1080}, 
                device_scale_factor=2
            )
            page = context.pages[0] if context.pages else context.new_page()
            
            if is_setup:
                page.goto("https://www.tradingview.com/", wait_until="domcontentloaded", timeout=60000)
                input("💡 [Setup] 请在浏览器中登录、调整好配色和布局后，在此按回车继续...")
            
            # --- 阶段1：同步列表 ---
            all_symbols = fetch_symbols(page)
            if not all_symbols: 
                print("❌ 无法获取品种列表，任务终止。")
                context.close()
                return

            # --- 阶段2：截图报价单 ---
            print("📸 正在截取报价单 (Watchlist)...")
            page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded")
            time.sleep(5) # 报价单加载通常较快
            try: 
                page.locator(".layout__area--right").screenshot(path=os.path.join(BASE_DIR, "00_Watchlist_Quotes.png"))
            except: 
                print("   ⚠️ 报价单截图失败")

            # --- 阶段3：品种循环截图 ---
            t2 = time.time()
            for i, symbol in enumerate(all_symbols):
                print(f"📸 [{i+1}/{len(all_symbols)}] 正在处理: {symbol}")
                s_folder = os.path.join(BASE_DIR, symbol.replace(":", "_"))
                os.makedirs(s_folder, exist_ok=True)
                
                for name, inv in INTERVALS.items():
                    url = f"https://www.tradingview.com/chart/?symbol={symbol}&interval={inv}"
                    
                    # 尝试最多 2 次加载
                    for attempt in range(2):
                        try:
                            page.goto(url, wait_until="domcontentloaded", timeout=60000)
                            if wait_for_chart_ready(page):
                                # 截取图表主体
                                page.locator(".chart-container-border").screenshot(path=os.path.join(s_folder, f"{name}.png"))
                                break # 成功则跳出重试
                            else:
                                if attempt == 0: print(f"   🔄 {name} 加载不完整，正在重试...")
                                page.reload()
                        except Exception as e:
                            print(f"   ❌ {symbol} {name} 尝试 {attempt+1} 失败: {str(e)[:30]}")
                            
            print(f"⏱️ 品种截图全部完成，耗时: {format_duration(time.time()-t2)}")
            context.close()

    # --- 阶段4：报告生成 ---
    web_path = generate_standard_html(all_symbols)
    print(f"🏁 【全部完成】总运行耗时: {format_duration(time.time()-start_all)}")
    print(f"报告已生成至: {web_path}")
    webbrowser.open(f"file://{web_path}")

if __name__ == "__main__":
    main()