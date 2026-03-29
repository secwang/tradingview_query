import os, sys, time, shutil, webbrowser, urllib.parse, argparse, asyncio, random, base64, json
from datetime import datetime
from playwright.async_api import async_playwright
from PIL import Image, ImageStat

# ================= 配置区 =================

WL = "https://www.tradingview.com/watchlists/191753745/"
UD = os.path.abspath("tv_user_data")
BD = os.path.abspath("tv_cache")       # 中间缓存目录
AD = os.path.abspath("tv_archive")     # 最终存档目录
MF_FILE = os.path.join(BD, "manifest.json")       # 任务清单文件
LW, MR, MF = 8, 3, 25000  # 基础等待秒, 最大重试次数, 最小字节校验
IV = {"Daily": "D", "Weekly": "W", "Monthly": "M", "Yearly": "12M"}
CONCURRENCY = 3  # 并发限制数

# 浏览器启动参数
HL_ARGS = ['--headless=new', '--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist', '--disable-gpu-sandbox']
BASE_ARGS = ['--disable-blink-features=AutomationControlled', '--disable-dev-shm-usage', '--no-sandbox']
CHART_JS = "()=>{const c=document.querySelectorAll('canvas');return c.length>2&&!!document.querySelector('.price-axis,.paneWrapper');}"

# ================= 辅助工具 =================

dur = lambda s: f"{s//60}分{s%60}秒" if s >= 60 else f"{s}秒"
get_wait = lambda base: max(2, base + random.uniform(-1.5, 2.5))

class Progress:
    """终端进度条管理"""
    def __init__(self, total):
        self.total = total
        self.done = 0
        self.lock = asyncio.Lock()

    async def update(self, s, n, status="✅"):
        async with self.lock:
            self.done += 1
            pct = (self.done / self.total) * 100
            bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
            sys.stdout.write(f"\r🚀 进度: |{bar}| {pct:.1f}% ({self.done}/{self.total}) | {status} {s} {n}    ")
            sys.stdout.flush()
            if self.done == self.total: print("\n✨ 任务已完成")

def bad(p):
    """检查图片是否加载失败"""
    try:
        if not os.path.exists(p) or os.path.getsize(p) < MF: return True
        with Image.open(p) as i:
            return ImageStat.Stat(i.convert('L')).stddev[0] < 8
    except: return True

def sym(h):
    """从URL中解析品种代码"""
    if not h: return None
    u = urllib.parse.urlparse(h); ps = [p for p in u.path.split('/') if p]
    if len(ps) < 2: return None
    t = ps[1]; q = urllib.parse.parse_qs(u.query)
    return f"{q['exchange'][0]}:{t}" if 'exchange' in q else t.replace("-", ":", 1) if "-" in t else f"TVC:{t}"

def to_b64(path):
    """将本地图片转为 Base64 编码字符串"""
    if not os.path.exists(path): return ""
    with open(path, "rb") as f:
        ext = path.split('.')[-1]
        return f"data:image/{ext};base64,{base64.b64encode(f.read()).decode()}"

# ================= 网页操作 =================

async def fetch(pg):
    print("📡 正在同步 Watchlist 列表...")
    await pg.goto(WL, wait_until="domcontentloaded", timeout=60000)
    try:
        await pg.wait_for_selector('[data-qa-id="column-symbol"]', timeout=30000)
    except:
        print("❌ 未能加载列表，请检查网络或 URL。"); return []
    await pg.mouse.wheel(0, 3000); await asyncio.sleep(2)
    elements = await pg.query_selector_all('[data-qa-id="column-symbol"] a')
    ss = [sym(await a.get_attribute("href")) for a in elements]
    r = list(dict.fromkeys(s for s in ss if s))
    print(f"✅ 共获取 {len(r)} 个品种")
    return r

async def wait_chart(pg, hl):
    try: await pg.wait_for_selector(".chart-container-border", timeout=15000, state="attached")
    except: pass
    if hl:
        try: await pg.wait_for_function(CHART_JS, timeout=20000, polling=500)
        except: pass
    await asyncio.sleep(get_wait(3))

