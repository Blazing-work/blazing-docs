# Blazing Documentation

[![License: CC BY 4.0](https://img.shields.io/badge/License-CC%20BY%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by/4.0/)

The official documentation repository for [Blazing](https://blazing.work) - comprehensive guides, tutorials, and references for Blazing Core and Blazing Flow.

**Live Documentation**: https://blazing.work/docs

## About

This repository serves as the single source of truth for all Blazing documentation. Documentation is automatically:
- Displayed on the Blazing documentation website
- Version controlled and tracked through Git
- Open for community contributions and improvements
- Rendered with proper syntax highlighting and navigation

Inspired by [Stripe's documentation approach](https://github.com/stripe/stripe-docs).

## Repository Structure

```
blazing-docs/
├── getting-started/          # Getting started guides
├── core-concepts/            # Core concepts and architecture
├── core-compose/             # Blazing Core Compose documentation
├── blazing-flow/             # Blazing Flow documentation
├── flow-sandbox/             # Flow Sandbox guides
├── gateway-introduction/     # Gateway documentation
├── tutorials/                # Step-by-step tutorials
├── api-reference/            # API reference documentation
├── providers/                # Cloud provider guides
├── services/                 # Service configuration
├── deployment/               # Deployment guides
├── governance/               # Governance and security
├── voip-lb/                  # VoIP load balancer docs
└── meta.json files           # Category configuration
```

## Documentation Categories

### Getting Started
Quick start guides to get up and running with Blazing products in minutes.

### Core Concepts
Deep dives into the architecture, design principles, and core concepts behind Blazing.

### Blazing Core
Complete documentation for Blazing Core - infrastructure as code with multi-cloud support.

### Blazing Flow
Comprehensive guides for Blazing Flow - distributed task orchestration and workflows.

### Tutorials
Step-by-step tutorials for common use cases and implementation patterns.

### API Reference
Complete API documentation for all Blazing products and services.

## Contributing to Documentation

We welcome contributions! Whether you're fixing a typo, improving clarity, or adding new content, your help makes our documentation better for everyone.

### How to Contribute

1. **Fork this repository**
2. **Create a new branch**:
   ```bash
   git checkout -b docs/improve-getting-started
   ```
3. **Make your changes** following our style guide
4. **Test locally** (optional but recommended)
5. **Commit your changes**:
   ```bash
   git add .
   git commit -m "docs: improve getting started guide clarity"
   ```
6. **Push to your fork**:
   ```bash
   git push origin docs/improve-getting-started
   ```
7. **Open a Pull Request** with a clear description of your changes

### Contribution Guidelines

- **Clarity first**: Write for understanding, not just completeness
- **Use examples**: Show, don't just tell - include code examples
- **Be concise**: Respect the reader's time - get to the point
- **Test your changes**: If possible, test code examples before submitting
- **Follow structure**: Keep the existing document structure and hierarchy
- **Check formatting**: Ensure proper Markdown formatting and syntax

## Documentation Style Guide

### Writing Style

- **Use active voice**: "Deploy your application" not "Your application is deployed"
- **Be direct**: Start with the action, not the explanation
- **Use present tense**: "Blazing creates" not "Blazing will create"
- **Address the reader**: Use "you" and "your", not "the user"
- **Keep it simple**: Avoid jargon unless necessary (and define it when you use it)

### Code Examples

- **Complete and runnable**: All code examples should work out of the box
- **Include context**: Show imports, setup, and any required configuration
- **Add comments**: Explain what non-obvious code does
- **Follow best practices**: Show the right way to do things

Example:
```python
"""
Basic Task Example

This example shows how to create and run a simple task with Blazing Flow.
"""

from blazing import flow

@flow.task
def process_data(data: str) -> str:
    """Process the input data and return result."""
    return data.upper()

# Run the task
result = process_data("hello world")
print(result)  # Output: HELLO WORLD
```

### Formatting

- **Headings**: Use ATX-style headings (`#`, `##`, `###`)
- **Code blocks**: Always specify the language for syntax highlighting
- **Lists**: Use `-` for unordered lists, `1.` for ordered lists
- **Links**: Use descriptive link text, not "click here"
- **Emphasis**: Use `**bold**` for UI elements, `*italic*` for emphasis

## File Structure

Each documentation directory should contain:

1. **meta.json**: Category configuration
   ```json
   {
     "title": "Getting Started",
     "label": "Getting Started",
     "position": 1,
     "description": "Quick start guides for Blazing products",
     "product": "blazing-core",
     "category": "guide"
   }
   ```

2. **MDX files**: Documentation content with optional React components
   ```markdown
   ---
   title: "Quick Start"
   label: "Quick Start"
   position: 1
   description: "Get started with Blazing Core in 5 minutes"
   ---

   # Quick Start

   Your content here...
   ```

## Testing Documentation Locally

To preview your changes locally before submitting:

1. **Clone the main website repository**:
   ```bash
   git clone https://github.com/Blazing-work/blazing-website
   cd blazing-website
   ```

2. **Link your local docs**:
   ```bash
   # The website reads from the _docs directory
   # You can symlink your local blazing-docs to test
   ```

3. **Run the development server**:
   ```bash
   npm install
   npm run dev
   ```

4. **Visit**: http://localhost:3001/docs

## License

This documentation is licensed under the [Creative Commons Attribution 4.0 International License](https://creativecommons.org/licenses/by/4.0/).

You are free to:
- **Share**: Copy and redistribute the material in any medium or format
- **Adapt**: Remix, transform, and build upon the material for any purpose, even commercially

Under the following terms:
- **Attribution**: You must give appropriate credit to Blazing, provide a link to the license, and indicate if changes were made

See the [LICENSE](LICENSE) file for the full license text.

## Questions or Issues?

- **Documentation issues**: Open an issue in this repository
- **Product issues**: Open an issue in the respective product repository
- **General questions**: Join our [Discord community](https://discord.gg/blazing)
- **Email support**: admin@blazing.work

## Resources

- **Website**: https://blazing.work
- **Documentation**: https://blazing.work/docs
- **GitHub**: https://github.com/Blazing-work
- **Discord**: https://discord.gg/blazing
- **Examples**: https://github.com/Blazing-work/blazing-examples

---

**Contributing to documentation?** Thank you! Every improvement helps the entire community.
