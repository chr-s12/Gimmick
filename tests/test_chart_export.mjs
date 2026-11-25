import assert from "node:assert/strict";
import { test } from "node:test";
import { bindChartDownload } from "../progress/static/js/chart_download.js";
import {
    chartDimensions, createSvgBlob, downloadSvg, exportChart, makeChartFilename,
    saveSvgDirect, supportsDirectSave,
} from "../progress/static/js/chart_export.js";

import { weeklyExportOptions } from "../progress/static/js/weekly_chart_download.js";

import { exerciseExportOptions } from "../progress/static/js/exercise_chart_download.js";

const xml = '<svg xmlns="http://www.w3.org/2000/svg" width="660" height="254"></svg>';
const blob = createSvgBlob(xml);

test("filename components are safe, descriptive and bounded", () => {
    assert.equal(makeChartFilename("Bénch Press", "Weight", "progression"), "bench-press-weight-progression.svg");
    assert.equal(makeChartFilename("../..", " \u0000 "), "workout-chart.svg");
    assert.equal(makeChartFilename("CON"), "workout-chart.svg");
    assert.equal(makeChartFilename("a".repeat(180)).length, 100);
    assert.equal(makeChartFilename("Weekly Consistency", "2026-11-24"), "weekly-consistency-2026-11-24.svg");
});

test("the SVG Blob preserves its XML and media type", async () => {
    assert.equal(blob.type, "image/svg+xml");
    assert.equal(await blob.text(), xml);
});

test("invalid charts fail preparation before interacting with download APIs", async () => {
    assert.throws(() => chartDimensions({ localName: "svg" }), TypeError);
    const result = await exportChart(null);
    assert.equal(result.status, "preparation-failed");
    assert.ok(result.error instanceof TypeError);
});

test("standard browser handoff removes the link and defers URL revocation", () => {
    const events = [];
    let cleanup;
    const link = {
        click() {
            assert.equal(this.href, "blob:chart");
            assert.equal(this.download, "weekly-consistency.svg");
            events.push("click");
        },
        remove() { events.push("remove"); },
    };
    const browser = {
        URL: {
            createObjectURL(file) {
                assert.equal(file, blob);
                events.push("create");
                return "blob:chart";
            },
            revokeObjectURL(url) {
                assert.equal(url, "blob:chart");
                events.push("revoke");
            },
        },
        document: {
            createElement(tag) { assert.equal(tag, "a"); return link; },
            body: { appendChild(anchor) { assert.equal(anchor, link); events.push("append"); } },
        },
        setTimeout(callback, delay) {
            assert.ok(delay > 0);
            cleanup = callback;
        },
    };

    assert.deepEqual(downloadSvg(blob, "Weekly Consistency.svg", browser), { status: "download-initiated" });
    assert.deepEqual(events, ["create", "append", "click", "remove"]);
    cleanup();
    assert.deepEqual(events, ["create", "append", "click", "remove", "revoke"]);
});

test("direct save requires a secure context and a picker function", async () => {
    assert.equal(supportsDirectSave({ isSecureContext: true }), false);
    const browser = {
        isSecureContext: false,
        showSaveFilePicker() { assert.fail("insecure context must not open a picker"); },
    };
    assert.equal(supportsDirectSave(browser), false);
    assert.deepEqual(await saveSvgDirect(blob, "chart", browser), { status: "direct-save-unsupported" });
});

test("picker dismissal is distinct from permission failures", async () => {
    for (const [name, status] of [["AbortError", "cancelled"], ["SecurityError", "permission-denied"],
        ["NotAllowedError", "permission-denied"]]) {
        const error = new DOMException("test", name);
        const browser = {
            isSecureContext: true,
            async showSaveFilePicker() { throw error; },
        };
        const result = await saveSvgDirect(blob, "chart", browser);
        assert.equal(result.status, status);
        assert.equal(result.error, status === "cancelled" ? undefined : error);
    }
});

