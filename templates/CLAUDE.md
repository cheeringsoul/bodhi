# Bodhi DSL — 代码与 DSL 同步生成规范

当你在本项目中写代码时，**必须同时维护 Bodhi DSL**。DSL 分两层，都要写。

---

## Layer 1: Inline Tags（每写/改一个函数都要做）

在函数/方法的 doc comment 中添加 `@bodhi.*` 标签。

### 必须添加的标签

| 标签 | 何时添加 | 说明 |
|------|----------|------|
| `@bodhi.intent` | **每个函数都要** | 一句话业务意图，用业务语言，不复述代码 |
| `@bodhi.reads` | 有读取数据时 | 声明读了什么：`request.body(fields)`, `table(fields)`, `cache:key(fields)` |
| `@bodhi.writes` | 有写入数据时 | 声明写了什么：`table(fields) via INSERT/UPDATE/DELETE`, `response(code, fields)` |
| `@bodhi.calls` | 有关键调用时 | 只列业务关键调用，格式 `ClassName.method [via protocol]`。远程调用加 `via http:POST /path` 或 `via grpc` |
| `@bodhi.emits` | 有事件发布时 | `event_name(payload_fields) [to destination]`，不要遗漏 MQ/EventBus/WebSocket |
| `@bodhi.consumes` | 有事件消费时 | `event_name(payload_fields) [from source]`，标注函数由什么事件触发 |
| `@bodhi.on_fail` | 有错误处理时 | `condition → action`，action 可链式：`retry 3 → reject 500`。支持 `circuit_breaker(...)`, `degrade(...)` 等微服务容错模式 |

### 可选标签（有就加）

- `@bodhi.auth required\|public\|required(role=X)`
- `@bodhi.validate <rule>`
- `@bodhi.log.success "<pattern>"`
- `@bodhi.log.error "<pattern>" [severity=level]`
- `@bodhi.metric <name> [threshold]`
- `@bodhi.idempotent key=<fields>`
- `@bodhi.ratelimit <rate> per <scope>`

### 语言适配

**Java/Kotlin/TypeScript**: 写在 `/** */` JSDoc/Javadoc 中
**Python**: 写在 `"""` docstring 中
**Go**: 写在 `//` 行注释中

### 示例

```java
/**
 * @bodhi.intent 创建订单，扣减库存，发布领域事件
 * @bodhi.reads request.body(userId, items, address)
 * @bodhi.writes orders(id, userId, totalAmount, status=PENDING) via INSERT
 * @bodhi.calls InventoryService.deduct via grpc:InventoryService/Deduct
 * @bodhi.calls PaymentService.hold via http:POST /api/payments/hold
 * @bodhi.emits order_created(orderId, userId) to kafka:order-events
 * @bodhi.on_fail inventory_insufficient → reject 400
 * @bodhi.on_fail payment_timeout → circuit_breaker(threshold=5, window=60s) → reject 503
 */
public OrderResponse create(CreateOrderRequest req) { ... }
```

---

## Layer 2: System Files（结构性变更时要做）

当代码变更涉及以下情况时，必须同步更新 `.bodhi/` 目录下的 YAML 文件。

### 触发规则

| 你做了什么 | 需要更新什么 |
|-----------|-------------|
| 新增/修改 HTTP 接口或请求处理链路 | `.bodhi/flows/<flow_name>.yaml` |
| 新增/修改数据库表、ORM 模型 | `.bodhi/entities/<table_name>.yaml` |
| 新增/修改状态枚举或状态流转逻辑 | `.bodhi/states/<state_machine_name>.yaml` |
| 新增/修改事件（MQ、EventBus 消息） | `.bodhi/events/<event_name>.yaml` |
| 新增/修改微服务间调用或依赖关系 | `.bodhi/services/<service_name>.yaml` |
| 引入新的业务术语或概念 | `.bodhi/concepts/glossary.yaml` |
| 项目初始化或框架变更 | `.bodhi/bodhi.yaml` |

### Flow 文件 — `.bodhi/flows/<name>.yaml`

当你写了一个 API 接口或完整的请求处理链路时，创建或更新对应 flow：

```yaml
name: create_order
description: 用户下单完整流程

entry:
  type: http          # http | grpc | mq_consumer | scheduler | websocket
  method: POST
  path: /api/orders
  auth: required(role=USER)

steps:
  - fn: OrderController.create
    intent: 接收请求，参数校验，编排创建流程
    reads:
      - request.body(userId, items, address)
    calls:
      - InventoryService.deduct
      - OrderRepository.save
      - EventPublisher.publish
    on_fail:
      - validation_failed → reject 400

  - fn: InventoryService.deduct
    intent: 扣减商品库存
    reads:
      - inventory(productId, stock)
    writes:
      - inventory(stock) via UPDATE
    on_fail:
      - inventory_insufficient → reject 400

  - fn: OrderRepository.save
    intent: 持久化订单到数据库
    writes:
      - orders(id, userId, totalAmount, status=PENDING) via INSERT
    on_fail:
      - db_write_failed → retry 2 → throw

  - fn: EventPublisher.publish
    intent: 发布订单创建领域事件
    emits:
      - order_created(orderId, userId) to kafka:order-events

error_handling:
  - condition: inventory_insufficient
    step: InventoryService.deduct
    action: reject 400
  - condition: db_write_failed
    step: OrderRepository.save
    action: retry 2 → rollback inventory → reject 500

related_flows:
  - cancel_order
  - get_order_detail

entities:
  - orders
  - inventory

events:
  - order_created
```

