#!/usr/bin/env python3
"""
Parser for clang diagnostic groups.

Parses an extract of clang's Diagnostic.td as formatted by the command
`llvm-tblgen -dump-json`, and identifies relevant information about the
compiler warning options.
"""

import argparse
from functools import total_ordering
from itertools import chain
import json
from typing import Any, Dict, List

import common


class ClangDiagnostic:
    """One clang warning message (Diagnostic)."""

    def __init__(self, obj: Dict[str, Any]) -> None:
        """Construct from a Diagnostic instance (JSON object)."""
        self.name = obj["!name"]
        self.text = obj["Text"]
        if obj["Group"] is not None:
            self.group_name = obj["Group"]["def"]
        else:
            self.group_name = None
        if "DefaultSeverity" in obj:
            # clang 3.5+
            self.enabled_by_default = obj["DefaultSeverity"]["def"] != "SEV_Ignored"
        else:
            # clang 3.4 (and earlier)
            self.enabled_by_default = obj["DefaultMapping"]["def"] != "MAP_IGNORE"


class ClangDiagGroup:
    """One clang diagnostic group (DiagGroup record)."""

    def __init__(self, obj: Dict[str, Any], parent: "ClangDiagnostics") -> None:
        """Construct from a DiagGroup instance (JSON object)."""
        self.name = obj["!name"]
        self.switch_name = obj["GroupName"]
        self.child_names = [s["def"] for s in obj["SubGroups"]]

        self.has_parent = False
        self.diagnostics: List[ClangDiagnostic] = []
        self.children: List[ClangDiagGroup] = []
        self.switch: ClangWarningSwitch = parent.get_switch(self.switch_name)

    def get_messages(self, enabled_by_default: bool) -> List[str]:
        """
        Return a list of diagnostic messages in the group.

        If enabled_by_default is True, only the mesages enabled by default are
        returned.
        """
        if enabled_by_default:
            return [diag.text for diag in self.diagnostics if diag.enabled_by_default]

        return [diag.text for diag in self.diagnostics]

    def is_dummy(self) -> bool:
        """
        Return whether a group does nothing.

        A dummy group has no warnings, directly or indirectly.
        """
        if self.diagnostics:
            return False

        for child in self.children:
            if not child.is_dummy():
                return False

        return True

    def has_disabled_diagnostic(self) -> bool:
        """Return whether a group has a disabled diagnostic."""
        for diagnostic in self.diagnostics:
            if not diagnostic.enabled_by_default:
                return True

        for child in self.children:
            if child.has_disabled_diagnostic():
                return True

        return False

    def has_enabled_diagnostic(self) -> bool:
        """Return whether a group has an enabled diagnostic."""
        for diagnostic in self.diagnostics:
            if diagnostic.enabled_by_default:
                return True

        for child in self.children:
            if child.has_enabled_diagnostic():
                return True

        return False


@total_ordering
class ClangWarningSwitch:
    """One clang warning switch (-Wxxxx option)."""

    def __init__(self, name: str):
        """Construct from a name."""
        self.name = name
        self.groups: List[ClangDiagGroup] = []

    def __eq__(self, other: object) -> bool:
        """Return True if self and other have the same name."""
        if not isinstance(other, ClangWarningSwitch):
            return NotImplemented

        return self.name.lower() == other.name.lower()

    def __lt__(self, other: object) -> bool:
        """Return True if self should be before other in a sorted list."""
        if not isinstance(other, ClangWarningSwitch):
            return NotImplemented

        return self.name.lower() < other.name.lower()

    def __hash__(self) -> int:
        """Return a hash of the switch name."""
        return hash(self.name.lower())

    def get_child_switches(
        self, enabled_by_default: bool
    ) -> List["ClangWarningSwitch"]:
        """
        Return a list of child ClangWarningSwitch for the switch.

        If enabled_by_default is True, include only the switches that are
        partially or completely enabled by default.
        """
        child_groups: List[ClangDiagGroup] = []
        for group in self.groups:
            child_groups += group.children

        child_switches = [group.switch for group in child_groups]
        if enabled_by_default:
            child_switches = [
                switch
                for switch in child_switches
                if switch.is_enabled_by_default()
                or switch.partially_enabled_by_default()
            ]

        return child_switches

    def get_messages(self, enabled_by_default: bool) -> List[str]:
        """Return a list of diagnostic messages controlled by the switch."""
        messages = []
        for group in self.groups:
            messages += group.get_messages(enabled_by_default)

        return list(set(messages))  # Remove duplicates

    def is_dummy(self) -> bool:
        """
        Return whether a switch does nothing.

        A switch is a dummy (does nothing) if all groups are dummy.
        """
        for group in self.groups:
            if not group.is_dummy():
                return False

        return True

    def is_enabled_by_default(self) -> bool:
        """
        Return whether a switch is enabled by default.

        A switch is enabled by default if no diagnostic (in any group)
        is disabled by default and the switch is not a dummy.
        """
        for group in self.groups:
            if group.has_disabled_diagnostic():
                return False

        return not self.is_dummy()

    def partially_enabled_by_default(self) -> bool:
        """
        Return whether a switch is partially enabled by default.

        A switch is partially enabled by default if it has both enabled and
        disabled diagnostics.
        """
        has_enabled = False
        has_disabled = False
        for group in self.groups:
            if group.has_disabled_diagnostic():
                has_disabled = True
            if group.has_enabled_diagnostic():
                has_enabled = True

        return has_enabled and has_disabled

    def is_top_level(self) -> bool:
        """
        Return whether a switch is top-level.

        A switch is top-level if none of its group(s) have a parent.
        """
        for group in self.groups:
            if group.has_parent:
                return False

        return True


