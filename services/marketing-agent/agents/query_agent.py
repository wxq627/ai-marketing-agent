"""
agents\query_agent.py
功能描述: 查询类Agent实现，秒级响应标准化事实查询
"""

from typing import Optional, Dict, Any, List

from .base_agent import BaseAgent, AgentType, IntentResult, AgentResponse
from .adapters import profile_adapter


class QueryAgent(BaseAgent):
    def __init__(self):
        super().__init__(AgentType.QUERY, "查询Agent")
        # 加权关键词：Dict[str, Dict[str, int]]
        self._intent_keywords = {
            "bill": {"账单": 3, "应还": 2, "还款": 2, "账单日": 3, "还款日": 3, "欠款": 3, "余额": 3},
            "credit": {"额度": 3, "可用": 2, "授信": 2, "信用额度": 3},
            "interest": {"利息": 3, "利率": 3, "费率": 2, "手续费": 2},
            "points": {"积分": 3, "积分兑换": 3},
            "account": {"账户": 2, "卡号": 3, "卡片": 2, "开户行": 3}
        }

        self._query_handlers = {
            "bill": self._handle_bill_query,
            "credit": self._handle_credit_query,
            "interest": self._handle_interest_query,
            "points": self._handle_points_query,
            "account": self._handle_account_query
        }

    def process(self, message: str, oneid: Optional[str] = None, 
                context: Optional[Dict[str, Any]] = None) -> AgentResponse:
        intents = self.recognize_intent(message, context)
        
        if not intents:
            content = "请问您想查询什么信息？我可以帮您查询账单、额度、利息等信息。"
            response = self._format_response(content)
        else:
            primary_intent = intents[0]
            handler = self._query_handlers.get(primary_intent.intent_type)
            if handler:
                content = handler(message, oneid)
            else:
                content = self._handle_default(message)
            response = self._format_response(content, primary_intent)
        
        self.log_interaction(message, response)
        return response

    def _handle_bill_query(self, message: str, oneid: str) -> str:
        billing = profile_adapter.get_billing_info(oneid)
        demographics = profile_adapter.get_demographics(oneid)
        
        if billing and demographics:
            name = demographics.get("name", "客户")
            bill_amount = billing.get("bill_amount", 0)
            bill_date = billing.get("bill_date", "")
            due_date = billing.get("due_date", "")
            
            if "应还" in message or "金额" in message:
                return f"您好！您本期账单应还金额为￥{bill_amount:,.2f}。"
            elif "账单日" in message:
                return f"您的账单日为{bill_date}。"
            elif "还款" in message or "还款日" in message:
                return f"您的还款日为{due_date}，请及时还款避免逾期。"
            else:
                return f"您好！您本期账单应还金额为￥{bill_amount:,.2f}，账单日为{bill_date}，还款日为{due_date}。"
        
        return "抱歉，暂时无法查询您的账单信息，请稍后再试。"

    def _handle_credit_query(self, message: str, oneid: str) -> str:
        account = profile_adapter.get_account_info(oneid)
        demographics = profile_adapter.get_demographics(oneid)
        
        if account and demographics:
            name = demographics.get("name", "客户")
            total_credit = account.get("total_credit_amount", 0)
            used_amount = account.get("used_amount", 0)
            available = total_credit - used_amount
            
            if "可用" in message or "剩余" in message:
                return f"您好！您当前可用额度为￥{available:,.2f}。"
            elif "总" in message or "授信" in message:
                return f"您的总授信额度为￥{total_credit:,.2f}。"
            else:
                return f"您好！您当前可用额度为￥{available:,.2f}，总授信额度￥{total_credit:,.2f}。"
        
        return "抱歉，暂时无法查询您的额度信息，请稍后再试。"

    def _handle_interest_query(self, message: str, oneid: str) -> str:
        demographics = profile_adapter.get_demographics(oneid)
        
        if demographics:
            name = demographics.get("name", "客户")
            
            if "分期" in message or "手续费" in message:
                return f"您好！账单分期费率低至0.45%/期，具体以页面展示为准。"
            elif "利息" in message or "利率" in message:
                return f"信用卡透支利息按日利率0.05%计算，按月计收复利。"
            else:
                return f"您好！信用卡透支利息按日利率0.05%计算，账单分期费率低至0.45%/期。"
        
        return "抱歉，暂时无法查询利率信息，请稍后再试。"

    def _handle_points_query(self, message: str, oneid: str) -> str:
        demographics = profile_adapter.get_demographics(oneid)
        
        if demographics:
            name = demographics.get("name", "客户")
            
            if "兑换" in message:
                return f"您好！积分可兑换航空里程、酒店住宿、礼品等，具体请登录积分商城查看。"
            else:
                return f"您好！您可以通过日常消费累积积分，积分可用于兑换各类权益。"
        
        return "抱歉，暂时无法查询积分信息，请稍后再试。"

    def _handle_account_query(self, message: str, oneid: str) -> str:
        account = profile_adapter.get_account_info(oneid)
        demographics = profile_adapter.get_demographics(oneid)
        
        if account and demographics:
            name = demographics.get("name", "客户")
            card_level = account.get("primary_card_level", "")
            product_name = account.get("product_name", "")
            
            if "卡片" in message or "卡" in message:
                return f"您好！您持有{card_level}，产品名称为{product_name}。"
            else:
                return f"您好！您的账户状态正常，持有{card_level}。"
        
        return "抱歉，暂时无法查询账户信息，请稍后再试。"

    def _handle_default(self, message: str) -> str:
        return "请问您想查询什么信息？我可以帮您查询账单、额度、利息、积分等信息。"


query_agent = QueryAgent()