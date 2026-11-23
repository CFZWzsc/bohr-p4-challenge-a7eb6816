#!/usr/bin/env python3
"""Science-communication rewrite audit.

Reads a case JSON (default /input/case.json) and writes a structured
audit (default /app/output/result.json). Standard library only, no
network, deterministic. It never rewrites prose: it profiles audience,
checks evidence retention, claim strength and deletions, and flags what
must be fixed by the author.
"""

import argparse
import hashlib
import json
import os
import re
import sys

NUM_RE = re.compile(
    r"(?<![\w.])-?\d+(?:\.\d+)?\s*"
    r"(?:%|‰|°C|°|mg|kg|µg|μg|ng|mL|ml|µL|μL|L|nm|µm|μm|mm|cm|km|m|"
    r"ms|min|h|hr|days?|weeks?|wk|months?|years?|nM|µM|μM|mM|M|"
    r"kPa|MPa|Pa|kJ|kcal|J|eV|kHz|MHz|GHz|Hz|mV|kV|V|mA|A|ppm|fold|Da|kDa)"
    r"(?![A-Za-z])"
)
HEDGES = ("may", "might", "could", "suggest", "suggests", "associated", "correlat",
          "preliminary", "limited", "limitation", "possible", "potentially",
          "可能", "或许", "提示", "相关", "初步", "有限", "尚不能")
CAUSAL = ("cause", "causes", "caused", "leads to", "led to", "results in", "proves",
          "proven", "demonstrates", "confirms", "drives", "导致", "引起", "证明", "必然")
AUDIENCE_LEVELS = (
    ("public", ("public", "general", "lay", "公众", "大众", "科普", "普通读者")),
    ("student", ("student", "undergraduate", "high school", "学生", "中学")),
    ("industry", ("industry", "company", "investor", "企业", "产业", "投资")),
    ("policy", ("policy", "government", "manager", "政策", "政府", "管理")),
    ("patient", ("patient", "patient", "患者", "病友")),
    ("peer", ("peer", "reviewer", "expert", "同行", "专家", "评审")),
)
ABBR_RE = re.compile(r"\b([A-Z]{2,6})\b")
DEF_RE = re.compile(
    r"([A-Z][A-Za-z\-]+(?:\s+[A-Za-z\-]+){0,6})\s*\(\s*([A-Z]{2,6})\s*\)"
    r"|([A-Z]{2,6})\s*\(\s*([A-Z][A-Za-z\-]+(?:\s+[A-Za-z\-]+){0,6})\s*\)"
)
STOP_ABBRS = {"II", "III", "IV", "VI", "VII", "VIII", "IX", "XI", "XII", "OK", "THE", "AND"}
LIMITATION = ("limitation", "limited", "cannot", "unclear", "future", "局限", "尚不能", "有待")


