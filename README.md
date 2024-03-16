# Sysman
System manager for Arch-based Linux distributions. Manage updates, packages, services etc. in the system by declaring them in a config file.

## Disclaimer
**Before using this software, you are encouraged to review its source to make sure it will work correctly with your setup. Use it at your own risk. I am not responsible for damage this program causes on your system.**

## Features
Sysman functionality is implemented by modules. Currently existing modules include:
- package - handles maintaining software packages in the system,
- service - handles maintaining systemd system- and user-level services in the system, both provided by software packages as well as user defined,
- update - performs system update according to the pipeline defined in config file, also implements rollback functionality to the state before last update.

## How to use
Run ```sysman``` script. To view info about present modules, run ```sysman help```. To view info about a specific module, run ```sysman <MODULE> help```.

## Installation
Download this repository and extract it, make ```sysman``` executable.
