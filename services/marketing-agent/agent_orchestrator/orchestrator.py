"""agent_orchestrator\orchestrator.py
功能描述: LangGraph调度中枢，实现多Agent协作状态机工作流
"""

import uuid
from typing import Optional, Dict, Any, List, Callable
from enum import Enum
from datetime import datetime

from common import logger, StrategyError, ComplianceError, AgentError, ChannelError

from .schemas import StrategyPackage, ExecutionPlan, DispatchResult
from .strategy_parser import strategy_loader, compliance_checker, strategy_executor
from .session_manager import SessionManager, SessionContext, SentimentType, session_manager
from agents import query_agent, service_agent, marketing_agent, AgentType
from agents.adapters import profile_adapter
from agents.intent_classifier import intent_classifier
from feedback_collector.collector import feedback_collector
from feedback_collector.data_reflow import data_reflow_queue


class WorkflowState(str, Enum):
    INIT = "init"
    COMPLIANCE_CHECK = "compliance_check"
    GENERATE_CONTENT = "generate_content"
    DISPATCH = "dispatch"
    INTERACT = "interact"
    FEEDBACK = "feedback"
    END = "end"


class WorkflowStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class OrchestratorState:
    def __init__(self):
        self.session_id: Optional[str] = None
        self.oneid: Optional[str] = None
        self.strategy: Optional[StrategyPackage] = None
        self.execution_plan: Optional[ExecutionPlan] = None
        self.current_state: WorkflowState = WorkflowState.INIT
        self.workflow_status: WorkflowStatus = WorkflowStatus.RUNNING
        self.generated_content: Optional[str] = None
        self.dispatch_results: List[DispatchResult] = []
        self.user_response: Optional[str] = None
        self.agent_response: Optional[str] = None
        self.feedback_collected: bool = False
        self.error_message: Optional[str] = None
        self.metadata: Dict[str, Any] = {}
        self.interaction_type: Optional[str] = None
        self.interaction_channel: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "oneid": self.oneid,
            "current_state": self.current_state.value,
            "workflow_status": self.workflow_status.value,
            "generated_content": self.generated_content,
            "dispatch_results": [dr.model_dump() for dr in self.dispatch_results],
            "user_response": self.user_response,
            "agent_response": self.agent_response,
            "feedback_collected": self.feedback_collected,
            "error_message": self.error_message,
            "metadata": self.metadata,
            "interaction_type": self.interaction_type,
            "interaction_channel": self.interaction_channel
        }


class Node:
    def __init__(self, name: str, handler: Callable):
        self.name = name
        self.handler = handler

    def __call__(self, state: OrchestratorState) -> OrchestratorState:
        try:
            logger.info(f"执行节点: {self.name}")
            return self.handler(state)
        except Exception as e:
            logger.error(f"节点执行失败 {self.name}: {e}")
            state.workflow_status = WorkflowStatus.FAILED
            state.error_message = str(e)
            return state


class Edge:
    def __init__(self, source: str, target: str, condition: Optional[Callable] = None):
        self.source = source
        self.target = target
        self.condition = condition or (lambda state: True)

    def can_transition(self, state: OrchestratorState) -> bool:
        return self.condition(state)


