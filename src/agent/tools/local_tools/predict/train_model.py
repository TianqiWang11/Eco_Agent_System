from __future__ import annotations

import argparse
import json
from dotenv import load_dotenv

from src.project_paths import SERVICE_ROOT
from .training import train


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the experimental tree growth model")
    parser.add_argument("--train", action="store_true", help="replace the current trained model")
    args = parser.parse_args()
    if not args.train:
        parser.error("training is explicit; pass --train after reviewing the current model")
    load_dotenv(SERVICE_ROOT / ".env", override=False)
    metadata = train()
    print(json.dumps({
        "model_name": metadata["model_name"],
        "model_version": metadata["model_version"],
        "training_rows": metadata["training_rows"],
        "species_count": metadata["species_count"],
        "features": metadata["features"],
        "plot_id_is_model_feature": metadata["plot_id_is_model_feature"],
        "validation": metadata["cross_validation"]["overall"],
        "baseline": metadata["cross_validation"]["baseline"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