async def screenshot(pg, p, hl):
    loc = pg.locator(".chart-container-border")
    if hl:
        bb = await loc.bounding_box() if await loc.count() > 0 else None
        if bb: await pg.screenshot(path=p, clip=bb)
        else: await pg.screenshot(path=p)
    else:
        await loc.screenshot(path=p)

async def shot_task(sem, ctx, s, n, iv, sf, hl, progress):
    async with sem:
        p = os.path.join(sf, f"{n}.png")
        pg = await ctx.new_page()
        success = False
        try:
            for a in range(1, MR + 1):
                try:
                    if a == 1: await asyncio.sleep(random.uniform(0, 3))
                    await pg.goto(f"https://www.tradingview.com/chart/?symbol={s}&interval={iv}",
                                  wait_until="domcontentloaded", timeout=60000)
                    await wait_chart(pg, hl)
                    await pg.mouse.move(10, 10)
                    await asyncio.sleep(get_wait(LW * a))
                    await screenshot(pg, p, hl)
                    if not bad(p):
                        success = True; break
                except: continue
            await progress.update(s, n, "✅" if success else "💀")
        finally:
            await pg.close()

async def shot_wl(pg, hl):
    print("📸 正在截取报价单概览...")
    await pg.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded")
    await asyncio.sleep(get_wait(10))
    try:
        await pg.add_style_tag(content="[data-name='details-pane'],[data-name='news-pane'],.resizer-3_ve2S35{border:none!important}.button-4m6_9f_9{display:none!important}")
        out = os.path.join(BD, "00_Watchlist_Quotes.png")
        for sel in [".widgetbar-widget-watchlist", ".layout__area--right"]:
            loc = pg.locator(sel)
            if await loc.count() > 0:
                if hl:
                    bb = await loc.bounding_box()
                    if bb: await pg.screenshot(path=out, clip=bb); return
                else: await loc.screenshot(path=out); return
        await pg.screenshot(path=out)
    except Exception as e: print(f"⚠️ 报价单截图失败: {e}")

# ================= 报告系统 =================

def gen_report(ss, archive=False):
    """
    生成报告。
    archive=False: 生成依赖本地文件的 HTML (存放在 tv_cache)
    archive=True: 生成全内嵌图片的单文件 HTML (存放在 tv_archive)
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    
    def get_img_src(sub_path):
        if not archive: return sub_path
        return to_b64(os.path.join(BD, sub_path))

    nav = ''.join(f'<a href="#{s.replace(":","")}">{s.split(":")[-1]}</a>' for s in ss)
    
    def make_card(s, n):
        sid = s.replace(":", "_")
        src = get_img_src(f"{sid}/{n}.png")
        return f'<div class="card"><img src="{src}" onclick="window.open(this.src)"><div class="card-label">{n}</div></div>'
    
    def make_sec(s):
        return f'<div class="symbol-section" id="{s.replace(":","")}"><div class="symbol-title">{s}</div><div class="grid">{"".join(make_card(s, n) for n in IV)}</div></div>'

    wl_src = get_img_src("00_Watchlist_Quotes.png")
    
    body = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>复盘报告_{ts}</title><style>
body{{font-family:-apple-system,sans-serif;background:#f2f4f7;margin:0;padding:20px}}
.nav{{position:sticky;top:0;background:rgba(255,255,255,.9);backdrop-filter:blur(8px);padding:12px;z-index:100;border-bottom:1px solid #d1d4dc;margin-bottom:30px;text-align:center}}
.nav a{{color:#2962ff;margin:0 10px;text-decoration:none;font-size:13px;font-weight:bold;padding:5px 10px;border-radius:4px}}
.symbol-section{{margin-bottom:40px;padding:25px;border-radius:12px;background:#fff;border:1px solid #e0e3eb}}
.symbol-title{{font-size:22px;margin-bottom:20px;border-left:6px solid #2962ff;padding-left:15px;font-weight:bold}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(600px,1fr));gap:20px}}
.card{{background:#fff;border-radius:8px;overflow:hidden;border:1px solid #e0e3eb;transition:0.2s}}
.card:hover{{box-shadow:0 4px 12px rgba(0,0,0,.1)}}
.card img{{width:100%;display:block;cursor:pointer}}
.card-label{{padding:10px;text-align:center;font-size:13px;font-weight:600;background:#f8f9fb}}
</style></head><body><h1 style="text-align:center;">市场全景复盘报告</h1>
<div class="nav"><a href="#watchlist_quotes">📋 报价概览</a>{nav}</div>
<div style="text-align:center;margin-bottom:40px;"><img id="watchlist_quotes" src="{wl_src}" style="max-width:450px;border:1px solid #ddd;border-radius:8px;" onerror="this.style.display='none'"></div>
{''.join(map(make_sec, ss))}
<p style="text-align:center;color:#999;margin-top:50px;">生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p></body></html>"""

    if archive:
        target = os.path.join(AD, f"Report_{ts}.html")
    else:
        target = os.path.join(BD, "index.html")
        
    with open(target, "w", encoding="utf-8") as f: f.write(body)
    return target

