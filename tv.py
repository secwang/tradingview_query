import os, sys, time, shutil, webbrowser, urllib.parse, argparse, asyncio, random, base64, json, subprocess
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

# 浏览器参数
HL_ARGS = ['--headless=new', '--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist', '--disable-gpu-sandbox']
BASE_ARGS = ['--disable-blink-features=AutomationControlled', '--disable-dev-shm-usage', '--no-sandbox']
CHART_JS = "()=>{const c=document.querySelectorAll('canvas');return c.length>2&&!!document.querySelector('.price-axis,.paneWrapper');}"

# ================= 辅助工具 =================

dur = lambda s: f"{s//60}分{s%60}秒" if s >= 60 else f"{s}秒"
get_wait = lambda base: max(2, base + random.uniform(-1.5, 2.5))

class Progress:
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
    try:
        if not os.path.exists(p) or os.path.getsize(p) < MF: return True
        with Image.open(p) as i:
            return ImageStat.Stat(i.convert('L')).stddev[0] < 8
    except: return True

def sym(h):
    if not h: return None
    u = urllib.parse.urlparse(h); ps = [p for p in u.path.split('/') if p]
    if len(ps) < 2: return None
    t = ps[1]; q = urllib.parse.parse_qs(u.query)
    return f"{q['exchange'][0]}:{t}" if 'exchange' in q else t.replace("-", ":", 1) if "-" in t else f"TVC:{t}"

def to_b64(path):
    if not os.path.exists(path): return ""
    with open(path, "rb") as f:
        ext = path.split('.')[-1]
        return f"data:image/{ext};base64,{base64.b64encode(f.read()).decode()}"

# ================= 网页操作 =================

async def fetch(pg):
    print("📡 正在同步 Watchlist 列表...")
    await pg.goto(WL, wait_until="domcontentloaded", timeout=60000)
    try: await pg.wait_for_selector('[data-qa-id="column-symbol"]', timeout=30000)
    except: print("❌ 列表加载失败"); return []
    await pg.mouse.wheel(0, 3000); await asyncio.sleep(2)
    elements = await pg.query_selector_all('[data-qa-id="column-symbol"] a')
    ss = [sym(await a.get_attribute("href")) for a in elements]
    r = list(dict.fromkeys(s for s in ss if s))
    print(f"✅ 获取到 {len(r)} 个品种")
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
        bb = await loc.bounding_box()
        if bb: await pg.screenshot(path=p, clip=bb)
        else: await pg.screenshot(path=p)
    else: await loc.screenshot(path=p)

async def shot_task(sem, ctx, s, n, iv, sf, hl, progress):
    async with sem:
        p = os.path.join(sf, f"{n}.png")
        pg = await ctx.new_page()
        success = False
        try:
            for a in range(1, MR + 1):
                try:
                    await pg.goto(f"https://www.tradingview.com/chart/?symbol={s}&interval={iv}", wait_until="domcontentloaded", timeout=60000)
                    await wait_chart(pg, hl); await pg.mouse.move(10, 10)
                    await asyncio.sleep(get_wait(LW * a))
                    await screenshot(pg, p, hl)
                    if not bad(p): success = True; break
                except: continue
            await progress.update(s, n, "✅" if success else "💀")
        finally: await pg.close()

async def shot_wl(pg, hl):
    print("📸 截取报价单概览...")
    await pg.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded")
    await asyncio.sleep(10)
    try:
        await pg.add_style_tag(content="[data-name='details-pane'],[data-name='news-pane'],.resizer-3_ve2S35{border:none!important}.button-4m6_9f_9{display:none!important}")
        out = os.path.join(BD, "00_Watchlist_Quotes.png")
        loc = pg.locator(".widgetbar-widget-watchlist")
        if await loc.count() > 0:
            if hl:
                bb = await loc.bounding_box()
                if bb: await pg.screenshot(path=out, clip=bb)
            else: await loc.screenshot(path=out)
        else: await pg.screenshot(path=out)
    except: pass

# ================= 报告系统 =================

def gen_local_html(ss, ts):
    nav = ''.join(f'<a href="#{s.replace(":","")}">{s.split(":")[-1]}</a>' for s in ss)
    make_card = lambda s, n: f'<div class="card"><img src="{s.replace(":","_")}/{n}.png"><div class="card-label">{n}</div></div>'
    make_sec = lambda s: f'<div class="symbol-section" id="{s.replace(":","")}"><div class="symbol-title">{s}</div><div class="grid">{"".join(make_card(s, n) for n in IV)}</div></div>'
    
    body = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Report_{ts}</title><style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap');
