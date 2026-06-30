# IMRAD Structure v3 — SportRxiv Submission Version

## Title
"Route Correction and Variance Decomposition for Aerobic Decoupling: A 253K-Workout Study of Durability Dimensionality"

---

## Introduction

### Framing
本研究はMeixner et al. (2025)の4Dフレームワークを**否定するものではなく**，スピードベースのDIで**operationalize**した場合に何が起こるかを検証し，フィールド展開に必要な定量的基盤を提供する．

### 先行研究

| テーマ | 先行研究 | Gap |
|---|---|---|
| Aerobic Decoupling の普及 | Coyle & González-Alonso (2001): cardiac drift の生理学．Friel (2009): Pa:HR の実務的基準（<5%）．TrainingPeaks, Strava 等で世界的に使用 | **起伏コースでの妥当性は未検証．Frielの閾値は査読論文で検証なし** |
| Meixner 4D Framework | Meixner et al. (2025): DI/FI/RI/ReI の 4 次元．8 本のレスポンス．Millet (2025): DI-FI 冗長性 | **全て理論的議論．大規模実証データゼロ．theoretical validity vs field-level deployment** |
| 分散構造 | Bourdon et al. (2017): IOC consensus（外的負荷 ≠ 内的応答）．Hopkins (2000): フィールド指標の信頼性．Halson (2014): 日内変動の影響 | **Person/Route/Occasion の定量化なし** |
| 偏心性筋収縮 | Peake et al. (2017): 微小筋損傷 → 炎症．Proske & Allen (2005): 下り走行の偏心性負荷 | **フィールドでの下り配置と心拍ドリフトの関係は未検証** |

### Research Questions

**CRQ1: スピードベースDIにおけるdurabilityフレームワークの実証的次元数は？**

**CRQ2: HR応答指標の分散はPerson/Route/Occasionにどう配分されるか？**

### 仮説

| 種別 | ID | 仮説 | 根拠 |
|---|---|---|---|
| Confirmatory | H1 | DI-FI は同一構成概念に縮約する | Millet (2025) |
| Confirmatory | H2 | 全次元の ICC < 0.50 | Hopkins (2000) |
| Confirmatory | H3 | DI のルート予測は勾配補正後に消滅する | DI 計算式の構造分析 |
| Confirmatory | H4 | Occasion が HR 応答分散の > 50% を占める | Bourdon et al. (2017) |
| Exploratory | E1 | 下りの位置が心拍ドリフト効果を持つ | Peake et al. (2017) |
| Exploratory | E2 | DI より安定した HR パラメータが存在する | — |
| Exploratory | E3 | ICC ≪ Split-half（順位安定性 > 絶対一致性） | Hopkins (2000) |

### 貢献

| # | 貢献 | 性質 |
|---|---|---|
| C1 | 2次元構造の実証＋ルートアーティファクトの定量化（R²=0.82; 7倍変動）＋Minetti推定パワーの過剰補正 | 方法論 |
| C2 | HR応答のPerson/Route/Occasion分散の初の大規模定量化: 27–53%のday-to-day変動 | 記述的 |
| C3 | 下りの時間的配置とcardiac driftの関係（between-person: β*=+0.29; within: modest） | 探索的 |
| C4 | 勾配感受性の収束分析: ≥6セッションでSB≥0.80 | プロトコル提案 |

---

## Methods

### Data
- FitRec: 253,020 workouts → Study 1: 13,750 (675 users) → Study 2–3: 2,343 (314 users)
- Inclusion: HR + altitude + speed arrays ≥30 finite points, duration >90 min, altitude range >200 m
- Demographics: cycling 61.8%, running 16.9%, MTB 16.7%, other 3.6%; 94% male

### 指標の操作化

