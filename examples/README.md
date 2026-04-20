# Blazing Examples

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

The official examples repository for [Blazing](https://blazing.work) - demonstrating real-world use cases for Blazing Core and Blazing Flow.

**Live Examples**: https://blazing.work/docs/examples

## About

This repository serves as the single source of truth for all Blazing examples. Examples are automatically:
- Displayed on the Blazing documentation website
- Tested in CI to ensure they work
- Available for the community to run, modify, and contribute

Inspired by [modal-examples](https://github.com/modal-labs/modal-examples).

## Repository Structure

```
blazing-examples/
├── 01_getting_started/      # Basic examples to get started
├── 02_web_endpoints/         # Web servers, APIs, HTTP endpoints
├── 03_data_processing/       # ETL, batch processing, data pipelines
├── 04_async_parallel/        # Async patterns and parallel execution
├── 05_integrations/          # Third-party service integrations
├── 06_advanced/              # Advanced patterns and techniques
├── generate_manifest.py      # Generates examples.json manifest
└── examples.json             # Generated manifest (auto-updated)
```

## Categories

### 01_getting_started
Basic examples to help you get started quickly with Blazing Core and Flow.

### 02_web_endpoints
Examples of web servers, REST APIs, GraphQL endpoints, and WebSocket servers.

### 03_data_processing
Data transformation, ETL pipelines, and batch processing examples.

### 04_async_parallel
Asynchronous programming patterns and parallel execution for maximum throughput.

### 05_integrations
Integration examples with popular services (databases, APIs, cloud services).

### 06_advanced
Advanced patterns including CRDT queues, custom runtimes, and zero-trust networking.

## Running Examples

### Prerequisites

```bash
# Install Blazing
pip install blazing

# Configure credentials
blazing configure
```

### Run Locally

```bash
# Navigate to an example
cd 01_getting_started

# Run the example
python hello_world.py
```

### Deploy to Production

```bash
blazing deploy hello_world.py
```

## Writing Examples

### Example Template

Each example should follow this structure:

```python
"""
# Example Title

Brief description of what this example demonstrates.

## Metadata
- **Product**: Blazing Core | Blazing Flow
- **Difficulty**: Beginner | Intermediate | Advanced | Expert
- **Time**: X min
- **Tags**: tag1, tag2, tag3

## Description

Detailed description of:
- What this example does
- Key concepts demonstrated
- Use cases

## What you'll learn

- Bullet point 1
- Bullet point 2
- Bullet point 3
"""

# Your example code here
```

### Adding a New Example

1. Choose the appropriate category directory
2. Create a new `.py` file with a descriptive name (use underscores)
3. Follow the template above
4. Add metadata in the docstring
5. Write clear, well-commented code
6. Test your example locally
7. Run the manifest generator:

```bash
python generate_manifest.py
```

8. Commit and push:

```bash
git add .
git commit -m "Add: [example name]"
git push
```

The documentation website will automatically update with your new example!

## Manifest System

The `generate_manifest.py` script scans all example files and creates `examples.json`, which contains:

- Example metadata (title, description, difficulty, etc.)
- Category and product associations
- GitHub URLs for each example
- Tags for searchability

This manifest is consumed by the documentation website at build time.

### Regenerating the Manifest

```bash
python generate_manifest.py
```

This should be run automatically in CI, but you can run it locally to preview changes.

## Contributing

We welcome contributions! To contribute an example:

1. Fork this repository
2. Create a new branch (`git checkout -b feature/my-example`)
3. Add your example following the guidelines above
4. Test your example locally
5. Run `python generate_manifest.py`
6. Commit your changes
7. Push to your fork
8. Open a Pull Request

### Contribution Guidelines

- **Quality over quantity**: Examples should be production-ready and well-documented
- **Clear documentation**: Every example must have a comprehensive docstring
- **Working code**: All examples must run successfully
- **Follow conventions**: Use the template structure and naming conventions
- **Test before submitting**: Run your example locally and ensure it works

## Example Metadata Fields

| Field | Required | Description | Example |
|-------|----------|-------------|---------|
| Product | Yes | Which product (Blazing Core or Blazing Flow) | `Blazing Core` |
| Difficulty | Yes | Skill level required | `Beginner`, `Intermediate`, `Advanced`, `Expert` |
| Time | Yes | Estimated time to complete | `10 min` |
| Tags | Yes | Comma-separated searchable tags | `api, fastapi, rest` |

## CI/CD

This repository uses GitHub Actions to:
- Validate all examples compile
- Run example tests
- Generate and commit updated `examples.json`
- Deploy examples to staging environment

## License

MIT License - see [LICENSE](LICENSE) for details

## Resources

- **Documentation**: https://blazing.work/docs
- **Website**: https://blazing.work
- **GitHub**: https://github.com/Blazing-work
- **Discord**: https://discord.gg/blazing

---

**Questions?** Open an issue or reach out on [Discord](https://discord.gg/blazing)
