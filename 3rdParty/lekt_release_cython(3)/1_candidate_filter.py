import argparse
import math
import os

import numpy as np
import pandas as pd
from tqdm import tqdm


def _load_interactions(csv_path, min_seq_len=3):
    df = pd.read_csv(csv_path, encoding="latin-1")
    df = df[["user_id", "skill_id", "skill_name", "correct", "order_id"]].dropna()
    df["correct"] = df["correct"].astype(int)
    df = df.sort_values("order_id")
    grouped = df.groupby("user_id", sort=False)
    sequences = []
    for _, group in grouped:
        if len(group) < min_seq_len:
            continue
        skills = group["skill_id"].tolist()
        correct = group["correct"].tolist()
        sequences.append((skills, correct))
    unique_skills = df["skill_id"].unique().tolist()
    skill_to_idx = {sid: i for i, sid in enumerate(unique_skills)}
    names = (
        df[["skill_id", "skill_name"]]
        .drop_duplicates("skill_id")
        .set_index("skill_id")["skill_name"]
        .to_dict()
    )
    return sequences, unique_skills, skill_to_idx, names


def build_candidates(
    csv_path,
    output_path,
    top_k=5,
    window_k=10,
    w1=0.6,
    w2=0.3,
    w3=0.1,
    min_pair_count=50,
    min_order_ratio=0.6,
    min_cond_count=20,
    min_score=0.0,
    min_seq_len=3,
):
    sequences, unique_skills, skill_to_idx, names = _load_interactions(
        csv_path, min_seq_len=min_seq_len
    )
    n = len(unique_skills)

    ordered = np.zeros((n, n), dtype=np.int64)
    trans = np.zeros((n, n), dtype=np.int64)
    cond_total = np.zeros((n, n), dtype=np.int64)
    cond_wrong = np.zeros((n, n), dtype=np.int64)

    for skills, correct in tqdm(sequences, desc="Scanning Users"):
        idx_seq = [skill_to_idx[s] for s in skills]
        seen = {}
        for b in idx_seq:
            for a, c in seen.items():
                ordered[a, b] += c
            seen[b] = seen.get(b, 0) + 1

        for t in range(1, len(idx_seq)):
            trans[idx_seq[t - 1], idx_seq[t]] += 1

        for t, a in enumerate(idx_seq):
            if correct[t] != 0:
                continue
            end = min(len(idx_seq), t + 1 + window_k)
            for u in range(t + 1, end):
                b = idx_seq[u]
                cond_total[a, b] += 1
                if correct[u] == 0:
                    cond_wrong[a, b] += 1

    total_pairs = ordered + ordered.T
    order_ratio = ordered / (total_pairs + 1e-9)
    out_counts = trans.sum(axis=1, keepdims=True)
    trans_prob = trans / (out_counts + 1e-9)
    cond_prob = cond_wrong / (cond_total + 1e-9)

    score = w1 * order_ratio + w2 * cond_prob + w3 * trans_prob

    rows = []
    for b in range(n):
        cand = []
        for a in range(n):
            if a == b:
                continue
            if total_pairs[a, b] < min_pair_count:
                continue
            if order_ratio[a, b] < min_order_ratio:
                continue
            if cond_total[a, b] < min_cond_count:
                continue
            s = float(score[a, b])
            if s < min_score:
                continue
            cand.append((s, a))
        cand.sort(reverse=True, key=lambda x: x[0])
        for s, a in cand[:top_k]:
            skill_a_id = unique_skills[a]
            skill_b_id = unique_skills[b]
            rows.append(
                {
                    "skill_A": skill_a_id,
                    "skill_B": skill_b_id,
                    "skill_A_idx": a,
                    "skill_B_idx": b,
                    "skill_A_name": names.get(skill_a_id, ""),
                    "skill_B_name": names.get(skill_b_id, ""),
                    "score": s,
                    "order_ratio": float(order_ratio[a, b]),
                    "cond_wrong": float(cond_prob[a, b]),
                    "transition_prob": float(trans_prob[a, b]),
                    "count_ab": int(total_pairs[a, b]),
                    "count_a_pre_b": int(ordered[a, b]),
                    "count_b_pre_a": int(ordered[b, a]),
                    "cond_total": int(cond_total[a, b]),
                }
            )

    out_df = pd.DataFrame(rows)
    out_df.to_csv(output_path, index=False, encoding="utf-8")
    return out_df, n, len(sequences)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data_path",
        type=str,
        default=r"c:\Users\liuxb\Desktop\刘祥\experiments\skill_builder_data.csv",
    )
    parser.add_argument("--output", type=str, default="candidates.csv")
    parser.add_argument("--top_k", type=int, default=5)
    parser.add_argument("--window_k", type=int, default=10)
    parser.add_argument("--w1", type=float, default=0.6)
    parser.add_argument("--w2", type=float, default=0.3)
    parser.add_argument("--w3", type=float, default=0.1)
    parser.add_argument("--min_pair_count", type=int, default=50)
    parser.add_argument("--min_order_ratio", type=float, default=0.6)
    parser.add_argument("--min_cond_count", type=int, default=20)
    parser.add_argument("--min_score", type=float, default=0.0)
    parser.add_argument("--min_seq_len", type=int, default=3)
    args = parser.parse_args()

    out_df, n, users = build_candidates(
        args.data_path,
        args.output,
        top_k=args.top_k,
        window_k=args.window_k,
        w1=args.w1,
        w2=args.w2,
        w3=args.w3,
        min_pair_count=args.min_pair_count,
        min_order_ratio=args.min_order_ratio,
        min_cond_count=args.min_cond_count,
        min_score=args.min_score,
        min_seq_len=args.min_seq_len,
    )
    print(f"Users used: {users}")
    print(f"Skills: {n}")
    print(f"Candidates saved: {len(out_df)} -> {args.output}")


if __name__ == "__main__":
    main()

