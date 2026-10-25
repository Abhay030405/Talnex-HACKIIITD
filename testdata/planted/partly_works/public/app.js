// NoteBox: notes live in the browser (localStorage). No account is needed.
// Planted on purpose for TalNex: Pin does nothing, an empty title is not refused, and the counter ignores deletes.
// There is no PDF export at all (the "control" claim in the expected file).
const KEY = "notebox.v1";
let state = load();
let query = "";
let editing = null;
let shownCount = state.notes.length;

function load() {
  try {
    const s = JSON.parse(localStorage.getItem(KEY));
    if (s && Array.isArray(s.notes)) return s;
  } catch (e) { /* start empty */ }
  return { notes: [], next: 1 };
}
function save() { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) { /* ignore */ } }
const $ = (id) => document.getElementById(id);

$("add-form").addEventListener("submit", (ev) => {
  ev.preventDefault();
  // BUG (planted): an empty title is accepted and saved as "Untitled".
  const title = $("title").value.trim() || "Untitled";
  state.notes.push({ id: state.next++, title, body: $("body").value.trim(), pinned: false });
  shownCount += 1;
  save();
  $("title").value = "";
  $("body").value = "";
  $("msg").textContent = `Added "${title}".`;
  render();
});

$("search").addEventListener("input", (e) => { query = e.target.value; render(); });

function render() {
  const q = query.toLowerCase();
  const list = $("notes");
  list.innerHTML = "";
  const shown = state.notes.filter((n) => !q || n.title.toLowerCase().includes(q) || n.body.toLowerCase().includes(q));
  for (const n of shown) list.appendChild(editing === n.id ? editRow(n) : noteRow(n));
  $("empty").hidden = shown.length > 0;
  // BUG (planted): the counter goes up when a note is added but is never lowered when one is deleted.
  $("count").textContent = `${shownCount} note${shownCount === 1 ? "" : "s"}`;
}

function noteRow(n) {
  const li = document.createElement("li");
  li.className = "note";
  const head = document.createElement("div");
  const name = document.createElement("span");
  name.className = "name";
  name.textContent = n.title;
  head.appendChild(name);
  const body = document.createElement("div");
  body.textContent = n.body;
  const row = document.createElement("div");
  row.className = "row";

  // BUG (planted): Pin is only a button; the note is neither moved to the top nor labelled.
  const pin = document.createElement("button");
  pin.type = "button"; pin.className = "plain"; pin.textContent = "Pin";
  pin.onclick = () => { n.pinned = true; save(); };

  const edit = document.createElement("button");
  edit.type = "button"; edit.className = "plain"; edit.textContent = "Edit";
  edit.onclick = () => { editing = n.id; render(); };
  const del = document.createElement("button");
  del.type = "button"; del.className = "plain"; del.textContent = "Delete";
  del.onclick = () => { state.notes = state.notes.filter((x) => x.id !== n.id); save(); render(); };
  row.append(pin, edit, del);
  li.append(head, body, row);
  return li;
}

function editRow(n) {
  const li = document.createElement("li");
  li.className = "note";
  const form = document.createElement("form");
  form.innerHTML = `<label>Title <input name="t"></label><label>Note <input name="b"></label>
    <button type="submit">Save</button><button type="button" class="plain">Cancel</button>`;
  form.t.value = n.title;
  form.b.value = n.body;
  form.onsubmit = (ev) => {
    ev.preventDefault();
    if (form.t.value.trim()) n.title = form.t.value.trim();
    n.body = form.b.value.trim();
    editing = null; save(); render();
  };
  form.querySelector("button.plain").onclick = () => { editing = null; render(); };
  li.appendChild(form);
  return li;
}

render();
