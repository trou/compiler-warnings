#!/usr/bin/env python3
"""Process a clang git repository for diagnostic groups."""
import json
import os
import subprocess  # noqa: S404
import sys
from typing import Optional

import git

DIR = os.path.dirname(os.path.realpath(__file__))


def create_diffs(target_dir: str, versions: list[str]) -> None:
    """
    Generate diffs for adjacent versions of the 'unique' warning lists.

    :param target_dir: Directory containing files to compare
    :param versions: List of versions to compare
    """
    for version_idx in range(0, len(versions) - 1):
        current_ver = versions[version_idx]
        next_ver = versions[version_idx + 1]
        shell(
            [
                f"{DIR}/create-diff.sh",
                f"{target_dir}/warnings-clang-unique-{current_ver}.txt",
                f"{target_dir}/warnings-clang-unique-{next_ver}.txt",
            ],
            f"{target_dir}/warnings-clang-diff-{current_ver}-{next_ver}.txt",
        )


def format_json(json_path: str) -> None:
    """Format the JSON file at json_path.

    :param json_path: The file to reformat.
    """
    obj = json.load(open(json_path))

    with open(json_path, "w") as json_file:
        json.dump(obj, json_file, indent=4)
        json_file.write("\n")  # Add trailing newline that json.dump does not


def parse_clang_info(version: str, target_dir: str, input_dir: str) -> None:
    """
    Parse clang diagnostic groups for the given version (in input_dir) to target_dir.

    :param version: Version number to use in output filenames
    :param target_dir: Directory to write outputs
    :param input_dir: Directory containing Diagnostic.td file
    """
    json_file = f"{target_dir}/warnings-clang-{version}.json"

    shell(
        ["llvm-tblgen", "-dump-json", "-I", input_dir, f"{input_dir}/Diagnostic.td"],
        json_file,
    )
    format_json(json_file)

    shell(
        [f"{DIR}/parse-clang-diagnostic-groups.py", json_file],
        f"{target_dir}/warnings-clang-{version}.txt",
    )
    shell(
        [f"{DIR}/parse-clang-diagnostic-groups.py", "--unique", json_file],
        f"{target_dir}/warnings-clang-unique-{version}.txt",
    )
    shell(
        [f"{DIR}/parse-clang-diagnostic-groups.py", "--top-level", json_file],
        f"{target_dir}/warnings-clang-top-level-{version}.txt",
    )
    shell(
        [f"{DIR}/parse-clang-diagnostic-groups.py", "--top-level", "--text", json_file],
        f"{target_dir}/warnings-clang-messages-{version}.txt",
    )


def shell(cmd: list[str], stdout_path: Optional[str] = None) -> None:
    """
    Run cmd in a subprocess.

    :param cmd: The command to run.
    :param stdout_path: Optional path to write stdout.
    """
    result = subprocess.run(cmd, capture_output=True, check=True)  # noqa: S603

    if stdout_path:
        with open(stdout_path, "wb") as stdout_file:
            stdout_file.write(result.stdout)


def main() -> None:
    """Entry point."""
    GIT_DIR = sys.argv[1]
    repo = git.Repo(GIT_DIR)

    target_dir = f"{DIR}/../clang"

    # Parse all released versions
    versions = [
        "3.2",
        "3.3",
        "3.4",
        "3.5",
        "3.6",
        "3.7",
        "3.8",
        "3.9",
        "4",
        "5",
        "6",
        "7",
        "8",
        "9",
        "10",
        "11",
        "12",
    ]

    for version in versions:
        print(f"Processing {version=}")
        repo.git.checkout(f"origin/release/{version}.x")
        parse_clang_info(version, target_dir, f"{GIT_DIR}/clang/include/clang/Basic")

    # Parse NEXT (main)
    versions.append("NEXT")

    print("Processing main")
    repo.git.checkout("origin/main")
    parse_clang_info("NEXT", target_dir, f"{GIT_DIR}/clang/include/clang/Basic")

    # Generate diffs
    create_diffs(target_dir, versions)


if __name__ == "__main__":
    main()
