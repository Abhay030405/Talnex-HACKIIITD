"""Finding routes without running the app: OpenAPI, the code (several frameworks, mounted prefixes) and the README."""
import json

from talnex_ai.sandbox.route_discovery.extract import (
    FoundRoute,
    from_code,
    from_openapi,
    from_readme,
    join_paths,
    merge,
    normalise_path,
)


def keys(routes):
    return sorted((r.method, r.path) for r in routes)


class TestPaths:
    def test_every_way_of_writing_a_parameter_is_one_spelling(self):
        assert {normalise_path(p) for p in ["/users/{id}", "/users/:id", "/users/<int:id>", "/users/[id]/"]} == {"/users/{}"}
        assert normalise_path("") == "/" and normalise_path("items/") == "/items"

    def test_joining_a_prefix_and_a_path(self):
        assert join_paths("/api/", "/items") == "/api/items" and join_paths("", "x") == "/x" and join_paths("/api", "") == "/api"


OPENAPI = {
    "openapi": "3.0.0",
    "paths": {
        "/items": {
            "get": {"summary": "List items"},
            "post": {"summary": "Create", "security": [{"bearer": []}],
                     "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Item"}}}}},
        },
        "/items/{id}": {"parameters": [], "delete": {"description": "Remove one"}},
    },
    "components": {"schemas": {"Item": {"properties": {"name": {}, "price": {}}}}},
}


class TestOpenApi:
    def test_methods_summaries_body_fields_and_auth_are_read(self):
        routes = {(r.method, r.path): r for r in from_openapi(json.dumps(OPENAPI))}
        assert set(routes) == {("GET", "/items"), ("POST", "/items"), ("DELETE", "/items/{id}")}
        post = routes[("POST", "/items")]
        assert post.body_fields == ("name", "price") and post.needs_auth is True and post.summary == "Create"
        assert routes[("GET", "/items")].needs_auth is None

    def test_a_global_security_requirement_means_auth_everywhere(self):
        doc = {"paths": {"/a": {"get": {}}}, "security": [{"k": []}]}
        assert from_openapi(doc)[0].needs_auth is True

    def test_swagger_two_base_path_and_body_parameter(self):
        doc = {"swagger": "2.0", "basePath": "/v1", "paths": {"/x": {"post": {"parameters": [
            {"in": "body", "schema": {"properties": {"a": {}}}}]}}}}
        (r,) = from_openapi(doc)
        assert (r.path, r.body_fields) == ("/v1/x", ("a",))

    def test_rubbish_gives_nothing(self):
        assert from_openapi("not json") == [] and from_openapi({"paths": []}) == [] and from_openapi("[1]") == []


class TestJavaScript:
    def test_express_routes_with_line_numbers(self):
        code = "const app = express();\napp.get('/health', h);\nrouter.post(\"/login\", login);\napp.delete(`/items/:id`, rm);\n"
        found = from_code({"server.js": code})
        assert keys(found) == [("DELETE", "/items/:id"), ("GET", "/health"), ("POST", "/login")]
        assert {r.path: r.line for r in found}["/health"] == 2

    def test_requests_made_by_the_code_are_not_routes(self):
        code = "axios.get('/api/x');\nsupertest(app).get('/y');\nfetch.get('/z');\napp.get('/real', h);\n"
        assert keys(from_code({"a.js": code})) == [("GET", "/real")]

    def test_a_router_mounted_with_a_prefix_gets_it(self):
        files = {
            "app.js": "const users = require('./routes/users');\napp.use('/api/users', users);\n",
            "routes/users.js": "router.get('/', list);\nrouter.post('/:id/follow', f);\n",
        }
        assert keys(from_code(files)) == [("GET", "/api/users"), ("POST", "/api/users/:id/follow")]

    def test_an_inline_require_mount_and_es_import_mount(self):
        files = {
            "index.js": "app.use('/v1', require('./items'));\nimport orders from './orders';\napp.use('/orders', orders);\n",
            "items.js": "router.get('/list', l);",
            "orders.js": "router.get('/', l);",
        }
        assert keys(from_code(files)) == [("GET", "/orders"), ("GET", "/v1/list")]

    def test_all_means_any_method(self):
        assert keys(from_code({"a.js": "app.all('/ping', p);"})) == [("ANY", "/ping")]


