## 第 1 页

ProGMLP: A Progressive Framework for GNN-to-MLP Knowledge Distillation
with Efficient Trade-offs
Weigang Lu1, Ziyu Guan2*, Wei Zhao2, Yaming Yang2, Yujie Sun2, Zheng Liang1,
Yibing Zhan3, Dapeng Tao4
1Department of Civil and Environmental Engineering, The Hong Kong University of Science and Technology, Hong Kong SAR
2School of Computer Science and Technology, Xidian University, Xi’an, China
3JD Explore Academy, Beijing, China
4School of Information Science and Engineering, Yunnan University, Kunming, China
weiganglu@ust.hk, {zyguan@, ywzhao@mail., yym@, yujsun@stu.}xidian.edu.cn, liangz@ust.hk, zhanyibing@jd.com,
dapeng.tao@gmail.com
Abstract
GNN-to-MLP (G2M) methods have emerged as a promising
approach to accelerate Graph Neural Networks (GNNs) by dis-
tilling their knowledge into simpler Multi-Layer Perceptrons
(MLPs). These methods bridge the gap between the expressive
power of GNNs and the computational efficiency of MLPs,
making them well-suited for resource-constrained environ-
ments. However, existing G2M methods are limited by their
inability to flexibly adjust inference cost and accuracy dynam-
ically, a critical requirement for real-world applications where
computational resources and time constraints can vary signifi-
cantly. To address this, we introduce a Progressive framework
designed to offer flexible and on-demand trade-offs between
inference cost and accuracy for GNN-to-MLP knowledge dis-
tillation (ProGMLP). ProGMLP employs a Progressive Train-
ing Structure (PTS), where multiple MLP students are trained
in sequence, each building on the previous one. Furthermore,
ProGMLP incorporates Progressive Knowledge Distillation
(PKD) to iteratively refine the distillation process from GNNs
to MLPs, and Progressive Mixup Augmentation (PMA) to en-
hance generalization by progressively generating harder mixed
samples. Our approach is validated through comprehensive
experiments on eight real-world graph datasets, demonstrating
that ProGMLP maintains high accuracy while dynamically
adapting to varying runtime scenarios, making it highly effec-
tive for deployment in diverse application settings.
Code — https://github.com/WeigangLu/ProGMLP-main
Introduction
GNN-to-MLP (G2M) methods have recently gained atten-
tion as an effective approach for accelerating the inference
of Graph Neural Networks (GNNs) (Kipf and Welling 2016;
Veliˇckovi´c et al. 2017; Hamilton, Ying, and Leskovec 2017;
Wu et al. 2019; Xu et al. 2018a; Klicpera, Bojchevski, and
G¨unnemann 2018; Yang et al. 2022a; Lu et al. 2024c) by dis-
tilling their knowledge into simpler Multi-Layer Perceptrons
(MLPs). These methods typically involve training a single
*Corresponding Author
Copyright © 2026, Association for the Advancement of Artificial
Intelligence (www.aaai.org). All rights reserved.
GCN
Accurate but 
Slower
GLNN
Faster but Less 
Accurate
Unsatisﬁed
Region
Inference  Latency
Accuracy
Satisﬁed
Region
(a) Static Inference of Current Models (b) On-demand Inference of ProGMLP 
Inference  Latency
Accuracy
ProGMLP
ProGMLP
ProGMLP
ProGMLP
Figure 1: Figure 1: ProGMLP Motivation. (a) Existing static
models offer only a single, fixed accuracy-latency trade-off,
failing to meet dynamic application needs. (b) ProGMLP
provides a single, adaptive framework that enables flexible,
on-demand trade-offs, offering a spectrum of operating points
to satisfy diverse requirements.
MLPs (Zhang et al. 2021; Tian et al. 2022; Wu et al. 2023b,a),
or a set of MLPs (Lu et al. 2024a), to mimic GNN predictions.
They aim to bridge the gap between the expressive power of
GNNs and the computational efficiency of MLPs, making
them promising for deployment in resource-constrained envi-
ronments or latency-sensitive applications. By pre-compiling
graph knowledge into MLPs, G2M techniques significantly
reduce the need for explicit graph traversal and neighborhood
aggregation during inference, leading to faster prediction
times.
However, a critical limitation of existing G2M approaches
is their lack of flexibility in balancing inference cost and ac-
curacy. Current methods are designed to operate within fixed
computational budgets, which means they cannot dynami-
cally adjust to the varying demands of different application
scenarios. As illustrated in Figure 1 (a), this creates a funda-
mental mismatch. System operators are forced to make a pre-
emptive choice: deploy a fast, low-accuracy model suitable
for edge devices, or a slow, high-accuracy model for server-
side analytics. In real-world settings, the ability to control
the trade-off between inference accuracy and computational
cost on-demand during execution is crucial. For instance, in
edge computing (Cao et al. 2020; Mao et al. 2017; Chen and
Ran 2019; Shi et al. 2016) or mobile environments (Hoehle
The Fortieth AAAI Conference on Artificial Intelligence (AAAI-26)
24088
