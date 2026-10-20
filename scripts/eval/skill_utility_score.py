#!/usr/bin/env python3
# skill_utility_score.py: specificity x abstractness score to flag low-utility skills for review.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""
skill_utility_score.py -- port of the skill-utility score from arXiv 2608.20274 ("Break It Down, Pass It On").

Ranks skills/ by a utility score = specificity * abstractness (embedding-only, NO execution),
and flags the low-utility tail as PRUNE-CANDIDATE for /review. ADVISORY ONLY, never deletes.

Utility (Section 6.1 of the paper):
  specificity(s)  = percentile rank of the skill's best task-match inside the task-to-task
                    similarity distribution (near 1 = hugs at least one real task).
  abstractness(s) = perplexity(softmax(c/tau)) / N  (near 1 = relevant across many tasks).
  utility(s)      = specificity * abstractness  (both in [0,1]; only the PRODUCT predicts fit,
                    because a skill that maxes one factor gives up the other).

CAVEAT (honest): the score is only as good as the TASK CORPUS. A skill can
score low from COLD COVERAGE (no tasks like it yet), not from being bad. A brand-new skill and a
dead skill both look low against a stale corpus. So this is a FLAG into /review, never an
auto-deleter. Percentile bands, not an absolute cutoff (the paper publishes no absolute number).

Run (needs numpy + the embedding stack from requirements-memory.txt, i.e. the interpreter
that runs scripts/memory/vector_brain.py):
  $AGENT_VENV_PY scripts/eval/skill_utility_score.py
  ... --proxy   force skill-descriptions-as-corpus proxy (coverage-overlap, NOT task-fit)
  ... --json    machine-readable
The module imports with the stdlib only; numpy and the model load on first use.
"""
import sys, os, re, json, glob, argparse

REPO = os.environ.get("AGENT_ROOT") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # scripts/eval/x.py -> repo root
SKILL_GLOBS = [os.path.join(REPO, "skills", "*.md"), os.path.join(REPO, "skills", "*", "SKILL.md"),
               os.path.join(REPO, "skills-shared", "*.md"), os.path.join(REPO, "skills-shared", "*", "SKILL.md")]
SESSION_LOG = os.path.join(os.environ.get("AGENT_LOG_DIR") or os.path.join(REPO, "logs"), "session.jsonl")


def _frontmatter_fields(path):
    """Extract name/trigger/description from a skill file's frontmatter."""
    txt = open(path, encoding="utf-8", errors="replace").read()
    m = re.match(r"^---\n(.*?)\n---", txt, re.S)
    fm = m.group(1) if m else ""

    def field(k):
        mm = re.search(rf"^{k}:\s*(.+)$", fm, re.M)
        return mm.group(1).strip() if mm else ""
    stem = os.path.splitext(os.path.basename(path))[0]
    if stem == "SKILL":
        stem = os.path.basename(os.path.dirname(path))
    name = field("name") or stem
    return name, field("trigger"), field("description")


def load_skills():
    out = []
    for g in SKILL_GLOBS:
        for p in sorted(glob.glob(g)):
            name, trig, desc = _frontmatter_fields(p)
            # the retrievable string the router matches on = name + trigger + description
            text = " ".join(x for x in [name, trig, desc] if x)
            out.append((name, os.path.relpath(p, REPO), text))
    return out


def load_task_corpus(limit=800):
    """Real routed queries/tasks. Best source = session.jsonl summaries/intents.
       Returns (corpus_or_None, source_label)."""
    texts = []
    if os.path.exists(SESSION_LOG):
        for line in open(SESSION_LOG, encoding="utf-8", errors="replace"):
            try:
                e = json.loads(line)
            except Exception:
                continue
            for k in ("summary", "intent", "task", "prompt", "details"):
                v = e.get(k)
                if isinstance(v, str) and 8 <= len(v) <= 400:
                    texts.append(v)
    texts = list(dict.fromkeys(texts))[-limit:]  # dedup, keep recent
    if len(texts) >= 30:
        return texts, f"session.jsonl ({len(texts)} routed tasks)"
    return None, "insufficient real corpus (<30 task strings)"


def _embed(texts):
    import numpy as np
    sys.path.insert(0, os.path.join(REPO, "scripts", "memory"))
    from vector_brain import load_embedding_model
    model = load_embedding_model()
    return np.asarray(model.encode(texts, show_progress_bar=False, normalize_embeddings=True))


def utility_scores(skill_vecs, task_vecs, tau=0.1):
    """Pure math. skill_vecs (M,d) + task_vecs (N,d), L2-normalized. Returns list of dicts."""
    import numpy as np
    S, T = np.asarray(skill_vecs), np.asarray(task_vecs)
    C = S @ T.T                      # (M,N) skill-to-task cosine
    TT = T @ T.T                     # (N,N) task-to-task cosine
    iu = np.triu_indices(len(T), k=1)
    pair = np.sort(TT[iu])           # task-pair similarity distribution, ascending
    npair = max(len(pair), 1)
    rows = []
    for m in range(len(S)):
        c = C[m]
        spec = np.searchsorted(pair, c.max(), side="right") / npair
        z = c / tau
        z = z - z.max()              # stability
        p = np.exp(z)
        p = p / p.sum()
        H = -(p * np.log(p + 1e-12)).sum()
        abst = float(np.exp(H) / len(c))
        rows.append({"i": m, "spec": float(spec), "abst": abst, "util": float(spec) * abst})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--proxy", action="store_true",
                    help="force skill-descriptions-as-corpus proxy (coverage-overlap, NOT task-fit)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    import numpy as np
    skills = load_skills()
    descs = [s[2] for s in skills]
    corpus, label = load_task_corpus()
    if corpus is None or a.proxy:
        corpus = descs
        label = "PROXY: other skill descriptions (coverage-overlap, NOT task-fit; label it as such)"

    S = _embed(descs)
    T = _embed(corpus)
    rows = utility_scores(S, T)
    rows.sort(key=lambda r: r["util"])
    utils = np.array([r["util"] for r in rows])
    q25, q50 = float(np.percentile(utils, 25)), float(np.percentile(utils, 50))

    if a.json:
        print(json.dumps([{**r, "skill": skills[r["i"]][0], "path": skills[r["i"]][1]} for r in rows], indent=2))
        return

    print("# skill-utility (arXiv 2608.20274). ADVISORY ONLY, never auto-deletes.")
    print(f"# corpus: {label}")
    print(f"# {len(skills)} skills | q25={q25:.4f} | q50(median, the paper's cut)={q50:.4f}")
    print(f"#   {'skill':<36} {'util':>7} {'spec':>6} {'abst':>6}  band")
    for r in rows:
        band = "PRUNE-CANDIDATE" if r["util"] < q25 else ("WATCH" if r["util"] < q50 else "keep")
        print(f"    {skills[r['i']][0][:36]:<36} {r['util']:>7.4f} {r['spec']:>6.3f} {r['abst']:>6.3f}  {band}")
    print("\n# CAVEAT: low util can mean COLD COVERAGE (no tasks like it yet), not a bad skill.")
    print("# PRUNE-CANDIDATE = surface to /review, never auto-delete. New + dead skills both look low vs a stale corpus.")


if __name__ == "__main__":
    main()
