"""Copy detection by code shape: renaming does not hide a copy, starter code is removed, unrelated code does not match."""
import json
import subprocess
import sys

from talnex_ai.checks.copy_between_teams import fingerprint as fp
from talnex_ai.checks.copy_between_teams.compare import Team, compare, level_for, starter_threshold

TODOS = """
// todo list
const items = [];
function addTodo(text) {
  if (!text || text.trim() === '') { showMessage('Please type something'); return; }
  items.push({ id: Date.now(), text: text.trim(), done: false });
  save();
  render();
}
function toggleTodo(id) {
  const found = items.find(t => t.id === id);
  if (found) { found.done = !found.done; }
  save(); render();
}
function removeTodo(id) {
  const idx = items.findIndex(t => t.id === id);
  if (idx >= 0) { items.splice(idx, 1); }
  save(); render();
}
function leftCount() { return items.filter(t => !t.done).length; }
function save() { localStorage.setItem('todos', JSON.stringify(items)); }
"""

# the same logic with every name changed, other comments and other strings
RENAMED = """
/* tasks */
const tasks = [];
function createTask(label) {
  if (!label || label.trim() === '') { notify('Write a task'); return; }
  tasks.push({ key: Date.now(), label: label.trim(), finished: false });
  persist();
  draw();
}
function flipTask(key) {
  const hit = tasks.find(x => x.key === key);
  if (hit) { hit.finished = !hit.finished; }
  persist(); draw();
}
function dropTask(key) {
  const pos = tasks.findIndex(x => x.key === key);
  if (pos >= 0) { tasks.splice(pos, 1); }
  persist(); draw();
}
function remaining() { return tasks.filter(x => !x.finished).length; }
function persist() { localStorage.setItem('tasks-v2', JSON.stringify(tasks)); }
"""

OTHER = """
import express from 'express';
const app = express();
app.get('/weather/:city', async (req, res) => {
  const key = process.env.WEATHER_KEY;
  const r = await fetch(`https://api.example.com/w?q=${req.params.city}&k=${key}`);
  if (!r.ok) { return res.status(502).json({ error: 'upstream failed' }); }
  const body = await r.json();
  res.json({ temp: body.main.temp, wind: body.wind.speed, sky: body.weather[0].main });
});
app.listen(3000, () => console.log('listening'));
"""


def team(tid, **files):
    return Team(tid, tid, {p: fp.fingerprint_text(t, ".js") for p, t in files.items()})


class TestFingerprint:
    def test_renaming_everything_keeps_the_fingerprint(self):
        a, b = set(fp.fingerprint_text(TODOS, ".js")), set(fp.fingerprint_text(RENAMED, ".js"))
        assert len(a) > 30 and len(a & b) / min(len(a), len(b)) > 0.8

    def test_unrelated_code_does_not_match(self):
        a, c = set(fp.fingerprint_text(TODOS, ".js")), set(fp.fingerprint_text(OTHER, ".js"))
        assert len(a & c) / min(len(a), len(c)) < 0.1

    def test_comments_and_strings_do_not_matter(self):
        louder = "// a long note about this code\n" + TODOS.replace("'Please type something'", "'Nothing to add'") + "/* more */"
        assert set(fp.fingerprint_text(TODOS, ".js")) == set(fp.fingerprint_text(louder, ".js"))

    def test_a_tiny_file_says_too_little(self):
        assert fp.fingerprint_text("const a = 1;", ".js") == []

    def test_which_files_are_read(self):
        assert fp.wanted("src/app.js") and fp.wanted("api/index.py")
        assert not fp.wanted("node_modules/x/a.js") and not fp.wanted("package-lock.json") and not fp.wanted("dist/app.min.js") and not fp.wanted("README.md")

    def test_the_script_runs_on_a_real_folder_the_way_the_vm_runs_it(self, tmp_path):
        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
        (tmp_path / "todo.js").write_text(TODOS)
        (tmp_path / "README.md").write_text("# hi")
        subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
        out = subprocess.run([sys.executable, fp.__file__, str(tmp_path)], capture_output=True, text=True, check=True).stdout
        data = json.loads(out)
        assert list(data["files"]) == ["todo.js"] and len(data["files"]["todo.js"]) > 30


class TestCompare:
    def test_a_renamed_copy_is_found_and_an_unrelated_team_is_not(self):
        out = compare([team("A", **{"todo.js": TODOS}), team("B", **{"tasks.js": RENAMED}), team("C", **{"weather.js": OTHER})])
        by = {(p.a_id, p.b_id): p for p in out.pairs}
        assert by[("A", "B")].shared_pct > 70 and by[("A", "C")].shared_pct < 10 and by[("B", "C")].shared_pct < 10
        assert by[("A", "B")].matching_files[0]["a_file"] == "todo.js" and by[("A", "B")].matching_files[0]["b_file"] == "tasks.js"

    def test_code_many_teams_share_is_starter_code_and_is_removed(self, monkeypatch):
        monkeypatch.setattr("talnex_ai.checks.copy_between_teams.compare.MIN_OWN_HASHES", 10)   # the made-up teams here have little code
        starter = TODOS     # every team started from the same template
        teams = [team(n, **{"starter.js": starter, "own.js": own}) for n, own in
                 (("A", OTHER), ("B", OTHER.replace("weather", "news").replace("sky", "tag") + "\nconst z = 1;"),
                  ("C", "".join(f"function f{i}(a, b) {{\n  while (a < b) {{ a = a * {i} + b; if (a % 2 === 0) {{ break; }} }}\n  for (let k = 0; k < {i}; k++) {{ b -= k; }}\n  return a ? [a, b] : null;\n}}\n" for i in range(3, 9))),
                  ("D", "".join(f"class K{i} {{\n  constructor(x) {{ this.x = x; this.log = []; }}\n  run(n) {{ do {{ this.log.push(n ** {i}); n--; }} while (n > 0); return this.log.length > {i} ? this.log : this.x; }}\n}}\n" for i in range(3, 9))))]
        out = compare(teams, share=0.5)
        assert out.starter_threshold == 2 or out.starter_threshold == 3
        assert out.starter_removed > 0
        # with the template removed, C and D share nothing
        by = {(p.a_id, p.b_id): p for p in out.pairs}
        assert by[("C", "D")].shared_pct < 15

    def test_two_teams_cannot_have_starter_code_told_apart(self):
        assert starter_threshold(2) is None and starter_threshold(3) == 3 and starter_threshold(10) == 5

    def test_a_team_with_too_little_code_is_left_out_not_marked(self):
        out = compare([team("A", **{"a.js": TODOS}), team("B", **{"b.js": RENAMED}), Team("C", "C", {})])
        assert out.left_out == ["C"] and all("C" not in (p.a_id, p.b_id) for p in out.pairs)

    def test_levels(self):
        assert level_for(39.9, 40, 70) is None and level_for(40, 40, 70) == "review" and level_for(70, 40, 70) == "strong"