test("direct save confirms success only after both write and close", async () => {
    const writing = Promise.withResolvers();
    const closing = Promise.withResolvers();
    const events = [];
    const browser = {
        isSecureContext: true,
        showSaveFilePicker(options) {
            assert.equal(options.suggestedName, "bench-press-weight-progression.svg");
            assert.deepEqual(options.types[0].accept, { "image/svg+xml": [".svg"] });
            events.push("picker");
            return {
                async createWritable() {
                    events.push("open");
                    return {
                        write(file) {
                            assert.equal(file, blob);
                            events.push("write");
                            return writing.promise;
                        },
                        close() { events.push("close"); return closing.promise; },
                    };
                },
            };
        },
    };

    const result = saveSvgDirect(blob, "Bench Press Weight Progression.svg", browser);
    assert.deepEqual(events, ["picker"]);
    let completed = false;
    result.then(() => { completed = true; });
    await new Promise(setImmediate);
    assert.deepEqual(events, ["picker", "open", "write"]);
    assert.equal(completed, false);
    writing.resolve();
    await new Promise(setImmediate);
    assert.deepEqual(events, ["picker", "open", "write", "close"]);
    assert.equal(completed, false);
    closing.resolve();
    assert.deepEqual(await result, { status: "saved" });
});

test("write and close failures are classified and attempt stream cleanup", async () => {
    for (const [phase, name, status] of [
        ["write", "QuotaExceededError", "storage-error"],
        ["write", "AbortError", "write-failed"],
        ["close", "UnknownError", "write-failed"],
        ["open", "NotAllowedError", "permission-denied"],
    ]) {
        let aborted = false;
        const error = new DOMException("test", name);
        const browser = {
            isSecureContext: true,
            async showSaveFilePicker() {
                return {
                    async createWritable() {
                        if (phase === "open") throw error;
                        return {
                            async write() { if (phase === "write") throw error; },
                            async close() { if (phase === "close") throw error; },
                            async abort() {
                                aborted = true;
                                throw new Error("stream already errored");
                            },
                        };
                    },
                };
            },
        };
        assert.deepEqual(await saveSvgDirect(blob, "chart", browser), { status, error });
        assert.equal(aborted, phase !== "open");
    }
});

test("weekly options distinguish the rendered relative period and plotted calendar weeks", () => {
    const rendered = {
        period: "Last 7 days", startDate: "2026-11-19", endDate: "2026-11-25",
        firstWeek: "2026-11-16", lastWeekEnd: "2026-11-29", currentWeek: "true", partialWeek: "true",
    };
    const { filename, metadata } = weeklyExportOptions(rendered);
    assert.equal(filename, "weekly-consistency-2026-11-19-to-2026-11-25.svg");
    assert.equal(metadata.period, "Last 7 days: 2026-11-19 to 2026-11-25 (inclusive)");
    assert.match(metadata.notes, /Plotted weeks: 2026-11-16 to 2026-11-29/);
    assert.match(metadata.notes, /Current week: incomplete/);
    assert.match(metadata.notes, /Partial selection/);
    assert.ok(metadata.headingLines.includes("Applied period: " + metadata.period));
});

test("weekly options omit missing boundaries and inapplicable week explanations", () => {
    const weeks = { firstWeek: "2026-11-02", lastWeekEnd: "2026-11-08" };
    const all = weeklyExportOptions({ period: "All time", ...weeks });
    assert.equal(all.filename, "weekly-consistency.svg");
    assert.equal(all.metadata.period, "All time");
    assert.doesNotMatch(all.metadata.notes, /Current week|Partial selection/);
    for (const [field, preposition] of [["startDate", "from"], ["endDate", "through"]]) {
        const options = weeklyExportOptions({ period: "Custom date range", [field]: "2026-11-04", ...weeks });
        assert.equal(options.filename, "weekly-consistency-" + preposition + "-2026-11-04.svg");
        assert.equal(options.metadata.period, "Custom date range: " + preposition + " 2026-11-04 (inclusive)");
        assert.equal(options.metadata[field === "startDate" ? "endDate" : "startDate"], undefined);
    }
});

