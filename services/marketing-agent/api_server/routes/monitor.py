"""
api_server\routes\monitor.py
功能描述: 监控统计API接口
"""

from fastapi import APIRouter
from typing import Dict, Any, List

from common import logger, exception_to_http
from agent_orchestrator import orchestrator, session_manager
from channel_gateway.channel_gateway import gateway
from feedback_collector import feedback_collector, conversation_summarizer, data_reflow_queue

router = APIRouter(prefix="/monitor", tags=["监控统计"])


@router.get("/stats")
async def get_stats():
    try:
        session_stats = session_manager.get_stats()
        reach_stats = gateway.get_dispatch_stats()
        feedback_stats = feedback_collector.get_event_stats()
        summary_stats = conversation_summarizer.get_summary_stats()
        reflow_status = data_reflow_queue.get_status()
        
        return {
            "sessions": session_stats,
            "reach": reach_stats,
            "feedback": feedback_stats,
            "summaries": summary_stats,
            "reflow": {
                "total_count": reflow_status.total_count,
                "success_count": reflow_status.success_count,
                "failed_count": reflow_status.failed_count,
                "pending_count": reflow_status.pending_count
            }
        }
    
    except Exception as e:
        logger.error(f"获取统计信息失败: {e}")
        raise exception_to_http(e)


@router.get("/workflows")
async def get_workflows():
    try:
        workflows = []
        
        for session_id, state in orchestrator._state_cache.items():
            workflows.append({
                "session_id": session_id,
                "oneid": state.oneid,
                "current_state": state.current_state.value,
                "workflow_status": state.workflow_status.value,
                "generated_content": state.generated_content[:50] if state.generated_content else None,
                "dispatch_count": len(state.dispatch_results),
                "error_message": state.error_message
            })
        
        return {"workflows": workflows}
    
    except Exception as e:
        logger.error(f"获取工作流列表失败: {e}")
        raise exception_to_http(e)


@router.get("/feedback")
async def get_feedback():
    try:
        campaign_feedbacks = feedback_collector.get_all_campaign_feedbacks()
        
        result = []
        for feedback in campaign_feedbacks:
            result.append({
                "campaign_id": feedback.campaign_id,
                "metrics": feedback.feedback_metrics.model_dump(),
                "channel_attribution": [attr.model_dump() for attr in feedback.channel_attribution],
                "segment_performance": [seg.model_dump() for seg in feedback.segment_performance],
                "conversation_outcome": feedback.conversation_outcome.model_dump()
            })
        
        return {"campaigns": result}
    
    except Exception as e:
        logger.error(f"获取反馈数据失败: {e}")
        raise exception_to_http(e)


@router.get("/reflow")
async def get_reflow_status():
    try:
        status = data_reflow_queue.get_status()
        project_one_status = data_reflow_queue.get_project_status("project_one")
        project_two_status = data_reflow_queue.get_project_status("project_two")
        
        return {
            "status": {
                "total_count": status.total_count,
                "success_count": status.success_count,
                "failed_count": status.failed_count,
                "pending_count": status.pending_count
            },
            "project_one": project_one_status,
            "project_two": project_two_status
        }
    
    except Exception as e:
        logger.error(f"获取回流状态失败: {e}")
        raise exception_to_http(e)


@router.get("/reflow/events")
async def get_reflow_events(limit: int = 20):
    try:
        events = data_reflow_queue.get_recent_events(limit=limit)
        return {"events": events}
    
    except Exception as e:
        logger.error(f"获取回流事件失败: {e}")
        raise exception_to_http(e)