| 指標 | 計算 |
|---|---|
| DI (naive) | (HR/Speed)\_H2 / (HR/Speed)\_H1 — 標準 aerobic decoupling |
| FI | 5勾配ビン内速度比の平均 (Speed\_H2 / Speed\_H1) |
| RI | 最終クライムvs最初クライムの平均速度比（累積獲得標高>50mのクライム） |
| GACD | HR ~ gradient + speed + time の OLS回帰 → β\_time（bpm/min） |
| 勾配感受性 | 同回帰 → β\_gradient（bpm/%） |
| 速度感受性 | 同回帰 → β\_speed（bpm/(m/s)） |

### VIF検証（多重共線性）
- median VIF: gradient=2.01, speed=2.09, time=1.07
- 100% of workouts < 10, 95.7% < 5
- → 回帰は安定

### Minetti推定パワー実験
- DI分母をspeedからestimated metabolic power（v × C\_r(g)）に置換
- C\_r(g): Minetti (2002) 23点テーブルから線形補間
- 結果: **逆方向に過剰補正**（r = −0.76 vs +0.48; CV R² = 0.57 vs 0.19）
- 原因: C\_r(-3%) ≈ 0.4 J/kg/m → 分母が極小化
- 追加問題: Minettiコスト関数はwalking/running由来 → cycling 61.8%のデータに生体力学的ミスマッチ

### 分析手法

| Study | 目的 | 手法 |
|---|---|---|
| 1 | 構成概念検証（CRQ1） | ICC, PCA (Parallel Analysis), Bootstrap相関 (B=2,000) |
| 2 | ルート補正検証（CRQ1） | Ridge/GBT予測, シミュレーション (N=5,000, drift=0), Minetti実験 |
| 2 | 下り位置効果（E1） | 偏相関, within-person, 層別分析, BH-FDR |
| 3 | 分散分解（CRQ2） | ICC + GroupKFold CV R² → %Person/%Route/%Occasion, Bootstrap CI (B=500) |
| 3 | 信頼性 | Split-half, Spearman-Brown, 収束分析 (k=2–10), ルートマッチICC |

> 全ての交差検証は GroupKFold(groups=userId) を使用．

---

## Results

### CRQ1: 2次元構造が支持される (H1, H2)

- DI–FI: r = −0.60 [−0.69, −0.49] → **同一構成概念** (H1 ✓)
- PCA: eigenvalue₁ = 1.66 (55.2%), eigenvalue₂ = 0.89 (parallel analysis閾値以下) → **1因子保持**
- RI は独立 (DI–RI: r = −0.19; FI–RI: r = +0.19)
- 全ICC < 0.50: DI=0.16, FI=0.08, RI=0.10 (H2 ✓)

### CRQ1: 勾配補正の成功 (H3)

| 条件 | DI ルート予測 CV R² |
|---|---|
| シミュレーション (drift=0) | **0.82** |
| 実データ (全ルート) | 0.58 |
| 実データ (hilly >500m) | 0.60 |
| GACD 補正後 | **−0.03** (H3 ✓) |
| DI/EstPower (Minetti) | 0.57 (**逆方向に過剰補正**) |

- ルートタイプ別DI (drift=0): front\_climb=0.39, back\_climb=2.76, symmetric=1.00
- → 7倍の範囲変動（心拍ドリフトゼロ）

### CRQ2: Occasion支配 + マルチセッション集約 (H4, E2, E3)

#### Table: 分散分解と信頼性

|  | **Person** | | | **Route** | | **Occ.** | **Val.** |
|---|---|---|---|---|---|---|---|
| Metric | ICC | Spl-h | SB | R²\_in | R²\_CV | % | Speed |
| DI | .16 | .45 | .63 | .013 | −.006 | **83** | — |
| GACD | .22 | .74 | .85 | .031 | −.030 | **78** | −.05 |
| **Grad. S.** | .36 | **.82** | **.90** | .128 | **+.089** | 58 | **+.33** |
| Speed S. | **.43** | **.87** | **.93** | .069 | −.092 | 57 | −.13 |

- Occasion 57–83% (H4 ✓)
- ルートマッチICC: GACD 0.22→0.47, GradS 0.36→0.52, SpeedS 0.43→0.73
- → 16–30 pp のapparent Occasion varianceはroute-related

