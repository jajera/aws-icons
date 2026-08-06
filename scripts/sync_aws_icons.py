#!/usr/bin/env python3
"""Sync AWS architecture icons and rebuild icons.json deterministically."""

from __future__ import annotations

import argparse
import collections
import datetime
import hashlib
import json
import re
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Iterable

ICON_PAGE_URL = "https://aws.amazon.com/architecture/icons/"
ASSET_PACKAGE_RE = re.compile(
    r"https://[^\"'\s>]*(?:Asset-Package|Icon-package)[^\"'\s>]*\.zip",
    re.IGNORECASE,
)

CATEGORY_ALIASES = {
    "analytics": "analytics",
    "app-integration": "integration",
    "application-integration": "integration",
    "artificial-intelligence": "ai",
    "blockchain": "blockchain",
    "business-applications": "business",
    "cloud-financial-management": "financial",
    "compute": "compute",
    "contact-center": "business",
    "customer-experience": "customer",
    "customer-enablement": "customer",
    "database": "database",
    "databases": "database",
    "developer-tools": "developer",
    "end-user-computing": "enduser",
    "front-end-web-mobile": "frontend",
    "games": "games",
    "general": "general",
    "general-icons": "general",
    "integration": "integration",
    "internet-of-things": "iot",
    "iot": "iot",
    "machine-learning": "ai",
    "management-governance": "management",
    "management-tools": "management",
    "media-services": "media",
    "migration-modernization": "migration",
    "multicloud-and-hybrid": "general",
    "networking-content-delivery": "networking",
    "quantum-technologies": "quantum",
    "satellite": "satellite",
    "security-identity": "security",
    "security-identity-compliance": "security",
    "serverless": "general",
    "storage": "storage",
    "48-dark": "general",
    "48-light": "general",
}

GROUP_KEYWORDS_TO_CATEGORY = {
    "subnet": "networking",
    "vpc": "networking",
    "greengrass": "iot",
    "ec2": "compute",
    "spot": "compute",
    "scaling": "compute",
}

ACRONYMS = {
    "acl": "ACL",
    "ami": "AMI",
    "api": "API",
    "asg": "ASG",
    "aws": "AWS",
    "az": "AZ",
    "ca": "CA",
    "cidr": "CIDR",
    "cpu": "CPU",
    "db": "DB",
    "dms": "DMS",
    "dns": "DNS",
    "ebs": "EBS",
    "ec2": "EC2",
    "ecr": "ECR",
    "ecs": "ECS",
    "efs": "EFS",
    "eks": "EKS",
    "emr": "EMR",
    "eni": "ENI",
    "etl": "ETL",
    "fsx": "FSx",
    "ftp": "FTP",
    "gpu": "GPU",
    "iam": "IAM",
    "iot": "IoT",
    "json": "JSON",
    "kms": "KMS",
    "nat": "NAT",
    "nlb": "NLB",
    "nacl": "NACL",
    "ocu": "OCU",
    "pci": "PCI",
    "ram": "RAM",
    "rds": "RDS",
    "sdk": "SDK",
    "sns": "SNS",
    "sqs": "SQS",
    "s3": "S3",
    "ssl": "SSL",
    "ssh": "SSH",
    "sql": "SQL",
    "sts": "STS",
    "tcp": "TCP",
    "tls": "TLS",
    "udp": "UDP",
    "ui": "UI",
    "url": "URL",
    "vpc": "VPC",
    "vpn": "VPN",
    "waf": "WAF",
    "wfs": "WFS",
    "xml": "XML",
}

PHRASE_REPLACEMENTS = {
    "Simple Storage Service": "S3",
    "Simple Queue Service": "SQS",
    "Simple Notification Service": "SNS",
    "Virtual Private Cloud": "VPC",
}

HEX_COLOR_RE = re.compile(r'fill="#([0-9a-fA-F]{6})"')


def _read_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "aws-icons-sync/1.0"},
    )
    with urllib.request.urlopen(request) as response:
        return response.read().decode("utf-8", errors="replace")


