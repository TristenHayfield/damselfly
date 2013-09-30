#!/usr/bin/python

# Damselfly Copyright (C) 2013 Tristen Hayfield GNU GPL 3+
#
# Damselfly is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# Damselfly is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with Damselfly.  If not, see <http://www.gnu.org/licenses/>.

import ConfigParser
import os
import select
import sys
import subprocess
import re
import time
import signal

myName = 'DamselflyServer'
myVersion='2013-09-30'
myID = myName + ' v. ' + myVersion 
print myID

# load config
config = ConfigParser.SafeConfigParser()

if config.read(os.path.expanduser('~/.damselfly.cfg')) == []:
    raise Exception("Failed to find or parse config file: " + os.path.expanduser('~/.damselfly.cfg') + "\nPlease add a config file and restart the server.")

## paths for sweet fifo action

natLinkPath = config.get("paths","natLinkPath")

serverOut = natLinkPath + '/damselServerOut'
serverIn = natLinkPath + '/damselServerIn'

done = False
connected = False
stopped = False

fpO = None
fpI = None
ep = select.epoll()

# precompiled regular expressions for use by various command handlers
prewmc = re.compile(r'^WM_CLASS\(STRING\) = "([A-Za-z0-9._]*)", "([A-Za-z0-9._]*)"$', re.M)
prewmnm = re.compile(r'^WM_NAME\(STRING\) = "(.*)"$', re.M)

# here there be dragons: re's for parsing key commands
prekey = re.compile("^ *(?:([acswm]+)-)?([a-zA-Z0-9]+)(?:[/]([0-9]+(?=:[0-9]+)))?(?:[:]([0-9]+))?(?:[/]([0-9]+))? *$")
prekeyp = re.compile("^ *(?:([acswm]+)-)?([a-zA-Z0-9]+)(?:[:])(up|down)(?:[/]([0-9]+))? *$")

# re's for parsing mouse commands
premousemove = re.compile("^ *(?:\( *(-?[0-9]+|-?(?:0?\.[0-9]+|1\.0)) *, *(-?[0-9]+|-?(?:0?\.[0-9]+|1\.0)) *\)|\[ *(-?[0-9]+|-?(?:0?\.[0-9]+|1\.0)) *, *(-?[0-9]+|-?(?:0?\.[0-9]+|1\.0)) *\]|< *(-?[0-9]+) *, *(-?[0-9]+) *>) *$")
premousepress = re.compile("^ *(left|middle|wheel (?:up|down)|right)(?::([0-3]))?(?:/([0-9]+))? *$")
premousehr = re.compile("^ *(left|middle|wheel (?:up|down)|right):(hold|release)(?:/([0-9]+))? *$")
premousesep = re.compile(" *,(?![- .0-9]*[])>])")

# for finding clients of a root window
prerwc = re.compile(r'^_NET_CLIENT_LIST\(WINDOW\): window id # ((?:0x[0-9a-f]+(?:, )?)+)$', re.M)
prexpwa = re.compile(r'^\(XGetWindowProperty\[[A-Z_]+\] failed .*$', re.M)

# getting geometry from xwininfo
prewh = re.compile(r'^  Height: ([0-9]+)$', re.M)
preww = re.compile(r'^  Width: ([0-9]+)$', re.M)

def sighangup(signum, frame):
    global done
    disconnect()
    done = True

signal.signal(signal.SIGHUP, sighangup)

