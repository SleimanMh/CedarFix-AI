# data — Canonical data & eval fixtures

Directory structure
- `knowledge_base/` — runtime KB (municipality registries, aliases, workflows)
- `complaint_intelligence/` — research artifacts, discovered leads
- `review_queue/` — human review queues and legacy corpus slices
- `training/` — JSONL training/validation/test files
- `eval/` — evaluation JSONL fixtures (routing, grounding, image fusion)

Common eval fixtures
- `data/eval/arabic_multilingual_routing_eval_v1.jsonl` — IEP-1 multilingual tests
- `data/eval/flooding_routing_eval_v1.jsonl` — flooding safety routing cases
- `data/eval/image_hazard_fusion_eval_v1.jsonl` — IEP-6 image fusion cases
- `data/eval/resolution_grounding_eval_v1.jsonl` — IEP-8 grounding benchmark

Notes
- Keep `knowledge_base/` CSVs clean and versioned; missing registry IDs and small
  gaps can cause routing failures in production.
