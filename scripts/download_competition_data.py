#!/usr/bin/env python3
"""Helper script to download Kaggle competition data using a config file."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import shutil
import tempfile
from pathlib import Path
from typing import Dict
from zipfile import BadZipFile, ZipFile

from dotenv import dotenv_values


REQUIRED_KEYS = {"KAGGLE_USERNAME", "KAGGLE_KEY", "KAGGLE_COMPETITION"}


def parse_env_file(path: Path, *, required: bool = True) -> Dict[str, str]:
    if not path.exists():
        if required:
            raise FileNotFoundError(f"Config file not found: {path}")
        return {}
    data = {
        key: value
        for key, value in dotenv_values(path).items()
        if value is not None
    }
    if required and not data:
        raise ValueError(f"No valid entries found in config: {path}")
    return data


def ensure_requirements(env: Dict[str, str], config_path: Path) -> Dict[str, str]:
    missing = REQUIRED_KEYS - env.keys()
    if missing:
        formatted = ", ".join(sorted(missing))
        raise KeyError(
            f"Missing required keys in {config_path}: {formatted}. "
            "Please update the config file."
        )
    return env


def parse_input_datasets(raw_value: str | None) -> list[tuple[str, Path | None]]:
    if not raw_value:
        return []
    pairs: list[tuple[str, Path | None]] = []
    for entry in raw_value.split(","):
        stripped = entry.strip()
        if not stripped:
            continue
        if ":" in stripped:
            ref, destination = stripped.split(":", 1)
            ref = ref.strip()
            dest_path = Path(destination.strip())
        else:
            ref = stripped
            dest_path = None
        if "/" not in ref:
            raise ValueError(
                f"Invalid dataset reference '{ref}'. Expected format <owner>/<dataset>."
            )
        pairs.append((ref, dest_path))
    return pairs


def download_and_extract(env: Dict[str, str], final_destination: Path) -> None:
    final_destination.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="kaggle-download-") as tmp_dir:
        tmp_path = Path(tmp_dir)
        command = [
            "kaggle",
            "competitions",
            "download",
            "-c",
            env["KAGGLE_COMPETITION"],
            "-p",
            str(tmp_path),
        ]

        try:
            subprocess.run(command, check=True)
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                "kaggle CLI is not installed or not available in PATH. "
                "Install it via `pip install kaggle` or use the Kaggle Docker image."
            ) from exc

        zip_files = list(tmp_path.glob("*.zip"))
        if not zip_files:
            non_zip = list(tmp_path.iterdir())
            if not non_zip:
                raise RuntimeError("No files were downloaded from Kaggle.")
            for item in non_zip:
                target = final_destination / item.name
                if item.is_dir():
                    shutil.copytree(item, target, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, target)
            return

        for zip_file in zip_files:
            print(f"Extracting {zip_file.name} ...")
            try:
                with ZipFile(zip_file) as archive:
                    archive.extractall(final_destination)
            except BadZipFile as error:
                raise RuntimeError(f"Failed to extract {zip_file}: {error}") from error


def download_input_dataset(dataset_ref: str, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    print(f"Downloading dataset {dataset_ref} -> {destination.resolve()}")
    with tempfile.TemporaryDirectory(prefix="kaggle-input-") as tmp_dir:
        tmp_path = Path(tmp_dir)
        command = [
            "kaggle",
            "datasets",
            "download",
            "-d",
            dataset_ref,
            "-p",
            str(tmp_path),
        ]
        try:
            subprocess.run(command, check=True)
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                "kaggle CLI is not installed or not available in PATH. "
                "Install it via `pip install kaggle` or use the Kaggle Docker image."
            ) from exc

        zip_files = list(tmp_path.glob("*.zip"))
        if not zip_files:
            raise RuntimeError(f"No files were downloaded for dataset {dataset_ref}.")

        for zip_file in zip_files:
            print(f"Extracting dataset {zip_file.name} ...")
            try:
                with ZipFile(zip_file) as archive:
                    archive.extractall(destination)
            except BadZipFile as error:
                raise RuntimeError(f"Failed to extract {zip_file}: {error}") from error


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download Kaggle competition data using a config file."
    )
    parser.add_argument(
        "--config",
        default="config/kaggle.env",
        help="Path to the config file that stores general Kaggle settings.",
    )
    parser.add_argument(
        "--secrets",
        default="config/kaggle.credentials.env",
        help="Path to the file that stores private Kaggle credentials (username/key).",
    )
    parser.add_argument(
        "--destination",
        help="Override destination directory. Defaults to data/input/<competition>.",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    secrets_path = Path(args.secrets)
    try:
        env = parse_env_file(config_path)
        secrets = parse_env_file(secrets_path, required=False)
        env.update(secrets)
        env = ensure_requirements(env, config_path)
    except (FileNotFoundError, ValueError, KeyError) as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1

    input_datasets: list[tuple[str, Path | None]] = []
    try:
        input_datasets = parse_input_datasets(env.get("KAGGLE_INPUT_DATASETS"))
    except ValueError as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1

    destination = Path(
        args.destination
        or env.get("KAGGLE_DOWNLOAD_DIR")
        or f"data/input/{env['KAGGLE_COMPETITION']}"
    )

    os.environ.update({
        "KAGGLE_USERNAME": env["KAGGLE_USERNAME"],
        "KAGGLE_KEY": env["KAGGLE_KEY"],
    })

    try:
        download_and_extract(env, destination)
    except FileNotFoundError as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as error:
        print(
            f"[ERROR] kaggle CLI exited with {error.returncode}. "
            "Check credentials and competition access.",
            file=sys.stderr,
        )
        return error.returncode
    except RuntimeError as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1

    for dataset_ref, custom_dest in input_datasets:
        slug = dataset_ref.split("/", 1)[1]
        dataset_destination = Path(custom_dest or f"data/input/{slug}")
        try:
            download_input_dataset(dataset_ref, dataset_destination)
        except (FileNotFoundError, RuntimeError, subprocess.CalledProcessError) as error:
            print(f"[ERROR] Failed to fetch dataset {dataset_ref}: {error}", file=sys.stderr)
            return 1

    print(
        "Download complete. Files are saved under",
        destination.resolve(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