def discover_latest_asset_zip(icon_page_url: str) -> str:
    html = _read_text(icon_page_url).replace("\\/", "/")
    matches = ASSET_PACKAGE_RE.findall(html)
    unique = []
    for match in matches:
        if match not in unique:
            unique.append(match)
    if not unique:
        raise RuntimeError(f"Could not find Asset-Package zip URL in {icon_page_url}")
    return unique[0]


def download(url: str, destination: Path) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "aws-icons-sync/1.0"},
    )
    with urllib.request.urlopen(request) as response:
        final_url = response.geturl()
        with destination.open("wb") as handle:
            shutil.copyfileobj(response, handle)
    return final_url


def _normalize_category_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def category_slug(raw: str) -> str:
    key = _normalize_category_key(raw)
    return CATEGORY_ALIASES.get(key, key)


def detect_icon_kind(path: Path) -> str | None:
    rel = path.as_posix()
    name = path.name
    if "__MACOSX" in rel:
        return None
    if "Architecture-Service-Icons_" in rel and name.startswith("Arch_") and name.endswith("_64.svg"):
        return "service"
    if (
        "Resource-Icons_" in rel
        and name.startswith("Res_")
        and re.search(r"_48(?:_(Light|Dark))?\.svg$", name)
    ):
        return "resource"
    if "Category-Icons_" in rel and name.startswith("Arch-Category_") and name.endswith("_64.svg"):
        return "category"
    if "Architecture-Group-Icons_" in rel and re.search(r"_32(?:_Dark)?\.svg$", name):
        return "group"
    return None


def _find_prefixed_parent(path: Path, prefixes: Iterable[str]) -> str | None:
    prefix_tuple = tuple(prefixes)
    for part in reversed(path.parts[:-1]):
        for prefix in prefix_tuple:
            if part.startswith(prefix):
                return part[len(prefix) :]
    return None


def _guess_group_category(filename: str) -> str:
    candidate = filename.lower()
    for keyword, slug in GROUP_KEYWORDS_TO_CATEGORY.items():
        if keyword in candidate:
            return slug
    return "general"


def _clean_stem(filename: str, kind: str) -> str:
    stem = filename[:-4] if filename.endswith(".svg") else filename
    if kind == "service":
        stem = re.sub(r"^Arch_", "", stem)
        stem = re.sub(r"_64$", "", stem)
    elif kind == "resource":
        stem = re.sub(r"^Res_", "", stem)
        stem = re.sub(r"_48(?:_(Light|Dark))?$", "", stem)
    elif kind == "category":
        stem = re.sub(r"^Arch-Category_", "", stem)
        stem = re.sub(r"_64$", "", stem)
    elif kind == "group":
        stem = re.sub(r"_32(?:_(Light|Dark))?$", "", stem)
    return stem


