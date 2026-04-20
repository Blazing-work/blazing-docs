# Blazing Flow Sandbox - Isolated Model Inference
# This code runs in a customer's isolated namespace for secure inference

import json
from typing import Any


def preprocess_input(data: dict) -> dict:
    """
    Validate and preprocess user input before inference.
    Runs in sandbox to prevent malicious data from affecting the system.
    """
    # Validate input structure
    if not isinstance(data, dict):
        raise ValueError("Input must be a dictionary")

    if "features" not in data:
        raise ValueError("Input must contain 'features' key")

    features = data["features"]
    if not isinstance(features, dict):
        raise ValueError("Features must be a dictionary")

    # Sanitize and normalize
    sanitized = {}
    for key, value in features.items():
        # Only allow alphanumeric keys
        if not key.isalnum():
            continue

        # Convert to float and clamp to valid range
        try:
            val = float(value)
            val = max(0.0, min(1.0, val))  # Clamp to [0, 1]
            sanitized[key] = val
        except (ValueError, TypeError):
            continue

    return {"features": sanitized, "id": data.get("id", "unknown")}


def run_local_inference(features: dict) -> dict:
    """
    Run a lightweight inference model locally in the sandbox.
    This example uses a simple rule-based classifier.
    """
    # Simple weighted sum classifier (placeholder for real model)
    weights = {"x": 0.3, "y": 0.5, "z": 0.2}

    score = sum(
        features.get(k, 0.0) * w
        for k, w in weights.items()
    )

    # Classify based on threshold
    if score > 0.6:
        label = "high"
        confidence = min(score, 1.0)
    elif score > 0.3:
        label = "medium"
        confidence = 0.5 + (score - 0.3) * 1.67
    else:
        label = "low"
        confidence = 1.0 - score

    return {
        "label": label,
        "confidence": round(confidence, 4),
        "raw_score": round(score, 4)
    }


def format_output(prediction: dict, input_id: str) -> str:
    """
    Format the prediction output for display.
    """
    return json.dumps({
        "id": input_id,
        "prediction": prediction["label"],
        "confidence": prediction["confidence"],
        "details": {
            "raw_score": prediction["raw_score"]
        }
    }, indent=2)


# Main sandbox execution
if __name__ == "__main__":
    # Example input (would come from user in production)
    user_input = {
        "id": "sample-001",
        "features": {
            "x": 0.7,
            "y": 0.4,
            "z": 0.9
        }
    }

    print("Processing user input in sandbox...")

    # Step 1: Preprocess (sanitize user input)
    try:
        processed = preprocess_input(user_input)
        print(f"Preprocessed: {processed}")
    except ValueError as e:
        print(f"Input validation error: {e}")
        exit(1)

    # Step 2: Run inference
    prediction = run_local_inference(processed["features"])
    print(f"Prediction: {prediction}")

    # Step 3: Format output
    output = format_output(prediction, processed["id"])
    print(f"\nFinal output:\n{output}")
