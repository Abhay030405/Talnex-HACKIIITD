"""Stack detection: from a repo's files to a run recipe. Pure, no VM needed."""
import json

from talnex_ai.sandbox.stack_detect.detect import (
    RepoFacts,
    candidate_dirs,
    detect_recipe,
    dockerfile_hints,
    env_placeholders,
    readme_commands,
)


def pkg(**kw):
    return json.dumps(kw)


EXPRESS = pkg(scripts={"start": "node index.js", "test": "jest"}, dependencies={"express": "4"})


class TestNode:
    def test_a_plain_express_app(self):
        r = detect_recipe(RepoFacts(["package.json", "package-lock.json", "index.js"], {"package.json": EXPRESS}))
        assert (r.stack, r.image, r.start_cmd, r.test_cmd) == ("node", "talnex-sandbox-full", "npm start", "npm test")
        assert r.install_cmd.startswith("npm ci") and r.env["PORT"] == "3000" and r.confidence == "high" and r.app_dir == ""

    def test_the_lock_file_decides_the_package_manager(self):
        base = {"package.json": EXPRESS}
        assert "pnpm" in detect_recipe(RepoFacts(["package.json", "pnpm-lock.yaml"], base)).install_cmd
        assert "yarn" in detect_recipe(RepoFacts(["package.json", "yarn.lock"], base)).install_cmd
        assert detect_recipe(RepoFacts(["package.json"], base)).install_cmd.startswith("npm install")

    def test_without_a_start_script_the_main_file_is_run(self):
        p = pkg(main="src/server.js", dependencies={"express": "4"})
        r = detect_recipe(RepoFacts(["package.json", "src/server.js"], {"package.json": p}))
        assert r.start_cmd == "node src/server.js"

    def test_the_npm_default_test_script_is_not_a_test_command(self):
        p = pkg(scripts={"start": "node a.js", "test": 'echo "Error: no test specified" && exit 1'}, dependencies={"express": "4"})
        assert detect_recipe(RepoFacts(["package.json"], {"package.json": p})).test_cmd == ""

    def test_next_is_built_before_it_starts(self):
        p = pkg(scripts={"start": "next start", "build": "next build"}, dependencies={"next": "14", "react": "18"})
        r = detect_recipe(RepoFacts(["package.json"], {"package.json": p}))
        assert (r.build_cmd, r.start_cmd) == ("npm run build", "npm start")


class TestChoosingTheBackend:
    def test_a_repo_with_client_and_server_runs_the_server(self):
        files = ["client/package.json", "server/package.json", "server/index.js"]
        texts = {"client/package.json": pkg(scripts={"start": "react-scripts start"}, dependencies={"react-scripts": "5"}),
                 "server/package.json": EXPRESS}
        r = detect_recipe(RepoFacts(files, texts))
        assert r.app_dir == "server" and r.start_cmd == "npm start"

    def test_a_frontend_only_repo_is_not_runnable_and_says_why(self):
        p = pkg(scripts={"dev": "vite"}, dependencies={"react": "18", "vite": "5"})
        r = detect_recipe(RepoFacts(["package.json", "src/App.jsx"], {"package.json": p}))
        assert r.stack == "unknown" and "frontend only" in r.notes[0]

    def test_node_and_python_in_one_repo_picks_the_stronger_backend(self):
        files = ["web/package.json", "api/requirements.txt", "api/main.py"]
        texts = {"web/package.json": pkg(dependencies={"react-scripts": "5"}),
                 "api/requirements.txt": "fastapi\nuvicorn\n", "api/main.py": "from fastapi import FastAPI\napp = FastAPI()\n"}
        r = detect_recipe(RepoFacts(files, texts))
        assert (r.stack, r.app_dir) == ("python", "api")

    def test_dirs_inside_libraries_and_tests_are_not_candidates(self):
        assert candidate_dirs(["package.json", "node_modules/x/package.json", "tests/fixtures/requirements.txt", "docs/package.json"]) == [""]


class TestPython:
    def test_fastapi_is_started_with_uvicorn_which_is_installed_if_missing(self):
        files = ["requirements.txt", "app/main.py"]
        texts = {"requirements.txt": "fastapi==0.110\n", "app/main.py": "from fastapi import FastAPI\napi = FastAPI(title='x')\n"}
        r = detect_recipe(RepoFacts(files, texts))
        assert r.start_cmd == "uvicorn app.main:api --host 0.0.0.0 --port 8000" and r.port == 8000
        assert "pip install --no-cache-dir uvicorn" in r.install_cmd and r.notes

    def test_a_flask_app_that_runs_itself_is_run_with_python(self):
        files = ["requirements.txt", "app.py"]
        texts = {"requirements.txt": "flask\n", "app.py": "from flask import Flask\napp = Flask(__name__)\nif __name__ == '__main__':\n    app.run()\n"}
        r = detect_recipe(RepoFacts(files, texts))
        assert r.start_cmd == "python app.py" and r.port is None

    def test_a_flask_app_without_run_uses_the_flask_command(self):
        files = ["requirements.txt", "src/app.py"]
        texts = {"requirements.txt": "flask\n", "src/app.py": "from flask import Flask\napp = Flask(__name__)\n"}
        r = detect_recipe(RepoFacts(files, texts))
        assert r.start_cmd == "flask --app src.app:app run --host 0.0.0.0 --port 5000"

    def test_django_migrates_then_runs_the_server(self):
        files = ["requirements.txt", "manage.py"]
        r = detect_recipe(RepoFacts(files, {"requirements.txt": "django\n", "manage.py": "import django"}))
        assert r.start_cmd == "python manage.py migrate --noinput && python manage.py runserver 0.0.0.0:8000" and r.port == 8000

    def test_pytest_is_noted_as_the_repos_own_test_command(self):
        r = detect_recipe(RepoFacts(["requirements.txt", "app.py", "tests/test_a.py"],
                                    {"requirements.txt": "flask\npytest\n", "app.py": "app = Flask(__name__)\n"}))
        assert r.test_cmd == "python -m pytest -x -q"


