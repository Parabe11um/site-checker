function attachCheckHandlers() {
    document.querySelectorAll(".check-btn").forEach(btn => {

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
            .then(data => {

                const statusEl = row.querySelector(".status-code");
                const timeEl = row.querySelector(".response-time");

                if (statusEl) statusEl.innerText = data.status;
                if (timeEl) timeEl.innerText = data.response_time + " c";

                // Подсветка строки
                row.classList.add("bg-green-100");
                setTimeout(() => row.classList.remove("bg-green-100"), 1500);

                button.innerHTML = "Готово";
                setTimeout(() => {
                    button.innerHTML = "Проверить";
                    button.classList.remove("opacity-50", "pointer-events-none");
                }, 2000);
            })
            .catch(err => console.error(err));
        });

    });
}

document.addEventListener("DOMContentLoaded", () => {

    attachCheckHandlers();

    // ---- Автообновление dashboard ----
    setInterval(() => {
        fetch("/dashboard/status/")
            .then(r => r.json())
            .then(data => {

                const okEl = document.getElementById("count-ok");
                const warnEl = document.getElementById("count-warn");
                const errEl = document.getElementById("count-err");

                if (okEl) okEl.innerText = data.counts.ok;
                if (warnEl) warnEl.innerText = data.counts.warn;
                if (errEl) errEl.innerText = data.counts.err;

            })
            .catch(() => {});
    }, 10000);


    // ---- Автообновление таблицы ----
    setInterval(() => {
        fetch("/")
            .then(r => r.text())
            .then(html => {
                const parser = new DOMParser();
                const doc = parser.parseFromString(html, "text/html");

                const newBodyWrapper = doc.querySelector("#site-table-body");
                const bodyWrapper = document.querySelector("#site-table-body");

                if (newBodyWrapper && bodyWrapper) {
                    bodyWrapper.innerHTML = newBodyWrapper.innerHTML;
                    attachCheckHandlers();
                }
            })
            .catch(() => {});
    }, 60000);
});
