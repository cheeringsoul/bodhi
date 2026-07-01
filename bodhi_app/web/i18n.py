"""Bodhi Web Dashboard i18n — lightweight translation support."""

from __future__ import annotations

TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        # Nav
        "nav.overview": "Overview",
        "nav.dashboard": "Dashboard",
        "nav.project_overview": "Project Overview",
        "nav.full_graph": "Full Graph",
        "nav.knowledge": "Knowledge",
        "nav.flows": "Flows",
        "nav.entities": "Entities",
        "nav.services": "Services",
        "nav.events": "Events",
        "nav.state_machines": "State Machines",

        # Dashboard
        "dash.title": "Dashboard",
        "dash.subtitle": "AI-friendliness overview for {project}",
        "dash.score_title": "AI Friendliness Score",
        "dash.score_explain": "Measures how well your codebase's Bodhi annotations enable AI to understand call chains, data flows, and error handling.",
        "dash.dimensions_title": "Score Dimensions",
        "dash.tag_coverage_title": "Tag Coverage ({count} tagged functions)",
        "dash.tag_coverage_subtitle": "How many functions in your codebase carry each type of @bodhi.* annotation.",

        # Dimensions
        "dim.intent_coverage": "Intent coverage",
        "dim.intent_coverage_desc": "How many tagged functions declare @bodhi.intent — without intent, AI doesn't know what a function does.",
        "dim.dataflow": "Data-flow completeness",
        "dim.dataflow_desc": "How many intent-bearing functions also declare @bodhi.reads / @bodhi.writes — missing data flow means AI can't trace which tables are affected.",
        "dim.error_handling": "Error handling",
        "dim.error_handling_desc": "How many functions with writes or remote calls declare @bodhi.on_fail — without this, failure modes are invisible to AI.",
        "dim.call_chain": "Call-chain traceability",
        "dim.call_chain_desc": "How many @bodhi.calls targets resolve to tagged functions — broken links mean AI loses the trace mid-chain.",
        "dim.structural": "Structural health",
        "dim.structural_desc": "Penalties for method overloading, dangling implementations, and other patterns that break Bodhi's ClassName.methodName identity model.",

        # Tags
        "tag.intent": "Declares what the function does in business terms",
        "tag.reads": "Which database tables / data sources the function reads from",
        "tag.writes": "Which database tables / data sources the function writes to",
        "tag.calls": "Which other functions this function invokes (local or remote)",
        "tag.emits": "Which domain events this function publishes",
        "tag.on_fail": "What happens when this function fails",

        # Summary cards
        "card.flows": "Flows",
        "card.flows_desc": "request-to-response chains",
        "card.entities": "Entities",
        "card.entities_desc": "database tables",
        "card.services": "Services",
        "card.services_desc": "microservices",
        "card.events": "Events",
        "card.events_desc": "domain events",

        # Flows page
        "flows.title": "Flows",
        "flows.subtitle": "Request-to-response call chains defined in .bodhi/flows/",
        "flows.col_name": "Name",
        "flows.col_entry": "Entry",
        "flows.col_auth": "Auth",
        "flows.col_steps": "Steps",
        "flows.col_entities": "Entities",
        "flows.col_events": "Events",

        # Flow detail
        "flow.entry_point": "Entry Point",
        "flow.steps": "Steps",
        "flow.diagram": "Flow Diagram",
        "flow.no_diagram": "No diagram available",
        "flow.related": "Related Flows",
        "flow.not_found": "Flow not found",

        # Entities page
        "entities.title": "Entities",
        "entities.subtitle": "Database table semantics defined in .bodhi/entities/",
        "entities.col_field": "Field",
        "entities.col_type": "Type",
        "entities.col_flags": "Flags",
        "entities.relations": "Relations",
        "entities.fields": "fields",
        "entities.relations_count": "relations",

        # Entity detail
        "entity.schema": "Schema",
        "entity.reads": "Reads",
        "entity.writes": "Writes",
        "entity.col_function": "Function",
        "entity.col_context": "Context",
        "entity.col_detail": "Detail",
        "entity.no_reads": "No reads found",
        "entity.no_writes": "No writes found",

        # Services page
        "services.title": "Services",
        "services.subtitle": "Service topology defined in .bodhi/services/",
        "services.topology": "Service Topology",
        "services.apis": "APIs",
        "services.dependencies": "Dependencies",
        "services.depended_by": "Depended By",

        # Events page
        "events.title": "Events",
        "events.subtitle": "Domain events and their producers/consumers",
        "events.producers": "Producers",
        "events.consumers": "Consumers",

        # States page
        "states.title": "State Machines",
        "states.subtitle": "State lifecycle definitions from .bodhi/states/",

        # Graph page
        "graph.title": "All Flows",
        "graph.subtitle": "Mermaid diagram of all flows with entity and event relationships",
        "graph.group_hint": "Flows are grouped to keep each diagram render-safe. Pick a group to view its call graph.",
        "graph.empty": "No flows found in .bodhi/flows/.",
        "graph.mode_simple": "Simplified",
        "graph.mode_detailed": "Detailed",
        "graph.hint_simple": "Each endpoint linked to the data it reads/writes, events it emits, and external services it calls. Pick a module tab to switch groups.",
        "graph.hint_detailed": "Full internal call chain for each flow. Denser — use for tracing a single request end to end.",

        # Project overview page
        "overview.title": "Project Overview",
        "overview.subtitle": "Bird's-eye view: entry points → flows → storage / events / externals",
        "overview.entry_points": "Entry Points",
        "overview.flows": "Flows",
        "overview.storage": "Storage",
        "overview.events": "Events",
        "overview.externals": "Externals",
    },

    "zh": {
        # Nav
        "nav.overview": "概览",
        "nav.dashboard": "仪表盘",
        "nav.project_overview": "项目鸟瞰",
        "nav.full_graph": "全局图",
        "nav.knowledge": "知识库",
        "nav.flows": "调用流",
        "nav.entities": "数据实体",
        "nav.services": "服务",
        "nav.events": "事件",
        "nav.state_machines": "状态机",

        # Dashboard
        "dash.title": "仪表盘",
        "dash.subtitle": "{project} 的 AI 友好度概览",
        "dash.score_title": "AI 友好度评分",
        "dash.score_explain": "衡量代码中 Bodhi 标注的完整度——标注越完整，AI 越能理解调用链、数据流和错误处理。",
        "dash.dimensions_title": "评分维度",
        "dash.tag_coverage_title": "标注覆盖率（{count} 个已标注函数）",
        "dash.tag_coverage_subtitle": "代码中各类 @bodhi.* 标注的使用情况。",

        # Dimensions
        "dim.intent_coverage": "意图覆盖",
        "dim.intent_coverage_desc": "有多少被标注的函数声明了 @bodhi.intent——没有意图声明，AI 无法知道函数做什么。",
        "dim.dataflow": "数据流完整性",
        "dim.dataflow_desc": "有意图的函数中有多少声明了 @bodhi.reads / @bodhi.writes——缺少数据流意味着 AI 无法追踪受影响的表。",
        "dim.error_handling": "错误处理",
        "dim.error_handling_desc": "写库或远程调用的函数中有多少声明了 @bodhi.on_fail——没有这个，失败模式对 AI 不可见。",
        "dim.call_chain": "调用链可追踪性",
        "dim.call_chain_desc": "有多少 @bodhi.calls 的目标函数也有标注——断链意味着 AI 在中途丢失追踪。",
        "dim.structural": "结构健康度",
        "dim.structural_desc": "方法重载、悬挂实现等违反 Bodhi ClassName.methodName 唯一标识约定的问题扣分。",

        # Tags
        "tag.intent": "声明函数的业务用途",
        "tag.reads": "函数读取的数据库表 / 数据源",
        "tag.writes": "函数写入的数据库表 / 数据源",
        "tag.calls": "函数调用的其他函数（本地或远程）",
        "tag.emits": "函数发布的领域事件",
        "tag.on_fail": "函数失败时的处理方式",

        # Summary cards
        "card.flows": "调用流",
        "card.flows_desc": "请求到响应的调用链",
        "card.entities": "数据实体",
        "card.entities_desc": "数据库表",
        "card.services": "服务",
        "card.services_desc": "微服务",
        "card.events": "事件",
        "card.events_desc": "领域事件",

        # Flows page
        "flows.title": "调用流",
        "flows.subtitle": "在 .bodhi/flows/ 中定义的请求-响应调用链",
        "flows.col_name": "名称",
        "flows.col_entry": "入口",
        "flows.col_auth": "认证",
        "flows.col_steps": "步骤",
        "flows.col_entities": "实体",
        "flows.col_events": "事件",

        # Flow detail
        "flow.entry_point": "入口",
        "flow.steps": "步骤",
        "flow.diagram": "流程图",
        "flow.no_diagram": "暂无图表",
        "flow.related": "关联流",
        "flow.not_found": "未找到该调用流",

        # Entities page
        "entities.title": "数据实体",
        "entities.subtitle": "在 .bodhi/entities/ 中定义的数据库表语义",
        "entities.col_field": "字段",
        "entities.col_type": "类型",
        "entities.col_flags": "标记",
        "entities.relations": "关联",
        "entities.fields": "个字段",
        "entities.relations_count": "个关联",

        # Entity detail
        "entity.schema": "表结构",
        "entity.reads": "读取",
        "entity.writes": "写入",
        "entity.col_function": "函数",
        "entity.col_context": "上下文",
        "entity.col_detail": "详情",
        "entity.no_reads": "暂无读取记录",
        "entity.no_writes": "暂无写入记录",

        # Services page
        "services.title": "服务",
        "services.subtitle": "在 .bodhi/services/ 中定义的服务拓扑",
        "services.topology": "服务拓扑",
        "services.apis": "接口",
        "services.dependencies": "依赖",
        "services.depended_by": "被依赖",

        # Events page
        "events.title": "事件",
        "events.subtitle": "领域事件及其生产者/消费者",
        "events.producers": "生产者",
        "events.consumers": "消费者",

        # States page
        "states.title": "状态机",
        "states.subtitle": "在 .bodhi/states/ 中定义的状态生命周期",

        # Graph page
        "graph.title": "全局图",
        "graph.subtitle": "所有调用流及实体、事件关系的 Mermaid 图",
        "graph.group_hint": "流程已分组，以保证每张图都能正常渲染。选择一个分组查看其调用图。",
        "graph.empty": "在 .bodhi/flows/ 中未找到任何流程。",
        "graph.mode_simple": "简化视图",
        "graph.mode_detailed": "详细视图",
        "graph.hint_simple": "每个接口连到它读写的数据表、发出的事件和调用的外部服务。点击模块标签切换分组。",
        "graph.hint_detailed": "每条流程的完整内部调用链。更密集，适合端到端追踪单个请求。",

        # Project overview page
        "overview.title": "项目鸟瞰",
        "overview.subtitle": "入口 → 调用流 → 存储 / 事件 / 外部依赖",
        "overview.entry_points": "入口点",
        "overview.flows": "调用流",
        "overview.storage": "存储",
        "overview.events": "事件",
        "overview.externals": "外部依赖",
    },
}

SUPPORTED_LANGS = list(TRANSLATIONS.keys())
DEFAULT_LANG = "en"


def get_translations(lang: str) -> dict[str, str]:
    return TRANSLATIONS.get(lang, TRANSLATIONS[DEFAULT_LANG])
