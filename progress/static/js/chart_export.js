const SVG_NS = "http://www.w3.org/2000/svg";
const SVG_TYPE = "image/svg+xml";
const GRAPHICS = new Set(["g", "rect", "line", "text", "tspan", "circle",
    "ellipse", "polyline", "polygon", "path"]);
const GRAPHIC_ATTRIBUTES = [
    "x", "y", "x1", "y1", "x2", "y2", "width", "height", "rx", "ry",
    "cx", "cy", "r", "d", "points", "transform", "dx", "dy",
];
const INHERITED_STYLES = [
    "color", "fill", "fill-opacity", "fill-rule", "stroke", "stroke-opacity", "stroke-width",
    "stroke-dasharray", "stroke-dashoffset", "stroke-linecap", "stroke-linejoin",
    "font-family", "font-size", "font-style", "font-weight", "font-variant-numeric",
    "letter-spacing", "text-anchor", "dominant-baseline",
];
const METADATA_FIELDS = {
    measurement: "Measurement", exercise: "Exercise", metric: "Metric", unit: "Unit",
    period: "Period", startDate: "Start date", endDate: "End date", notes: "Notes",
};

function xmlText(value) {
    return String(value ?? "").replace(
        /[^\u0009\u000A\u000D\u0020-\uD7FF\uE000-\uFFFD\u{10000}-\u{10FFFF}]/gu, "\uFFFD",
    );
}

function childWithName(svg, name) {
    return Array.from(svg.children).find(child => child.namespaceURI === SVG_NS && child.localName === name);
}

