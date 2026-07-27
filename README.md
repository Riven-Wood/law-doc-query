# law-doc-query

> 律师法律资料查询 Skill —— 本地库 + 华宇元典 + ima 多源、法规/案例/理解适用多类型、强制溯源防幻觉。

面向 [WorkBuddy](https://www.codebuddy.cn/) 的法律资料查询技能。把分散在本地 Markdown 文档库、华宇元典（yuandian-mcp）、ima 知识库等多来源、多类型的法律资料统一成一个可溯源、防脑补的查询入口。

专为律师/法律工作者设计——律师场景最怕的不是"完全编造"，而是**一字之差意思相反**、**个案观点当普遍规则**、**已废止条文当现行**、**要旨当原文**。本 skill 围绕这几类风险构建。

---

## ✨ 特性

- **多类型自动识别**：规范性文件（normative）/ 裁判文书（case）/ 理解与适用（commentary）/ 其他，按文件特征启发式识别，也可用 frontmatter 显式标注。
- **多数据源路由**：本地库 → 华宇元典 → ima → 其他法律数据库（北大法宝/威科先行等），按优先级自动扩展，本地查到足够就不查外部。
- **12 道防幻觉关卡**：6 条通用约束 + 6 条外部源专用约束（字段类型/效力层级/效力状态/原文优先/未核对标注/跨源冲突）。
- **本地核对机制**：`verify` 子命令逐字比对 + 唯一性校验，套话重复不会被误判为"已核对"。
- **纯标准库、只读、无网络**：脚本仅用 Python 标准库，不写不删不联网，路径遍历已防护。
- **条文边界精确**：只认行首"第X条"并排除"规定/款/项/之"等引用后缀，正文内交叉引用不会截断条文。

---

## 🧠 工作原理

三层架构：

```
用户提问
   │
   ├─ ① 路由层（SKILL.md 提示词约束）
   │     按问题类型决策查哪里：
   │     法条/司法解释 → 本地 normative；本地无 → 华宇元典
   │     案例/裁判观点   → 本地 case；本地无 → 华宇元典
   │     理解与适用      → 本地 commentary + ima
   │     模糊问题        → 本地 search + 元典 + ima
   │
   ├─ ② 本地执行层（law_query.py，纯标准库、只读）
   │     7 个子命令：list / outline / search / article / case / read / verify
   │     全部输出 JSON，每条带 source=文件名:行号 便于溯源
   │     文件类型启发式识别 + 条文边界精确提取
   │
   └─ ③ 外部源层（MCP 连接器）
        华宇元典（yuandian-mcp）：法条原文 + 效力状态
        ima（ima-mcp）：理解与适用 / 个人收藏
        其他法律数据库：北大法宝 / 威科先行 等
```

### 12 道防幻觉关卡

| 类别 | 关卡 | 机制 |
|------|------|------|
| 通用 | ① 先查后答 | 禁止凭模型自身知识回答法条/裁判 |
| 通用 | ② 找不到就说找不到 | 工具未命中不补全 |
| 通用 | ③ 三类内容区分 | 法条原文 / 理解适用 / 裁判原文 分列 |
| 通用 | ④ 引用必经 verify | 本地 verify 逐字比对 + 唯一性（unique）校验 |
| 通用 | ⑤ 多源不混淆 | 本地/元典/ima/其他分别标注来源 |
| 通用 | ⑥ 分析标注性质 | agent 分析独立成段，不冒充原文 |
| 外部源 | ⑦ 字段类型标注 | 法条原文 / 裁判要旨 / 案件评析 / 摘要 区分 |
| 外部源 | ⑧ 案例效力层级标注 | 指导性 / 公报 / 普通案例 区分 |
| 外部源 | ⑨ 条文效力状态确认 | 现行有效 / 已废止 / 已修改 |
| 外部源 | ⑩ 原文优先 | 同时有原文和摘要时引原文 |
| 外部源 | ⑪ 无定位标注 | 摘要无原文定位标"未逐字核对" |
| 外部源 | ⑫ 跨源冲突处理 | 效力以专业库为准；已废止时本地降级为历史参考 |

---

## 📦 安装

### 方式一：作为 WorkBuddy Skill 安装

把本仓库放到 `~/.workbuddy/skills/law-doc-query/`：

```bash
git clone https://github.com/Riven-Wood/law-doc-query.git ~/.workbuddy/skills/law-doc-query
```

目录结构应为：
```
~/.workbuddy/skills/law-doc-query/
├── SKILL.md
├── README.md
└── scripts/
    └── law_query.py
```

### 方式二：仅用脚本（脱离 WorkBuddy 也可用）

`scripts/law_query.py` 是纯标准库的只读查询工具，可独立使用：

```bash
python3 scripts/law_query.py list
```

---

## 🔧 配置

### 本地文档库（两种方式任选其一）

- **方式 A（推荐）**：不设环境变量，在包含法律文档库的目录里直接运行——脚本以当前工作目录作为文档库。
- **方式 B（固定路径）**：设环境变量 `LAW_DOCS_DIR` 指向固定路径：
  ```bash
  echo 'export LAW_DOCS_DIR="/path/to/你的法律文档库"' >> ~/.zshrc
  ```

> ⚠️ 若用方式 A 且当前目录含非法律 md 文件，这些文件也会被纳入检索并可能被误分类。建议把法律文档单独放一个目录，或用方式 B 指定专用路径。

### 外部数据源（WorkBuddy 连接器）

在 WorkBuddy 的连接器管理中启用：

- **华宇元典**（yuandian-mcp）：法律法规/案例/裁判文书专业检索，条文效力状态可靠
- **ima 知识库**（ima-mcp）：个人收藏的理解与适用等资料
- **其他**：北大法宝（pkulaw）/ 威科先行（wk-workbuddy）等，按需启用

---

## 🚀 使用方法

### 1. 自然语言（WorkBuddy 内推荐）

在 WorkBuddy 任务区直接问，agent 自动识别意图、选择数据源：

- "帮我查民法典第143条" → 本地 normative；本地无 → 华宇元典
- "有没有不可抗力免责的案例" → 本地 case + 华宇元典
- "（2023）京01民终123号怎么判的" → 本地 case --case-no；本地无 → 元典
- "这条法律理解与适用怎么讲" → 本地 commentary + ima
- "这条规定现在还有效吗" → 华宇元典确认效力状态

### 2. 手动调用脚本（本地库）

```bash
SCRIPT=scripts/law_query.py

python3 $SCRIPT list                                    # 列出所有文档（含类型）
python3 $SCRIPT article 民法典 143                      # 取某法某条
python3 $SCRIPT case --case-no "（2023）京01民终123号"  # 按案号查裁判文书
python3 $SCRIPT case 案例-张三李四                       # 提取某文书结构
python3 $SCRIPT search 不可抗力 --type case --context 3 # 只在裁判文书里搜
python3 $SCRIPT search 民事行为能力 --type normative    # 只在法规里搜
python3 $SCRIPT outline 刑法                            # 看某法大纲
python3 $SCRIPT read 民法典.md --from 17 --to 23        # 读指定行段
python3 $SCRIPT verify 民法典.md --from 18 --to 22 --expect "行为人具有相应的民事行为能力"
```

### 子命令一览

| 子命令 | 作用 | 关键参数 |
|--------|------|---------|
| `list` | 列出所有文档（含类型、条文号、案号） | 无 |
| `outline` | 输出某文件大纲 | `<file>` |
| `search` | 跨文件关键词搜索（带上下文） | `<keyword> [--context N] [--type T]` |
| `article` | 精确取某法某条原文 | `<law_name> <article_no>` |
| `case` | 查询裁判文书（提取案号/本院认为/判决） | `<file>` 或 `--case-no <案号>` |
| `read` | 读取文件行段或章节 | `<file> [--from N] [--to M] [--section 标题]` |
| `verify` | 核对指定行段是否含某原文 | `<file> --from N --to M --expect 片段` |

所有子命令输出 JSON，`verify` 额外返回 `match_count` 与 `unique` 字段。

---

## ⚠️ 注意事项

1. **防幻觉约束是"软约束"**：12 道关卡写进 SKILL.md，由 LLM 自觉遵守。脚本层只能保证行号溯源与 verify 的布尔值，无法把"最终回答里的引用"与"一次真实 verify 调用"做密码学绑定。底线仍是模型的服从度。
2. **本地库配置**：未设 `LAW_DOCS_DIR` 时脚本回退到当前工作目录，会把 cwd 下所有 `.md`（含非法律文件）纳入检索。请把法律文档单独放一个目录或用环境变量指定。
3. **外部源字段需探测**：首次使用华宇元典/ima 等外部源前，应先做一次探测调用（如元典的 `yuandian_list_apis`）记录返回字段名与含义，再按实际字段类型标注，不得臆测——否则会把"裁判要旨"误当"裁判原文"。
4. **本地原文可能过期**：若外部源标记某条文"已修改/已废止"，即使本地有原文，本地也只作历史参考，引用须以外部源现行有效文本为准。
5. **条文识别依赖格式**：脚本靠"第X条"模式识别条文；若文档用其他格式（如纯阿拉伯数字无"条"字），需调整 `ARTICLE_START_RE`。
6. **非语义检索**：本地 `search` 是关键词精确子串匹配，非向量检索；库极大时召回率有限。
7. **仅支持 .md**：本地库仅识别 Markdown；docx/txt 需先转换。
8. **路径遍历已防护**：`resolve_file` 做了 basename 提取与 `relative_to` 校验，`../../../etc/passwd` 等攻击会被拦截。

---

## 📁 文件结构

```
law-doc-query/
├── SKILL.md              # 技能定义：多源路由 + 工作流 + 12 道防幻觉约束
├── README.md             # 本文件
├── LICENSE               # MIT
└── scripts/
    └── law_query.py      # 本地库查询工具（纯标准库，只读，7 个子命令）
```

---

## 📄 许可证

MIT，见 [LICENSE](./LICENSE)。
