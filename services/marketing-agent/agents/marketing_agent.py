"""
agents\marketing_agent.py
功能描述: 营销类Agent实现，个性化文案生成和营销时机判断
"""

from typing import Optional, Dict, Any, List

from .base_agent import BaseAgent, AgentType, IntentResult, AgentResponse
from .adapters import profile_adapter, knowledge_adapter, frequency_adapter
from agent_orchestrator.strategy_parser import strategy_loader
from common import llm_client, logger


class MarketingAgent(BaseAgent):
    def __init__(self):
        super().__init__(AgentType.MARKETING, "营销Agent")
        # 加权关键词：Dict[str, Dict[str, int]]
        # 注意：移除"申请"避免与service冲突；"需要/想要"降为低权重
        self._intent_keywords = {
            "interest": {"优惠": 3, "活动": 3, "权益": 2, "红包": 3, "折扣": 3, "券": 3, "省钱": 3, "福利": 3},
            "price": {"多少钱": 2, "价格": 2, "贵吗": 2},
            "compare": {"对比": 2, "哪个好": 2, "推荐": 2, "选择": 1},
            "need": {"需要": 1, "想要": 1, "想办": 1}
        }

        self._marketing_handlers = {
            "interest": self._handle_interest_request,
            "price": self._handle_price_query,
            "compare": self._handle_compare_request,
            "need": self._handle_need_request
        }

        self._trigger_keywords = [
            "分期", "额度", "办理", "申请", "优惠", "活动", 
            "权益", "划算", "省钱", "折扣", "利率", "费率"
        ]

    def process(self, message: str, oneid: Optional[str] = None, 
                context: Optional[Dict[str, Any]] = None) -> AgentResponse:
        intents = self.recognize_intent(message, context)
        
        should_recommend = self._should_recommend(message, oneid)
        
        if not intents:
            if should_recommend:
                content = self._generate_proactive_recommendation(oneid)
            else:
                content = "您好！请问有什么可以帮助您的？"
            response = self._format_response(content)
        else:
            primary_intent = intents[0]
            handler = self._marketing_handlers.get(primary_intent.intent_type)
            if handler:
                content = handler(message, oneid)
            else:
                content = self._handle_default(message, oneid, should_recommend)
            response = self._format_response(content, primary_intent)
        
        self.log_interaction(message, response)
        return response

    def _should_recommend(self, message: str, oneid: str) -> bool:
        for keyword in self._trigger_keywords:
            if keyword in message:
                break
        else:
            return False
        
        if oneid:
            profile = profile_adapter.get_profile(oneid)
            if profile:
                do_not_contact = profile.get("risk", {}).get("do_not_contact", False)
                marketing_consent = profile.get("consent", {}).get("marketing_consent", False)
                
                if do_not_contact or not marketing_consent:
                    logger.info(f"[频控] 营销推荐被拒绝: oneid={oneid}, do_not_contact={do_not_contact}, marketing_consent={marketing_consent}")
                    return False
            
            freq_result = frequency_adapter.check_frequency(oneid)
            if not freq_result.get("can_send", True):
                blocked_channels = freq_result.get("blocked_channels", [])
                logger.info(f"[频控] 营销推荐被拒绝: oneid={oneid}, blocked_channels={blocked_channels}")
                return False
            
            contact_count = freq_result.get("contact_count", {})
            logger.info(f"[频控] 营销推荐允许: oneid={oneid}, contact_count={contact_count}")
        
        return True

    def _generate_proactive_recommendation(self, oneid: str) -> str:
        profile = profile_adapter.get_profile(oneid)
        demographics = profile.get("demographics", {}) if profile else {}
        name = demographics.get("name", "客户")

        strategy = strategy_loader.load_latest()
        
        benefit = strategy.benefit_rule if strategy else None
        brief = strategy.content_brief if strategy else None
        
        if benefit and brief:
            return f"您好！{brief.core_message}。{benefit.benefit_name}已为您准备好，{benefit.limit}。立即领取享受优惠吧！"
        
        return f"您好！我们有多种优惠活动正在进行中，请问您想了解哪方面的优惠？"

    def _generate_personalized_content(self, oneid: str, strategy_data: Dict[str, Any]) -> str:
        profile = profile_adapter.get_profile(oneid)
        demographics = profile.get("demographics", {}) if profile else {}
        name = demographics.get("name", "客户")
        city = demographics.get("city", "")
        
        benefit_type = strategy_data.get("benefit_type", "")
        benefit_name = strategy_data.get("benefit_name", "")
        core_message = strategy_data.get("core_message", "")
        
        return f"【{core_message}】\n您好！{benefit_name}已为您准备好！活动规则以页面展示为准。"

    def _handle_interest_request(self, message: str, oneid: str) -> str:
        profile = profile_adapter.get_profile(oneid)
        demographics = profile.get("demographics", {}) if profile else {}
        name = demographics.get("name", "客户")
        
        try:
            strategy = strategy_loader.load_latest()
            benefit = strategy.benefit_rule if strategy else None

            if benefit:
                return f"您好！{benefit.benefit_name}正在进行中，{benefit.limit}。立即领取享受优惠吧！"
        except Exception:
            pass
        
        activities = knowledge_adapter.search_benefits("活动")
        if activities:
            activity_list = "\n".join([f"- {a['name']}: {a['description']}" for a in activities])
            return f"您好！以下是当前热门活动：\n{activity_list}"
        
        return f"您好！我们有多种优惠活动正在进行中，请问您想了解哪方面的优惠？"

    def _handle_price_query(self, message: str, oneid: str) -> str:
        profile = profile_adapter.get_profile(oneid)
        demographics = profile.get("demographics", {}) if profile else {}
        name = demographics.get("name", "客户")
        
        if "分期" in message or "费率" in message:
            return f"您好！账单分期费率低至0.45%/期，具体以页面展示为准。现在办理还可享受手续费折扣优惠！"
        
        elif "年费" in message:
            products = knowledge_adapter.search_products("年费")
            if products:
                product_list = "\n".join([f"- {p['name']}: 年费{p['annual_fee']}元/年" for p in products])
                return f"您好！\n{product_list}"
        
        return f"您好！具体价格请以页面展示为准，我们会为您推荐最优惠的方案。"

    def _handle_compare_request(self, message: str, oneid: str) -> str:
        profile = profile_adapter.get_profile(oneid)
        demographics = profile.get("demographics", {}) if profile else {}
        name = demographics.get("name", "客户")
        
        products = knowledge_adapter.search_products(message)
        if products:
            product_info = "\n".join([
                f"- {p['name']}: {p['description']}，年费{p['annual_fee']}元/年" 
                for p in products
            ])
            return f"您好！根据您的需求，为您推荐以下产品：\n{product_info}\n您想了解哪一款的详细信息？"
        
        return f"您好！请问您想对比什么产品？我可以为您详细介绍。"

    def _handle_need_request(self, message: str, oneid: str) -> str:
        profile = profile_adapter.get_profile(oneid)
        demographics = profile.get("demographics", {}) if profile else {}
        name = demographics.get("name", "客户")
        
        if "分期" in message:
            return f"您好！办理账单分期非常简单，费率低至0.45%/期。现在办理还可享受手续费折扣优惠！请问您需要办理几期？"
        
        elif "额度" in message:
            return f"您好！提升额度有助于您更好地规划消费。使用信用卡满6个月后即可申请调额，系统会根据您的用卡情况综合评估。"
        
        return f"您好！请问您想办理什么业务？我可以帮您详细介绍。"

    def _handle_default(self, message: str, oneid: str, should_recommend: bool) -> str:
        if should_recommend:
            return self._generate_proactive_recommendation(oneid)
        return "您好！请问有什么可以帮助您的？"

    def generate_push_content(self, oneid: str, channel: str = "push") -> str:
        profile = profile_adapter.get_profile(oneid)
        demographics = profile.get("demographics", {}) if profile else {}
        name = demographics.get("name", "客户")

        try:
            strategy = strategy_loader.load_latest()
            benefit = strategy.benefit_rule if strategy else None
            brief = strategy.content_brief if strategy else None
            
            if benefit and brief:
                content = f"【{brief.core_message}】\n{name}您好！{benefit.benefit_name}已为您准备好！\n活动规则以页面展示为准。"
            else:
                content = f"{name}您好！我们为您准备了专属优惠，快来看看吧！"
        except Exception:
            content = f"{name}您好！我们为您准备了专属优惠，快来看看吧！"
        
        return content


marketing_agent = MarketingAgent()