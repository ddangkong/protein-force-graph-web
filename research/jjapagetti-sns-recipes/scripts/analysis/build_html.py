# -*- coding: utf-8 -*-
"""Render the HTML report (artifact) from out/master.json + out/stats.json.
Narrative blocks (FINDINGS, RECIPE_CARDS, IMPLICATIONS, PLATFORM_NOTES) are edited by hand after reviewing data."""
import json, os, sys, re, collections, datetime
from html import escape
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tags import TAG_RULES, CATEGORY_LABEL, CATEGORY_ORDER, tag_text
from svg_charts import hbar_chart, grouped_hbar_chart, stacked_columns

SCRATCH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(SCRATCH, "out")
items = json.load(open(os.path.join(OUT, "master.json"), encoding="utf-8"))
st = json.load(open(os.path.join(OUT, "stats.json"), encoding="utf-8"))
jj = [i for i in items if i["mentions_jjapagetti"]]
TODAY = datetime.date.today().isoformat()

try:
    from narrative import FINDINGS, RECIPE_CARDS, IMPLICATIONS, PLATFORM_NOTES, TREND_NOTE, METHOD_NOTES
except ImportError:  # placeholders until narrative.py exists
    FINDINGS, RECIPE_CARDS, IMPLICATIONS, PLATFORM_NOTES, TREND_NOTE, METHOD_NOTES = [], [], [], {}, "", []


def sq(s, n=None):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    if n and len(s) > n:
        s = s[: n - 1] + "…"
    return escape(s)


def num(n):
    return f"{n:,}" if isinstance(n, (int, float)) and n is not None else "–"


def compact(n):
    if n is None:
        return "–"
    if n >= 1e8:
        return f"{n / 1e8:.1f}억"
    if n >= 1e4:
        return f"{n / 1e4:.1f}만"
    return f"{n:,}"


tagcat = {t: c for t, c, _ in TAG_RULES}


def count_tags(pred):
    c = collections.Counter()
    for i in jj:
        if pred(i):
            for t in i["tags"]:
                c[t] += 1
    return c


def count_cats(pred):
    c = collections.Counter()
    for i in jj:
        if pred(i):
            for cat in i["categories"]:
                c[cat] += 1
    return c


# ------------------------------------------------------------------ numbers
n_all = len(items)
n_jj = len(jj)
n_recipe = sum(1 for i in jj if i["recipe_like"])
n_2026 = sum(1 for i in jj if (i["date"] or "").startswith("2026"))
n_2025 = sum(1 for i in jj if (i["date"] or "").startswith("2025"))
n_comments = st.get("n_comments", 0)
plat_counts = collections.Counter(i["platform"] for i in jj)
plat_all = collections.Counter(i["platform"] for i in items)
tags_all = count_tags(lambda i: True)
tags_26 = count_tags(lambda i: (i["date"] or "").startswith("2026"))
tags_25 = count_tags(lambda i: (i["date"] or "").startswith("2025"))
cats_26 = count_cats(lambda i: (i["date"] or "").startswith("2026"))
cats_25 = count_cats(lambda i: (i["date"] or "").startswith("2025"))
cats_all = count_cats(lambda i: True)
comment_tags = dict(st.get("comment_tags", []))

# rising tags: share in 2026 vs 2025
def share(c, t):
    tot = sum(c.values()) or 1
    return c[t] / tot
rising = []
for t, _ in tags_all.most_common():
    if tags_26[t] + tags_25[t] >= 12:
        rising.append((t, share(tags_26, t) - share(tags_25, t), tags_26[t], tags_25[t]))
rising.sort(key=lambda x: -x[1])

# monthly by platform
months = []
y, m = 2025, 1
today = datetime.date.today()
while (y, m) <= (today.year, today.month):
    months.append(f"{y}-{m:02d}")
    m += 1
    if m > 12:
        y, m = y + 1, 1