body{{font-family:'Inter',sans-serif;background:#f2f4f7;margin:0;padding:20px;color:#131722}}
.nav{{position:sticky;top:0;background:rgba(255,255,255,.9);backdrop-filter:blur(8px);padding:12px;z-index:100;border-bottom:1px solid #d1d4dc;margin-bottom:30px;text-align:center}}
.nav a{{color:#2962ff;margin:0 10px;text-decoration:none;font-size:13px;font-weight:bold;padding:5px 10px;border-radius:4px}}
.symbol-section{{margin-bottom:40px;padding:25px;border-radius:12px;background:#fff;border:1px solid #e0e3eb;page-break-after:always}}
.symbol-title{{font-size:24px;margin-bottom:20px;border-left:6px solid #2962ff;padding-left:15px;font-weight:bold}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(600px,1fr));gap:20px}}
.card{{background:#fff;border-radius:8px;overflow:hidden;border:1px solid #e0e3eb}}
.card img{{width:100%;display:block}}
.card-label{{padding:12px;text-align:center;font-size:14px;font-weight:600;background:#f8f9fb}}
</style></head><body><h1 style="text-align:center;">市场全景复盘报告</h1>
<div class="nav"><a href="#watchlist_quotes">📋 报价概览</a>{nav}</div>
<div style="text-align:center;margin-bottom:40px;"><img id="watchlist_quotes" src="00_Watchlist_Quotes.png" style="max-width:450px;border:1px solid #ddd;border-radius:8px;"></div>
{''.join(map(make_sec, ss))}
<p style="text-align:center;color:#999;font-size:12px;">生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p></body></html>"""
    
    target = os.path.join(BD, "index.html")
    with open(target, "w", encoding="utf-8") as f: f.write(body)
    return target

async def run_monolith(input_html, ts):
    out = os.path.join(AD, f"tv_{ts}.html")
    print(f"📦 Monolith 打包存档...")
    proc = await asyncio.create_subprocess_exec('monolith', input_html, '-o', out, '--no-video', '--quiet', stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await proc.communicate()
    if proc.returncode == 0: return out
    print(f"❌ 打包失败: {stderr.decode()}"); return None

async def export_pdf(ctx, ss, ts):
    out = os.path.join(AD, f"tv_{ts}.pdf")
    print(f"🖨️ 导出 PDF...")
    pcard = lambda sid, n: f'<div class="card"><img src="{to_b64(os.path.join(BD, sid, f"{n}.png"))}"><div class="card-label">{n}</div></div>'
    psec = lambda s: f'<div class="page"><div class="symbol-title">{s}</div><div class="grid">{"".join(pcard(s.replace(":","_"),n) for n in IV)}</div></div>'
    body = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><style>
@page{{size:A4 landscape;margin:0}} body{{margin:0;padding:0;font-family:sans-serif;width:297mm}}
.page{{width:297mm;height:210mm;page-break-after:always;padding:10mm;display:flex;flex-direction:column}}
.symbol-title{{font-size:20px;color:#2962ff;font-weight:bold;margin-bottom:10px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;grid-template-rows:1fr 1fr;gap:10px;flex:1}}
.card{{border:1px solid #ddd;display:flex;flex-direction:column;overflow:hidden}}
.card img{{width:100%;height:85%;object-fit:contain;background:#fafafa}}
.card-label{{height:15%;text-align:center;font-size:12px;background:#f8f9fb;display:flex;align-items:center;justify-content:center}}
</style></head><body>{''.join(map(psec, ss))}</body></html>"""
    tmp = os.path.join(BD, "pdf_tmp.html")
    with open(tmp, "w", encoding="utf-8") as f: f.write(body)
    pg = await ctx.new_page()
    await pg.goto(f"file://{os.path.abspath(tmp)}", wait_until="networkidle")
    await pg.pdf(path=out, format="A4", landscape=True, print_background=True)
    await pg.close(); return out

# ================= 主程序 =================

async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["html", "pdf", "setup", "clean"])
    ap.add_argument("-H", "--headless", action="store_true")
    ap.add_argument("-C", "--cache", action="store_true")
    a = ap.parse_args()

    if a.cmd == "clean":
        for d in [BD, AD]: 
            if os.path.exists(d): shutil.rmtree(d)
        print("✅ 已清理"); return

    os.makedirs(BD, exist_ok=True); os.makedirs(AD, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    t0 = asyncio.get_event_loop().time()

    async with async_playwright() as p:
        la = BASE_ARGS + (HL_ARGS if a.headless else [])
        ctx = await p.chromium.launch_persistent_context(UD, headless=a.headless, args=la, viewport={'width':1920,'height':1080}, device_scale_factor=2)
        pg = ctx.pages[0] if ctx.pages else await ctx.new_page()

        if a.cmd == "setup":
            await pg.goto("https://www.tradingview.com/"); input("👉 登录后按回车退出..."); return

        ss = []
        if not a.cache:
            ss = await fetch(pg)
            if not ss: await ctx.close(); return
            await shot_wl(pg, a.headless)
            prog = Progress(len(ss)*len(IV)); sem = asyncio.Semaphore(CONCURRENCY); tasks = []
            for s in ss:
                sf = os.path.join(BD, s.replace(":","_")); os.makedirs(sf, exist_ok=True)
                for n, iv in IV.items(): tasks.append(shot_task(sem, ctx, s, n, iv, sf, a.headless, prog))
            await asyncio.gather(*tasks)
            with open(MF_FILE, "w") as f: json.dump({"symbols":ss, "ts":ts}, f)
        else:
            if os.path.exists(MF_FILE):
                with open(MF_FILE, "r") as f: d = json.load(f); ss = d.get("symbols", [])
            else:
                for i in os.listdir(BD): 
                    if os.path.isdir(os.path.join(BD,i)): ss.append(i.replace("_",":",1))
            if not ss: print("❌ 无缓存"); await ctx.close(); return

        if a.cmd == "html":
            tmp_h = gen_local_html(ss, ts)
            final = await run_monolith(tmp_h, ts)
            if final: webbrowser.open(f"file://{final}")
        elif a.cmd == "pdf":
            final = await export_pdf(ctx, ss, ts)
            if final: webbrowser.open(f"file://{final}")

        await ctx.close()
    print(f"✨ 完成! 耗时: {dur(int(asyncio.get_event_loop().time()-t0))} | 存档: {AD}")

if __name__ == "__main__":
    asyncio.run(main())