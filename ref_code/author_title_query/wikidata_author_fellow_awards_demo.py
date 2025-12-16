#!/usr/bin/env python3
"""
Wikidata 作者头衔/称号 Demo：从 Wikidata 提取包含 “Fellow” 的 award received(P166)。

该脚本演示 Wikidata（MediaWiki/Wikibase）常用 API 的最小用法：
  - 搜索实体（按作者名）：GET https://www.wikidata.org/w/api.php?action=wbsearchentities
  - 获取实体详情：GET https://www.wikidata.org/wiki/Special:EntityData/Qxxxx.json
  - 批量取 label/aliases：GET https://www.wikidata.org/w/api.php?action=wbgetentities

实现逻辑：
  1) 用作者名搜索候选实体；
  2) 若提供机构名：在候选实体的 employer(P108)/affiliation(P1416) 中做字符串匹配，选择第一个匹配者；
     若不提供机构名：直接选择第一个候选实体；
  3) 进入该作者实体，读取 award received(P166)；
  4) 取出其中 label 包含关键字（默认 Fellow）的条目，原样输出为 JSON。

示例：
  /data/QUEST/jzshe/miniconda3/envs/rag-any/bin/python \\
    ref_code/author_title_query/wikidata_author_fellow_awards_demo.py \\
    --name "Qiang Yang" --affiliation "Hong Kong University of Science and Technology"

  # 也可用单个字符串（用 2 个及以上空格分隔“姓名”和“机构”）：
  /data/QUEST/jzshe/miniconda3/envs/rag-any/bin/python \\
    ref_code/author_title_query/wikidata_author_fellow_awards_demo.py \\
    --query "Qiang Yang  Hong Kong University of Science and Technology"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIDATA_ENTITYDATA = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"

PID_INSTANCE_OF = "P31"
QID_HUMAN = "Q5"
PID_EMPLOYER = "P108"
PID_AFFILIATION = "P1416"
PID_AWARD_RECEIVED = "P166"


def _http_get_json(url: str, timeout_s: int, max_retries: int = 2) -> Dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "PaperCitedRemarkAnalysis/WikidataAuthorTitleDemo (+https://www.wikidata.org/)",
            "Accept": "application/json",
        },
        method="GET",
    )
    last_err: Optional[BaseException] = None
    for attempt in range(max(1, max_retries) + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            return json.loads(body)
        except Exception as e:  # demo 脚本：统一处理
            last_err = e
            # 简单退避，尽量避免 429/5xx 短暂抖动导致失败
            if attempt < max_retries + 1:
                time.sleep(0.6 * attempt)
                continue
            break
    raise RuntimeError(f"HTTP request failed after retries: {last_err}")


def _normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower().strip()
    text = re.sub(r"[^0-9a-z]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _dedupe_keep_order(items: Iterable[str]) -> List[str]:
    seen: Dict[str, None] = {}
    out: List[str] = []
    for x in items:
        if x in seen:
            continue
        seen[x] = None
        out.append(x)
    return out


def wikidata_search_entities(query: str, language: str, limit: int, timeout_s: int) -> List[Dict[str, Any]]:
    params = {
        "action": "wbsearchentities",
        "search": query,
        "language": language,
        "format": "json",
        "type": "item",
        "limit": str(limit),
    }
    url = f"{WIKIDATA_API}?{urllib.parse.urlencode(params)}"
    payload = _http_get_json(url, timeout_s=timeout_s)
    results = payload.get("search")
    if not isinstance(results, list):
        return []
    return [r for r in results if isinstance(r, dict) and r.get("id")]


def wikidata_get_entitydata(qid: str, timeout_s: int) -> Dict[str, Any]:
    url = WIKIDATA_ENTITYDATA.format(qid=qid)
    payload = _http_get_json(url, timeout_s=timeout_s)
    entities = payload.get("entities") or {}
    if not isinstance(entities, dict) or qid not in entities:
        raise RuntimeError(f"Missing entity data for {qid}")
    entity = entities[qid]
    if not isinstance(entity, dict):
        raise RuntimeError(f"Invalid entity payload for {qid}")
    return entity


def _extract_entity_ids_from_claims(entity: Mapping[str, Any], pid: str) -> List[str]:
    claims = (entity.get("claims") or {}).get(pid) or []
    if not isinstance(claims, list):
        return []
    out: List[str] = []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        mainsnak = claim.get("mainsnak") or {}
        if not isinstance(mainsnak, dict) or mainsnak.get("snaktype") != "value":
            continue
        datavalue = mainsnak.get("datavalue") or {}
        if not isinstance(datavalue, dict) or datavalue.get("type") != "wikibase-entityid":
            continue
        value = datavalue.get("value") or {}
        if isinstance(value, dict) and isinstance(value.get("id"), str) and value["id"].startswith("Q"):
            out.append(value["id"])
    return out


def _extract_best_label(entity: Mapping[str, Any], languages: Sequence[str]) -> Optional[str]:
    labels = entity.get("labels") or {}
    if not isinstance(labels, dict):
        return None
    for lang in languages:
        obj = labels.get(lang) or {}
        if isinstance(obj, dict) and isinstance(obj.get("value"), str) and obj["value"].strip():
            return obj["value"].strip()
    # fallback: any label
    for obj in labels.values():
        if isinstance(obj, dict) and isinstance(obj.get("value"), str) and obj["value"].strip():
            return obj["value"].strip()
    return None


def wikidata_get_entities_labels_aliases(
    qids: Sequence[str],
    languages: str,
    timeout_s: int,
) -> Dict[str, Dict[str, Any]]:
    """
    返回 {qid: {"label": str|None, "aliases": [str, ...]}}。
    """
    qids = [q for q in qids if isinstance(q, str) and q.startswith("Q")]
    if not qids:
        return {}

    result: Dict[str, Dict[str, Any]] = {}
    chunk_size = 50
    for i in range(0, len(qids), chunk_size):
        chunk = qids[i : i + chunk_size]
        params = {
            "action": "wbgetentities",
            "ids": "|".join(chunk),
            "props": "labels|aliases",
            "languages": languages,
            "format": "json",
        }
        url = f"{WIKIDATA_API}?{urllib.parse.urlencode(params)}"
        payload = _http_get_json(url, timeout_s=timeout_s)
        entities = payload.get("entities") or {}
        if not isinstance(entities, dict):
            continue
        for qid, ent in entities.items():
            if not isinstance(ent, dict):
                continue
            label = _extract_best_label(ent, languages=languages.split("|"))
            aliases_obj = ent.get("aliases") or {}
            aliases: List[str] = []
            if isinstance(aliases_obj, dict):
                for lang in languages.split("|"):
                    for item in aliases_obj.get(lang) or []:
                        if isinstance(item, dict) and isinstance(item.get("value"), str) and item["value"].strip():
                            aliases.append(item["value"].strip())
            result[qid] = {"label": label, "aliases": _dedupe_keep_order(aliases)}
    return result


def _is_human(entity: Mapping[str, Any]) -> bool:
    instance_of = _extract_entity_ids_from_claims(entity, PID_INSTANCE_OF)
    return QID_HUMAN in set(instance_of)


def _affiliation_matches(entity: Mapping[str, Any], affiliation: str, timeout_s: int) -> Tuple[bool, List[str]]:
    aff_norm = _normalize_text(affiliation)
    if not aff_norm:
        return False, []

    org_qids = _dedupe_keep_order(
        _extract_entity_ids_from_claims(entity, PID_EMPLOYER)
        + _extract_entity_ids_from_claims(entity, PID_AFFILIATION)
    )
    if not org_qids:
        return False, []

    org_info = wikidata_get_entities_labels_aliases(org_qids, languages="en", timeout_s=timeout_s)
    matched_org_labels: List[str] = []
    for qid in org_qids:
        info = org_info.get(qid) or {}
        label = info.get("label")
        aliases = info.get("aliases") or []
        candidates: List[str] = []
        if isinstance(label, str):
            candidates.append(label)
        if isinstance(aliases, list):
            candidates.extend([a for a in aliases if isinstance(a, str)])
        for cand in candidates:
            cand_norm = _normalize_text(cand)
            if not cand_norm:
                continue
            if aff_norm in cand_norm or cand_norm in aff_norm:
                if isinstance(label, str) and label.strip():
                    matched_org_labels.append(label.strip())
                else:
                    matched_org_labels.append(cand)
                break

    matched_org_labels = _dedupe_keep_order(matched_org_labels)
    return bool(matched_org_labels), matched_org_labels


def pick_author_entity(
    name: str,
    affiliation: Optional[str],
    language: str,
    search_limit: int,
    require_human: bool,
    timeout_s: int,
) -> Tuple[Dict[str, Any], Dict[str, Any], str, List[Dict[str, Any]]]:
    """
    返回 (author_entitydata, search_hit, reason, debug_candidates)。
    """
    hits = wikidata_search_entities(name, language=language, limit=search_limit, timeout_s=timeout_s)
    if not hits:
        raise RuntimeError(f'No wikidata entity found for name="{name}" (language={language})')

    fallback: Optional[Tuple[Dict[str, Any], Dict[str, Any], str]] = None
    debug_candidates: List[Dict[str, Any]] = []

    for hit in hits:
        qid = str(hit["id"])
        try:
            entity = wikidata_get_entitydata(qid, timeout_s=timeout_s)
        except Exception as e:
            debug_candidates.append({"id": qid, "error": str(e)})
            continue

        human = _is_human(entity)
        if require_human and not human:
            debug_candidates.append({"id": qid, "label": hit.get("label"), "description": hit.get("description"), "human": False})
            continue

        if fallback is None:
            fallback = (entity, hit, "first_human" if human else "first_candidate")

        if affiliation:
            ok, matched_orgs = _affiliation_matches(entity, affiliation=affiliation, timeout_s=timeout_s)
            debug_candidates.append(
                {
                    "id": qid,
                    "label": hit.get("label"),
                    "description": hit.get("description"),
                    "human": human,
                    "affiliation_match": ok,
                    "matched_orgs": matched_orgs,
                }
            )
            if ok:
                return entity, hit, "matched_affiliation", debug_candidates
        else:
            debug_candidates.append(
                {
                    "id": qid,
                    "label": hit.get("label"),
                    "description": hit.get("description"),
                    "human": human,
                }
            )
            return entity, hit, "first_match", debug_candidates

    if fallback is not None:
        entity, hit, reason = fallback
        return entity, hit, reason, debug_candidates

    # require_human=True 且没有 human：退化到第一个搜索结果
    qid = str(hits[0]["id"])
    entity = wikidata_get_entitydata(qid, timeout_s=timeout_s)
    return entity, hits[0], "fallback_first_hit", debug_candidates


def extract_award_received(entity: Mapping[str, Any], timeout_s: int, languages: str) -> List[Dict[str, Any]]:
    award_qids = _dedupe_keep_order(_extract_entity_ids_from_claims(entity, PID_AWARD_RECEIVED))
    if not award_qids:
        return []

    award_info = wikidata_get_entities_labels_aliases(award_qids, languages=languages, timeout_s=timeout_s)
    out: List[Dict[str, Any]] = []
    for qid in award_qids:
        info = award_info.get(qid) or {}
        out.append({"id": qid, "label": info.get("label"), "aliases": info.get("aliases") or []})
    return out


def _parse_query(query: str) -> Tuple[str, Optional[str]]:
    q = query.strip()
    if not q:
        return "", None
    parts = [p.strip() for p in re.split(r"\s{2,}", q) if p.strip()]
    if len(parts) >= 2:
        name = parts[0]
        affiliation = " ".join(parts[1:]).strip()
        return name, affiliation or None
    return q, None


def main() -> int:
    parser = argparse.ArgumentParser(description="Query Wikidata awards received(P166) and extract items whose label contains 'Fellow'.")
    parser.add_argument(
        "--query",
        default=None,
        help='Single query string. If it contains 2+ spaces, we treat it as "name  affiliation".',
    )
    parser.add_argument("--name", default=None, help="Author name to search on Wikidata (e.g. 'Qiang Yang').")
    parser.add_argument("--affiliation", default=None, help="Optional affiliation/institution name for disambiguation.")
    parser.add_argument("--language", default="en", help="Search language for wbsearchentities (default: en).")
    parser.add_argument("--search-limit", type=int, default=20, help="How many candidates to consider (default: 20).")
    parser.add_argument("--keyword", default="Fellow", help="Keyword to match in award labels (default: Fellow).")
    parser.add_argument("--labels-languages", default="en", help="Languages for award labels (wbgetentities languages=, default: en).")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds.")
    parser.add_argument("--no-require-human", action="store_true", help="Do not filter candidates by instance of human(Q5).")
    parser.add_argument("--debug", action="store_true", help="Include candidate evaluation details in output JSON.")
    args = parser.parse_args()

    name = args.name or ""
    affiliation = args.affiliation
    if args.query and not name:
        name, parsed_affiliation = _parse_query(args.query)
        if affiliation is None:
            affiliation = parsed_affiliation

    if not name.strip():
        print("[ERROR] Missing author name: provide --name or --query.", file=sys.stderr)
        return 2

    try:
        author_entity, author_hit, reason, debug_candidates = pick_author_entity(
            name=name,
            affiliation=affiliation,
            language=args.language,
            search_limit=max(1, args.search_limit),
            require_human=not args.no_require_human,
            timeout_s=max(1, args.timeout),
        )
    except Exception as e:
        print(f"[ERROR] Failed to pick author entity: {e}", file=sys.stderr)
        return 2

    author_qid = str(author_entity.get("id") or author_hit.get("id") or "")
    author_label = _extract_best_label(author_entity, languages=(args.language, "en", "zh"))
    author_desc_obj = author_entity.get("descriptions") or {}
    author_desc = None
    if isinstance(author_desc_obj, dict):
        for lang in (args.language, "en", "zh"):
            obj = author_desc_obj.get(lang) or {}
            if isinstance(obj, dict) and isinstance(obj.get("value"), str) and obj["value"].strip():
                author_desc = obj["value"].strip()
                break

    awards = extract_award_received(author_entity, timeout_s=max(1, args.timeout), languages=args.labels_languages)
    keyword_norm = args.keyword.lower()
    fellow_awards: List[Dict[str, Any]] = []
    award_items: List[Dict[str, Any]] = []
    for a in awards:
        label = a.get("label")
        label_str = label if isinstance(label, str) else ""
        matched = keyword_norm in label_str.lower() if label_str else False
        award_items.append({"id": a.get("id"), "label": label, "matched": matched})
        if matched:
            fellow_awards.append({"id": a.get("id"), "label": label})

    output: Dict[str, Any] = {
        "input": {
            "name": name,
            "affiliation": affiliation,
            "keyword": args.keyword,
            "search_language": args.language,
        },
        "matched_author": {
            "id": author_qid,
            "label": author_label,
            "description": author_desc,
            "selection_reason": reason,
            "url": f"https://www.wikidata.org/wiki/{author_qid}" if author_qid else None,
        },
        "award_received": {
            "property": PID_AWARD_RECEIVED,
            "total": len(award_items),
            "keyword_matched": len(fellow_awards),
            "items": award_items,
        },
        "keyword_items": fellow_awards,
    }
    if args.debug:
        output["debug_candidates"] = debug_candidates

    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
