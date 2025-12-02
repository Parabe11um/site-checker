
    document.addEventListener("DOMContentLoaded", function () {
        fetch("/site/{{ site.id }}/response-data/")
            .then(res => res.json())
            .then(data => {
                const ctx = document.getElementById("responseChart").getContext("2d");

                new Chart(ctx, {
                    type: "line",
                    data: {
                        labels: data.labels,
                        datasets: [{
                            label: "Время отклика (сек.)",
                            data: data.values,
                            borderWidth: 2,
                            tension: 0.3
                        }]
                    },
                    options: {
                        responsive: true,
                        scales: {
                            y: { beginAtZero: true }
                        }
                    }
                });
            });
    });

document.addEventListener("DOMContentLoaded", () => {

    document.querySelectorAll(".check-btn").forEach(btn => {

        btn.addEventListener("click", async function (e) {
            e.preventDefault();

            const url = this.dataset.checkUrl;

            this.innerHTML = `
                <svg class="animate-spin h-4 w-4 text-white inline-block" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10"
                        stroke="currentColor" stroke-width="4" fill="none"></circle>
                    <path class="opacity-75" fill="currentColor"
                        d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 100 16v-4l-3 3 3 3v-4a8 8 0 01-8-8z">
                    </path>
                </svg>
                Проверка…
            `;
            this.disabled = true;

            try {
                await fetch(url, { method: "POST" });
                location.reload();
            } catch (err) {
                alert("Ошибка проверки сайта");
            }
        });

    });

});

document.addEventListener("DOMContentLoaded", () => {
    const history = [
        {% for h in history reversed %}
            {
                t: "{{ h.checked_at|date:'H:i' }}",
                ok: {% if h.status_code == 200 %}1{% else %}0{% endif %},
                code: "{{ h.status_code }}"
            },
        {% endfor %}
    ];

    const ctx = document.getElementById("uptimeChart").getContext("2d");

    new Chart(ctx, {
        type: "bar",
        data: {
            labels: history.map(x => x.t),
            datasets: [{
                label: "Доступность",
                data: history.map(x => x.ok),
                borderWidth: 1,
                backgroundColor: history.map(x =>
                    x.ok ? "rgba(34,197,94,0.7)" : "rgba(239,68,68,0.7)"
                ),
            }]
        },
        options: {
            scales: {
                y: { beginAtZero: true, max: 1 },
            }
        }
    });
});