test("exercise exports label all three metrics with the rendered period and plotted dates", () => {
    for (const [metric, measurement, unit] of [
        ["Weight", "Highest external weight", "kg"],
        ["Repetitions", "Most repetitions per set", "reps"],
        ["Volume", "Combined daily volume", "kg"],
    ]) {
        const { filename, metadata } = exerciseExportOptions({
            exercise: "Bénch Press", metric, measurement, unit, period: "Last 7 days",
            startDate: "2026-11-19", endDate: "2026-11-25",
            firstDate: "2026-11-21", lastDate: "2026-11-24",
        });
        assert.equal(filename, "bench-press-" + metric.toLowerCase() + "-progression-2026-11-19-to-2026-11-25.svg");
        assert.equal(metadata.period, "Last 7 days: 2026-11-19 to 2026-11-25 (inclusive)");
        assert.equal(metadata.notes, "Recorded training dates: 2026-11-21 to 2026-11-24.");
        assert.ok(metadata.headingLines.includes(measurement + " (" + unit + ") by training date, Jamaica time."));
    }
});

test("exercise filenames preserve disambiguation and period within the length limit", () => {
    const options = exerciseExportOptions({
        exercise: "A".repeat(150) + " (E2)", filenameExercise: "A".repeat(150), exerciseKey: "E2",
        metric: "Volume", measurement: "Combined daily volume", unit: "kg", period: "Custom date range",
        endDate: "2026-11-24", firstDate: "2026-11-24", lastDate: "2026-11-24",
    });
    assert.ok(options.filename.length <= 100);
    assert.match(options.filename, /-e2-volume-progression-through-2026-11-24\.svg$/);
    assert.equal(options.metadata.period, "Custom date range: through 2026-11-24 (inclusive)");
    assert.equal(options.metadata.notes, "Recorded training date: 2026-11-24.");
    assert.equal(exerciseExportOptions({ exercise: "../../", metric: "Weight", period: "All time" }).filename,
        "workout-chart-weight-progression.svg");
});

test("long duplicate exercise IDs cannot consume the metric and date filename suffix", () => {
    const naming = key => exerciseExportOptions({
        exercise: "Bench Press", exerciseKey: key, metric: "Repetitions", period: "Last 30 days",
        startDate: "2026-10-27", endDate: "2026-11-25",
    }).filename;
    const prefix = "EX".repeat(80);
    for (const [first, second] of [[prefix + "A", prefix + "B"], ["ex/1", "ex?1"]]) {
        assert.notEqual(naming(first), naming(second));
        for (const value of [first, second]) {
            assert.match(naming(value), /^bench-press-id-[a-f0-9]{8}-repetitions-progression-2026-10-27-to-2026-11-25\.svg$/);
        }
    }
});

function saveControls(browser, runExport, name = "weekly") {
    const chart = {};
    const status = { textContent: "" };
    const elements = new Map([[name + "-svg", chart], [name + "-status", status]]);
    const document = browser.document ??= { getElementById: id => elements.get(id) };
    if (browser.testElements) {
        for (const [id, element] of elements) browser.testElements.set(id, element);
    } else {
        browser.testElements = elements;
    }

    function control(id) {
        const attributes = new Map([["aria-controls", name + "-svg"]]);
        const node = {
            ownerDocument: document, dataset: {}, hidden: true, textContent: "Download SVG",
            getAttribute: key => attributes.get(key),
            setAttribute: (key, value) => attributes.set(key, value),
            removeAttribute: key => attributes.delete(key),
            addEventListener(event, callback) { assert.equal(event, "click"); this.activate = callback; },
        };
        browser.testElements.set(id, node);
        return node;
    }

    const primary = control(name);
    const alternative = control(name + "-alternative");
    bindChartDownload(name, name + "-status", () => ({ filename: name + ".svg" }), name, browser,
        (svg, options, context) => {
            assert.equal(svg, chart);
            assert.equal(context, browser);
            assert.equal(options.filename, name + ".svg");
            return runExport(options.mode);
        });
    return { primary, alternative, status };
}

