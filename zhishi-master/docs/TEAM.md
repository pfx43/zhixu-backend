# 团队分工

## 项目：知拾 KT 融合 (Patchouli Knowledge × LEKT)

---

## 人员

| 姓名 | 角色 | GitHub |
|------|------|--------|
| 罗洁 |  KT 算法/后端 | @luowww |
| 陈勇搏 | Flutter 前端开发 | — |
| 张子麟 | 可视化 + UI 组件 | — |

---

## 分工图

```
                        罗洁
                   (项目负责人)
                    算法 + 后端
                         │
            ┌────────────┼────────────┐
            │            │            │
        算法核心      后端 API      方案/文档
        (LEKT)      (FastAPI)    (论文/答辩)
            │            │
            └─────┬──────┘
                  │ 提供 REST API (localhost:8765)
                  │
        ┌─────────┴─────────┐
        │                   │
    陈勇搏               张子麟
  Flutter 前端        可视化 + UI
        │                   │
  · Service 层         · 依赖网络图
  · 数据模型           · 学习进度折线图
  · 页面逻辑           · 掌握度雷达图
  · Agent 集成         · 学习路径卡片
  · 聊天模式切换       · 仪表盘视觉设计
        │                   │
        └─────────┬─────────┘
                  │
              联调测试
            (三人共同负责)
```

---

## 罗洁 —  KT 算法/后端

**你负责的部分：**

- 整个项目的架构设计和方案制定
- LEKT/LADL 算法理解和接口说明
- Python FastAPI 后端开发维护
- `logic_matrix.npy` 先修矩阵生成（真实学科数据）
- 数据管线（`1_candidate_filter.py` → `2_optimized_axiom_generator.py`）
- 后端 API 测试（curl / Postman）


**工作目录：**

```
KT融合/
├── kt_backend/           ← 你主力维护
├── lekt_release_cython(3)/ ← 参考/只读
├── README.md / PLAN.md   ← 你定稿
└── TEAM.md               ← 你维护
```

**你的任务清单：**

| # | 任务 | 状态 |
|---|------|------|
| 1 | 维护 `xzs` conda 环境（Python 3.14） | ✅ 已搭建 |
| 2 | FastAPI 后端（server.py / lekt_service.py / models.py） | ✅ 已完成 |
| 3 | 后端端点全部测试通过 | ✅ 已验证 |
| 4 | 根据实际学科数据生成 `logic_matrix.npy` | ✅ CSV工具已完成; 🔄 真实学科数据待导入 |
| 5 | 启动脚本 + 部署文档 | ✅ 全部完成 (start_server.bat + DEPLOY.md) |
| 6 | 后端降级方案（.pyd 不可用时的纯 NumPy 回退） | ✅ 已实现 |
| 7 | 论文/答辩材料准备 | ✅ DEFENSE.md 已完成（论点/架构/PPT结构） |

---

## 陈勇搏 — Flutter 前端开发

### 已为你准备好的文件（先看这些）

| 文件 | 说明 |
|------|------|
| `lib/models/kt_models.dart` | 所有 KT 数据类（SkillNode, DependencyGraphData, LearningPathStep 等） |
| `lib/serve/kt_api_service.dart` | KT 后端 HTTP 客户端，单例模式。**已增加** `loadConfig()`、`saveConfig()` |
| `lib/main.dart` | 已加 KT 健康检查（line 90-94），不要再动 |
| `PLAN.md` | 完整 API 格式、数据流图 |

### 你需要写的文件

**新建 6 个：**

#### 1. `lib/serve/kt_graph_service.dart`
```dart
/// 依赖图数据缓存与处理
class KTGraphService {
  static final KTGraphService instance = KTGraphService._();
  KTGraphService._();

  DependencyGraphData? _cachedGraph;

  /// 获取依赖图（首次从 API 拉取，后续用缓存）
  Future<DependencyGraphData> getGraph({bool forceRefresh = false});

  /// 根据掌握度更新节点颜色/状态
  List<SkillNode> applyMastery(DependencyGraphData graph, Map<String, double> states);

  /// 搜索技能
  List<SkillNode> search(String query);
}
```

#### 2. `lib/serve/learning_record_service.dart`
```dart
/// 学习记录 JSON 持久化（文件路径: {appDataDir}/data/learning_records.json）
class LearningRecordService {
  final String appDataDir;
  LearningRecordService(this.appDataDir);

  /// 保存一次认知状态快照
  Future<void> saveSnapshot(CognitiveState state);

  /// 读取所有历史快照
  Future<LearningProgress> getProgress();

  /// 获取指定技能的掌握度变化序列
  List<({DateTime time, double mastery})> getSkillHistory(
    LearningProgress progress, String skillId);
}
```

