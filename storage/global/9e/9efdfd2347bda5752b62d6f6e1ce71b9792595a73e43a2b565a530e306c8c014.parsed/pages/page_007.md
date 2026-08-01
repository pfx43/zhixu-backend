## 第 7 页

7
常模型误差完全相同，则不存在仅凭现有信息实现无条件
检测的方法。本文能够保证的是：受保护参考不会直接使
用新到测量更新；在已覆盖正常运行区域内，离开正常联
合残差区域的异常能够被统计量发现；结构隔离只在相应
条件可辨识时成立。
X. 结论
本文面向只有正常训练数据、没有故障方向和故障作用
模型的闭环非线性系统，提出受保护Koopman–T–S 正常
参考方法。数据编码状态负责持续描述实际系统，正常参
考状态只由延迟确认的安全起点初始化，并在检测时间窗
内依据已知控制指令和冻结模型自由递推。带起点的统一
多步残差消除了训练与在线阶段的定义不一致；精确非线
性递推和完整Jacobian 上界揭示了正常模型误差如何随
输入、规则区域和参考持续时间传播。对于完全未知的异
常方向，本文证明严格降维会留下不可见方向，并据此建
立全维联合归一化、多时间尺度统计量和输入条件动态阈
值。传感器屏蔽预测和正常输入响应空间进一步实现传感
器通道判断、执行器等效解释和过程侧剩余分解，同时给
出多执行器可分条件及不可唯一分离的边界。该框架在不
使用故障样本、不对故障求导的前提下，形成了逻辑一致
的正常模型训练、参考保护、未知故障检测、结构化隔离
和安全恢复方法。
附录A
条件新增量分解
将R = col(Ry, RS, RL) 及其协方差按相同顺序分块。第
一项为˜Ry = Ry −µy。第二项扣除正常情况下由Ry 可解
释的部分：
˜RS = RS −µS −ΣSyΣ−1
yy (Ry −µy),
(62)
其协方差为ΣS|y = ΣSS −ΣSyΣ−1
yy ΣyS。第三项再扣除给
定(Ry, RS) 后的条件均值。对Σ 作分块LDL⊤分解即可
得到式(41)。
附录B
有限时间输入响应矩阵的推导
沿受保护正常轨迹对学习模型作一阶展开：
δzt+1 = Az
t δzt + Bu
t δut.
(63)
从δzk−L = 0 开始递推并堆叠δzk−L+1:k，得到式(52)。这
里Az
t 和Bu
t 是正常模型对普通状态变量和控制指令的导
数，不涉及未知故障参数。
参考文献
[1] T. Takagi and M. Sugeno, “Fuzzy identification of systems and
its applications to modeling and control,” IEEE Trans. Syst.,
Man, Cybern., vol. SMC-15, no. 1, pp. 116–132, 1985.
[2] S. L. Brunton, B. W. Brunton, J. L. Proctor, and J. N. Kutz,
“Koopman invariant subspaces and finite linear representations
of nonlinear dynamical systems for control,” PLoS ONE, vol.
11, no. 2, Art. no. e0150171, 2016.
[3] M. Korda and I. Mezić, “Linear predictors for nonlinear dynami-
cal systems: Koopman operator meets model predictive control,”
Automatica, vol. 93, pp. 149–160, 2018.
[4] B. Lusch, J. N. Kutz, and S. L. Brunton, “Deep learning for
universal linear embeddings of nonlinear dynamics,” Nature
Commun., vol. 9, Art. no. 4950, 2018.
[5] M. Bakhtiaridoust, M. Yadegar, N. Meskin, and M. Noorizadeh,
“Model-free geometric fault detection and isolation for nonlinear
systems using Koopman operator,” IEEE Trans. Syst., Man,
Cybern.: Syst., vol. 52, no. 11, pp. 7207–7218, 2022.
[6] M. Bakhtiaridoust, M. Yadegar, and N. Meskin, “Data-driven
fault detection and isolation of nonlinear systems using deep
learning for Koopman operator,” ISA Trans., vol. 134, pp. 200–
211, 2023.
[7] M. Bakhtiaridoust, F. N. Irani, M. Yadegar, and N. Meskin,
“Data-driven sensor fault detection and isolation of nonlinear
systems: Deep neural-network Koopman operator,” IET Control
Theory Appl., vol. 17, no. 2, pp. 123–132, 2023.
[8] F. N. Irani, M. Yadegar, and N. Meskin, “Koopman-based deep
iISS bilinear parity approach for data-driven fault diagnosis:
Experimental demonstration using three-tank system,” Control
Eng. Pract., vol. 142, Art. no. 105744, 2024.
[9] D. Ichalal, B. Marx, J. Ragot, and D. Maquin, “State esti-
mation of Takagi–Sugeno systems with unmeasurable premise
variables,” IET Control Theory Appl., vol. 4, no. 5, pp. 897–
908, 2010.
[10] H. Ghorbel, M. Souissi, M. Chaabane, and D. Mehdi, “Observer
design for fault diagnosis for the Takagi–Sugeno model with
unmeasurable premise variables,” in Proc. IEEE Int. Conf.
Fuzzy Syst., 2012, pp. 1–8.
[11] Z. Lendek, T. M. Guerra, R. Babuška, and B. De Schutter,
Stability Analysis and Nonlinear Observer Design Using Takagi–
Sugeno Fuzzy Models. Berlin, Germany: Springer, 2010.
[12] S. X. Ding, Model-Based Fault Diagnosis Techniques: De-
sign Schemes, Algorithms, and Tools, 2nd ed. London, U.K.:
Springer, 2013.
[13] J. Gertler, “Fault detection and isolation using parity relations,”
Control Eng. Pract., vol. 5, no. 5, pp. 653–661, 1997.
[14] P. M. Frank, “Fault diagnosis in dynamic systems using analyt-
ical and knowledge-based redundancy: A survey and some new
results,” Automatica, vol. 26, no. 3, pp. 459–474, 1990.
[15] M. Basseville and I. V. Nikiforov, Detection of Abrupt Changes:
Theory and Application. Englewood Cliffs, NJ, USA: Prentice-
Hall, 1993.
[16] H. V. Poor, An Introduction to Signal Detection and Estimation,
2nd ed. New York, NY, USA: Springer, 1994.
[17] V. Vovk, A. Gammerman, and G. Shafer, Algorithmic Learning
in a Random World. New York, NY, USA: Springer, 2005.
[18] C. Xu and Y. Xie, “Conformal prediction for time series,”
arXiv:2010.09107, 2021.
[19] C. Xu and Y. Xie, “Sequential predictive conformal inference for
time series,” in Proc. Int. Conf. Mach. Learn., 2023, pp. 38707–
38727.
[20] G. W. Stewart and J.-G. Sun, Matrix Perturbation Theory.
Boston, MA, USA: Academic Press, 1990.
[21] S. Boyd and L. Vandenberghe, Convex Optimization. Cam-
bridge, U.K.: Cambridge Univ. Press, 2004.
