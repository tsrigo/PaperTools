#!/usr/bin/env python3
"""Preflight checker for PaperTools daily automation."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

SJTU_BASE_URL = "https://models.sjtu.edu.cn/api/v1/"
SJTU_MODELS = {"minimax", "glm", "qwen", "deepseek-chat", "deepseek-reasoner"}
PRISM_BASE_URL = "https://ai.prism.uno/v1"
DEFAULT_SUMMARY_MODEL_CHAIN = (
    "sjtu:minimax,sjtu:glm,sjtu:qwen,sjtu:deepseek-chat,sjtu:deepseek-reasoner"
)
SUMMARY_PROVIDERS = {"modelscope", "sjtu", "prism"}

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.openai_client import create_openai_client  # noqa: E402

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

_OPENROUTER_MODEL_ALIASES = {
    "qwen": "qwen/qwen3-30b-a3b",
    "qwen3-30b-a3b": "qwen/qwen3-30b-a3b",
    "minimax": "qwen/qwen3-30b-a3b",
    "minimax-m2": "qwen/qwen3-30b-a3b",
    "minimax-m2.5": "qwen/qwen3-30b-a3b",
    "minimax-m2.7": "qwen/qwen3-30b-a3b",
    "minimax/minimax-m2": "qwen/qwen3-30b-a3b",
    "minimax/minimax-m2.5": "qwen/qwen3-30b-a3b",
    "minimax/minimax-m2.7": "qwen/qwen3-30b-a3b",
    "deepseek-chat": "deepseek/deepseek-chat-v3-0324",
    "deepseek-reasoner": "deepseek/deepseek-chat-v3-0324",
    "deepseek/deepseek-chat": "deepseek/deepseek-chat-v3-0324",
    "deepseek/deepseek-r1": "deepseek/deepseek-chat-v3-0324",
    "deepseek-r1": "deepseek/deepseek-chat-v3-0324",
}


@dataclass(frozen=True)
class ModelCheck:
    label: str
    api_key: str
    base_url: str
    models: tuple[str, ...]


def _normalize_model(model: str) -> str:
    raw = str(model or "").strip()
    key = raw.lower().replace("（", "(").replace("）", ")").replace("_", "-").strip()
    key = " ".join(key.split())
    return _MODEL_ALIASES.get(key, raw)


def is_openrouter_base_url(base_url: str) -> bool:
    return "openrouter.ai" in (base_url or "").lower()


def is_sjtu_base_url(base_url: str) -> bool:
    return (base_url or "").rstrip("/") == SJTU_BASE_URL.rstrip("/")


def normalize_model_for_base_url(model: str, base_url: str) -> str:
    raw = str(model or "").strip()
    key = raw.lower().replace("（", "(").replace("）", ")").replace("_", "-").strip()
    key = " ".join(key.split())
    if is_openrouter_base_url(base_url):
        return _OPENROUTER_MODEL_ALIASES.get(key, raw)
    return _normalize_model(raw)


def env_str(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def mask(value: str | None) -> str:
    if not value:
        return "<empty>"
    if len(value) <= 8:
        return "***"
    return value[:3] + "..." + value[-4:]


def split_models(value: str | None) -> list[str]:
    models: list[str] = []
    for item in split_chain_entries(value):
        if ":" in item:
            item = item.split(":", 1)[1]
        models.append(item)
    return models


def split_chain_entries(value: str | None) -> list[str]:
    if not value:
        return []
    entries: list[str] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        entries.append(item)
    return entries


def first_nonempty_env(*names: str) -> tuple[str, str]:
    """Return the first configured environment variable from a priority list."""
    for name in names:
        value = os.getenv(name, "")
        if value:
            return name, value
    return names[0], ""


def dedupe_models(models: list[str], base_url: str) -> tuple[str, ...]:
    deduped: list[str] = []
    seen = set()
    for model in models:
        normalized = normalize_model_for_base_url(model, base_url)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return tuple(deduped)


def parse_summary_model_entry(entry: str) -> tuple[str, str]:
    provider_name = ""
    model = entry
    if ":" in entry:
        maybe_provider, maybe_model = entry.split(":", 1)
        maybe_provider = maybe_provider.strip().lower()
        if maybe_provider in SUMMARY_PROVIDERS:
            provider_name = maybe_provider
            model = maybe_model.strip()

    if not provider_name:
        model = model.strip()
        provider_name = "modelscope" if "/" in model else "sjtu"

    return provider_name, model


def summary_provider_config(
    provider_name: str, openai_api_key: str, openai_base_url: str
) -> tuple[str, str]:
    if provider_name == "modelscope":
        return (
            env_str("SUMMARY_OPENAI_API_KEY", openai_api_key),
            env_str("SUMMARY_OPENAI_BASE_URL", openai_base_url or SJTU_BASE_URL),
        )
    if provider_name == "sjtu":
        return (
            env_str(
                "SUMMARY_SJTU_OPENAI_API_KEY",
                env_str("SJTU_OPENAI_API_KEY", openai_api_key),
            ),
            env_str(
                "SUMMARY_SJTU_OPENAI_BASE_URL",
                env_str("SJTU_OPENAI_BASE_URL", SJTU_BASE_URL),
            ),
        )
    if provider_name == "prism":
        return (
            env_str(
                "SUMMARY_PRISM_OPENAI_API_KEY", env_str("PRISM_OPENAI_API_KEY", "")
            ),
            env_str("SUMMARY_PRISM_OPENAI_BASE_URL", PRISM_BASE_URL),
        )
    return "", ""


def build_summary_model_checks(
    summary_chain: str, openai_api_key: str, openai_base_url: str
) -> tuple[list[ModelCheck], list[str], bool]:
    checks_by_provider: dict[tuple[str, str, str], list[str]] = {}
    warnings: list[str] = []
    saw_summary_entry = False

    for entry in split_chain_entries(summary_chain):
        provider_name, model = parse_summary_model_entry(entry)
        if not model:
            continue
        saw_summary_entry = True
        api_key, base_url = summary_provider_config(
            provider_name, openai_api_key, openai_base_url
        )
        if not api_key or not base_url:
            warnings.append(
                f"WARNING: skipping summary provider without credentials: "
                f"{provider_name}:{model}"
            )
            continue
        checks_by_provider.setdefault((provider_name, api_key, base_url), []).append(
            model
        )

    checks: list[ModelCheck] = []
    for (provider_name, api_key, base_url), models in checks_by_provider.items():
        checks.append(
            ModelCheck(
                f"summary:{provider_name}",
                api_key,
                base_url,
                dedupe_models(models, base_url),
            )
        )
    return checks, warnings, saw_summary_entry


def merge_model_checks(checks: list[ModelCheck]) -> list[ModelCheck]:
    merged: dict[tuple[str, str], tuple[set[str], set[str]]] = {}
    for check in checks:
        if not check.api_key or not check.base_url or not check.models:
            continue
        models, labels = merged.setdefault(
            (check.api_key, check.base_url), (set(), set())
        )
        models.update(check.models)
        labels.add(check.label)

    result: list[ModelCheck] = []
    for (api_key, base_url), (models, labels) in merged.items():
        result.append(
            ModelCheck(
                ", ".join(sorted(labels)),
                api_key,
                base_url,
                tuple(sorted(models)),
            )
        )
    return result


def check_disk_space(
    min_gb: float = 5.0, path: str | Path | None = None
) -> tuple[bool, str]:
    """Check if enough disk space is available. Returns (ok, message)."""
    target = Path.cwd() if path is None else Path(path)
    try:
        usage = shutil.disk_usage(target)
        free_gb = usage.free / (1024**3)
        if free_gb < min_gb:
            return (
                False,
                f"CRITICAL: only {free_gb:.1f}GB free on {target} "
                f"(need {min_gb:.0f}GB minimum)",
            )
        if free_gb < min_gb * 2:
            return (
                True,
                f"WARNING: only {free_gb:.1f}GB free on {target} "
                f"(recommend {min_gb * 2:.0f}GB+)",
            )
        return True, f"Disk space OK on {target}: {free_gb:.1f}GB free"
    except Exception as exc:
        return False, f"CRITICAL: disk check failed for {target}: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--offline-ok",
        action="store_true",
        help="Do not call the remote /models endpoint.",
    )
    args = parser.parse_args()

    root = Path.cwd()
    if load_dotenv is not None:
        load_dotenv(root / ".env", override=False)

    # Disk space pre-check
    disk_ok, disk_msg = check_disk_space()
    print(f"💾 {disk_msg}")
    if not disk_ok:
        return 2

    required = ["OPENAI_API_KEY", "OPENAI_BASE_URL"]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        print(f"ERROR: missing required environment variables: {', '.join(missing)}")
        return 2

    openai_api_key = env_str("OPENAI_API_KEY")
    base_url = env_str("OPENAI_BASE_URL")
    print(f"OPENAI_BASE_URL={base_url}")
    print(f"OPENAI_API_KEY={mask(openai_api_key)}")

    model_vars = {
        "MODEL": env_str("MODEL", "minimax"),
        "FILTER_MODEL": env_str("FILTER_MODEL", "qwen"),
        "CLUSTER_MODEL": env_str("CLUSTER_MODEL", "glm"),
        "SUMMARY_MODEL": env_str("SUMMARY_MODEL", "minimax"),
    }
    for name, value in model_vars.items():
        print(f"{name}={value}")

    summary_chain = env_str(
        "SUMMARY_MODEL_CHAIN",
        env_str("PAPERTOOLS_DEFAULT_SUMMARY_MODEL_CHAIN", DEFAULT_SUMMARY_MODEL_CHAIN),
    )
    chain_vars = {
        "SUMMARY_MODEL_CHAIN": summary_chain,
    }
    filter_chain_name, filter_chain = first_nonempty_env(
        "PAPERTOOLS_FILTER_MODEL_CHAIN", "FILTER_MODEL_CHAIN"
    )
    cluster_chain_name, cluster_chain = first_nonempty_env(
        "PAPERTOOLS_CLUSTER_MODEL_CHAIN", "CLUSTER_MODEL_CHAIN"
    )
    chain_vars[filter_chain_name] = filter_chain
    chain_vars[cluster_chain_name] = cluster_chain
    for name, value in chain_vars.items():
        if value:
            print(f"{name}={value}")

    checks = [
        ModelCheck(
            "main/filter",
            openai_api_key,
            base_url,
            dedupe_models(
                [model_vars["MODEL"], model_vars["FILTER_MODEL"]]
                + split_models(filter_chain),
                base_url,
            ),
        )
    ]
    cluster_base_url = env_str("CLUSTER_OPENAI_BASE_URL", base_url)
    checks.append(
        ModelCheck(
            "cluster",
            env_str("CLUSTER_OPENAI_API_KEY", openai_api_key),
            cluster_base_url,
            dedupe_models(
                [model_vars["CLUSTER_MODEL"]] + split_models(cluster_chain),
                cluster_base_url,
            ),
        )
    )
    summary_checks, summary_warnings, saw_summary_entry = build_summary_model_checks(
        summary_chain, openai_api_key, base_url
    )
    for warning in summary_warnings:
        print(warning)
    if saw_summary_entry and not summary_checks:
        print("ERROR: no usable summary providers configured for SUMMARY_MODEL_CHAIN")
        return 2
    checks.extend(summary_checks)

    for check in checks:
        if not is_sjtu_base_url(check.base_url):
            continue
        unknown = sorted(model for model in check.models if model not in SJTU_MODELS)
        if unknown:
            print(
                f"ERROR: {check.label} model IDs are not in the known "
                "SJTU model_id list: " + ", ".join(unknown)
            )
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
        for check in merge_model_checks(checks):
            client = None
            print(f"Checking /models for {check.label} at {check.base_url}")
            try:
                client = create_openai_client(
                    api_key=check.api_key,
                    base_url=check.base_url,
                    timeout=20.0,
                    max_retries=0,
                )
                models = client.models.list()
                available = {
                    getattr(model, "id", "") for model in getattr(models, "data", [])
                }
                if not available:
                    print(
                        f"ERROR: remote /models returned no model IDs for {check.label}"
                    )
                    return 2
                missing_remote = sorted(
                    model for model in check.models if model not in available
                )
                if missing_remote:
                    print(
                        f"ERROR: requested models not returned by /models for "
                        f"{check.label}: " + ", ".join(missing_remote)
                    )
                    return 2
            except Exception as exc:
                print(f"ERROR: remote /models check failed for {check.label}: {exc}")
                print(
                    "Use --offline-ok only when intentionally running without /models."
                )
                return 2
            finally:
                if client is not None:
                    try:
                        client.close()
                    except Exception:
                        pass

    print("Preflight OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