class TestPython:
    def test_flask_routes_default_to_get_and_read_their_methods(self):
        code = "@app.route('/')\ndef i(): ...\n@app.route('/items', methods=['GET', 'POST'])\ndef it(): ...\n@app.post('/x')\ndef x(): ...\n"
        assert keys(from_code({"app.py": code})) == [("GET", "/"), ("GET", "/items"), ("POST", "/items"), ("POST", "/x")]

    def test_fastapi_routes_and_router_prefix(self):
        code = "router = APIRouter(prefix='/items')\n@router.get('/{item_id}')\nasync def g(): ...\n@app.get('/health')\ndef h(): ...\n"
        assert keys(from_code({"main.py": code})) == [("GET", "/health"), ("GET", "/items/{item_id}")]

    def test_a_blueprint_registered_in_another_file_gets_its_prefix(self):
        files = {
            "app.py": "from users import users_bp\napp.register_blueprint(users_bp, url_prefix='/api/users')\n",
            "users.py": "users_bp = Blueprint('users', __name__)\n@users_bp.route('/<int:id>')\ndef g(id): ...\n",
        }
        assert keys(from_code(files)) == [("GET", "/api/users/<int:id>")]

    def test_django_urls_are_any_method(self):
        found = from_code({"shop/urls.py": "urlpatterns = [path('products/', v), path('cart/<int:id>/', c)]"})
        assert keys(found) == [("ANY", "/cart/<int:id>"), ("ANY", "/products")] or keys(found) == [("ANY", "/cart/<int:id>/"), ("ANY", "/products/")]


class TestOtherLanguagesAndReadme:
    def test_spring_and_gin(self):
        assert keys(from_code({"A.java": '@GetMapping("/users")\n@PostMapping(value = "/users")'})) == [("GET", "/users"), ("POST", "/users")]
        assert keys(from_code({"main.go": 'r.GET("/ping", h)\nr.POST("/items", c)'})) == [("GET", "/ping"), ("POST", "/items")]

    def test_readme_endpoints_from_lists_and_tables(self):
        text = "## API\n- `GET /api/items` list\n| POST | /api/items | create |\nPOST /login\nuse the GET method to read\n"
        assert keys(from_readme(text)) == [("GET", "/api/items"), ("POST", "/api/items"), ("POST", "/login")]


class TestMerge:
    def test_each_route_once_and_the_best_source_wins_but_facts_are_combined(self):
        spec = FoundRoute("POST", "/items", "openapi", body_fields=("name",))
        code = FoundRoute("POST", "/items/", "code", "api.js", 4, needs_auth=True)
        readme = FoundRoute("POST", "/items", "readme", "README.md", 9)
        (r,) = merge([readme], [code], [spec])
        assert r.source == "openapi" and r.body_fields == ("name",) and r.needs_auth is True

    def test_an_any_route_is_dropped_when_a_specific_method_exists_for_the_path(self):
        merged = merge([FoundRoute("ANY", "/a", "code"), FoundRoute("GET", "/a", "code"), FoundRoute("ANY", "/b", "code")])
        assert [(r.method, r.path) for r in merged] == [("GET", "/a"), ("ANY", "/b")]

    def test_parameter_spellings_count_as_the_same_route(self):
        merged = merge([FoundRoute("GET", "/u/:id", "code")], [FoundRoute("GET", "/u/{id}", "openapi")])
        assert len(merged) == 1 and merged[0].source == "openapi"


