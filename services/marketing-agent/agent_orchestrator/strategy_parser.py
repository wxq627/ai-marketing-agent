"""
agent_orchestrator\strategy_parser.py
功能描述: 策略包加载器和解析器，支持从本地Mock文件或HTTP远程接口加载策略
"""

import json
import uuid
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

from .schemas import StrategyPackage, ExecutionPlan
from common import logger, StrategyError, StrategyValidationError, StrategyNotFoundError

DEFAULT_STRATEGY_MOCK_FILE = Path(__file__).parent.parent / "contracts/examples/strategy_package_example.json"


class StrategyLoader:
    def __init__(self, mock_file: Optional[str] = None):
        self._mock_file = mock_file or str(DEFAULT_STRATEGY_MOCK_FILE)
        self._cache: Dict[str, StrategyPackage] = {}
        # 按保存顺序记录的 campaign_id 列表，用于查找最新策略
        self._latest_campaign_id: Optional[str] = None

    def load_from_file(self, file_path: Optional[str] = None) -> StrategyPackage:
        path = Path(file_path or self._mock_file)
        if not path.exists():
            raise StrategyNotFoundError(f"策略包文件不存在: {path}")

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return self._validate_and_parse(data)
        except json.JSONDecodeError as e:
            raise StrategyValidationError(f"策略包JSON格式错误: {str(e)}")
        except Exception as e:
            raise StrategyError(f"加载策略包失败: {str(e)}")

    def load_from_api(self, url: str) -> StrategyPackage:
        try:
            import httpx
            with httpx.Client(timeout=10) as client:
                response = client.get(url)
                response.raise_for_status()
                data = response.json()
            return self._validate_and_parse(data)
        except ImportError:
            raise StrategyError("需要安装httpx库来调用远程API")
        except Exception as e:
            raise StrategyError(f"从API加载策略包失败: {str(e)}")

    def load_by_campaign_id(self, campaign_id: str) -> Optional[StrategyPackage]:
        if campaign_id in self._cache:
            return self._cache[campaign_id]

        try:
            strategy = self.load_from_file()
            if strategy.campaign_metadata.campaign_id == campaign_id:
                self._cache[campaign_id] = strategy
                return strategy
            return None
        except StrategyNotFoundError:
            return None

    def load_latest(self, auto_generate: bool = True) -> StrategyPackage:
        """
        优先读取已保存的最新策略包（来自 strategy_agent 推送或 generate 接口）；
        若无且 auto_generate=True，则自动调用 strategy_agent 生成默认策略；
        都失败则回退到 mock 文件。
        """
        if self._latest_campaign_id and self._latest_campaign_id in self._cache:
            logger.info(f"[StrategyLoader] 使用最近保存的策略: campaign_id={self._latest_campaign_id}")
            return self._cache[self._latest_campaign_id]

        if auto_generate:
            try:
                from agents.adapters import strategy_agent_adapter
                logger.info("[StrategyLoader] 无已保存策略，尝试自动调用 strategy_agent 生成默认策略")
                strategy_dict = strategy_agent_adapter.generate_strategy({
                    "goal": "提升信用卡分期转化，控制投诉风险",
                    "product": "installment",
                    "channel_mode": "omni",
                    "budget_wan": 80,
                    "risk_level": 2,
                    "frequency_level": 2,
                })
                if strategy_dict:
                    strategy = self._validate_and_parse(strategy_dict)
                    self.save_strategy(strategy)
                    logger.info(
                        f"[StrategyLoader] 自动生成策略成功: campaign_id={strategy.campaign_metadata.campaign_id}"
                    )
                    return strategy
                logger.warning("[StrategyLoader] strategy_agent 生成失败，回退到 mock 文件")
            except Exception as e:
                logger.warning(f"[StrategyLoader] 自动生成策略异常: {e}，回退到 mock 文件")

        logger.info("[StrategyLoader] 回退到 mock 文件")
        return self.load_from_file()

    def save_strategy(self, strategy: StrategyPackage) -> None:
        """保存策略包到内存缓存，并标记为最新"""
        campaign_id = strategy.campaign_metadata.campaign_id
        self._cache[campaign_id] = strategy
        self._latest_campaign_id = campaign_id
        logger.info(f"[StrategyLoader] 策略已缓存为最新: campaign_id={campaign_id}")

    def set_latest_campaign_id(self, campaign_id: str) -> None:
        """将已存在的某个 campaign_id 标记为最新"""
        if campaign_id in self._cache:
            self._latest_campaign_id = campaign_id
            logger.info(f"[StrategyLoader] 已切换最新策略: campaign_id={campaign_id}")
        else:
            logger.warning(f"[StrategyLoader] 切换失败，campaign_id 不存在: {campaign_id}")

    def list_cached_campaign_ids(self) -> list:
        """列出所有已缓存的 campaign_id"""
        return list(self._cache.keys())

    def _validate_and_parse(self, data: Dict[str, Any]) -> StrategyPackage:
        try:
            strategy = StrategyPackage(**data)
            logger.info(f"策略包校验成功: campaign_id={strategy.campaign_metadata.campaign_id}")
            return strategy
        except Exception as e:
            raise StrategyValidationError(f"策略包校验失败: {str(e)}")


