from __future__ import annotations

from celery import chain, shared_task
from django.utils import timezone

from plants.models import DemoPipelineRun


@shared_task(bind=True)
def pipeline_start(self, pipeline_id: int):
    DemoPipelineRun.objects.filter(id=pipeline_id).update(
        status=DemoPipelineRun.STATUS_RUNNING,
        current_step="start",
        started_at=timezone.now(),
        error_message=None,
    )
    return {"pipeline_id": pipeline_id}


@shared_task(bind=True, max_retries=3, default_retry_delay=2)
def pipeline_work(self, payload: dict, mode: str):
    pipeline_id = int(payload["pipeline_id"])
    DemoPipelineRun.objects.filter(id=pipeline_id).update(current_step="work")

    # A single task that can succeed, retry a bit, or fail.
    if mode == DemoPipelineRun.MODE_SUCCESS:
        return {"pipeline_id": pipeline_id, "work": "ok"}

    if mode == DemoPipelineRun.MODE_FAILURE:
        raise Exception("Intentional failure in pipeline_work")

    if mode == DemoPipelineRun.MODE_RETRY:
        # retry twice, then succeed on the 3rd attempt
        attempt = self.request.retries + 1
        if attempt < 3:
            raise self.retry(exc=Exception(f"Intentional retry attempt {attempt}"), countdown=2)
        return {"pipeline_id": pipeline_id, "work": f"ok_after_{attempt}_attempts"}

    raise ValueError(f"Unknown mode: {mode}")


@shared_task(bind=True)
def pipeline_postprocess(self, payload: dict):
    """
    Lightweight step to demonstrate an additional DAG stage.
    """
    pipeline_id = int(payload["pipeline_id"])
    DemoPipelineRun.objects.filter(id=pipeline_id).update(current_step="postprocess")
    return {**payload, "postprocess": "ok"}


@shared_task(bind=True)
def pipeline_finalize(self, payload: dict):
    pipeline_id = int(payload["pipeline_id"])
    DemoPipelineRun.objects.filter(id=pipeline_id).update(
        status=DemoPipelineRun.STATUS_SUCCESS,
        current_step="finalize",
        finished_at=timezone.now(),
    )
    return {"pipeline_id": pipeline_id, "status": "READY"}


@shared_task(bind=True)
def pipeline_mark_failed(self, request, exc, traceback, pipeline_id: int):
    # Celery passes request/exception/traceback to errback signatures.
    DemoPipelineRun.objects.filter(id=pipeline_id).update(
        status=DemoPipelineRun.STATUS_FAILURE,
        current_step="failed",
        error_message=str(exc),
        finished_at=timezone.now(),
    )


def kickoff_demo_pipeline(*, pipeline_id: int, mode: str):
    """
    Returns AsyncResult for the chained workflow:
      start -> work -> postprocess -> finalize

    If any task fails permanently, the errback marks the pipeline as FAILED.
    """
    wf = chain(
        pipeline_start.s(pipeline_id),
        pipeline_work.s(mode=mode),
        pipeline_postprocess.s(),
        pipeline_finalize.s(),
    )
    return wf.apply_async(link_error=pipeline_mark_failed.s(pipeline_id))