def _words_from_stem(stem: str, keep_vendor_prefix: bool) -> list[str]:
    text = stem.replace("_", " ").replace("-", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if not keep_vendor_prefix:
        text = re.sub(r"^(Amazon|AWS)\s+", "", text, flags=re.IGNORECASE)
    if not text:
        text = "Unknown"
    words = text.split(" ")
    out = []
    for word in words:
        key = word.lower()
        if key in ACRONYMS:
            out.append(ACRONYMS[key])
        elif key.isdigit():
            out.append(key)
        else:
            out.append(word.capitalize())
    full = " ".join(out)
    for source, replacement in PHRASE_REPLACEMENTS.items():
        full = full.replace(source, replacement)
    return full.split(" ")


def derive_fullname(path: Path, kind: str) -> str:
    keep_vendor_prefix = kind == "group"
    stem = _clean_stem(path.name, kind)
    return " ".join(_words_from_stem(stem, keep_vendor_prefix)).strip()


def derive_name_slug(fullname: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", fullname.lower()).strip("-")
    return slug or "icon"


def derive_description(fullname: str, icon_kind: str) -> str:
    if icon_kind == "service":
        return f"{fullname} service icon from the AWS Architecture Icons set."
    if icon_kind == "resource":
        return f"{fullname} resource icon from the AWS Architecture Icons set."
    if icon_kind == "category":
        return f"{fullname} category icon from the AWS Architecture Icons set."
    return f"{fullname} group icon from the AWS Architecture Icons set."


def derive_tags(fullname: str, kind: str, folder_category: str, existing_tags: list[str] | None) -> list[str]:
    tags = set()
    for token in re.findall(r"[a-z0-9]+", fullname.lower()):
        if len(token) > 1:
            tags.add(token)
    if kind == "service":
        tags.add(folder_category)
    if kind == "resource":
        tags.add("resource")
    if kind == "group":
        tags.add("group")
        tags.add("infrastructure")
    if kind == "category":
        tags.add("category")
    tags.add("aws")
    if existing_tags:
        for tag in existing_tags:
            if isinstance(tag, str) and tag.strip():
                tags.add(tag.strip().lower())
    return sorted(tags)


def detect_primary_color(svg_path: Path) -> str:
    try:
        content = svg_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return "#527FFF"

    colors = collections.Counter(c.upper() for c in HEX_COLOR_RE.findall(content))
    for ignored in ("FFFFFF", "000000"):
        colors.pop(ignored, None)
    if colors:
        return f"#{colors.most_common(1)[0][0]}"
    return "#527FFF"


def _load_existing_catalog(catalog_path: Path) -> dict[str, dict]:
    if not catalog_path.exists():
        return {}
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    by_path: dict[str, dict] = {}
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        path_value = entry.get("path")
        if not isinstance(path_value, str):
            continue
        by_path[path_value] = entry
    return by_path


def _target_path_for_icon(
    source_path: Path,
    kind: str,
) -> Path:
    filename = source_path.name
    if kind == "service":
        raw_category = _find_prefixed_parent(source_path, ("Arch_",))
        category = category_slug(raw_category or "general")
        return Path("icons") / "service" / category / filename

    if kind == "resource":
        raw_category = _find_prefixed_parent(source_path, ("Res_",))
        category = category_slug(raw_category or "general")
        return Path("icons") / "resource" / category / filename

    if kind == "category":
        category_name = _clean_stem(filename, "category")
        category = category_slug(category_name)
        return Path("icons") / "category" / category / filename

    guessed = _guess_group_category(filename)
    return Path("icons") / "group" / guessed / filename


def _icon_kind_from_target_path(path: Path) -> str:
    if len(path.parts) < 4:
        raise RuntimeError(f"Unexpected icon path format: {path.as_posix()}")
    return path.parts[1]


def _catalog_category_value(path: Path) -> str:
    kind = _icon_kind_from_target_path(path)
    if kind == "service":
        return path.parts[2]
    if kind == "resource":
        return "resource"
    if kind == "category":
        return "category"
    return "group"


def _catalog_kind_value(path: Path) -> str:
    return _icon_kind_from_target_path(path)


def sync_icons(repo_root: Path, asset_url: str | None, keep_descriptions: bool) -> None:
    icons_root = repo_root / "icons"
    catalog_path = repo_root / "icons.json"
    review_path = repo_root / "icons-missing-from-latest.json"
    existing_by_path = _load_existing_catalog(catalog_path)
    existing_by_basename: dict[str, Path] = {}
    for svg_path in icons_root.rglob("*.svg"):
        existing_by_basename.setdefault(svg_path.name, svg_path.relative_to(repo_root))

    if asset_url is None:
        asset_url = discover_latest_asset_zip(ICON_PAGE_URL)
    print(f"Resolved asset package URL: {asset_url}")

    with tempfile.TemporaryDirectory(prefix="aws-icons-sync-") as temp_dir:
        temp_path = Path(temp_dir)
        zip_path = temp_path / "aws-asset-package.zip"
        final_url = download(asset_url, zip_path)
        print(f"Downloaded package from: {final_url}")

        extract_path = temp_path / "extract"
        extract_path.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(extract_path)

        source_candidates: dict[Path, list[tuple[Path, str]]] = collections.defaultdict(list)
        for source in sorted(extract_path.rglob("*.svg")):
            kind = detect_icon_kind(source)
            if kind is None:
                continue
            relative_target = _target_path_for_icon(source, kind)
            # Prefer existing repo path for same basename so we update in place
            # and avoid duplicate copies under a new category folder.
            existing_rel = existing_by_basename.get(source.name)
            if existing_rel is not None:
                relative_target = existing_rel
            source_candidates[relative_target].append((source, kind))

        updated = 0
        added = 0
        collisions = 0
        package_basenames: set[str] = set()
        for relative_target in sorted(source_candidates):
            candidates = source_candidates[relative_target]
            source, kind = candidates[0]

            if len(candidates) > 1 and kind in {"service", "resource"}:
                target_category = relative_target.parts[2] if len(relative_target.parts) > 2 else "general"
                preferred = None
                for candidate_source, _ in candidates:
                    parent_prefix = "Arch_" if kind == "service" else "Res_"
                    raw_category = _find_prefixed_parent(candidate_source, (parent_prefix,))
                    if raw_category and category_slug(raw_category) == target_category:
                        preferred = candidate_source
                        break
                if preferred is not None:
                    source = preferred

            target = repo_root / relative_target
            target.parent.mkdir(parents=True, exist_ok=True)
            package_basenames.add(source.name)
            existed = target.exists()
            shutil.copy2(source, target)
            if existed:
                updated += 1
            else:
                added += 1
            if len(candidates) > 1:
                collisions += len(candidates) - 1
                if any(target.read_bytes() != s.read_bytes() for s, _ in candidates):
                    print(
                        "Resolved duplicate source icons for target path "
                        f"{relative_target.as_posix()}"
                    )
        if collisions:
            print(f"Resolved {collisions} duplicate source icon candidates")
        print(f"Updated {updated} existing icons; added {added} new icons")

        missing_paths = sorted(
            p.relative_to(repo_root).as_posix()
            for p in icons_root.rglob("*.svg")
            if p.name not in package_basenames
        )
        review_payload = {
            "generated_at": datetime.datetime.now(tz=datetime.timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "asset_package_url": final_url,
            "policy": (
                "Icons missing from the latest AWS package are kept in-repo for review "
                "and are never deleted by sync. This file is overwritten each sync."
            ),
            "count": len(missing_paths),
            "paths": missing_paths,
        }
        review_path.write_text(
            json.dumps(review_payload, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        print(
            f"Wrote review list with {len(missing_paths)} missing-from-latest icons to "
            f"{review_path.as_posix()}"
        )

    used_names: set[str] = set()
    entries = []
    for svg_path in sorted(icons_root.rglob("*.svg")):
        rel = svg_path.relative_to(repo_root)
        rel_posix = rel.as_posix()
        kind = _catalog_kind_value(rel)
        category_value = _catalog_category_value(rel)
        existing = existing_by_path.get(rel_posix, {})

        fullname = derive_fullname(svg_path, kind)
        slug = derive_name_slug(fullname)
        if slug in used_names:
            suffix = hashlib.sha1(rel_posix.encode("utf-8")).hexdigest()[:6]
            slug = f"{slug}-{suffix}"
        used_names.add(slug)

        description = existing.get("description")
        if not keep_descriptions or not isinstance(description, str) or not description.strip():
            description = derive_description(fullname, kind)

        tags = derive_tags(
            fullname=fullname,
            kind=kind,
            folder_category=rel.parts[2] if len(rel.parts) > 2 else "general",
            existing_tags=existing.get("tags") if isinstance(existing, dict) else None,
        )

        entries.append(
            {
                "path": rel_posix,
                "tags": tags,
                "category": category_value,
                "color": detect_primary_color(svg_path),
                "description": description,
                "fullname": fullname,
                "name": slug,
            }
        )

    catalog_path.write_text(json.dumps(entries, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"Wrote {len(entries)} entries to {catalog_path.as_posix()}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync AWS architecture icons and rebuild icons.json")
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Path to repository root (default: current directory)",
    )
    parser.add_argument(
        "--asset-url",
        default=None,
        help="Optional direct Asset-Package zip URL to use",
    )
    parser.add_argument(
        "--no-keep-descriptions",
        action="store_true",
        help="Regenerate descriptions instead of keeping existing ones when present",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    sync_icons(
        repo_root=repo_root,
        asset_url=args.asset_url,
        keep_descriptions=not args.no_keep_descriptions,
    )


if __name__ == "__main__":
    main()
