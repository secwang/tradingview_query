import os,sys,time,shutil,webbrowser,urllib.parse,argparse
from datetime import datetime
from playwright.sync_api import sync_playwright
from PIL import Image,ImageStat

WL="https://www.tradingview.com/watchlists/191753745/"
UD=os.path.abspath("tv_user_data")
BD=os.path.abspath("TradingView_Reports")
LW,MR,MF=8,3,25000
IV={"Daily":"D","Weekly":"W","Monthly":"M","Yearly":"12M"}

dur=lambda s:f"{s//60}分{s%60}秒" if s>=60 else f"{s}秒"

def bad(p):
    try:
        if not os.path.exists(p) or os.path.getsize(p)<MF:return True
        with Image.open(p) as i:return ImageStat.Stat(i.convert('L')).stddev[0]<8
    except:return True

def sym(h):
    if not h:return None
    u=urllib.parse.urlparse(h);ps=[p for p in u.path.split('/') if p]
    if len(ps)<2:return None
    t=ps[1];q=urllib.parse.parse_qs(u.query)
    return f"{q['exchange'][0]}:{t}" if 'exchange' in q else t.replace("-",":",1) if "-" in t else f"TVC:{t}"

def fetch(pg):
    print("📡 正在同步 Watchlist 列表...")
    pg.goto(WL,wait_until="domcontentloaded",timeout=60000)
    try:pg.wait_for_selector('[data-qa-id="column-symbol"]',timeout=30000)
    except:print("❌ 未能加载列表。");return[]
    pg.mouse.wheel(0,3000);time.sleep(2)
    ss=[sym(a.get_attribute("href")) for a in pg.query_selector_all('[data-qa-id="column-symbol"] a')]
    r=list(dict.fromkeys(s for s in ss if s))
    print(f"✅ 共获取 {len(r)} 个品种");return r

CHART_JS="()=>{const c=document.querySelectorAll('canvas');return c.length>2&&!!document.querySelector('.price-axis,.paneWrapper');}"

def wait_chart(pg,hl):
    try:pg.wait_for_selector(".chart-container-border",timeout=15000,state="attached")
    except:pass
    if hl:
        try:pg.wait_for_function(CHART_JS,timeout=20000,polling=500)
        except:pass
        time.sleep(3)

def screenshot(pg,p,hl):
    """headless 优先 bounding_box 裁剪，普通模式直接元素截图"""
    loc=pg.locator(".chart-container-border")
    if hl:
        bb=loc.bounding_box() if loc.count()>0 else None
        pg.screenshot(path=p,clip=bb) if bb else pg.screenshot(path=p)
    else:
        loc.screenshot(path=p)

def shot(pg,s,n,iv,sf,hl,idx,total):
    p=os.path.join(sf,f"{n}.png")
    for a in range(1,MR+1):
        try:
            pg.goto(f"https://www.tradingview.com/chart/?symbol={s}&interval={iv}",wait_until="domcontentloaded",timeout=60000)
            wait_chart(pg,hl)
            pg.mouse.move(10,10);time.sleep(LW*a)
            screenshot(pg,p,hl)
            if not bad(p):
                if a>1:print(f"   ✅ [{idx}/{total}] 第{a}次重试成功")
                return
            print(f"   ⚠️ [{idx}/{total}] {s}/{n} 第{a}次图像异常，重试...")
        except Exception as e:
            print(f"   ❌ [{idx}/{total}] {s}/{n} 第{a}次异常: {str(e)[:60]}")
    print(f"   💀 [{idx}/{total}] {s}/{n} 全部重试失败，跳过")

def shot_wl(pg,hl):
    print("📸 正在截取精简 Watchlist...")
    pg.goto("https://www.tradingview.com/chart/",wait_until="domcontentloaded");time.sleep(10)
    try:
        pg.add_style_tag(content="[data-name='details-pane'],[data-name='news-pane'],.resizer-3_ve2S35{border:none!important}.button-4m6_9f_9{display:none!important}")
        out=os.path.join(BD,"00_Watchlist_Quotes.png")
        for sel in[".widgetbar-widget-watchlist",".layout__area--right"]:
            loc=pg.locator(sel)
            if loc.count()>0:
                if hl:
                    bb=loc.bounding_box()
                    if bb:pg.screenshot(path=out,clip=bb);return
                else:loc.screenshot(path=out);return
        pg.screenshot(path=out)
    except Exception as e:print(f"   ⚠️ Watchlist 截图失败: {e}")

