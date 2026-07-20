"""
agents\service_agent.py
功能描述: 服务类Agent实现，采用RAG架构，检索知识库并生成答复
"""

from typing import Optional, Dict, Any, List

from .base_agent import BaseAgent, AgentType, IntentResult, AgentResponse
from .adapters import knowledge_adapter, profile_adapter


class ServiceAgent(BaseAgent):
    def __init__(self):
        super().__init__(AgentType.SERVICE, "服务Agent")
        # 加权关键词：Dict[str, Dict[str, int]]
        self._intent_keywords = {
            "business": {"办理": 3, "开通": 3, "申请": 2, "激活": 3, "注销": 3},
            "complaint": {"投诉": 3, "问题": 2, "错误": 2, "异常": 2, "失败": 2},
            "consult": {"咨询": 2, "了解": 2, "怎么样": 2, "如何": 1, "怎么": 1},
            "help": {"帮助": 2, "指导": 2, "教程": 2, "步骤": 2}
        }

        self._service_handlers = {
            "business": self._handle_business_request,
            "complaint": self._handle_complaint,
            "consult": self._handle_consultation,
            "help": self._handle_help_request
        }

    def process(self, message: str, oneid: Optional[str] = None, 
                context: Optional[Dict[str, Any]] = None) -> AgentResponse:
        intents = self.recognize_intent(message, context)
        
        if not intents:
            content = "请问您需要什么服务？我可以帮您办理业务、解答疑问。"
            response = self._format_response(content)
        else:
            primary_intent = intents[0]
            handler = self._service_handlers.get(primary_intent.intent_type)
            if handler:
                content = handler(message, oneid)
            else:
                content = self._handle_default(message)
            response = self._format_response(content, primary_intent)
        
        self.log_interaction(message, response)
        return response

    def _retrieve_knowledge(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        results = knowledge_adapter.search(query, top_k)
        return results

    def _generate_response(self, query: str, knowledge_results: List[Dict[str, Any]]) -> str:
        if not knowledge_results:
            return "抱歉，我暂时无法找到相关信息，请换一种方式提问。"
        
        main_result = knowledge_results[0]
        category = main_result.get("category", "")
        
        if category == "faq":
            return main_result.get("answer", "")
        elif category == "benefit_catalog":
            return f"{main_result.get('name', '')}: {main_result.get('description', '')}"
        elif category == "product_catalog":
            return f"{main_result.get('name', '')}: {main_result.get('description', '')}，年费{main_result.get('annual_fee', 0)}元/年"
        elif category == "activity_rules":
            return f"{main_result.get('name', '')}: {main_result.get('description', '')}，有效期至{main_result.get('valid_period', '')}"
        
        return main_result.get("description", "") or main_result.get("answer", "")

    def _handle_business_request(self, message: str, oneid: str) -> str:
        demographics = profile_adapter.get_demographics(oneid)
        name = demographics.get("name", "客户") if demographics else "客户"
        
        knowledge = self._retrieve_knowledge(message)
        
        if "分期" in message:
            if knowledge:
                base_response = self._generate_response(message, knowledge)
                return f"您好！{base_response} 请问您需要办理几期分期？"
            return f"您好！办理账单分期非常简单，登录手机银行APP，进入\"分期\"页面，选择账单分期，按照提示操作即可完成办理。"
        
        elif "额度" in message:
            if knowledge:
                return f"您好！{self._generate_response(message, knowledge)}"
            return f"您好！使用信用卡满6个月后，可通过手机银行APP申请调额，系统会根据您的用卡情况综合评估。"
        
        elif "激活" in message:
            return f"您好！您可以通过手机银行APP或拨打客服热线激活信用卡。"
        
        elif "注销" in message:
            return f"您好！如需注销卡片，请确保账户无欠款后，拨打客服热线申请注销。"
        
        else:
            if knowledge:
                return f"您好！{self._generate_response(message, knowledge)}"
            return f"您好！请问您想办理什么业务？我可以帮您办理分期、调额等业务。"

    def _handle_complaint(self, message: str, oneid: str) -> str:
        demographics = profile_adapter.get_demographics(oneid)
        name = demographics.get("name", "客户") if demographics else "客户"
        
        if "失败" in message or "错误" in message:
            return f"您好！非常抱歉给您带来不便，请告诉我具体情况，我会尽力为您处理。"
        
        elif "投诉" in message:
            return f"您好！感谢您的反馈，我们非常重视您的意见，请详细描述您的问题，我会记录并跟进处理。"
        
        else:
            return f"您好！非常抱歉给您带来不好的体验，请告诉我具体遇到了什么问题，我会尽力帮助您解决。"

    def _handle_consultation(self, message: str, oneid: str) -> str:
        demographics = profile_adapter.get_demographics(oneid)
        name = demographics.get("name", "客户") if demographics else "客户"
        
        knowledge = self._retrieve_knowledge(message)
        
        if knowledge:
            return f"您好！{self._generate_response(message, knowledge)}"
        
        if "年费" in message:
            return f"您好！白金卡年费1800元/年，金卡年费300元/年，普卡免年费。年费在卡片激活后首个账单日收取。"
        
        elif "权益" in message:
            benefits = knowledge_adapter.search_benefits("权益")
            if benefits:
                benefit_list = "\n".join([f"- {b['name']}: {b['description']}" for b in benefits])
                return f"您好！以下是您可能感兴趣的权益：\n{benefit_list}"
        
        return f"您好！请详细描述您想了解的问题，我会尽力为您解答。"

    def _handle_help_request(self, message: str, oneid: str) -> str:
        demographics = profile_adapter.get_demographics(oneid)
        name = demographics.get("name", "客户") if demographics else "客户"
        
        knowledge = self._retrieve_knowledge(message)
        
        if knowledge:
            return f"您好！{self._generate_response(message, knowledge)}"
        
        return f"您好！请问有什么可以帮助您的？我可以协助您办理业务、查询信息。"

    def _handle_default(self, message: str) -> str:
        knowledge = self._retrieve_knowledge(message)
        if knowledge:
            return self._generate_response(message, knowledge)
        return "请问您需要什么服务？我可以帮您办理各类业务。"


service_agent = ServiceAgent()