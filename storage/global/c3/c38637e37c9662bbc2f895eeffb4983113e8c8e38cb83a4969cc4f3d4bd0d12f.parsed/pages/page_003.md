## 第 3 页

and GSDN (Wu et al. 2022b) incorporates structural infor-
mation to further enhance the MLP student’s performance.
VQGraph (Yang et al. 2024) proposes to learn a codebook
that represents informative local structures, and uses these
local structures as additional information for distillation. The
most related work is AdaGMLP (Lu et al. 2024a) which
adopts an AdaBoosting ensemble framework to train multi-
ple MLPs, collecting all the knowledge from each student to
make predictions.
Motivation
In resource-constrained environments, it is often crucial to
balance the trade-off between computational cost and model
accuracy. For example, early exit strategies (Bolukbasi et al.
2017; Dennis et al. 2018; Laskaridis, Kouris, and Lane 2021;
Teerapittayanon, McDanel, and Kung 2016) have been exten-
sively studied to allow models to terminate inference early
if a satisfactory prediction can be made to improve energy
efficiency. This is particularly useful in scenarios where the
computational budget can be variable, but still allows the
model to make high-confidence predictions in cases where
the input is easy to classify. Early exit mechanisms are proac-
tive in reducing computation by identifying simpler cases
early in the inference process, improving efficiency without
significantly sacrificing accuracy.
On the other hand, anytime inference strategies (Ruiz and
Verbeek 2021; Huang et al. 2017; Dennis et al. 2023) have
also been proposed to provide flexible, interruptible inference,
where a model can yield a prediction even when inference is
interrupted, e.g., due to the time limitation. In this scenario,
the model is expected to provide a prediction, even if it has
not completed the entire inference process. The main focus
here is ensuring the model can yield a usable (though po-
tentially suboptimal) prediction at any moment, allowing for
adaptive responses in real-time systems where the computa-
tion time is constrained or unpredictable.
However, to our knowledge, current G2M methods ignore
the urgent need for a more flexible and adaptive approach.
Our ProGMLP is designed to fill this gap by offering a pro-
gressive training and inference mechanism that enables dy-
namic adjustment of the trade-off between accuracy and in-
ference cost. This makes ProGMLP particularly suitable for
real-world applications where computational resources are
limited, and the ability to control inference time is critical.
Methodology
Overview
ProGMLP is an ensemble framework designed to distill
knowledge from a pre-trained GNN into a sequence of pro-
gressively trained MLPs, as illustrated in Figure 2. The pro-
gressive training structure is established by initializing each
student MLP fk+1 with the parameters θk of the previously
trained student fk. A pre-trained GNN serves as the teacher,
guiding the learning of this MLP sequence. For each stu-
dent MLP fk+1, the input comprises both the original node
features X and the hidden representation Hk output by the
previous MLP. The initial hidden representation H0 is a zero
matrix. Each MLP is trained using a combination of three
A Pretrained GNN
True 
Labels
Mixed 
Labels
True 
Labels
Mixed 
Labels
…
…
θk−1
θk
θk+1
KD 
Loss
CE 
Loss
Mixup 
Loss
Mixup 
Loss
CE 
Loss
KD 
Loss
X
X
Mixup
Mixup
Mixup
Mixup with 
Smaller/Larger  Mixing Ratio
Mixup
ProGMLP
Loss with 
Smaller/Larger Weights
Legend
Pk
…
Hk
Hk−1
Hk
Hk+1
…
Pk+1
Hk+1
MLP k
MLP k+1
…
Hidden Space
Projection
Prediction Space
Projection
Hk−1
Hk
Figure 2: The training architecture of ProGMLP.
loss functions: Mixup Loss (from interpolated samples and la-
bels), Cross-Entropy Loss (from predictions and ground-truth
labels), and Knowledge Distillation (KD) Loss (from the dis-
crepancy between the teacher GNN and the student MLP
outputs). This training process proceeds iteratively, with each
subsequent MLP student refining the knowledge distilled by
its predecessor. The mixup strategy employs an increasingly
stronger mixing ratio over time, while the loss weights for KD
and mixup components are progressively increased for later
MLPs. This encourages deeper and more robust learning.
Progressive Training Structure
The progressive training structure is at the heart of ProGMLP.
Unlike conventional G2M methods that train a single student
model, ProGMLP trains a sequence of student MLPs, each
one initialized with the parameters of the previously trained
model. This progressive approach ensures that the later mod-
els in the sequence start from a more advanced state and are
capable of tackling more complex tasks. A L-layer MLPs stu-
dent fk, consisting of a (L−1)-layer fully connected network
(FCNs) with the same hidden dimensionality for latent space
projection and 1-layer FCN for prediction space projection,
can be described as:
Hk, Pk = fk(Xk),
Hk ∈RN×d′, Pk ∈RN×C,
(1)
where Xk = CONCAT(X, Hk−1) is the input consisting
of raw features X and hidden representations Hk−1 from
the previous student. Here, H0 = O ∈RN×d′ is a zero
matrix. First, fk projects input Xk into the hidden space
within the first (L −1)-layer FCNs and then maps the hidden
representations Hk into the prediction space to obtain the
predictions Pk via the last FCN. The first MLPs student f1
is trained with random initialization. Then, after training fk,
its parameters are used to initialize the next student fk+1.
The process is repeated for each subsequent student model,
progressively refining the learning process. The relationship
24090
