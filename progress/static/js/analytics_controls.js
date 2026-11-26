for (const form of document.querySelectorAll("form[data-autosubmit]")) {
    form.querySelector('button[type="submit"]').hidden = true;
    for (const picker of form.querySelectorAll("select")) {
        picker.addEventListener("change", () => form.requestSubmit());
    }
}

const period = document.querySelector("#period");
const periodForm = period.form;
const dateControls = periodForm.querySelectorAll("[data-custom-period]");

function showCustomDates() {
    const custom = period.value === "custom";
    for (const control of dateControls) {
        control.hidden = !custom;
        const input = control.querySelector("input");
        if (input) input.disabled = !custom;
    }
}

showCustomDates();
period.addEventListener("change", () => {
    showCustomDates();
    if (period.value !== "custom") periodForm.requestSubmit();
});
