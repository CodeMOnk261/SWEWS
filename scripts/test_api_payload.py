import argparse
import json
from typing import List

import numpy as np
import requests


SEQ_LEN = 12
NUM_FEATURES = 192


def build_payload(mode: str) -> dict:
    rng = np.random.default_rng(42)
    sequence = np.zeros((SEQ_LEN, NUM_FEATURES), dtype=np.float32)

    if mode == "random":
        sequence = rng.normal(0.0, 0.2, size=(SEQ_LEN, NUM_FEATURES)).astype(np.float32)
    elif mode == "elevated":
        sequence = rng.normal(0.0, 0.15, size=(SEQ_LEN, NUM_FEATURES)).astype(np.float32)
        sequence[:, 0] = rng.normal(1.2, 0.1, size=SEQ_LEN)
        sequence[:, 1] = rng.normal(0.8, 0.1, size=SEQ_LEN)
        sequence[:, 2] = rng.normal(1.5, 0.1, size=SEQ_LEN)

    return {"sequence": sequence.tolist()}


def post_payload(api_url: str, payload: dict) -> dict:
    response = requests.post(f"{api_url.rstrip('/')}/predict", json=payload, timeout=30)
    response.raise_for_status()
    return response.json()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate and optionally post a SWEWS test payload.")
    parser.add_argument("--mode", choices=["zeros", "random", "elevated"], default="random")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--post", action="store_true", help="Post the payload to the running API.")
    args = parser.parse_args()

    payload = build_payload(args.mode)

    if args.post:
        result = post_payload(args.api_url, payload)
        print(json.dumps(result, indent=2))
        return

    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