class Orchestrator:
    def __init__(self):
        self._nodes: Dict[str, Node] = {}
        self._edges: List[Edge] = []
        self._state_cache: Dict[str, OrchestratorState] = {}
        self._session_manager: SessionManager = session_manager
        self._register_default_nodes()
        self._register_default_edges()

    def _register_default_nodes(self):
        self._nodes["init"] = Node("init", self._init_node)
        self._nodes["compliance_check"] = Node("compliance_check", self._compliance_check_node)
        self._nodes["generate_content"] = Node("generate_content", self._generate_content_node)
        self._nodes["dispatch"] = Node("dispatch", self._dispatch_node)
        self._nodes["interact"] = Node("interact", self._interact_node)
        self._nodes["feedback"] = Node("feedback", self._feedback_node)
        self._nodes["end"] = Node("end", self._end_node)

    def _register_default_edges(self):
        self._edges.append(Edge("init", "compliance_check"))
        self._edges.append(Edge("compliance_check", "generate_content", 
                                lambda s: s.workflow_status == WorkflowStatus.RUNNING))
        self._edges.append(Edge("compliance_check", "end", 
                                lambda s: s.workflow_status != WorkflowStatus.RUNNING))
        self._edges.append(Edge("generate_content", "dispatch",
                                lambda s: s.generated_content and s.workflow_status == WorkflowStatus.RUNNING))
        self._edges.append(Edge("generate_content", "end",
                                lambda s: not s.generated_content or s.workflow_status != WorkflowStatus.RUNNING))
        self._edges.append(Edge("dispatch", "interact",
                                lambda s: s.dispatch_results and s.workflow_status == WorkflowStatus.RUNNING))
        self._edges.append(Edge("dispatch", "end",
                                lambda s: not s.dispatch_results or s.workflow_status != WorkflowStatus.RUNNING))
        self._edges.append(Edge("interact", "feedback",
                                lambda s: s.workflow_status == WorkflowStatus.RUNNING))
        self._edges.append(Edge("interact", "end",
                                lambda s: s.workflow_status != WorkflowStatus.RUNNING))
        self._edges.append(Edge("feedback", "interact",
                                lambda s: s.workflow_status == WorkflowStatus.RUNNING))
        self._edges.append(Edge("feedback", "end",
                                lambda s: s.workflow_status != WorkflowStatus.RUNNING))
        self._edges.append(Edge("end", "end"))

    def register_node(self, name: str, handler: Callable):
        self._nodes[name] = Node(name, handler)

    def register_edge(self, source: str, target: str, condition: Optional[Callable] = None):
        self._edges.append(Edge(source, target, condition))

    def _init_node(self, state: OrchestratorState) -> OrchestratorState:
        try:
            strategy = strategy_loader.load_latest()
            state.strategy = strategy
            state.execution_plan = strategy_executor._generate_execution_plan(strategy)
            
            if not state.session_id:
                session = self._session_manager.create_session(state.oneid, strategy.campaign_metadata.campaign_id)
                state.session_id = session.session_id
            
            logger.info(f"初始化完成: campaign_id={strategy.campaign_metadata.campaign_id}, session_id={state.session_id}")
        except Exception as e:
            logger.error(f"初始化失败: {e}")
            state.workflow_status = WorkflowStatus.FAILED
            state.error_message = f"初始化失败: {e}"
        
        return state

    def _compliance_check_node(self, state: OrchestratorState) -> OrchestratorState:
        if not state.strategy:
            state.workflow_status = WorkflowStatus.FAILED
            state.error_message = "策略包未加载"
            return state

        try:
            user_age = 28
            if state.oneid:
                profile = profile_adapter.get_profile(state.oneid)
                if profile:
                    user_age = profile.get("demographics", {}).get("age", 28)
            
            if not compliance_checker.check_age_restriction(state.strategy, user_age):
                raise ComplianceError(f"用户年龄不符合要求: {user_age}")
            
            logger.info(f"合规预检通过: user_age={user_age}")
        except ComplianceError as e:
            logger.error(f"合规校验失败: {e}")
            state.workflow_status = WorkflowStatus.FAILED
            state.error_message = str(e)
        
        return state

    def _generate_content_node(self, state: OrchestratorState) -> OrchestratorState:
        if not state.strategy:
            state.workflow_status = WorkflowStatus.FAILED
            state.error_message = "策略包未加载"
            return state

        try:
            content = marketing_agent.generate_push_content(state.oneid)
            
            if not compliance_checker.check_sensitive_words(content, state.strategy):
                raise ComplianceError("文案包含敏感词")
            
            state.generated_content = content
            logger.info(f"内容生成完成: {content[:50]}...")
        except ComplianceError as e:
            logger.error(f"内容合规校验失败: {e}")
            state.workflow_status = WorkflowStatus.FAILED
            state.error_message = str(e)
        except Exception as e:
            logger.error(f"内容生成失败: {e}")
            state.workflow_status = WorkflowStatus.FAILED
            state.error_message = str(e)
        
        return state

    def _dispatch_node(self, state: OrchestratorState) -> OrchestratorState:
        if not state.strategy or not state.generated_content:
            state.workflow_status = WorkflowStatus.FAILED
            state.error_message = "策略包或内容未准备"
            return state

        try:
            from channel_gateway.channel_gateway import ChannelGateway
            
            gateway = ChannelGateway()
            for route in state.strategy.channel_routing:
                result = gateway.dispatch(
                    user_id=state.oneid,
                    channel=route.channel,
                    content=state.generated_content,
                    trace_id=state.execution_plan.trace_id if state.execution_plan else str(uuid.uuid4())
                )
                state.dispatch_results.append(result)
                logger.info(f"渠道分发: channel={route.channel}, success={result.success}")

                if result.success:
                    feedback_collector.collect_event(
                        trace_id=state.execution_plan.trace_id if state.execution_plan else str(uuid.uuid4()),
                        oneid=state.oneid,
                        event_type="impression",
                        campaign_id=state.strategy.campaign_metadata.campaign_id,
                        channel=route.channel,
                        detail={
                            "content_id": result.content_id if hasattr(result, 'content_id') else "",
                            "message": state.generated_content[:50]
                        }
                    )
                    
                    reflow_data = {
                        "oneid": state.oneid,
                        "event_type": "impression",
                        "campaign_id": state.strategy.campaign_metadata.campaign_id,
                        "channel": route.channel,
                        "timestamp": datetime.now().isoformat(),
                        "detail": {
                            "content_id": result.content_id if hasattr(result, 'content_id') else "",
                            "message": state.generated_content[:50]
                        }
                    }
                    data_reflow_queue.enqueue("marketing_agent", "project_one", reflow_data)
                    data_reflow_queue.process_next()

        except Exception as e:
            logger.error(f"渠道分发失败: {e}")
            state.workflow_status = WorkflowStatus.FAILED
            state.error_message = str(e)
        
        return state

    def _interact_node(self, state: OrchestratorState) -> OrchestratorState:
        try:
            if state.user_response:
                session = self._session_manager.get_session(state.session_id)
                session.add_message("user", state.user_response)
                
                agent_response, agent_type, intent_result = self._route_to_agent(state)
                state.agent_response = agent_response
                
                session.add_message("agent", agent_response)
                
                # 记录本轮意图到会话上下文（供下一轮使用）
                if intent_result:
                    session.last_agent_type = agent_type
                    session.last_intent_type = intent_result.intent_type
                    session.last_intent_score = intent_result.score
                
                sentiment = self._analyze_sentiment(state.user_response)
                session.update_sentiment(sentiment)
                
                self._session_manager.save_session(session)
                
                logger.info(f"交互完成: user_response={state.user_response[:30]}, agent_response={agent_response[:30]}, agent_type={agent_type}, intent={intent_result.intent_type if intent_result else 'N/A'}")
        except Exception as e:
            logger.error(f"交互节点失败: {e}")
            state.workflow_status = WorkflowStatus.FAILED
            state.error_message = str(e)
        
        return state

    def _route_to_agent(self, state: OrchestratorState) -> tuple:
        """
        层级化路由：
        1. 第一层：使用IntentClassifier识别大类（带上下文记忆）
        2. 第二层：路由到对应Agent，Agent内部做细类识别
        3. 返回: (response_content, agent_type, intent_result)
        """
        user_message = state.user_response
        
        # 获取会话上下文（上一轮意图信息）
        session = self._session_manager.get_session(state.session_id)
        context = {
            "last_agent_type": session.last_agent_type,
            "last_intent_type": session.last_intent_type,
            "last_intent_score": session.last_intent_score,
            "recent_messages": session.messages[-3:] if session.messages else []
        }
        
        # 第一层：大类分类（加权关键词 + 上下文记忆）
        category, score, confidence = intent_classifier.classify(user_message, context)
        
        # 第二层：路由到对应Agent（传入context用于细类识别的上下文增强）
        agent_map = {
            "query": query_agent,
            "service": service_agent,
            "marketing": marketing_agent
        }
        agent = agent_map.get(category, marketing_agent)
        
        # 调用Agent.process（内部会做第二层细类识别）
        response = agent.process(user_message, state.oneid, context)
        
        logger.info(f"[路由] category={category}, score={score}, confidence={confidence}, agent={agent.name}")
        
        return response.content, category, response.intent

    def _analyze_sentiment(self, message: str) -> SentimentType:
        negative_words = ["不好", "不行", "问题", "错误", "失败", "投诉", "麻烦", "糟", "差"]
        positive_words = ["好", "不错", "满意", "谢谢", "感谢", "棒", "赞"]
        
        negative_count = sum(1 for word in negative_words if word in message)
        positive_count = sum(1 for word in positive_words if word in message)
        
        if negative_count > positive_count:
            return SentimentType.NEGATIVE
        elif positive_count > negative_count:
            return SentimentType.POSITIVE
        else:
            return SentimentType.NEUTRAL

    def _feedback_node(self, state: OrchestratorState) -> OrchestratorState:
        try:
            state.feedback_collected = True
            
            session = self._session_manager.get_session(state.session_id)
            sentiment = session.sentiment
            
            event_type = state.interaction_type or "interaction"
            
            feedback_data = {
                "session_id": state.session_id,
                "oneid": state.oneid,
                "campaign_id": state.strategy.campaign_metadata.campaign_id if state.strategy else None,
                "sentiment": sentiment.value,
                "round_count": session.current_round,
                "feedback_type": event_type,
                "timestamp": datetime.now().isoformat()
            }
            
            logger.info(f"反馈采集完成: {feedback_data}")

            if state.interaction_type in ["user_click", "user_reject"]:
                detail = {
                    "sentiment": sentiment.value,
                    "round_count": session.current_round,
                    "session_id": state.session_id,
                    "interaction_type": state.interaction_type,
                    "channel": state.interaction_channel,
                    "user_response": state.user_response[:50] if state.user_response else "",
                    "agent_response": state.agent_response[:50] if state.agent_response else ""
                }

                feedback_collector.collect_event(
                    trace_id=state.execution_plan.trace_id if state.execution_plan else str(uuid.uuid4()),
                    oneid=state.oneid,
                    event_type=event_type,
                    campaign_id=state.strategy.campaign_metadata.campaign_id if state.strategy else None,
                    channel=state.interaction_channel,
                    detail=detail
                )
                
                reflow_data = {
                    "oneid": state.oneid,
                    "event_type": event_type,
                    "campaign_id": state.strategy.campaign_metadata.campaign_id if state.strategy else "",
                    "channel": state.interaction_channel,
                    "timestamp": datetime.now().isoformat(),
                    "detail": detail
                }
                data_reflow_queue.enqueue("marketing_agent", "project_one", reflow_data)
                data_reflow_queue.process_next()

        except Exception as e:
            logger.error(f"反馈采集失败: {e}")
            state.workflow_status = WorkflowStatus.FAILED
            state.error_message = str(e)
        
        return state

    def _end_node(self, state: OrchestratorState) -> OrchestratorState:
        try:
            state.current_state = WorkflowState.END
            
            if state.workflow_status == WorkflowStatus.RUNNING:
                state.workflow_status = WorkflowStatus.COMPLETED
            
            if state.session_id:
                session = self._session_manager.get_session(state.session_id)
                session.end()
                self._session_manager.save_session(session)

                from feedback_collector.summarizer import conversation_summarizer

                session_messages = session.messages if hasattr(session, 'messages') else []
                
                conversation_summary = conversation_summarizer.generate_summary(
                    conversation_id=state.session_id,
                    session_id=state.session_id,
                    oneid=state.oneid,
                    messages=session_messages
                )

                conversation_event = {
                    "oneid": state.oneid,
                    "event_type": "conversation",
                    "campaign_id": state.strategy.campaign_metadata.campaign_id if state.strategy else "",
                    "timestamp": datetime.now().isoformat(),
                    "detail": {
                        "conversation_id": state.session_id,
                        "summary": conversation_summary.summary,
                        "intent": conversation_summary.intent,
                        "sentiment": conversation_summary.sentiment,
                        "top_concerns": conversation_summary.top_concerns,
                        "round_count": session.current_round
                    }
                }
                data_reflow_queue.enqueue("marketing_agent", "project_one", conversation_event)
                data_reflow_queue.process_next()

                campaign_id = state.strategy.campaign_metadata.campaign_id if state.strategy else ""
                campaign_feedback = feedback_collector.get_campaign_feedback(campaign_id)
                if campaign_feedback:
                    campaign_feedback_data = campaign_feedback.model_dump()
                    campaign_feedback_data["session_id"] = state.session_id
                    campaign_feedback_data["oneid"] = state.oneid
                    campaign_feedback_data["timestamp"] = datetime.now().isoformat()
                    data_reflow_queue.enqueue("marketing_agent", "project_two", campaign_feedback_data)
                    data_reflow_queue.process_next()
            
            logger.info(f"工作流结束: session_id={state.session_id}, status={state.workflow_status}")
        except Exception as e:
            logger.error(f"结束节点失败: {e}")
        
        return state

    def _get_next_state(self, current_state_name: str, state: OrchestratorState) -> str:
        for edge in self._edges:
            if edge.source == current_state_name and edge.can_transition(state):
                return edge.target
        return "end"

    def start_workflow(self, oneid: str, session_id: Optional[str] = None) -> OrchestratorState:
        state = OrchestratorState()
        state.oneid = oneid
        state.session_id = session_id
        
        initial_key = state.session_id or str(uuid.uuid4())
        self._state_cache[initial_key] = state
        
        state = self.run_until_interact(state)
        
        if state.session_id and state.session_id != initial_key:
            del self._state_cache[initial_key]
            self._state_cache[state.session_id] = state
        
        return state

    def run_until_interact(self, state: OrchestratorState) -> OrchestratorState:
        state.current_state = WorkflowState.INIT
        
        while state.current_state != WorkflowState.INTERACT and state.workflow_status == WorkflowStatus.RUNNING:
            node_name = state.current_state.value
            if node_name in self._nodes:
                state = self._nodes[node_name](state)
            next_node = self._get_next_state(node_name, state)
            state.current_state = WorkflowState(next_node)
        
        return state

    def continue_workflow(self, session_id: str, user_response: str) -> OrchestratorState:
        if session_id not in self._state_cache:
            raise AgentError(f"工作流状态不存在: {session_id}")
        
        state = self._state_cache[session_id]
        state.user_response = user_response
        
        if state.current_state == WorkflowState.INTERACT:
            node_name = state.current_state.value
            if node_name in self._nodes:
                state = self._nodes[node_name](state)
            next_node = self._get_next_state(node_name, state)
            state.current_state = WorkflowState(next_node)
        
        while state.current_state != WorkflowState.INTERACT and state.workflow_status == WorkflowStatus.RUNNING:
            node_name = state.current_state.value
            if node_name in self._nodes:
                state = self._nodes[node_name](state)
            next_node = self._get_next_state(node_name, state)
            state.current_state = WorkflowState(next_node)
        
        self._state_cache[session_id] = state
        return state

    def get_workflow_state(self, session_id: str) -> Optional[OrchestratorState]:
        return self._state_cache.get(session_id)

    def end_workflow(self, session_id: str):
        if session_id in self._state_cache:
            state = self._state_cache[session_id]
            state = self._nodes["end"](state)
            del self._state_cache[session_id]


orchestrator = Orchestrator()