test("unsupported browsers show one standard download control and precise feedback", async () => {
    const modes = [];
    const { primary, alternative, status } = saveControls({ isSecureContext: true }, async mode => {
        modes.push(mode);
        return { status: "download-initiated" };
    });
    assert.equal(primary.hidden, false);
    assert.equal(primary.textContent, "Download SVG");
    assert.equal(alternative.hidden, true);
    await primary.activate();
    assert.deepEqual(modes, ["download"]);
    assert.equal(status.textContent, "SVG download initiated. Check your browser's downloads for the file.");
});

test("native save prevents overlap, preserves cancellation and allows a manual download", async () => {
    const pending = Promise.withResolvers();
    const modes = [];
    const { primary, alternative, status } = saveControls({
        isSecureContext: true, showSaveFilePicker() {},
    }, mode => {
        modes.push(mode);
        return mode === "direct" ? pending.promise : Promise.resolve({ status: "download-initiated" });
    });
    assert.equal(primary.textContent, "Save SVG");
    assert.equal(alternative.hidden, false);
    const saving = primary.activate();
    assert.deepEqual(modes, ["direct"]);
    assert.equal(status.textContent, "Saving SVG…");
    assert.equal(primary.getAttribute("aria-disabled"), "true");
    assert.equal(alternative.getAttribute("aria-disabled"), "true");
    await primary.activate();
    await alternative.activate();
    assert.deepEqual(modes, ["direct"]);
    pending.resolve({ status: "cancelled" });
    await saving;
    assert.equal(status.textContent, "Save cancelled.");
    assert.deepEqual(modes, ["direct"]);
    assert.equal(primary.getAttribute("aria-disabled"), undefined);
    assert.equal(alternative.getAttribute("aria-disabled"), undefined);
    await alternative.activate();
    assert.deepEqual(modes, ["direct", "download"]);
    assert.match(status.textContent, /^SVG download initiated/);
});

test("save feedback distinguishes failures and restores controls without leaking details", async () => {
    for (const [outcome, message] of [
        ["saved", /^Visualisation saved successfully/],
        ["permission-denied", /^File access was denied/],
        ["storage-error", /reported a storage or quota problem/],
        ["write-failed", /^The visualisation could not be saved/],
        ["preparation-failed", /^The visualisation could not be prepared/],
        ["direct-save-unsupported", /^Direct saving is unavailable/],
        ["reject", /^The visualisation could not be saved/],
    ]) {
        const modes = [];
        const { primary, status } = saveControls({ isSecureContext: true, showSaveFilePicker() {} }, async mode => {
            modes.push(mode);
            if (outcome === "reject") throw new Error("internal file detail");
            return { status: outcome, error: new Error("internal file detail") };
        });
        await primary.activate();
        assert.deepEqual(modes, ["direct"]);
        assert.match(status.textContent, message);
        assert.doesNotMatch(status.textContent, /internal file detail/);
        assert.equal(primary.getAttribute("aria-disabled"), undefined);
    }
});

test("each chart has independent feedback", async () => {
    const browser = { isSecureContext: true, showSaveFilePicker() {} };
    const weekly = saveControls(browser, async () => ({ status: "saved" }), "weekly");
    const exercise = saveControls(browser, async () => ({ status: "permission-denied" }), "exercise");
    await weekly.primary.activate();
    await exercise.primary.activate();
    assert.match(weekly.status.textContent, /^Visualisation saved successfully/);
    assert.match(exercise.status.textContent, /^File access was denied/);
});
