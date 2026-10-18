#!/usr/bin/env python3
"""Select a stable version without modifying the repository or GitHub."""
import json
import os
import re
import subprocess


def parse_version(tag):
    match = re.fullmatch(r"v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", tag)
    return tuple(map(int, match.groups())) if match else None


def select_version(tags, releases, sha, requested=""):
    stable = {tag: parse_version(tag) for tag in tags if tag.startswith("v") and parse_version(tag)}
    published = {r["tag_name"] for r in releases if not r["draft"] and not r["prerelease"]}
    published_versions = [stable[t] for t in published if t in stable]
    latest = max(published_versions, default=(0, 0, 0))
    if requested:
        version = parse_version(requested)
        if not version or requested.startswith("v"):
            raise ValueError("Use a stable version without v, for example 1.5.0")
        tag = "v" + requested
    else:
        completed = [t for t in stable if tags[t] == sha and t in published]
        if completed:
            tag = max(completed, key=stable.get)
            return {"version": tag[1:], "tag": tag, "should_release": "false"}
        pending = [t for t in stable if tags[t] == sha and t not in published]
        if pending:
            tag = max(pending, key=stable.get)
            version = stable[tag]
        else:
            major, minor, patch = max(stable.values(), default=(0, 0, 0))
            version = (major, minor, patch + 1)
            tag = "v" + ".".join(map(str, version))
    if tag in tags and tags[tag] != sha:
        raise ValueError(f"{tag} belongs to another commit; tags are never overwritten")
    if tag in published:
        return {"version": tag[1:], "tag": tag, "should_release": "false"}
    if version <= latest:
        raise ValueError("Version must be newer than all published stable releases")
    return {"version": tag[1:], "tag": tag, "should_release": "true"}


def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()


def main():
    subprocess.run(["git", "fetch", "origin", "--tags"], check=True)
    sha = git("rev-parse", "HEAD")
    tags = {t: git("rev-list", "-n", "1", t) for t in git("tag", "--list", "v*").splitlines()}
    pages = json.loads(subprocess.check_output([
        "gh", "api", f"repos/{os.environ['GITHUB_REPOSITORY']}/releases?per_page=100",
        "--paginate", "--slurp",
    ], text=True))
    releases = [release for page in pages for release in page]
    result = select_version(tags, releases, sha, os.environ.get("INPUT_VERSION", ""))
    if result["should_release"] == "true":
        # An old workflow rerun must never make an older source tree the latest release.
        published = [r["tag_name"] for r in releases
                     if not r["draft"] and not r["prerelease"] and r["tag_name"] in tags
                     and parse_version(r["tag_name"])]
        if published:
            latest = max(published, key=parse_version)
            subprocess.run(["git", "merge-base", "--is-ancestor", tags[latest], sha], check=True)
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        for key, value in result.items():
            output.write(f"{key}={value}\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