mon = collections.defaultdict(collections.Counter)
for i in jj:
    if i["date"] and i["date"][:7] in set(months):
        mon[i["date"][:7]][i["platform"]] += 1
PLATS = ["YouTube", "TikTok", "Instagram", "Web"]
monthly_series = [(p, [mon[mo][p] for mo in months]) for p in PLATS]

# ------------------------------------------------------------------ charts
chart_cats = grouped_hbar_chart(
    [(CATEGORY_LABEL[c], [cats_26[c], cats_25[c]]) for c in CATEGORY_ORDER],
    ["2026년", "2025년"], "튜닝 카테고리별 게시물 수 (2026 vs 2025)")
chart_tags = hbar_chart([(t, n) for t, n in tags_all.most_common(24)], "세부 튜닝 태그 순위", top_n=24, width=470, label_w=205, bar_h=15, gap=7)
chart_tags26 = hbar_chart([(t, n) for t, n in tags_26.most_common(15)], "2026년 게시물 튜닝 태그 순위", top_n=15, color="var(--s2)", width=470, label_w=205, bar_h=15, gap=7)
chart_month = stacked_columns([mo[2:].replace("-", ".") for mo in months], monthly_series, "월별 게시물 수(플랫폼별)",
                              label_every=1 if len(months) <= 14 else 2)
chart_comments = hbar_chart(sorted(comment_tags.items(), key=lambda x: -x[1])[:15], "댓글에서 언급된 튜닝 태그", top_n=15, color="var(--s3)")


# ------------------------------------------------------------------ tables
def row_link(url, text="열기"):
    return f'<a href="{escape(url)}" target="_blank" rel="noopener">{text}</a>'


def tag_chips(tags, n=4):
    tags = list(tags)[:n]
    return "".join(f'<span class="chip">{escape(t)}</span>' for t in tags)


top_recent_yt = sorted([i for i in jj if i["platform"] == "YouTube" and (i["date"] or "") >= "2025-01-01"], key=lambda x: -(x["views"] or 0))[:25]
top_all_yt = sorted([i for i in jj if i["platform"] == "YouTube"], key=lambda x: -(x["views"] or 0))[:12]
recent_all = sorted([i for i in jj if i["date"] and i["recipe_like"]], key=lambda x: x["date"], reverse=True)
tt_videos = sorted([i for i in items if i["platform"] == "TikTok" and i["format"] == "video"], key=lambda x: x["date"] or "", reverse=True)
ig_posts = sorted([i for i in items if i["platform"] == "Instagram" and i["format"] in ("post", "reel")], key=lambda x: x["date"] or "", reverse=True)


def yt_table(rows, show_likes=True):
    h = ['<div class="tablewrap"><table><thead><tr><th>게시일</th><th>형식</th><th>제목</th><th>채널</th><th class="r">조회수</th>' +
         ('<th class="r">좋아요</th>' if show_likes else '') + '<th>튜닝 태그</th><th></th></tr></thead><tbody>']
    for i in rows:
        h.append(f'<tr><td class="mono">{i["date"] or ""}</td><td>{sq(i["format"])}</td><td class="t">{sq(i["title"], 90)}</td>'
                 f'<td>{sq(i["author"], 22)}</td><td class="r mono">{num(i["views"])}</td>' +
                 (f'<td class="r mono">{num(i["likes"])}</td>' if show_likes else '') +
                 f'<td>{tag_chips(i["tags"])}</td><td>{row_link(i["url"])}</td></tr>')
    h.append("</tbody></table></div>")
    return "\n".join(h)


def social_table(rows, caption_len=160):
    h = ['<div class="tablewrap"><table><thead><tr><th>게시일</th><th>계정</th><th>캡션(발췌)</th><th>튜닝 태그</th><th></th></tr></thead><tbody>']
    for i in rows:
        h.append(f'<tr><td class="mono">{i["date"] or ""}</td><td>{sq(i["author"], 22)}</td><td class="t">{sq(i["title"], caption_len)}</td>'
                 f'<td>{tag_chips(i["tags"])}</td><td>{row_link(i["url"])}</td></tr>')
    h.append("</tbody></table></div>")
    return "\n".join(h)