def connect():
    global fpO, fpI, connected, ep, done, stopped

    if not connected:
        try:
            if os.path.exists(serverOut):
                os.remove(serverOut)

            os.mkfifo(serverOut)

            if os.path.exists(serverIn):
                os.remove(serverIn)

            os.mkfifo(serverIn)

            print 'Attempting to open output fifo to client (could block) ... ',
            sys.stdout.flush()

            fpO = open(serverOut, 'w')
            print 'Success'

            print 'Attempting to open input fifo from client (could block)... ',
            sys.stdout.flush()

            fpI = open(serverIn, 'rU')
            print 'Success'

            connected = True
            stopped = False

            print 'Waiting for greeting (could block)... ',
            greeting = fpI.readline()
            print 'Success, greeting :', greeting

            print 'Sending response (could block)... ',
            fpO.write(myID+'\n')
            fpO.flush()
            print 'Success'


            print 'Registering input fifo for level polling ... ',
            ep.register(fpI, select.EPOLLIN | select.EPOLLERR | select.EPOLLHUP)
            print 'Success'

            print 'Polling connection ... ',
            polo()
        except KeyboardInterrupt:
            print 'Caught keyboard interrupt, exiting'
            done = True
        except IOError as e:
            print str(e)
            done = True
        finally:
            disconnect()

   

def disconnect():
    global fpO, fpI, connected, stopped

    try:
        if fpO is not None:
            fpO.close()
            fpO = None

        if fpI is not None:
            ep.unregister(fpI)
            fpI.close()
            fpI = None

        connected = False
        stopped = True
        print 'Disconnected'

        print 'Removing FIFOs ... ',
        if os.path.exists(serverOut):
            os.remove(serverOut)

        if os.path.exists(serverIn):
            os.remove(serverIn)
        print 'Done'
    except:
        print 'Unknown error in', sys._getframe().f_code.co_name, ', exiting: ', sys.exc_info()[0]
        raise


def polo():
    while True:
        iev = ep.poll(1.0)
        if len(iev) != 0:                
            if iev[0][1] & select.EPOLLIN:
                inputHandler()
            elif iev[0][1] & select.EPOLLERR:
                raise IOError("Unknown fifo error occurred")
            elif iev[0][1] & select.EPOLLHUP:
                print "hangup event, stopping polling"
                break
            else:
                raise Exception("unknown event")

def inputHandler():   
    imess = fpI.readline().strip()
    fdic.get(imess, Exception)(imess)


def doCmdOutputWithRetries(cmd, maxTries = 3, dt = 0.01):
    cmdSucceeded = False
    nt = 0
    while (not cmdSucceeded) and (nt < maxTries):
        try:            
            nt += 1
#            print 'attempt #', nt
            xp = subprocess.check_output(cmd, stderr = open(os.devnull,'w'))
            cmdSucceeded = True
        except subprocess.CalledProcessError as e:
            cmderr = e
            time.sleep(dt)
    if cmdSucceeded:
        return xp
    else:
        raise cmderr

def getXCtx(name):
    try:
        wid = int(doCmdOutputWithRetries(["xdotool", "getactivewindow"],1).strip())
        xp = doCmdOutputWithRetries(["xprop", "-id", str(wid)],1)

        wmc = prewmc.search(xp)
        wmnm = prewmnm.search(xp)
        if wmc:
            wmc = wmc.groups()[0] + ' ' + wmc.groups()[1]
        else:
            wmc = ''

        if wmnm:
            wmnm = wmnm.groups()[0]
        else:
            wmnm = ''

        fpO.write(wmnm+'\n')
        fpO.write(wmc+'\n')
        fpO.write(str(wid)+'\n')
        fpO.flush()
    except subprocess.CalledProcessError as e:
        mess = 'Failure: ' + str(e)
        print mess
        fpO.write(mess+'\n')
        fpO.flush()
        stopped = True


