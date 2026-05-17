#!/usr/bin/env python3
"""Preflight checker for PaperTools daily automation."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

SJTU_BASE_URL = "https://models.sjtu.edu.cn/api/v1/"
SJTU_MODELS = {"minimax", "glm", "qwen", "deepseek-chat", "deepseek-reasoner"}

# Lightweight alias map matching src/utils/config.py's _normalize_model_alias.
_MODEL_ALIASES = {
    "minimax-m2": "minimax",
    "minimax-m2.5": "minimax",
    "minimax-m2.7": "minimax",
    "minimax/minimax-m2": "minimax",
    "minimax/minimax-m2.5": "minimax",
    "minimax/minimax-m2.7": "minimax",
    "minimax/m2.7": "minimax",
    "glm-5.1": "glm",
    "glm5.1": "glm",
    "qwen3.5-27b": "qwen",
    "qwen-3.5-27b": "qwen",
    "qwen/qwen3.5-27b": "qwen",
    "deepseek v3.2(常规模式)": "deepseek-chat",
    "deepseek-v3.2(常规模式)": "deepseek-chat",
    "deepseek v3.2 chat": "deepseek-chat",
    "deepseek v3.2(思考模式)": "deepseek-reasoner",
    "deepseek-v3.2(思考模式)": "deepseek-reasoner",
    "deepseek r1": "deepseek-reasoner",
    "deepseek-r1": "deepseek-reasoner",
    "deepseek/deepseek-r1": "deepseek-reasoner",
    "deepseek/deepseek-chat": "deepseek-chat",
    "deepseek/deepseek-chat-v3-0324": "deepseek-chat",
}


def _normalize_model(model: str) -> str:
    key = model.lower().replace("_", "-").strip()
    return _MODEL_ALIASES.get(key, model)


def mask(value: str | None) -> str:
    if not value:
        return "<empty>"
    if len(value) <= 8:
        return "***"
    return value[:3] + "..." + value[-4:]


def split_models(value: str | None) -> list[str]:
    if not value:
        return []
    models: list[str] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            item = item.split(":", 1)[1]
        models.append(item)
    return models


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline-ok", action="store_true", help="Do not call the remote /models endpoint.")
    args = parser.parse_args()

    root = Path.cwd()
    if load_dotenv is not None:
        load_dotenv(root / ".env", override=True)

    required = ["OPENAI_API_KEY", "OPENAI_BASE_URL"]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        print(f"ERROR: missing required environment variables: {', '.join(missing)}")
        return 2

    base_url = os.getenv("OPENAI_BASE_URL", "")
    print(f"OPENAI_BASE_URL={base_url}")
    print(f"OPENAI_API_KEY={mask(os.getenv('OPENAI_API_KEY'))}")

    model_vars = {
        "MODEL": os.getenv("MODEL", "minimax"),
        "FILTER_MODEL": os.getenv("FILTER_MODEL", "qwen"),
        "CLUSTER_MODEL": os.getenv("CLUSTER_MODEL", "glm"),
        "SUMMARY_MODEL": os.getenv("SUMMARY_MODEL", "minimax"),
    }
    for name, value in model_vars.items():
        print(f"{name}={value}")

    chain_models = split_models(os.getenv("SUMMARY_MODEL_CHAIN")) + split_models(os.getenv("PAPERTOOLS_FILTER_MODEL_CHAIN"))
    requested = {_normalize_model(value) for value in model_vars.values() if value} | {_normalize_model(m) for m in chain_models}
    if base_url.rstrip("/") == SJTU_BASE_URL.rstrip("/"):
        unknown = sorted(model for model in requested if model not in SJTU_MODELS)
        if unknown:
            print("ERROR: these model IDs are not in the known SJTU model_id list: " + ", ".join(unknown))
            print("Known SJTU model_id values: " + ", ".join(sorted(SJTU_MODELS)))
            return 2

    # Cheap local import checks catch most broken deployments before cron spends API calls.
    for module in ["openai", "requests", "bs4", "tqdm", "dotenv"]:
        try:
            __import__(module)
        except Exception as exc:
            print(f"ERROR: cannot import {module}: {exc}")
            return 2

    if not args.offline_ok:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url=base_url, timeout=20.0, max_retries=0)
            models = client.models.list()
            available = {getattr(model, "id", "") for model in getattr(models, "data", [])}
            if available:
                missing_remote = sorted(model for model in requested if model not in available)
                if missing_remote:
                    print("ERROR: requested models not returned by /models: " + ", ".join(missing_remote))
                    return 2
        except Exception as exc:
            print(f"WARNING: remote /models check skipped/failed: {exc}")

    print("Preflight OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
