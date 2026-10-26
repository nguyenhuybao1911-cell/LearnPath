import pandas as pd
import json

# Doc du lieu tuong tac da lam sach
df_interactions = pd.read_csv('data/backup/processed_previous_20261022/interactions_clean.csv')

# Chia du lieu theo thoi gian: Loc tap Train
train_df = df_interactions[df_interactions['dataset_split'] == 'train'].copy()
train_df['submitted_at'] = pd.to_datetime(train_df['submitted_at'])
train_df = train_df.sort_values('submitted_at')

# Tinh do kho cua tung bai tap tren tap Train
difficulty_df = train_df.groupby('problem_id').agg(
    total_attempts=('is_correct', 'count'),
    correct_attempts=('is_correct', lambda x: (x == True).sum())
).reset_index()

difficulty_df['difficulty'] = 1 - (difficulty_df['correct_attempts'] / difficulty_df['total_attempts'])
difficulty_df.to_csv('data/backup/processed_previous_20261022/concept_difficulty.csv', index=False)

# Trich xuat Trang thai nguoi hoc (Learner State)
learner_state = {}
for learner_id, group in train_df.groupby('learner_id'):
    mastered_concepts = group[group['is_correct'] == True]['problem_id'].unique().tolist()
    learner_state[learner_id] = {
        "mastered_concepts": mastered_concepts,
        "total_train_interactions": len(group)
    }

with open('data/backup/processed_previous_20261022/learner_state.json', 'w', encoding='utf-8') as f:
    json.dump(learner_state, f, ensure_ascii=False, indent=2)

print("Da hoan thanh tinh toan do kho va trich xuat learner_state cho Ngay 3!")
