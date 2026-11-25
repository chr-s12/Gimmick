import { makeChartFilename } from "./chart_export.js";
import { bindChartDownload, describePeriod } from "./chart_download.js";

function exerciseFileKey(key) {
    if (!key || /^[A-Z0-9]{1,20}$/.test(key)) return key;
    // Keep long or punctuation-heavy duplicate-name IDs distinct in a bounded suffix.
    let fingerprint = 2166136261;
    for (const character of key) {
        fingerprint = Math.imul(fingerprint ^ character.codePointAt(0), 16777619);
    }
    return "id-" + (fingerprint >>> 0).toString(16).padStart(8, "0");
}

export function exerciseExportOptions({
    exercise, filenameExercise, exerciseKey, metric, measurement, unit, period, startDate, endDate, firstDate, lastDate,
}) {
    const { applied, filenameSuffix } = describePeriod(period, startDate, endDate);
    const plotted = firstDate === lastDate
        ? "Recorded training date: " + firstDate + "."
        : "Recorded training dates: " + firstDate + " to " + lastDate + ".";
    const suffix = makeChartFilename(exerciseFileKey(exerciseKey), metric, "progression", ...filenameSuffix);
    const stem = makeChartFilename(filenameExercise ?? exercise).slice(0, -4);
    // Preserve the metric and period even when the exercise name must be shortened.
    const exerciseSlug = stem.slice(0, 99 - suffix.length);
    return {
        filename: makeChartFilename(exerciseSlug, suffix.slice(0, -4)),
        metadata: {
            title: "Individual Exercise Progression",
            description: "Dots represent recorded performances by Jamaica calendar date. A dashed line connects observations where multiple points are present.",
            exercise,
            metric,
            measurement,
            unit,
            period: applied,
            startDate,
            endDate,
            notes: plotted,
            headingLines: [
                exercise + " · " + metric,
                measurement + " (" + unit + ") by training date, Jamaica time.",
                "Applied period: " + applied,
                plotted,
            ],
        },
    };
}

bindChartDownload("download-exercise-chart", "exercise-download-status", exerciseExportOptions, "Exercise Progression");
