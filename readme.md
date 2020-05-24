# Display Controller

This repository contains a python script to configure the display arrangement of multiple displays on linux.
The script was initially written to connect two external displays with a docking station in a shared desk office.
Since it was annoying to identitfy which cable has to be connected to which docking station port, a simplified solution was required.

With the script, the display arrangement can be saved to a configuration file and be re-applied from it.
The order defined in the configuration file is restored by identifying displays by their hardware EDIDs. It doesn't matter to which ports displays are (re)connected to.

# Installation

Run the `install.sh` script.

# Usage

Usage: display-controller.py --setup
| --list | --internal | --clone | --extend [--all] [--right | --left] | --external [--all] [--right | --left] | --version | --help 

Utility to simplify external display management on linux notebooks.

Explanation of arguments:  
  --setup                                 Create a configuration file with the physical order of displays from left to right.  
  --list                                  Lists all connected displays.  
  --internal                              Use the internal display, disable external displays if available.  
  --clone                                 Clones the image to all connected displays.  
  --extend [--all] [--right | --left]     Use the internal display and (all) external display(s). Extend to the left or right.  
  --external [--all] [--right | --left]   Use external display(s). Extend to the left or right.  
  --help                                  Display the help.  
  --version                               Display the version of the tool.