#--clearmodifiers
keySymDict = {
    'a' : 'a',
    'b' : 'b',
    'c' : 'c',
    'd' : 'd',
    'e' : 'e',
    'f' : 'f',
    'g' : 'g',
    'h' : 'h',
    'i' : 'i',
    'j' : 'j',
    'k' : 'k',
    'l' : 'l',
    'm' : 'm',
    'n' : 'n',
    'o' : 'o',
    'p' : 'p',
    'q' : 'q',
    'r' : 'r',
    's' : 's',
    't' : 't',
    'u' : 'u',
    'v' : 'v',
    'w' : 'w',
    'x' : 'x',
    'y' : 'y',
    'z' : 'z',
    'A' : 'A',
    'B' : 'B',
    'C' : 'C',
    'D' : 'D',
    'E' : 'E',
    'F' : 'F',
    'G' : 'G',
    'H' : 'H',
    'I' : 'I',
    'J' : 'J',
    'K' : 'K',
    'L' : 'L',
    'M' : 'M',
    'N' : 'N',
    'O' : 'O',
    'P' : 'P',
    'Q' : 'Q',
    'R' : 'R',
    'S' : 'S',
    'T' : 'T',
    'U' : 'U',
    'V' : 'V',
    'W' : 'W',
    'X' : 'X',
    'Y' : 'Y',
    'Z' : 'Z',
    '0' : '0',
    '1' : '1',
    '2' : '2',
    '3' : '3',
    '4' : '4',
    '5' : '5',
    '6' : '6',
    '7' : '7',
    '8' : '8',
    '9' : '9',
    ' ' : 'space',
    '_' : 'underscore',
    '.' : 'period',
    ',' : 'comma',
    '!' : 'exclam',
    '"' : 'quotedbl',
    '#' : 'numbersign',
    '$' : 'dollar',
    '%' : 'percent',
    '&' : 'ampersand',
    "'" : 'apostrophe',
    '(' : 'parenleft',
    ')' : 'parenright',
    '*' : 'asterisk',
    '+' : 'plus',
    '-' : 'minus',
    '/' : 'slash',
    ':' : 'colon',
    ';' : 'semicolon',
    '<' : 'less',
    '=' : 'equal',
    '>' : 'greater',
    '?' : 'question',
    '@' : 'at',
    '[' : 'bracketleft',
    ']' : 'bracketright',
    '^' : 'asciicircum',
    '`' : 'grave',
    '{' : 'braceleft',
    '|' : 'bar',
    '}' : 'braceright',
    '~' : 'asciitilde',
    'backslash' : 'backslash',
}

keyModDict = {
    'a' : 'alt',
    'c' : 'ctrl',
    's' : 'shift',
    'w' : 'super',
    'm' : 'meta',
}

keyDirDict = {
    'up' : 'keyup',
    'down' : 'keydown',
}

