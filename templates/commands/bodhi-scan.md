扫描指定目录，为存量代码补充 Bodhi DSL 标注。按以下顺序执行：

## 参数

$ARGUMENTS 是要扫描的目标，格式为以下之一：
- `init` — 初始化 .bodhi/ 目录（第一次使用时执行）
- 目录路径 — 扫描该目录下的源代码，补充 @bodhi.* inline tags
- `flows` — 从已有的 inline tags 生成 .bodhi/flows/*.yaml
- `concepts` — 从已有的 states 和 flows 生成 .bodhi/concepts/glossary.yaml

## 执行规则

### 如果参数是 `init`

1. 读取项目构建文件（pom.xml / build.gradle / package.json / go.mod / pyproject.toml）确定语言和框架
2. 创建 `.bodhi/bodhi.yaml`，填写 project name、languages、frameworks
3. 扫描 ORM 模型 / 数据库 migration / DDL 文件，为每个表创建 `.bodhi/entities/<table>.yaml`
4. 扫描状态枚举（如 OrderStatus、PaymentState），为有状态流转的实体创建 `.bodhi/states/<name>.yaml`
5. 优先处理核心业务表（外键关联最多的、代码中引用最多的），不需要一次做完所有表

### 如果参数是目录路径

1. 找到该目录下所有源代码文件中的 public 方法/函数（跳过 getter/setter/toString/构造函数/测试代码）
2. 先列出要处理的方法清单，等用户确认后再修改
3. 按照 CLAUDE.md 中的 Bodhi DSL 规范，在每个方法的 doc comment 中补充 @bodhi.* 标签：
   - 必须补：`@bodhi.intent` + `@bodhi.reads` + `@bodhi.writes`
   - 有关键调用补 `@bodhi.calls`
   - 有事件发布补 `@bodhi.emits`
   - 有错误处理补 `@bodhi.on_fail`
4. 如果 `.bodhi/entities/` 已存在，对照其中的字段名确保 reads/writes 标签准确

### 如果参数是 `flows`

1. 扫描所有 Controller / Handler / Router 文件，找到所有 HTTP/gRPC/MQ 入口
2. 对每个入口，根据代码中的 `@bodhi.calls` 标签追踪调用链
3. 为每个入口创建 `.bodhi/flows/<name>.yaml`
4. 优先处理 POST/PUT/DELETE 接口（有写操作的）
5. 先列出入口清单，等用户确认优先级后再生成

### 如果参数是 `concepts`

1. 阅读 `.bodhi/states/` 和 `.bodhi/flows/` 中的内容
2. 提取关键业务术语（状态含义、业务动作、领域概念）
3. 创建或更新 `.bodhi/concepts/glossary.yaml`
