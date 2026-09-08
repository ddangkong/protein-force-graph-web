"""Full YouTube harvest for 짜파게티 recipe research.
Phase 1: multi-query search (recency filters + relevance) -> search_hits.jsonl
Phase 2: per-video details via `next` -> videos.jsonl
Phase 3: comments for selected videos -> comments.jsonl
Resumable: existing output lines are skipped.
"""
import json, os, sys, time, re, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from yt_api import call, iter_dicts, runs_text, search

BASE = os.path.dirname(os.path.abspath(__file__))
HITS = os.path.join(BASE, "search_hits.jsonl")
VIDEOS = os.path.join(BASE, "videos.jsonl")
COMMENTS = os.path.join(BASE, "comments.jsonl")
LOG = os.path.join(BASE, "harvest.log")
_lock = threading.Lock()


def log(msg):
    line = time.strftime("%H:%M:%S ") + msg
    with _lock:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    print(line, flush=True)


QUERIES_KO = [
    "짜파게티 레시피", "짜파게티 꿀조합", "짜파게티 맛있게 끓이는법", "짜파게티 튜닝", "짜파게티 만들기",
    "짜파게티 요리", "짜파게티 응용", "짜파게티 조합", "짜파게티 먹방", "짜파게티 #shorts", "짜파게티 쇼츠",
    "짜파게티 볶음밥", "짜파게티 치즈", "짜파게티 계란", "짜계치", "짜파구리", "사천 짜파게티", "윤남노 짜파게티",
    "정지선 짜파게티", "짜파게티 불닭", "짜파게티 너구리", "짜파게티 열라면", "짜파게티 파기름", "짜파게티 굴소스",
    "짜파게티 트러플", "짜파게티 새우", "짜파게티 삼겹살", "짜파게티 김치", "짜파게티 파김치", "짜파게티 전자레인지",
    "짜파게티 큰사발", "짜파게티 컵라면", "짜파게티 범벅", "짜파게티 더블랙", "짜파게티 요리대회", "짜파게티 요리사",
    "짜파게티 챌린지", "짜파게티 자취요리", "짜파게티 다이어트", "짜파게티 에어프라이어", "짜파게티 떡볶이",
    "짜파게티 만두", "짜파게티 스테이크", "짜파게티 마요네즈", "짜파게티 참치", "짜파게티 순후추", "짜파게티 카레",
    "짜파게티 물 안버리고", "짜파게티 면수", "짜파게티 국물", "짜파게티 밥", "짜파게티 편의점", "짜파게티 캠핑",
    "짜파게티 고기", "짜파게티 오일", "짜파게티 올리브유", "짜파게티 마라", "짜파게티 참깨라면", "짜파게티 짜왕",
    "짜장라면 꿀조합", "짜장라면 레시피",
]
QUERIES_EN = [
    "chapagetti recipe", "chapagetti hack", "chapagetti", "jjapaghetti recipe", "chapaguri recipe", "ram-don recipe",
    "chapagetti cheese", "nongshim chapagetti", "chapagetti mukbang",
]
# params: (label, params, max_pages)
PARAM_SETS = [
    ("today", "CAISAggC", 1),
    ("week", "CAISAggD", 3),
    ("month", "CAISAggE", 5),
    ("year", "CAISAggF", 6),
    ("views", "CAMSAhAB", 2),
    ("relevance", None, 3),
]


def load_jsonl(path, key):
    d = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    o = json.loads(line)
                    d[o[key]] = o
    return d


