# -*- coding: utf-8 -*-
"""Assemble README.md (Korean report) from narrative.py + out/report_tables.md + stats."""
import json, os, re, sys, datetime, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from narrative import FINDINGS, RECIPE_CARDS, IMPLICATIONS, PLATFORM_NOTES, TREND_NOTE, METHOD_NOTES
from tags import TAG_RULES, CATEGORY_LABEL

SCRATCH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(SCRATCH, "out")
items = json.load(open(os.path.join(OUT, "master.json"), encoding="utf-8"))
st = json.load(open(os.path.join(OUT, "stats.json"), encoding="utf-8"))
tables = open(os.path.join(OUT, "report_tables.md"), encoding="utf-8").read()
TODAY = datetime.date.today().isoformat()


def section(md, title_prefix):
    """Extract one '## 표N.' section from report_tables.md (demoted to H3 for README hierarchy)."""
    m = re.search(r"(## " + re.escape(title_prefix) + r".*?)(?=\n## |\Z)", md, re.S)
    s = m.group(1).strip() if m else ""
    return re.sub(r"^## ", "### ", s, count=1).replace("\n### TikTok discover", "\n#### TikTok discover")


def strip_html(s):
    s = re.sub(r"<b>(.*?)</b>", r"**\1**", s)
    s = re.sub(r"<[^>]+>", "", s)
    return s


jj = [i for i in items if i["mentions_jjapagetti"]]
plat_all = collections.Counter(i["platform"] for i in items)
n_recipe = sum(1 for i in jj if i["recipe_like"])
n_2026 = sum(1 for i in jj if (i["date"] or "").startswith("2026"))
n_2025 = sum(1 for i in jj if (i["date"] or "").startswith("2025"))
tt_videos = sum(1 for i in items if i["platform"] == "TikTok" and i["format"] == "video")
tt_topics = sum(1 for i in items if i["platform"] == "TikTok" and i["format"] != "video")
ig_posts = sum(1 for i in items if i["platform"] == "Instagram" and i["format"] in ("post", "reel"))
ig_other = sum(1 for i in items if i["platform"] == "Instagram" and i["format"] not in ("post", "reel"))

L = []
P = L.append
P("# 짜파게티 SNS 튜닝 레시피 수집 · 분석 (YouTube · TikTok · Instagram · Web)\n")
P(f"수집 기준일 **{TODAY}** · 최신 게시물부터 역순 정리 · 모든 표의 링크는 원문으로 연결됩니다.\n")
P("> 인터랙티브 HTML 보고서: `report/jjapagetti-tuning-map.html` (플랫폼 필터·검색 가능) · 엑셀: `data/짜파게티_SNS_튜닝레시피_수집.xlsx` · 전체 데이터: `data/master.csv`, `data/master.json`, `data/youtube_comments.csv`\n")

P("## 1. 한눈에 보기\n")
P("| 구분 | 수치 |\n|---|---:|")
P(f"| 수집 게시물(전체) | {len(items):,} |")
P(f"| ├ YouTube 영상(쇼츠 포함) | {plat_all['YouTube']:,} |")
P(f"| ├ TikTok 영상 / 토픽(discover·tag) 페이지 | {tt_videos:,} / {tt_topics:,} |")
P(f"| ├ Instagram 게시물·릴스 / 토픽·프로필 페이지 | {ig_posts:,} / {ig_other:,} |")
P(f"| └ Web(기사·커뮤니티·레시피 사이트·공식) | {plat_all['Web']:,} |")
P(f"| 짜파게티 언급 게시물 | {len(jj):,} |")
P(f"| 그중 튜닝 정보(레시피성) 있는 게시물 | {n_recipe:,} |")
P(f"| 2026년 게시 / 2025년 게시 | {n_2026:,} / {n_2025:,} |")
P(f"| 분석한 YouTube 댓글 | {st.get('n_comments', 0):,} |")
P("")

P("## 2. 핵심 요약\n")
for i, f in enumerate(FINDINGS, 1):
    P(f"{i}. {strip_html(f)}")
P("")

