#Embedded file name: ACEStream\__init__.pyo
LIBRARYNAME = 'ACEStream'
DEFAULT_I2I_LISTENPORT = 0
import os
current_file_path = os.path.dirname(os.path.realpath(__file__))
port_file = os.path.join(current_file_path,"values","port.txt")
f = open(port_file, "r")
string = f.read()
DEFAULT_SESSION_LISTENPORT = int(string)
DEFAULT_HTTP_LISTENPORT = 6878
