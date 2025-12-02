// timetable/static/timetable/js/app.js

document.addEventListener("DOMContentLoaded", () => {
    console.log("app.js loaded");

    const statusEl = document.getElementById("status-message");
    const generateForm = document.getElementById("generate-form");
    const footerYear = document.getElementById("footer-year");

    // ---------- Footer year ----------
    if (footerYear) {
        footerYear.textContent = new Date().getFullYear().toString();
    }

    // ---------- Status / toast helper ----------
    function showStatus(message, type = "success", timeout = 3500) {
        if (!statusEl) {
            console.log(type.toUpperCase(), message);
            return;
        }
        statusEl.textContent = message;
        statusEl.className = "tt-status__toast tt-status__toast--visible";

        if (type === "success") {
            statusEl.classList.add("tt-status__toast--success");
        } else if (type === "error") {
            statusEl.classList.add("tt-status__toast--error");
        }

        if (timeout) {
            setTimeout(() => {
                statusEl.classList.remove("tt-status__toast--visible");
            }, timeout);
        }
    }

    // ---------- Generate form hint ----------
    if (generateForm) {
        generateForm.addEventListener("submit", () => {
            showStatus("Generating timetable… please wait.", "success", 5000);
        });
    }

    // ---------- Slot click debug (optional) ----------
    document.querySelectorAll(".tt-slot").forEach((slot) => {
        slot.addEventListener("click", () => {
            const subject = slot.querySelector(".tt-slot__subject");
            if (subject) {
                console.debug("Clicked slot:", subject.textContent.trim());
            }
        });
    });

    // ---------- Export libs check ----------
    console.log("html2canvas:", window.html2canvas);
    console.log("jspdf:", window.jspdf);

    const hasHtml2Canvas = typeof window.html2canvas !== "undefined";
    const hasJsPdf = window.jspdf && window.jspdf.jsPDF;

    if (!hasHtml2Canvas || !hasJsPdf) {
        showStatus(
            "Export libraries not loaded (html2canvas/jsPDF). PNG/PDF export disabled.",
            "error",
            8000
        );
    }

    // ---------- Core export helper (PNG / PDF) ----------
    async function exportElementAs(format, element, filenameBase) {
        if (!hasHtml2Canvas || !hasJsPdf) {
            showStatus("Export libraries not loaded.", "error");
            return;
        }
        if (!element) {
            showStatus("Timetable element not found.", "error");
            return;
        }

        element.style.boxShadow = "0 0 0 2px rgba(59,130,246,0.7)";
        element.style.transition = "box-shadow 180ms ease-out";
        setTimeout(() => {
            element.style.boxShadow = "";
        }, 250);

        try {
            const canvas = await window.html2canvas(element, {
                backgroundColor: "#020617",
                scale: 2,
            });

            const imgData = canvas.toDataURL("image/png");
            const safeName = filenameBase.replace(/\s+/g, "_");

            if (format === "png") {
                const a = document.createElement("a");
                a.href = imgData;
                a.download = `${safeName}.png`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                showStatus(`Downloaded ${safeName}.png`, "success");
                return;
            }

            if (format === "pdf") {
                const { jsPDF } = window.jspdf;
                const pdf = new jsPDF("l", "pt", "a4");
                const pageWidth = pdf.internal.pageSize.getWidth();
                const pageHeight = pdf.internal.pageSize.getHeight();

                const ratio = Math.min(
                    pageWidth / canvas.width,
                    pageHeight / canvas.height
                );
                const imgWidth = canvas.width * ratio;
                const imgHeight = canvas.height * ratio;
                const x = (pageWidth - imgWidth) / 2;
                const y = (pageHeight - imgHeight) / 2;

                pdf.addImage(imgData, "PNG", x, y, imgWidth, imgHeight);
                pdf.save(`${safeName}.pdf`);
                showStatus(`Downloaded ${safeName}.pdf`, "success");
            }
        } catch (e) {
            console.error("Export error:", e);
            showStatus("Error during export (check console).", "error");
        }
    }

    // ==========================================================
    // CLASS EXPORTS (Dashboard: per class + all classes)
    // ==========================================================

    async function exportClass(classId, format) {
        console.log("exportClass called", { classId, format });
        const card = document.getElementById(`class-card-${classId}`);
        if (!card) {
            showStatus("Class card not found.", "error");
            return;
        }
        const wrapper = card.querySelector(".tt-class-card__table-wrapper");
        const name = card.getAttribute("data-class-name") || `class-${classId}`;
        await exportElementAs(format, wrapper, `timetable-${name}`);
    }

    async function exportAllClassesPdf() {
        if (!hasHtml2Canvas || !hasJsPdf) {
            showStatus("Export libraries not loaded.", "error");
            return;
        }
        const cards = Array.from(document.querySelectorAll(".tt-class-card"));
        if (!cards.length) {
            showStatus("No class timetables to export.", "error");
            return;
        }

        showStatus("Preparing all class timetables as PDF…", "success", 7000);

        const { jsPDF } = window.jspdf;
        const pdf = new jsPDF("l", "pt", "a4");
        const pageWidth = pdf.internal.pageSize.getWidth();
        const pageHeight = pdf.internal.pageSize.getHeight();
        let first = true;

        for (const card of cards) {
            const name = card.getAttribute("data-class-name") || "class";
            const wrapper = card.querySelector(".tt-class-card__table-wrapper");
            if (!wrapper) continue;

            const canvas = await window.html2canvas(wrapper, {
                backgroundColor: "#020617",
                scale: 2,
            });
            const imgData = canvas.toDataURL("image/png");

            const ratio = Math.min(
                pageWidth / canvas.width,
                pageHeight / canvas.height
            );
            const imgWidth = canvas.width * ratio;
            const imgHeight = canvas.height * ratio;
            const x = (pageWidth - imgWidth) / 2;
            const y = (pageHeight - imgHeight) / 2;

            if (!first) pdf.addPage();
            first = false;

            pdf.addImage(imgData, "PNG", x, y, imgWidth, imgHeight);
            pdf.setTextColor(230, 230, 230);
            pdf.setFontSize(14);
            pdf.text(String(name), 30, 30);
        }

        pdf.save("timetable-all-classes.pdf");
        showStatus("Downloaded timetable-all-classes.pdf", "success", 5000);
    }

    // Bind per-class export buttons (Dashboard)
    document
        .querySelectorAll("[data-export][data-class-id]")
        .forEach((btn) => {
            btn.addEventListener("click", async () => {
                const format = btn.getAttribute("data-export"); // "png" or "pdf"
                const cid = btn.getAttribute("data-class-id");
                if (!cid || !format) return;
                console.log("Class button clicked", { cid, format });
                await exportClass(cid, format);
            });
        });

    // Bind "Download all classes (PDF)" button (Dashboard)
    const btnExportAllPdf = document.getElementById("btn-export-all-pdf");
    if (btnExportAllPdf) {
        btnExportAllPdf.addEventListener("click", async () => {
            await exportAllClassesPdf();
        });
    }

    // ==========================================================
    // TEACHER EXPORTS (Teachers module: per teacher)
    // ==========================================================

    async function exportTeacher(teacherId, format) {
        console.log("exportTeacher called", { teacherId, format });
        const card = document.getElementById(`teacher-card-${teacherId}`);
        if (!card) {
            showStatus("Teacher card not found.", "error");
            return;
        }
        const wrapper = card.querySelector(".tt-teacher-card__table-wrapper");
        const name = card.getAttribute("data-teacher-name") || `teacher-${teacherId}`;
        await exportElementAs(format, wrapper, `teacher-${name}`);
    }

    // Bind per-teacher export buttons (Teachers page)
    document
        .querySelectorAll("[data-export-teacher][data-teacher-id]")
        .forEach((btn) => {
            btn.addEventListener("click", async () => {
                const tid = btn.getAttribute("data-teacher-id");
                const format = btn.getAttribute("data-export-teacher"); // "png" or "pdf"
                if (!tid || !format) return;
                console.log("Teacher button clicked", { tid, format });
                await exportTeacher(tid, format);
            });
        });

    // ==========================================================
    // TEACHER SEARCH FILTER
    // ==========================================================

    const teacherSearchInput = document.getElementById("teacher-search");
    if (teacherSearchInput) {
        console.log("Teacher search input found, enabling filter");

        teacherSearchInput.addEventListener("input", () => {
            const query = teacherSearchInput.value.trim().toLowerCase();
            console.log("Teacher search query:", query);

            document.querySelectorAll(".tt-teacher-card").forEach((card) => {
                const haystack = (card.getAttribute("data-teacher-search") || "").toLowerCase();

                if (!query || haystack.includes(query)) {
                    card.style.display = "";
                } else {
                    card.style.display = "none";
                }
            });
        });
    } else {
        console.log("Teacher search input NOT found on this page.");
    }
});