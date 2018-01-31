from __future__ import absolute_import

"""
    M2Crypto utility routines.

    Copyright (c) 1999-2004 Ng Pheng Siong. All rights reserved.

    Portions created by Open Source Applications Foundation (OSAF) are
    Copyright (C) 2004 OSAF. All Rights Reserved.
"""

import sys

from M2Crypto import m2

# Python 2 has int() and long().
# Python 3 and higher only has int().
# Work around this.
if sys.version_info > (3,):
    long = int


class UtilError(Exception):
    pass

m2.util_init(UtilError)


def h2b(s):
    import array
    ar = array.array('c')
    start = 0
    if s[:2] == '0x':
        start = 2
    for i in range(start, len(s), 2):
        num = int("%s" % (s[i:i + 2],), 16)
        ar.append(chr(num))
    return ar.tostring()


def pkcs5_pad(data, blklen=8):
    pad = (8 - (len(data) % 8))
    return data + chr(pad) * pad


def pkcs7_pad(data, blklen):
    if blklen > 255:
        raise ValueError('illegal block size')
    pad = (blklen - (len(data) % blklen))
    return data + chr(pad) * pad


def octx_to_num(x):
    v = long(0)
    lx = len(x)
    for i in range(lx):
        v = v + ord(x[i]) * (long(256) ** (lx - i - 1))
    return v


def genparam_callback(p, n, out=sys.stdout):
    ch = ['.', '+', '*', '\n']
    out.write(ch[p])
    out.flush()


def quiet_genparam_callback(p, n, out):
    pass


def passphrase_callback(v, prompt1='Enter passphrase:',
                        prompt2='Verify passphrase:'):
    from getpass import getpass
    while 1:
        try:
            p1 = getpass(prompt1)
            if v:
                p2 = getpass(prompt2)
                if p1 == p2:
                    break
            else:
                break
        except KeyboardInterrupt:
            return None
    return p1


def no_passphrase_callback(*args):
    return ''
