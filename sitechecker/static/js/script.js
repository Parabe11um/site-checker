function attachCheckHandlers() {
    document.querySelectorAll(".check-btn").forEach(btn => {

        if (btn.dataset.bound === "1") {
            return;
        }

        btn.dataset.bound = "1";

        btn.addEventListener("click", function (event) {
            event.preventDefault();

            const url = this.href;
            const button = this;
            const row = button.closest("tr");

            button.innerHTML = `
                <svg class="animate-spin h-4 w-4 text-white inline-block" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10"
                            stroke="currentColor" stroke-width="4" fill="none"></circle>
                    <path class="opacity-75" fill="currentColor"
                          d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 100 16v-4l-3 3 3 3v-4a8 8 0 01-8-8z"></path>
                </svg>
                Проверка…
            `;
            button.classList.add("opacity-50", "pointer-events-none");

            fetch(url, {
                method: "POST",
                headers: { "X-Requested-With": "XMLHttpRequest" }
            })
            .then(response => response.json())
            .then(() => {
                row.classList.add("bg-green-100");
                setTimeout(() => row.classList.remove("bg-green-100"), 1500);

                button.innerHTML = "Готово";

                refreshDashboard();

                setTimeout(() => {
                    button.innerHTML = "Проверить";
                    button.classList.remove("opacity-50", "pointer-events-none");
                }, 2000);
            })
            .catch(err => {
                console.error(err);
                button.innerHTML = "Ошибка";
                button.classList.remove("opacity-50", "pointer-events-none");
            });
        });

    });
}


function renderStats(stats) {
    const okEl = document.getElementById("stat-ok") || document.getElementById("count-ok");
    const warnEl = document.getElementById("stat-warn") || document.getElementById("count-warn");
    const errEl = document.getElementById("stat-error") || document.getElementById("count-err");

    if (okEl) okEl.innerText = stats.ok ?? 0;
    if (warnEl) warnEl.innerText = stats.warn ?? 0;
    if (errEl) errEl.innerText = stats.error ?? stats.err ?? 0;
}


function getStatusClass(statusCode) {
    statusCode = Number(statusCode);

    if (statusCode >= 200 && statusCode < 300) {
        return "text-emerald-600";
    }

    if (statusCode >= 300 && statusCode < 500) {
        return "text-amber-600";
    }

    return "text-rose-600";
}


function escapeHtml(value) {
    if (value === null || value === undefined) {
        return "";
    }

    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}


function renderRows(rows) {
    const tbody = document.getElementById("site-table-body");

    if (!tbody) {
        return;
    }

    tbody.innerHTML = rows.map(row => {
        const statusClass = getStatusClass(row.status_code);

        return `
            <tr class="hover:bg-slate-50/80 transition">
                <td class="px-4 py-4">
                    <div class="font-medium text-slate-900">${escapeHtml(row.name)}</div>
                    <div class="text-xs text-slate-500">${escapeHtml(row.url)}</div>
                </td>

                <td class="px-4 py-4 text-center">
                    <span class="status-code font-semibold ${statusClass}">
                        ${escapeHtml(row.status_code)}
                    </span>
                </td>

                <td class="px-4 py-4 text-center text-slate-700">
                    <span class="response-time">${escapeHtml(row.response_time)}</span>
                    ${row.median_response_time ? `<div class="text-xs text-slate-400">${escapeHtml(row.median_response_time)}</div>` : ""}
                </td>

                <td class="px-4 py-4 text-center text-slate-700">
                    ${escapeHtml(row.ssl)}
                </td>

                <td class="px-4 py-4 text-center text-slate-700">
                    ${escapeHtml(row.domain)}
                </td>

                <td class="px-4 py-4 text-center text-slate-500 text-sm">
                    ${escapeHtml(row.last_checked_at)}
                </td>

                <td class="px-4 py-4 text-right">
                    <a href="${escapeHtml(row.check_url)}"
                       class="check-btn inline-flex items-center justify-center px-3 py-2 rounded-lg bg-blue-600 text-white text-sm hover:bg-blue-700 transition">
                        Проверить
                    </a>
                </td>

                <td class="px-4 py-4 text-right">
                    <a href="${escapeHtml(row.detail_url)}"
                       class="inline-flex items-center justify-center px-3 py-2 rounded-lg bg-slate-100 text-slate-700 text-sm hover:bg-slate-200 transition">
                        Подробнее
                    </a>
                </td>

                <td class="px-4 py-4 text-right">
                    <a href="${escapeHtml(row.delete_url)}"
                       onclick="return confirm('Удалить сайт из мониторинга?')"
                       class="inline-flex items-center justify-center px-3 py-2 rounded-lg bg-red-50 text-red-600 text-sm hover:bg-red-100 transition">
                        Удалить
                    </a>
                </td>
            </tr>
        `;
    }).join("");

    attachCheckHandlers();
}


async function refreshDashboard() {
    try {
        const response = await fetch("/dashboard/sites-data/", {
            headers: {
                "X-Requested-With": "XMLHttpRequest"
            }
        });

        const data = await response.json();

        renderStats(data.stats);
        renderRows(data.rows);

    } catch (error) {
        console.error("Ошибка обновления dashboard:", error);
    }
}


document.addEventListener("DOMContentLoaded", () => {
    attachCheckHandlers();

    refreshDashboard();

    setInterval(refreshDashboard, 30000);
});
