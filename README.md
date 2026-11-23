# Runtime contract

Bohrium Playground Period 4 submission — challenge `challenge-a7eb6816` (track: `academic-writing`).

This repository holds the complete skill package for the challenge: the skill
definition, its executable entry point and all supporting scripts. No precomputed
answers, private data or credentials are included.

## Skill

- Name: `science-to-public-rewriter`
- Summary: Use when a case supplies a technical source (paper abstract, report, or paper section) plus a target audience and asks for science-communication rewriting or genre conversion; profiles the audience, keeps a number-and-hedge retention table, audits claim strength against the source, locks a term base, records deletions, and writes /app/output/result.json preserving case_id and every output_contract field. Deterministic standard library only; no network.

## Contents

| File |
|------|
| `SKILL.md` |
| `scripts/run_skill.py` |
| `README.md` |

## How to run

```bash
python scripts/run_skill.py --case /input/case.json --output /app/output/result.json
```

The entry point is `SKILL.md`; input/output contracts, error handling and a minimal
usage example are documented there.

## Notes

- Pure Python standard library; no network access required.
- The result JSON keeps the input case id, the main results, per-item evidence,
  a run status and an uncertainty section.
