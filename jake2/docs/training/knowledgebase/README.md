# Jake Knowledgebase Staging

This directory defines the documents Jake should treat as:

- RAG knowledge
- training-only material
- eval-only material
- excluded noise

The goal is to keep Jake's future fine-tuning and RAG ingestion disciplined.

## Files

- `jake_kb_manifest.json`
  - generated machine-readable manifest of source files
  - each row classifies a file for RAG/training/eval use
- `jake_kb_audit.md`
  - generated human-readable audit summary

## Rules

- Site docs, runbooks, controller docs, reference corpora, and operator learned notes are usually RAG-eligible.
- Checklists, capability audits, and question-bank docs are usually eval/training material, not primary operator knowledge.
- Soak prompts are training/eval seeds, not canonical site facts.
- Live/generated outputs should not be treated as primary knowledge unless explicitly curated.
