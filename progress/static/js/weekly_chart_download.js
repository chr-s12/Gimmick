import { makeChartFilename } from "./chart_export.js";
import { bindChartDownload, describePeriod } from "./chart_download.js";

const MEASUREMENT = "Active training days per Monday–Sunday week (Jamaica time)";

export function weeklyExportOptions({
    period, startDate, endDate, firstWeek, lastWeekEnd, currentWeek, partialWeek,
}) {
    const { applied, filenameSuffix } = describePeriod(period, startDate, endDate);

    const plotted = "Plotted weeks: " + firstWeek + " to " + lastWeekEnd + " (Monday–Sunday).";
    const notes = [];
    if (currentWeek === "true") notes.push("Current week: incomplete, shown with a dashed outline or marker.");
    if (partialWeek === "true") notes.push("Partial selection: only dates in the applied period count.");

    return {
        filename: makeChartFilename("weekly-consistency", ...filenameSuffix),
        metadata: {
            title: "Weekly Consistency",
            description: "Each bar counts distinct training days on a zero-to-seven scale. Zero-day weeks use a baseline marker.",
            measurement: MEASUREMENT,
            period: applied,
            startDate,
            endDate,
            notes: [plotted, ...notes].join(" "),
            headingLines: [MEASUREMENT, "Applied period: " + applied, plotted, ...notes],
        },
    };
}

bindChartDownload("download-weekly-chart", "weekly-download-status", weeklyExportOptions, "Weekly Consistency");