card =lambda sid,n:f'<div class="card"><img src="{sid}/{n}.png" onclick="window.open(this.src)"><div class="card-label">{n}</div></div>'
pcard=lambda sid,n:f'<div class="card"><img src="{sid}/{n}.png"><div class="card-label">{n} Chart</div></div>'
sec  =lambda s:f'<div class="symbol-section" id="{s.replace(":","_")}"><div class="symbol-title">{s}</div><div class="grid">{"".join(card(s.replace(":","_"),n) for n in IV)}</div></div>'
psec =lambda s:f'<div class="page"><div class="symbol-title">{s} 趋势全景</div><div class="grid">{"".join(pcard(s.replace(":","_"),n) for n in IV)}</div></div>'

def html(ss):
    nav=''.join(f'<a href="#{s.replace(":","_")}">{s.split(":")[-1]}</a>' for s in ss)
    body=f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>复盘报告</title><style>
body{{font-family:-apple-system,sans-serif;background:#f2f4f7;margin:0;padding:20px}}
.nav{{position:sticky;top:0;background:rgba(255,255,255,.9);backdrop-filter:blur(8px);padding:12px;z-index:100;border-bottom:1px solid #d1d4dc;margin-bottom:30px;text-align:center}}
.nav a{{color:#2962ff;margin:0 10px;text-decoration:none;font-size:13px;font-weight:bold;padding:5px 10px;border-radius:4px}}
.symbol-section{{margin-bottom:40px;padding:25px;border-radius:12px;background:#fff;border:1px solid #e0e3eb}}
.symbol-title{{font-size:22px;margin-bottom:20px;border-left:6px solid #2962ff;padding-left:15px;font-weight:bold}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(600px,1fr));gap:20px}}
.card{{background:#fff;border-radius:8px;overflow:hidden;border:1px solid #e0e3eb}}
.card img{{width:100%;display:block}}.card-label{{padding:10px;text-align:center;font-size:13px;font-weight:600;background:#f8f9fb}}
</style></head><body><h1 style="text-align:center;">市场复盘报告</h1>
<div class="nav"><a href="#watchlist_quotes">📋 报价单</a>{nav}</div>
<div style="text-align:center;margin-bottom:40px;"><img id="watchlist_quotes" src="00_Watchlist_Quotes.png" style="max-width:450px;border:1px solid #ddd;border-radius:8px;" onerror="this.style.display='none'"></div>
{''.join(map(sec,ss))}<p style="text-align:center;color:#999;">Updated:{datetime.now().strftime('%Y-%m-%d %H:%M')}</p></body></html>"""
    open(os.path.join(BD,"index.html"),"w",encoding="utf-8").write(body)
    return os.path.join(BD,"index.html")

def phtml(ss):
    now=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    body=f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><style>
@page{{size:A4 landscape;margin:0}}*{{box-sizing:border-box;-webkit-print-color-adjust:exact}}
body{{margin:0;padding:0;background:#fff;width:297mm;font-family:sans-serif}}
.page{{width:297mm;height:210mm;page-break-after:always;padding:10mm 15mm;display:flex;flex-direction:column;overflow:hidden}}
.symbol-title{{font-size:22px;color:#2962ff;border-left:5px solid #2962ff;padding-left:12px;margin-bottom:10px;font-weight:bold}}
.grid{{display:grid;grid-template-columns:1fr 1fr;grid-template-rows:1fr 1fr;gap:10px;flex:1}}
.card{{border:1px solid #d1d4dc;border-radius:6px;display:flex;flex-direction:column;overflow:hidden}}
.card img{{width:100%;height:88%;object-fit:contain;background:#fafafa}}
.card-label{{height:12%;text-align:center;font-size:11px;background:#f8f9fb;font-weight:bold;display:flex;align-items:center;justify-content:center;border-top:1px solid #d1d4dc}}
.cover{{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;border:2px solid #2962ff;margin:10px;border-radius:10px}}
</style></head><body>
<div class="page"><div class="cover"><h1 style="font-size:48px;color:#131722;margin-bottom:10px;">市场全景复盘报告</h1>
<p style="font-size:20px;color:#666;margin-bottom:30px;">TradingView Automated Report</p>
<div style="text-align:center;color:#999;font-size:14px;">生成时间:{now}<br>品种总数:{len(ss)}</div></div></div>
<div class="page"><div class="symbol-title">报价概览(精简版)</div>
<div style="flex:1;display:flex;align-items:flex-start;justify-content:center;overflow:hidden;padding-top:10px;">
<img src="00_Watchlist_Quotes.png" style="height:100%;width:auto;max-width:450px;border:1px solid #d1d4dc;border-radius:4px;" onerror="this.style.display='none'"></div></div>
{''.join(map(psec,ss))}</body></html>"""
    p=os.path.join(BD,"pdf_template.html")
    open(p,"w",encoding="utf-8").write(body);return p

HL_ARGS=['--headless=new','--use-gl=swiftshader','--enable-webgl','--ignore-gpu-blocklist','--disable-gpu-sandbox']
BASE_ARGS=['--disable-blink-features=AutomationControlled','--disable-dev-shm-usage','--no-sandbox']

def launch(p,hl):
    la=BASE_ARGS+(HL_ARGS if hl else [])
    ctx=p.chromium.launch_persistent_context(UD,headless=False,args=la,viewport={'width':1920,'height':1080},device_scale_factor=2)
    return ctx,ctx.pages[0] if ctx.pages else ctx.new_page()

def cached_symbols():
    if not os.path.exists(BD):return[]
    ss=[d.replace("_",":",1) for d in os.listdir(BD) if os.path.isdir(os.path.join(BD,d))]
    return sorted(ss)

def export_pdf(ctx,ss):
    print("🖨️ 正在导出 PDF...")
    pp=phtml(ss);op=os.path.join(BD,f"Report_{datetime.now().strftime('%m%d_%H%M')}.pdf")
    pg2=ctx.new_page();pg2.goto(f"file://{pp}",wait_until="networkidle");time.sleep(4)
    pg2.pdf(path=op,format="A4",landscape=True,print_background=True)
    print(f"🏁 PDF 已生成: {op}");webbrowser.open(f"file://{op}")

def main():
    ap=argparse.ArgumentParser(prog="tv",description="TradingView 自动复盘")
    ap.add_argument("cmd",choices=["html","pdf","setup","clean"])
    ap.add_argument("-H","--headless",action="store_true",help="无头模式")
    ap.add_argument("--cache",action="store_true",help="使用本地截图缓存，跳过抓取")
    a=ap.parse_args()

    t0=time.time()
    if a.cmd=="clean":
        [shutil.rmtree(d) for d in[UD,BD] if os.path.exists(d)];print("✅ 目录已清理。");return
    os.makedirs(BD,exist_ok=True)

    if a.cache:
        ss=cached_symbols()
        if not ss:print("❌ 本地无截图缓存，请先运行 make run 或 make run-hl。");return
        print(f"📂 使用本地缓存，共 {len(ss)} 个品种")
        if a.cmd=="pdf":
            with sync_playwright() as p:
                ctx,_=launch(p,a.headless);export_pdf(ctx,ss);ctx.close()
        else:
            rp=html(ss);print(f"🏁 Web报告已生成: {rp}");webbrowser.open(f"file://{rp}")
        print(f"✨ 总耗时: {dur(int(time.time()-t0))}");return

    with sync_playwright() as p:
        ctx,pg=launch(p,a.headless)
        if a.cmd=="setup":
            pg.goto("https://www.tradingview.com/",wait_until="domcontentloaded");input("💡 Setup: 调整好后回车...");ctx.close();return
        ss=fetch(pg)
        if not ss:ctx.close();return
        shot_wl(pg,a.headless)
        t1=time.time();total=len(ss)*len(IV)
        for i,s in enumerate(ss):
            sf=os.path.join(BD,s.replace(":","_"));os.makedirs(sf,exist_ok=True)
            for j,(n,iv) in enumerate(IV.items()):
                idx=i*len(IV)+j+1
                print(f"📸 [{idx}/{total}] {s} / {n}")
                shot(pg,s,n,iv,sf,a.headless,idx,total)
        print(f"⏱️ 截图耗时: {dur(int(time.time()-t1))}")
        if a.cmd=="pdf":export_pdf(ctx,ss)
        else:rp=html(ss);print(f"🏁 Web报告已生成: {rp}");webbrowser.open(f"file://{rp}")
        ctx.close()
    print(f"✨ 总耗时: {dur(int(time.time()-t0))}")

if __name__=="__main__":main()