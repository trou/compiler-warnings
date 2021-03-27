#!/bin/bash

set -euo pipefail

DIR=$(dirname "$(readlink -f "$0")")

function parse_clang_info()
{
    local version=$1
    local target_dir=$2
    local input_dir=$3

    local json_file="${target_dir}/warnings-clang-${version}.json"

    llvm-tblgen -dump-json -I "${input_dir}" \
          "${input_dir}/Diagnostic.td" \
          | python3 -mjson.tool \
          > "${json_file}"
    "${DIR}/parse-clang-diagnostic-groups.py" "${json_file}" \
          > "${target_dir}/warnings-clang-${version}.txt"
    "${DIR}/parse-clang-diagnostic-groups.py" --unique "${json_file}" \
          > "${target_dir}/warnings-clang-unique-${version}.txt"
    "${DIR}/parse-clang-diagnostic-groups.py" --top-level "${json_file}" \
          > "${target_dir}/warnings-clang-top-level-${version}.txt"
    "${DIR}/parse-clang-diagnostic-groups.py" --top-level --text "${json_file}" \
          > "${target_dir}/warnings-clang-messages-${version}.txt"
}

GIT_DIR=$1

target_dir=${DIR}/../clang

# Parse all released versions
versions=(
    3.2
    3.3
    3.4
    3.5
    3.6
    3.7
    3.8
    3.9
    4
    5
    6
    7
    8
    9
    10
    11
    12
)

for v in "${versions[@]}"; do
    git -C "${GIT_DIR}" checkout "origin/release/${v}.x"
    parse_clang_info "${v}" "${target_dir}" "${GIT_DIR}/clang/include/clang/Basic"
done

# Parse NEXT (main)
versions=( "${versions[@]}" "NEXT" )

git -C "${GIT_DIR}" checkout origin/main
parse_clang_info NEXT "${target_dir}" "${GIT_DIR}/clang/include/clang/Basic"

# Generate diffs
seq 2 "${#versions[@]}" | while read -r version_idx; do
    current=${versions[$(( version_idx - 2 ))]}
    next=${versions[$(( version_idx - 1 ))]}
    "${DIR}/create-diff.sh" \
          "${target_dir}/warnings-clang-unique-${current}.txt" \
          "${target_dir}/warnings-clang-unique-${next}.txt" \
          > "${target_dir}/warnings-clang-diff-${current}-${next}.txt"
done
