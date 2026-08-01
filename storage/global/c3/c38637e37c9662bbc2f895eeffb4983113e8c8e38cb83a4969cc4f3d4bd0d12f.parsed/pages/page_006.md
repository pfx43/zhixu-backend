## 第 6 页

Teacher
Cora
Pubmed
CS
Physics
Photo
Computers
Impro.
+Student
GCN
79.03±0.37
76.66±0.35
90.68±0.17
93.59±0.59
88.57±0.83
77.82±0.88
0.00%
+E-GLNN2
79.28±0.62
76.60±0.48
89.88±0.16
92.11±0.82
84.42±1.18
75.39±1.17
-1.67%
+E-GLNN4
79.30±0.83
76.98±0.53
89.79±0.19
92.65±0.33
84.73±1.64
75.82±1.12
-1.36%
+AdaGMLP2
79.15±0.19
76.84±0.64
90.53±0.12
92.58±0.26
84.49±1.53
76.34±1.26
-1.23%
+AdaGMLP4
79.36±1.12
77.21±0.66
91.69±0.37
92.71±0.29
85.26±1.61
77.11±1.19
-0.56%
+ProGMLP
80.19±0.39
77.42±0.35
92.43±0.12
94.23±0.04
90.91±0.77
78.82±0.44
+1.50%
GAT
78.47±2.77
75.71±0.46
90.42±0.66
92.88±0.24
86.48±1.51
76.82±1.23
0.00%
+E-GLNN2
78.94±2.05
76.84±0.76
89.72±0.70
90.63±0.95
82.66±1.69
74.78±2.16
-1.36%
+E-GLNN4
79.04±2.12
77.08±0.44
90.66±0.41
90.98±0.48
83.01±1.63
74.54±2.34
-1.04%
+AdaGMLP2
78.95±2.44
76.92±0.79
90.42±0.25
92.94±0.18
84.39±1.86
76.85±1.17
-0.02%
+AdaGMLP4
79.95±2.50
77.25±0.46
90.77±0.14
93.07±0.29
85.64±1.69
77.31±1.38
+0.70%
+ProGMLP
80.50±2.08
77.63±0.82
91.83±0.44
94.16±0.14
88.94±1.64
79.16±1.29
+2.33%
GraphSAGE
78.56±0.64
75.39±0.49
91.84±0.46
92.37±1.44
86.54±0.69
79.32±0.31
0.00%
+E-GLNN2
78.37±0.80
76.09±0.65
91.11±0.13
92.24±0.41
84.55±1.16
76.28±0.29
-1.06%
+E-GLNN4
78.32±0.97
76.95±0.79
90.62±0.36
92.41±0.39
84.78±2.38
76.14±0.32
-0.93%
+AdaGMLP2
78.39±0.76
77.01±0.84
92.41±0.20
92.67±0.29
85.16±0.84
77.94±1.41
-0.08%
+AdaGMLP4
78.84±0.98
77.31±0.29
92.79±0.21
94.20±0.30
86.98±0.72
79.23±1.06
+1.05%
+ProGMLP
79.28±0.86
77.84±1.05
93.13±0.10
93.70±0.16
87.48±1.74
80.21±1.21
+1.54%
Table 2: Comparison with Ensemble G2M Methods.
predictions from all students that have finished executing.
• AdaGMLPK: This is an ensemble framework that uses
the AdaBoost algorithm. If stopped early, its prediction is
the re-normalized, weighted sum of the outputs from the
already-executed students
Non-Ensemble G2M Methods.
Additionally, we choose
three state-of-the-art (SOTA) non-ensemble G2M methods:
• NOSMOG (Tian et al. 2022): It aims to enhance the MLP
student’s performance by incorporating structural infor-
mation from the graph.
• KRD (Wu et al. 2023b): It focuses on improving the qual-
ity of the knowledge transferred from the GNN teacher to
the MLP student.
• HGMD (Wu et al. 2024): It decouples and estimates two
types of distillation hardness and knowledge hardness to
better transfer knowledge from GNNs to MLPs.
Hyperparameters.
We
search
learning
rate
in
{0.001, 0.002, 0.005, 0.01, 0.02, 0.05},
hidden
dimen-
sionality
in
{16, 32, 64, 128, 256, 512},
weight
decay
rate in {5e −4, 5e −5, 5e −7, 5e −9}, dropout in
{0.1, 0.2, · · · , 0.9}, teacher model depth in {2, 3}, and
number of students in {2, 3, · · · , 6}, for all the methods.
Main Results
Accuracy-Cost Trade-off.
Our central claim is that
ProGMLP excels across the entire accuracy-cost spectrum.
Figure 3 visualizes the performance as a function of infer-
ence cost (number of executed students). The ProGMLP
curve (green) consistently dominates the baselines. Notably,
it delivers strong accuracy in the low-cost regime (e.g., with
1-3 students) and continues to improve steadily as more com-
putation is permitted. In contrast, E-GLNN plateaus quickly,
while AdaGMLP’s gains are inefficient. This demonstrates
ProGMLP’s ability to provide a meaningful, on-demand
trade-off, making it highly adaptable to diverse computa-
tional budgets.
GCN
GAT
SAGE
87
90
92
Accuracy (%)
CS
GCN
GAT
SAGE
92
94
Physics
GCN
GAT
SAGE
80
90
Accuracy (%)
Photo
GCN
GAT
SAGE
77
80
Computers
Teacher
+KRD
+HGMD
+NOOSG
+ProGMLP
Figure 4: Performance Comparison against G2M Methods.
Peak Performance.
Beyond the trade-off curve, ProGMLP
also achieves state-of-the-art peak accuracy. Tables 2 and
Figure 4 show that ProGMLP’s final performance is consis-
tently superior or highly competitive against both ensemble
and single-student baselines across all datasets and teacher
models. This confirms that our progressive approach does
not sacrifice peak performance for flexibility.
24093
