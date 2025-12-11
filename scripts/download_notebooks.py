#!/usr/bin/env python3
"""Download published Kaggle notebooks into the local dev workspace."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Sequence

from dotenv import dotenv_values

if TYPE_CHECKING:  # pragma: no cover - import only for static typing
    from kaggle.api.kaggle_api_extended import KaggleApi
    from kagglesdk.kernels.types.kernels_api_service import ApiKernelMetadata


REQUIRED_KEYS = {"KAGGLE_USERNAME", "KAGGLE_KEY"}
NOTEBOOK_EXTENSIONS = {
    "python": ".ipynb",
    "r": ".irnb",
    "julia": ".ijlnb",
}


def parse_env_file(path: Path, *, required: bool = True) -> Dict[str, str]:
    if not path.exists():
        if required:
            raise FileNotFoundError(f"Config file not found: {path}")
        return {}
    data = {key: value for key, value in dotenv_values(path).items() if value is not None}
    if required and not data:
        raise ValueError(f"No valid entries found in config: {path}")
    return data


def ensure_credentials(env: Dict[str, str], config_path: Path) -> Dict[str, str]:
    missing = REQUIRED_KEYS - env.keys()
    if missing:
        formatted = ", ".join(sorted(missing))
        raise KeyError(
            f"Missing required keys in {config_path}: {formatted}. "
            "Please update the config file."
        )
    return env


def configure_api(env: Dict[str, str]) -> "KaggleApi":
    os.environ["KAGGLE_USERNAME"] = env["KAGGLE_USERNAME"]
    os.environ["KAGGLE_KEY"] = env["KAGGLE_KEY"]
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
    except ImportError as error:  # pragma: no cover - dependency issue reported at runtime
        print(
            "[ERROR] Failed to import Kaggle dependencies. "
            "Install them via `uv sync` before running this script.",
            file=sys.stderr,
        )
        raise SystemExit(1) from error

    api = KaggleApi()
    api.authenticate()
    return api


def normalize_kernel_ref(owner: str, kernel: str) -> str:
    kernel = kernel.strip()
    if not kernel:
        raise ValueError("Kernel reference must not be empty.")
    if "/" in kernel:
        return kernel
    return f"{owner}/{kernel}"


def fetch_notebooks(
    api: KaggleApi,
    owner: str,
    include_private: bool,
    page_size: int,
) -> List[ApiKernelMetadata]:
    page = 1
    kernels: List[ApiKernelMetadata] = []
    while True:
        try:
            page_items: Sequence[ApiKernelMetadata | None] | None = api.kernels_list(
                page=page,
                page_size=page_size,
                mine=include_private,
                user=None if include_private else owner,
                kernel_type="notebook",
                sort_by="dateCreated",
            )
        except Exception as error:  # pragma: no cover - depends on network/API
            raise RuntimeError(f"Failed to list notebooks: {error}") from error

        if not page_items:
            break

        for kernel in page_items:
            if kernel is None:
                continue
            if not include_private and bool(kernel.is_private):
                continue
            kernels.append(kernel)

        page += 1
    return kernels


def determine_extension(kernel: ApiKernelMetadata) -> str:
    language = (kernel.language or "").lower()
    return NOTEBOOK_EXTENSIONS.get(language, ".ipynb")


def download_notebook(api: KaggleApi, kernel: ApiKernelMetadata, destination: Path, overwrite: bool) -> Path:
    extension = determine_extension(kernel)
    target_file = destination / f"{kernel.slug}{extension}"

    if target_file.exists() and not overwrite:
        raise FileExistsError(f"{target_file} already exists")

    try:
        api.kernels_pull(kernel.ref, path=str(destination), metadata=False, quiet=True)
    except Exception as error:  # pragma: no cover - depends on API/network
        raise RuntimeError(f"Failed to download {kernel.ref}: {error}") from error

    return target_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Download Kaggle notebooks into dev/.")
    parser.add_argument(
        "--config",
        default="config/kaggle.env",
        help="Path to the config file that stores Kaggle settings.",
    )
    parser.add_argument(
        "--secrets",
        default="config/kaggle.credentials.env",
        help="Path to the file that stores private Kaggle credentials (username/key).",
    )
    parser.add_argument(
        "--destination",
        default="dev",
        help="Directory to store downloaded notebooks (default: dev).",
    )
    parser.add_argument(
        "--owner",
        help="Kaggle username to pull notebooks for. Defaults to KAGGLE_NOTEBOOK_OWNER or KAGGLE_USERNAME.",
    )
    parser.add_argument(
        "--kernel",
        help="Download only the specified notebook (<owner>/<slug> or slug). Defaults to downloading all notebooks.",
    )
    parser.add_argument(
        "--include-private",
        action="store_true",
        help="Include private notebooks (requires authenticated access).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing notebooks instead of skipping.",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=50,
        help="Number of notebooks to fetch per API page (default: 50).",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    secrets_path = Path(args.secrets)
    try:
        env = parse_env_file(config_path)
        env.update(parse_env_file(secrets_path, required=False))
        env = ensure_credentials(env, config_path)
    except (FileNotFoundError, ValueError, KeyError) as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1

    owner = args.owner or env.get("KAGGLE_NOTEBOOK_OWNER") or env["KAGGLE_USERNAME"]

    try:
        api = configure_api(env)
    except SystemExit:
        return 1

    destination = Path(args.destination)
    destination.mkdir(parents=True, exist_ok=True)

    if args.kernel:
        try:
            kernel_ref = normalize_kernel_ref(owner, args.kernel)
            owner_slug, slug = kernel_ref.split("/", 1)
        except ValueError as error:
            print(f"[ERROR] {error}", file=sys.stderr)
            return 1

        assumed_file = destination / f"{slug}.ipynb"
        if assumed_file.exists() and not args.overwrite:
            print(f"- Skipping {kernel_ref} (already exists). Use --overwrite to re-download.")
            return 0

        try:
            api.kernels_pull(kernel_ref, path=str(destination), metadata=False, quiet=True)
        except Exception as error:  # pragma: no cover - depends on API/network
            print(f"[ERROR] Failed to download {kernel_ref}: {error}", file=sys.stderr)
            return 1

        print(f"- Downloaded {kernel_ref}")
        print("Done.", "downloaded=1", "skipped=0", "failed=0")
        return 0

    try:
        notebooks = fetch_notebooks(api, owner, args.include_private, max(1, args.page_size))
    except RuntimeError as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1

    if not notebooks:
        print(f"No notebooks found for owner '{owner}'.")
        return 0

    downloaded = 0
    skipped = 0
    failed: List[str] = []

    print(f"Found {len(notebooks)} notebooks. Downloading to {destination.resolve()} ...")
    for kernel in notebooks:
        extension = determine_extension(kernel)
        target_path = destination / f"{kernel.slug}{extension}"
        if target_path.exists() and not args.overwrite:
            print(f"- Skipping {kernel.ref} (already exists)")
            skipped += 1
            continue
        try:
            download_notebook(api, kernel, destination, args.overwrite)
        except (FileExistsError, RuntimeError) as error:
            print(f"[ERROR] {error}", file=sys.stderr)
            failed.append(kernel.ref)
            continue
        print(f"- Downloaded {kernel.ref} -> {target_path}")
        downloaded += 1

    print(
        "Done.",
        f"downloaded={downloaded}",
        f"skipped={skipped}",
        f"failed={len(failed)}",
    )

    if failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
