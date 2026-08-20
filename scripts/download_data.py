import requests
from tqdm import tqdm
import os
import tarfile

url = "https://storage.googleapis.com/ann-filtered-benchmark/datasets/hnm.tgz"
data_dir = os.path.join("ann-filtering-benchmark-datasets", "data")
os.makedirs(data_dir, exist_ok=True)
dest_path = os.path.join(data_dir, "hnm.tgz")

print(f"Downloading {url}...")
response = requests.get(url, stream=True)
total_size = int(response.headers.get('content-length', 0))
block_size = 1024 * 1024 # 1 Megabyte

with open(dest_path, 'wb') as file, tqdm(
        desc=dest_path,
        total=total_size,
        unit='iB',
        unit_scale=True,
        unit_divisor=1024,
    ) as bar:
    for data in response.iter_content(block_size):
        file.write(data)
        bar.update(len(data))

print("Extracting hnm.tgz...")
with tarfile.open(dest_path, "r:gz") as tar:
    # Get total number of members for progress bar
    members = tar.getmembers()
    for member in tqdm(members, desc="Extracting"):
        tar.extract(member, path=data_dir)

print("Extraction complete.")
