#!/usr/bin/python2.7
import os
import sys
sys.path.append("/usr/share/acestream/python-modules")
curdir = os.path.abspath(os.path.dirname(sys.argv[0]))
from ACEStream.Plugin.EngineConsole import start
apptype = 'acestream'
start(apptype, curdir)

