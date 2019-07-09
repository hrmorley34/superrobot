#!/bin/bash

cd /home/pi/robot/

git pull --ff-only # try to update beforehand; may fail (no internet etc.)

/home/pi/robot/startup.py
/home/pi/robot/main.py
