import argparse
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
from tqdm import tqdm

from utils import load_data

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


_thread_local = threading.local()


def _read_deepseek_config(config_path):
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw = f.read()
    except Exception:
        return None

    lines = [line.strip() for line in raw.splitlines()]
    start_idx = None
    for idx, line in enumerate(lines):
        if line.lower().startswith("model_one") and "deepseek" in line.lower():
            start_idx = idx + 1
            break
    if start_idx is None:
        return None

    end_idx = len(lines)
    for idx in range(start_idx, len(lines)):
        if lines[idx].lower().startswith("model_") and idx != start_idx:
            end_idx = idx
            break

    section = "\n".join(lines[start_idx:end_idx])
    key_match = re.search(r'api_key\s*=\s*["“](.+?)["”]', section)
    url_match = re.search(r'base_url\s*=\s*["“](.+?)["”]', section)

    api_key = key_match.group(1).strip() if key_match else None
    base_url = url_match.group(1).strip() if url_match else None
    if not api_key and not base_url:
        return None
    return {"api_key": api_key, "base_url": base_url}


def _get_client(api_key, base_url):
    client = getattr(_thread_local, "client", None)
    if client is None:
        _thread_local.client = OpenAI(api_key=api_key, base_url=base_url, timeout=60.0, max_retries=2)
        client = _thread_local.client
    return client


def _extract_json(text):
    if not text:
        return None
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    blob = m.group(0)
    try:
        return json.loads(blob)
    except Exception:
        return None


def _ask_once(api_key, base_url, model, skill_a_name, skill_b_name):
    client = _get_client(api_key, base_url)
    prompt = f"""
You are an expert curriculum designer.

Question: Is concept A a necessary prerequisite for mastering concept B?
A: {skill_a_name}
B: {skill_b_name}

Answer ONLY this JSON:
{{"is_prerequisite": "Yes" or "No"}}
"""
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a domain expert in education and curriculum design."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
        )
        msg = resp.choices[0].message
        content = (msg.content or "").strip()
    except Exception as e:
        return False, f"error: {e}"
    data = _extract_json(content)
    if data and isinstance(data, dict) and "is_prerequisite" in data:
        val = str(data["is_prerequisite"]).strip().lower()
        if val.startswith("y"):
            return True, content
        if val.startswith("n"):
            return False, content
    lower = content.lower()
    if "yes" in lower and "no" not in lower:
        return True, content
    if "no" in lower and "yes" not in lower:
        return False, content
    return False, content


def _vote_edge(api_key, base_url, model, skill_a_name, skill_b_name, n_votes):
    yes = 0
    notes = []
    for _ in range(n_votes):
        ok, content = _ask_once(api_key, base_url, model, skill_a_name, skill_b_name)
        notes.append(content)
        yes += 1 if ok else 0
    return yes, notes


def build_matrix_from_candidates(
    csv_path,
    candidates_csv,
    output_path,
    accepted_edges_path=None,
    api_key=None,
    base_url=None,
    model=None,
    max_workers=10,
    n_votes=3,
    mock=False,
    mock_yes_prob=0.2,
):
    _, num_skills, skill_id_map, skill_name_map = load_data(csv_path)
    id_to_name = {}
    for original_id, internal_id in skill_id_map.items():
        id_to_name[internal_id] = skill_name_map.get(original_id, f"Skill_{original_id}")

    matrix = np.zeros((num_skills, num_skills), dtype=int)
    np.fill_diagonal(matrix, 0)

    cand = pd.read_csv(candidates_csv, encoding="utf-8")
    if "skill_A_idx" in cand.columns and "skill_B_idx" in cand.columns:
        a_idx = cand["skill_A_idx"].astype(int).tolist()
        b_idx = cand["skill_B_idx"].astype(int).tolist()
    else:
        a_idx = [skill_id_map.get(x, None) for x in cand["skill_A"].tolist()]
        b_idx = [skill_id_map.get(x, None) for x in cand["skill_B"].tolist()]

    edges = []
    for row_idx in range(len(cand)):
        a = a_idx[row_idx]
        b = b_idx[row_idx]
        if a is None or b is None:
            continue
        if a == b:
            continue
        if a < 0 or b < 0 or a >= num_skills or b >= num_skills:
            continue
        edges.append((row_idx, a, b))

    if not mock and OpenAI is None:
        raise ImportError("Please install openai package: pip install openai")

    if not model:
        model = "deepseek-reasoner"
    if not base_url:
        base_url = os.environ.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"
    if not api_key:
        api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        config_path = os.path.join(os.path.dirname(__file__), "apikey.txt")
        config = _read_deepseek_config(config_path)
        if config and config.get("api_key"):
            api_key = config["api_key"]
        if config and config.get("base_url") and not os.environ.get("DEEPSEEK_BASE_URL"):
            base_url = config["base_url"]
    if not api_key and not mock:
        raise ValueError("Missing API key. Set DEEPSEEK_API_KEY/OPENAI_API_KEY or put it in apikey.txt (model_one: deepseek).")

    accepted = []

    def worker(row_idx, a, b):
        a_name = id_to_name[a]
        b_name = id_to_name[b]
        if mock:
            h = hash((a, b, row_idx)) % 100000
            ok = (h / 100000.0) < mock_yes_prob
            return row_idx, a, b, ok, 0, []
        yes, notes = _vote_edge(api_key, base_url, model, a_name, b_name, n_votes)
        ok = yes >= (n_votes // 2 + 1)
        return row_idx, a, b, ok, yes, notes

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(worker, row_idx, a, b) for (row_idx, a, b) in edges]
        for fut in tqdm(as_completed(futures), total=len(futures), desc="Verifying Candidates"):
            row_idx, a, b, ok, yes, notes = fut.result()
            if ok:
                matrix[a, b] = 1
            accepted.append(
                {
                    "row_idx": row_idx,
                    "skill_A_idx": a,
                    "skill_B_idx": b,
                    "skill_A_name": id_to_name[a],
                    "skill_B_name": id_to_name[b],
                    "accepted": bool(ok),
                    "yes_votes": int(yes),
                }
            )

    np.save(output_path, matrix)
    print(f"Matrix saved: {output_path}")
    print(f"Shape: {matrix.shape}, Edges: {int(matrix.sum())}")

    if accepted_edges_path:
        pd.DataFrame(accepted).to_csv(accepted_edges_path, index=False, encoding="utf-8")
        print(f"Accepted edges saved: {accepted_edges_path}")

    return matrix


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data_path",
        type=str,
        default=r"c:\Users\liuxb\Desktop\刘祥\experiments\skill_builder_data.csv",
    )
    parser.add_argument("--candidates", type=str, default="candidates.csv")
    parser.add_argument("--output", type=str, default="prerequisite_matrix_full.npy")
    parser.add_argument("--accepted_edges", type=str, default="accepted_edges.csv")
    parser.add_argument("--api_key", type=str, default=None)
    parser.add_argument("--base_url", type=str, default=None)
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--max_workers", type=int, default=10)
    parser.add_argument("--n_votes", type=int, default=3)
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--mock_yes_prob", type=float, default=0.2)
    args = parser.parse_args()

    build_matrix_from_candidates(
        args.data_path,
        args.candidates,
        args.output,
        accepted_edges_path=args.accepted_edges,
        api_key=args.api_key,
        base_url=args.base_url,
        model=args.model,
        max_workers=args.max_workers,
        n_votes=args.n_votes,
        mock=args.mock,
        mock_yes_prob=args.mock_yes_prob,
    )


if __name__ == "__main__":
    main()
