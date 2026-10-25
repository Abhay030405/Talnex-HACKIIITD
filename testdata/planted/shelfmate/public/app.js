// ShelfMate: everything lives in the browser (localStorage). No account is needed.
// Planted on purpose for TalNex: the CSV export and the goal progress bar do not do what they promise.
const KEY = "shelfmate.v1";
const LABEL = { want: "Want to read", reading: "Reading", finished: "Finished" };

let state = load();
let filter = "all";
let query = "";
let editing = null;

function load() {
  try {
    const s = JSON.parse(localStorage.getItem(KEY));
    if (s && Array.isArray(s.books)) return s;
  } catch (e) { /* start empty */ }
  return { books: [], goal: 0, next: 1 };
}
function save() { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) { /* ignore */ } }

const $ = (id) => document.getElementById(id);

function addBook(ev) {
  ev.preventDefault();
  const title = $("title").value.trim();
  const author = $("author").value.trim();
  const msg = $("add-msg");
  if (!title || !author) {
    msg.textContent = "Please enter both a title and an author.";
    msg.className = "msg err";
    return;
  }
  state.books.push({ id: state.next++, title, author, status: "want", rating: 0 });
  save();
  $("title").value = "";
  $("author").value = "";
  msg.textContent = `Added "${title}".`;
  msg.className = "msg";
  render();
}

function visibleBooks() {
  const q = query.toLowerCase();
  return state.books.filter((b) =>
    (filter === "all" || b.status === filter) &&
    (!q || b.title.toLowerCase().includes(q) || b.author.toLowerCase().includes(q)));
}

function render() {
  const list = $("books");
  list.innerHTML = "";
  const shown = visibleBooks();
  for (const b of shown) list.appendChild(editing === b.id ? editRow(b) : bookRow(b));
  $("empty").hidden = shown.length > 0;
  $("count").textContent = `${state.books.length} book${state.books.length === 1 ? "" : "s"} on your shelf`;

  const rated = state.books.filter((b) => b.status === "finished" && b.rating > 0);
  $("avg").textContent = rated.length
    ? `Average rating: ${(rated.reduce((n, b) => n + b.rating, 0) / rated.length).toFixed(1)} from ${rated.length} finished book${rated.length === 1 ? "" : "s"}`
    : "Average rating: no rated books yet";

  document.querySelectorAll("#tabs button").forEach((t) => t.classList.toggle("on", t.dataset.filter === filter));
  renderGoal();
}

function bookRow(b) {
  const li = document.createElement("li");
  li.className = "book";
  li.innerHTML = `<div><span class="name"></span> <span class="by"></span></div>`;
  li.querySelector(".name").textContent = b.title;
  li.querySelector(".by").textContent = `by ${b.author}`;

  const row = document.createElement("div");
  row.className = "row";
  const badge = document.createElement("span");
  badge.className = `badge ${b.status}`;
  badge.textContent = LABEL[b.status];
  row.appendChild(badge);

  const sel = document.createElement("select");
  sel.setAttribute("aria-label", `Status of ${b.title}`);
  for (const k of Object.keys(LABEL)) {
    const o = document.createElement("option");
    o.value = k; o.textContent = LABEL[k]; o.selected = b.status === k;
    sel.appendChild(o);
  }
  sel.onchange = () => { b.status = sel.value; if (b.status !== "finished") b.rating = 0; save(); render(); };
  row.appendChild(sel);

  if (b.status === "finished") {
    const rate = document.createElement("select");
    rate.setAttribute("aria-label", `Rating of ${b.title}`);
    for (let i = 0; i <= 5; i++) {
      const o = document.createElement("option");
      o.value = i; o.textContent = i ? `${i} star${i === 1 ? "" : "s"}` : "Rate";
      o.selected = b.rating === i;
      rate.appendChild(o);
    }
    rate.onchange = () => { b.rating = Number(rate.value); save(); render(); };
    row.appendChild(rate);
  }

  const edit = document.createElement("button");
  edit.type = "button"; edit.className = "plain"; edit.textContent = "Edit";
  edit.onclick = () => { editing = b.id; render(); };
  const del = document.createElement("button");
  del.type = "button"; del.className = "plain"; del.textContent = "Delete";
  del.onclick = () => { state.books = state.books.filter((x) => x.id !== b.id); save(); render(); };
  row.append(edit, del);
  li.appendChild(row);
  return li;
}

function editRow(b) {
  const li = document.createElement("li");
  li.className = "book";
  const form = document.createElement("form");
  form.innerHTML = `<label>Title <input name="t"></label><label>Author <input name="a"></label>
    <button type="submit">Save</button><button type="button" class="plain">Cancel</button>`;
  form.t.value = b.title;
  form.a.value = b.author;
  form.onsubmit = (ev) => {
    ev.preventDefault();
    if (form.t.value.trim() && form.a.value.trim()) { b.title = form.t.value.trim(); b.author = form.a.value.trim(); }
    editing = null; save(); render();
  };
  form.querySelector("button.plain").onclick = () => { editing = null; render(); };
  li.appendChild(form);
  return li;
}

// BUG (planted): the bar is never filled, whatever the number of finished books.
function renderGoal() {
  const done = state.books.filter((b) => b.status === "finished").length;
  $("goal-text").textContent = state.goal ? `Goal: ${state.goal} books this year` : "No goal set yet.";
  $("goal-fill").style.width = "0%";
  void done;
}

function setGoal(ev) {
  ev.preventDefault();
  const n = Number($("goal").value);
  if (n >= 1) { state.goal = Math.floor(n); save(); }
  render();
}

// BUG (planted): the button is wired to nothing that downloads a file.
function exportCsv() {
  $("count").textContent = `${state.books.length} book${state.books.length === 1 ? "" : "s"} on your shelf`;
}

$("add-form").addEventListener("submit", addBook);
$("goal-form").addEventListener("submit", setGoal);
$("search").addEventListener("input", (e) => { query = e.target.value; render(); });
$("tabs").addEventListener("click", (e) => { const f = e.target.dataset.filter; if (f) { filter = f; render(); } });
$("export-btn").addEventListener("click", exportCsv);
render();
