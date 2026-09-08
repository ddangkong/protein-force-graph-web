# -*- coding: utf-8 -*-
"""Generate markdown tables (report_tables.md) from out/master.json + out/stats.json."""
import json, os, sys, collections, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tags import TAG_RULES, CATEGORY_LABEL, CATEGORY_ORDER

SCRATCH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(SCRATCH, "out")
items = json.load(open(os.path.join(OUT, "master.json"), encoding="utf-8"))
st = json.load(open(os.path.join(OUT, "stats.json"), encoding="utf-8"))
jj = [i for i in items if i["mentions_jjapagetti"]]


def esc(s, n=80):
    s = re.sub(r"\s+", " ", str(s or "")).replace("|", "¦").strip()
    return (s[: n - 1] + "…") if len(s) > n else s


def fmt(n):
    return f"{n:,}" if isinstance(n, (int, float)) and n is not None else ""


L = []
P = L.append

# 1. platform summary
P("## 표1. 플랫폼별 수집 규모\n")
P("| 플랫폼 | 전체 수집 | 짜파게티 언급 | 레시피성 | 2026 게시 | 2025 게시 | 게시일 확인 |")
P("|---|---:|---:|---:|---:|---:|---:|")
for p in ["YouTube", "TikTok", "Instagram", "Web"]:
    tot = sum(1 for i in items if i["platform"] == p)
    m = sum(1 for i in jj if i["platform"] == p)
    r = sum(1 for i in jj if i["platform"] == p and i["recipe_like"])
    y26 = sum(1 for i in jj if i["platform"] == p and (i["date"] or "").startswith("2026"))
    y25 = sum(1 for i in jj if i["platform"] == p and (i["date"] or "").startswith("2025"))
    dated = sum(1 for i in items if i["platform"] == p and i["date"])
    P(f"| {p} | {tot:,} | {m:,} | {r:,} | {y26:,} | {y25:,} | {dated:,} |")
P(f"| **합계** | {len(items):,} | {len(jj):,} | {sum(1 for i in jj if i['recipe_like']):,} | "
  f"{sum(1 for i in jj if (i['date'] or '').startswith('2026')):,} | {sum(1 for i in jj if (i['date'] or '').startswith('2025')):,} | {sum(1 for i in items if i['date']):,} |")
P("")

