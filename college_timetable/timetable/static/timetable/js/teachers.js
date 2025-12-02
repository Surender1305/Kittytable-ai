// timetable/static/timetable/js/teacher.js

document.addEventListener("DOMContentLoaded", () => {
    const statusEl = document.getElementById("status-message");
    const footerYear = document.getElementById("footer-year");

    if (footerYear) {
        footerYear.textContent = new Date().getFullYear().toString();
    }

    function showStatus(message, type = "success", timeout = 3500) {
        if (!statusEl) return;
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

    const hasHtml2Canvas = typeof window.html2canvas !== "undefined";
    const hasJsPdf = window.jspdf && window.jspdf.jsPDF;

    if (!hasHtml2Canvas || !hasJsPdf) {
        console.warn("html2canvas or jsPDF not loaded; export will not work.");
    }

    async function exportElement(format, element, filenameBase) {
        if (!hasHtml2Canvas || !hasJsPdf) {
            showStatus("Export libraries not loaded (check CDN / internet).", "error");
            return;
        }
        if (!element) {
            showStatus("Nothing to export (element not found).", "error");
            return;
        }

        // Highlight element briefly
        element.style.boxShadow = "0 0 0 2px rgba(59,130,246,0.7)";
        setTimeout(() => {
            element.style.boxShadow = "";
        }, 250);

        try {
            const canvas = await window.html2canvas(element, {
                backgroundColor: "#020617",
                scale: 2
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
            console.error(e);
            showStatus("Error while exporting (see console).", "error");
        }
    }

    async function exportTeacher(teacherId, format) {
        const card = document.getElementById(`teacher-card-${teacherId}`);
        if (!card) {
            showStatus("Teacher card not found.", "error");
            return;
        }
        const wrapper = card.querySelector(".tt-teacher-card__table-wrapper");
        const name = card.getAttribute("data-teacher-name") || `teacher-${teacherId}`;
        await exportElement(format, wrapper, `timetable-${name}`);
    }

    // Per-teacher buttons
    document.querySelectorAll("[data-export-teacher][data-teacher-id]").forEach((btn) => {
        btn.addEventListener("click", () => {
            const tid = btn.getAttribute("data-teacher-id");
            const format = btn.getAttribute("data-export-teacher"); // "png" or "pdf"
            exportTeacher(tid, format);
        });
    });

    // Export all teachers into one PDF
    const btnAll = document.getElementById("btn-export-all-teachers-pdf");
    if (btnAll && hasHtml2Canvas && hasJsPdf) {
        btnAll.addEventListener("click", async () => {
            const cards = Array.from(document.querySelectorAll(".tt-teacher-card"));
            if (!cards.length) {
                showStatus("No teachers to export.", "error");
                return;
            }

            showStatus("Preparing all teacher timetables as PDF…", "success", 7000);

            const { jsPDF } = window.jspdf;
            const pdf = new jsPDF("l", "pt", "a4");
            const pageWidth = pdf.internal.pageSize.getWidth();
            const pageHeight = pdf.internal.pageSize.getHeight();
            let first = true;

            for (const card of cards) {
                const name = card.getAttribute("data-teacher-name") || "teacher";
                const wrapper = card.querySelector(".tt-teacher-card__table-wrapper");
                if (!wrapper) continue;

                const canvas = await window.html2canvas(wrapper, {
                    backgroundColor: "#020617",
                    scale: 2
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

            pdf.save("timetable-all-teachers.pdf");
            showStatus("Downloaded timetable-all-teachers.pdf", "success", 5000);
        });
    }
});