def latest_table(rows):
    h = ['<div class="tablewrap"><table id="latest"><thead><tr><th>게시일</th><th>플랫폼</th><th>제목/캡션</th><th>작성자</th><th class="r">조회수</th><th>튜닝 태그</th><th></th></tr></thead><tbody>']
    for k, i in enumerate(rows):
        fmt = "Shorts" if i["format"] == "Shorts" else ""
        h.append(f'<tr data-p="{i["platform"]}" data-k="{k}" class="{"hid" if k >= 120 else ""}"><td class="mono">{i["date"]}</td>'
                 f'<td><span class="pl pl-{i["platform"].lower()}">{i["platform"]}</span> <small>{fmt}</small></td>'
                 f'<td class="t">{sq(i["title"], 110)}</td><td>{sq(i["author"], 20)}</td><td class="r mono">{num(i["views"])}</td>'
                 f'<td>{tag_chips(i["tags"], 3)}</td><td>{row_link(i["url"])}</td></tr>')
    h.append("</tbody></table></div>")
    return "\n".join(h)


# comments
crow = []
for i in items:
    for c in i.get("comments") or []:
        tg = [t for t, _ in tag_text(c.get("text") or "")]
        if tg:
            try:
                lv = int(str(c.get("likes") or 0).replace(",", ""))
            except Exception:
                lv = 0
            crow.append((lv, i, c, tg))
crow.sort(key=lambda x: -x[0])


def comments_block(rows):
    h = []
    for lv, i, c, tg in rows:
        h.append(f'<figure class="cmt"><blockquote>{sq(c.get("text"), 260)}</blockquote>'
                 f'<figcaption><span class="mono">👍 {lv:,}</span> · {sq(c.get("author"), 16)} · {sq(c.get("publishedTime"))} · '
                 f'<a href="{escape(i["url"])}" target="_blank" rel="noopener">{sq(i["title"], 44)}</a> {tag_chips(tg, 3)}</figcaption></figure>')
    return "\n".join(h)


def recipe_cards(cards):
    h = []
    for c in cards:
        src = " · ".join(f'<a href="{escape(u)}" target="_blank" rel="noopener">{escape(n)}</a>' for n, u in c.get("sources", []))
        ing = "".join(f"<li>{escape(x)}</li>" for x in c.get("ingredients", []))
        steps = "".join(f"<li>{escape(x)}</li>" for x in c.get("steps", []))
        h.append(f'''<article class="card">
  <div class="card-k">{escape(c.get("kicker", ""))}</div>
  <h3>{escape(c["name"])}</h3>
  <p class="card-o">{escape(c.get("origin", ""))}</p>
  {"<h4>재료</h4><ul class='ing'>" + ing + "</ul>" if ing else ""}
  {"<h4>조리</h4><ol class='steps'>" + steps + "</ol>" if steps else ""}
  {"<p class='card-n'>" + escape(c.get("note", "")) + "</p>" if c.get("note") else ""}
  <p class="src">출처: {src}</p>
</article>''')
    return "\n".join(h)


