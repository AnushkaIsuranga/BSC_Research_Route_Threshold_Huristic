"""Download and extract the H&M benchmark subset used in Phase A."""

from __future__ import annotations

import tarfile

import requests
from tqdm import tqdm

from src import BENCHMARK_DATA_DIR, HM_DATASET_URL, ensure_dir


def download_hm_dataset(url: str = HM_DATASET_URL, data_dir=BENCHMARK_DATA_DIR) -> None:
    ensure_dir(data_dir)
    dest_path = data_dir / "hnm.tgz"

    print(f"Downloading {url}...")
    response = requests.get(url, stream=True, timeout=60)
    response.raise_for_status()

    total_size = int(response.headers.get("content-length", 0))
    block_size = 1024 * 1024
    with dest_path.open("wb") as file, tqdm(
        desc=str(dest_path),
        total=total_size,
        unit="iB",
        unit_scale=True,
        unit_divisor=1024,
    ) as bar:
        for data in response.iter_content(block_size):
            file.write(data)
            bar.update(len(data))

    print("Extracting hnm.tgz...")
    with tarfile.open(dest_path, "r:gz") as tar:
        members = tar.getmembers()
        for member in tqdm(members, desc="Extracting"):
            tar.extract(member, path=data_dir)

    print("Extraction complete.")


def main() -> None:
    download_hm_dataset()

if __name__ == "__main__":
    main()
