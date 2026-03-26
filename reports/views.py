import json

from django.conf import settings
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from plants.models import SolarPlant
from reports.models import Report
from reports.services import generate_csv_report_for_owner


def _is_staff(user) -> bool:
    return bool(user and user.is_authenticated and user.is_staff)


@login_required
@require_GET
def reports_list(request):
    if request.user.is_staff:
        reports = Report.objects.select_related("owner", "plant").all()[:200]
        plants = SolarPlant.objects.all()
    else:
        reports = Report.objects.select_related("owner", "plant").filter(owner=request.user)[:200]
        plants = SolarPlant.objects.filter(owner=request.user)

    return render(
        request,
        "reports/reports_list.html",
        {
            "reports": reports,
            "plants": plants,
            "now": timezone.localtime(timezone.now()),
        },
    )


@login_required
@require_GET
def report_download(request, report_id: int):
    report = get_object_or_404(Report, id=report_id)
    if not request.user.is_staff and report.owner_id != request.user.id:
        raise Http404()
    if report.status != Report.STATUS_SUCCESS or not report.file_exists():
        raise Http404("Report file not available")
    return FileResponse(open(report.file_path, "rb"), as_attachment=True, filename=report.file_name)


@login_required
@require_POST
def report_generate_now(request):
    """
    Manual generate (UI). Airflow scheduled DAG will use the token-protected endpoint below.
    """
    period = request.POST.get("period", Report.PERIOD_DAILY)
    plant_id_raw = request.POST.get("plant_id") or None
    plant_id = int(plant_id_raw) if plant_id_raw else None

    # owner-level permissions
    if plant_id is not None:
        if request.user.is_staff:
            pass
        else:
            get_object_or_404(SolarPlant, id=plant_id, owner=request.user)

    report = generate_csv_report_for_owner(
        owner_id=request.user.id,
        period=period,
        plant_id=plant_id,
    )
    return JsonResponse({"ok": True, "report_id": report.id})


@csrf_exempt
@require_POST
def airflow_generate_report(request):
    """
    Called by Airflow (Option A) to generate a report through Django.
    """
    expected = getattr(settings, "AIRFLOW_REPORTS_TOKEN", None)
    token = request.headers.get("X-Airflow-Token") or request.headers.get("x-airflow-token")
    if not expected or token != expected:
        return JsonResponse({"ok": False, "error": "unauthorized"}, status=401)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        payload = {}

    owner_id = int(payload.get("owner_id"))
    period = payload.get("period", Report.PERIOD_DAILY)
    plant_id = payload.get("plant_id")
    plant_id = int(plant_id) if plant_id is not None else None

    airflow_dag_id = payload.get("airflow_dag_id")
    airflow_run_id = payload.get("airflow_run_id")

    report = generate_csv_report_for_owner(
        owner_id=owner_id,
        period=period,
        plant_id=plant_id,
        airflow_dag_id=airflow_dag_id,
        airflow_run_id=airflow_run_id,
    )
    return JsonResponse({"ok": True, "report_id": report.id})

