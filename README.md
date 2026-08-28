# Harmony-Healing
Status: Beta - After a few sessions in Claude and Grok, the project is back on track!

### Description
A frequency generation program for Windows 10-11, currently covering...
- The 11th harmonic, theoretically capable of causing sonic-obliteration of cancers/fungus.
- Some useful/important frequencies for healing/meditation/Sleep.

### Preview
- The main window (v0.08)...
![image_missing](https://github.com/wiseman-timelord/Harmony-Healing/blob/main/media/main_interface.jpg)

### Requirements
- Windows 10-11 (tested on Windows 10)
- Python 3.10-3.13 (tested on Python 3.12)

### Instructions
Here are the instructions...
```
1. Download the latest release, and extract to a suitable folder.
2. Run the batch with right-click run-as-admin.
3. On the batch menu, choose to install the program with clean install. After completing install, check that it installed correctly from the summary, if not then try again, ensuring there are not other apps hogging the internet.
4. Back on the batch menu, try 1 or 2 to load the main program (hopefully 1 works currently but if not try 2).
5. Determine correct page and programming, and click start to begin, it will begin to produce noise on default windows sound device. You can always stop the noise by 
- If reinstalling, delete the `.\.venv` folder first (i can fix this later).
```

### Structure
```
.\Harmony-Healing\
├── Harmony-Healing.bat  (batch menu to launch, installer and launcher)
├── launcher.py  (main function/loop, startup/initialization, shutdown sequence)
├── installer.py (the installer for the requirements)
├── scripts\
│   ├── __init__.py  (blank file)
│   ├── displays.py  (displays and interfaces)
│   ├── configure.py  (global variables/maps/lists/arrays)
│   ├── generator.py  (sound generation/code)
│   └── utilities.py  (general functions and functions that dont belong in other logically named scripts)
└── data\
    └── virus.json  (persistent settings for relating page).
    └── fungal.json  (persistent settings for relating page).
    └── healing.json  (persistent settings for relating page).
```

### Disclaimer
- This program has set timers, thereabouts its experimental, but the science is not to be under-estimated, so start off with, smaller or calculated, program timers and volume levels.
- The user is intended to understand the science beforehand, and be willing to accept the full blame of any negative results.
- Any failure for the user's hardware to produce the correct frequencies resulting in unexpected frequencies, would likewise be the blame upon, the user and the owner of the hardware.