def append_jsonl(path, obj):
    with _lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def phase1():
    done = set()
    if os.path.exists(HITS):
        with open(HITS, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    o = json.loads(line)
                    done.add((o["query"], o["params"]))
    jobs = [(q, lab, p, n) for q in QUERIES_KO + QUERIES_EN for (lab, p, n) in PARAM_SETS]
    log(f"phase1: {len(jobs)} search jobs ({len(done)} already done)")
    for q, lab, p, n in jobs:
        if (q, p or "") in done:
            continue
        try:
            res = search(q, params=p, max_pages=n, log=lambda m: None)
        except Exception as e:
            log(f"  search failed {q!r}/{lab}: {e}")
            res = []
            time.sleep(5)
        for it in res:
            it["filter"] = lab
            append_jsonl(HITS, it)
        # write a sentinel so an empty result is also considered done
        if not res:
            append_jsonl(HITS, {"videoId": None, "query": q, "params": p or "", "filter": lab, "kind": "sentinel"})
        log(f"  {q!r}/{lab}: {len(res)} hits")
        time.sleep(0.5)


def parse_next(vid, d):
    out = {"videoId": vid}
    for x in iter_dicts(d):
        if "videoPrimaryInfoRenderer" in x and "title" not in out:
            p = x["videoPrimaryInfoRenderer"]
            out["title"] = runs_text(p.get("title"))
            vc = p.get("viewCount", {}).get("videoViewCountRenderer", {})
            out["viewCountText"] = runs_text(vc.get("viewCount"))
            out["dateText"] = runs_text(p.get("dateText"))
            out["relativeDateText"] = runs_text(p.get("relativeDateText"))
            for y in iter_dicts(p.get("videoActions", {})):
                if "segmentedLikeDislikeButtonViewModel" in y:
                    try:
                        out["likeText"] = y["segmentedLikeDislikeButtonViewModel"]["likeButtonViewModel"][
                            "likeButtonViewModel"]["toggleButtonViewModel"]["toggleButtonViewModel"][
                            "defaultButtonViewModel"]["buttonViewModel"]["title"]
                    except Exception:
                        pass
                    break
        if "videoSecondaryInfoRenderer" in x and "channel" not in out:
            s = x["videoSecondaryInfoRenderer"]
            own = s.get("owner", {}).get("videoOwnerRenderer", {})
            out["channel"] = runs_text(own.get("title"))
            out["subscriberText"] = runs_text(own.get("subscriberCountText"))
            out["channelId"] = own.get("navigationEndpoint", {}).get("browseEndpoint", {}).get("browseId")
            out["description"] = s.get("attributedDescription", {}).get("content") or runs_text(s.get("description"))
        if "commentsEntryPointHeaderRenderer" in x and "commentCountText" not in out:
            out["commentCountText"] = runs_text(x["commentsEntryPointHeaderRenderer"].get("commentCount"))
        if "itemSectionRenderer" in x and x["itemSectionRenderer"].get("sectionIdentifier") == "comment-item-section" \
                and "commentToken" not in out:
            for c in x["itemSectionRenderer"].get("contents", []):
                if "continuationItemRenderer" in c:
                    try:
                        out["commentToken"] = c["continuationItemRenderer"]["continuationEndpoint"][
                            "continuationCommand"]["token"]
                    except Exception:
                        pass
    # parse numbers
    m = re.search(r"([\d,]+)", out.get("viewCountText", "") or "")
    out["viewCount"] = int(m.group(1).replace(",", "")) if m else None
    m = re.search(r"(\d{4})\. (\d{1,2})\. (\d{1,2})\.", out.get("dateText", "") or "")
    out["publishDate"] = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else None
    out["ok"] = "title" in out and bool(out.get("title"))
    return out


def fetch_next(vid):
    try:
        d = call("next", {"videoId": vid})
        return parse_next(vid, d)
    except Exception as e:
        return {"videoId": vid, "ok": False, "error": str(e)[:200]}


JJ_RE = re.compile(r"짜파게티|짜파구리|짜계치|짜파|chapagetti|jjapagh?etti|jjapaguri|chapaguri|ram-?don|짜장라면", re.I)


def phase2(workers=4):
    hits = load_jsonl(HITS, "videoId")
    hits.pop(None, None)
    have = load_jsonl(VIDEOS, "videoId")
    todo = [v for v in hits if v not in have or not have[v].get("ok")]
    # prioritise videos whose search title/snippet mentions 짜파게티 (most relevant first)
    def prio(vid):
        h = hits[vid]
        txt = (h.get("title") or "") + " " + (h.get("snippet") or "")
        return 0 if JJ_RE.search(txt) else 1
    todo.sort(key=prio)
    log(f"phase2: {len(hits)} unique videos, {len(todo)} to fetch ({sum(1 for v in todo if prio(v)==0)} title-matched first)")
    n = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fetch_next, v): v for v in todo}
        for fut in as_completed(futs):
            r = fut.result()
            append_jsonl(VIDEOS, r)
            n += 1
            if n % 50 == 0:
                log(f"  details {n}/{len(todo)}")
            time.sleep(0.15)
    log("phase2 done")


