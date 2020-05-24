#!/usr/bin/env python3

"""
Usage: display-controller.py \
--setup
| --list \
| --internal \
| --clone \
| --extend [--all] [--right | --left] \
| --external [--all] [--right | --left] \
| --version \
| --help \


Utility to simplify external display management on linux notebooks.

Explanation of arguments:
  --setup                                 Create a configuration file with the physical order of displays from left to right
  --list                                  Lists all connected displays.
  --internal                              Use the internal display, disable external displays if available.
  --clone                                 Clones the image to all connected displays.
  --extend [--all] [--right | --left]     Use the internal display and (all) external display(s).
                                          Extend to the left or right.
  --external [--all] [--right | --left]   Use external display(s). Extend to the left or right.
  --help                                  Display the help
  --version                               Display the version of the tool

"""

from enum import Enum
from subprocess import Popen, PIPE, check_output
from sys import argv, exit
from textwrap import TextWrapper
from typing import List, Optional, Dict
from lark import Lark, Tree
from docopt import docopt
from os import path

import json
import logging

logging.basicConfig(level=logging.DEBUG)


class DisplayMode(Enum):
    CLONE = 0,
    INTERNAL_ONLY = 1,
    INTERNAL_EXTEND = 2,
    EXTERNAL_ONLY = 3


class Offset:
    def __init__(self, direction: str, offset: str) -> None:
        self.direction = direction
        self.offset = offset

    @classmethod
    def from_json(cls, json_data: dict):
        return cls(**json_data)


class Display:
    def __init__(self, name: str, resolution: str, x_offset: Offset, y_offset: Offset, edid: str = None) -> None:
        self.name = name
        self.resolution = resolution
        self.x_offset = x_offset
        self.y_offset = y_offset
        if edid == None:
            self.edid = ''
        else:
            self.edid = edid

    @classmethod
    def from_json(cls, json_data: dict):
        x_offset = Offset.from_json(json_data["x_offset"])
        y_offset = Offset.from_json(json_data["y_offset"])
        name = json_data["name"]
        resolution = json_data["resolution"]
        edid = json_data["edid"]

        return cls(name, resolution, x_offset, y_offset, edid)


class DisplayList:
    def __init__(self, displays: List[Display]) -> None:
        self.displays = displays

    @classmethod
    def from_json(cls, json_data: dict):
        displays = list(map(Display.from_json, json_data["displays"]))
        return cls(displays)


class JsonUtils:
    @staticmethod
    def to_json(displays: DisplayList) -> None:
        file_name = path.expanduser('~') + '/.config/display-switcher.conf'
        with open(file_name, 'w') as file:
            json.dump(displays.__dict__, file, default=lambda o: o.__dict__, indent=2)

    @staticmethod
    def from_json() -> Optional[DisplayList]:
        file_name = path.expanduser('~') + '/.config/display-switcher.conf'
        if not path.isfile(file_name):
            return None
        with open(file_name, 'r') as json_file:
            return DisplayList.from_json(json.load(json_file))