keyNameDict = {
    'a' : 'a',
    'b' : 'b',
    'c' : 'c',
    'd' : 'd',
    'e' : 'e',
    'f' : 'f',
    'g' : 'g',
    'h' : 'h',
    'i' : 'i',
    'j' : 'j',
    'k' : 'k',
    'l' : 'l',
    'm' : 'm',
    'n' : 'n',
    'o' : 'o',
    'p' : 'p',
    'q' : 'q',
    'r' : 'r',
    's' : 's',
    't' : 't',
    'u' : 'u',
    'v' : 'v',
    'w' : 'w',
    'x' : 'x',
    'y' : 'y',
    'z' : 'z',
    'A' : 'A',
    'B' : 'B',
    'C' : 'C',
    'D' : 'D',
    'E' : 'E',
    'F' : 'F',
    'G' : 'G',
    'H' : 'H',
    'I' : 'I',
    'J' : 'J',
    'K' : 'K',
    'L' : 'L',
    'M' : 'M',
    'N' : 'N',
    'O' : 'O',
    'P' : 'P',
    'Q' : 'Q',
    'R' : 'R',
    'S' : 'S',
    'T' : 'T',
    'U' : 'U',
    'V' : 'V',
    'W' : 'W',
    'X' : 'X',
    'Y' : 'Y',
    'Z' : 'Z',
    '0' : '0',
    '1' : '1',
    '2' : '2',
    '3' : '3',
    '4' : '4',
    '5' : '5',
    '6' : '6',
    '7' : '7',
    '8' : '8',
    '9' : '9',
    'left' : 'Left', 
    'right' : 'Right', 
    'up' : 'Up', 
    'down' : 'Down',
    'pgup' : 'Page_Up',
    'pgdown' : 'Page_Down',
    'home' : 'Home',
    'end' : 'End',
    'space' : 'space',
    'tab' : 'Tab',
    'enter' : 'Return',
    'backspace' : 'BackSpace',
    'del' : 'Delete',
    'insert' : 'Insert',
    'ampersand' : 'ampersand',
    'apostrophe' : 'apostrophe',
    'asterisk' : 'asterisk',
    'at' : 'at',
    'backslash' : 'backslash', 
    'colon' : 'colon', 
    'comma' : 'comma', 
    'dollar' : 'dollar',
    'backtick' : 'grave',
    'bar' : 'bar',
    'caret' : 'asciicircum',
    'dot' : 'period',
    'dquote' : 'quotedbl',
    'equal' : 'equal', 
    'minus' : 'minus', 
    'percent' : 'percent', 
    'plus' : 'plus', 
    'question' : 'question', 
    'semicolon' : 'semicolon', 
    'slash' : 'slash',
    'underscore' : 'underscore',
    'escape' : 'Escape',
    'exclamation' : 'exclam',
    'hash' : 'numbersign',
    'hyphen' : 'minus',
    'squote' : 'apostrophe',
    'tilde' : 'asciitilde',
    'f1' : 'F1',
    'f2' : 'F2',
    'f3' : 'F3',
    'f4' : 'F4',
    'f5' : 'F5',
    'f6' : 'F6',
    'f7' : 'F7',
    'f8' : 'F8',
    'f9' : 'F9',
    'f10' : 'F10',
    'f11' : 'F11',
    'f12' : 'F12',
    'f13' : 'F13',
    'f14' : 'F14',
    'f15' : 'F15',
    'f16' : 'F16',
    'f17' : 'F17',
    'f18' : 'F18',
    'f19' : 'F19',
    'f20' : 'F20',
    'f21' : 'F21',
    'f22' : 'F22',
    'f23' : 'F23',
    'f24' : 'F24',
    'ctrl' : 'ctrl',
    'alt' : 'alt',
    'shift' : 'shift',
    'langle' : 'less',
    'lbrace' : 'braceleft',
    'lbracket' : 'bracketleft',
    'lparen' : 'parenleft',
    'rangle' : 'greater',
    'rbrace' : 'braceright',
    'rbracket' : 'bracketright',
    'rparen' : 'parenright',
    'apps' : 'meta',
    'win' : 'super',    
    'np0' : 'KP_0',
    'np1' : 'KP_1',
    'np2' : 'KP_2',
    'np3' : 'KP_3',
    'np4' : 'KP_4',
    'np5' : 'KP_5',
    'np6' : 'KP_6',
    'np7' : 'KP_7',
    'np8' : 'KP_8',
    'np9' : 'KP_9',
    'npadd' : 'KP_Add',
    'npdec' : 'KP_Decimal',
    'npdiv' : 'KP_Divide',
    'npmul' : 'KP_Multiply',
    'npsep' : 'KP_Separator',
    'npsub' : 'KP_Subtract',   
}

mouseButtonDict = {
    'left' : '1',
    'middle' : '2',
    'right' : '3',
    'wheel up' : '4',
    'wheel down' : '5',
    }

mouseHRDict = {
    'down' : 'mousedown',
    'up' : 'mouseup',
    }

class ParseFailure(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)

class InvalidArgs(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)

class WindowNotFound(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)

