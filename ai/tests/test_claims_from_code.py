"""Open-theme claims read from the project's own code: which files are read, that a feature must stand on a file we read,
and that the hint about how to reach a feature goes to the test planner."""
import re

from talnex_ai.claims.from_code import feature_files, find_features
from talnex_ai.sandbox.client import ExecResult
from talnex_ai.worker.handlers.test_plan import _hint
from tests.fakes import ScriptedModel

CODE = {
    "src/pages/Todos.jsx": "export default function Todos() {\n  return <button onClick={add}>Add todo</button>\n}\n",
    "src/pages/Login.jsx": "export default function Login() { return <form onSubmit={signIn}/> }\n",
    "server/routes.js": "app.post('/api/todos', (req, res) => res.json({}))\n",
    "README.md": "# Todos\n",
}


class Vm:
    def __init__(self, files):
        self.files = files

    def exec(self, command, **kw):
        paths = re.findall(r'@@@TALNEX-FILE ([^"]+)"', command)
        return ExecResult(0, stdout="\n".join(f"@@@TALNEX-FILE {p}\n{self.files.get(p, '')}\n" for p in paths))


def feature(text, file="src/pages/Todos.jsx", **kw):
    return {"text": text, "claim_group": "Core", "importance": 3, "how_to_try": "open the todo page, press Add todo",
            "evidence": [{"file": file, "line": 2, "what": "the Add todo button"}], **kw}


class TestWhichFilesAreRead:
    def test_pages_and_routes_come_first_and_noise_is_left_out(self):
        files = ["node_modules/x/index.js", "package-lock.json", "src/pages/Todos.jsx", "server/routes.js", "tests/todos.test.js",
                 "vite.config.js", "src/util/strings.js", "dist/bundle.js", "README.md", "src/App.test.tsx"]
        chosen = feature_files(files, 10)
        assert chosen[:2] == ["src/pages/Todos.jsx", "server/routes.js"]
        assert not {"node_modules/x/index.js", "dist/bundle.js", "tests/todos.test.js", "vite.config.js", "package-lock.json", "README.md", "src/App.test.tsx"} & set(chosen)

    def test_only_the_limit_is_read(self):
        assert len(feature_files([f"src/pages/p{i}.jsx" for i in range(40)], 25)) == 25


class TestFeaturesFromCode:
    def test_a_feature_with_evidence_becomes_a_code_claim_with_its_hint(self):
        model = ScriptedModel({"features": [feature("Add a todo item")]})
        found = find_features(model, Vm(CODE), "Todos", list(CODE), readme="# Todos", live_url="https://t.example")
        claim = found.claims[0]
        assert (claim.source, claim.track, claim.claim_group, claim.importance, claim.testable) == ("code", "live", "Core", 3, True)
        note = found.notes["Add a todo item"]
        assert "press Add todo" in note["how_to_try"] and note["evidence"][0]["file"] == "src/pages/Todos.jsx"
        # the model sees the code with line numbers, and the live link
        text = model.user_text(0)
        assert "   2|   return <button onClick={add}>Add todo</button>" in text and "https://t.example" in text

    def test_a_feature_pointing_at_a_file_we_did_not_read_is_dropped(self):
        model = ScriptedModel({"features": [feature("Pay by card", file="src/pages/Checkout.jsx"), feature("Add a todo item")]})
        found = find_features(model, Vm(CODE), "Todos", list(CODE))
        assert [c.text for c in found.claims] == ["Add a todo item"] and found.dropped == ["Pay by card"]

    def test_duplicates_are_merged_and_the_limit_holds(self):
        model = ScriptedModel({"features": [feature("Add a todo"), feature("add  a TODO"), feature("Sign in", file="src/pages/Login.jsx"), feature("Third")]})
        found = find_features(model, Vm(CODE), "Todos", list(CODE), max_claims=2)
        assert [c.text for c in found.claims] == ["Add a todo", "Sign in"]

    def test_an_unknown_group_becomes_core_and_a_known_criterion_is_kept(self):
        model = ScriptedModel({"features": [feature("Add a todo", claim_group="Banana"), feature("Sign in", file="src/pages/Login.jsx", claim_group="Look")]})
        found = find_features(model, Vm(CODE), "Todos", list(CODE), criteria=["Look"])
        assert [c.claim_group for c in found.claims] == ["Core", "Look"]

    def test_a_feature_a_visitor_cannot_try_is_kept_but_not_testable(self):
        model = ScriptedModel({"features": [feature("Nightly cleanup", testable=False, untestable_reason="a background job")]})
        claim = find_features(model, Vm(CODE), "Todos", list(CODE)).claims[0]
        assert not claim.testable and claim.untestable_reason == "a background job"

    def test_every_readme_feature_comes_before_finer_detail(self):
        # Seen on the planted ShelfMate app: twelve features were allowed, sign-in was split into four, and the README's yearly
        # reading goal (one of nine features) was cut, so its broken progress bar was never tested.
        from talnex_ai.llm.prompts.feature_finder import SYSTEM
        assert "one entry for each feature the README lists" in SYSTEM and "before adding any finer detail" in SYSTEM
        assert "Do not split" in SYSTEM

    def test_nothing_to_read_asks_no_model(self):
        model = ScriptedModel()
        assert find_features(model, Vm({}), "Empty", ["package.json", "README.md"]).claims == [] and model.calls == []


class TestTheHintForThePlanner:
    def test_it_carries_the_steps_the_login_and_the_file(self):
        hint = _hint({"how_to_try": "press Add todo", "needs_login": True, "evidence": [{"file": "a.jsx", "line": 4}]})
        assert "press Add todo" in hint and "sign-in" in hint and "a.jsx:4" in hint

    def test_a_claim_without_notes_has_no_hint(self):
        assert _hint({}) == ""