class ClangDiagnostics:
    """
    Data model for clang diagnostics.

    In the clang model, a switch controls one or more diagnostic groups. Each
    group is associated with one switch name, has zero or more warnings, and
    has zero or more subgroups.
    """

    def __init__(self, filename: str):
        """Construct from a JSON file."""
        self.groups = {}  # Dict: group name -> ClangDiagGroup
        self.switches: Dict[str, ClangWarningSwitch] = {}

        json_data = json.loads(open(filename).read())

        # Instantiate all group and switch objects
        for group_name in json_data["!instanceof"]["DiagGroup"]:
            group = ClangDiagGroup(json_data[group_name], self)

            self.groups[group_name] = group
            self.switches[group.switch_name].groups.append(group)

        # Resolve parent-child relationships in groups
        for group in self.groups.values():
            group.children = [self.groups[name] for name in group.child_names]
            for child_group in group.children:
                child_group.has_parent = True

        # Instantiate all diagnostics and link to groups
        for diag_name in json_data["!instanceof"]["Diagnostic"]:
            diag = ClangDiagnostic(json_data[diag_name])

            if diag.group_name is not None and diag.group_name in self.groups:
                self.groups[diag.group_name].diagnostics.append(diag)

    def get_switch(self, switch_name: str) -> ClangWarningSwitch:
        """Return the ClangWarningSwitch with the given name."""
        try:
            return self.switches[switch_name]
        except KeyError:
            self.switches[switch_name] = ClangWarningSwitch(switch_name)
            return self.switches[switch_name]


def create_comment_text(
    switch: ClangWarningSwitch, args: argparse.Namespace, enabled_by_default: bool
) -> str:
    """Return a comment appropriate for the switch and output type."""
    if switch.is_dummy():
        return " # DUMMY switch"
    elif args.unique:
        if switch.is_enabled_by_default():
            return " # Enabled by default."
        if switch.partially_enabled_by_default():
            return " # Partially enabled by default."
    elif enabled_by_default and switch.partially_enabled_by_default():
        return " (partial)"

    return ""


def print_references(
    switch: ClangWarningSwitch,
    level: int,
    args: argparse.Namespace,
    enabled_by_default: bool,
) -> None:
    """Print all children of switch, indented."""
    for child_switch in sorted(switch.get_child_switches(enabled_by_default)):
        print_switch(child_switch, level, args, enabled_by_default)


def print_switch(
    switch: ClangWarningSwitch,
    level: int,
    args: argparse.Namespace,
    enabled_by_default: bool,
) -> None:
    """Print the given switch (and its children), indented."""
    comment_string = create_comment_text(switch, args, enabled_by_default)
    print("# {}-W{}{}".format("  " * level, switch.name, comment_string))
    if args.text:
        for item in sorted(switch.get_messages(enabled_by_default)):
            print("#       {}{}".format("  " * level, item))

    print_references(switch, level + 1, args, enabled_by_default)


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Clang diagnostics group parser")
    common.add_common_parser_options(parser)
    parser.add_argument(
        "--text", action="store_true", help="Show text of each diagnostic message.",
    )
    parser.add_argument(
        "json_path",
        metavar="json-path",
        help="The path to the JSON output from llvm-tblgen.",
    )
    args = parser.parse_args()

    diagnostics = ClangDiagnostics(args.json_path)

    # Print enabled-by-default switches in top-level output
    if args.top_level:
        # Find all switches that are enabled by default and are not children
        # of another switch that is enabled by default.
        all_defaults = {
            s
            for s in diagnostics.switches.values()
            if s.is_enabled_by_default() or s.partially_enabled_by_default()
        }
        children = set(
            chain.from_iterable([s.get_child_switches(True) for s in all_defaults])
        )
        toplevel_defaults = all_defaults - children

        print("# enabled by default:")
        for switch in sorted(toplevel_defaults):
            print_switch(switch, 1, args, enabled_by_default=True)

    for switch in sorted(diagnostics.switches.values()):
        if args.top_level and (
            not switch.is_top_level() or switch.is_enabled_by_default()
        ):
            continue
        comment_string = create_comment_text(switch, args, enabled_by_default=False)
        print("-W{}{}".format(switch.name, comment_string))
        if args.text:
            for item in sorted(switch.get_messages(enabled_by_default=False)):
                print("#     {}".format(item))
        if args.unique:
            continue
        print_references(switch, 1, args, enabled_by_default=False)


if __name__ == "__main__":
    main()
