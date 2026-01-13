#!/usr/bin/env python3
"""
Convert single-file examples to folder-based structure.

This script:
1. Parses existing .py examples' docstrings to extract metadata
2. Creates folders for each example
3. Generates meta.json from the metadata
4. Creates flow.py with the code (minus metadata docstring)
5. Creates sandbox.py for sandbox examples
6. Creates core.yaml for infrastructure examples (where applicable)
"""

import json
import os
import re
import shutil
from pathlib import Path


def parse_metadata_from_docstring(content: str) -> dict:
    """Extract metadata from the docstring header."""
    # Match the docstring
    docstring_match = re.search(r'^"""(.*?)"""', content, re.DOTALL)
    if not docstring_match:
        docstring_match = re.search(r"^'''(.*?)'''", content, re.DOTALL)

    if not docstring_match:
        return None

    docstring = docstring_match.group(1)

    # Extract title (first line after #)
    title_match = re.search(r'^#\s*(.+)$', docstring, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else None

    # Extract metadata section
    metadata = {}

    # Product
    product_match = re.search(r'\*\*Product\*\*:\s*(.+?)(?:\n|$)', docstring)
    if product_match:
        product_raw = product_match.group(1).strip()
        # Normalize product names
        product_raw_lower = product_raw.lower()
        if 'sandbox' in product_raw_lower:
            metadata['products'] = ['blazing-flow-sandbox']
            metadata['primaryProduct'] = 'blazing-flow-sandbox'
        elif 'flow' in product_raw_lower:
            metadata['products'] = ['blazing-flow']
            metadata['primaryProduct'] = 'blazing-flow'
        elif 'core' in product_raw_lower:
            metadata['products'] = ['blazing-core']
            metadata['primaryProduct'] = 'blazing-core'
        else:
            metadata['products'] = ['blazing-flow']
            metadata['primaryProduct'] = 'blazing-flow'

    # Difficulty
    diff_match = re.search(r'\*\*Difficulty\*\*:\s*(.+?)(?:\n|$)', docstring)
    if diff_match:
        metadata['difficulty'] = diff_match.group(1).strip()

    # Time
    time_match = re.search(r'\*\*Time\*\*:\s*(.+?)(?:\n|$)', docstring)
    if time_match:
        metadata['time'] = time_match.group(1).strip()

    # Tags
    tags_match = re.search(r'\*\*Tags\*\*:\s*(.+?)(?:\n|$)', docstring)
    if tags_match:
        tags_raw = tags_match.group(1).strip()
        metadata['tags'] = [t.strip() for t in tags_raw.split(',')]

    # Description - everything between ## Description and ## What you'll learn
    desc_match = re.search(r'##\s*Description\s*\n(.*?)(?=##\s*What|$)', docstring, re.DOTALL)
    if desc_match:
        metadata['description'] = desc_match.group(1).strip()
    else:
        # Try to get first paragraph after title
        first_para = re.search(r'^#\s*.+?\n\n(.+?)(?=\n\n|$)', docstring, re.DOTALL)
        if first_para:
            metadata['description'] = first_para.group(1).strip()

    return {
        'title': title,
        **metadata
    }


def extract_code_without_docstring(content: str) -> str:
    """Remove the metadata docstring from the code."""
    # Match and remove the docstring at the start
    result = re.sub(r'^""".*?"""\n*', '', content, count=1, flags=re.DOTALL)
    if result == content:
        result = re.sub(r"^'''.*?'''\n*", '', content, count=1, flags=re.DOTALL)
    return result.strip()


def create_folder_structure(example_path: Path, output_base: Path):
    """Convert a single example file to folder structure."""
    # Read the original file
    with open(example_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Parse metadata
    metadata = parse_metadata_from_docstring(content)
    if not metadata or not metadata.get('title'):
        print(f"  SKIP: No valid metadata found in {example_path.name}")
        return False

    # Create folder name from file name (without .py)
    folder_name = example_path.stem
    folder_path = output_base / folder_name

    # Create the folder
    folder_path.mkdir(parents=True, exist_ok=True)

    # Generate meta.json
    meta = {
        'id': folder_name,
        'title': metadata.get('title', folder_name.replace('_', ' ').title()),
        'description': metadata.get('description', ''),
        'category': get_category_from_path(example_path),
        'difficulty': metadata.get('difficulty', 'Intermediate'),
        'time': metadata.get('time', '15 min'),
        'tags': metadata.get('tags', []),
        'products': metadata.get('products', ['blazing-flow']),
        'primaryProduct': metadata.get('primaryProduct', 'blazing-flow')
    }

    with open(folder_path / 'meta.json', 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2)
        f.write('\n')

    # Extract code without docstring
    code = extract_code_without_docstring(content)

    # Determine which file(s) to create based on product
    primary = meta['primaryProduct']

    if primary == 'blazing-flow-sandbox':
        # Create sandbox.py with the code
        with open(folder_path / 'sandbox.py', 'w', encoding='utf-8') as f:
            # Just write the code - metadata is in meta.json
            f.write(code)
            f.write('\n')

        # Also create a minimal flow.py that shows how to integrate
        create_minimal_flow(folder_path, meta)
    else:
        # Create flow.py with the code
        with open(folder_path / 'flow.py', 'w', encoding='utf-8') as f:
            # Just write the code - metadata is in meta.json
            f.write(code)
            f.write('\n')

    print(f"  OK: {example_path.name} -> {folder_name}/")
    return True


def create_minimal_flow(folder_path: Path, meta: dict):
    """Create a minimal flow.py for sandbox examples."""
    flow_code = f'''# {meta['title']} - Flow Integration
# This shows how to call the sandboxed code from a Blazing Flow workflow

from blazing import Blazing, run_sandboxed, create_signing_key

app = Blazing()

# Read the sandbox code
with open("sandbox.py", "r") as f:
    sandbox_code = f.read()

signing_key = create_signing_key()


@app.workflow
async def run_sandbox(input_data: dict, services=None) -> dict:
    """Execute the sandbox code securely."""
    result = await run_sandboxed(
        sandbox_code,
        input_data,
        signing_key=signing_key,
        func_name="main",  # Entry point in sandbox.py
        services=services
    )
    return result


if __name__ == "__main__":
    import asyncio

    async def main():
        await app.publish()
        result = await app.run_sandbox(input_data={{"test": True}}).wait_result()
        print(result)

    asyncio.run(main())
'''
    with open(folder_path / 'flow.py', 'w', encoding='utf-8') as f:
        f.write(flow_code)


def get_category_from_path(path: Path) -> str:
    """Determine category from the parent folder name."""
    parent = path.parent.name
    categories = {
        '01_getting_started': 'Getting Started',
        '02_web_endpoints': 'Web Endpoints',
        '03_data_processing': 'Data Processing',
        '04_async_parallel': 'Async & Parallel',
        '05_integrations': 'Integrations',
        '06_advanced': 'Advanced',
    }
    return categories.get(parent, 'General')


def main():
    """Main conversion function."""
    base_path = Path(__file__).parent

    # Categories to process
    categories = [
        '01_getting_started',
        '02_web_endpoints',
        '03_data_processing',
        '04_async_parallel',
        '05_integrations',
        '06_advanced',
    ]

    converted = 0
    skipped = 0

    for category in categories:
        category_path = base_path / category
        if not category_path.exists():
            continue

        print(f"\n=== {category} ===")

        # Find all .py files (not in subfolders, not __pycache__)
        for py_file in sorted(category_path.glob('*.py')):
            if py_file.name.startswith('_'):
                continue

            # Skip if already converted (folder exists with same name)
            folder_path = category_path / py_file.stem
            if folder_path.exists() and folder_path.is_dir():
                print(f"  SKIP: {py_file.name} (already converted)")
                skipped += 1
                continue

            if create_folder_structure(py_file, category_path):
                converted += 1
            else:
                skipped += 1

    print(f"\n=== Summary ===")
    print(f"Converted: {converted}")
    print(f"Skipped: {skipped}")
    print(f"\nNext steps:")
    print("1. Review the generated folders")
    print("2. Delete the original .py files once verified")
    print("3. Update generate_manifest.py to use new structure")


if __name__ == "__main__":
    main()