class TestBodyFieldsFromCode:
    def test_express_reads_of_the_body_become_fields(self):
        code = ("app.post('/api/books/:id/rating', (req, res) => {\n  const stars = req.body.stars;\n  const who = req.body['reviewer'];\n  res.json({});\n});\n"
                "app.post('/api/items', (req, res) => {\n  const { name, price = 3, tags } = req.body;\n});\n"
                "app.get('/api/books', (req, res) => { res.json(req.body.ignored); });\n")
        found = {r.path: r.body_fields for r in from_code({"s.js": code}) if r.method == "POST"}
        assert found["/api/books/:id/rating"] == ("stars", "reviewer") and found["/api/items"] == ("name", "price", "tags")
        assert [r.body_fields for r in from_code({"s.js": code}) if r.method == "GET"] == [()]      # a read has no body

    def test_a_field_belongs_to_its_own_route_only(self):
        code = "app.post('/a', (req, res) => { req.body.one; });\napp.post('/b', (req, res) => { req.body.two; });\n"
        assert {r.path: r.body_fields for r in from_code({"s.js": code})} == {"/a": ("one",), "/b": ("two",)}

    def test_flask_and_fastapi_style_reads(self):
        code = ("@app.post('/api/users')\ndef make():\n    data = request.get_json()\n    name = data['username']\n    mail = data.get('email')\n    return {}\n"
                "@app.post('/api/other')\ndef other():\n    return request.json['value']\n")
        found = {r.path: r.body_fields for r in from_code({"app.py": code})}
        assert found["/api/users"] == ("username", "email") and found["/api/other"] == ("value",)


class TestMoreFrameworks:
    """Route styles the first version missed (a real repo's aiohttp REST API was found to have 0 routes)."""

    def test_aiohttp_add_methods_add_route_and_route_tables(self):
        code = (
            "app.router.add_get('/api/jobs', list_jobs)\n"
            "app.router.add_post('/api/jobs', submit_job)\n"
            "app.router.add_route('DELETE', '/api/jobs/{id}', cancel)\n"
            "app.router.add_route('*', '/api/any', anything)\n"
            "app.add_routes([web.get('/api/peers', peers), web.post('/api/wallet/send', send)])\n"
        )
        assert keys(from_code({"agent/rest_api.py": code})) == [
            ("ANY", "/api/any"), ("DELETE", "/api/jobs/{id}"), ("GET", "/api/jobs"), ("GET", "/api/peers"),
            ("POST", "/api/jobs"), ("POST", "/api/wallet/send")]

    def test_aiohttp_route_table_decorators(self):
        code = "routes = web.RouteTableDef()\n@routes.get('/api/trust')\nasync def trust(r): ...\n@routes.post('/api/pipelines')\nasync def p(r): ...\n"
        assert keys(from_code({"api.py": code})) == [("GET", "/api/trust"), ("POST", "/api/pipelines")]

    def test_starlette_routes_and_flask_add_url_rule(self):
        starlette = "routes = [Route('/health', health), Route('/items', create, methods=['POST', 'PUT'])]\n"
        flask = "app.add_url_rule('/login', 'login', login, methods=['POST'])\napp.add_url_rule('/about', view_func=about)\n"
        assert keys(from_code({"app.py": starlette})) == [("GET", "/health"), ("POST", "/items"), ("PUT", "/items")]
        assert keys(from_code({"web.py": flask})) == [("GET", "/about"), ("POST", "/login")]

    def test_fastapi_router_prefix_in_the_same_file(self):
        code = "router = APIRouter(prefix='/v2')\n@router.get('/users')\ndef users(): ...\n"
        assert keys(from_code({"users.py": code})) == [("GET", "/v2/users")]

    def test_express_route_chains_koa_prefix_and_hono_mounts(self):
        express = "app.route('/book').get(getBook).post(addBook)\n"
        koa = "const router = new Router({ prefix: '/api' })\nrouter.get('/todos', list)\n"
        hono = "import todos from './todos'\nconst app = new Hono()\napp.route('/api/todos', todos)\n"
        todos = "const todos = new Hono()\ntodos.get('/', list)\ntodos.post('/', add)\nexport default todos\n"
        assert keys(from_code({"server.js": express})) == [("GET", "/book"), ("POST", "/book")]
        assert keys(from_code({"routes.js": koa})) == [("GET", "/api/todos")]
        assert keys(from_code({"index.ts": hono, "todos.ts": todos})) == [("GET", "/api/todos"), ("POST", "/api/todos")]

    def test_client_calls_are_still_not_routes(self):
        assert from_code({"client.py": "requests.get('/api/jobs')\nhttpx.post('/api/x')\n"}) == []