# ------------------------------------------------------------------ page
CSS = r"""
:root{
  --bg:#fbfaf7; --surface:#ffffff; --surface-2:#f2f0ea; --ink:#1a1512; --ink-2:#4d4741; --muted:#8a847b; --line:#e4e0d6;
  --accent:#f0b400; --accent-ink:#1a1512; --accent-soft:#fff3c4; --link:#1c5cab;
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --s4:#eda100;
  --grid:#e6e3da; --axis:#c9c5bb;
  color-scheme:light;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --bg:#141210; --surface:#1d1a17; --surface-2:#26221e; --ink:#f3efe6; --ink-2:#c9c2b6; --muted:#8f887d; --line:#332e29;
    --accent:#f5c02a; --accent-ink:#1a1512; --accent-soft:#3a3010; --link:#86b6ef;
    --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500;
    --grid:#2c2926; --axis:#3d3833; color-scheme:dark;
  }
}
:root[data-theme="dark"]{
  --bg:#141210; --surface:#1d1a17; --surface-2:#26221e; --ink:#f3efe6; --ink-2:#c9c2b6; --muted:#8f887d; --line:#332e29;
  --accent:#f5c02a; --accent-ink:#1a1512; --accent-soft:#3a3010; --link:#86b6ef;
  --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500;
  --grid:#2c2926; --axis:#3d3833; color-scheme:dark;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:"Noto Sans KR",system-ui,-apple-system,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;font-size:15px;line-height:1.65;-webkit-font-smoothing:antialiased}
a{color:var(--link);text-decoration:none}a:hover{text-decoration:underline}
a:focus-visible,button:focus-visible,input:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.wrap{max-width:1000px;margin:0 auto;padding:0 24px 80px}
header.top{padding:48px 0 28px;border-bottom:3px solid var(--ink)}
.eyebrow{font-size:12px;font-weight:700;letter-spacing:.12em;color:var(--ink-2);margin-bottom:10px}
h1{font-family:"Black Han Sans","Noto Sans KR",sans-serif;font-weight:400;font-size:clamp(40px,7vw,64px);line-height:1.05;margin:0 0 12px;letter-spacing:-.01em;text-wrap:balance}
h1 .hl{background:linear-gradient(transparent 55%,var(--accent) 55%)}
.lede{font-size:17px;color:var(--ink-2);max-width:62ch;margin:0 0 18px}
.meta{font-size:13px;color:var(--muted);display:flex;flex-wrap:wrap;gap:6px 18px}
.meta b{color:var(--ink-2);font-weight:500}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:14px;margin:26px 0 6px}
.tile{background:var(--surface);border:1px solid var(--line);padding:16px 18px 14px}
.tile .l{font-size:12.5px;color:var(--ink-2);margin-bottom:6px}
.tile .v{font-size:34px;font-weight:700;line-height:1.05;letter-spacing:-.02em}
.tile .d{font-size:12px;color:var(--muted);margin-top:6px}
section{padding:44px 0 6px;border-top:1px solid var(--line)}
section:first-of-type{border-top:0}
.kicker{font-size:12px;font-weight:700;letter-spacing:.12em;color:var(--ink-2);margin:0 0 8px}
.kicker::before{content:"";display:inline-block;width:10px;height:10px;background:var(--accent);margin-right:8px;vertical-align:-1px}
h2{font-family:"Black Han Sans","Noto Sans KR",sans-serif;font-weight:400;font-size:30px;line-height:1.15;margin:0 0 14px;letter-spacing:-.005em;text-wrap:balance}
h3{font-size:18px;font-weight:700;margin:26px 0 10px}
p{max-width:70ch}
.findings{display:grid;gap:12px;margin:12px 0 0;padding:0;list-style:none;counter-reset:f}
.findings li{background:var(--surface);border:1px solid var(--line);padding:14px 16px 14px 56px;position:relative;line-height:1.55}
.findings li::before{counter-increment:f;content:counter(f);position:absolute;left:16px;top:12px;width:28px;height:28px;border-radius:50%;background:var(--accent);color:var(--accent-ink);font-weight:700;display:grid;place-items:center;font-size:14px}
.findings b{font-weight:700}
.two{display:grid;grid-template-columns:1fr 1fr;gap:24px}
@media (max-width:820px){.two{grid-template-columns:1fr}}
figure.fig{margin:18px 0 8px;background:var(--surface);border:1px solid var(--line);padding:14px 14px 10px}
figure.fig figcaption{font-size:13px;color:var(--ink-2);margin-bottom:8px;font-weight:500}
figure.fig .note{font-size:12px;color:var(--muted);margin-top:6px}
svg.chart{width:100%;height:auto;display:block;font-family:inherit}
svg.chart .grid{stroke:var(--grid);stroke-width:1}
svg.chart .axis{stroke:var(--axis);stroke-width:1}
svg.chart .tick{fill:var(--muted);font-size:11px;font-variant-numeric:tabular-nums}
svg.chart .lbl{fill:var(--ink-2);font-size:12px}
svg.chart .val{fill:var(--ink);font-size:12px;font-weight:600;font-variant-numeric:tabular-nums}
svg.chart .val.small{font-size:11px;font-weight:500}
svg.chart path:hover,svg.chart rect:hover{opacity:.82}
.tablewrap{overflow-x:auto;border:1px solid var(--line);background:var(--surface);margin:14px 0}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top;text-align:left}
th{font-size:12px;color:var(--ink-2);font-weight:700;background:var(--surface-2);position:sticky;top:0;white-space:nowrap}
td.r,th.r{text-align:right}
td.mono{font-variant-numeric:tabular-nums;white-space:nowrap;color:var(--ink-2)}
td.t{min-width:260px}
tr.hid{display:none}
.chip{display:inline-block;font-size:11px;padding:1px 7px;border:1px solid var(--line);border-radius:999px;margin:1px 3px 1px 0;color:var(--ink-2);background:var(--surface-2);white-space:nowrap}
.pl{display:inline-block;font-size:11px;font-weight:700;padding:1px 7px;border-radius:3px;color:#fff}
.pl-youtube{background:var(--s1)}.pl-tiktok{background:var(--s2)}.pl-instagram{background:var(--s3)}.pl-web{background:var(--s4);color:var(--accent-ink)}
.filters{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:12px 0 4px}
.filters button{font:inherit;font-size:13px;padding:6px 12px;border:1px solid var(--line);background:var(--surface);color:var(--ink);cursor:pointer;border-radius:999px}
.filters button[aria-pressed="true"]{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.filters input{font:inherit;font-size:13px;padding:6px 10px;border:1px solid var(--line);background:var(--surface);color:var(--ink);min-width:220px}
.filters .cnt{font-size:12px;color:var(--muted);margin-left:auto}
.more{font:inherit;font-size:13px;padding:8px 14px;border:1px solid var(--line);background:var(--surface);cursor:pointer;margin:6px 0 10px;color:var(--ink)}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px;margin-top:14px}
.card{background:var(--surface);border:1px solid var(--line);padding:18px 18px 14px;display:flex;flex-direction:column;gap:6px}
.card-k{font-size:11.5px;font-weight:700;letter-spacing:.08em;color:var(--ink-2)}
.card h3{margin:0;font-size:19px;line-height:1.3}
.card-o{font-size:13px;color:var(--ink-2);margin:0}
.card h4{font-size:12.5px;margin:8px 0 2px;color:var(--muted);font-weight:700}
.card ul,.card ol{margin:0;padding-left:18px;font-size:13.5px}
.card li{margin:2px 0}
.card-n{font-size:13px;color:var(--ink-2);margin:6px 0 0;background:var(--accent-soft);padding:8px 10px}
.card .src{font-size:12px;color:var(--muted);margin:8px 0 0}
.cmts{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px}
@media (max-width:820px){.cmts{grid-template-columns:1fr}}
figure.cmt{margin:0;background:var(--surface);border:1px solid var(--line);padding:12px 14px}
figure.cmt blockquote{margin:0 0 8px;font-size:14px;line-height:1.55}
figure.cmt figcaption{font-size:12px;color:var(--muted)}
.impl{display:grid;gap:14px;margin-top:8px}
.impl div{background:var(--surface);border-left:4px solid var(--accent);padding:12px 16px}
.impl b{display:block;margin-bottom:4px}
.pnotes{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px;margin:8px 0 12px}
.pnotes div{background:var(--surface-2);padding:12px 14px;font-size:14px}
.pnotes b{display:block;margin-bottom:4px}
.small{font-size:13px;color:var(--ink-2)}
ul.plain{padding-left:18px}
footer{margin-top:40px;font-size:12.5px;color:var(--muted);border-top:1px solid var(--line);padding-top:14px}
@media (prefers-reduced-motion:no-preference){svg.chart path,svg.chart rect{transition:opacity .15s}}
"""