class DisplayParser:

    def parse(self) -> DisplayList:
        grammar = \
            """
                start: output "connected" "primary"? resolution_offset? orientation screen_size?

                output: TEXT

                resolution_offset: pixels "x" pixels screen_offset
                pixels: NUMBER
                screen_offset: offset offset
                offset: OFFSET_DIRECTION offset_value
                offset_value: NUMBER

                orientation: "(" ("normal"|"left"|"inverted"|"right"|"x"|"axis"|"y")+ ")"
                screen_size: length "x" length
                length: NUMBER "mm"
                
                OFFSET_DIRECTION: ("+"|"-")
                TEXT: /[-a-zA-Z0-9]+/

                %import common.LETTER
                %import common.INT -> NUMBER
                %import common.WS
                %import common.NEWLINE -> NL
                %ignore WS
            """
        parser = Lark(grammar, parser='lalr', debug=True)

        #Run xrandr
        output, _ = ProcessUtils.run("xrandr --props")
        lines = output.split("\n")

        parsed_displays = []
        edid_buffer = []
        collect_lines = False
        attribute_indentation = 0
        last_connected = False
        for line in lines:
            if "disconnected" in line:
                last_connected = False
                continue
            elif "connected" in line:
                # Print the parse tree to debug changes
                # print(parser.parse(output).pretty())

                # Get sub-tree with list of displays from parse tree
                display = parser.parse(line)
                parsed_display = self.parse_display(display)
                parsed_displays.append(parsed_display)

                # Mark the last parsed display as connected display to parse EDID
                last_connected = True
            
            elif last_connected and "EDID" in line:
                # Start collection of subsequent lines with EDID parts if the EDID belongs to a connected display
                edid_buffer = []
                attribute_indentation = line.index("EDID")
                collect_lines = True
            elif collect_lines:
                # Check if end of EDID is found by checking the attribute indentation
                indentation = 0
                if line.startswith(' '):
                    indentation = attribute_indentation
                else:
                    for c in line:
                        if c == "\t":
                            indentation+=1
                        else:
                            break

                if attribute_indentation == indentation:
                    collect_lines = False
                    #Add edid to the display
                    parsed_displays[len(parsed_displays) - 1].edid = ''.join(edid_buffer)
                    continue
                
                # Otherwise collect the EDID parts
                edid_buffer.append(line.strip())

        return DisplayList(parsed_displays)

    @classmethod
    def __filter_tree(cls, elements: List[Tree], element: str) -> List[Tree]:
        return list(filter(lambda entry: isinstance(entry, Tree) and entry.data == element, elements))

    @classmethod
    def __filter_tree_single(cls, elements: List[Tree], element: str) -> Optional[Tree]:
        return cls.__first(cls.__filter_tree(elements, element))

    @classmethod
    def __first(cls, elements: List[Tree]) -> Optional[Tree]:
        return next(iter(elements), None)

    @classmethod
    def parse_display(cls, display: Tree) -> Optional[Display]:
        # Extract parameters of the display
        display_name = cls.__filter_tree_single(display.children, "output").children[0].value
        resolution_offset = cls.__filter_tree_single(display.children, "resolution_offset")
        if resolution_offset:
            pixels = cls.__filter_tree(resolution_offset.children, "pixels")
            resolution = pixels[0].children[0] + "x" + pixels[1].children[0]

            offset = cls.__filter_tree_single(resolution_offset.children, "screen_offset").children
            x_offset = cls.parse_offset(offset[0])
            y_offset = cls.parse_offset(offset[1])
        else:
            resolution = None
            x_offset = None
            y_offset = None

        # Return displays with parameters
        return Display(display_name, resolution, x_offset, y_offset)

    @classmethod
    def parse_offset(cls, direction_offset: Tree) -> Offset:
        direction = direction_offset.children[0].value
        offset = direction_offset.children[1].children[0].value
        return Offset(direction, offset)


class DisplayController:
    @staticmethod
    def list() -> None:
        displays = DisplayParser().parse().displays
        for display in displays:
            print("{} ({}), x: {}{}, y: {}{}, edid: {}...".format(display.name,
                                                                  display.resolution,
                                                                  display.x_offset.direction if display.x_offset is not None else "-",
                                                                  display.x_offset.offset if display.x_offset is not None else "-",
                                                                  display.y_offset.direction if display.y_offset is not None else "-",
                                                                  display.y_offset.offset if display.y_offset is not None else "-",
                                                                  display.edid[:32] if display.edid is not None else "(No EDID)"))

    @staticmethod
    def configure(displays: List[Display],
                  display_mode: DisplayMode,
                  extend_all: bool = False,
                  direction: str = "right") -> None:
        """
        Configures the displays according to provided parameters.

        :param displays: list of displays
        :param display_mode: mode how to configure the displays
        :param extend_all: (default: False): extend only with single external display or all available
        :param direction: (values: "left", "right"): the direction to extend
        """

        command = "xrandr"

        for idx, display in enumerate(displays):
            command += " --output {}".format(display.name)
            if display_mode == DisplayMode.CLONE:
                if idx == 0:
                    command += " --primary --auto"
                else:
                    command += " --auto --same-as {}".format(displays[idx - 1].name)
            if display_mode == DisplayMode.INTERNAL_ONLY:
                if idx == 0:
                    command += " --primary --auto"
                else:
                    command += " --off"
            elif display_mode == DisplayMode.EXTERNAL_ONLY:
                if idx == 0:
                    command += " --off"
                if idx == 1:
                    command += " --primary --auto"
                elif extend_all:
                    command += " --auto --{}-of {}".format(direction, displays[idx - 1].name)
                else:
                    command += " --off"
            elif display_mode == DisplayMode.INTERNAL_EXTEND:
                if idx == 0:
                    command += " --primary --auto"
                elif idx == 1:
                    command += " --auto --{}-of {}".format(direction, displays[idx - 1].name)
                elif extend_all:
                    command += " --auto --{}-of {}".format(direction, displays[idx - 1].name)
                else:
                    command += " --off"

        print("command: {}".format(command))
        output, error = ProcessUtils.run(command)
        ProcessUtils.print(output, error)


