const esc = (value) => String(value ?? "").replace(
  /[&<>"']/g,
  (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char],
);

const REVEALED_MONTHS_KEY = "cm-rotation-revealed-months";
const state = {
  data: null,
  selectedMonth: null,
  revealedMonths: loadRevealedMonths(),
};
const currentMonth = new Date().toISOString().slice(0, 7);

function loadRevealedMonths() {
  try {
    const value = JSON.parse(localStorage.getItem(REVEALED_MONTHS_KEY) || "[]");
    return new Set(Array.isArray(value) ? value : []);
  } catch {
    return new Set();
  }
}

function rememberRevealedMonth(month) {
  state.revealedMonths.add(month);
  try {
    localStorage.setItem(REVEALED_MONTHS_KEY, JSON.stringify([...state.revealedMonths]));
  } catch {
    // Storage can be blocked by browser privacy settings; the current reveal still works.
  }
}

function peopleFor(status) {
  return state.data.months.flatMap((month) =>
    (month.presenters || [])
      .filter((person) => person.status === status)
      .map((person) => ({ ...person, month: month.month })),
  );
}

function personRow(person) {
  return `<tr class="${esc(person.status)}"><td class="month">${esc(person.month.replace("-", "."))}</td><td class="name">${esc(person.name)}</td><td>${esc(person.department || "-")}</td><td>${esc(person.jobTitle || "-")}</td></tr>`;
}

function renderCompletedTable() {
  const people = peopleFor("completed");
  document.getElementById("completed-table").innerHTML = people.length
    ? people.map(personRow).join("")
    : '<tr><td class="empty" colspan="4">표시할 발표자가 없습니다.</td></tr>';
}

function renderScheduledTable() {
  const months = state.data.months.filter((month) => month.assignedCount > month.completedCount);
  const rows = months.flatMap((month) => {
    if (!state.revealedMonths.has(month.month)) {
      return [`<tr class="scheduled concealed"><td class="month">${esc(month.month.replace("-", "."))}</td><td class="name">공개 전</td><td colspan="2">${esc(month.assignedCount)}명 사전 추첨 완료</td></tr>`];
    }
    return (month.presenters || [])
      .filter((person) => person.status === "scheduled")
      .map((person) => personRow({ ...person, month: month.month }));
  });
  document.getElementById("scheduled-table").innerHTML = rows.length
    ? rows.join("")
    : '<tr><td class="empty" colspan="4">표시할 발표자가 없습니다.</td></tr>';
}

function renderStage() {
  const month = state.data.months.find((item) => item.month === state.selectedMonth);
  const stage = document.getElementById("stage");
  const button = document.getElementById("show-result");
  const isRevealed = month && state.revealedMonths.has(month.month);

  button.disabled = !month?.assignedCount;
  button.textContent = month?.assignedCount
    ? isRevealed
      ? "🎉 결과 다시 보기"
      : "🎉 3명 발표자 공개"
    : "아직 추첨 전";

  if (!month || !month.assignedCount) {
    stage.innerHTML = "아직 사전 추첨되지 않은 월입니다. 다음 발표 순서가 확정되면 자동으로 준비됩니다.";
    return;
  }
  if (!isRevealed) {
    stage.innerHTML = `<div><strong>${esc(month.month.replace("-", "."))} · ${esc(month.assignedCount)}명</strong><span>사전 추첨이 완료되었습니다. 타운홀에서 결과를 공개해 주세요.</span></div>`;
    return;
  }

  const people = (month.presenters || []).map(
    (person) => `<div class="stage-person"><b>${esc(person.name)}</b><span>${esc(person.department || person.jobTitle || "")}</span></div>`,
  ).join("");
  stage.innerHTML = state.data.cycle.showNames
    ? `<div><strong>${esc(month.month.replace("-", "."))} · ${esc(month.assignedCount)}명</strong><div class="stage-people">${people}</div></div>`
    : `<div><strong>${esc(month.month.replace("-", "."))} · ${esc(month.assignedCount)}명</strong><span>발표자 선정 완료</span></div>`;
}

function showResult() {
  const month = state.data.months.find((item) => item.month === state.selectedMonth);
  if (!month || month.assignedCount !== state.data.cycle.monthlyTarget) {
    alert(`이 달의 발표자는 ${month?.assignedCount || 0}명입니다.`);
    return;
  }

  rememberRevealedMonth(month.month);
  renderStage();
  renderScheduledTable();

  const people = state.data.cycle.showNames
    ? (month.presenters || []).map(
      (person) => `<div class="winner"><b>${esc(person.name)}</b><span>${esc([person.department, person.jobTitle].filter(Boolean).join(" · "))}</span></div>`,
    ).join("")
    : `<div class="winner"><b>${esc(month.assignedCount)}명</b><span>발표자 선정 완료</span></div>`;
  document.getElementById("result-content").innerHTML = `<div class="result-month">${esc(month.month.replace("-", "."))} CM 발표자 추첨 결과</div><h2 class="result-title">🎉 축하합니다! 🎉</h2><div class="winner-grid">${people}</div>`;

  const colors = ["#ffd24a", "#74d8c4", "#80b8ff", "#ff7f96", "#f7f9ff"];
  document.getElementById("result-confetti").innerHTML = Array.from(
    { length: 72 },
    (_, index) => `<i style="--x:${(index * 37) % 101}%;--w:${5 + index % 6}px;--h:${9 + index % 9}px;--color:${colors[index % colors.length]};--duration:${4.6 + (index % 13) * 0.18}s;--delay:${-((index * 17) % 60) / 10}s;--drift:${-70 + (index * 29) % 140}px;--rotate:${(index * 47) % 180}deg"></i>`,
  ).join("");
  document.getElementById("result-dialog").showModal();
}

function render(data, preferredMonth = null) {
  state.data = data;
  document.getElementById("cycle-label").textContent = `CM 활동 기간 ${data.cycle.startMonth.replace("-", ".")} ~ ${data.cycle.endMonth.replace("-", ".")} · 월 ${data.cycle.monthlyTarget}명`;

  const available = data.months.filter((month) =>
    (month.month >= data.cycle.allocationStartMonth && month.month <= data.cycle.planningEndMonth)
      || month.assignedCount > 0,
  );
  const firstPending = available.find((month) => month.assignedCount > month.completedCount);
  const firstUndrawn = available.find((month, index) =>
    !month.assignedCount && (index === 0 || available[index - 1].completedCount >= data.cycle.monthlyTarget),
  );
  const selected = available.find((month) => month.month === preferredMonth)
    || firstPending
    || firstUndrawn
    || available.find((month) => month.month === currentMonth)
    || available.at(-1);
  state.selectedMonth = selected?.month || available[0]?.month;

  const select = document.getElementById("month-select");
  select.innerHTML = available.map((month) => {
    const label = month.assignedCount
      ? month.completedCount === month.assignedCount
        ? "완료"
        : state.revealedMonths.has(month.month)
          ? "공개 완료"
          : "사전 추첨 완료 · 공개 전"
      : "추첨 전";
    return `<option value="${esc(month.month)}"${month.month === state.selectedMonth ? " selected" : ""}>${esc(month.month.replace("-", "."))} · ${label}</option>`;
  }).join("");

  const summary = [
    ["대상", data.summary.eligibleCount],
    ["발표 완료", data.summary.completedCount],
    ["발표 예정", data.summary.scheduledCount],
    ["남은 인원", data.summary.remainingCount],
  ];
  document.getElementById("summary").innerHTML = summary.map(
    ([label, value]) => `<div class="summary-card"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`,
  ).join("");
  renderCompletedTable();
  renderScheduledTable();
  renderStage();
}

document.getElementById("month-select").addEventListener("change", (event) => {
  state.selectedMonth = event.target.value;
  renderStage();
});
document.getElementById("show-result").addEventListener("click", showResult);
document.getElementById("result-close").addEventListener("click", () => document.getElementById("result-dialog").close());
document.getElementById("result-dialog").addEventListener("click", (event) => {
  if (event.target.closest(".result-content")) return;
  document.getElementById("result-dialog").close();
});
fetch("data/presenter-rotation.json", { cache: "no-cache" })
  .then((response) => {
    if (!response.ok) throw new Error(response.status);
    return response.json();
  })
  .then((data) => render(data))
  .catch(() => {
    document.getElementById("stage").textContent = "발표 일정 데이터를 불러오지 못했습니다.";
  });

window.rotationPage = { state, render, renderStage, showResult, esc };
