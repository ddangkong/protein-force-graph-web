"""Minimal YouTube InnerTube client via youtubei.googleapis.com (allowed host).
Provides: search (with continuation), player (video details/description), comments.
"""
import json, time, re, sys, os
import requests

API = "https://youtubei.googleapis.com/youtubei/v1/"
CLIENT_VERSION = "2.20250825.01.00"
CTX = {"client": {"clientName": "WEB", "clientVersion": CLIENT_VERSION, "hl": "ko", "gl": "KR",
                  "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"}}
HDR = {"Content-Type": "application/json", "X-YouTube-Client-Name": "1",
       "X-YouTube-Client-Version": CLIENT_VERSION,
       "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36",
       "Accept-Language": "ko-KR,ko;q=0.9"}

_session = requests.Session()


def call(ep, body, retries=4):
    body = dict(body)
    body.setdefault("context", CTX)
    last = None
    for i in range(retries):
        try:
            r = _session.post(API + ep + "?prettyPrint=false", json=body, headers=HDR, timeout=40)
            if r.status_code == 200:
                return r.json()
            last = f"HTTP {r.status_code}: {r.text[:200]}"
            if r.status_code in (400, 404):
                break
        except Exception as e:  # noqa
            last = repr(e)
        time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"{ep} failed: {last}")


def runs_text(o):
    if not o:
        return ""
    if isinstance(o, str):
        return o
    if "simpleText" in o:
        return o["simpleText"]
    if "runs" in o:
        return "".join(r.get("text", "") for r in o["runs"])
    if "content" in o and isinstance(o["content"], str):
        return o["content"]
    return ""


def iter_dicts(o):
    """Yield every dict in a nested structure."""
    stack = [o]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            yield cur
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)


def parse_search_items(data):
    items, cont = [], None
    for d in iter_dicts(data):
        if "videoRenderer" in d:
            v = d["videoRenderer"]
            snippets = v.get("detailedMetadataSnippets") or []
            snippet = " ".join(runs_text(s.get("snippetText")) for s in snippets)
            badges = [runs_text(b.get("metadataBadgeRenderer", {}).get("label")) for b in v.get("badges", [])]
            overlays = []
            for ov in v.get("thumbnailOverlays", []):
                for k, val in ov.items():
                    if isinstance(val, dict) and "text" in val:
                        overlays.append(runs_text(val["text"]))
            items.append({
                "videoId": v.get("videoId"),
                "kind": "video",
                "title": runs_text(v.get("title")),
                "channel": runs_text(v.get("ownerText")) or runs_text(v.get("longBylineText")),
                "channelId": (v.get("ownerText", {}).get("runs", [{}])[0].get("navigationEndpoint", {})
                              .get("browseEndpoint", {}).get("browseId")),
                "publishedTimeText": runs_text(v.get("publishedTimeText")),
                "viewCountText": runs_text(v.get("viewCountText")) or runs_text(v.get("shortViewCountText")),
                "lengthText": runs_text(v.get("lengthText")),
                "snippet": snippet,
                "badges": [b for b in badges if b],
                "overlays": overlays,
            })
        elif "shortsLockupViewModel" in d:
            v = d["shortsLockupViewModel"]
            vid = None
            try:
                vid = v["onTap"]["innertubeCommand"]["reelWatchEndpoint"]["videoId"]
            except Exception:
                eid = v.get("entityId", "")
                m = re.search(r"shorts-shelf-item-([A-Za-z0-9_-]{11})", eid)
                vid = m.group(1) if m else None
            om = v.get("overlayMetadata", {})
            items.append({
                "videoId": vid, "kind": "short",
                "title": runs_text(om.get("primaryText")),
                "channel": "", "channelId": None, "publishedTimeText": "",
                "viewCountText": runs_text(om.get("secondaryText")),
                "lengthText": "", "snippet": "", "badges": [], "overlays": [],
            })
        elif "reelItemRenderer" in d:
            v = d["reelItemRenderer"]
            items.append({
                "videoId": v.get("videoId"), "kind": "short",
                "title": runs_text(v.get("headline")),
                "channel": "", "channelId": None, "publishedTimeText": "",
                "viewCountText": runs_text(v.get("viewCountText")),
                "lengthText": "", "snippet": "", "badges": [], "overlays": [],
            })
        elif "continuationItemRenderer" in d and cont is None:
            try:
                cont = d["continuationItemRenderer"]["continuationEndpoint"]["continuationCommand"]["token"]
            except Exception:
                pass
    # continuation may also live in onResponseReceivedCommands
    if cont is None:
        for d in iter_dicts(data):
            if "continuationCommand" in d and "token" in d["continuationCommand"]:
                cont = d["continuationCommand"]["token"]
                break
    return items, cont


def search(query, params=None, max_pages=5, sleep=0.8, log=print):
    out, seen = [], set()
    body = {"query": query}
    if params:
        body["params"] = params
    cont = None
    for page in range(max_pages):
        data = call("search", body if cont is None else {"continuation": cont})
        items, cont = parse_search_items(data)
        new = 0
        for it in items:
            if it["videoId"] and it["videoId"] not in seen:
                seen.add(it["videoId"])
                it["query"] = query
                it["params"] = params or ""
                it["page"] = page + 1
                out.append(it)
                new += 1
        log(f"  search[{query!r} params={params}] page {page+1}: {len(items)} items, {new} new, total {len(out)}")
        if not cont or new == 0:
            break
        time.sleep(sleep)
    return out