class ProcessUtils:
    @staticmethod
    def run(command: str) -> (str, str):
        """
        Runs a command in a sub process.

        :param command: the command to execute
        :return: (str,str): stdout and stderr as tuple
        """

        p = Popen(args=command,
                  shell=True,
                  stdout=PIPE,
                  stderr=PIPE)
        out, err = p.communicate()
        output = out.decode("utf-8").strip(" \t\n\r")
        error = err.decode("utf-8").strip(" \t\n\r")
        return output, error

    @staticmethod
    def print(output: str, error: str) -> None:
        """
        Prints output and error string if set.

        :param output: optional output string
        :param error: optional error string
        """

        wrapper = TextWrapper(initial_indent="  ", subsequent_indent="  ", width=300)
        if output != "":
            print(wrapper.fill(output))
        if error != "":
            print(wrapper.fill(error))


def rotate(l, n):
    return l[-n:] + l[:-n]


def get_edids(displays: List[Display]) -> List[str]:
    return [display["edid"] if isinstance(display, Dict) else display.edid for display in displays]


def main():
    args = docopt(__doc__, argv=None, help=True, version="1.0.0", options_first=False)

    current_displays = DisplayParser().parse()

    if args["--setup"]:
        display_list = current_displays.displays
        is_correct = False
        while True:
            DisplayController.configure(display_list, DisplayMode.INTERNAL_EXTEND, True, "right")
            while True:
                correct_order = input("Is this order correct (y/n)? ")
                if 'y' == correct_order:
                    is_correct = True
                    break
                elif 'n' == correct_order:
                    break

            if is_correct:
                current_displays.displays = display_list
                JsonUtils.to_json(current_displays)
                break
            else:
                display_list = rotate(display_list, 1)

        print("Correct order is:")
        [print(display.name) for display in display_list]
    elif args["--list"]:
        DisplayController.list()
    else:
        use_current = True
        configuration_list = JsonUtils.from_json()

        if configuration_list is not None:
            config_edids = get_edids(configuration_list.displays)
            current_edids = get_edids(current_displays.displays)
            if set(current_edids).issubset(config_edids):
                use_current = False

        if use_current:
            displays = current_displays.displays
        else:
            displays = configuration_list.displays
            for display in displays:
                display.name = next(iter([d.name for d in current_displays.displays if d.edid == display.edid]), display.name)

        if args["--internal"]:
            DisplayController.configure(displays, DisplayMode.INTERNAL_ONLY)
        elif args["--clone"]:
            DisplayController.configure(displays, DisplayMode.CLONE)
        elif args["--extend"]:
            extend_direction = "left" if args["--left"] else "right"
            DisplayController.configure(displays, DisplayMode.INTERNAL_EXTEND, args["--all"], extend_direction)
        elif args["--external"]:
            extend_direction = "left" if args["--left"] else "right"
            DisplayController.configure(displays, DisplayMode.EXTERNAL_ONLY, args["--all"], extend_direction)
        else:
            print("Operation not implemented")


if __name__ == '__main__':
    if len(argv) == 1:
        argv.append('-h')
        exit(main())
    main()
