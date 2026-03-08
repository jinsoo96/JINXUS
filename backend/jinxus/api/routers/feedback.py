"""Feedback API - 피드백 처리"""
from fastapi import APIRouter, HTTPException

from jinxus.api.models import FeedbackRequest, FeedbackResponse
from jinxus.core import get_jinx_loop

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackResponse)
async def submit_feedback(request: FeedbackRequest):
    """피드백 제출

    rating ≤ 2면 JinxLoop 자동 트리거
    """
    jinx_loop = get_jinx_loop()

    try:
        result = await jinx_loop.process_feedback(
            task_id=request.task_id,
            rating=request.rating,
            comment=request.comment,
            target_agent=request.target_agent,
        )

        return FeedbackResponse(
            success=True,
            message="Feedback received",
            triggered_improve=result.get("triggered_improve", False),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
