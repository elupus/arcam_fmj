# arcam_fmj

Python library for controlling Arcam AV receivers.

## Upstream

The upstream repository is [elupus/arcam_fmj](https://github.com/elupus/arcam_fmj). We are very respectful of the upstream maintainer's (elupus) feedback and preferences. When preparing changes for upstream, follow the existing code style and conventions closely.

## Fork-only files

The following files exist only in this fork and **must not** be included in PRs to upstream:

- `flake.nix`, `flake.lock`
- `.envrc`
- `CLAUDE.md`, `.claude/`

Remove or exclude these before submitting anything to elupus. This includes references in e.g. .gitignore

## Development environment

This project runs on NixOS without much on the global PATH. The nix devshell (activated automatically via direnv) provides `uv` and `python3`.

- **Package management & virtualenv**: Use `uv` (e.g. `uv sync`, `uv run`).
- **Testing**: `uv run pytest` (install test deps with `uv sync --extra tests`).
- **Running the CLI**: `uv run arcam-fmj`.

## Commits

Let the user review changes before committing. When committing, use [Conventional Commits](https://www.conventionalcommits.org/) style (e.g. `fix:`, `feat:`, `chore:`, `docs:`).

## Specs and Reference Implementation

The protocol specs live as committed Markdown in `docs/specs/` (see `docs/specs/README.md` for the model → document mapping and links to the original PDFs). They are generated from Arcam's official PDFs by `nix run '.#fetch-specs'`; re-run that when the upstream documents change.

NOTE: The PDFs _mostly_ translate well into markdown, _except_ table ordering - often tables are offset from the text they belong to, especially with regard to command reference: in the PDF, a command description will be in the left column and a table with the data layout in the right; in the markdown you'll see a whole group of descriptions followed by a whole group of tables.

## Firmware dump

See `docs/Firmware Dump.md` for full details. Highlights:

Run `nix run '.#fetch-firmware'` to download the official AVRx1 firmware bundle and unpack it into `.firmware/`.

Arcam's own embedded "setup" web app lives at `.firmware/net/rootfs/www/pages/setup/`. It is their implementation of the protocol, and examining its code can be as useful as reading the specifications. (Though, keep in mind their implementation has its shortcomings too.)
