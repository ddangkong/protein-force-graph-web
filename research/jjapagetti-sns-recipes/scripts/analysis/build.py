# -*- coding: utf-8 -*-
"""Merge YouTube / TikTok / Instagram / Web harvests into one tagged dataset + stats + exports."""
import json, os, re, csv, sys, datetime, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tags import tag_text, CATEGORY_ORDER, CATEGORY_LABEL, is_recipe_like, is_mukbang

SCRATCH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(SCRATCH, "out")
os.makedirs(OUT, exist_ok=True)

JJ = re.compile(r"짜파게티|짜파구리|짜계치|짜파|chapagetti|jjapagh?etti|jjapaguri|chapaguri|ram-?don|짜장라면|짜장 라면|jajang", re.I)


def load_jsonl(path):
    out = []
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def norm_url(u):
    return (u or "").split("?")[0].rstrip("/")


# ---------- date helpers
def tiktok_date(url):
    m = re.search(r"/video/(\d{15,20})", url or "")
    if not m:
        return None
    ts = int(m.group(1)) >> 32
    if 1.3e9 < ts < 1.9e9:
        return datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
    return None


IG_ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"


def instagram_date(url):
    m = re.search(r"/(?:p|reel|reels|tv)/([A-Za-z0-9_-]{9,12})", url or "")
    if not m:
        return None
    code = m.group(1)
    n = 0
    for ch in code:
        n = n * 64 + IG_ALPHA.index(ch)
    ms = (n >> 23) + 1314220021721
    try:
        d = datetime.datetime.utcfromtimestamp(ms / 1000)
    except Exception:
        return None
    if 2011 <= d.year <= 2027:
        return d.strftime("%Y-%m-%d")
    return None


def parse_count(text):
    """'조회수 2,477,708회' / '조회수 68만회' / '2.3만' / '3.8천' -> int"""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return int(text)
    t = str(text).replace(",", "")
    m = re.search(r"([\d.]+)\s*(만|천|억|K|M|B)?", t)
    if not m:
        return None
    v = float(m.group(1))
    unit = m.group(2)
    mult = {"만": 1e4, "천": 1e3, "억": 1e8, "K": 1e3, "M": 1e6, "B": 1e9}.get(unit, 1)
    return int(v * mult)


# ---------- load
def load_youtube():
    hits = load_jsonl(os.path.join(SCRATCH, "yt", "search_hits.jsonl"))
    vids = {v["videoId"]: v for v in load_jsonl(os.path.join(SCRATCH, "yt", "videos.jsonl")) if v.get("videoId")}
    comments = {c["videoId"]: c.get("comments", []) for c in load_jsonl(os.path.join(SCRATCH, "yt", "comments.jsonl"))}
    by_id = {}
    for h in hits:
        vid = h.get("videoId")
        if not vid:
            continue
        b = by_id.setdefault(vid, {"videoId": vid, "queries": set(), "filters": set(), "kind": h.get("kind"),
                                   "search_title": h.get("title"), "search_channel": h.get("channel"),
                                   "publishedTimeText": h.get("publishedTimeText"), "viewCountText_s": h.get("viewCountText"),
                                   "lengthText": h.get("lengthText"), "snippet": h.get("snippet")})
        b["queries"].add(h.get("query"))
        b["filters"].add(h.get("filter"))
        if h.get("kind") == "short":
            b["kind"] = "short"
        if h.get("lengthText") and not b.get("lengthText"):
            b["lengthText"] = h["lengthText"]
        if h.get("snippet") and not b.get("snippet"):
            b["snippet"] = h["snippet"]
    items = []
    for vid, b in by_id.items():
        d = vids.get(vid, {})
        title = d.get("title") or b.get("search_title") or ""
        desc = d.get("description") or ""
        channel = d.get("channel") or b.get("search_channel") or ""
        views = d.get("viewCount") if d.get("viewCount") is not None else parse_count(b.get("viewCountText_s"))
        length = b.get("lengthText") or ""
        is_short = b.get("kind") == "short" or (length and re.match(r"^\d{1,2}:\d{2}$", length) and int(length.split(":")[0]) == 0 and int(length.split(":")[1]) <= 60)
        # /shorts/ url when short-like
        url = f"https://www.youtube.com/shorts/{vid}" if is_short else f"https://www.youtube.com/watch?v={vid}"
        text = " \n".join([title, desc, b.get("snippet") or ""])
        items.append({
            "platform": "YouTube",
            "id": vid,
            "url": url,
            "date": d.get("publishDate"),
            "relative_date": d.get("relativeDateText") or b.get("publishedTimeText"),
            "title": title,
            "author": channel,
            "author_meta": d.get("subscriberText") or "",
            "views": views,
            "likes": parse_count(d.get("likeText")),
            "comments_count": parse_count(d.get("commentCountText")),
            "format": "Shorts" if is_short else "Video",
            "length": length,
            "text": text,
            "description": desc,
            "queries": sorted(q for q in b["queries"] if q),
            "filters": sorted(f for f in b["filters"] if f),
            "comments": comments.get(vid, []),
            "detail_ok": bool(d.get("ok")),
        })
    return items


