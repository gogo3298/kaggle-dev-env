#!/usr/bin/env python3
"""Utility to push a local notebook to Kaggle."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict

from dotenv import dotenv_values

REQUIRED_KEYS = {"KAGGLE_USERNAME", "KAGGLE_KEY"}


def parse_env_file(path: Path, *, required: bool) -> Dict[str, str]:
    if not path.exists():
        if required:
            raise FileNotFoundError(f"Config file not found: {path}")
        return {}
    data = {key: value for key, value in dotenv_values(path).items() if value is not None}
    if required and not data:
        raise ValueError(f"No valid entries found in config: {path}")
    return data


def ensure_credentials(env: Dict[str, str]) -> Dict[str, str]:
    missing = REQUIRED_KEYS - env.keys()
    if missing:
        raise KeyError(f"Missing required keys: {', '.join(sorted(missing))}")
    return env


def normalize_slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower())
    return re.sub(r"-+", "-", cleaned).strip("-")


def validate_slug(slug: str) -> str:
    normalized = normalize_slug(slug)
    if not normalized:
        raise ValueError("Slug must contain at least one alphanumeric character.")
    if normalized != slug:
        raise ValueError(
            f"Invalid slug '{slug}'. Suggested slug: '{normalized}'. "
            "Use lowercase letters, numbers, and dashes only."
        )
    return slug


def ensure_title_matches_slug(title: str, slug: str) -> str:
    if normalize_slug(title) == slug:
        return title
    fallback = slug.replace("-", " ").title()
    print(
        f"[INFO] Adjusted kernel title to '{fallback}' so that it matches slug '{slug}'.",
        file=sys.stderr,
    )
    return fallback


def build_metadata(
    username: str,
    slug: str,
    title: str,
    code_file: str,
    competition: str | None,
    enable_gpu: bool,
    enable_internet: bool,
    is_private: bool,
) -> Dict[str, object]:
    metadata: Dict[str, object] = {
        "id": f"{username}/{slug}",
        "title": title,
        "code_file": code_file,
        "language": "python",
        "kernel_type": "notebook",
        "is_private": str(is_private).lower(),
        "enable_gpu": str(enable_gpu).lower(),
        "enable_tpu": "false",
        "enable_internet": str(enable_internet).lower(),
        "keywords": [],
        "dataset_sources": [],
        "kernel_sources": [],
        "model_sources": [],
        "docker_image": "python",
    }
    if competition:
        metadata["competition_sources"] = [competition]
    else:
        metadata["competition_sources"] = []
    return metadata


def run_command(command: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(command, check=True, cwd=cwd)


def main() -> int:
    parser = argparse.ArgumentParser(description="Push a local notebook to Kaggle.")
    parser.add_argument("--config", default="config/kaggle.env", help="Path to general Kaggle settings file.")
    parser.add_argument(
        "--secrets",
        default="config/kaggle.credentials.env",
        help="Path to private Kaggle credentials (username/key).",
    )
    parser.add_argument("--notebook", required=True, help="Path to the notebook (.ipynb).")
    parser.add_argument("--slug", required=True, help="Kernel slug (lowercase letters, numbers, dashes).")
    parser.add_argument("--title", help="Kernel title; defaults to notebook name.")
    parser.add_argument(
        "--competition",
        help="Competition identifier used for kernel metadata (optional).",
    )
    parser.add_argument("--enable-gpu", action="store_true", help="Enable GPU for the kernel.")
    parser.add_argument("--enable-internet", action="store_true", help="Enable internet access for the kernel.")
    parser.add_argument("--private", action="store_true", help="Mark the kernel as private.")
    args = parser.parse_args()

    config_path = Path(args.config)
    secrets_path = Path(args.secrets)
    try:
        env = parse_env_file(config_path, required=False)
        env.update(parse_env_file(secrets_path, required=True))
        env = ensure_credentials(env)
    except (FileNotFoundError, ValueError, KeyError) as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1

    competition = args.competition or env.get("KAGGLE_COMPETITION")

    notebook_path = Path(args.notebook)
    if not notebook_path.exists():
        print(f"[ERROR] Notebook not found: {notebook_path}", file=sys.stderr)
        return 1

    try:
        validate_slug(args.slug)
    except ValueError as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1

    title = args.title or notebook_path.stem.replace("_", " ").title()
    title = ensure_title_matches_slug(title, args.slug)

    username = env["KAGGLE_USERNAME"]
    kernel_ref = f"{username}/{args.slug}"
    code_file = notebook_path.name

    os.environ.update({"KAGGLE_USERNAME": username, "KAGGLE_KEY": env["KAGGLE_KEY"]})

    try:
        with tempfile.TemporaryDirectory(prefix="kaggle-kernel-") as tmp_dir:
            tmp_path = Path(tmp_dir)
            shutil.copy2(notebook_path, tmp_path / code_file)
            metadata = build_metadata(
                username=username,
                slug=args.slug,
                title=title,
                code_file=code_file,
                competition=competition,
                enable_gpu=args.enable_gpu,
                enable_internet=args.enable_internet,
                is_private=args.private,
            )
            (tmp_path / "kernel-metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
            print(f"Pushing kernel {kernel_ref} ...")
            run_command(["kaggle", "kernels", "push", "-p", str(tmp_path)])
    except subprocess.CalledProcessError as error:
        print(f"[ERROR] kaggle CLI failed with exit code {error.returncode} during kernel push.", file=sys.stderr)
        return error.returncode
    except Exception as error:
        print(f"[ERROR] Failed to prepare kernel: {error}", file=sys.stderr)
        return 1

    print(
        "Kernel push complete. Track execution at",
        f"https://www.kaggle.com/code/{kernel_ref}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