function copyComputedStyle(target, style, parentStyle) {
    for (const property of INHERITED_STYLES) {
        const value = style.getPropertyValue(property);
        if (value && value !== parentStyle?.getPropertyValue(property)) {
            // The current charts have only solid paints. Drop resource references.
            if ((property === "fill" || property === "stroke") && /url\s*\(/i.test(value)) {
                target.style.setProperty(property, "none");
            } else {
                target.style.setProperty(property, value);
            }
        }
    }
    if (style.opacity && style.opacity !== "1") {
        target.style.setProperty("opacity", style.opacity);
    }
}

function copyGraphic(source, parentStyle, document, view) {
    if (source.namespaceURI !== SVG_NS) return null;
    if (source.localName === "title" || source.localName === "desc") {
        const label = document.createElementNS(SVG_NS, source.localName);
        label.textContent = xmlText(source.textContent);
        return label;
    }
    if (!GRAPHICS.has(source.localName)) return null;

    const style = view.getComputedStyle(source);
    if (style.display === "none" || style.visibility !== "visible" || style.opacity === "0"
        || source.hasAttribute("hidden")) return null;

    const clone = document.createElementNS(SVG_NS, source.localName);
    for (const attribute of GRAPHIC_ATTRIBUTES) {
        if (source.hasAttribute(attribute)) {
            clone.setAttribute(attribute, xmlText(source.getAttribute(attribute)));
        }
    }
    copyComputedStyle(clone, style, parentStyle);

    for (const child of source.childNodes) {
        if (child.nodeType === 1) {
            const graphic = copyGraphic(child, style, document, view);
            if (graphic) clone.appendChild(graphic);
        } else if (child.nodeType === 3 && (source.localName === "text" || source.localName === "tspan")) {
            clone.appendChild(document.createTextNode(xmlText(child.nodeValue)));
        }
    }
    return clone;
}

/** Validate that the caller supplied a rendered, intrinsically sized SVG root. */
export function chartDimensions(svg) {
    if (svg?.namespaceURI !== SVG_NS || svg.localName !== "svg" || !svg.isConnected
        || !svg.ownerDocument.defaultView) {
        throw new TypeError("Expected a connected SVG chart.");
    }
    const width = Number(svg.getAttribute("width"));
    const height = Number(svg.getAttribute("height"));
    const viewBox = (svg.getAttribute("viewBox") ?? "").trim().split(/[\s,]+/).map(Number);
    if (viewBox.length !== 4 || ![width, height, ...viewBox].every(Number.isFinite)
        || width <= 0 || height <= 0 || viewBox[2] <= 0 || viewBox[3] <= 0) {
        throw new TypeError("Expected positive SVG dimensions and a valid viewBox.");
    }
    return { width, height, viewBox };
}

function wrapHeading(value, capacity) {
    const lines = [];
    let remaining = Array.from(xmlText(value).trim().replace(/\s+/g, " "));
    while (remaining.length > capacity) {
        const split = remaining.lastIndexOf(" ", capacity);
        const end = split > 0 ? split : capacity;
        lines.push(remaining.slice(0, end).join(""));
        remaining = remaining.slice(end + (remaining[end] === " " ? 1 : 0));
    }
    if (remaining.length) lines.push(remaining.join(""));
    return lines;
}

/** Add visible context above the existing SVG viewport without rescaling it. */
function addVisibleHeading(chart, title, description, lines, width, height) {
    const document = chart.ownerDocument;
    const wrapper = document.createElementNS(SVG_NS, "svg");
    const fullWidth = Math.max(width, 640);
    const padding = 16;
    const heading = [
        ...wrapHeading(title.textContent, Math.floor((fullWidth - 2 * padding) / 20))
            .map(label => ({ label, size: 20 })),
        ...lines.flatMap(line => wrapHeading(line, Math.floor((fullWidth - 2 * padding) / 12)))
            .map(label => ({ label, size: 12 })),
    ];
    const headerHeight = padding + heading.reduce((sum, item) => sum + item.size + 6, 0);
    wrapper.setAttribute("width", fullWidth);
    wrapper.setAttribute("height", height + headerHeight);
    wrapper.setAttribute("viewBox", `0 0 ${fullWidth} ${height + headerHeight}`);
    for (const attribute of ["role", "aria-labelledby", "aria-describedby"]) {
        wrapper.setAttribute(attribute, chart.getAttribute(attribute));
        chart.removeAttribute(attribute);
    }
    wrapper.append(title, description);

    const background = document.createElementNS(SVG_NS, "rect");
    background.setAttribute("width", fullWidth);
    background.setAttribute("height", height + headerHeight);
    background.setAttribute("fill", "#ffffff");
    wrapper.appendChild(background);

    let y = padding;
    for (const { label, size } of heading) {
        const text = document.createElementNS(SVG_NS, "text");
        text.setAttribute("x", padding);
        text.setAttribute("y", y + size);
        text.setAttribute("font-size", size);
        text.setAttribute("font-family", chart.style.getPropertyValue("font-family"));
        text.setAttribute("font-weight", size === 20 ? "700" : "400");
        text.setAttribute("fill", "#15233b");
        text.textContent = label;
        wrapper.appendChild(text);
        y += size + 6;
    }

    chart.setAttribute("y", headerHeight);
    wrapper.appendChild(chart);
    return wrapper;
}

/** Build a detached, static clone with only the SVG elements the charts use. */
export function prepareStandaloneSvg(svg, metadata = {}) {
    const { width, height, viewBox } = chartDimensions(svg);
    const document = svg.ownerDocument;
    const view = document.defaultView;
    const sourceStyle = view.getComputedStyle(svg);
    const clone = document.createElementNS(SVG_NS, "svg");
    clone.setAttribute("width", width);
    clone.setAttribute("height", height);
    clone.setAttribute("viewBox", viewBox.join(" "));
    clone.setAttribute("role", "img");
    clone.setAttribute("aria-labelledby", "chart-title");
    clone.setAttribute("aria-describedby", "chart-description");
    copyComputedStyle(clone, sourceStyle);
    // Resolve system font choices from the source; keep a standalone fallback.
    const family = sourceStyle.getPropertyValue("font-family");
    clone.style.setProperty("font-family", family ? family + ", sans-serif" : "sans-serif");

    const title = document.createElementNS(SVG_NS, "title");
    title.id = "chart-title";
    title.textContent = xmlText(metadata.title ?? childWithName(svg, "title")?.textContent) || "Workout chart";
    const description = document.createElementNS(SVG_NS, "desc");
    description.id = "chart-description";
    const details = Object.entries(METADATA_FIELDS)
        .filter(([key]) => typeof metadata[key] === "string" && metadata[key].trim())
        .map(([key, label]) => label + ": " + xmlText(metadata[key]));
    description.textContent = [
        xmlText(metadata.description ?? childWithName(svg, "desc")?.textContent) || "Workout analytics chart.",
        ...details,
    ].join("\n");
    clone.append(title, description);

    const background = document.createElementNS(SVG_NS, "rect");
    for (const [index, attribute] of ["x", "y", "width", "height"].entries()) {
        background.setAttribute(attribute, viewBox[index]);
    }
    background.style.setProperty("fill", "#ffffff");
    background.style.setProperty("stroke", "none");
    background.setAttribute("aria-hidden", "true");
    clone.appendChild(background);

    for (const child of svg.children) {
        if (child.localName === "title" || child.localName === "desc") continue;
        const graphic = copyGraphic(child, sourceStyle, document, view);
        if (graphic) clone.appendChild(graphic);
    }
    return metadata.headingLines?.length
        ? addVisibleHeading(clone, title, description, metadata.headingLines, width, height)
        : clone;
}

/** Use the platform XML serializer so labels remain text and the SVG namespace is emitted. */
export function serializeSvg(svg) {
    const Serializer = svg.ownerDocument.defaultView.XMLSerializer;
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + new Serializer().serializeToString(svg);
}

export function createSvgBlob(xml) {
    return new Blob([xml], { type: SVG_TYPE });
}

export function makeChartFilename(...components) {
    const stem = components
        .filter(component => typeof component === "string")
        .join("-")
        .normalize("NFKD")
        .replace(/\p{M}/gu, "")
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "")
        .slice(0, 96)
        .replace(/-+$/g, "");
    const reserved = /^(?:con|prn|aux|nul|com[0-9]|lpt[0-9])$/;
    return (stem && !reserved.test(stem) ? stem : "workout-chart") + ".svg";
}