class TestFallbacks:
    def test_a_stack_we_have_no_image_for_says_so(self):
        r = detect_recipe(RepoFacts(["go.mod", "main.go"], {}))
        assert r.stack == "unknown" and "Go" in r.notes[0] and "no Go image" in r.notes[0]

    def test_an_empty_repo_says_no_package_file(self):
        r = detect_recipe(RepoFacts(["README.md"], {}))
        assert r.stack == "unknown" and "no package file" in r.notes[0]

    def test_the_dockerfile_supplies_a_missing_start_command_and_the_port(self):
        p = pkg(dependencies={"express": "4"})
        docker = 'FROM node:20\nEXPOSE 4000\nCMD ["node", "dist/server.js"]\n'
        r = detect_recipe(RepoFacts(["package.json", "Dockerfile"], {"package.json": p, "Dockerfile": docker}))
        assert (r.start_cmd, r.port, r.source) == ("node dist/server.js", 4000, "dockerfile")

    def test_the_readme_supplies_a_missing_start_command_with_low_confidence(self):
        p = pkg(dependencies={"express": "4"})
        readme = "# App\n```bash\nnpm install\nnode bin/www\n```\n"
        r = detect_recipe(RepoFacts(["package.json", "README.md"], {"package.json": p, "README.md": readme}))
        assert (r.start_cmd, r.source, r.confidence) == ("node bin/www", "readme", "low")


class TestHelpers:
    def test_dockerfile_cmd_forms(self):
        assert dockerfile_hints("CMD npm start")["cmd"] == "npm start"
        assert dockerfile_hints('CMD ["uvicorn", "a:b"]')["cmd"] == "uvicorn a:b"
        assert dockerfile_hints("FROM x")["cmd"] == "" and dockerfile_hints("EXPOSE 80/tcp")["port"] == 80

    def test_readme_commands_come_only_from_code_blocks(self):
        text = "Run npm start to begin.\n```sh\n$ npm install\n$ npm run dev\nls -la\n```\n"
        assert readme_commands(text) == {"install": ["npm install"], "start": ["npm run dev"]}

    def test_env_placeholders_keep_the_authors_values_and_fake_the_empty_secrets(self):
        out = env_placeholders("# comment\nPORT=\nDATABASE_URL=postgres://u:p@localhost/db\nSTRIPE_SECRET_KEY=\nAPI_TOKEN=<your-token>\nMODE=dev\nexport EXTRA=1\n")
        assert out == {"PORT": "3000", "DATABASE_URL": "postgres://u:p@localhost/db", "STRIPE_SECRET_KEY": "talnex-placeholder-stripe_secret_key",
                       "API_TOKEN": "talnex-placeholder-api_token", "MODE": "dev", "EXTRA": "1"}

    def test_services_are_noticed_from_dependencies_and_env_examples(self):
        p = pkg(scripts={"start": "node a.js"}, dependencies={"express": "4", "mongoose": "8", "ioredis": "5"})
        r = detect_recipe(RepoFacts(["package.json"], {"package.json": p}))
        assert sorted(r.services) == ["mongodb", "redis"]


class TestPlaceholdersFitTheirNames:
    """An app that reads MAIL_PORT as a number crashes on the text 'placeholder'; that crash would be ours, not the project's."""

    def test_values_fit_what_the_setting_is_called(self):
        out = env_placeholders("MAIL_PORT=\nMAIL_SERVER=\nSESSION_TIMEOUT=\nDEBUG=\nUSE_TLS=\nAPI_BASE_URL=\nDB_HOST=\n"
                               "ADMIN_EMAIL=\nDB_USER=\nJWT_SECRET=\nSOMETHING_ELSE=\nREDIS_URL=redis://cache:6379/0\n")
        assert out == {"MAIL_PORT": "1025", "MAIL_SERVER": "localhost", "SESSION_TIMEOUT": "60", "DEBUG": "false", "USE_TLS": "false",
                       "API_BASE_URL": "http://localhost", "DB_HOST": "localhost", "ADMIN_EMAIL": "talnex@example.com", "DB_USER": "talnex",
                       "JWT_SECRET": "talnex-placeholder-jwt_secret", "SOMETHING_ELSE": "placeholder", "REDIS_URL": "redis://cache:6379/0"}
