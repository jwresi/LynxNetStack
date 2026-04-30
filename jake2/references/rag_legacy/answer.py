from query import search
import sys


def build_context(q):
    r = search(q)

    if not r:
        return "[NO CONTEXT FOUND]"

    blocks = []

    for item in r[:4]:
        _, doc, meta, _, _ = item
        blocks.append(f"[{meta.get('relative_path')}]\n{doc[:600]}")

    return "\n\n---\n\n".join(blocks)


def main():
    q = " ".join(sys.argv[1:])
    ctx = build_context(q)

    prompt = f"""
You are Jake, a senior network operations engineer.

IMPORTANT:
- Do NOT output any thinking, reasoning, or analysis.
- Do NOT output "Thinking..." or similar text.
- Start directly with "Interpretation:"
- End after "Sources:" and stop immediately.

FORMAT:

Interpretation:
What the docs say:
Likely fault domain:
Exact next commands:
Sources:

Context:
{ctx}

Question:
{q}
"""

    print(prompt)


if __name__ == "__main__":
    main()
