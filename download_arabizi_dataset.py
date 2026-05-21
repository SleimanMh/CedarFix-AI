import os
import sys
import subprocess
import importlib.util

DATASET_ID = "arbml/Arabizi_Transliteration"
OUTPUT_DIR = "Arabizi_Transliteration_Dataset"


def install_if_missing(package_name, import_name=None):
    import_name = import_name or package_name
    if importlib.util.find_spec(import_name) is None:
        print(f"Installing {package_name}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])


# Install required packages if missing
install_if_missing("datasets")
install_if_missing("pandas")
install_if_missing("pyarrow")
install_if_missing("huggingface_hub")

from datasets import load_dataset
from huggingface_hub import snapshot_download


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"Downloading dataset: {DATASET_ID}")

    # 1. Load dataset using Hugging Face datasets
    dataset = load_dataset(DATASET_ID)

    print("\nDataset loaded successfully:")
    print(dataset)

    # 2. Save each split as CSV and Parquet
    for split_name in dataset.keys():
        print(f"\nProcessing split: {split_name}")

        df = dataset[split_name].to_pandas()

        csv_path = os.path.join(OUTPUT_DIR, f"{split_name}.csv")
        parquet_path = os.path.join(OUTPUT_DIR, f"{split_name}.parquet")

        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        df.to_parquet(parquet_path, index=False)

        print(f"Saved CSV: {csv_path}")
        print(f"Saved Parquet: {parquet_path}")

    # 3. Download full raw Hugging Face dataset repository
    raw_repo_dir = os.path.join(OUTPUT_DIR, "raw_huggingface_repo")

    print("\nDownloading full raw Hugging Face dataset repo...")

    snapshot_download(
        repo_id=DATASET_ID,
        repo_type="dataset",
        local_dir=raw_repo_dir,
        local_dir_use_symlinks=False
    )

    print(f"Raw repo saved to: {raw_repo_dir}")

    print("\nDone.")
    print(f"All files are inside: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()