function safeFilename(filename) {
    return makeChartFilename(typeof filename === "string" ? filename.replace(/\.svg$/i, "") : "");
}

export function supportsDirectSave(browser = globalThis) {
    return browser.isSecureContext === true && typeof browser.showSaveFilePicker === "function";
}

/** Initiate a standard download. The browser API does not confirm a disk write. */
export function downloadSvg(blob, filename, browser = globalThis) {
    let url;
    let link;
    try {
        url = browser.URL.createObjectURL(blob);
        link = browser.document.createElement("a");
        link.href = url;
        link.download = safeFilename(filename);
        link.hidden = true;
        browser.document.body.appendChild(link);
        link.click();
        return { status: "download-initiated" };
    } catch (error) {
        return { status: "download-failed", error };
    } finally {
        link?.remove();
        // Navigation and download handoff can run asynchronously after the click.
        if (url) browser.setTimeout(() => browser.URL.revokeObjectURL(url), 60_000);
    }
}

function writeFailure(error) {
    if (error?.name === "NotAllowedError" || error?.name === "SecurityError") return "permission-denied";
    if (error?.name === "QuotaExceededError") return "storage-error";
    return "write-failed";
}

/** Call directly from a user action. A resolved close is the confirmation of saving. */
export async function saveSvgDirect(blob, filename, browser = globalThis) {
    if (!supportsDirectSave(browser)) return { status: "direct-save-unsupported" };
    let handle;
    try {
        handle = await browser.showSaveFilePicker({
            suggestedName: safeFilename(filename),
            types: [{ description: "SVG image", accept: { [SVG_TYPE]: [".svg"] } }],
        });
    } catch (error) {
        if (error?.name === "AbortError") return { status: "cancelled" };
        return { status: writeFailure(error), error };
    }
    if (typeof handle?.createWritable !== "function") return { status: "direct-save-unsupported" };

    let writable;
    try {
        writable = await handle.createWritable();
        await writable.write(blob);
        await writable.close();
        return { status: "saved" };
    } catch (error) {
        try {
            await writable?.abort();
        } catch {
            // The browser may already have closed or errored the stream.
        }
        return { status: writeFailure(error), error };
    }
}

/** Prepare the displayed snapshot and start the selected save mechanism in the same user action. */
export async function exportChart(svg, options = {}, browser = globalThis) {
    const { metadata, filename, mode = "auto" } = options;
    let blob;
    try {
        blob = createSvgBlob(serializeSvg(prepareStandaloneSvg(svg, metadata)));
    } catch (error) {
        return { status: "preparation-failed", error };
    }
    if (mode === "direct" || (mode === "auto" && supportsDirectSave(browser))) {
        return saveSvgDirect(blob, filename, browser);
    }
    return downloadSvg(blob, filename, browser);
}