def parse_comment_page(data):
    ents, order, token = {}, [], None
    for d in iter_dicts(data.get("frameworkUpdates", {})):
        if "commentEntityPayload" in d:
            p = d["commentEntityPayload"]
            props = p.get("properties", {})
            ents[props.get("commentId")] = {
                "commentId": props.get("commentId"),
                "text": runs_text(props.get("content", {})),
                "publishedTime": props.get("publishedTime"),
                "author": p.get("author", {}).get("displayName"),
                "likes": p.get("toolbar", {}).get("likeCountNotliked"),
                "replyCount": p.get("toolbar", {}).get("replyCount"),
            }
    for ep in data.get("onResponseReceivedEndpoints", []):
        items = (ep.get("reloadContinuationItemsCommand") or ep.get("appendContinuationItemsAction") or {}).get(
            "continuationItems", [])
        for it in items:
            if "commentThreadRenderer" in it:
                ct = it["commentThreadRenderer"]
                try:
                    cid = ct["commentViewModel"]["commentViewModel"]["commentId"]
                    if cid in ents:
                        order.append(ents[cid])
                except Exception:
                    cr = ct.get("comment", {}).get("commentRenderer")
                    if cr:
                        order.append({"commentId": cr.get("commentId"), "text": runs_text(cr.get("contentText")),
                                      "publishedTime": runs_text(cr.get("publishedTimeText")),
                                      "author": runs_text(cr.get("authorText")),
                                      "likes": runs_text(cr.get("voteCount")), "replyCount": None})
            elif "continuationItemRenderer" in it:
                try:
                    token = it["continuationItemRenderer"]["continuationEndpoint"]["continuationCommand"]["token"]
                except Exception:
                    pass
    return order, token


def fetch_comments(vid, token, max_comments=30):
    out = []
    try:
        while token and len(out) < max_comments:
            data = call("next", {"continuation": token})
            page, token = parse_comment_page(data)
            if not page:
                break
            out.extend(page)
            time.sleep(0.3)
    except Exception as e:
        return {"videoId": vid, "comments": out, "error": str(e)[:200]}
    return {"videoId": vid, "comments": out[:max_comments]}


def select_for_comments(videos, cap=450):
    vs = [v for v in videos.values() if v.get("ok") and v.get("commentToken")]
    recent = [v for v in vs if (v.get("publishDate") or "") >= "2025-01-01" and (v.get("viewCount") or 0) >= 5000]
    popular = [v for v in vs if (v.get("viewCount") or 0) >= 200000]
    sel = {v["videoId"]: v for v in recent + popular}
    ranked = sorted(sel.values(), key=lambda v: -(v.get("viewCount") or 0))
    return ranked[:cap]


def phase3(workers=3):
    videos = load_jsonl(VIDEOS, "videoId")
    have = load_jsonl(COMMENTS, "videoId")
    sel = [v for v in select_for_comments(videos) if v["videoId"] not in have]
    log(f"phase3: {len(sel)} videos for comments")
    n = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fetch_comments, v["videoId"], v["commentToken"]): v for v in sel}
        for fut in as_completed(futs):
            r = fut.result()
            append_jsonl(COMMENTS, r)
            n += 1
            if n % 25 == 0:
                log(f"  comments {n}/{len(sel)}")
    log("phase3 done")


if __name__ == "__main__":
    phases = sys.argv[1:] or ["1", "2", "3"]
    if "1" in phases:
        phase1()
    if "2" in phases:
        phase2()
    if "3" in phases:
        phase3()
    log("ALL DONE")
