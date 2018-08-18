#!/usr/bin/env python3
'''
Parser for clang diagnostic groups

Parses an extract of clang's Diagnostic.td as formatted by the command
`llvm-tblgen -dump-json`, and identifies relevant information about the
compiler warning options.
'''
from __future__ import print_function

import argparse
import json
import sys
from functools import total_ordering
import common

class ClangDiagnostic:
    '''
    One clang warning message (Diagnostic)
    '''
    def __init__(self, obj):
        '''
        Construct from a Diagnostic instance (JSON object)
        '''
        self.name = obj['!name']
        if obj['Group'] is not None:
            self.group_name = obj['Group']['def']
        else:
            self.group_name = None


class ClangDiagGroup:
    '''
    clang diagnostic group (DiagGroup record)
    '''
    def __init__(self, obj):
        '''
        Construct from a DiagGroup instance (JSON object)
        '''
        self.name = obj['!name']
        self.switch_name = obj['GroupName']
        self.child_names = [s['def'] for s in obj['SubGroups']]

        self.has_parent = False
        self.diagnostics = []   # List of ClangDiagnostic
        self.children = []      # List of ClangDiagGroup
        self.switch = None      # ClangWarningSwitch

    def is_dummy(self):
        '''
        Determines if a group does nothing

        A dummy group has no warnings, directly or indirectly.
        '''

        if self.diagnostics:
            return False

        for child in self.children:
            if not child.is_dummy():
                return False

        return True

@total_ordering
class ClangWarningSwitch:
    '''
    clang warning switch (-Wxxxx option)
    '''
    def __init__(self, name: str):
        '''
        Construct from a name
        '''
        self.name = name
        self.groups = []        # List of ClangDiagGroup

    def __eq__(self, other):
        '''Returns True if self and other have the same name'''
        return self.name.lower() == other.name.lower()

    def __lt__(self, other):
        '''Returns True if self should be before other in a sorted list'''
        return self.name.lower() < other.name.lower()

    def get_child_switches(self) -> list:
        '''Returns a list of child ClangWarningSwitch for the switch'''
        child_groups = []
        for group in self.groups:
            child_groups += group.children

        return [group.switch for group in child_groups]

    def is_dummy(self) -> bool:
        '''
        Determines if a switch does nothing

        A switch is a dummy if all groups are dummy, and therefore
        should do nothing.
        '''

        for group in self.groups:
            if not group.is_dummy():
                return False

        return True


    def is_top_level(self) -> bool:
        '''
        Determines whether a switch is top-level

        A top-level switch is not controlled by any of its parents
        '''
        for group in self.groups:
            if group.has_parent:
                return False

        return True


class ClangDiagnostics:
    '''
    Data model for clang diagnostics

    In the clang model, a switch controls one or more diagnostic groups. Each
    group is associated with one switch name, has zero or more warnings, and
    has zero or more subgroups.
    '''
    def __init__(self, json_file: str):
        self.groups = {}                # Dict: group name -> ClangDiagGroup
        self.switches = {}              # Dict: switch name -> ClangWarningSwitch

        json_data = json.loads(open(json_file).read())

        # Instantiate all group and switch objects
        for group_name in json_data['!instanceof']['DiagGroup']:
            group = ClangDiagGroup(json_data[group_name])

            self.groups[group_name] = group

            switch_name = group.switch_name
            if switch_name not in self.switches:
                self.switches[switch_name] = ClangWarningSwitch(switch_name)
            self.switches[switch_name].groups.append(group)
            group.switch = self.switches[switch_name]

        # Resolve parent-child relationships in groups
        for group_name, group in self.groups.items():
            group.children = [self.groups[name] for name in group.child_names]
            for child_group in group.children:
                child_group.has_parent = True

        # Instantiate all diagnostics and link to groups
        for diag_name in json_data['!instanceof']['Diagnostic']:
            diag = ClangDiagnostic(json_data[diag_name])

            if diag.group_name is not None and diag.group_name in self.groups:
                self.groups[diag.group_name].diagnostics.append(diag_name)


def create_dummy_text(switch: ClangWarningSwitch) -> str:
    '''Returns a comment appropriate for the switch, if it is a dummy'''
    if switch.is_dummy():
        return " # DUMMY switch"
    return ""


def print_references(switch: ClangWarningSwitch, level: int):
    '''
    Print all children of switch, indented
    '''
    for child_switch in sorted(switch.get_child_switches()):
        dummy_string = create_dummy_text(child_switch)
        print("# %s-W%s%s" % (
            "  " * level, child_switch.name, dummy_string))
        print_references(child_switch, level + 1)


def main(argv):
    '''Entry point'''
    parser = argparse.ArgumentParser(
        description="Clang diagnostics group parser")
    common.add_common_parser_options(parser)
    parser.add_argument("json_path", metavar="json-path", help="""\
The path to the JSON output from llvm-tblgen.
""")
    args = parser.parse_args(argv[1:])

    diagnostics = ClangDiagnostics(args.json_path)

    for switch in sorted(diagnostics.switches.values()):
        if args.top_level and not switch.is_top_level():
            continue
        dummy_string = create_dummy_text(switch)
        print("-W%s%s" % (switch.name, dummy_string))
        if args.unique:
            continue
        print_references(switch, 1)


if __name__ == "__main__":
    main(sys.argv)