P("## 3. 튜닝 유형 지도\n")
P(f"7개 카테고리 · {len(TAG_RULES)}개 세부 태그의 키워드 규칙으로 제목·캡션·설명을 자동 분류했습니다(중복 태깅 허용).\n")
cats = "\n".join(f"- **{v}**" for v in CATEGORY_LABEL.values())
P(cats + "\n")
P(section(tables, "표2.") + "\n")
tag_sec = section(tables, "표3.")
# keep top 35 rows of tag table
lines = tag_sec.split("\n")
head, rows = lines[:4], lines[4:]
P("\n".join(head + rows[:35]) + "\n")
P(f"_전체 {len(TAG_RULES)}개 태그의 통계는 엑셀 '튜닝유형_통계' 시트 참조._\n")

P("## 4. 시간 흐름\n")
P(strip_html(TREND_NOTE) + "\n")
mon_sec = section(tables, "표4.")
mlines = mon_sec.split("\n")
P("\n".join(mlines[:4] + [l for l in mlines[4:] if l.startswith("| 2025") or l.startswith("| 2026")]) + "\n")

P("## 5. 플랫폼별 특징\n")
for k, v in PLATFORM_NOTES.items():
    P(f"- **{k}** — {strip_html(v)}")
P("")

P("## 6. 대표 튜닝 레시피 (반복 재생산되는 것들)\n")
for c in RECIPE_CARDS:
    P(f"### {c['name']}")
    P(f"_{c.get('kicker', '')}_ · {c.get('origin', '')}\n")
    if c.get("ingredients"):
        P("- 재료: " + " / ".join(c["ingredients"]))
    if c.get("steps"):
        for j, s in enumerate(c["steps"], 1):
            P(f"  {j}. {s}")
    if c.get("note"):
        P(f"- 메모: {c['note']}")
    P("- 출처: " + " · ".join(f"[{n}]({u})" for n, u in c.get("sources", [])))
    P("")

P("## 7. 최신 게시물 (전 플랫폼)\n")
P(section(tables, "표5.") + "\n")
P("## 8. YouTube 상위 영상\n")
P(section(tables, "표6.") + "\n")
P(section(tables, "표7.") + "\n")
P("## 9. TikTok 게시물\n")
P(section(tables, "표8.") + "\n")
P("## 10. Instagram 게시물\n")
P(section(tables, "표9.") + "\n")
P("## 11. 웹(기사·커뮤니티·레시피 사이트)\n")
P(section(tables, "표10.") + "\n")
P("## 12. 시청자 댓글에 나타난 튜닝\n")
P(section(tables, "표11.") + "\n")
P("## 13. 크리에이터\n")
P(section(tables, "표12.") + "\n")

P("## 14. 시사점 (제품·마케팅 관점)\n")
for t, b in IMPLICATIONS:
    P(f"- **{t}** — {strip_html(b)}")
P("")

P("## 15. 수집 방법과 한계\n")
for m in METHOD_NOTES:
    P(f"- {strip_html(m)}")
P("")
P("## 16. 파일 구성\n")
P("""| 파일 | 내용 |
|---|---|
| `report/jjapagetti-tuning-map.html` | 인터랙티브 HTML 보고서(차트·필터·검색) |
| `data/짜파게티_SNS_튜닝레시피_수집.xlsx` | 요약·전체 최신순·플랫폼별·튜닝유형 통계·월별 추이·댓글·방법론 시트 |
| `data/master.csv` / `data/master.json` | 통합 데이터(플랫폼·게시일·제목·작성자·조회수·태그·URL·설명·검색어) |
| `data/youtube_comments.csv` | YouTube 상위 영상 댓글(태그 포함) |
| `data/raw/` | 플랫폼별 원천 수집 파일(검색 히트, 영상 상세, 댓글, 에이전트 원문 로그) |
| `data/web_findings.md` | 웹 컨텍스트 정리(요리대회·신제품·셰프 레시피·커뮤니티 꿀조합·조리 팁, 출처 포함) |
| `scripts/` | 수집·분석·보고서 생성 스크립트(재현 가능) |
""")

open(os.path.join(OUT, "README.md"), "w", encoding="utf-8").write("\n".join(L))
print("wrote README.md", len("\n".join(L)))
