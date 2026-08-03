import os
import glob
import pandas as pd
import numpy as np
import torch
from torch.utils.data import Dataset, DataLoader

def load_data(csv_path, min_seq_len=3, max_skills=None):
    """
    Loads and preprocesses the skill builder data.
    Args:
        max_skills: If set, only keep the top N most frequent skills (or first N).
    Returns:
        train_data, test_data, num_skills, skill_id_map, skill_name_map
    """
    df = pd.read_csv(csv_path, encoding='latin-1') # Handle potential encoding issues
    
    # Filter necessary columns
    df = df[['user_id', 'skill_id', 'skill_name', 'correct', 'order_id']].dropna()
    df['correct'] = df['correct'].astype(int)
    
    # Sort by order_id to ensure temporal sequence
    df = df.sort_values('order_id')
    
    # Filter Skills if max_skills is set
    unique_skills = df['skill_id'].unique()
    
    if max_skills is not None and max_skills < len(unique_skills):
        # Let's take the most frequent skills to ensure we have data
        top_skills = df['skill_id'].value_counts().head(max_skills).index.tolist()
        df = df[df['skill_id'].isin(top_skills)]
        unique_skills = top_skills
        print(f"Filtered to top {max_skills} skills.")
    
    # Map skill_ids to continuous integers 0..N-1
    skill_id_map = {sid: i for i, sid in enumerate(unique_skills)}
    num_skills = len(unique_skills)
    
    # Create skill_name map for the LLM generator
    skill_name_map = {}
    # We iterate over the filtered df to get names
    temp_df = df[['skill_id', 'skill_name']].drop_duplicates('skill_id')
    for _, row in temp_df.iterrows():
        skill_name_map[row['skill_id']] = row['skill_name']
            
    # Group by user to create sequences
    sequences = []
    for user_id, group in df.groupby('user_id'):
        if len(group) < min_seq_len:
            continue
            
        # Get sequences
        skill_seq = [skill_id_map[sid] for sid in group['skill_id'].values]
        correct_seq = group['correct'].values.tolist()
        
        sequences.append((skill_seq, correct_seq))
        
    return sequences, num_skills, skill_id_map, skill_name_map

class KTDataset(Dataset):
    def __init__(self, sequences, max_len=100):
        self.sequences = sequences
        self.max_len = max_len
        
    def __len__(self):
        return len(self.sequences)
    
    def __getitem__(self, idx):
        skill_seq, correct_seq = self.sequences[idx]
        seq_len = len(skill_seq)
        
        # Truncate or pad
        if seq_len > self.max_len:
            skill_seq = skill_seq[-self.max_len:]
            correct_seq = correct_seq[-self.max_len:]
            seq_len = self.max_len
        
        # Create input/target tensors
        s_seq = np.zeros(self.max_len, dtype=int)
        c_seq = np.zeros(self.max_len, dtype=int)
        mask = np.zeros(self.max_len, dtype=int)
        
        s_seq[:seq_len] = skill_seq
        c_seq[:seq_len] = correct_seq
        mask[:seq_len] = 1
        
        return {
            'skill_seq': torch.tensor(s_seq, dtype=torch.long),
            'correct_seq': torch.tensor(c_seq, dtype=torch.float),
            'mask': torch.tensor(mask, dtype=torch.bool) # boolean mask
        }