def parseStr2xdotool(string):
    skip = False
    js = ''


    if string[0] == '\\':
        skip = True
        ns = []
    elif string[0] not in keySymDict:
        raise ParseFailure('invalid character: "' + string[0] + '" in string')
    else:
        ns = [keySymDict[string[0]]]

    if len(string) > 1: 
        for ch in string[1:]:
            if ch == ' ':
                skip = False
                if js == 'backslash':
                    ns.append(keySymDict[js])
                js = ''
            elif ch == '\\':
                skip = True
                continue
            
            if skip:
                js += ch
                continue
            
            if ch not in keySymDict:
                raise ParseFailure('invalid character: "' + ch + '" in string')
            ns.append(keySymDict[ch])

        if skip and js == 'backslash':
            ns.append(keySymDict[js])
            
    return ns

## need to parse:
# either: [modifiers -] keyname [/ innerpause] [: repeat] [/ outerpause]
# or: [modifiers -] keyname : direction [/ outerpause] 
## PARSES A SINGLE KEY
def parseKey2xdotool(kexp):
    babby = prekey.match(kexp)
    cmd = []
    op = None
    bc = 0
    tc = ''

    ## does babby conform to: [modifiers -] keyname [/ innerpause] [: repeat] [/ outerpause] ?
    if babby:
        #modifiers
        bg = babby.groups()
        if bg[0]:
            for ch in bg[0][:]:
                if ch in tc:
                    raise ParseFailure('Double modifier in expression: '+ str(bg[0]))
                tc += bc*'+' + keyModDict[ch]
                bc = 1
        #key to send
        if bg[1] not in keyNameDict:
            raise ParseFailure('invalid key name in expression: '+ str(bg[1]))

        tc += bc*'+' + keyNameDict[bg[1]]

        cmd.append(tc)

        cmd.insert(0,'-delay')
        if bg[2]:
            cmd.insert(1, bg[2])
        else:
            cmd.insert(1, '1')
            
        if bg[3]:
            cmd.extend((int(bg[3])-1)*[tc])

        cmd.insert(0, 'key')
        cmd.insert(1, '-clearmodifiers')

        if bg[4]:
            op = float(bg[4])/1000.0
    else:        
        # does babby conform to: [modifiers -] keyname : direction [/ outerpause] ?
        babby = prekeyp.match(kexp)

        if babby is None:
            raise ParseFailure('invalid key expression: ' + kexp)

        bg = babby.groups()
        if bg[0]:
            for ch in bg[0][:]:
                if ch in tc:
                    raise ParseFailure('Double modifier in expression: '+ str(bg[0]))
                tc += bc*'+' + keyModDict[ch]
                bc = 1
        #key to send
        if bg[1] not in keyNameDict:
            raise ParseFailure('invalid key name in expression: '+ bg[1])

        tc += bc*'+' + keyNameDict[bg[1]]

        cmd.append(tc)

        cmd.insert(0, bg[2])
        cmd.insert(1, '-clearmodifiers')

        if bg[3]:
            op = float(bg[3])/1000.0
            
    return [cmd, op]

## need to parse:
# either: movement (3*2 types), or clicks, or presses
## PARSES A SINGLE mouse command

