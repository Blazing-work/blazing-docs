#!/usr/bin/env python3
"""
Generate examples.json manifest from example folders.

This script scans all example folders, reads metadata from their meta.json files,
and generates a manifest file that can be consumed by the documentation website
and the Playground feature.

New Structure (folder-based):
  01_getting_started/
    hello_world/
      meta.json       <- Example metadata
      flow.py         <- Blazing Flow code (primary runner)
      sandbox.py      <- Optional: Sandbox code
      core.yaml       <- Optional: Core infrastructure

Legacy Structure (file-based):
  01_getting_started/
    hello_world.py    <- All-in-one with docstring metadata
"""

import json
import re
from pathlib import Path


def load_folder_metadata(folder_path: Path) -> dict | None:
    """Load metadata from a folder-based example."""
    meta_file = folder_path / "meta.json"
    if not meta_file.exists():
        return None

    with open(meta_file, "r", encoding="utf-8") as f:
        meta = json.load(f)

    # Determine which files exist
    files = {
        "flow": (folder_path / "flow.py").exists(),
        "sandbox": (folder_path / "sandbox.py").exists(),
        "core": (folder_path / "core.yaml").exists(),
    }

    return {
        **meta,
        "files": files,
        "is_folder": True,
    }


def extract_legacy_metadata(content: str) -> dict | None:
    """Extract metadata from legacy single-file example docstring."""
    # Find the docstring
    docstring_match = re.search(r'"""(.*?)"""', content, re.DOTALL)
    if not docstring_match:
        return None

    docstring = docstring_match.group(1)

    # Extract title (first line starting with #)
    title_match = re.search(r"^#\s+(.+)$", docstring, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else None

    # Extract description (first paragraph after title)
    desc_match = re.search(
        r"^#.*?\n\n(.+?)(?:\n\n|##)", docstring, re.DOTALL | re.MULTILINE
    )
    description = desc_match.group(1).strip() if desc_match else None

    # Extract metadata section
    metadata = {}
    metadata_section = re.search(r"## Metadata\n(.*?)(?:\n##|$)", docstring, re.DOTALL)
    if metadata_section:
        for line in metadata_section.group(1).strip().split("\n"):
            if match := re.match(r"-\s+\*\*(.+?)\*\*:\s+(.+)", line):
                key = match.group(1).lower().replace(" ", "_")
                value = match.group(2).strip()
                metadata[key] = value

    return {
        "title": title,
        "description": description,
        **metadata,
        "is_folder": False,
    }


def generate_manifest(repo_path: Path) -> list[dict]:
    """Generate manifest from all examples (folder-based and legacy)."""
    examples = []

    # Category directories to scan
    category_dirs = [
        d for d in sorted(repo_path.iterdir())
        if d.is_dir() and not d.name.startswith(".") and "_" in d.name
    ]

    for category_dir in category_dirs:
        # Extract category info
        parts = category_dir.name.split("_", 1)
        if len(parts) != 2:
            continue
        category_num, category_name = parts

        # Scan for folder-based examples first
        for item in sorted(category_dir.iterdir()):
            if not item.is_dir() or item.name.startswith("_"):
                continue

            # Try to load folder metadata
            metadata = load_folder_metadata(item)
            if metadata:
                example = build_example_entry(
                    metadata, category_dir.name, category_name, item.name
                )
                examples.append(example)
                continue

        # Then scan for legacy single-file examples
        for example_file in sorted(category_dir.glob("*.py")):
            if example_file.name.startswith("_"):
                continue

            # Skip if there's a folder with the same name
            folder_path = category_dir / example_file.stem
            if folder_path.exists() and folder_path.is_dir():
                continue

            # Read and parse example
            content = example_file.read_text()
            metadata = extract_legacy_metadata(content)

            if not metadata or not metadata.get("title"):
                print(f"Warning: Skipping {example_file} - no valid metadata found")
                continue

            example = build_legacy_example_entry(
                metadata, category_dir.name, category_name, example_file.name
            )
            examples.append(example)

    return examples


def build_example_entry(
    metadata: dict, category_dir_name: str, category_name: str, folder_name: str
) -> dict:
    """Build example entry for folder-based examples."""
    return {
        "id": metadata.get("id", folder_name),
        "title": metadata.get("title", folder_name.replace("_", " ").title()),
        "description": metadata.get("description", ""),
        "category": metadata.get("category", category_name.replace("_", " ").title()),
        "difficulty": metadata.get("difficulty", "Intermediate"),
        "time": metadata.get("time", "15 min"),
        "tags": metadata.get("tags", []),
        "products": metadata.get("products", ["blazing-flow"]),
        "primaryProduct": metadata.get("primaryProduct", "blazing-flow"),
        "files": metadata.get("files", {"flow": True}),
        "folder_path": f"{category_dir_name}/{folder_name}",
        "github_url": f"https://github.com/Blazing-work/blazing-examples/blob/main/{category_dir_name}/{folder_name}",
        "href": f"/docs/{folder_name}",
    }


def build_legacy_example_entry(
    metadata: dict, category_dir_name: str, category_name: str, file_name: str
) -> dict:
    """Build example entry for legacy single-file examples."""
    file_stem = file_name.replace(".py", "")
    product = metadata.get("product", "Blazing Flow").lower().replace(" ", "-")

    return {
        "id": file_stem,
        "title": metadata.get("title", file_stem.replace("_", " ").title()),
        "description": metadata.get("description", ""),
        "category": category_name.replace("_", " ").title(),
        "difficulty": metadata.get("difficulty", "Intermediate"),
        "time": metadata.get("time", "15 min"),
        "tags": [tag.strip() for tag in metadata.get("tags", "").split(",") if tag.strip()],
        "products": [product],
        "primaryProduct": product,
        "files": {"flow": True},  # Legacy files are always flow
        "folder_path": f"{category_dir_name}/{file_name}",
        "github_url": f"https://github.com/Blazing-work/blazing-examples/blob/main/{category_dir_name}/{file_name}",
        "href": f"/docs/{file_stem}",
    }


def main():
    """Main entry point."""
    repo_path = Path(__file__).parent

    print("Scanning for examples...")
    examples = generate_manifest(repo_path)

    print(f"Found {len(examples)} examples")

    # Write manifest
    manifest_path = repo_path / "examples.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(examples, f, indent=2)
        f.write("\n")

    print(f"Manifest written to {manifest_path}")

    # Print summary
    print("\nExamples by category:")
    from collections import Counter

    categories = Counter(ex["category"] for ex in examples)
    for category, count in sorted(categories.items()):
        print(f"  {category}: {count}")

    print("\nExamples by primary product:")
    products = Counter(ex["primaryProduct"] for ex in examples)
    for product, count in sorted(products.items()):
        print(f"  {product}: {count}")

    print("\nExamples with sandbox code:")
    sandbox_count = sum(1 for ex in examples if ex.get("files", {}).get("sandbox"))
    print(f"  {sandbox_count} examples")

    print("\nExamples with core.yaml:")
    core_count = sum(1 for ex in examples if ex.get("files", {}).get("core"))
    print(f"  {core_count} examples")


if __name__ == "__main__":
    main()