def player(video_id):
    data = call("player", {"videoId": video_id, "contentCheckOk": True, "racyCheckOk": True})
    vd = data.get("videoDetails", {})
    mf = data.get("microformat", {}).get("playerMicroformatRenderer", {})
    return {
        "videoId": video_id,
        "title": vd.get("title"),
        "channel": vd.get("author"),
        "channelId": vd.get("channelId"),
        "lengthSeconds": int(vd.get("lengthSeconds") or 0),
        "viewCount": int(vd.get("viewCount") or 0),
        "description": vd.get("shortDescription", ""),
        "keywords": vd.get("keywords", []),
        "publishDate": mf.get("publishDate"),
        "uploadDate": mf.get("uploadDate"),
        "category": mf.get("category"),
        "likeCount": None,
        "playability": data.get("playabilityStatus", {}).get("status"),
    }


def comments(video_id, max_comments=30, sleep=0.6):
    """Return (comment_count_text, [comments]) using the next endpoint."""
    data = call("next", {"videoId": video_id})
    token = None
    for d in iter_dicts(data):
        if "itemSectionRenderer" in d and d["itemSectionRenderer"].get("sectionIdentifier") == "comment-item-section":
            for c in d["itemSectionRenderer"].get("contents", []):
                if "continuationItemRenderer" in c:
                    token = c["continuationItemRenderer"]["continuationEndpoint"]["continuationCommand"]["token"]
                    break
        if token:
            break
    like_text = None
    for d in iter_dicts(data):
        # like button (segmented like/dislike)
        if "segmentedLikeDislikeButtonViewModel" in d:
            try:
                like_text = d["segmentedLikeDislikeButtonViewModel"]["likeButtonViewModel"]["likeButtonViewModel"][
                    "toggleButtonViewModel"]["toggleButtonViewModel"]["defaultButtonViewModel"]["buttonViewModel"]["title"]
            except Exception:
                pass
            break
    if not token:
        return {"commentCountText": None, "likeText": like_text, "comments": []}
    result, count_text = [], None
    while token and len(result) < max_comments:
        data = call("next", {"continuation": token})
        token = None
        # new-style entity payloads
        ents = {}
        for d in iter_dicts(data.get("frameworkUpdates", {})):
            if "commentEntityPayload" in d:
                p = d["commentEntityPayload"]
                key = p.get("key") or p.get("properties", {}).get("commentId")
                props = p.get("properties", {})
                ents[props.get("commentId")] = {
                    "commentId": props.get("commentId"),
                    "text": runs_text(props.get("content", {})),
                    "publishedTime": props.get("publishedTime"),
                    "author": p.get("author", {}).get("displayName"),
                    "likes": p.get("toolbar", {}).get("likeCountNotliked") or p.get("toolbar", {}).get("likeCountA11y"),
                    "replyCount": p.get("toolbar", {}).get("replyCount"),
                }
        # order per commentThreadRenderer sequence
        for d in iter_dicts(data):
            if "commentsHeaderRenderer" in d and count_text is None:
                count_text = runs_text(d["commentsHeaderRenderer"].get("countText")) or runs_text(
                    d["commentsHeaderRenderer"].get("commentsCount"))
            if "commentThreadRenderer" in d:
                ct = d["commentThreadRenderer"]
                cid = None
                try:
                    cid = ct["commentViewModel"]["commentViewModel"]["commentId"]
                except Exception:
                    cr = ct.get("comment", {}).get("commentRenderer")
                    if cr:
                        result.append({"commentId": cr.get("commentId"), "text": runs_text(cr.get("contentText")),
                                       "publishedTime": runs_text(cr.get("publishedTimeText")),
                                       "author": runs_text(cr.get("authorText")),
                                       "likes": runs_text(cr.get("voteCount")), "replyCount": None})
                        continue
                if cid and cid in ents:
                    result.append(ents[cid])
            if "continuationItemRenderer" in d and token is None:
                try:
                    tok = d["continuationItemRenderer"]["continuationEndpoint"]["continuationCommand"]["token"]
                    # skip reply continuations (they hang under commentRepliesRenderer)
                    token = tok
                except Exception:
                    pass
        if len(result) >= max_comments:
            break
        time.sleep(sleep)
    return {"commentCountText": count_text, "likeText": like_text, "comments": result[:max_comments]}


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "짜파게티 레시피"
    for params in ["CAI=", "CAISAggE", "CAISBAgFEAE="]:
        res = search(q, params=params, max_pages=1)
        print(params, len(res))
        for it in res[:8]:
            print("   ", it["kind"], it["videoId"], it["publishedTimeText"], "|", it["title"][:50], "|", it["channel"], "|", it["viewCountText"])
    print("--- player test")
    p = player(res[0]["videoId"] if res else "w7kAOqnYQ_c")
    print(json.dumps({k: (v[:200] if isinstance(v, str) else v) for k, v in p.items()}, ensure_ascii=False, indent=1))
    print("--- comments test")
    c = comments("w7kAOqnYQ_c", max_comments=10)
    print(c["commentCountText"], c["likeText"])
    for cm in c["comments"]:
        print("  ", cm["publishedTime"], cm["likes"], cm["author"], "|", (cm["text"] or "")[:100].replace("\n", " "))
