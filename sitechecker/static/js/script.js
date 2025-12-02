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
                row.querySelector(".status-code").innerText = data.status;
                row.querySelector(".response-time").innerText = data.response_time + " c";

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
                document.getElementById("count-ok").innerText = data.counts.ok;
                document.getElementById("count-warn").innerText = data.counts.warn;
                document.getElementById("count-err").innerText = data.counts.err;
            });
    }, 10000);

    // ---- Автообновление таблицы ----
    setInterval(() => {
        fetch("/")
            .then(r => r.text())
            .then(html => {
                const parser = new DOMParser();
                const doc = parser.parseFromString(html, "text/html");

                const newBody = doc.querySelector("#site-table-body").innerHTML;
                document.querySelector("#site-table-body").innerHTML = newBody;

                attachCheckHandlers();
            });
    }, 60000);
});