### Entity 文件 — `.bodhi/entities/<table>.yaml`

当你创建或修改数据库表/ORM 模型时：

```yaml
table: orders
description: 核心订单表
database: mongodb          # mysql | postgresql | mongodb | redis

fields:
  - name: id
    type: bigint
    description: 订单主键
    primary_key: true
  - name: status
    type: int
    description: 订单状态
    state_machine: order_lifecycle    # 有状态流转就关联状态机
    enum:
      0: INIT
      1: PAID
      3: SHIPPED
      4: COMPLETED
      5: CANCELLED
  - name: phone
    type: string
    description: 用户联系电话
    sensitive: true                   # PII 敏感数据标记

indexes:
  - name: idx_user_status
    fields: [user_id, status]
    description: 用户订单列表查询

relations:
  - target: order_items
    type: one_to_many
    join: orders.id = order_items.order_id
  - target: users
    type: many_to_one
    join: orders.user_id = users.id
```

### State Machine 文件 — `.bodhi/states/<name>.yaml`

当你实现状态流转逻辑（枚举 + 转换方法）时：

```yaml
name: order_lifecycle
entity: orders
field: status
description: 订单生命周期

states:
  - id: INIT
    value: 0
    description: 等待支付
    transitions:
      - target: PAID
        trigger: event(payment_success)
        fn: PaymentCallback.onSuccess
      - target: CANCELLED
        trigger: timeout(30m)
        fn: OrderScheduler.cancelExpired

  - id: PAID
    value: 1
    description: 已支付
    transitions:
      - target: SHIPPED
        trigger: event(shipment_created)
        fn: ShipmentCallback.onShipped

  - id: COMPLETED
    value: 4
    description: 订单完成
    terminal: true

  - id: CANCELLED
    value: 5
    description: 已取消
    terminal: true
    side_effects:
      - rollback inventory
      - refund if paid
```

### Service 文件 — `.bodhi/services/<service_name>.yaml`

仅微服务/分布式架构需要。当你新增服务间调用或修改服务依赖时：

```yaml
name: order-service
description: 订单核心服务
port: 8080
tech_stack: [spring-boot, mysql, kafka]

apis:
  - method: POST
    path: /api/orders
    flow: create_order
    description: 创建订单

depends_on:
  - service: payment-service
    protocol: http
    apis:
      - POST /api/payments/hold
      - POST /api/payments/charge
    resilience:
      timeout: 3s
      retry: 2
      circuit_breaker: threshold=5, window=60s

  - service: kafka
    type: mq
    topics: [order-events]
```

### Event 文件 — `.bodhi/events/<event_name>.yaml`

当你实现了事件的发布或消费逻辑时（Kafka、RabbitMQ、EventBus 等），创建或更新对应 event：

```yaml
name: order_created
description: 订单创建后发布的领域事件
channel: kafka:order-events

schema:
  - field: orderId
    type: string
    description: 订单ID
  - field: userId
    type: string
    description: 用户ID
  - field: totalAmount
    type: decimal
    description: 订单总金额

producers:
  - fn: OrderService.create
    flow: create_order

consumers:
  - fn: NotificationHandler.onOrderCreated
    flow: send_order_notification
    description: 发送订单通知给用户
```

### Concept 文件 — `.bodhi/concepts/glossary.yaml`

当代码中出现业务术语时（尤其是状态判断、业务规则）：

```yaml
concepts:
  - term: 成交
    definition: 订单状态从 PAID 变为 COMPLETED，表示交易已全部完成
    related_states: [PAID, COMPLETED]
    related_flows: [create_order, confirm_delivery]

  - term: 锁库存
    definition: 下单时预扣库存数量，防止超卖
    related_fields: [inventory.stock, inventory.locked_stock]
    related_flows: [create_order, cancel_order]
```

### Project 元信息 — `.bodhi/bodhi.yaml`

项目初始化时创建一次：

```yaml
version: "0.1.0"
project:
  name: "your-project-name"
  description: "项目描述"
  languages: [java]
  frameworks: [spring-boot, mybatis]

inline:
  java: javadoc
  python: docstring
  go: line_comment
  typescript: jsdoc
```

---

## 判断规则

**不确定要不要写 DSL？用这个决策树：**

1. 你写了一个函数吗？→ 加 Layer 1 inline tags
2. 这个函数是 API 入口 / 请求处理链的一部分吗？→ 更新 `.bodhi/flows/`
3. 你建了新表或改了表结构吗？→ 更新 `.bodhi/entities/`
4. 你实现了状态枚举或状态转换吗？→ 更新 `.bodhi/states/`
5. 你实现了事件发布或消费吗？→ 更新 `.bodhi/events/`
6. 你新增了微服务间调用或依赖吗？→ 更新 `.bodhi/services/`
7. 你引入了新的业务术语吗？→ 更新 `.bodhi/concepts/`

**什么不需要写 DSL：**
- 纯工具函数（format, log wrapper, string utils）
- 简单 getter/setter
- 测试代码
- 配置类/启动类
