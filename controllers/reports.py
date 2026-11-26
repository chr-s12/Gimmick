"""Analyze Usage Trends pages (US-07): attendance report, charts and CSV export (operator only)."""
from datetime import timedelta

from flask import Blueprint, Response, flash, render_template, request

from occupancyTrends import ReportError, ReportService
from occupancyTrends.analytics import formatDuration, hourLabel

from .charts import barChart
from .common import rolesAllowed, svc

reports = Blueprint("reports", __name__, url_prefix="/reports")


def _charts(a) -> dict:
    hours = list(a.visitsPerHour)
    days = list(a.visitsPerDay)
    weeks = list(a.weekly)
    return {
        "hourly": barChart("Visits by hour of day", [hourLabel(h) for h in hours],
                           list(a.visitsPerHour.values()), [hours.index(h) for h in a.peakHours if h in hours]),
        "daily": barChart("Visits per day", [d.strftime("%a %d %b") for d in days], list(a.visitsPerDay.values()),
                          [days.index(d) for d in a.busiestDays if d in days]),
        "weekly": barChart("Visits per week (week starting)", [w.strftime("%d %b") for w in weeks],
                           list(a.weekly.values())),
    }


def _generate(start: str, end: str):
    first, last = ReportService.parseDateRange(start, end)
    return svc("reports").generateReport(first, last)


@reports.route("/")
@rolesAllowed("operator")
def report():
    today = svc("clock")().date()
    start = request.args.get("start") or (today - timedelta(days=27)).isoformat()
    end = request.args.get("end") or today.isoformat()
    analytics, error = None, None
    if request.args.get("start"):
        try:
            analytics = _generate(start, end)
        except ReportError as e:
            error = str(e)
            flash(error, "error")
    return render_template("reports/report.html", start=start, end=end, a=analytics, error=error,
                           summary=analytics.summary() if analytics else None,
                           charts=_charts(analytics) if analytics else None,
                           periods=[(s, e, formatDuration((e - s).total_seconds()))
                                    for s, e in analytics.capacityPeriods] if analytics else [])


@reports.route("/export.csv")
@rolesAllowed("operator")
def exportCsv():
    try:
        analytics = _generate(request.args.get("start", ""), request.args.get("end", ""))
    except ReportError as e:
        return Response(str(e), status=400, mimetype="text/plain")
    name = f"gym-usage-{analytics.startDate}-to-{analytics.endDate}.csv"
    return Response(ReportService.exportCsv(analytics), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={name}"})


@reports.route("/chart/<kind>.svg")
@rolesAllowed("operator")
def chart(kind):
    """Save a chart to the device (Review Gym Usage Analytics use case)."""
    try:
        analytics = _generate(request.args.get("start", ""), request.args.get("end", ""))
    except ReportError as e:
        return Response(str(e), status=400, mimetype="text/plain")
    charts = _charts(analytics)
    if kind not in charts:
        return Response("Unknown chart.", status=404, mimetype="text/plain")
    name = f"gym-{kind}-{analytics.startDate}-to-{analytics.endDate}.svg"
    return Response(charts[kind], mimetype="image/svg+xml",
                    headers={"Content-Disposition": f"attachment; filename={name}"})
