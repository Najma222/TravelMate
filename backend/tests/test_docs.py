"""OpenAPI and Postman must cover every route the app actually registers."""
import json
import os
import re

import yaml

DOCS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "docs"))


def _app_routes(app):
    out = set()
    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        path = re.sub(r"<(?:[a-z]+:)?(\w+)>", r"{\1}", rule.rule)
        for m in rule.methods - {"HEAD", "OPTIONS"}:
            out.add((m.lower(), path))
    return out


def test_openapi_matches_app(app):
    spec = yaml.safe_load(open(os.path.join(DOCS, "openapi.yaml"), encoding="utf-8"))
    documented = {(m, p) for p, ops in spec["paths"].items() for m in ops}
    assert documented == _app_routes(app)


def test_postman_matches_app(app):
    coll = json.load(open(os.path.join(DOCS, "postman", "travelmate.postman_collection.json"), encoding="utf-8"))
    names = {i["name"] for folder in coll["item"] for i in folder["item"]}
    expected = {f"{m.upper()} {p}" for m, p in _app_routes(app)}
    assert names == expected


def test_openapi_is_valid_spec():
    from openapi_spec_validator import validate

    validate(yaml.safe_load(open(os.path.join(DOCS, "openapi.yaml"), encoding="utf-8")))
