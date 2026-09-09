# TCN 知识点 tag（按领域）

每个领域一份词表，文件名就是 `domain`。`id` 给 `predict` 的 `current_node`；`name` 写在题目上。

完整点边图谱在仓库 `assets/tcn/domain-graphs/{domain}.tcn-domain-graph.json`，由运行时 `graph_export` 读取。

| 领域 | JSON | 说明 | active 节点 |
| --- | --- | --- | ---: |
| `higher_math` | [higher_math.json](./higher_math.json) / [higher_math.md](./higher_math.md) | 高等数学，源 [`higher_math.tcn-domain-graph.json`](../../../assets/tcn/domain-graphs/higher_math.tcn-domain-graph.json) | 233 |
| `math` | [math.json](./math.json) / [math.md](./math.md) | 数学，源 [`math.tcn-domain-graph.json`](../../../assets/tcn/domain-graphs/math.tcn-domain-graph.json) | 83 |
| `physics` | [physics.json](./physics.json) / [physics.md](./physics.md) | 物理，源 [`physics.tcn-domain-graph.json`](../../../assets/tcn/domain-graphs/physics.tcn-domain-graph.json) | 87 |
| `discrete_math` | [discrete_math.json](./discrete_math.json) / [discrete_math.md](./discrete_math.md) | 离散数学，源 [`discrete_math.tcn-domain-graph.json`](../../../assets/tcn/domain-graphs/discrete_math.tcn-domain-graph.json) | 100 |