# 2. categories
P("## 표2. 튜닝 카테고리별 건수 (짜파게티 언급 게시물, 중복 허용)\n")
P("| 카테고리 | 전체 | 2026 | 2025 | 2024 이전 | YouTube | TikTok | Instagram | Web |")
P("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
for c in CATEGORY_ORDER:
    f = lambda cond: sum(1 for i in jj if c in i["categories"] and cond(i))
    P(f"| {CATEGORY_LABEL[c]} | {f(lambda i: True)} | {f(lambda i: (i['date'] or '').startswith('2026'))} | "
      f"{f(lambda i: (i['date'] or '').startswith('2025'))} | {f(lambda i: i['date'] and i['date'] < '2025-01-01')} | "
      f"{f(lambda i: i['platform']=='YouTube')} | {f(lambda i: i['platform']=='TikTok')} | {f(lambda i: i['platform']=='Instagram')} | {f(lambda i: i['platform']=='Web')} |")
P("")

# 3. tags
P("## 표3. 세부 튜닝 태그 순위 (짜파게티 언급 게시물)\n")
P("| 순위 | 태그 | 카테고리 | 전체 | 2026 | 2025 | 2024 이전 | YouTube | TikTok | Instagram | YouTube 조회수 합(2025~) | 댓글 언급 |")
P("|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
tagcat = {t: c for t, c, _ in TAG_RULES}
cnt = collections.Counter()
by = collections.defaultdict(collections.Counter)
vw = collections.Counter()
for i in jj:
    y = (i["date"] or "")[:4]
    for t in i["tags"]:
        cnt[t] += 1
        by[t]["2026" if y == "2026" else "2025" if y == "2025" else "pre" if y and y < "2025" else "nodate"] += 1
        by[t][i["platform"]] += 1
        if i["platform"] == "YouTube" and y >= "2025":
            vw[t] += i["views"] or 0
ct = dict(st.get("comment_tags", []))
for rank, (t, n) in enumerate(cnt.most_common(), 1):
    P(f"| {rank} | {t} | {CATEGORY_LABEL.get(tagcat.get(t,''), '')} | {n} | {by[t]['2026']} | {by[t]['2025']} | {by[t]['pre']} | "
      f"{by[t]['YouTube']} | {by[t]['TikTok']} | {by[t]['Instagram']} | {fmt(vw[t])} | {ct.get(t, 0)} |")
P("")

# 4. monthly
P("## 표4. 월별 게시 추이 (짜파게티 언급, 게시일 확인분)\n")
P("| 월 | 전체 | YouTube | TikTok | Instagram | Web |")
P("|---|---:|---:|---:|---:|---:|")
mon = collections.defaultdict(collections.Counter)
for i in jj:
    if i["date"] and i["date"] >= "2024-01":
        mon[i["date"][:7]]["all"] += 1
        mon[i["date"][:7]][i["platform"]] += 1
for m in sorted(mon):
    c = mon[m]
    P(f"| {m} | {c['all']} | {c['YouTube']} | {c['TikTok']} | {c['Instagram']} | {c['Web']} |")
P("")

# 5. latest posts across platforms
P("## 표5. 최신 게시물 (전 플랫폼, 게시일 내림차순 상위 80건, 짜파게티 언급·레시피성)\n")
P("| 게시일 | 플랫폼 | 제목/캡션 | 작성자 | 조회수 | 튜닝 태그 | 링크 |")
P("|---|---|---|---|---:|---|---|")
recent = sorted([i for i in jj if i["date"] and i["recipe_like"]], key=lambda x: x["date"], reverse=True)[:80]
for i in recent:
    P(f"| {i['date']} | {i['platform']}{'·Shorts' if i['format']=='Shorts' else ''} | {esc(i['title'], 70)} | {esc(i['author'], 20)} | {fmt(i['views'])} | {esc('; '.join(i['tags']), 60)} | [열기]({i['url']}) |")
P("")

# 6. top youtube by views 2025+
P("## 표6. YouTube 조회수 상위 (2025년 이후 게시, 짜파게티 언급, 상위 60)\n")
P("| 게시일 | 형식 | 제목 | 채널 | 조회수 | 좋아요 | 튜닝 태그 | 링크 |")
P("|---|---|---|---|---:|---:|---|---|")
top = sorted([i for i in jj if i["platform"] == "YouTube" and (i["date"] or "") >= "2025-01-01"], key=lambda x: -(x["views"] or 0))[:60]
for i in top:
    P(f"| {i['date']} | {i['format']} | {esc(i['title'], 70)} | {esc(i['author'], 20)} | {fmt(i['views'])} | {fmt(i['likes'])} | {esc('; '.join(i['tags']), 60)} | [열기]({i['url']}) |")
P("")

# 7. top youtube all-time
P("## 표7. YouTube 역대 조회수 상위 (전체 기간, 짜파게티 언급, 상위 30)\n")
P("| 게시일 | 형식 | 제목 | 채널 | 조회수 | 튜닝 태그 | 링크 |")
P("|---|---|---|---|---:|---|---|")
for i in sorted([i for i in jj if i["platform"] == "YouTube"], key=lambda x: -(x["views"] or 0))[:30]:
    P(f"| {i['date'] or ''} | {i['format']} | {esc(i['title'], 70)} | {esc(i['author'], 20)} | {fmt(i['views'])} | {esc('; '.join(i['tags']), 60)} | [열기]({i['url']}) |")
P("")

# 8. tiktok latest
P("## 표8. TikTok 게시물 (영상 URL 기준, 게시일 내림차순)\n")
P("| 게시일 | 작성자 | 캡션(발췌) | 튜닝 태그 | 링크 |")
P("|---|---|---|---|---|")
tt = sorted([i for i in items if i["platform"] == "TikTok" and i["format"] == "video"], key=lambda x: x["date"] or "", reverse=True)
for i in tt:
    P(f"| {i['date'] or ''} | {esc(i['author'], 22)} | {esc(i['title'], 110)} | {esc('; '.join(i['tags']), 50)} | [열기]({i['url']}) |")
P("")
P("### TikTok discover/tag 토픽 페이지\n")
for i in [i for i in items if i["platform"] == "TikTok" and i["format"] != "video"]:
    P(f"- {esc(i['title'], 100)} — {i['url']}")
P("")

# 9. instagram latest
P("## 표9. Instagram 게시물/릴스 (게시일 내림차순)\n")
P("| 게시일 | 작성자 | 캡션(발췌) | 튜닝 태그 | 링크 |")
P("|---|---|---|---|---|")
ig = sorted([i for i in items if i["platform"] == "Instagram" and i["format"] in ("post", "reel")], key=lambda x: x["date"] or "", reverse=True)
for i in ig:
    P(f"| {i['date'] or ''} | {esc(i['author'], 22)} | {esc(i['title'], 110)} | {esc('; '.join(i['tags']), 50)} | [열기]({i['url']}) |")
P("")

# 10. web items by category
P("## 표10. 웹(기사·커뮤니티·레시피 사이트) 수집 항목\n")
P("| 분류 | 날짜 | 사이트 | 제목 | 튜닝 태그 | 링크 |")
P("|---|---|---|---|---|---|")
for i in sorted([i for i in items if i["platform"] == "Web"], key=lambda x: (x.get("web_category") or "", x["date"] or ""), reverse=False):
    P(f"| {i.get('web_category') or ''} | {i['date'] or ''} | {esc(i['author_meta'], 20)} | {esc(i['title'], 80)} | {esc('; '.join(i['tags']), 50)} | [열기]({i['url']}) |")
P("")

# 11. comments with tuning tags
P("## 표11. 시청자 댓글 중 튜닝 언급 (좋아요 순 상위 80)\n")
P("| 영상 | 댓글 시점 | 좋아요 | 댓글 | 태그 |")
P("|---|---|---:|---|---|")
from tags import tag_text
rows = []
for i in items:
    for c in i.get("comments") or []:
        tg = [t for t, _ in tag_text(c.get("text") or "")]
        if tg:
            likes = c.get("likes")
            try:
                lv = int(str(likes).replace(",", "")) if likes not in (None, "") else 0
            except Exception:
                lv = 0
            rows.append((lv, i, c, tg))
rows.sort(key=lambda x: -x[0])
for lv, i, c, tg in rows[:80]:
    P(f"| {esc(i['title'], 40)} | {c.get('publishedTime') or ''} | {lv} | {esc(c.get('text'), 140)} | {esc('; '.join(tg), 40)} |")
P("")

# 12. creators
P("## 표12. 게시물 수 상위 크리에이터/채널 (짜파게티 언급)\n")
P("| 플랫폼 | 크리에이터 | 게시물 수 | 대표 게시물 |")
P("|---|---|---:|---|")
cr = collections.defaultdict(list)
for i in jj:
    if i["author"]:
        cr[(i["platform"], i["author"])].append(i)
for (p, a), lst in sorted(cr.items(), key=lambda kv: -len(kv[1]))[:40]:
    best = max(lst, key=lambda x: (x["views"] or 0, x["date"] or ""))
    P(f"| {p} | {esc(a, 25)} | {len(lst)} | {esc(best['title'], 60)} ({best['date'] or ''}) |")
P("")

open(os.path.join(OUT, "report_tables.md"), "w", encoding="utf-8").write("\n".join(L))
print("wrote report_tables.md", len(L), "lines")
