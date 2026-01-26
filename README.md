<div align="center">
  <h1>img-sanitizer</h1>
</div>

<p align="center">
  <img src="https://img.shields.io/github/license/6c656c65/img-sanitizer?style=for-the-badge">
  <img src="https://img.shields.io/github/issues/6c656c65/img-sanitizer?style=for-the-badge">
  <img src="https://img.shields.io/github/issues-closed/6c656c65/img-sanitizer?style=for-the-badge">
  <br>
  <img src="https://img.shields.io/github/forks/6c656c65/img-sanitizer?style=for-the-badge">
  <img src="https://img.shields.io/github/stars/6c656c65/img-sanitizer?style=for-the-badge">
  <img src="https://img.shields.io/github/commit-activity/w/6c656c65/img-sanitizer?style=for-the-badge">
  <img src="https://img.shields.io/github/contributors/6c656c65/img-sanitizer?style=for-the-badge">
  <br>
  <img src="https://img.shields.io/pypi/v/img-sanitizer?style=for-the-badge">
  <img src="https://img.shields.io/pypi/pyversions/img-sanitizer?style=for-the-badge">
</p>

Python library designed to sanitize images by removing sensitive metadata.

## Features

- CLI tool to scan and sanitize images.
- Generates simple reports about findings.
- Designed to be used in scripts or as a developer tool.

## Installation

Install from PyPI with:

```bash
pip install img-sanitizer
```

Or install from source in an editable virtual environment:

```bash
git clone https://github.com/6C656C65/img-sanitizer.git
cd img-sanitizer
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Usage

After installation the CLI command is `img-sanitizer`.

Sanitize a source directory (or files) and write sanitized images to a destination directory:

```bash
img-sanitizer sanitize SOURCE DESTINATION --worker 4
```

- `SOURCE`: a directory containing images (or a file path). 
- `DESTINATION`: directory where sanitized images will be written.
- `--worker`: number of worker threads (default: 4).

Global flags:

- `--debug`: enable debug logging for more verbose output (global).

Other commands:

- `img-sanitizer version`: print the installed package version.

Check `--help` for subcommand and flag details:

```bash
img-sanitizer --help
img-sanitizer sanitize --help
```

## How it works

The project provides a small Python package (`img_sanitizer`) with a CLI entrypoint.

- `sanitizer.py` contains the core logic to inspect and sanitize image files.
- `report.py` builds a human-readable report from the sanitizer's findings.
- `cli.py` wires the command-line interface to the sanitizer and report generators.

Typical processing flow:

1. CLI parses command-line arguments and file paths.
2. The sanitizer opens each image, inspects metadata and content heuristics.
3. Any sensitive items are removed (when requested) or recorded in a report.
4. The report is printed to stdout or written to a file.

The tool is intentionally small and focused; it does not try to be a comprehensive forensic solution.

## Testing

The project includes unit tests (in the `tests/` directory). Run them with `pytest`:

```bash
pytest -q
```

## Contributing

Contributions are welcome. Please open issues for bugs or feature requests and submit PRs with tests.

## License

See the repository `LICENSE` for license details.# img-sanitizer
