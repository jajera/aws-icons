# AWS Icons

![GitHub Pages](https://github.com/jajera/aws-icons/actions/workflows/pages.yml/badge.svg)

A comprehensive web-based icon library for browsing and copying AWS Architecture Icons. This project provides an easy-to-use interface to search, filter, and download official AWS service icons, resource icons, category icons, and group icons.

## Features

- 🔍 **Search & Filter**: Search by service name, tags, or abbreviations across all icon types
- 🏷️ **Tag System**: Filter by categories, service types, and common abbreviations
- 🌓 **Dark Mode**: Toggle between light and dark themes
- 📋 **Copy to Clipboard**: Copy SVG code or download as PNG with original dimensions preserved
- 📱 **Responsive Design**: Works on desktop, tablet, and mobile devices
- 🎯 **Serverless Tagging**: Easily find serverless services
- 📖 **Descriptions**: Hover over icons to see detailed, unique descriptions for each icon
- 🎨 **Multiple Icon Types**: Browse service icons, resource icons, category icons, and group icons

## Statistics

- Icon count changes with AWS quarterly releases and local sync runs
- Sync never deletes icons; candidates missing from the latest package are listed for review

## Usage

1. Open `index.html` in your web browser
2. Use the search bar to find specific services
3. Click on tags to filter by category or service type
4. Hover over icons to see descriptions
5. Click the action buttons to copy SVG or download PNG

## Automated Icon Sync

Sync from the latest AWS Architecture Asset Package and rebuild `icons.json`:

- Local run: `python3 scripts/sync_aws_icons.py --repo-root .`
- CI run: `.github/workflows/sync-aws-icons.yml` (monthly schedule + manual dispatch)
  - commits and pushes changes to `main` automatically
  - then dispatches `pages.yml` so GitHub Pages updates (needed because `GITHUB_TOKEN` pushes do not cascade)

### Sync behavior

- **Add / update only** — existing icons are never deleted
- **In-place updates** — if a filename already exists, it is overwritten at the current path
- **Review list** — `icons-missing-from-latest.json` is overwritten each run with icons present in-repo but absent from the latest AWS package

### Naming Rules (Deterministic)

- `fullname` is generated from the AWS filename (`Arch_`/`Res_` prefix and size suffix removed)
- common acronyms are normalized (`API`, `S3`, `SQS`, `SNS`, `VPC`, `IAM`, `EC2`, etc.)
- `name` is a slug generated from `fullname`; collisions get a stable hash suffix
- existing descriptions are preserved by default unless `--no-keep-descriptions` is used

## Icon Types

### Service Icons (64x64)

Main AWS service icons organized by category:

- AI & Machine Learning (41 services)
- Analytics (21 services)
- Compute (25 services)
- Database (11 services)
- Storage (16 services)
- Networking (18 services)
- Security (27 services)
- Management (30 services)
- Integration (10 services)
- And 16 more categories

### Resource Icons (48x48)

Detailed resource-level icons for specific components and configurations within AWS services, perfect for detailed architecture diagrams.

### Category Icons (64x64)

High-level category icons representing AWS service categories.

### Group Icons (32x32)

Infrastructure grouping icons for representing collections of resources, subnets, regions, and organizational structures.

## Attribution

Icons are provided by [AWS Architecture Icons](https://aws.amazon.com/architecture/icons/). Use per [AWS Trademark Guidelines](https://aws.amazon.com/trademark-guidelines/).

## License

This project is open source and available under the MIT License.