#### 3. `lib/pages/learning_dashboard_page.dart`
页面接收参数：
```dart
class LearningDashboardPage extends StatefulWidget {
  final KTApiService ktApi;       // 用 KTApiService.instance
  final KTGraphService graphService; // 用 KTGraphService.instance  
  final LearningRecordService recordService;

  // 页面结构: 顶部 3 个统计卡片 + TabBar(3个tab)
  // Tab 1: KtDependencyGraphWidget + 技能选中详情
  // Tab 2: LearningProgressChart + 技能筛选下拉
  // Tab 3: MasteryRadarChart + LADL修正前后对比
}
```

#### 4. `lib/pages/learning_path_page.dart`
```dart
class LearningPathPage extends StatefulWidget {
  final KTApiService ktApi;

  // 调用 ktApi.recommendLearningPath(states, topK: 5)
  // 渲染 ListView of LearningPathCard
}
```

#### 5. `lib/serve/socratic_tina_service.dart`
```dart
/// 苏格拉底导师 Agent（参考 agent_serve.dart 的 ChatTinaService）
class SocraticTinaService {
  // 构造函数参数：BaseAPI llm, DifyKnowledgeDatabase difyKnowledge, 
  //   FileServe fileServe, KTApiService ktApi

  // 专属工具的 function definitions:
  // - analyze_current_knowledge(topic): 调用 ktApi.evaluate() + correct()
  // - get_learning_scaffold(topic): 根据先修关系生成引导问题链
  // - evaluate_answer(topic, answer): LLM 评估回答深度
  // - suggest_next_question(topic, depth): 生成下一个引导问题
}
```

#### 6. `lib/serve/kt_config.dart`
```dart
/// KT 配置状态管理（ChangeNotifier，供 SettingPage 使用）
class KTConfig extends ChangeNotifier {
  String backendUrl;
  bool isConnected;
  int skillsCount;

  Future<void> loadFrom(KTApiService api);
  Future<void> saveTo(KTApiService api);
  Future<void> checkConnection(KTApiService api);
}
```

**修改 2 个现有文件：**

#### `lib/pages_adapter.dart` — 加 2 个适配器
```dart
// 参考现有 HomePageAdapter 模式，接收必要的服务参数
Widget LearningDashboardAdapter({...})
Widget LearningPathPageAdapter({...})
```

#### `lib/serve/agent_manager.dart` — 加 SocraticTina
```dart
// 在现有 AgentManager 中追加：
SocraticTinaService? _socraticTina;
SocraticTinaService get socraticTina => _socraticTina!;
Future<void> initializeKT(KTApiService ktApi, FileServe fileServe);
```

部分文件已由罗洁完成（未完成的你再动工）：

| # | 任务 | 状态 |
|---|------|------|
| 2 | `kt_api_service.dart` — HTTP 客户端 | ✅ 已由罗洁完成 |
| 3 | `kt_models.dart` — 数据模型 | ✅ 已由罗洁完成 |
| 4 | `kt_graph_service.dart` | 🔲 待你做 |
| 5 | `learning_record_service.dart` | 🔲 待你做 |
| 6 | `learning_dashboard_page.dart` + `learning_path_page.dart` | 🔲 待你做 |
| 7 | agent_manager.dart 扩展 + pages_adapter.dart | 🔲 待你做 |
| 8 | HomePage/SettingPage/ChatPage 扩展 | 🔲 待你做 |
| 9 | `socratic_tina_service.dart` | 🔲 待你做 |

**不依赖后端，可以立刻开始写** — 用模拟数据先跑通 UI：
```dart
// 模拟 ktApi 返回值（写页面时用）
final mockStates = {'skill_0': 0.3, 'skill_1': 0.5, 'skill_2': 0.8, 'skill_3': 0.2, 'skill_4': 0.1, 'skill_5': 0.0, 'skill_6': 0.0};
final mockGraph = DependencyGraphData(skills: [...], edges: [...], totalSkills: 7, totalEdges: 11);
```

---

## 张子麟 — 可视化 + UI 组件

### 你需要的依赖

`pubspec.yaml` 已添加 `fl_chart: ^0.69.0`，clone 后先跑 `flutter pub get`。

### 模拟数据（复制到你的 widget 文件里直接用）

