import { exportChart, supportsDirectSave } from "./chart_export.js";

export function describePeriod(period, startDate, endDate) {
    if (startDate && endDate) {
        return {
            applied: period + ": " + startDate + " to " + endDate + " (inclusive)",
            filenameSuffix: [startDate, "to", endDate],
        };
    }
    if (startDate || endDate) {
        const side = startDate ? "from" : "through";
        const date = startDate || endDate;
        return { applied: period + ": " + side + " " + date + " (inclusive)", filenameSuffix: [side, date] };
    }
    return { applied: period, filenameSuffix: [] };
}

const FEEDBACK = {
    "saved": "Visualisation saved successfully.",
    "download-initiated": "SVG download initiated. Check your browser's downloads for the file.",
    "cancelled": "Save cancelled.",
    "direct-save-unsupported": "Direct saving is unavailable here. Use Download SVG instead.",
    "permission-denied": "File access was denied. Choose another location or use Download SVG.",
    "storage-error": "The browser reported a storage or quota problem. Check available space or choose another location, then try again.",
    "write-failed": "The visualisation could not be saved. Try again or choose another location.",
    "preparation-failed": "The visualisation could not be prepared. Please try again.",
    "download-failed": "The SVG download could not be started. Please try again.",
};

export function bindChartDownload(buttonId, statusId, buildOptions, chartName,
    browser = globalThis, runExport = exportChart) {
    const button = browser.document?.getElementById(buttonId);
    if (!button) return;
    const document = button.ownerDocument;
    const chart = document.getElementById(button.getAttribute("aria-controls"));
    const status = document.getElementById(statusId);
    const alternative = document.getElementById(buttonId + "-alternative");
    if (!chart || !status || !alternative) return;

    const options = buildOptions(button.dataset);
    const direct = supportsDirectSave(browser);
    const controls = [button, alternative];
    let saving = false;

    async function save(mode) {
        if (saving) return;
        saving = true;
        // Keep keyboard focus on the action while suppressing repeat activation.
        for (const control of controls) control.setAttribute("aria-disabled", "true");
        status.textContent = mode === "direct" ? "Saving SVG…" : "Preparing SVG…";
        const genericFailure = mode === "direct" ? FEEDBACK["write-failed"] : FEEDBACK["download-failed"];
        try {
            // No asynchronous work precedes the native picker invocation.
            const result = await runExport(chart, { ...options, mode }, browser);
            status.textContent = Object.hasOwn(FEEDBACK, result.status) ? FEEDBACK[result.status] : genericFailure;
        } catch {
            status.textContent = genericFailure;
        } finally {
            saving = false;
            for (const control of controls) control.removeAttribute("aria-disabled");
        }
    }

    if (direct) {
        button.textContent = "Save SVG";
        button.setAttribute("aria-label", "Save SVG for " + chartName);
        alternative.hidden = false;
    }
    button.addEventListener("click", () => save(direct ? "direct" : "download"));
    alternative.addEventListener("click", () => save("download"));
    button.hidden = false;
}
