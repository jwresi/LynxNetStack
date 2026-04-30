# Jake Fine-Tuning Workspace

This directory is the staging area for taking Jake from:

- raw prompt logs
- corrected operator conversations
- regression prompts

to:

- curated SFT examples
- train/eval splits
- Unsloth-ready exports

## What belongs here

- `data/curated/jake_sft_curated.jsonl`
  - hand-reviewed training examples
  - each row is a single prompt/answer example with metadata
- `data/curated/*.jsonl`
  - you can split curated corpora into multiple files by domain, phrasing family, or source campaign
  - validation and train/eval splitting now load every curated JSONL in this directory
- `data/annotation_queue.jsonl`
  - auto-generated queue of prompts that still need curation
- `data/train.jsonl`
  - train split generated from curated examples
- `data/eval.jsonl`
  - eval split generated from curated examples
- `exports/unsloth_train_messages.jsonl`
  - Unsloth/HF-friendly export built from the curated train split
- `configs/unsloth_sft_config.example.yaml`
  - starter config for local LoRA/QLoRA work

## Recommended workflow

1. Build the raw annotation queue

```bash
python3 scripts/build_jake_training_corpus.py
```

2. Add or refine curated examples in:

- `training/data/curated/jake_sft_curated.jsonl`

3. Validate the curated dataset

```bash
python3 scripts/validate_jake_sft_dataset.py
```

4. Split train/eval

```bash
python3 scripts/split_jake_sft_dataset.py
```

5. Export an Unsloth-ready dataset

```bash
python3 scripts/export_jake_unsloth_dataset.py
```

6. Check the local Unsloth stack

```bash
python3 scripts/check_unsloth_stack.py
```

7. Dry-run the trainer

```bash
python3 scripts/train_jake_unsloth_sft.py --dry-run
```

8. Launch training

```bash
python3 scripts/train_jake_unsloth_sft.py
```

9. Compare a local MLX adapter against the base model

```bash
training/.venv312/bin/python scripts/compare_jake_mlx_adapter.py
```

10. Stage outside web/forum material into the right lane

```bash
python3 scripts/intake_jake_external_source.py \
  --title "Example source" \
  --url "https://example.com" \
  --source-kind official_doc \
  --content-file /path/to/source.txt
```

11. Audit staged outside material

```bash
python3 scripts/audit_jake_external_source_intake.py
```

## Training paths

- Local Apple Silicon path:
  - `docs/jake/JAKE_MLX_BOOTSTRAP_2026-04-10.md` in the old Jake repo
- Future Linux/NVIDIA Unsloth path:
  - `docs/jake/JAKE_UNSLOTH_BOOTSTRAP_2026-04-09.md` in the old Jake repo
- External source intake:
  - `training/source_intake/README.md` in the old Jake repo

6. Run the Jake regressions before and after any training run

- `python3 scripts/run_jake_conversational_ringer.py`
- `python3 scripts/run_jake_ops_ringer.py`
- `python3 scripts/run_jake_reasoning_ringer.py`

## Training guidance

Use fine-tuning for:

- Jake's tone and answer shape
- evidence ordering
- owner split language
- fault-domain reasoning order
- when to be decisive vs cautious

Do not rely on fine-tuning for:

- changing site facts
- live metrics
- current alert counts
- topology updates

That still belongs in RAG and deterministic/live tool paths.