def _first(d, *keys):
    for k in keys:
        v = d.get(k)
        if v:
            return v
    return ""


def load_agent(platform, path, url_key="url"):
    rows = load_jsonl(path)
    items, seen = [], set()
    for r in rows:
        url = r.get(url_key) or ""
        if not url:
            continue
        key = norm_url(url)
        if key in seen:
            continue
        seen.add(key)
        caption = _first(r, "title_or_caption", "title", "caption")
        variants = r.get("title_variants") or []
        if isinstance(variants, list):
            for v in variants:
                if isinstance(v, str) and len(v) > len(str(caption)):
                    caption = v
        caption = re.sub(r"\s*\|\s*TikTok\s*$", "", str(caption))
        recipe = _first(r, "recipe_details")
        notes = _first(r, "summary_notes", "summary")
        if isinstance(recipe, list):
            recipe = " / ".join(map(str, recipe))
        if isinstance(notes, list):
            notes = " / ".join(map(str, notes))
        dates_counts = _first(r, "dates_or_counts", "date")
        if isinstance(dates_counts, dict):
            dates_counts = json.dumps(dates_counts, ensure_ascii=False)
        author = _first(r, "author")
        if not author:
            m = re.search(r"tiktok\.com/@([^/]+)/", url) or re.search(r"instagram\.com/([A-Za-z0-9_.]+)/(?:p|reel)/", url)
            if m and m.group(1) not in ("p", "reel", "reels", "explore", "popular"):
                author = "@" + m.group(1)
        rtype = _first(r, "type")
        if platform == "TikTok":
            date = tiktok_date(url)
            if not rtype:
                rtype = "video" if "/video/" in url else ("discover" if "/discover/" in url else ("tag" if "/tag/" in url else "other"))
        elif platform == "Instagram":
            date = instagram_date(url)
            if not rtype:
                rtype = "reel" if "/reel" in url else ("post" if "/p/" in url else ("popular" if "/popular/" in url else "other"))
        else:
            date = None
            ds = str(dates_counts or "") + " " + str(_first(r, "date"))
            m = re.search(r"(20\d{2})[.\-/년 ]\s?(\d{1,2})[.\-/월 ]\s?(\d{1,2})", ds)
            if m:
                date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
            else:
                m = re.search(r"(20\d{2})[.\-/년 ]\s?(\d{1,2})월?", ds)
                if m:
                    date = f"{m.group(1)}-{int(m.group(2)):02d}"
        text = " \n".join(str(x) for x in [caption, recipe, notes] if x)
        items.append({
            "platform": platform,
            "id": key,
            "url": url,
            "date": date,
            "relative_date": str(dates_counts or ""),
            "title": str(caption)[:2000],
            "author": author,
            "author_meta": _first(r, "site"),
            "views": None,
            "likes": None,
            "comments_count": None,
            "format": rtype,
            "length": "",
            "text": text,
            "description": str(recipe or ""),
            "queries": r.get("found_by_queries") or ([r.get("query")] if r.get("query") else []),
            "filters": [],
            "comments": [],
            "detail_ok": True,
            "web_category": _first(r, "category"),
        })
    return items


