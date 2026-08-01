## 第 5 页

1
2
3
4
5
6
7
8
9 10
# Executed Students
90
92
Accuracy (%)
CS
E-GLNN10
AdaGMLP10
ProGMLP10
1
2
3
4
5
6
7
8
9 10
# Executed Students
90
92
94
Physics
E-GLNN10
AdaGMLP10
ProGMLP10
1
2
3
4
5
6
7
8
9 10
# Executed Students
82
85
Photo
E-GLNN10
AdaGMLP10
ProGMLP10
1
2
3
4
5
6
7
8
9 10
# Executed Students
60
70
Computers
E-GLNN10
AdaGMLP10
ProGMLP10
(a) Teacher = GCN
1
2
3
4
5
6
7
8
9 10
# Executed Students
87
90
92
Accuracy (%)
CS
E-GLNN10
AdaGMLP10
ProGMLP10
1
2
3
4
5
6
7
8
9 10
# Executed Students
90
92
94
Physics
E-GLNN10
AdaGMLP10
ProGMLP10
1
2
3
4
5
6
7
8
9 10
# Executed Students
80
85
Photo
E-GLNN10
AdaGMLP10
ProGMLP10
1
2
3
4
5
6
7
8
9 10
# Executed Students
60
70
Computers
E-GLNN10
AdaGMLP10
ProGMLP10
(b) Teacher = GraphSAGE
Figure 3: Accuracy vs. Inference Cost (# Number of Executed Students) for ProGMLP, AdaGMLP, and GLNN.
If ck < τ conf, ProGMLP proceeds to the next student fk+1.
The output P is a weighted sum of predictions from the
evaluated models:
P =
k
X
j=1
wjPj,
wk = SOFTMAX({c1, c2, · · · , ck})k,
(10)
This ensures efficient and adaptive inference for varying con-
ditions.
Complexity
The time complexity of the ProGMLP framework is pri-
marily determined by the number of MLPs students K.
The time complexity of training each MLPs student mainly
comes from: (1) feature forward O(Nd′(d + d′ + C));
(2) knowledge distillation O(NC); (3) mixup augmen-
tation O(|VL|(d + d′)), where |VL| and d′ are largely
small compared to N and d, respectively. Therefore, the
overall training complexity of ProGMLP can be approxi-
mated as O (KN(d′(d + d′ + C) + C)). During inference,
ProGMLP evaluates each MLPs student sequentially, stop-
ping the process based on the confidence-time budgeting
mechanism. In the worst-case scenario, all K MLPs are eval-
uated. The inference time complexity for a single sample is
therefore O (Kd′(d + d′ + C)).
Experiments
In this section, we present a comprehensive set of experi-
ments to evaluate our ProGMLP.
Experimental Setup
Hardware and Software.
ProGMLP is implemented based
on the Torch Geometric library (Fey and Lenssen 2019) and
PyTorch 3.7.1 with Intel(R) Core(TM) i9-10980XE CPU @
3.00GHz and one NVIDIA A100 GPUs with 40GB memory.
Dataset
# Nodes
# Edges
# Features
# Classes
Cora
2,708
5,278
1,433
7
Pubmed
19,717
44,324
500
3
Amazon Photo
7,650
119,081
745
8
Amazon Computers
13,381
245,778
767
10
Coauthor CS
18,333
81,894
6,805
15
Coauthor Physics
34,493
247,962
8,415
5
ogbn-arxiv
169,343
1,166,243
128
40
ogbn-products
2,449,029
61,859,140
128
47
Table 1: Datasets Statics.
Datasets.
To comprehensively evaluate the performance,
generalizability, and scalability of ProGMLP, we have se-
lected eight widely-adopted real-world graph datasets: Cora,
Pubmed (Sen et al. 2008), Amazon Photo, Amazon Comput-
ers, Coauthor CS, Coauthor Physics (Shchur et al. 2018),
ogbn-arxiv, and ogbn-products (Hu et al. 2020). These
datasets exhibit diversity in node features, graph structures,
and task complexities, offering a comprehensive benchmark
for evaluating the generalizability of our approach. We pro-
vide the statistical summaries in Table 1.
Teacher Models.
For the teacher GNN models, we select
three of the most representative architectures: GCN (Kipf
and Welling 2016), GAT (Veliˇckovi´c et al. 2017), and Graph-
SAGE (Hamilton, Ying, and Leskovec 2017). Each GNN is
implemented with a standard 2-layer structure to ensure a fair
and consistent comparison across experiments.
Ensemble Student Models.
To compare ProGMLP in set-
tings that require early-exit or anytime inference, we adapt
two representative G2M methods, GLNN (Zhang et al. 2021)
and AdaGMLP (Lu et al. 2024a) , which normally only pro-
duce output upon complete execution. The adapted versions
are as follows:
• E-GLNNK: This is an ensemble of K students based
on the GLNN method. For an early exit, it averages the
24092