async def export_pdf(ctx, ss):
    """导出 PDF 至存档目录"""
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    print(f"🖨️ 正在导出 PDF 打印版 (Report_{ts}.pdf)...")
    
    pcard = lambda sid, n: f'<div class="card"><img src="{to_b64(os.path.join(BD, sid, f"{n}.png"))}"><div class="card-label">{n} Chart</div></div>'
    psec = lambda s: f'<div class="page"><div class="symbol-title">{s} 趋势全景</div><div class="grid">{"".join(pcard(s.replace(":","_"),n) for n in IV)}</div></div>'
    wl_b64 = to_b64(os.path.join(BD, "00_Watchlist_Quotes.png"))

    body = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><style>
@page{{size:A4 landscape;margin:0}}*{{box-sizing:border-box;-webkit-print-color-adjust:exact}}
body{{margin:0;padding:0;background:#fff;width:297mm;font-family:sans-serif}}
.page{{width:297mm;height:210mm;page-break-after:always;padding:10mm 15mm;display:flex;flex-direction:column;overflow:hidden}}
.symbol-title{{font-size:22px;color:#2962ff;border-left:5px solid #2962ff;padding-left:12px;margin-bottom:10px;font-weight:bold}}
.grid{{display:grid;grid-template-columns:1fr 1fr;grid-template-rows:1fr 1fr;gap:10px;flex:1}}
.card{{border:1px solid #d1d4dc;border-radius:6px;display:flex;flex-direction:column;overflow:hidden}}
.card img{{width:100%;height:88%;object-fit:contain;background:#fafafa}}
.card-label{{height:12%;text-align:center;font-size:11px;background:#f8f9fb;display:flex;align-items:center;justify-content:center;border-top:1px solid #d1d4dc}}
.cover{{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;border:2px solid #2962ff;margin:10px;border-radius:10px}}
</style></head><body>
<div class="page"><div class="cover"><h1 style="font-size:48px;margin-bottom:10px;">市场复盘报告</h1><p style="font-size:20px;color:#666;">TradingView Automated Report</p><div style="color:#999;margin-top:20px;">生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}</div></div></div>
<div class="page"><div class="symbol-title">实时报价概览 (Watchlist)</div><div style="flex:1;display:flex;align-items:center;justify-content:center;overflow:hidden;padding:20px;"><img src="{wl_b64}" style="max-height:100%;border:1px solid #d1d4dc;border-radius:4px;" onerror="this.style.display='none'"></div></div>
{''.join(map(psec, ss))}
</body></html>"""

    tmp = os.path.join(BD, "pdf_template.html")
    with open(tmp, "w", encoding="utf-8") as f: f.write(body)

    out_pdf = os.path.join(AD, f"Report_{ts}.pdf")
    pg = await ctx.new_page()
    await pg.goto(f"file://{os.path.abspath(tmp)}", wait_until="networkidle")
    await asyncio.sleep(3)
    await pg.pdf(path=out_pdf, format="A4", landscape=True, print_background=True)
    await pg.close()
    return out_pdf

# ================= 主程序 =================

async def main():
    ap = argparse.ArgumentParser(prog="TV_Robot", description="TradingView 自动化截图及存档工具")
    ap.add_argument("cmd", choices=["html", "pdf", "setup", "clean"], help="操作命令")
    ap.add_argument("-H", "--headless", action="store_true", help="启用无头模式")
    ap.add_argument("-C", "--cache", action="store_true", help="直接读取清单缓存生成报告，不请求网络")
    a = ap.parse_args()

    if a.cmd == "clean":
        for d in [UD, BD, AD]:
            if os.path.exists(d): shutil.rmtree(d)
        print("✅ 缓存、报告及存档目录已清理。"); return

    os.makedirs(BD, exist_ok=True)
    os.makedirs(AD, exist_ok=True)
    t0 = asyncio.get_event_loop().time()

    async with async_playwright() as p:
        la = BASE_ARGS + (HL_ARGS if a.headless else [])
        ctx = await p.chromium.launch_persistent_context(
            UD, headless=a.headless, args=la,
            viewport={'width': 1920, 'height': 1080},
            device_scale_factor=2
        )
        pg = ctx.pages[0] if ctx.pages else await ctx.new_page()

        if a.cmd == "setup":
            print("💡 进入设置模式，请在浏览器中登录。")
            await pg.goto("https://www.tradingview.com/")
            input("👉 完成设置后按回车退出...")
            await ctx.close(); return

        ss = []
        if not a.cache:
            # 正常执行模式
            ss = await fetch(pg)
            if not ss:
                print("❌ 未能获取到品种。"); await ctx.close(); return

            await shot_wl(pg, a.headless)

            total_tasks = len(ss) * len(IV)
            progress = Progress(total_tasks)
            sem = asyncio.Semaphore(CONCURRENCY)
            tasks = []

            print(f"🚀 开始并发截图 (并发数: {CONCURRENCY})...")
            for s in ss:
                sf = os.path.join(BD, s.replace(":", "_"))
                os.makedirs(sf, exist_ok=True)
                for n, iv in IV.items():
                    tasks.append(shot_task(sem, ctx, s, n, iv, sf, a.headless, progress))
            await asyncio.gather(*tasks)
            
            # 抓取结束后，保存本次成功的任务清单
            mf_data = {"symbols": ss, "last_run": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            with open(MF_FILE, "w", encoding="utf-8") as f:
                json.dump(mf_data, f, ensure_ascii=False, indent=2)
            print(f"📝 已更新任务清单: {MF_FILE}")
        else:
            # 缓存读取模式：优先读取清单文件
            if os.path.exists(MF_FILE):
                print(f"📦 正在从清单加载上一次任务数据 ({MF_FILE})...")
                with open(MF_FILE, "r", encoding="utf-8") as f:
                    mf_data = json.load(f)
                    ss = mf_data.get("symbols", [])
                print(f"✅ 清单加载成功，共 {len(ss)} 个品种，上次抓取时间: {mf_data.get('last_run')}")
            else:
                print("⚠️ 未找到清单文件，尝试扫描目录...")
                for item in os.listdir(BD):
                    if os.path.isdir(os.path.join(BD, item)):
                        ss.append(item.replace("_", ":", 1))
            
            if not ss:
                print("❌ 缓存读取失败：未找到有效数据。"); await ctx.close(); return

        # 生成报告
        gen_report(ss, archive=False)
        arc_html = gen_report(ss, archive=True)
        print(f"🏁 存档版 HTML 已生成: {arc_html}")

        if a.cmd == "pdf":
            pdf_path = await export_pdf(ctx, ss)
            print(f"🏁 存档版 PDF 已生成: {pdf_path}")
            webbrowser.open(f"file://{pdf_path}")
        else:
            webbrowser.open(f"file://{arc_html}")

        await ctx.close()

    print(f"✨ 任务完成，总耗时: {dur(int(asyncio.get_event_loop().time() - t0))}")
    print(f"📂 存档位置: {AD}")

if __name__ == "__main__":
    asyncio.run(main())