#### 収束分析
- Gradient sensitivity: SB≥0.80 at **k=6** sessions
- Speed sensitivity: SB≥0.80 at **k=3** sessions
- DI: k≥9 required
- GACD: k>10 (SB₁₀=0.71)

### E1: 下り位置効果

| 分析 | 指標 | 結果 |
|---|---|---|
| 下りの量（total\_descent） | r with GACD | +0.03 ns |
| 下りの位置（desc\_front） | β* | **+0.29*** |
| Within-person (n=108) | Mean r | +0.089*, 66/108正方向 |
| Gentle (σ<5) | r | +0.10*** |
| Moderate (5–8) | r | **+0.53*** |
| Cycling | r | +0.14*** |
| Running | r | +0.20* |
| MTB | r | +0.01 ns |

- 7/8 exploratory tests survived BH-FDR
- Between-person pattern consistent with eccentric damage; within-person support modest

---

## Discussion

### D1. Operationalization Framing（先人へのリスペクト）

本研究は既存の理論的フレームワークを**builds upon, rather than contradicts**する：
- **Millet (2025)**: DI–FI冗長性の理論的予測と**consistent** → 初の大規模実証
- **Meixner et al. (2025)**: 4Dフレームワークの**フィールド展開に必要な定量的基盤**を提供
- **Friel (2009)**: <5%ルールはフラット/対称ルートでの**pioneering insight** → GACDが**全地形に拡張**

### D2. Dual-Profiling Framework

GACD回帰の3係数は概念的に異なる役割：
- **β\_time (GACD)**: 真のdurability指標 sensu Maunder et al. (2021) — 時間依存の心効率劣化
- **β\_gradient / β\_speed**: ルート補正済みsubmaximal fitness capacity profile — 地形感受性

→ β\_timeでdurability評価, β\_gradient/β\_speedで個人fitness profiling

### D3. 推奨プロトコル
1. GACDを適用しルートアーティファクトを除去
2. Gradient/speed sensitivityを個人プロファイルとして抽出
3. ≥6セッションを集約して安定推定
4. スポーツ別ベースライン必須（cycling +7.25, MTB +3.83, running +1.49 bpm/%）

### D4. Occasion支配の実務的意味
- Residual (27–53% route-matched) ≠ effort intensity (r=−0.004 ns)
- → 睡眠・水分・気温・累積疲労などunmeasured readiness factors
- → daily readiness markersとの統合が次の課題

### D5. 下り位置効果（E1）
- Between-person: β*=+0.29, moderated by steepness, absent in MTB
- Within-person: modest (r=0.089)
- → eccentric damage仮説と整合するが因果推論は不可

---

### Limitations (10項目)

1. Speed-based DI（HR/Speed, not HR/Power）→ 結果はpower-based DIには直接適用不可
2. 二次データ — センサー品質未制御
3. Residual–noise conflation（ルートマッチICCで部分対応）
4. Gold standard欠如（VO₂max, power）
5. Demographics: 94% male; age/training history unknown
6. 探索的知見は事前登録なし
7. 多重比較: 7/8 BH-FDR survived, broader analytic flexibility未考慮
8. 観察研究デザイン
9. 単一データセット
10. Sport bias (cycling 62%)

---

### Conclusion

> スピードベースDIの下では，データは4次元ではなく**2次元構造**を支持する（CRQ1）．勾配補正（GACD）はルートアーティファクトからtrue cardiac driftを分離することに成功した．Gradient sensitivityとspeed sensitivityをroute-corrected durability profiling metricsとして提案する．フィールドベースの信頼的測定の鍵は**マルチセッション集約**（CRQ2）：gradient sensitivityは**≥6セッション**で十分な信頼性（SB≥0.80）に達する．Person signal (22–43%)は集約で回復可能；Occasion component (27–53%)はreadiness/recoveryに関する情報を含みうる．マルチセッションgradient sensitivityとdaily readiness markersの統合が，フィールドベースfitness monitoringの有望な方向性である．