class ComplianceChecker:
    def __init__(self):
        self._sensitive_words = []

    def check_age_restriction(self, strategy: StrategyPackage, user_age: int) -> bool:
        if strategy.compliance_guard and strategy.compliance_guard.age_restriction:
            return user_age >= strategy.compliance_guard.age_restriction
        return True

    def check_sensitive_words(self, text: str, strategy: Optional[StrategyPackage] = None) -> bool:
        blocked_words = []
        if strategy and strategy.compliance_guard and strategy.compliance_guard.blocked_words:
            blocked_words.extend(strategy.compliance_guard.blocked_words)
        
        blocked_words.extend(self._sensitive_words)
        
        for word in blocked_words:
            if word in text:
                logger.warning(f"检测到敏感词: {word}")
                return False
        return True

    def check_frequency_limit(self, oneid: str, channel: str, strategy: StrategyPackage, 
                              touch_count: int) -> bool:
        if strategy.compliance_guard and strategy.compliance_guard.frequency_limit:
            limit = int(strategy.compliance_guard.frequency_limit.replace('天最多触达', '').replace('次', ''))
            return touch_count < limit
        return True

    def validate_strategy_package(self, strategy: StrategyPackage) -> dict:
        errors = []
        warnings = []
        
        if not strategy.campaign_metadata.campaign_id:
            errors.append("活动ID不能为空")
        if strategy.campaign_metadata.budget <= 0:
            errors.append("预算金额必须大于0")
        
        total_ratio = sum(route.budget_ratio for route in strategy.channel_routing)
        if abs(total_ratio - 1.0) > 0.01:
            errors.append(f"渠道预算比例总和必须为1.0，当前为{total_ratio:.4f}")
        
        if not strategy.content_brief.core_message:
            errors.append("核心消息不能为空")
        
        if strategy.compliance_guard and strategy.compliance_guard.frequency_limit:
            try:
                limit = int(strategy.compliance_guard.frequency_limit.replace('天最多触达', '').replace('次', ''))
                if limit <= 0:
                    warnings.append("频率限制值应为正数")
            except ValueError:
                warnings.append("频率限制格式不正确")
        
        if strategy.experiment_plan:
            if strategy.experiment_plan.control_group_ratio and strategy.experiment_plan.test_group_ratio:
                total = strategy.experiment_plan.control_group_ratio + strategy.experiment_plan.test_group_ratio
                if abs(total - 1.0) > 0.01:
                    warnings.append(f"实验组和对照组比例总和应为1.0，当前为{total:.4f}")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }


class StrategyExecutor:
    def __init__(self):
        self._compliance_checker = ComplianceChecker()
        self._saved_strategies: Dict[str, StrategyPackage] = {}
        # 按保存时间顺序记录 campaign_id，用于查找最新策略
        self._latest_campaign_id: Optional[str] = None

    def parse_and_plan(self, strategy_data: Dict[str, Any]) -> ExecutionPlan:
        strategy = strategy_loader._validate_and_parse(strategy_data)
        return self._generate_execution_plan(strategy)

    def execute_from_file(self) -> ExecutionPlan:
        strategy = strategy_loader.load_from_file()
        return self._generate_execution_plan(strategy)

    def save_strategy(self, strategy: StrategyPackage):
        campaign_id = strategy.campaign_metadata.campaign_id
        self._saved_strategies[campaign_id] = strategy
        self._latest_campaign_id = campaign_id
        # 同步到 strategy_loader，让 load_latest 可以读到
        strategy_loader.save_strategy(strategy)
        logger.info(f"策略已保存: campaign_id={campaign_id}")

    def get_strategy(self, campaign_id: str) -> Optional[StrategyPackage]:
        return self._saved_strategies.get(campaign_id)

    def get_latest_strategy(self) -> Optional[StrategyPackage]:
        """获取最近保存的策略"""
        if self._latest_campaign_id:
            return self._saved_strategies.get(self._latest_campaign_id)
        return None

    def _generate_execution_plan(self, strategy: StrategyPackage) -> ExecutionPlan:
        trace_id = str(uuid.uuid4())
        tasks = []

        for i, channel in enumerate(strategy.channel_routing, 1):
            tasks.append({
                "task_id": f"TASK_{trace_id[:8]}_{i}",
                "channel": channel.channel,
                "budget_ratio": channel.budget_ratio,
                "contact_order": channel.contact_order or i,
                "retry_rule": channel.retry_rule,
                "status": "pending"
            })

        plan = ExecutionPlan(
            trace_id=trace_id,
            campaign_id=strategy.campaign_metadata.campaign_id,
            status="planned",
            tasks=tasks
        )

        logger.info(f"生成执行计划: trace_id={trace_id}, campaign_id={plan.campaign_id}")
        return plan


strategy_loader = StrategyLoader()
compliance_checker = ComplianceChecker()
strategy_executor = StrategyExecutor()