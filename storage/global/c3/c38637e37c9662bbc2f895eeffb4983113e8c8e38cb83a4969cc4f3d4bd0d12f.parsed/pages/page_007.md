## 第 7 页

ogbn-arxiv
ogbn-products
Acc.
Inf. Time
Acc.
Inf. Time
GCN
68.42±0.67
84.13
72.94±0.14
274.77
+ProGMLP
70.11±0.74
3.95
73.00±0.12
52.21
Impro.
+2.47%
↑21×
+0.08%
↑5×
GAT
69.25±1.26
97.81
OOM
-
+ProGMLP
70.29±1.94
12.80
-
-
Impro.
+1.50%
↑8×
-
-
GraphSAGE
69.70±0.21
27.99
75.59±0.10
139.21
+ProGMLP
70.97±0.85
6.93
75.68±0.07
59.06
Impro.
+1.80%
↑4×
+0.01%
↑2×
Table 3: Node Classification Accuracy (%) and Inference
Time (ms) on Large-scale Graphs. “↑m ×” indicates
ProGMLP is m times faster than the teacher at the infer-
ence stage.
Scalability and Generalization
We further test ProGMLP on large-scale graphs and in an
inductive setting to verify its practicality.
Large-scale Graphs.
On the OGB datasets (Table 3),
ProGMLP not only improves accuracy over strong GNN
teachers but also delivers massive inference speedups: up to
21× faster than GCN on ogbn-arxiv. This result highlights
its suitability for real-world, large-scale applications where
inference latency is a critical bottleneck.
Inductive Setting.
When required to generalize to unseen
nodes (Table 4), ProGMLP again demonstrates substantial
improvements over its GNN teachers (e.g., +9.85% over
GCN on Pubmed). This suggests our proposed PKD and
PMA components effectively distill robust, generalizable
knowledge, not just memorizing patterns in a transductive
setting.
Cora
Pubmed
CS
Physics
GCN
70.31±0.54
80.06±0.37
90.93±0.35
93.27±0.26
+ProGMLP
73.07±0.66
87.95±0.36
93.38±0.31
95.44±0.18
Impro.
+3.92%
+9.85%
+2.69%
+2.32%
GAT
71.47±1.35
82.67±0.88
90.51±0.30
93.41±0.18
+ProGMLP
72.50±0.91
88.01±0.42
94.02±0.21
95.99±0.20
Impro.
+1.44%
+6.46%
+3.88%
+2.76%
GraphSAGE
69.71±1.13
85.56±0.54
90.50±0.53
93.95±0.49
+ProGMLP
71.91±0.71
88.60±0.30
94.80±0.21
95.26±0.15
Impro.
+3.16%
+3.55%
+4.75%
+1.39%
Table 4: Inductive Node Classification Accuracy (%).
Ablation and Hyperparameter Analysis
To understand the source of ProGMLP’s effectiveness, we
ablate its components and analyze its hyperparameters.
Component Ablation.
Figure 5 shows that all components
are integral to our method’s success. The Progressive Train-
ing Structure (PTS) is most critical; its removal causes a
drastic accuracy drop ( 4% on CS), confirming that our core
Ori.
- PTS
- PKD
- PMA
90
92
Accuracy (%)
CS
Ori.
- PTS
- PKD
- PMA
92
94
Physics
Ori.
- PTS
- PKD
- PMA
85
90
Accuracy (%)
Photo
Ori.
- PTS
- PKD
- PMA
70
75
Computers
Figure 5: Ablation Study. Each figure compares the accuracy
of the original ProGMLP (Ori.) with three ablated versions:
without PTS (- PTS) / PKD (- PKD) / PMA (- PMA).
idea of sequential knowledge refinement is essential. Progres-
sive Knowledge Distillation (PKD) and Progressive Mixup
Augmentation (PMA) provide significant and complementary
gains, aiding in effective knowledge transfer and generaliza-
tion, respectively.
0.0
0.5
1.0
80
90
Accuracy (%)
0.0
0.5
1.0
90
92
0.0
0.5
1.0
87
90
Accuracy (%)
0.00
0.25
0.50
0.75
90
92
conf
Figure 6: Hyperparameter Sensitivity Analysis.
Hyperparameter Sensitivity.
Our analysis in Figure 6
reveals that ProGMLP is robust to most hyperparameter
choices. The model’s performance is largely stable across dif-
ferent values for β, γ, and the early-exit threshold τ conf. The
most sensitive parameter is α, which balances the distillation
and ground-truth losses, underscoring the importance of this
balance in the distillation process.
Conclusion
In this paper, we present ProGMLP, a novel framework that
bridges the gap between the high expressiveness of GNNs and
the computational efficiency of MLPs. ProGMLP introduces
a progressive learning mechanism that allows for flexible
and adaptive trade-offs between inference cost and accuracy.
Through comprehensive evaluations on multiple datasets,
including large-scale graphs, ProGMLP demonstrates signifi-
cant improvements in accuracy over existing methods while
drastically reducing inference times. The results highlight
ProGMLP’s suitability for real-world applications where
computational resources and time are limited. The frame-
work’s ability to scale to large datasets further shows its
effectiveness in balancing performance with efficiency.
24094