def load_ednet_data(data_dir, questions_path=None, min_seq_len=3, max_skills=None):
    """
    Load EdNet-KT1 dataset.
    data_dir   : directory containing per-student CSV files (u{user_id}.csv or *.csv)
    questions_path : path to questions.csv that contains 'question_id' and 'correct_answer'.
                     If None, tries <data_dir>/../questions.csv automatically.
                     If still not found, assumes each student file has a 'correct' (0/1) column.
    Returns: sequences, num_skills, skill_id_map (question_id -> int), {}
    """
    # --- locate questions file ---
    if questions_path is None:
        candidate = os.path.join(data_dir, "..", "questions.csv")
        if os.path.exists(candidate):
            questions_path = os.path.normpath(candidate)

    correct_answer_map = {}  # question_id (str) -> correct_answer (str)
    if questions_path and os.path.exists(questions_path):
        q_df = pd.read_csv(questions_path, encoding="utf-8", dtype=str)
        q_df.columns = [c.strip() for c in q_df.columns]
        if "question_id" in q_df.columns and "correct_answer" in q_df.columns:
            for _, row in q_df.iterrows():
                correct_answer_map[str(row["question_id"]).strip()] = str(row["correct_answer"]).strip()

    # --- scan student files ---
    student_files = sorted(
        glob.glob(os.path.join(data_dir, "*.csv"))
    )
    if not student_files:
        raise FileNotFoundError(f"No CSV files found in {data_dir}")

    all_question_ids = []
    raw_sequences = []  # list of (user_id, [(qid, correct), ...])

    for fpath in student_files:
        try:
            df = pd.read_csv(fpath, encoding="utf-8", dtype=str)
        except Exception:
            continue
        df.columns = [c.strip() for c in df.columns]

        if "question_id" not in df.columns:
            continue

        df["question_id"] = df["question_id"].str.strip()

        # determine correctness
        if "correct" in df.columns:
            df["correct_int"] = pd.to_numeric(df["correct"], errors="coerce").fillna(0).astype(int)
        elif "user_answer" in df.columns and correct_answer_map:
            df["correct_int"] = (
                df["user_answer"].str.strip() == df["question_id"].map(correct_answer_map)
            ).astype(int)
        else:
            # cannot determine correctness — skip file
            continue

        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
            df = df.sort_values("timestamp")

        seq_qids = df["question_id"].tolist()
        seq_correct = df["correct_int"].tolist()

        if len(seq_qids) < min_seq_len:
            continue

        all_question_ids.extend(seq_qids)
        raw_sequences.append((seq_qids, seq_correct))

    if not raw_sequences:
        raise ValueError("No valid student sequences found in EdNet directory.")

    # --- build skill map ---
    unique_qids = list(dict.fromkeys(all_question_ids))  # preserve insertion order, deduplicate

    if max_skills is not None and max_skills < len(unique_qids):
        # keep top-N most frequent questions
        from collections import Counter
        counts = Counter(all_question_ids)
        unique_qids = [q for q, _ in counts.most_common(max_skills)]
        qid_set = set(unique_qids)
        # re-filter sequences
        filtered = []
        for qids, corrects in raw_sequences:
            fq = [q for q in qids if q in qid_set]
            fc = [c for q, c in zip(qids, corrects) if q in qid_set]
            if len(fq) >= min_seq_len:
                filtered.append((fq, fc))
        raw_sequences = filtered

    skill_id_map = {qid: i for i, qid in enumerate(unique_qids)}
    num_skills = len(unique_qids)

    sequences = []
    for qids, corrects in raw_sequences:
        skill_seq = [skill_id_map[q] for q in qids if q in skill_id_map]
        corr_seq = [c for q, c in zip(qids, corrects) if q in skill_id_map]
        if len(skill_seq) >= min_seq_len:
            sequences.append((skill_seq, corr_seq))

    return sequences, num_skills, skill_id_map, {}


def get_ednet_dataloaders(data_dir, questions_path=None, batch_size=32, max_len=200,
                          train_split=0.8, max_skills=None, seed=42):
    sequences, num_skills, skill_id_map, skill_name_map = load_ednet_data(
        data_dir, questions_path=questions_path, max_skills=max_skills
    )

    import random
    rng = random.Random(seed)
    rng.shuffle(sequences)
    split_idx = int(len(sequences) * train_split)
    train_seqs = sequences[:split_idx]
    test_seqs = sequences[split_idx:]

    train_dataset = KTDataset(train_seqs, max_len=max_len)
    test_dataset = KTDataset(test_seqs, max_len=max_len)

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False)

    return train_loader, test_loader, num_skills, skill_id_map, skill_name_map


def get_dataloaders(csv_path, batch_size=32, max_len=100, train_split=0.8, max_skills=None, seed=42):
    sequences, num_skills, skill_id_map, skill_name_map = load_data(csv_path, max_skills=max_skills)

    # Shuffle by student then split to avoid distribution shift
    import random
    rng = random.Random(seed)
    rng.shuffle(sequences)
    split_idx = int(len(sequences) * train_split)
    train_seqs = sequences[:split_idx]
    test_seqs = sequences[split_idx:]
    
    train_dataset = KTDataset(train_seqs, max_len=max_len)
    test_dataset = KTDataset(test_seqs, max_len=max_len)
    
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False)
    
    return train_loader, test_loader, num_skills, skill_id_map, skill_name_map
