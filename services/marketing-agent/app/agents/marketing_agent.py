"""
营销 Agent 编排。
基于 LangGraph 构建状态机，串联意图识别、内容生成、合规校验等节点。
"""

import logging
from typing import TypedDict, Literal, Dict, Any, Optional
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app.models.strategy import StrategyPackage
from app.services.content_gen import content_generator
from app.services.frequency import frequency_service, FrequencyLimitExceeded

logger = logging.getLogger(__name__)


# ==================== State 定义 ====================

class AgentState(TypedDict):
    """Agent 状态机的状态结构"""
    campaign_id: str
    customer_id: str
    customer_profile: Dict[str, Any]
    strategy: Optional[StrategyPackage]
    intent: Literal["marketing", "query", "service", "unknown"]
    generated_content: Optional[str]
    compliance_passed: Optional[bool]
    final_response: Optional[str]
    error_message: Optional[str]


# ==================== Node 实现 ====================

class MarketingAgent:
    """
    营销 Agent。
    基于 LangGraph 的状态机，处理多轮对话和营销触达决策。
    """

    def __init__(self):
        self.graph = self._build_graph()

    def _identify_intent(self, state: AgentState) -> AgentState:
        """
        意图识别节点。
        根据客户输入判断意图类型：营销响应 / 查询 / 服务 / 未知。
        """
        # MVP 阶段使用简单规则匹配，后续可替换为 LLM 分类
        customer_profile = state.get("customer_profile", {})
        last_message = customer_profile.get("last_message", "").lower()

        intent = "unknown"
        if any(kw in last_message for kw in ["分期", "优惠", "办理", "申请"]):
            intent = "marketing"
        elif any(kw in last_message for kw in ["费率", "利息", "费用", "多少钱"]):
            intent = "query"
        elif any(kw in last_message for kw in ["还款", "账单", "额度", "密码"]):
            intent = "service"

        logger.info(f"意图识别结果 | customer_id={state['customer_id']} | intent={intent}")
        state["intent"] = intent
        return state

    async def _generate_content(self, state: AgentState) -> AgentState:
        """
        内容生成节点。
        调用 ContentGenerator 生成个性化文案。
        """
        if state["intent"] != "marketing" or not state.get("strategy"):
            logger.debug(f"非营销意图或无策略包，跳过内容生成 | intent={state['intent']}")
            return state

        try:
            content = await content_generator.generate(
                strategy=state["strategy"],
                customer_profile=state["customer_profile"],
            )
            state["generated_content"] = content
            logger.info(f"Agent 内容生成完成 | campaign_id={state['campaign_id']}")
        except Exception as e:
            state["error_message"] = f"内容生成失败: {str(e)}"
            logger.error(f"内容生成异常 | error={e}")

        return state

    async def _compliance_check(self, state: AgentState) -> AgentState:
        """
        合规校验节点。
        检查生成内容是否包含禁用词或违规承诺。
        """
        content = state.get("generated_content")
        if not content:
            state["compliance_passed"] = True
            return state

        compliance = state["strategy"].compliance_guard if state.get("strategy") else None
        if not compliance:
            state["compliance_passed"] = True
            return state

        # 检查禁用词
        for word in compliance.blocked_words:
            if word in content:
                state["compliance_passed"] = False
                state["error_message"] = f"内容包含禁用词: {word}"
                logger.warning(f"合规校验失败（禁用词）| campaign_id={state['campaign_id']} | word={word}")
                return state

        # 检查禁止承诺
        for claim in compliance.must_not_claim:
            if claim in content:
                state["compliance_passed"] = False
                state["error_message"] = f"内容包含禁止承诺: {claim}"
                logger.warning(f"合规校验失败（禁止承诺）| campaign_id={state['campaign_id']} | claim={claim}")
                return state

        state["compliance_passed"] = True
        logger.info(f"合规校验通过 | campaign_id={state['campaign_id']}")
        return state

    def _format_response(self, state: AgentState) -> AgentState:
        """
        响应格式化节点。
        根据状态生成最终响应。
        """
        if state.get("error_message"):
            state["final_response"] = f"抱歉，暂时无法处理您的请求。错误信息：{state['error_message']}"
            return state

        intent = state.get("intent", "unknown")

        if intent == "marketing" and state.get("generated_content") and state.get("compliance_passed"):
            state["final_response"] = state["generated_content"]

        elif intent == "query":
            # 查询类意图的简单响应（后续可接入知识库）
            state["final_response"] = self._handle_query_intent(state["customer_profile"].get("last_message", ""))

        elif intent == "service":
            # 服务类意图的简单响应（后续可接入服务网关）
            state["final_response"] = self._handle_service_intent(state["customer_profile"].get("last_message", ""))

        else:
            state["final_response"] = "您好，我是您的智能助手。请问有什么可以帮您？"

        return state

    def _handle_query_intent(self, message: str) -> str:
        """处理查询类意图"""
        if "费率" in message:
            return "分期费率根据期数不同有所差异，3期约0.65%/期，6期约0.60%/期，12期约0.55%/期。具体以申请页面展示为准。"
        elif "利息" in message:
            return "分期手续费按期收取，不额外收取利息。提前还款时，已收取的手续费不予退还。"
        else:
            return "关于您咨询的问题，建议您查看App内的产品详情页，或联系在线客服获取详细解答。"

    def _handle_service_intent(self, message: str) -> str:
        """处理服务类意图"""
        if "还款" in message:
            return "您可以通过App首页的\"还款\"入口进行还款操作，支持全额还款和最低还款。"
        elif "账单" in message:
            return "您可以在App的\"我的账单\"页面查看本期账单详情。"
        else:
            return "您可以在App内完成大部分服务操作，如需人工帮助，请拨打客服热线。"

    def _route_after_intent(self, state: AgentState) -> Literal["generate_content", "format_response"]:
        """意图识别后的路由：营销意图进入内容生成，其他直接进入响应格式化"""
        if state["intent"] == "marketing":
            return "generate_content"
        return "format_response"

    def _route_after_compliance(self, state: AgentState) -> Literal["format_response", "format_response"]:
        """合规校验后的路由：无论通过与否，都进入响应格式化"""
        return "format_response"

    def _build_graph(self) -> StateGraph:
        """构建 LangGraph 状态机"""
        graph = StateGraph(AgentState)

        # 添加节点
        graph.add_node("intent_node", self._identify_intent)
        graph.add_node("generate_content", self._generate_content)
        graph.add_node("compliance_node", self._compliance_check)
        graph.add_node("format_response", self._format_response)

        # 设置入口
        graph.set_entry_point("intent_node")

        # 添加边
        graph.add_conditional_edges(
            "intent_node",
            self._route_after_intent,
            {
                "generate_content": "generate_content",
                "format_response": "format_response",
            },
        )
        graph.add_edge("generate_content", "compliance_node")
        graph.add_edge("compliance_node", "format_response")
        graph.add_edge("format_response", END)

        # 编译图（使用 MemorySaver 作为检查点存储）
        memory = MemorySaver()
        compiled_graph = graph.compile(checkpointer=memory)

        return compiled_graph

    async def run(
        self,
        campaign_id: str,
        customer_id: str,
        customer_profile: Dict[str, Any],
        strategy: Optional[StrategyPackage] = None,
        thread_id: str = "default",
    ) -> Dict[str, Any]:
        """
        运行 Agent。

        Args:
            campaign_id: 活动 ID
            customer_id: 客户 ID
            customer_profile: 客户画像
            strategy: 策略包（营销意图时必传）
            thread_id: 对话线程 ID（用于多轮对话状态保持）

        Returns:
            包含最终响应和完整状态信息的字典
        """
        initial_state = AgentState(
            campaign_id=campaign_id,
            customer_id=customer_id,
            customer_profile=customer_profile,
            strategy=strategy,
            intent="unknown",
            generated_content=None,
            compliance_passed=None,
            final_response=None,
            error_message=None,
        )

        config = {"configurable": {"thread_id": thread_id}}

        try:
            # 异步执行状态机
            final_state = await self.graph.ainvoke(initial_state, config=config)

            logger.info(
                f"Agent 执行完成 | campaign_id={campaign_id} | customer_id={customer_id} | "
                f"intent={final_state['intent']} | final_response={final_state['final_response'][:50]}..."
            )

            return {
                "success": True,
                "response": final_state["final_response"],
                "state": final_state,
            }

        except Exception as e:
            logger.error(f"Agent 执行异常 | error={e}")
            return {
                "success": False,
                "response": "抱歉，系统暂时不可用，请稍后再试。",
                "error": str(e),
            }


# 全局单例
marketing_agent = MarketingAgent()