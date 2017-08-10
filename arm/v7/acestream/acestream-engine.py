#!/usr/bin/python2.7
import os
import sys
base_dir =  os.path.dirname(os.path.realpath(__file__))
python_modules_dir = os.path.join(base_dir,"python-modules")
sys.path.append(python_modules_dir)
curdir = os.path.abspath(os.path.dirname(sys.argv[0]))
from ACEStream.Plugin.EngineConsole import start
apptype = 'acestream'
start(apptype, curdir)

