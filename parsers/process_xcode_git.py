#!/usr/bin/env python3
"""Process an Apple LLVM (Xcode) git repository for diagnostic groups."""
import os
import sys

import git
from process_clang_git import create_diffs, create_readme, parse_clang_info

DIR = os.path.dirname(os.path.realpath(__file__))

README_TEMPLATE = """
# Apple clang (Xcode) warning flags

Apple's fork of clang (as shipped with Xcode) is _based on_ the LLVM project but
is not a 100% match; some warnings are added, others are removed, and the
versioning scheme is different. The official Xcode releases are built from an
Apple-internal repository, so the exact list of compiler warning flags is not
truly knowable without experimentation.

That said, [Apple's public fork of LLVM](https://github.com/apple/llvm-project)
has `apple/stable/*` branches which are a close approximation of the Xcode
sources especially with regard to available compiler warnings. For example, the
delta between `apple/stable/20200108` and Xcode 12.2 is about ten flags.

Warnings available in each `apple/stable` branch are as follows:

{% for prev, current in versions %}
* {{current}} [all](warnings-{{current}}.txt)
  • [top level](warnings-top-level-{{current}}.txt)
  • [messages](warnings-messages-{{current}}.txt)
  • [unique](warnings-unique-{{current}}.txt)
{%- if prev %}
  • [diff](warnings-diff-{{prev}}-{{current}}.txt)
{%- endif %}
{%- endfor %}
"""


def main() -> None:
    """Entry point."""
    GIT_DIR = sys.argv[1]
    repo = git.Repo(GIT_DIR)

    target_dir = f"{DIR}/../xcode"

    # Parse all apple/stable branches as well as apple/main
    branches = sorted(
        ref.name for ref in repo.refs if ref.name.startswith("origin/apple/stable/")
    )
    versions = [(branch.split("/")[-1], branch) for branch in branches]
    versions += [("NEXT", "origin/apple/main")]

    os.makedirs(target_dir, exist_ok=True)

    for version, ref in versions:
        print(f"Processing {version=}")
        repo.git.checkout(ref)
        parse_clang_info(version, target_dir, f"{GIT_DIR}/clang/include/clang/Basic")

    # Generate diffs
    version_numbers = [version for version, _ in versions]
    create_diffs(target_dir, [version for version, _ in versions])

    # Generate index (README.md) except for NEXT
    create_readme(target_dir, version_numbers[:-1], README_TEMPLATE)


if __name__ == "__main__":
    main()
