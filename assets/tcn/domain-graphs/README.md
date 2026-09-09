# TCN 封闭学科完整图谱（点 + 边）

运行时由 `app.services.tcn.graph_export` 读取，供学习路径 / `tcn-graph` API 使用。

命名：`{domain}.tcn-domain-graph.json`  
例如 `math.tcn-domain-graph.json` 对应学科 `math`。

`docs/api/TCN/{domain}.json` 是从这些导出抽出来的 **tag 词表**（只有 id/name），不替代本目录。
