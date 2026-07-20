"""
api_server\routes\strategy.py
功能描述: 策略接收与管理API接口
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional, List

from common import logger, exception_to_http
from agent_orchestrator import strategy_loader, strategy_executor, compliance_checker, StrategyPackage
from agents.adapters import strategy_agent_adapter

router = APIRouter(prefix="/strategy", tags=["策略管理"])


class StrategyReceiveRequest(BaseModel):
    strategy: Dict[str, Any]


class StrategyReceiveResponse(BaseModel):
    success: bool
    campaign_id: str
    message: str


@router.post("/receive", response_model=StrategyReceiveResponse)
async def receive_strategy(request: StrategyReceiveRequest):
    try:
        strategy = StrategyPackage(**request.strategy)

        validation_result = compliance_checker.validate_strategy_package(strategy)
        if not validation_result["valid"]:
            raise HTTPException(status_code=400, detail=f"策略校验失败: {validation_result['errors']}")

        strategy_executor.save_strategy(strategy)

        logger.info(f"策略接收成功: campaign_id={strategy.campaign_metadata.campaign_id}")

        return StrategyReceiveResponse(
            success=True,
            campaign_id=strategy.campaign_metadata.campaign_id,
            message="策略接收成功"
        )

    except Exception as e:
        logger.error(f"策略接收失败: {e}")
        raise exception_to_http(e)


@router.get("/current")
async def get_current_strategy():
    try:
        strategy = strategy_loader.load_latest()

        if not strategy:
            return {"message": "未加载策略包"}

        return strategy.model_dump()

    except Exception as e:
        logger.error(f"获取当前策略失败: {e}")
        raise exception_to_http(e)


@router.post("/validate")
async def validate_strategy(request: StrategyReceiveRequest):
    try:
        strategy = StrategyPackage(**request.strategy)

        validation_result = compliance_checker.validate_strategy_package(strategy)

        return {
            "valid": validation_result["valid"],
            "errors": validation_result["errors"],
            "warnings": validation_result["warnings"]
        }

    except Exception as e:
        logger.error(f"策略校验失败: {e}")
        return {
            "valid": False,
            "errors": [str(e)],
            "warnings": []
        }


# ==================== strategy_agent 对接接口 ====================

class StrategyGenerateRequest(BaseModel):
    """调用 strategy_agent 生成策略包的请求参数"""
    goal: str
    product: str = "installment"
    channel_mode: str = "omni"
    budget_wan: int = 80
    risk_level: int = 2
    frequency_level: int = 2


class StrategyGenerateResponse(BaseModel):
    success: bool
    campaign_id: str
    message: str
    strategy: Optional[Dict[str, Any]] = None
    raw_plan: Optional[Dict[str, Any]] = None


@router.post("/generate", response_model=StrategyGenerateResponse)
async def generate_strategy_from_sa(request: StrategyGenerateRequest):
    """
    调用 strategy_agent 生成营销策略包：
    1. 调用 strategy_agent /api/generate 生成 MarketingPlan
    2. 转换为 StrategyPackage 格式
    3. 校验并保存到内存
    4. 返回完整策略包
    """
    try:
        if not request.goal.strip():
            raise HTTPException(status_code=400, detail="goal 不能为空")

        request_params = {
            "goal": request.goal,
            "product": request.product,
            "channel_mode": request.channel_mode,
            "budget_wan": request.budget_wan,
            "risk_level": request.risk_level,
            "frequency_level": request.frequency_level,
        }

        logger.info(f"调用 strategy_agent 生成策略: {request_params}")

        strategy_dict = strategy_agent_adapter.generate_strategy(request_params)

        if not strategy_dict:
            raise HTTPException(
                status_code=502,
                detail="strategy_agent 不可用或返回为空，请检查 strategy_agent 服务状态"
            )

        # 用 StrategyPackage 做格式校验
        try:
            strategy = StrategyPackage(**strategy_dict)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"策略包格式校验失败: {str(e)}"
            )

        # 合规校验
        validation_result = compliance_checker.validate_strategy_package(strategy)
        if not validation_result["valid"]:
            raise HTTPException(
                status_code=400,
                detail=f"策略校验失败: {validation_result['errors']}"
            )

        # 保存（会同步到 strategy_loader，让 load_latest 可以读到）
        strategy_executor.save_strategy(strategy)

        logger.info(
            f"策略生成成功: campaign_id={strategy.campaign_metadata.campaign_id}, "
            f"audience_size={sum(s.size for s in strategy.audience_segments)}"
        )

        return StrategyGenerateResponse(
            success=True,
            campaign_id=strategy.campaign_metadata.campaign_id,
            message="策略生成成功",
            strategy=strategy.model_dump(),
            raw_plan=strategy_agent_adapter.get_last_raw_plan(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"生成策略失败: {e}")
        raise exception_to_http(e)


@router.get("/cached")
async def get_cached_strategy():
    """获取 strategy_agent_adapter 内存中缓存的最新策略（不触发工作流加载）"""
    try:
        cached = strategy_agent_adapter.get_cached_strategy()
        if not cached:
            return {"message": "无缓存策略，请先调用 /api/v3/strategy/generate"}
        return {
            "campaign_id": cached.get("campaign_metadata", {}).get("campaign_id"),
            "strategy": cached,
        }
    except Exception as e:
        logger.error(f"获取缓存策略失败: {e}")
        raise exception_to_http(e)


@router.get("/list")
async def list_cached_strategies():
    """列出所有已缓存的 campaign_id"""
    try:
        campaign_ids = strategy_loader.list_cached_campaign_ids()
        return {
            "campaign_ids": campaign_ids,
            "latest_campaign_id": strategy_loader._latest_campaign_id,
            "total": len(campaign_ids),
        }
    except Exception as e:
        logger.error(f"获取策略列表失败: {e}")
        raise exception_to_http(e)


@router.post("/switch")
async def switch_latest_strategy(request: Dict[str, Any]):
    """切换当前使用的策略包（按 campaign_id）"""
    try:
        campaign_id = request.get("campaign_id")
        if not campaign_id:
            raise HTTPException(status_code=400, detail="campaign_id 不能为空")

        strategy_loader.set_latest_campaign_id(campaign_id)
        return {
            "success": True,
            "latest_campaign_id": strategy_loader._latest_campaign_id,
            "message": f"已切换到策略: {campaign_id}",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"切换策略失败: {e}")
        raise exception_to_http(e)