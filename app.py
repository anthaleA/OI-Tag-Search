import json
import logging
import os
import re
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Tuple

from flask import Blueprint, Flask, jsonify, redirect, render_template, request, Response

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

DEFAULT_CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.example.json")
LOCAL_CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.json")


def _read_json_file(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def load_config() -> Dict[str, Any]:
    config = _read_json_file(DEFAULT_CONFIG_PATH)
    local = _read_json_file(LOCAL_CONFIG_PATH)
    config = _deep_merge(config, local)

    env_map = {
        "PA_DATA_FILE": ("data_file",),
        "PA_DB_PATH": ("data_source", "db_path"),
        "PA_DATA_SOURCE": ("data_source", "type"),
        "PA_BASE_PATH": ("app", "base_path"),
        "PA_HOST": ("app", "host"),
        "PA_PORT": ("app", "port"),
        "PA_DEBUG": ("app", "debug"),
        "PA_DEFAULT_MATCH_MODE": ("search", "default_match_mode"),
        "PA_CASE_SENSITIVE": ("search", "case_sensitive"),
        "PA_DEFAULT_LIMIT": ("search", "default_limit"),
        "PA_MAX_LIMIT": ("search", "max_limit"),
    }

    for env_key, path in env_map.items():
        if env_key not in os.environ:
            continue
        value: Any = os.environ[env_key]
        # Basic type coercion
        if value.lower() in {"true", "false"}:
            value = value.lower() == "true"
        else:
            try:
                value = int(value)
            except ValueError:
                pass

        cursor = config
        for part in path[:-1]:
            cursor = cursor.setdefault(part, {})
        cursor[path[-1]] = value

    return config


config = load_config()


def _normalize_base_path(path: str) -> str:
    if not path:
        return ""
    path = path.strip()
    if not path:
        return ""
    if not path.startswith("/"):
        path = "/" + path
    return path.rstrip("/")


BASE_PATH = _normalize_base_path(config.get("app", {}).get("base_path", ""))

app = Flask(__name__)

logging.basicConfig(
    level=logging.DEBUG if config.get("app", {}).get("debug") else logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
)


def _resolve_path(path_value: str) -> str:
    if not path_value:
        return path_value
    if os.path.isabs(path_value):
        return path_value
    return os.path.join(PROJECT_ROOT, path_value)


DATA_STATE: Dict[str, Any] = {
    "mtime": None,
    "payload": {"problems": [], "updated_at": None},
    "source": None,
}


def _pick_link(links: Dict[str, Any]) -> str:
    if not links:
        return ""
    for key in ("main", "url", "link", "luogu", "codeforces"):
        if key in links and links[key]:
            return str(links[key])
    for value in links.values():
        if value:
            return str(value)
    return ""


def _load_data_file() -> Dict[str, Any]:
    data_path = _resolve_path(config.get("data_file", "data/problems.json"))
    if not data_path or not os.path.exists(data_path):
        logging.warning("Data file not found: %s", data_path)
        return {"problems": [], "updated_at": None}

    mtime = os.path.getmtime(data_path)
    if DATA_STATE["source"] == "json" and DATA_STATE["mtime"] == mtime:
        return DATA_STATE["payload"]

    with open(data_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    if not isinstance(payload, dict):
        payload = {"problems": payload, "updated_at": None}

    if "problems" not in payload:
        payload = {"problems": [], "updated_at": None}

    DATA_STATE["mtime"] = mtime
    DATA_STATE["payload"] = payload
    DATA_STATE["source"] = "json"
    logging.info("Loaded %s problems from %s", len(payload.get("problems", [])), data_path)
    return payload


def _load_data_db() -> Dict[str, Any]:
    source_cfg = config.get("data_source", {})
    db_path = source_cfg.get("db_path")
    db_path = _resolve_path(db_path)
    if not db_path or not os.path.exists(db_path):
        logging.warning("DB file not found: %s", db_path)
        return {"problems": [], "updated_at": None}

    mtime = os.path.getmtime(db_path)
    if DATA_STATE["source"] == "sqlite" and DATA_STATE["mtime"] == mtime:
        return DATA_STATE["payload"]

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT problem_id, problem_name, difficulty, platforms, tags, links FROM problems"
    )
    rows = cursor.fetchall()
    conn.close()

    problems = []
    for row in rows:
        try:
            tags = json.loads(row["tags"]) if row["tags"] else []
        except json.JSONDecodeError:
            tags = []
        try:
            links = json.loads(row["links"]) if row["links"] else {}
        except json.JSONDecodeError:
            links = {}
        try:
            platforms = json.loads(row["platforms"]) if row["platforms"] else []
        except json.JSONDecodeError:
            platforms = []

        problems.append(
            {
                "id": row["problem_id"],
                "title": row["problem_name"] or "",
                "tags": tags if isinstance(tags, list) else [],
                "url": _pick_link(links) if isinstance(links, dict) else "",
                "source": platforms[0] if isinstance(platforms, list) and platforms else "unknown",
                "difficulty": row["difficulty"] or "",
            }
        )

    payload = {"problems": problems, "updated_at": datetime.now().strftime("%Y-%m-%d")}
    DATA_STATE["mtime"] = mtime
    DATA_STATE["payload"] = payload
    DATA_STATE["source"] = "sqlite"
    logging.info("Loaded %s problems from %s", len(problems), db_path)
    return payload


def _load_data() -> Dict[str, Any]:
    source_type = (config.get("data_source", {}) or {}).get("type", "json").lower()
    if source_type == "sqlite":
        return _load_data_db()
    return _load_data_file()


def _normalize_tag(tag: str, case_sensitive: bool) -> str:
    cleaned = tag.strip()
    cleaned = re.sub(r"^L\\d+-", "", cleaned, flags=re.IGNORECASE)
    if re.match(r"^[IC]\\d+$", cleaned, flags=re.IGNORECASE):
        return ""
    return cleaned if case_sensitive else cleaned.lower()


def _parse_tags(raw: str) -> List[str]:
    if not raw:
        return []
    parts = [p for chunk in raw.split(";") for p in chunk.split(",")]
    return [p.strip() for p in parts if p.strip()]


def _apply_search(
    problems: List[Dict[str, Any]],
    tags: List[str],
    query: str,
    match_mode: str,
    case_sensitive: bool,
) -> List[Dict[str, Any]]:
    normalized_tags = [normalized for tag in tags if (normalized := _normalize_tag(tag, case_sensitive))]

    def matches(problem: Dict[str, Any]) -> bool:
        problem_tags = problem.get("tags", [])
        normalized_problem_tags = [
            normalized for tag in problem_tags if (normalized := _normalize_tag(tag, case_sensitive))
        ]

        if normalized_tags:
            if match_mode == "all":
                if not all(tag in normalized_problem_tags for tag in normalized_tags):
                    return False
            else:
                if not any(tag in normalized_problem_tags for tag in normalized_tags):
                    return False

        if query:
            haystack = f"{problem.get('id', '')} {problem.get('title', '')}"
            if not case_sensitive:
                haystack = haystack.lower()
                query_cmp = query.lower()
            else:
                query_cmp = query
            if query_cmp not in haystack:
                return False

        return True

    return [problem for problem in problems if matches(problem)]


def _static_version(relative_path: str) -> int:
    file_path = os.path.join(PROJECT_ROOT, relative_path)
    try:
        return int(os.path.getmtime(file_path))
    except OSError:
        return int(datetime.now().timestamp())


def register_routes(router):
    @router.route("/")
    def index():
        ui_config = {
            "base_path": BASE_PATH,
            "default_match_mode": config.get("search", {}).get("default_match_mode", "all"),
            "default_limit": config.get("search", {}).get("default_limit", 50),
            "cache_buster": max(
                _static_version(os.path.join("static", "css", "app.css")),
                _static_version(os.path.join("static", "js", "app.js")),
            ),
        }
        return render_template("index.html", ui_config=ui_config)

    @router.route("/api/search")
    def search():
        payload = _load_data()
        problems = payload.get("problems", [])

        tags = _parse_tags(request.args.get("tags", ""))
        query = request.args.get("q", "").strip()
        match_mode = request.args.get("mode", config.get("search", {}).get("default_match_mode", "all"))
        case_sensitive = bool(config.get("search", {}).get("case_sensitive", False))

        filtered = _apply_search(problems, tags, query, match_mode, case_sensitive)

        sort_key = request.args.get("sort", "id")
        if sort_key not in {"id", "title"}:
            sort_key = "id"

        filtered.sort(key=lambda item: str(item.get(sort_key, "")).lower())

        max_limit = int(config.get("search", {}).get("max_limit", 200))
        try:
            limit = int(request.args.get("limit", config.get("search", {}).get("default_limit", 50)))
        except ValueError:
            limit = int(config.get("search", {}).get("default_limit", 50))

        limit = max(1, min(limit, max_limit))
        offset = max(0, int(request.args.get("offset", 0)))

        sliced = filtered[offset : offset + limit]

        return jsonify(
            {
                "ok": True,
                "count": len(filtered),
                "limit": limit,
                "offset": offset,
                "data": sliced,
                "updated_at": payload.get("updated_at"),
            }
        )

    @router.route("/api/tags")
    def tags():
        payload = _load_data()
        problems = payload.get("problems", [])

        case_sensitive = bool(config.get("search", {}).get("case_sensitive", False))
        tag_map: Dict[str, Dict[str, Any]] = {}

        for problem in problems:
            for tag in problem.get("tags", []):
                normalized = _normalize_tag(tag, case_sensitive)
                if not normalized:
                    continue
                display_tag = normalized if case_sensitive else normalized
                entry = tag_map.setdefault(display_tag, {"tag": display_tag, "count": 0})
                entry["count"] += 1

        tags_list = sorted(tag_map.values(), key=lambda item: (-item["count"], item["tag"]))

        return jsonify({"ok": True, "count": len(tags_list), "data": tags_list})

    @router.route("/api/health")
    def health():
        payload = _load_data()
        return jsonify(
            {
                "ok": True,
                "problems": len(payload.get("problems", [])),
                "updated_at": payload.get("updated_at"),
                "server_time": datetime.now().isoformat(),
            }
        )


if BASE_PATH:
    api = Blueprint("pa", __name__)
    register_routes(api)
    app.register_blueprint(api, url_prefix=BASE_PATH)

    @app.route("/")
    def root_redirect():
        return redirect(f"{BASE_PATH}/")
else:
    register_routes(app)


@app.route("/favicon.ico")
def favicon():
    return Response(status=204)


if __name__ == "__main__":
    app_config = config.get("app", {})
    host = app_config.get("host", "127.0.0.1")
    port = int(app_config.get("port", 5000))
    debug = bool(app_config.get("debug", True))

    app.run(host=host, port=port, debug=debug)