def build():
    yt = load_youtube()
    tt = load_agent("TikTok", os.path.join(SCRATCH, "tiktok", "tiktok_posts.jsonl"))
    ig = load_agent("Instagram", os.path.join(SCRATCH, "instagram", "instagram_posts.jsonl"))
    web = load_agent("Web", os.path.join(SCRATCH, "web", "web_items.jsonl"))
    allitems = yt + tt + ig + web
    # --- noise filter: keyword-spam channels (candy ASMR etc.) whose descriptions stuff '짜파게티' without the title ever mentioning it
    NOISE_TITLE = re.compile(r"candy|lollipop|gummy|unboxing|satisfying|mystery box|slime|squishy", re.I)
    tot, tm = collections.Counter(), collections.Counter()
    for it in allitems:
        if it["platform"] == "YouTube":
            tot[it["author"]] += 1
            if JJ.search(it["title"] or ""):
                tm[it["author"]] += 1
    for it in allitems:
        title_m = bool(JJ.search(it["title"] or ""))
        text_m = bool(JJ.search(it["text"]))
        noise = (not title_m) and (bool(NOISE_TITLE.search(it["title"] or "")) or
                                   (it["platform"] == "YouTube" and it["author"] and tot[it["author"]] >= 5 and tm[it["author"]] == 0))
        it["title_mentions"] = title_m
        it["noise"] = noise
        tags = tag_text(it["text"]) if not noise else []
        it["tags"] = [t for t, c in tags]
        it["categories"] = sorted({c for t, c in tags}, key=CATEGORY_ORDER.index)
        it["mentions_jjapagetti"] = text_m and not noise
        it["recipe_like"] = is_recipe_like(it["text"]) or bool(it["tags"])
        it["is_mukbang"] = is_mukbang(it["title"] or "") or (it["platform"] == "YouTube" and is_mukbang(it["text"][:400]))
        # comment-derived tags (YouTube)
        ctags = collections.Counter()
        for c in it.get("comments", []):
            for t, _ in tag_text(c.get("text", "")):
                ctags[t] += 1
        it["comment_tags"] = dict(ctags)
    return allitems


def month_of(d):
    return d[:7] if d else None


def stats(items):
    st = {}
    st["counts_platform"] = collections.Counter(i["platform"] for i in items)
    st["counts_platform_jj"] = collections.Counter(i["platform"] for i in items if i["mentions_jjapagetti"])
    st["counts_platform_recipe"] = collections.Counter(i["platform"] for i in items if i["mentions_jjapagetti"] and i["recipe_like"])
    st["dated"] = collections.Counter(i["platform"] for i in items if i["date"])
    # monthly (2024-01 .. now) for jjapagetti recipe-like
    mon = collections.defaultdict(collections.Counter)
    for i in items:
        if i["date"] and i["mentions_jjapagetti"]:
            mon[month_of(i["date"])][i["platform"]] += 1
    st["monthly"] = {m: dict(c) for m, c in sorted(mon.items())}
    # tags overall / by platform / recent 12 months
    def tagcount(filter_fn):
        c = collections.Counter()
        for i in items:
            if filter_fn(i):
                for t in i["tags"]:
                    c[t] += 1
        return c
    st["tags_all"] = tagcount(lambda i: i["mentions_jjapagetti"])
    st["tags_2026"] = tagcount(lambda i: i["mentions_jjapagetti"] and (i["date"] or "").startswith("2026"))
    st["tags_2025"] = tagcount(lambda i: i["mentions_jjapagetti"] and (i["date"] or "").startswith("2025"))
    st["tags_pre2025"] = tagcount(lambda i: i["mentions_jjapagetti"] and i["date"] and i["date"] < "2025-01-01")
    for p in ["YouTube", "TikTok", "Instagram", "Web"]:
        st[f"tags_{p}"] = tagcount(lambda i, p=p: i["mentions_jjapagetti"] and i["platform"] == p)
    # categories
    cat = collections.Counter()
    for i in items:
        if i["mentions_jjapagetti"]:
            for c in i["categories"]:
                cat[c] += 1
    st["categories"] = cat
    # views-weighted tags (YouTube, 2025+)
    vw = collections.Counter()
    for i in items:
        if i["platform"] == "YouTube" and i["mentions_jjapagetti"] and (i["date"] or "") >= "2025-01-01":
            for t in i["tags"]:
                vw[t] += i["views"] or 0
    st["tags_views_2025plus"] = vw
    # comment tags
    ct = collections.Counter()
    ncom = 0
    for i in items:
        for c in i.get("comments", []):
            ncom += 1
            for t, _ in tag_text(c.get("text", "")):
                ct[t] += 1
    st["comment_tags"] = ct
    st["n_comments"] = ncom
    # top creators
    cr = collections.Counter()
    for i in items:
        if i["mentions_jjapagetti"] and i["author"]:
            cr[(i["platform"], i["author"])] += 1
    st["top_creators"] = cr.most_common(40)
    return st


