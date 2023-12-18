# Python modules for controlling SURF.

These are the SURF-specific Python functions.

All functions which could be 'generic' go into anita-python.

To clone this repository make sure to clone with the recursive flag!

e.g. git clone --recursive https://github.com/barawn/surf_python 

This will pull in anita-python. Make sure to read the anita_python
documentation - you'll need to build that module first if you're
just going to use this module in place.

Also, when you pull updates, make sure to do

git pull
git submodule update --init --recursive

There are ways for this to be made automatic if it bothers you to
remember (aliases).


## Note
simple_script.py: to read data from all LABs using forced trigger,
simple_script9.py: to read data from single LAB,
simple_scripts81.py: to read test pattern from single LAB.