def parseMouse2xdotool(kexp):
    babby = premousemove.match(kexp)
    cmd = []
    op = None

    ## does babby move?
    if babby:
        ic = None
        wh = None
        mref = None

        bg = babby.groups()
        ## 0,1 - parentheses - window-relative
        ## 2,3 - brackets - absolute
        ## 4,5 - angle brackets - mouse-relative
        if bg[0]:
            cmd = ["getactivewindow","mousemove","--window","%1"]
            ic = 0
            mref = "active"
        elif bg[2]:
            cmd = ["mousemove"]
            ic = 2
            mref = "root"
        else:
            ic = 4
            cmd = ["mousemove_relative"]
            mref = "mouse"

        ## tests for presence of - or .
        ix = bg[ic].isdigit()
        iy = bg[ic+1].isdigit()

        if not (ix and iy):
            wh = getWindowSize(mref)
            
        ## test for integer coords
        if bg[ic].find('.') == -1:
            x = int(bg[ic])
            if x < 0:
                x += wh[0]
        else:
            x = float(bg[ic])
            if x < 0.0:
                x += 1.0
            x = int(round(x*(wh[0]-1)))

        cmd.append(str(x))

        if bg[ic+1].find('.') == -1:
            y = int(bg[ic+1])
            if y < 0:
                y += wh[1]
        else:
            y = float(bg[ic+1])
            if y < 0.0:
                y += 1.0
            y = int(round(y*(wh[1]-1)))

        cmd.append(str(y))

    else:        
        # does babby click
        babby = premousepress.match(kexp)

        if babby:
            bg = babby.groups()
            cmd = ["click"]
            if bg[2]:
                op = float(bg[2])/100.0
                
            if bg[1]:
                if int(bg[1]) == 0:
                    cmd = ["sleep", "0"]
                    return [cmd,op]
                else:
                    cmd.extend(["--repeat",bg[1]])

            cmd.append(mouseButtonDict[bg[0]])
        else:
            babby = premousehr.match(kexp)

            if babby is None:
                raise ParseFailure('invalid mouse expression: ' + kexp)

            bg = babby.groups()
            
            cmd = [mouseHRDict[bg[1]], mouseButtonDict[bg[0]]]
            
            if bg[2]:
                op = float(bg[2])/100.0

    return [cmd, op]

def sendXText(name):
    global stopped
    try:
        istr = fpI.readline().strip()
        if not stopped:
            cmd = ["xdotool", "key", "-clearmodifiers"]
            res = parseStr2xdotool(istr)
            if res:
                cmd.extend(res)
                xp = subprocess.check_call(cmd)
            fpO.write('Success\n')
            fpO.flush()
        else:
            fpO.write('Failure: Server is stopped, please resume it before continuing\n')
            fpO.flush()

    except (subprocess.CalledProcessError, ParseFailure) as e:
        mess = 'Failure: ' + str(e)
        print mess
        fpO.write(mess+'\n')
        fpO.flush()
        stopped = True

def sendXInput(name):
    global stopped
    try:
        lstr = fpI.readline().strip()
        if not stopped:
            if name == "sendXKeys":
                lstr = lstr.split(',')
            elif name == "sendXMouse":
                lstr = premousesep.split(lstr)
                        
            for istr in lstr:
                cmd = ["xdotool"]
                if name == "sendXKeys":
                    tcmd = parseKey2xdotool(istr)
                elif name == "sendXMouse":
                    tcmd = parseMouse2xdotool(istr)
                    
                cmd.extend(tcmd[0])
                xp = subprocess.check_call(cmd)

                if tcmd[1]:
                    time.sleep(tcmd[1])

            fpO.write('Success\n')
            fpO.flush()
        else:
            fpO.write('Failure: Server is stopped, please resume it before continuing\n')
            fpO.flush()
    except (subprocess.CalledProcessError, ParseFailure) as e:
        mess = 'Failure: ' + str(e)
        print mess
        fpO.write(mess+'\n')
        fpO.flush()
        stopped = True

def doResume(name):
    global stopped
    stopped = False
    print 'Resumed.'
    fpO.write('Success\n')
    fpO.flush()


def getWindowSize(id = "root"):
    if id == "root":
        wid = int(doCmdOutputWithRetries(['xdotool', 'search','--limit','1', '--maxdepth', '0', '']).strip())
    elif id == "active":
        wid = int(doCmdOutputWithRetries(['xdotool', 'getactivewindow']))
    else:
        wid = int(id)        
    xp = doCmdOutputWithRetries(['xwininfo', '-id', str(wid)])
    width = int(preww.search(xp).groups()[0])
    height = int(prewh.search(xp).groups()[0])
    return [width,height]

def findRootWindowClients(tids):
    try:
        wid = int(doCmdOutputWithRetries(['xdotool', 'search','--limit','1', '--maxdepth', '0', '']).strip())
    
        xp = doCmdOutputWithRetries(['xprop', '-id', str(wid)])