def export(items, st):
    # master JSON (full, for the report pipeline) + public slim copy for the repository (no duplicated text / comments)
    with open(os.path.join(OUT, "master.json"), "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False)
    slim = [{k: v for k, v in i.items() if k not in ("text", "comments", "comment_tags", "filters")} for i in items]
    with open(os.path.join(OUT, "master_public.json"), "w", encoding="utf-8") as f:
        json.dump(slim, f, ensure_ascii=False)
    # master CSV (no comments)
    cols = ["platform", "date", "relative_date", "format", "title", "author", "author_meta", "views", "likes", "comments_count",
            "url", "tags", "categories", "mentions_jjapagetti", "recipe_like", "description", "queries"]
    with open(os.path.join(OUT, "master.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for i in sorted(items, key=lambda x: (x["date"] or "0000"), reverse=True):
            w.writerow([i.get("platform"), i.get("date"), i.get("relative_date"), i.get("format"), i.get("title"),
                        i.get("author"), i.get("author_meta"), i.get("views"), i.get("likes"), i.get("comments_count"),
                        i.get("url"), "; ".join(i["tags"]), "; ".join(CATEGORY_LABEL.get(c, c) for c in i["categories"]),
                        i["mentions_jjapagetti"], i["recipe_like"], (i.get("description") or "")[:3000],
                        "; ".join(i.get("queries") or [])])
    # comments CSV
    with open(os.path.join(OUT, "youtube_comments.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["videoId", "video_title", "video_date", "comment_date", "author", "likes", "reply_count", "text", "tags"])
        for i in items:
            for c in i.get("comments", []):
                w.writerow([i["id"], i["title"], i["date"], c.get("publishedTime"), c.get("author"), c.get("likes"),
                            c.get("replyCount"), c.get("text"), "; ".join(t for t, _ in tag_text(c.get("text", "")))])
    # stats JSON
    ser = {}
    for k, v in st.items():
        if isinstance(v, collections.Counter):
            ser[k] = v.most_common()
        elif k == "top_creators":
            ser[k] = [[p, a, n] for (p, a), n in v]
        else:
            ser[k] = v
    with open(os.path.join(OUT, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(ser, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    items = build()
    st = stats(items)
    export(items, st)
    print("items:", len(items), dict(st["counts_platform"]))
    print("mentions jj:", dict(st["counts_platform_jj"]), "recipe-like:", dict(st["counts_platform_recipe"]))
    print("dated:", dict(st["dated"]))
    print("categories:", st["categories"].most_common())
    print("tags all top20:", st["tags_all"].most_common(20))
    print("tags 2026 top20:", st["tags_2026"].most_common(20))
    print("monthly:", {m: v for m, v in st["monthly"].items() if m >= "2025-01"})
    print("comments:", st["n_comments"], st["comment_tags"].most_common(15))
    print("top creators:", st["top_creators"][:15])
