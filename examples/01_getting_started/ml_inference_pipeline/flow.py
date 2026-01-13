# Blazing Flow - ML Inference Pipeline Orchestration
# This pipeline handles batch inference with automatic scaling

import os
from blazing import Blazing, task, workflow

app = Blazing()

# Get configuration from environment
MODEL_ENDPOINT = os.getenv("MODEL_ENDPOINT", "http://model-server:8080")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "32"))


@task(retries=3, timeout=300)
async def preprocess_data(raw_data: list[dict]) -> list[dict]:
    """
    Preprocess raw input data for model inference.
    Handles data validation, normalization, and feature extraction.
    """
    processed = []
    for item in raw_data:
        # Validate required fields
        if "features" not in item:
            continue

        # Normalize numeric features
        features = item["features"]
        normalized = {
            k: (v - min(features.values())) / (max(features.values()) - min(features.values()) + 1e-8)
            for k, v in features.items()
        }

        processed.append({
            "id": item.get("id"),
            "features": normalized,
            "metadata": item.get("metadata", {})
        })

    return processed


@task(retries=2, timeout=60)
async def run_inference(batch: list[dict]) -> list[dict]:
    """
    Run model inference on a batch of preprocessed data.
    Calls the model server deployed via Blazing Core.
    """
    import httpx

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{MODEL_ENDPOINT}/predict",
            json={"inputs": batch},
            timeout=30.0
        )
        response.raise_for_status()
        return response.json()["predictions"]


@task(retries=1)
async def postprocess_results(predictions: list[dict], original_data: list[dict]) -> list[dict]:
    """
    Combine predictions with original data and format output.
    """
    results = []
    for pred, orig in zip(predictions, original_data):
        results.append({
            "id": orig["id"],
            "prediction": pred["label"],
            "confidence": pred["score"],
            "metadata": orig.get("metadata", {})
        })
    return results


@workflow
async def inference_pipeline(input_data: list[dict]) -> list[dict]:
    """
    Complete ML inference pipeline:
    1. Preprocess input data
    2. Batch and run inference
    3. Postprocess and return results
    """
    # Step 1: Preprocess
    processed = await preprocess_data(input_data)

    # Step 2: Batch inference (process in chunks)
    all_predictions = []
    for i in range(0, len(processed), BATCH_SIZE):
        batch = processed[i:i + BATCH_SIZE]
        predictions = await run_inference(batch)
        all_predictions.extend(predictions)

    # Step 3: Postprocess
    results = await postprocess_results(all_predictions, processed)

    return results


if __name__ == "__main__":
    # Example usage
    sample_data = [
        {"id": "1", "features": {"x": 0.5, "y": 0.3, "z": 0.8}},
        {"id": "2", "features": {"x": 0.1, "y": 0.9, "z": 0.2}},
    ]

    result = app.run(inference_pipeline(sample_data))
    print(f"Inference results: {result}")
