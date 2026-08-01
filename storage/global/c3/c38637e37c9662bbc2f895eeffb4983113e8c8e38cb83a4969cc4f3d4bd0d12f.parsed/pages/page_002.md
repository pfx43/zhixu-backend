## 第 2 页

and Venkatesh 2015; Islam, Islam, and Mazumder 2010),
where computational power and energy resources can fluc-
tuate, a model that can adaptively tune its inference process
to optimize for either speed or accuracy would be highly
beneficial. During peak loads, it may be necessary to serve
predictions with lower latency at the cost of a slight accuracy
drop to meet throughput demands. This reality necessitates
the use of early-exit (Bolukbasi et al. 2017; Dennis et al.
2018) or anytime inference (Ruiz and Verbeek 2021; Huang
et al. 2017; Dennis et al. 2023) applications, where the infer-
ence process may be interrupted due to changing resource
availability. Unfortunately, this aspect of flexibility has been
largely overlooked in existing G2M methods, limiting their
practical utility.
To address this gap, we propose ProGMLP, a progres-
sive framework designed to offer flexible and on-demand
trade-offs between inference cost and accuracy in the con-
text of G2M. The motivation behind ProGMLP is to enable
users to dynamically adjust the inference process based on
the specific needs of their applications, whether it be maxi-
mizing accuracy under loose time constraints or minimizing
inference time when computational resources are scarce. As
visualized in Figure 1 (b), ProGMLP is not a single-point
solution but an adaptive framework that spans a spectrum of
operating points on the accuracy-latency curve. ProGMLP
achieves this through a sequence of progressively trained
MLPs, each building on the knowledge of the previous one,
and incorporates a performance-time budgeting mechanism
that intelligently manages when to stop inference based on
real-time performance metrics.
Our contributions can be summarized as follows:
• We propose ProGMLP, the first framework to address
flexible trade-offs between accuracy and inference cost
in the G2M paradigm, allowing dynamic runtime adjust-
ments based on application needs, such as computational
resources or time constraints.
• ProGMLP features a novel design with Progressive Train-
ing, Progressive Knowledge Distillation, and Progressive
Mixup Augmentation, refining each student model for
improved task performance.
• We evaluate ProGMLP on eight real-world graphs, demon-
strating that it delivers high accuracy while enabling flex-
ible control over inference costs, making it practical for
diverse runtime scenarios.
Preliminaries
Notations
We define a graph G = {V, E, Y }, where V is the set of
N nodes and E is the set of edges. The node features are
represented by the matrix X ∈RN×d, where xi is the d-
dimensional feature vector for node i. The one-hot label
matrix for C classes is Y ∈RN×C, and the graph structure is
encoded by the adjacency matrix A ∈RN×N, where Aij = 1
if an edge exists between nodes i and j, and 0 otherwise. For
the node classification task, we divide the nodes into labeled
(VL) and unlabeled (VU) subsets. In this paper, uppercase
letters (e.g., X) denote matrices, while lowercase letters (e.g.,
xi) denote row vectors from these matrices.
Related Works
Graph
Neural
Networks.
Graph
Neural
Networks
(GNNs) (Kipf and Welling 2016; Veliˇckovi´c et al. 2017;
Hamilton, Ying, and Leskovec 2017; Wu et al. 2019; Xu et al.
2018a; Klicpera, Bojchevski, and G¨unnemann 2018; Yang
et al. 2022a; Chen et al. 2020a; Xu et al. 2018b; Du et al.
2024) are a class of models that leverage the graph structure
to learn node representations. A GNN typically follows an
iterative message-passing paradigm, where each node in the
graph aggregates information from its neighboring nodes
to update its own representation. Through multiple layers,
GNNs enable the learning of node embeddings that incor-
porate not only the node’s features but also the structural
information from its local and extended neighborhood. This
mechanism allows GNNs to generalize well to diverse tasks
such as node classification (Lu et al. 2024c, 2023, 2024b,
2025), link prediction (Shomer et al. 2024), and graph classi-
fication (Yang et al. 2022b). However, despite their efficacy,
GNNs face several challenges, particularly in terms of scala-
bility and inference efficiency. As the size and complexity of
real-world graphs grow, GNNs become increasingly expen-
sive to train and deploy due to the high computational and
memory costs associated with processing large graphs and
multiple layers of message passing. This issue is further ex-
acerbated when GNNs are deployed in resource-constrained
environments, such as edge devices or mobile platforms,
where both computation and memory are limited.
GNN-to-GNN Knowledge Distillation.
To address the ef-
ficacy issue in GNNs, GNN-to-GNN Knowledge Distillation
(G2G KD) (Lassance et al. 2020; Zhang et al. 2023; Ren
et al. 2021; Joshi et al. 2022; Wu et al. 2022a; Zhang et al.
2019; Ren et al. 2021; Chen et al. 2020b) has been exten-
sively studied. They aim to compress large, complex Graph
Neural Networks (GNNs) into smaller, more efficient GNN
models. These approaches leverage KD techniques (Hinton,
Vinyals, and Dean 2015; Ba and Caruana 2014) to transfer
the knowledge embedded in a large teacher GNN to a smaller
student GNN. For example, methods like LSP (Yang et al.
2020) and TinyGNN (Yan et al. 2020) facilitate the trans-
fer of localized structural information from teacher GNNs
to their student counterparts. Similarly, RDD (Zhang et al.
2020) enhances G2G KD by considering the reliability of
nodes and edges. Although effective, these methods often
require neighbor fetching during inference, which can intro-
duce latency and make them less practical for real-time or
resource-constrained applications.
GNN-to-MLP Knowledge Distillation.
To address the in-
ference efficacy issue in G2G KD, GNN-to-MLP (G2M)
KD has emerged as a promising alternative. This approach
transfers the knowledge of a GNN to a simpler MLPs model,
which eliminates the need for message passing during in-
ference and thus significantly reduces latency. Early work
such as GLNN (Zhang et al. 2021) introduces a general
G2M framework where an MLPs student is trained using
both ground-truth and soft labels from a GNN teacher. Sub-
sequent methods like KRD (Wu et al. 2023b) introduces
a reliable sampling strategy to improve the quality of the
knowledge transferred, while NOSMOG (Tian et al. 2022)
24089