#        print 'wid',str(wid)
        babby = prerwc.search(xp)
        if babby:
            ids = frozenset(map(lambda x: int(x, base=16), babby.groups()[0].split(', ')))
#            print 'ids:',ids

            return list(ids & tids)
        else:
            return []
    except subprocess.CalledProcessError:
        return []

def getWindowArgs(mode, value):
    if mode == 'id':
        return int(value)
    elif mode == 'any':
        xp = doCmdOutputWithRetries(['xdotool', 'search', value]).split()
    elif mode in ('name','class'):
        xp = doCmdOutputWithRetries(['xdotool', 'search', '--'+mode, value]).split()
    else:
        raise InvalidArgs('Invalid argument to focusWindow: ' + tp)

    tids = frozenset(map(int, xp))
    ids = findRootWindowClients(tids)

    if len(ids) > 0:
        return(ids[0])
    else:
        raise WindowNotFound('Could not find window: ' + value)


def focusWindowArgs(mode, value):
    if mode == 'id':
        cmd = ['xdotool','windowactivate', '--sync', str(value)]
    elif mode == 'any':
        xp = doCmdOutputWithRetries(['xdotool', 'search', value]).split()
        tids = frozenset(map(int, xp))
#        print 'tids:', tids
        ids = findRootWindowClients(tids)
        if len(ids) > 0:
            cmd = ['xdotool','windowactivate', '--sync', str(ids[0])]
        else:
            raise WindowNotFound('Could not find activatable window: ' + value)
    elif mode in ('name','class'):
        xp = doCmdOutputWithRetries(['xdotool', 'search', '--'+mode, value]).split()
        tids = frozenset(map(int, xp))

        ids = findRootWindowClients(tids)
        if len(ids) > 0:
            cmd = ['xdotool','windowactivate', '--sync', str(ids[0])]
        else:
            raise WindowNotFound('Could not find activatable window: ' + value)
    else:
        raise InvalidArgs('Invalid argument to focusWindow: ' + tp)

    # this command will either fail with an error, complete almost immediately (success), or complete after a short pause and complain to stderr (fail)
#    print cmd
    xp = subprocess.check_output(cmd)
    babby = prexpwa.search(xp)

    if babby:
        raise WindowNotFound('Could not activate window: ' + value)


def focusXWindow(name):
    global stopped
    try:
        tp = fpI.readline().strip()
        val = fpI.readline().strip()

        if not stopped:
            print 'focuswindow:', tp, val
            focusWindowArgs(tp,val)
            fpO.write('Success\n')
            fpO.flush()
        else:
            fpO.write('Failure: Server is stopped, please resume it before continuing\n')
            fpO.flush()
    except (subprocess.CalledProcessError, InvalidArgs, WindowNotFound) as e:
        mess = 'Failure: ' + str(e)
        print mess
        fpO.write(mess+'\n')
        fpO.flush()
        stopped = True

def hideXWindow(name):
    global stopped
    try:
        tp = fpI.readline().strip()
        val = fpI.readline().strip()

        if not stopped:
            print 'hideXWindow:', tp, val
            if val != 'None':
                res = getWindowArgs(tp,val)
                xp = doCmdOutputWithRetries(['xdotool', 'windowminimize', '--sync', str(res)])
            else:
                xp = doCmdOutputWithRetries(['xdotool', 'getactivewindow', 'windowminimize', '--sync'])
            fpO.write('Success\n')
            fpO.flush()
        else:
            fpO.write('Failure: Server is stopped, please resume it before continuing\n')
            fpO.flush()
    except (subprocess.CalledProcessError, InvalidArgs, WindowNotFound) as e:
        mess = 'Failure: ' + str(e)
        print mess
        fpO.write(mess+'\n')
        fpO.flush()
        stopped = True