```dart
// ─── 依赖网络图模拟数据 ───
import '../models/kt_models.dart';

final mockSkills = [
  SkillNode(id: 'skill_0', name: '加法', index: 0, mastery: 0.9),
  SkillNode(id: 'skill_1', name: '减法', index: 1, mastery: 0.7),
  SkillNode(id: 'skill_2', name: '乘法', index: 2, mastery: 0.5),
  SkillNode(id: 'skill_3', name: '除法', index: 3, mastery: 0.4),
  SkillNode(id: 'skill_4', name: '一元一次方程', index: 4, mastery: 0.2),
  SkillNode(id: 'skill_5', name: '函数基础', index: 5, mastery: 0.1),
  SkillNode(id: 'skill_6', name: '微积分入门', index: 6, mastery: 0.0),
];

final mockEdges = [
  KnowledgeDependencyEdge(sourceId: 'skill_0', targetId: 'skill_2', sourceName: '加法', targetName: '乘法'),
  KnowledgeDependencyEdge(sourceId: 'skill_0', targetId: 'skill_4', sourceName: '加法', targetName: '一元一次方程'),
  KnowledgeDependencyEdge(sourceId: 'skill_2', targetId: 'skill_4', sourceName: '乘法', targetName: '一元一次方程'),
  KnowledgeDependencyEdge(sourceId: 'skill_2', targetId: 'skill_5', sourceName: '乘法', targetName: '函数基础'),
  KnowledgeDependencyEdge(sourceId: 'skill_4', targetId: 'skill_5', sourceName: '一元一次方程', targetName: '函数基础'),
  KnowledgeDependencyEdge(sourceId: 'skill_4', targetId: 'skill_6', sourceName: '一元一次方程', targetName: '微积分入门'),
  KnowledgeDependencyEdge(sourceId: 'skill_5', targetId: 'skill_6', sourceName: '函数基础', targetName: '微积分入门'),
];

final mockGraph = DependencyGraphData(
  skills: mockSkills,
  edges: mockEdges,
  totalSkills: 7,
  totalEdges: 7,
);

// ─── 折线图模拟数据 ───
// 格式: List<({String skillName, List<double> values, List<DateTime> dates})>
// 或者直接用 fl_chart 的 FlSpot 列表
final mockProgressData = [
  {'skill': '加法', 'history': [0.2, 0.4, 0.6, 0.8, 0.9], 'days': ['5/20','5/21','5/22','5/23','5/24']},
  {'skill': '乘法', 'history': [0.1, 0.3, 0.4, 0.5, 0.5], 'days': ['5/20','5/21','5/22','5/23','5/24']},
  {'skill': '方程', 'history': [0.0, 0.1, 0.1, 0.2, 0.2], 'days': ['5/20','5/21','5/22','5/23','5/24']},
];

// ─── 雷达图模拟数据 ───
final mockRadarData = {
  '加法': 0.9, '减法': 0.7, '乘法': 0.5, '除法': 0.4,
  '方程': 0.2, '函数': 0.1, '微积分': 0.0,
};
final mockRadarCorrected = {
  '加法': 0.9, '减法': 0.7, '乘法': 0.5, '除法': 0.4,
  '方程': 0.15, '函数': 0.05, '微积分': 0.0,
}; // LADL 修正后（方程、微积分被拉低，因为先修未掌握）

// ─── 学习路径卡片模拟数据 ───
import '../models/kt_models.dart';
final mockPathSteps = [
  LearningPathStep(
    skillId: 'skill_2', skillName: '乘法',
    currentMastery: 0.5, priorityScore: 2.5, readiness: 0.75,
    prereqsDoneIds: ['skill_0', 'skill_1'],
    prereqsDoneNames: ['加法', '减法'],
    prereqsMissingIds: [], prereqsMissingNames: [],
  ),
  LearningPathStep(
    skillId: 'skill_3', skillName: '除法',
    currentMastery: 0.4, priorityScore: 2.0, readiness: 0.8,
    prereqsDoneIds: ['skill_0'],
    prereqsDoneNames: ['加法'],
    prereqsMissingIds: [], prereqsMissingNames: [],
  ),
];
```

### 你需要写的组件

#### 1. `lib/widgets/kt_dependency_graph_widget.dart`

```dart
/// 知识依赖有向网络图
/// 
/// 技术: CustomPainter + AnimationController（力导向布局）
/// 参考: lib/widgets/knowledge_graph_widget.dart
class KtDependencyGraphWidget extends StatefulWidget {
  final DependencyGraphData graph;        // 节点和边
  final Map<String, double>? masteryMap;  // skill_id → 掌握度 [0,1]
  final void Function(SkillNode node)? onNodeTap;

  // 渲染要求:
  // - 节点: 圆形, 颜色=mastery2color(掌握度), 大小=重要性(被依赖越多越大)
  // - 边:  有向箭头(→), 粗=依赖强度, 浅灰色
  // - 交互: 支持拖拽节点, 点击弹出 bottom sheet 显示详情
  // - mastery2color: >=0.8绿色, >=0.5黄色, >=0.3橙色, <0.3红色
}
```

#### 2. `lib/widgets/learning_progress_chart.dart`

