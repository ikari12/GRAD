
import pandas as pd
import numpy as np

# データの読み込み
df = pd.read_csv("data/meixner_4d_indices.csv")
print(f"Total rows in meixner_4d_indices.csv: N = {len(df)}, K = {df['userId'].nunique()}")

# 1. 有効な DI を持つワークアウト (N)
df_di = df[df['DI'].notna()]
print(f"Workouts with valid DI: N = {len(df_di)}, K = {df_di['userId'].nunique()}")

# 2. 有効な FI を持つワークアウト (N)
df_fi = df[df['FI'].notna()]
print(f"Workouts with valid FI: N = {len(df_fi)}, K = {df_fi['userId'].nunique()}")

# 3. 有効な RI を持つワークアウト (N)
df_ri = df[df['RI'].notna()]
print(f"Workouts with valid RI: N = {len(df_ri)}, K = {df_ri['userId'].nunique()}")

# Study 1 (Construct Validity) の基準: 5ワークアウト以上のユーザ
user_counts = df['userId'].value_counts()
users_ge5 = user_counts[user_counts >= 5].index
df_ge5 = df[df['userId'].isin(users_ge5)]
print(f"Users with >= 5 workouts: N = {len(df_ge5)}, K = {len(users_ge5)}")

# abc_metrics.csv の確認 (Study 2, 3 のベース)
try:
    df_abc = pd.read_csv("data/abc_metrics.csv")
    print(f"Total rows in abc_metrics.csv: N = {len(df_abc)}, K = {df_abc['userId'].nunique()}")
except:
    print("abc_metrics.csv not found")

# ReI (Recovery Index) の存在確認
if 'ReI' in df.columns:
    df_rei = df[df['ReI'].notna()]
    print(f"Workouts with valid ReI: N = {len(df_rei)}, K = {df_rei['userId'].nunique()}")
else:
    print("ReI column not found in meixner_4d_indices.csv")