## at the moment we support a limited version of this call, with no args supplied
def startXApp(name):
    global stopped
    try:
        appname = fpI.readline().strip()
        if not stopped:
            sp = subprocess.Popen([appname])
            fpO.write('Success\n')
            fpO.flush()
        else:
            fpO.write('Failure: Server is stopped, please resume it before continuing\n')
            fpO.flush()
    except OSError as e:
        mess = 'Failure: ' + str(e)
        print mess
        fpO.write(mess+'\n')
        fpO.flush()
        stopped = True

def waitXWindow(name):
    global stopped
    try:
        winname = fpI.readline().strip()
        timeout = float(fpI.readline().strip())
        if not stopped:
            xp = doCmdOutputWithRetries(['xdotool', 'search', winname]).split()
            tids = frozenset(map(int, xp))
            ids = findRootWindowClients(tids)
            if len(ids) > 0:
                cmd = ['xdotool','behave', str(ids[0]), 'focus', 'exec', 'echo', 'focus']
            else:
                raise WindowNotFound('Could not find activatable window: ' + value)

            sp = subprocess.Popen(cmd, stdout = subprocess.PIPE, stderr = open(os.devnull,'w'))
            tep = select.epoll()
            tep.register(sp.stdout, select.EPOLLIN | select.EPOLLERR | select.EPOLLHUP)
            iev = tep.poll(timeout)
            exp = None
            if len(iev) != 0:                
                if iev[0][1] & select.EPOLLIN:
                    xp = sp.stdout.readline().strip()
                    if xp != 'focus':
                        exp = Exception("unexpected message while waiting for window: " + xp)
                else:
                    exp = Exception("unknown exception occurred while waiting for window")
            else:
                exp =  WindowNotFound("wait timeout occurred")
            tep.unregister(sp.stdout)
            tep.close()
            sp.terminate()
            if exp:
                raise exp
            fpO.write('Success\n')
            fpO.flush()
        else:
            fpO.write('Failure: Server is stopped, please resume it before continuing\n')
            fpO.flush()
    except (OSError, subprocess.CalledProcessError, WindowNotFound) as e:
        mess = 'Failure: ' + str(e)
        print mess
        fpO.write(mess+'\n')
        fpO.flush()
        stopped = True



def bringXApp(name):
    global stopped
    try:
        winname = fpI.readline().strip()
        execname = fpI.readline().strip()
        timeout = float(fpI.readline().strip())
        if not stopped:
            try:
                focusWindowArgs('any', winname)
            except (subprocess.CalledProcessError, WindowNotFound) as e:
                sp = subprocess.Popen([execname])
                t0 = time.time()
                wf = False
                wfexcp = None
                while ((time.time() - t0) < max(timeout, 0.1)) and not wf:
                    time.sleep(0.1) # needs to be replace with some kind of polling
                    try:
                        focusWindowArgs('any', winname)
                        wf = True
                    except WindowNotFound as e:
                        wfexcp = e

                if not wf:
                    raise wfexcp

            fpO.write('Success\n')
            fpO.flush()
        else:
            fpO.write('Failure: Server is stopped, please resume it before continuing\n')
            fpO.flush()
    except (OSError, subprocess.CalledProcessError, WindowNotFound) as e:
        mess = 'Failure: ' + str(e)
        print mess
        fpO.write(mess+'\n')
        fpO.flush()
        stopped = True

fdic = { 
    "getXCtx": getXCtx, 
    "sendXText" : sendXText,
    "sendXKeys" : sendXInput,
    "sendXMouse" : sendXInput,
    "doResume" : doResume,
    "focusXWindow" : focusXWindow,
    "startXApp" : startXApp,
    "bringXApp" : bringXApp,
    "waitXWindow" : waitXWindow,
    "hideXWindow" : hideXWindow,
    }

if __name__ == "__main__":
    while not done:
        connect()

