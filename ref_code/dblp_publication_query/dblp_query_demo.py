#!/usr/bin/env python3
"""
DBLP 论文发表情况查询 Demo

运行方式（需要联网访问 https://dblp.org）：
  1) 直接运行（默认查询示例论文）：
       python3 ref_code/call_llm/dblp_query_demo.py

  2) 查询任意标题：
       python3 ref_code/call_llm/dblp_query_demo.py --title "Paper Title"

       python3 ref_code/call_llm/dblp_query_demo.py  --title "QUEST: Query Optimization in Unstructured Document Analysis"

  3) 调整返回条数/匹配阈值：
       python3 ref_code/call_llm/dblp_query_demo.py --hits 20 --min-sim 0.92

该脚本演示 DBLP Publication Search API 的最小用法：
  - Endpoint: GET https://dblp.org/search/publ/api
  - 常用参数：
      q      : 查询关键词（支持用双引号做短语搜索，比如: "some title"）
      format : json / xml
      h      : 返回条数（hits）
      f      : offset（从第几条开始）
  - 返回结构（JSON）大致为：
      result -> hits -> hit[] -> info{title, venue, year, type, url, ee, doi, authors{author[...]}}

注意：
  - DBLP 同时可能收录正式发表版本（期刊/会议）以及预印本（如 CoRR/arXiv）。
  - 下面的“是否已发表”是一个启发式判断：优先认为 Journal Articles / Conference and Workshop Papers
    这两类为“已发表在期刊/会议”，而 Informal and Other Publications（如 CoRR）更像预印本。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Optional, Tuple


DBLP_PUBL_SEARCH_API = "https://dblp.org/search/publ/api"

# DBLP 搜索返回的 type 字段常见值（经验上）：
PEER_REVIEWED_TYPES = {
    "Journal Articles",
    "Conference and Workshop Papers",
}
INFORMAL_TYPES = {
    "Informal and Other Publications",
}
INFORMAL_VENUES = {
    "CoRR",
}


def _normalize_title(text: str) -> str:
    # 归一化：去掉大小写差异/全角半角差异/标点差异，并压缩空白。
    text = unicodedata.normalize("NFKC", text).lower()
    text = text.strip()
    # DBLP 的 title 往往以句号结尾；先统一去掉尾部的句号/空白。
    text = re.sub(r"[.\s]+$", "", text)
    # 移除大部分标点，仅保留字母数字空格（用于稳健匹配）。
    text = re.sub(r"[^0-9a-z]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _title_similarity(a: str, b: str) -> float:
    a_n = _normalize_title(a)
    b_n = _normalize_title(b)
    if not a_n or not b_n:
        return 0.0
    return SequenceMatcher(a=a_n, b=b_n).ratio()


def _build_search_url(query: str, hits: int, offset: int, quoted_phrase: bool) -> str:
    q = f"\"{query}\"" if quoted_phrase else query
    params = {
        "q": q,
        "format": "json",
        "h": str(hits),
        "f": str(offset),
    }
    return f"{DBLP_PUBL_SEARCH_API}?{urllib.parse.urlencode(params)}"


def _http_get_json(url: str, timeout_s: int) -> Dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={
            # DBLP 官方建议带上清晰的 UA，避免被当作爬虫误伤；这里给 demo 一个固定 UA。
            "User-Agent": "PaperCitedRemarkAnalysis/DBLPQueryDemo (+https://dblp.org)",
            "Accept": "application/json",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    return json.loads(body)


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _extract_authors(info: Dict[str, Any]) -> List[str]:
    authors_obj = info.get("authors") or {}
    author_field = authors_obj.get("author")
    authors: List[str] = []
    for item in _as_list(author_field):
        if isinstance(item, dict):
            name = item.get("text")
            if name:
                authors.append(str(name))
        elif isinstance(item, str):
            authors.append(item)
    return authors


def _extract_ee_links(info: Dict[str, Any]) -> List[str]:
    ee = info.get("ee")
    links: List[str] = []
    for item in _as_list(ee):
        if isinstance(item, str) and item.strip():
            links.append(item.strip())
        elif isinstance(item, dict) and item.get("text"):
            links.append(str(item["text"]).strip())
    return links


@dataclass(frozen=True)
class ScoredHit:
    sim: float
    score: float
    info: Dict[str, Any]

    @property
    def title(self) -> str:
        return str(self.info.get("title") or "")

    @property
    def venue(self) -> str:
        return str(self.info.get("venue") or "")

    @property
    def year(self) -> str:
        return str(self.info.get("year") or "")

    @property
    def pub_type(self) -> str:
        return str(self.info.get("type") or "")

    @property
    def dblp_url(self) -> str:
        return str(self.info.get("url") or "")


def _score_hits(query_title: str, hits: Iterable[Dict[str, Any]]) -> List[ScoredHit]:
    scored: List[ScoredHit] = []
    for hit in hits:
        info = hit.get("info") or {}
        title = str(info.get("title") or "")
        sim = _title_similarity(query_title, title)
        # @score 是字符串；缺失时默认 0。
        try:
            score = float(hit.get("@score") or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        scored.append(ScoredHit(sim=sim, score=score, info=info))
    return scored


def _pick_best_matches(scored: List[ScoredHit], min_sim: float) -> Tuple[List[ScoredHit], List[ScoredHit], List[ScoredHit]]:
    """返回 (peer_reviewed, informal, others) 三类匹配（只保留相似度 >= min_sim）。"""
    matched = [h for h in scored if h.sim >= min_sim]

    peer_reviewed: List[ScoredHit] = []
    informal: List[ScoredHit] = []
    others: List[ScoredHit] = []
    for h in matched:
        if h.pub_type in PEER_REVIEWED_TYPES and h.venue not in INFORMAL_VENUES:
            peer_reviewed.append(h)
        elif h.pub_type in INFORMAL_TYPES or h.venue in INFORMAL_VENUES:
            informal.append(h)
        else:
            others.append(h)

    # 排序：相似度 > 类型优先级 > DBLP score > 年份
    def sort_key(x: ScoredHit) -> Tuple[float, float, int]:
        year = 0
        try:
            year = int(x.year)
        except (TypeError, ValueError):
            year = 0
        return (x.sim, x.score, year)

    peer_reviewed.sort(key=sort_key, reverse=True)
    informal.sort(key=sort_key, reverse=True)
    others.sort(key=sort_key, reverse=True)
    return peer_reviewed, informal, others


def _safe_hits_list(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    hits_obj = (result.get("result") or {}).get("hits") or {}
    hit_field = hits_obj.get("hit")
    if hit_field is None:
        return []
    if isinstance(hit_field, list):
        return hit_field
    if isinstance(hit_field, dict):
        return [hit_field]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description="Query DBLP to verify whether a paper is published and where.")
    parser.add_argument(
        "--title",
        default="QUEST: Query Optimization in Unstructured Document Analysis",
        help="Paper title to query (default: the demo paper).",
    )
    parser.add_argument("--hits", type=int, default=20, help="How many hits to fetch from DBLP (h=).")
    parser.add_argument("--offset", type=int, default=0, help="Offset for hits (f=).")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds.")
    parser.add_argument(
        "--min-sim",
        type=float,
        default=0.92,
        help="Minimal title similarity to accept as the same paper (0~1).",
    )
    parser.add_argument(
        "--no-quote",
        action="store_true",
        help='Do not wrap title in quotes. By default we use phrase search: q="...".',
    )
    parser.add_argument("--show-top", type=int, default=5, help="Also show top-N candidates for manual check.")
    parser.add_argument("--raw-json", action="store_true", help="Print raw JSON payload and exit.")
    args = parser.parse_args()

    url = _build_search_url(
        query=args.title,
        hits=max(1, args.hits),
        offset=max(0, args.offset),
        quoted_phrase=not args.no_quote,
    )
    try:
        payload = _http_get_json(url, timeout_s=max(1, args.timeout))
    except Exception as e:  # demo 脚本：直接打印错误即可
        print(f"[ERROR] Failed to query DBLP: {e}", file=sys.stderr)
        print(f"[DEBUG] URL: {url}", file=sys.stderr)
        return 2

    if args.raw_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    hits = _safe_hits_list(payload)
    scored = _score_hits(args.title, hits)
    scored_sorted = sorted(scored, key=lambda x: (x.sim, x.score), reverse=True)

    peer_reviewed, informal, others = _pick_best_matches(scored_sorted, min_sim=args.min_sim)

    print("=== DBLP 论文发表情况核验（Demo） ===")
    print(f"Query title : {args.title}")
    print(f"DBLP API    : {url}")
    print(f"Hits fetched: {len(hits)}")
    print(f"Min sim     : {args.min_sim}")
    print()

    if peer_reviewed:
        best = peer_reviewed[0]
        print("[RESULT] 已发表（DBLP 命中期刊/会议版本）")
        print(f"Title : {best.title}")
        print(f"Type  : {best.pub_type}")
        print(f"Venue : {best.venue}")
        print(f"Year  : {best.year}")
        print(f"DBLP  : {best.dblp_url}")
        ee_links = _extract_ee_links(best.info)
        if ee_links:
            print(f"EE    : {ee_links[0]}")
        doi = best.info.get("doi")
        if doi:
            print(f"DOI   : {doi}")
        authors = _extract_authors(best.info)
        if authors:
            print(f"Authors ({len(authors)}): {', '.join(authors)}")
        print(f"Similarity: {best.sim:.3f} (score={best.score:g})")
        print()
        if informal:
            # 同标题存在 CoRR/预印本很常见；给出补充信息便于人工核验。
            alt = informal[0]
            print("[INFO] 同标题的预印本/非正式收录（如 CoRR）")
            print(f"Venue : {alt.venue}")
            print(f"Type  : {alt.pub_type}")
            print(f"Year  : {alt.year}")
            print(f"DBLP  : {alt.dblp_url}")
            print()
    elif informal:
        best = informal[0]
        print("[RESULT] 未发现期刊/会议发表版本；仅命中预印本/非正式收录（如 CoRR）")
        print(f"Title : {best.title}")
        print(f"Type  : {best.pub_type}")
        print(f"Venue : {best.venue}")
        print(f"Year  : {best.year}")
        print(f"DBLP  : {best.dblp_url}")
        ee_links = _extract_ee_links(best.info)
        if ee_links:
            print(f"EE    : {ee_links[0]}")
        print(f"Similarity: {best.sim:.3f} (score={best.score:g})")
        print()
    else:
        print("[RESULT] 未能在 DBLP 中找到可信匹配（可能未发表/DBLP 尚未收录/标题不一致）")
        print()

    if args.show_top > 0 and scored_sorted:
        print(f"--- Top {min(args.show_top, len(scored_sorted))} candidates ---")
        for i, h in enumerate(scored_sorted[: args.show_top], 1):
            print(f"{i:>2}. sim={h.sim:.3f} score={h.score:g} year={h.year} venue={h.venue} type={h.pub_type}")
            print(f"    {h.title}")
            print(f"    {h.dblp_url}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

