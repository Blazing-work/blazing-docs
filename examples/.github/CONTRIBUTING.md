# Contributing to Blazing Examples

Thank you for your interest in contributing!

## Getting Started

1. **Fork the repository**

2. **Clone your fork**
   ```bash
   git clone https://github.com/YOUR_USERNAME/blazing-examples.git
   cd blazing-examples
   ```

3. **Set up development environment**
   ```bash
   uv venv --python 3.12
   uv pip install ruff blazing
   ```

4. **Create a branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Development Workflow

### Before committing

Run linting and formatting:
```bash
uv run ruff check --fix .
uv run ruff format .
```

### Commit messages

Follow conventional commits:
- `feat:` New example or feature
- `fix:` Bug fix in existing example
- `docs:` Documentation changes
- `chore:` Maintenance tasks

### Submitting a Pull Request

1. Push your branch to your fork
2. Open a PR against `main`
3. Fill out the PR template
4. Wait for CI checks to pass
5. Request a review

## Adding New Examples

### File structure

Place examples in the appropriate category folder:
```
XX_category_name/
  your_example.py
```

### Example template

Every example should include:
```python
"""
# Example Title

Brief description of what this example demonstrates.

## Metadata
- **Product**: Blazing Flow | Blazing Core
- **Difficulty**: Beginner | Intermediate | Advanced | Expert
- **Time**: X min
- **Tags**: tag1, tag2, tag3

## Description

Detailed description of the example.

## What you'll learn

- Learning point 1
- Learning point 2
"""

from blazing import Blazing


async def main():
    app = Blazing()

    # Your example code here

    await app.publish()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

### Update examples.json

Add your example to `examples.json` with all metadata.

## Code Style

- Python 3.10+ features allowed
- Use type hints where helpful
- Follow Ruff formatting (88 char line length)
- Keep examples focused and minimal
- Add comments explaining non-obvious code

## Questions?

Open an issue or start a discussion!
