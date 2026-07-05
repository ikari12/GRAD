
import pandas as pd
import numpy as np
from scipy import stats

def calculate_icc(df, metric):
    # Simplified ICC(1,1) calculation for stratification
    df_valid = df[df[metric].notna()]
    user_counts = df_valid['userId'].value_counts()
    users_ge5 = user_counts[user_counts >= 5].index
    df_sub = df_valid[df_valid['userId'].isin(users_ge5)]
    
    if len(df_sub) == 0: return np.nan
    
    k = df_sub['userId'].nunique()
    n = len(df_sub)
    n0 = (n - (df_sub['userId'].value_counts()**2).sum() / n) / (k - 1)
    
    grand_mean = df_sub[metric].mean()
    msb = (df_sub.groupby('userId')[metric].mean() - grand_mean).pow(2).mul(df_sub['userId'].value_counts()).sum() / (k - 1)
    msw = (df_sub[metric] - df_sub.groupby('userId')[metric].transform('mean')).pow(2).sum() / (n - k)
    
    icc = (msb - msw) / (msb + (n0 - 1) * msw)
    return max(0, icc)

# データの読み込み
df = pd.read_csv("data/meixner_4d_indices.csv")

# 種目の特定 (Endomondo sportId: 1=Cycling, 2=Running, 10=MTB)
# ※ データセットの特性上、比率から推定または userId ごとの主要種目で分類
# 今回は Study 1 の比率 (61.8%, 16.9%, 16.7%) に基づく分類をシミュレート
# 実際には 00a_compute_4d.py の出力に sport 列を追加するのが理想的だが
# 現状の meixner_4d_indices.csv に sport がない場合は、userId ごとの特性を抽出

print("Sport-Stratified Analysis Results:")
print("-" * 50)

# 仮に sport 列がない場合、上位の userId 群から種目を推論するロジックが必要だが
# 正確を期すため、元データ (abc_metrics.csv) と結合するか、
# 或者は全体の結果として報告する。


# abc_metrics.csv には sport 情報があるはずなので確認
try:
    df_abc = pd.read_csv("data/abc_metrics.csv")
    # userId ごとの最頻種目（主要種目）を特定
    user_sport = df_abc.groupby('userId')['sport'].agg(lambda x: x.mode()[0] if not x.empty else 'unknown').reset_index()
    
    # マージ前に確認
    # print(f"User sport columns: {user_sport.columns}")
    
    merged = pd.merge(df, user_sport, on='userId', how='left')
    # print(f"Merged columns: {merged.columns}")
    
    # 実際の種目名に合わせてループ
    sport_map = {
        'BIKE': 'bike',
        'RUN': 'run',
        'MOUNTAIN BIKE': 'mountain bike'
    }
    
    for label, sport_key in sport_map.items():
        sub = merged[merged['sport'] == sport_key]
        if sub.empty: continue
        
        # DI-FI Correlation
        df_corr = sub[['DI', 'FI']].dropna()
        if len(df_corr) > 10:
            corr = df_corr.corr().iloc[0, 1]
        else:
            corr = np.nan
            
        # ICC
        icc_di = calculate_icc(sub, 'DI')
        icc_fi = calculate_icc(sub, 'FI')
        
        print(f"Sport: {label}")
        print(f"  N(workouts) = {len(sub):>6,}, K(users) = {sub['userId'].nunique():>4,}")
        print(f"  DI-FI Correlation: r = {corr:.3f}")
        print(f"  ICC (DI): {icc_di:.3f}")
        print(f"  ICC (FI): {icc_fi:.3f}")
        print("-" * 30)
except Exception as e:
    import traceback
    print(f"Error: {e}")
    traceback.print_exc()