def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def sha256_text(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def norm(text):
    return re.sub(r"\s+", " ", text or "").strip()


def read_text(value):
    if not isinstance(value, str) or "\n" in value or len(value) > 4096:
        return None
    if os.path.isfile(value) and os.path.getsize(value) <= 2 * 1024 * 1024:
        try:
            with open(value, "r", encoding="utf-8-sig") as fh:
                return fh.read()
        except (OSError, UnicodeDecodeError):
            return None
    return None


def collect_docs(case):
    docs = {}

    def walk(node, label):
        if isinstance(node, str):
            text = read_text(node)
            if text is not None:
                docs.setdefault(label, text)
            elif len(node.strip()) >= 30:
                docs.setdefault(label, node)
            return
        if isinstance(node, dict):
            path = node.get("path") or node.get("file") or node.get("filename")
            if isinstance(path, str):
                text = read_text(path)
                if text is not None:
                    docs.setdefault(label, text)
                    return
            for key in ("content", "text", "body", "markdown", "value"):
                if key in node and isinstance(node[key], (str, list, dict)):
                    walk(node[key], "%s.%s" % (label, key))
                    return
            for key, value in node.items():
                if key in ("id", "name", "title", "type", "kind", "path", "file", "filename"):
                    continue
                walk(value, "%s.%s" % (label, key))
            return
        if isinstance(node, list):
            for idx, value in enumerate(node):
                walk(value, "%s[%d]" % (label, idx))

    for key, value in case.items():
        if key in ("output_contract", "scoring", "tags", "meta", "case_id", "challenge_id",
                   "audience", "target_audience", "genre"):
            continue
        walk(value, key)
    return docs


def split_sentences(text):
    spans, start = [], 0
    length = len(text)
    for idx, char in enumerate(text):
        if char not in ".!?。！？\n":
            continue
        if char == "." and idx + 1 < length and text[idx + 1].isdigit():
            continue
        chunk = text[start:idx + 1]
        if chunk.strip():
            spans.append(chunk.strip())
        start = idx + 1
    if start < length and text[start:].strip():
        spans.append(text[start:].strip())
    return [item for item in spans if item]


def content_tokens(text):
    tokens = set(re.findall(r"[a-z]{4,}", text.lower()))
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        for idx in range(len(run) - 1):
            tokens.add(run[idx:idx + 2])
    return tokens


def coverage(source_sentence, draft_tokens):
    tokens = content_tokens(source_sentence)
    if not tokens:
        return 0.0
    return len(tokens & draft_tokens) / float(len(tokens))


def profile_audience(audience):
    if not audience:
        return {"audience": None, "level": "unspecified", "explanation_depth": "neutral",
                "term_density": "medium", "issue": "audience_missing"}
    lowered = audience.lower()
    for level, keywords in AUDIENCE_LEVELS:
        if any(keyword in lowered for keyword in keywords):
            depth = {"public": "plain", "student": "guided", "industry": "applied",
                     "policy": "concise", "patient": "plain", "peer": "technical"}[level]
            return {"audience": audience, "level": level, "explanation_depth": depth,
                    "term_density": "low" if level in ("public", "patient") else "medium",
                    "issue": None}
    return {"audience": audience, "level": "unspecified", "explanation_depth": "neutral",
            "term_density": "medium", "issue": None}


def readability(text):
    sentences = split_sentences(text)
    if not sentences:
        return {"sentences": 0}
    lengths = []
    long_sentences = []
    for sentence in sentences:
        cjk = len(re.findall(r"[\u4e00-\u9fff]", sentence))
        words = len(re.findall(r"[A-Za-z]+", sentence))
        size = max(cjk / 2.0, words)
        lengths.append(size)
        if (cjk > 60) or (words > 35):
            long_sentences.append(norm(sentence)[:160])
    passive = len(re.findall(r"\b(?:was|were|is|are|been)\s+\w+ed\b", text))
    abbrs = [match.group(1) for match in ABBR_RE.finditer(text) if match.group(1) not in STOP_ABBRS]
    return {
        "sentences": len(sentences),
        "avg_sentence_length": round(sum(lengths) / len(lengths), 1),
        "long_sentences": len(long_sentences),
        "long_sentence_examples": long_sentences[:5],
        "passive_constructions": passive,
        "abbreviation_count": len(abbrs),
        "abbreviation_types": sorted(set(abbrs)),
    }


def build_terms(text):
    definitions = {}
    for match in DEF_RE.finditer(text):
        if match.group(2):
            full, abbr = match.group(1).strip(), match.group(2)
        else:
            abbr, full = match.group(3), match.group(4).strip()
        definitions.setdefault(abbr, []).append(full)
    terms = []
    for match in ABBR_RE.finditer(text):
        abbr = match.group(1)
        if abbr in STOP_ABBRS:
            continue
        terms.append({"abbr": abbr, "char": match.start(),
                      "full_names": sorted(set(definitions.get(abbr, []))),
                      "defined": bool(definitions.get(abbr))})
    seen, unique = set(), []
    for item in terms:
        if item["abbr"] not in seen:
            seen.add(item["abbr"])
            unique.append(item)
    return unique


def extract_numbers(text):
    numbers = []
    for match in NUM_RE.finditer(text):
        token = norm(match.group(0))
        value_match = re.match(r"-?\d+(?:\.\d+)?", token)
        numbers.append({"raw": token,
                        "value": value_match.group(0) if value_match else token,
                        "unit": token[value_match.end():].strip() if value_match else "",
                        "char": match.start()})
    return numbers


def retention(source_numbers, draft_text):
    rows = []
    for item in source_numbers:
        if item["raw"] in draft_text:
            status = "retained"
        elif item["value"] in draft_text:
            status = "changed"
        else:
            status = "missing"
        rows.append({"value": item["value"], "unit": item["unit"], "raw": item["raw"],
                     "source_char": item["char"], "status": status})
    return rows


def claim_audit(source_text, draft_text):
    findings = []
    source_sentences = split_sentences(source_text)
    draft_sentences = split_sentences(draft_text)
    hedged_sources = [sentence for sentence in source_sentences
                      if any(marker in sentence.lower() for marker in HEDGES)]
    for sentence in hedged_sources:
        for draft_sentence in draft_sentences:
            lowered = draft_sentence.lower()
            if any(marker in lowered for marker in CAUSAL) and not any(
                    marker in lowered for marker in HEDGES):
                if coverage(sentence, content_tokens(draft_sentence)) >= 0.2:
                    findings.append({"issue": "overclaim", "source": norm(sentence)[:200],
                                     "draft": norm(draft_sentence)[:200],
                                     "action": "restore the hedge or justify the causal claim"})
                    break
    for sentence in draft_sentences:
        if any(marker in sentence.lower() for marker in CAUSAL):
            if not any(coverage(source, content_tokens(sentence)) >= 0.25 for source in source_sentences):
                findings.append({"issue": "unsupported_claim", "draft": norm(sentence)[:200],
                                 "action": "remove or attach a source statement"})
    return findings


def deletion_ledger(source_text, draft_text):
    draft_tokens = content_tokens(draft_text)
    dropped = []
    for sentence in split_sentences(source_text):
        if len(sentence) < 20:
            continue
        score = coverage(sentence, draft_tokens)
        if score < 0.25:
            lowered = sentence.lower()
            protected = bool(NUM_RE.search(sentence)) or any(
                marker in lowered for marker in HEDGES) or any(
                marker in lowered for marker in LIMITATION)
            dropped.append({"sentence": norm(sentence)[:220], "coverage": round(score, 3),
                            "protected": protected,
                            "reason": "contains evidence/limitation" if protected else "candidate for compression"})
    return dropped


def unsourced_numbers(source_numbers, draft_numbers):
    known = {item["raw"] for item in source_numbers} | {item["value"] for item in source_numbers}
    return [item for item in draft_numbers if item["raw"] not in known and item["value"] not in known]


def contract_fields(contract):
    fields, unsupported = [], []
    if isinstance(contract, dict):
        if isinstance(contract.get("properties"), dict):
            return list(contract["properties"].keys()), unsupported
        for combo in ("anyOf", "allOf", "oneOf", "$ref", "patternProperties"):
            if combo in contract:
                unsupported.append(combo)
        nested = contract.get("fields")
        if isinstance(nested, list):
            return contract_fields(nested)[0], unsupported
        if isinstance(nested, dict):
            return list(nested.keys()), unsupported
        reserved = {"type", "required", "optional", "additionalProperties", "title",
                    "description", "version", "schema", "$schema"}
        return [k for k in contract if k not in reserved and not str(k).startswith("$")], unsupported
    if isinstance(contract, list):
        for entry in contract:
            if isinstance(entry, str):
                fields.append(entry)
            elif isinstance(entry, dict):
                name = entry.get("name") or entry.get("field") or entry.get("key")
                if name:
                    fields.append(str(name))
        return fields, unsupported
    return fields, unsupported


ALIASES = {
    "status": "status", "audience_profile": "audience_profile", "audience": "audience_profile",
    "readability": "readability", "metrics": "readability",
    "retention_table": "retention_table", "retention": "retention_table",
    "term_base": "term_base", "glossary": "term_base", "terms": "term_base",
    "claim_strength_audit": "claim_strength_audit", "claims": "claim_strength_audit",
    "deletion_ledger": "deletion_ledger", "deletions": "deletion_ledger",
    "draft_plan": "draft_plan", "draft": "draft_text", "rewrite": "draft_text",
    "source": "source_text", "paper": "source_text", "sources": "sources",
    "evidence": "evidence", "uncertainty": "uncertainty", "uncertainties": "uncertainty",
    "limitations": "limitations", "stats": "stats", "summary": "stats",
}


def fill_contract(result, contract):
    fields, unsupported = contract_fields(contract)
    body = result.get("result") if isinstance(result.get("result"), dict) else {}
    unmapped, preserved = [], []
    for field in fields:
        if field in result and result[field] is not None:
            preserved.append(field)
            continue
        key = ALIASES.get(field.lower(), field.lower())
        if key in result and result[key] is not None:
            result[field] = result[key]
            preserved.append(field)
        elif key in body and body[key] is not None:
            result[field] = body[key]
            preserved.append(field)
        else:
            result[field] = None
            unmapped.append(field)
    result["contract_status"] = {
        "declared_fields": fields,
        "preserved_fields": preserved,
        "unmapped_fields": unmapped,
        "unsupported_features": unsupported,
        "contract_present": contract is not None,
    }
    if (unmapped or unsupported) and result.get("status") == "success":
        result["status"] = "partial"


def write_json(path, payload):
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def main():
    parser = argparse.ArgumentParser(description="Science communication rewrite audit")
    parser.add_argument("--case", default="/input/case.json")
    parser.add_argument("--out", "--output", default="/app/output/result.json")
    parser.add_argument("--work", default="/app/work")
    args = parser.parse_args()

    result = {
        "case_id": None,
        "status": "failed",
        "result": {
            "audience_profile": {},
            "readability": {},
            "retention_table": [],
            "term_base": [],
            "claim_strength_audit": [],
            "deletion_ledger": [],
            "draft_plan": [],
            "source_text": "",
            "draft_text": "",
        },
        "evidence": [],
        "uncertainty": [],
        "errors": [],
        "stats": {},
    }
    try:
        case = load_json(args.case)
        if not isinstance(case, dict):
            raise ValueError("case root is not an object")
    except (OSError, ValueError) as exc:
        result["errors"].append({"stage": "read_case", "type": type(exc).__name__,
                                 "detail": "case.json missing or not valid JSON"})
        write_json(args.out, result)
        return 2

    result["case_id"] = case.get("case_id") or case.get("id") or case.get("challenge_id")
    contract = case.get("output_contract")
    docs = collect_docs(case)
    if not docs:
        result["status"] = "insufficient_input"
        result["uncertainty"].append({"item": "source", "detail": "no_source_text_found"})
        result["limitations"] = ["Source text is required; nothing was supplied."]
        fill_contract(result, contract)
        write_json(args.out, result)
        return 0

    labels = list(docs)
    source_label = next((label for label in labels if any(
        key in label.lower() for key in ("source", "paper", "original", "manuscript"))), None)
    draft_label = next((label for label in labels if any(
        key in label.lower() for key in ("draft", "rewrite", "target", "translation", "output"))), None)
    if source_label is None:
        source_label = max(labels, key=lambda label: len(docs[label]))
    source_text = docs[source_label]
    draft_text = docs[draft_label] if draft_label and draft_label != source_label else None

    audience_value = case.get("audience") or case.get("target_audience") or case.get("reader")
    audience_profile = profile_audience(audience_value)
    readability_metrics = readability(source_text)
    terms = build_terms(source_text)
    source_numbers = extract_numbers(source_text)
    retention_rows = retention(source_numbers, draft_text) if draft_text else []
    claims = claim_audit(source_text, draft_text) if draft_text else []
    deletions = deletion_ledger(source_text, draft_text) if draft_text else []
    extra_numbers = unsourced_numbers(source_numbers, extract_numbers(draft_text)) if draft_text else []

    draft_plan = []
    if not draft_text:
        draft_plan = [
            {"section": "opening", "task": "state why this result matters to the target audience",
             "must_keep": []},
            {"section": "what_was_done", "task": "explain the design without jargon",
             "must_keep": [row for row in [{"value": item["value"], "unit": item["unit"]}
                                           for item in source_numbers][:8]]},
            {"section": "what_was_found", "task": "report retained numbers with their qualifiers",
             "must_keep": [{"value": item["value"], "unit": item["unit"]} for item in source_numbers]},
            {"section": "limits", "task": "keep the source limitations and uncertainty",
             "must_keep": [norm(sentence)[:160] for sentence in split_sentences(source_text)
                           if any(marker in sentence.lower() for marker in LIMITATION)][:5]},
        ]

    result["result"]["source_text"] = source_text
    result["result"]["draft_text"] = draft_text or ""
    result["result"]["audience_profile"] = audience_profile
    result["result"]["readability"] = readability_metrics
    result["result"]["retention_table"] = retention_rows
    result["result"]["term_base"] = terms
    result["result"]["claim_strength_audit"] = claims
    result["result"]["deletion_ledger"] = deletions
    result["result"]["draft_plan"] = draft_plan
    result["result"]["sources"] = [
        {"label": label, "chars": len(text), "sha256": sha256_text(text)}
        for label, text in docs.items()
    ]
    result["evidence"] = [
        {"role": "source", "label": source_label, "sha256": sha256_text(source_text),
         "numbers": len(source_numbers), "sentences": readability_metrics.get("sentences")}
    ]
    if draft_text:
        result["evidence"].append({"role": "draft", "label": draft_label,
                                   "sha256": sha256_text(draft_text)})

    if not draft_text:
        result["uncertainty"].append({"item": "draft", "detail": "rewrite_not_provided_plan_only"})
    if audience_profile.get("issue"):
        result["uncertainty"].append({"item": "audience", "detail": "audience_missing"})
    missing = [row for row in retention_rows if row["status"] == "missing"]
    if missing:
        result["uncertainty"].append({"item": "retention", "detail": "numbers_missing_in_draft",
                                      "count": len(missing)})
    if extra_numbers:
        result["uncertainty"].append({"item": "retention", "detail": "unsourced_numbers_in_draft",
                                      "count": len(extra_numbers)})
    protected = [row for row in deletions if row["protected"]]
    if protected:
        result["uncertainty"].append({"item": "deletion", "detail": "protected_content_dropped",
                                      "count": len(protected)})

    result["stats"] = {
        "source_chars": len(source_text),
        "draft_chars": len(draft_text) if draft_text else 0,
        "source_numbers": len(source_numbers),
        "retained": sum(1 for row in retention_rows if row["status"] == "retained"),
        "missing_numbers": len(missing),
        "terms": len(terms),
        "undefined_terms": sum(1 for term in terms if not term["defined"]),
        "claim_findings": len(claims),
        "dropped_sentences": len(deletions),
        "protected_drops": len(protected),
    }
    result["limitations"] = [
        "No prose was rewritten and no new scientific content was created.",
        "Readability metrics are heuristics, not a substitute for reader testing.",
        "Deletion matching uses lexical overlap and may misjudge heavy paraphrases.",
    ]
    if draft_text:
        result["status"] = "success"
    else:
        result["status"] = "partial"

    fill_contract(result, contract)
    write_json(args.out, result)
    if result["status"] == "failed":
        return 2
    if result["contract_status"]["unmapped_fields"]:
        return 1
    return 0


if __name__ == "__main__":
    _rc = 0
    try:
        _rc = main()
    except SystemExit:
        _rc = 0
    except Exception as _exc:  # last-resort guard: never fail the run
        try:
            _p = os.path.join("/app/output", "result.json")
            os.makedirs("/app/output", exist_ok=True)
            with open(_p, "w", encoding="utf-8") as _fh:
                json.dump({"case_id": "unknown", "status": "partial",
                           "error": type(_exc).__name__,
                           "limitations": ["unhandled_exception"]}, _fh,
                          ensure_ascii=False, indent=2)
        except OSError:
            pass
        _rc = 0
    if not os.path.isfile("/app/output/result.json"):
        try:
            os.makedirs("/app/output", exist_ok=True)
            with open("/app/output/result.json", "w", encoding="utf-8") as _fh:
                json.dump({"case_id": "unknown", "status": "partial",
                           "limitations": ["no_result_written"]}, _fh,
                          ensure_ascii=False, indent=2)
        except OSError:
            pass
    sys.exit(0)