```dart
/// 学习进度折线图
/// 
/// 技术: fl_chart LineChart
/// 参考: https://github.com/imaNNeo/fl_chart/blob/master/repo_files/documentations/line_chart.md
class LearningProgressChart extends StatelessWidget {
  final List<Map<String, dynamic>> skillHistories;
  // skillHistories[i] = {'skill': String, 'history': List<double>, 'days': List<String>}

  // 渲染要求:
  // - X轴: 时间 (最多显示 7 个刻度)
  // - Y轴: 掌握度 [0, 1], 刻度 0.0/0.25/0.5/0.75/1.0
  // - 每条线一种颜色 (最多 5 条线)
  // - 图例在底部
  // - 支持触摸查看数据点详情
  // - 0.8 处画一条虚线 (表示"已掌握"阈值)
}
```

#### 3. `lib/widgets/mastery_radar_chart.dart`

```dart
/// 掌握度雷达图
/// 
/// 技术: fl_chart RadarChart
/// 参考: https://github.com/imaNNeo/fl_chart/blob/master/repo_files/documentations/radar_chart.md
class MasteryRadarChart extends StatelessWidget {
  final Map<String, double> mastery;            // 当前掌握度
  final Map<String, double>? correctedMastery;   // LADL 修正后 (可选)

  // 渲染要求:
  // - 两个图层: 修正前(蓝色半透明) + 修正后(紫色虚线)
  // - 7个轴 (7个技能)
  // - 如果有差值 > 0.1 的节点, 用红色标记标注 "已修正"
  // - 支持点击轴标签查看技能详情
}
```

#### 4. `lib/widgets/learning_path_card.dart`

```dart
/// 学习路径推荐卡片
class LearningPathCard extends StatelessWidget {
  final LearningPathStep step;
  final VoidCallback? onTap;

  // 渲染要求:
  // - 左侧: 序号(1,2,3...) 大字体
  // - 中间: 技能名 + 优先级评分条形图
  // - 下方: 完成的先修技能(✅绿色) + 缺失的先修(❌红色)
  // - 右侧: 箭头图标  "→"
  // - 样式参考现有 Card 组件 (BorderRadius 20, 白底, 阴影)
}
```

### 开发顺序建议

| # | 任务 | 状态 |
|---|------|------|
| 1 | Flutter 环境 + fl_chart 调研 | 🔲 P0 |
| 2 | `kt_dependency_graph_widget.dart` | 🔲 P0 |
| 3 | `learning_progress_chart.dart` | 🔲 P1 |
| 4 | `mastery_radar_chart.dart` | 🔲 P1 |
| 5 | `learning_path_card.dart` | 🔲 P1 |

> 建议先做卡片（最简单），再做折线图和雷达图（fl_chart 文档清晰），最后做网络图（工作量大）。

### 每个组件独立测试方法

在 `main.dart` 临时替换 home 页面来单独调试你的组件：

```dart
// main.dart 中 runApp 之前，临时替换 home:
home: Scaffold(
  body: Center(
    child: KtDependencyGraphWidget(
      graph: mockGraph,
      masteryMap: mockSkills.fold({}, (m, s) => { ...m, s.id: s.mastery }),
    ),
  ),
)
```

这样不用等陈勇搏的页面写好就能看到效果。

---

## 协作流程

```
1. 罗洁在 GitHub 创建 Issues 分配任务
       │
2. 各人创建 feature 分支
   feature/cyb-kt-service
   feature/zzl-dependency-graph
   feature/rj-backend-api
       │
3. 本地开发 + 自测
       │
4. Push 分支 → 提 Pull Request
       │
5. 罗洁 Code Review → Merge
```

### Git 分支命名

```
feature/<名字缩写>-<功能>
fix/<名字缩写>-<bug描述>

例:
feature/cyb-kt-api-service
feature/zzl-radar-chart
fix/rj-backend-health-check
```

### 提交信息格式

```
<type>: <简短描述>

feat: 添加学习进度折线图组件
fix: 修复依赖网络图拖拽时坐标越界
```

### 标注约定

| 标注 | 含义 |
|------|------|
| `// TODO(ZL): ` | 张子麟待办 |
| `// TODO(CYB): ` | 陈勇搏待办 |
| `// TODO(RJ): ` | 罗洁待办 |
| `// FIXME: ` | 已知问题，需要修复 |

---

## 时间建议

| 周次 | 罗洁 | 陈勇搏 | 张子麟 |
|------|------|--------|--------|
| 第1周 | 后端完善 + 数据管线 | Service 层 + 数据模型 | 图表组件开发 |
| 第2周 | 后端测试 + 文档 | 页面开发 + Agent 集成 | 页面视觉 + 暗色模式 |
| 第3周 | 论文/PPT | 联调 + 苏格拉底集成 | 联调 + 动画/细节 |
| 第4周 | 答辩准备 + 演示 | Bug 修复 | Bug 修复 |

> 如果时间紧（赶答辩），压缩为 2 周：后端 3 天 + 前端 4 天 + 可视化 4 天 + 联调 3 天。后端已完成 80%，前端和可视化可并行开发。