JS = r"""
(function(){
  var active='ALL', q='';
  var rows=Array.prototype.slice.call(document.querySelectorAll('#latest tbody tr'));
  var cnt=document.getElementById('cnt'); var more=document.getElementById('more'); var limit=120;
  function apply(){
    var shown=0;
    rows.forEach(function(r){
      var ok=(active==='ALL'||r.dataset.p===active) && (!q || r.textContent.toLowerCase().indexOf(q)>=0);
      if(ok){shown++; r.classList.toggle('hid', shown>limit);} else {r.classList.add('hid');}
    });
    cnt.textContent=Math.min(shown,limit)+' / '+shown+'건 표시';
    more.hidden = shown<=limit;
  }
  document.querySelectorAll('.filters button[data-p]').forEach(function(b){
    b.addEventListener('click',function(){
      document.querySelectorAll('.filters button[data-p]').forEach(function(x){x.setAttribute('aria-pressed','false')});
      b.setAttribute('aria-pressed','true'); active=b.dataset.p; limit=120; apply();
    });
  });
  document.getElementById('q').addEventListener('input',function(e){q=e.target.value.trim().toLowerCase(); limit=120; apply();});
  more.addEventListener('click',function(){limit+=200; apply();});
  apply();
})();
"""


def build():
    findings_html = "".join(f"<li>{f}</li>" for f in FINDINGS)
    rising_rows = "".join(
        f'<tr><td>{escape(t)}</td><td class="r mono">{n26}</td><td class="r mono">{n25}</td><td class="r mono">{d * 100:+.1f}%p</td></tr>'
        for t, d, n26, n25 in rising[:10])
    falling_rows = "".join(
        f'<tr><td>{escape(t)}</td><td class="r mono">{n26}</td><td class="r mono">{n25}</td><td class="r mono">{d * 100:+.1f}%p</td></tr>'
        for t, d, n26, n25 in sorted(rising, key=lambda x: x[1])[:8])
    pnotes = "".join(f"<div><b>{escape(k)}</b>{v}</div>" for k, v in PLATFORM_NOTES.items())
    impl = "".join(f"<div><b>{escape(t)}</b>{b}</div>" for t, b in IMPLICATIONS)
    method = "".join(f"<li>{m}</li>" for m in METHOD_NOTES)
    creators = collections.defaultdict(list)
    for i in jj:
        if i["author"]:
            creators[(i["platform"], i["author"])].append(i)
    creator_rows = "".join(
        f'<tr><td><span class="pl pl-{p.lower()}">{p}</span></td><td>{sq(a, 26)}</td><td class="r mono">{len(l)}</td><td class="t">{sq(max(l, key=lambda x: (x["views"] or 0, x["date"] or ""))["title"], 70)}</td></tr>'
        for (p, a), l in sorted(creators.items(), key=lambda kv: -len(kv[1]))[:20])

    html = f"""<title>짜파게티 튜닝 지도</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Black+Han+Sans&family=Noto+Sans+KR:wght@400;500;700&display=swap">
<style>{CSS}</style>
<div class="wrap">
<header class="top">
  <div class="eyebrow">SNS 튜닝 레시피 수집 · {TODAY} 기준</div>
  <h1>짜파게티 <span class="hl">튜닝 지도</span></h1>
  <p class="lede">유튜브·틱톡·인스타그램과 웹(기사·커뮤니티·레시피 사이트)에서 "짜파게티를 어떻게 바꿔 먹는지"를 최신 게시물부터 모아 유형별로 정리했습니다. 표의 모든 행은 원문 링크로 연결됩니다.</p>
  <div class="meta"><span>수집 범위 <b>YouTube 71개 키워드 × 6개 필터, TikTok·Instagram·웹 검색 인덱스</b></span><span>분류 <b>키워드 규칙 기반 자동 태깅(7개 카테고리 · {len(TAG_RULES)}개 태그)</b></span></div>
  <div class="tiles">
    <div class="tile"><div class="l">수집 게시물</div><div class="v">{n_all:,}</div><div class="d">YouTube {plat_all['YouTube']:,} · TikTok {plat_all['TikTok']:,} · Instagram {plat_all['Instagram']:,} · Web {plat_all['Web']:,}</div></div>
    <div class="tile"><div class="l">짜파게티 언급 · 튜닝 정보 있음</div><div class="v">{n_recipe:,}</div><div class="d">언급 게시물 {n_jj:,}건 중</div></div>
    <div class="tile"><div class="l">2026년 게시</div><div class="v">{n_2026:,}</div><div class="d">2025년 {n_2025:,}건 · 게시일 확인분 기준</div></div>
    <div class="tile"><div class="l">분석한 시청자 댓글</div><div class="v">{n_comments:,}</div><div class="d">YouTube 상위 영상 댓글</div></div>
  </div>
</header>

<section>
  <p class="kicker">핵심 요약</p>
  <h2>사람들은 짜파게티를 이렇게 바꿔 먹는다</h2>
  <ol class="findings">{findings_html}</ol>
</section>

<section>
  <p class="kicker">튜닝 유형</p>
  <h2>7개 카테고리, {len(TAG_RULES)}개 세부 태그로 본 튜닝 지도</h2>
  <p>제목·캡션·설명 텍스트에서 재료·조합·조리법 키워드를 잡아 분류했습니다. 한 게시물에 여러 태그가 붙을 수 있어 합계는 게시물 수보다 큽니다.</p>
  <figure class="fig"><figcaption>카테고리별 게시물 수 (짜파게티 언급, 2026년 vs 2025년 게시)</figcaption>{chart_cats}</figure>
  <div class="two">
    <figure class="fig"><figcaption>세부 태그 순위 (전체 기간, 상위 24)</figcaption>{chart_tags}</figure>
    <figure class="fig"><figcaption>2026년 게시물 태그 순위 (상위 15)</figcaption>{chart_tags26}</figure>
  </div>
  <div class="two">
    <div><h3>2026년에 비중이 커진 태그</h3><div class="tablewrap"><table><thead><tr><th>태그</th><th class="r">2026</th><th class="r">2025</th><th class="r">비중 변화</th></tr></thead><tbody>{rising_rows}</tbody></table></div></div>
    <div><h3>비중이 줄어든 태그</h3><div class="tablewrap"><table><thead><tr><th>태그</th><th class="r">2026</th><th class="r">2025</th><th class="r">비중 변화</th></tr></thead><tbody>{falling_rows}</tbody></table></div></div>
  </div>
  <p class="small">비중 변화 = 해당 연도 전체 태그 부착 수 대비 점유율 차이(%p). 태그 부착 수 12건 이상만 비교.</p>
</section>

<section>
  <p class="kicker">시간 흐름</p>
  <h2>월별 게시 추이</h2>
  <p>{TREND_NOTE}</p>
  <figure class="fig"><figcaption>월별 짜파게티 언급 게시물 수 (게시일 확인분, 플랫폼별 누적)</figcaption>{chart_month}<div class="note">YouTube는 '오늘/이번 주/이번 달/올해' 필터 검색을 병행해 최근 12개월이 상대적으로 촘촘히 잡힘. TikTok·Instagram은 검색 엔진 인덱스 노출분만 포함되어 절대 수치가 아니라 상대 추세로 읽어야 함.</div></figure>
</section>

<section>
  <p class="kicker">플랫폼별</p>
  <h2>플랫폼마다 다른 튜닝 문법</h2>
  <div class="pnotes">{pnotes}</div>
  <h3>YouTube · 2025년 이후 조회수 상위</h3>
  {yt_table(top_recent_yt)}
  <h3>YouTube · 역대 조회수 상위</h3>
  {yt_table(top_all_yt, show_likes=False)}
  <h3>TikTok · 최신순 (검색 인덱스 노출 영상)</h3>
  {social_table(tt_videos[:40])}
  <h3>Instagram · 최신순 (검색 인덱스 노출 게시물·릴스)</h3>
  {social_table(ig_posts[:40])}
  <h3>게시물 수 상위 크리에이터</h3>
  <div class="tablewrap"><table><thead><tr><th>플랫폼</th><th>크리에이터</th><th class="r">게시물</th><th>대표 게시물</th></tr></thead><tbody>{creator_rows}</tbody></table></div>
</section>

<section>
  <p class="kicker">바이럴 레시피</p>
  <h2>반복해서 등장하는 대표 튜닝 레시피</h2>
  <p>여러 플랫폼에서 반복 재생산되는 레시피를 원문 기준으로 정리했습니다. 분량은 게시자마다 달라 대표적인 수치만 적었습니다.</p>
  <div class="cards">{recipe_cards(RECIPE_CARDS)}</div>
</section>

<section>
  <p class="kicker">최신 게시물</p>
  <h2>전 플랫폼 최신순 목록</h2>
  <p>짜파게티를 언급하고 튜닝 정보가 있는 게시물 {len(recent_all):,}건. 플랫폼 버튼과 검색창으로 좁혀 볼 수 있습니다.</p>
  <div class="filters">
    <button data-p="ALL" aria-pressed="true">전체</button><button data-p="YouTube" aria-pressed="false">YouTube</button><button data-p="TikTok" aria-pressed="false">TikTok</button><button data-p="Instagram" aria-pressed="false">Instagram</button><button data-p="Web" aria-pressed="false">Web</button>
    <input id="q" type="search" placeholder="재료·키워드 검색 (예: 치즈, 굴소스, 윤남노)" aria-label="검색">
    <span class="cnt" id="cnt"></span>
  </div>
  {latest_table(recent_all[:1500])}
  <button class="more" id="more">더 보기</button>
  <p class="small">이 페이지에는 최신 1,500건만 실었습니다. 전체 목록은 엑셀 '전체_최신순' 시트 또는 master.csv 참조.</p>
</section>

<section>
  <p class="kicker">댓글</p>
  <h2>시청자는 무엇을 더 넣는다고 말하는가</h2>
  <p>YouTube 상위 영상 댓글 {n_comments:,}개에서 재료·조리법 키워드를 추출했습니다. 영상이 보여주는 튜닝과 시청자가 스스로 말하는 튜닝의 차이를 볼 수 있습니다.</p>
  <figure class="fig"><figcaption>댓글에서 언급된 튜닝 태그 (상위 15)</figcaption>{chart_comments}</figure>
  <div class="cmts">{comments_block(crow[:16])}</div>
</section>

<section>
  <p class="kicker">시사점</p>
  <h2>제품·마케팅 관점에서 읽기</h2>
  <div class="impl">{impl}</div>
</section>

<section>
  <p class="kicker">방법론</p>
  <h2>수집 방법과 한계</h2>
  <ul class="plain small">{method}</ul>
</section>
<footer>데이터 파일: master.csv / master.json / youtube_comments.csv / 짜파게티_SNS_튜닝레시피_수집.xlsx (저장소 research/jjapagetti-sns-recipes/). 조회수·좋아요는 {TODAY} 수집 시점 스냅숏.</footer>
</div>
<script>{JS}</script>
"""
    path = os.path.join(OUT, "jjapagetti-tuning-map.html")
    open(path, "w", encoding="utf-8").write(html)
    print("wrote", path, len(html))
    return path


if __name__ == "__main__":
    build()
