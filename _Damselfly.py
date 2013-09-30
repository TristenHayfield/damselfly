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

import natlinkstatus

import sys
import re

from dragonfly import (Grammar, Rule, MappingRule, CompoundRule,
                       Dictation, IntegerRef, Context, ActionBase)

from dragonfly.actions.action_base import DynStrActionBase

myName = 'Damselfly'
myVersion='2013-09-30'
myID = myName + ' v. ' + myVersion 
print myID

## need to figure out where natlink resides
status = natlinkstatus.NatlinkStatus()

# fifos to SnapDragonServer

## is this a reasonable way of divining the natlink path?
natLinkPath = status.getCoreDirectory().rstrip('core')

serverOut = natLinkPath + 'damselServerOut'
serverIn = natLinkPath + 'damselServerIn'

connected = False
fpO = None
fpI = None

windowCache = {}

class ConnectionDropped(Exception):
    def __init__(self, value = None):
        self.value = value
    def __str__(self):
        return repr(self.value)

class CommandFailure(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)

def connect():
    global fpO, fpI, connected

    if not connected:
        try:
            print 'Attempting to open input fifo from server (could block)... ',
            sys.stdout.flush()

            fpI = open(serverOut, 'rU')
            print 'Success'

            print 'Attempting to open output fifo to server (could block)... ',
            sys.stdout.flush()

            fpO = open(serverIn, 'w')
            print 'Success'
            connected = True

            print 'Sending greeting (could block)... ',
            fpO.write(myID+'\n')
            fpO.flush()
            print 'Success'

            print 'Waiting for response (could block)... ',
            response = fpI.readline()
            print 'Success, response :', response

        except IOError as ee:
            print 'IOError: ', ee
            disconnect()
        except:
            print 'Unknown error: ', sys.exc_info()[0]
            disconnect()


def disconnect():
    global fpO, fpI, connected

    if fpO is not None:
        fpO.close()
        fpO = None

    if fpI is not None:
        fpI.close()
        fpI = None

    print 'Disconnected'

    connected = False

def resumeServer():
    if connected:
        try:
            fpO.write('doResume\n')
            fpO.flush()

            res = fpI.readline().strip()

            if res != 'Success':
                raise CommandFailure(res)
        except (CommandFailure, KeyboardInterrupt, IOError) as e:
            print "caught exception:" +  str(e) + 'aborting and disconnecting'
            disconnect()
            raise ConnectionDropped()

def getXCtx():
    if connected:
        try:
            print 'Requesting X context... ',
            fpO.write('getXCtx\n')
            fpO.flush()
            print 'request sent'

            xctx = []
            print 'waiting for response... ',
            xctx.append(fpI.readline().strip())
            if xctx[0].startswith('Failure'):
                raise CommandFailure(xctx[0])
            xctx.append(fpI.readline().strip())
            xctx.append(int(fpI.readline().strip()))
            print 'response received: ', xctx
            return xctx
        except (KeyboardInterrupt, IOError) as e:
            print "caught exception:" +  str(e) + 'aborting and disconnecting'
            disconnect()
            raise ConnectionDropped()

# custom contexts

def reCmp(pattern, string):
    return pattern.search(string) is not None

def strCmp(sub, string):
    return sub in string

class XAppContext(Context):
    def __init__(self, wmname = None, wmclass = None, wid = None, usereg = False):
        self.wmname = wmname
        
        if wmclass is None:
            self.wmclass = wmname
            self.either = True
        else:
            self.wmclass = wmclass
            self.either = False
                
        self.wid = wid

        if usereg:
            self.myCmp = reCmp

            if self.wmname:
                self.wmname = re.compile(self.wmname)

            if self.wmclass:
                self.wmclass = re.compile(self.wmclass)

        else:
            self.myCmp = strCmp

        self.emptyCtx = (wmname is None) & (wmclass is None) & (wid is None) 
        self._str = "name: " + str(wmname) + ", " + "class: " + str(wmclass) + ", " + "id: " + str(wid)


    def matches(self, executable, title, handle):
        if connected:
            if self.emptyCtx:
                return True
            else :
#                if (executable != '') or (title != '') or (handle != 0):
#                    return False
        
                iMatch = True        

                try:
                    ctx = getXCtx()
                except CommandFailure:
                    resumeServer()
                    return False
                except ConnectionDropped:
                    return False

                if self.either:
                    iMatch &= self.myCmp(self.wmname, ctx[0]) | self.myCmp(self.wmclass, ctx[1])
                else:
                    if self.wmname:                   
                        iMatch &= self.myCmp(self.wmname, ctx[0])

                    if self.wmclass:
                        iMatch &= self.myCmp(self.wmclass, ctx[1])
                
                    
                if self.wid:
                    iMatch &= (ctx[2] == self.wid)

                return iMatch
        else :
            return False

# custom actions: prepare for the babbyscape
def dispatchAndHandle(mess):
    if connected:
        try:
            print 'sending request'
            fpO.write(mess)
            fpO.flush()
            print 'request sent'
            print 'waiting for response... ',
            res = fpI.readline().strip()
            print 'response received: ', res
        
            if res.startswith('Failure'):
                raise CommandFailure(res)
            elif res != 'Success':
                raise Exception(res)

        except CommandFailure as e:
            print 'Execution failed: ' + str(e)
            return False
        except (KeyboardInterrupt, IOError) as e:
            print "Caught exception:" +  str(e) + ': aborting and disconnecting'
            disconnect()
            raise ConnectionDropped()
    else:
        return False

class FocusXWindow(DynStrActionBase):
    def __init__(self, spec, search = None, static = False):
        DynStrActionBase.__init__(self, spec = spec, static = static)
        if not search:
            self.search = 'any'
        else:
            self.search = str(search)

    def _execute_events(self, events):
        if (self.search == 'any') and (self._pspec in windowCache):
            mymess = 'focusXWindow\n' + 'id' + '\n' + windowCache[self._pspec] + '\n'
        else:
            mymess = 'focusXWindow\n' + self.search + '\n' + str(self._pspec) + '\n'
        return(dispatchAndHandle(mymess))

    def _parse_spec(self, spec):
        self._pspec = spec
        return self

class HideXWindow(DynStrActionBase):
    def __init__(self, spec = None, search = None, static = False):
        DynStrActionBase.__init__(self, spec = str(spec), static = (spec is None))
        if not search:
            self.search = 'any'
        else:
            self.search = str(search)

    def _execute_events(self, events):
        if (self.search == 'any') and (self._pspec in windowCache):
            mymess = 'hideXWindow\n' + 'id' + '\n' + windowCache[self._pspec] + '\n'
        else:
            mymess = 'hideXWindow\n' + self.search + '\n' + str(self._pspec) + '\n'
        return(dispatchAndHandle(mymess))

    def _parse_spec(self, spec):
        self._pspec = spec
        return self

class CacheXWindow(DynStrActionBase):
    def __init__(self, spec, static = False, forget = False):
        DynStrActionBase.__init__(self, spec = str(spec), static = static)
        self.search = 'id'
        self.forget =  forget

    def _execute_events(self, events):
        global windowCache
        if not self.forget:            
            xctx = getXCtx()
            if xctx:
                windowCache[self._pspec] = str(xctx[2])
            else:
                return False
        else:
            if self._pspec == 'all':
                windowCache = {}
            elif self._pspec in windowCache:
                del windowCache[self._pspec]
            else:
                return False
            
    def _parse_spec(self, spec):
        self._pspec = spec
        return self


class BringXApp(ActionBase):
    def __init__(self, execname, winname = None, timeout = 5.0):
        ActionBase.__init__(self)
        self.execname = execname
        if winname == None:
            self.winname = execname
        else:
            self.winname = winname
        self.timeout = timeout

    def _execute(self, data=None):
        mymess = 'bringXApp\n' + self.winname + '\n' + self.execname + '\n'
        mymess += str(self.timeout) + '\n'
        return(dispatchAndHandle(mymess))

class WaitXWindow(ActionBase):
    def __init__(self, title, timeout = 5.0):
        ActionBase.__init__(self)
        self.winname = title
        self.timeout = timeout

    def _execute(self, data=None):
        mymess = 'waitXWindow\n' + self.title + '\n' + str(self.timeout) + '\n'
        return(dispatchAndHandle(mymess))

class StartXApp(ActionBase):
    def __init__(self, execname):
        ActionBase.__init__(self)
        self.execname = execname

    def _execute(self, data=None):
        mymess = 'startXApp\n' + self.execname + '\n'
        return(dispatchAndHandle(mymess))

class XKey(DynStrActionBase):
    def _execute_events(self, events):
        mymess = 'sendXKeys\n' + self._pspec + '\n'
        return(dispatchAndHandle(mymess))

    def _parse_spec(self, spec):
        self._pspec = spec
        return self

class XMouse(DynStrActionBase):
    def _execute_events(self, events):
        mymess = 'sendXMouse\n' + self._pspec + '\n'
        return(dispatchAndHandle(mymess))

    def _parse_spec(self, spec):
        self._pspec = spec
        return self

## neither autoformat nor pause are considered atm
class XText(DynStrActionBase):
    def __init__(self, spec, static = False, space = True, title = False, upper = False):
        DynStrActionBase.__init__(self, spec = str(spec), static = static)
        self.space = space
        self.title = title
        self.upper = upper

    def _parse_spec(self, spec):
        self._pspec = spec
        return self

    def _execute_events(self, events):
        tspec = self._pspec
        if self.title:
            tspec = tspec.title()
        elif self.upper:
            tspec = tspec.upper()
            
        if not self.space:
            tspec = tspec.replace(' ','')
            
        mymess = 'sendXText\n' + tspec + '\n'
        return(dispatchAndHandle(mymess))

class DoNothing(ActionBase):
    def __init__(self, message = 'Recognition event consumed.'):
        self.message = message
        
    def _execute(self, data=None):
        print self.message
        
# custom grammars



# rules
class ConnectRule(CompoundRule):
    spec = "damselfly connect"

    def _process_recognition(self, node, extras):
        connect()

class DisconnectRule(CompoundRule):
    spec = "damselfly disconnect"

    def _process_recognition(self, node, extras):
        disconnect()

class ResumeRule(CompoundRule):
    spec = "damselfly resume"

    def _process_recognition(self, node, extras):
        resumeServer()
        print 'Resumed.'

# rudimentary wm control
class WMRule(MappingRule):
    mapping = {
        "win hide" : HideXWindow(),
        "win hide <text>" : HideXWindow("%(text)s"),
        "win cache <text>" : CacheXWindow("%(text)s"),
        "win forget <text>" : CacheXWindow("%(text)s", forget = True),
        "win focus <text>" : FocusXWindow("%(text)s"),
        }
    extras = [
        Dictation("text")
        ]
    
# these rules consume events which could cause dragon to hang or behave
# strangely in linux

class DNSOverride(MappingRule):
    mapping = {
        "type [<text>]" : DoNothing(),
        "MouseGrid [<text>]" : DoNothing(),
        "mouse [<text>]" : DoNothing(),
        "copy [(that | line)]" : DoNothing(),
        "paste [that]" : DoNothing(),
        }
    extras = [
        Dictation("text")
        ]

######################################################################
# USER DEFINED RULES BELOW THIS POINT                                #
######################################################################

#######################################
## charkey : basic character input
#######################################

class CharkeyRule(MappingRule):
    mapping = {
        "alpha" : XKey("a"),
        "bravo" : XKey("b"),
        "Charlie" : XKey("c"),
        "delta" : XKey("d"),
        "echo" : XKey("e"),
        "foxtrot" : XKey("f"),
        "golf" : XKey("g"),
        "hotel" : XKey("h"),
        "India" : XKey("i"),
        "Jill" : XKey("j"),
        "kilo" : XKey("k"),
        "Lima" : XKey("l"),
        "Mike" : XKey("m"),
        "nova" : XKey("n"),
        "Oscar" : XKey("o"),
        "papa" : XKey("p"),
        "Quebec" : XKey("q"),
        "Romeo" : XKey("r"),
        "sick" : XKey("s"),
        "tango" : XKey("t"),
        "unit" : XKey("u"),
        "Victor" : XKey("v"),
        "whiskey" : XKey("w"),
        "xray" : XKey("x"),
        "yankee" : XKey("y"),
        "Zulu" : XKey("z"),
        "one" : XKey("1"),
        "(to | two | too)" : XKey("2"),
        "three" : XKey("3"),
        "four" : XKey("4"),
        "five" : XKey("5"),
        "six" : XKey("6"),
        "seven" : XKey("7"),
        "eight" : XKey("8"),
        "nine" : XKey("9"),
        "zero" : XKey("0"),
        "dot" : XText("."),
        "plus" : XText("+"),
        "(minus | hyphen)" : XText("-"),
        "stress" : XText("_"),
        "star" : XText("*"),
        "bar" : XText("|"),
        "dollar" : XText("$"),
        "equals" : XText("="),
        "caret" : XText("^"),
        "bang" : XText("!"),
        "colon" : XText(":"),
        "semi" : XText(";"),
        "pound" : XText("#"),
        "tilde" : XText("~"),
        "Andy" : XText("&"),
        "Atoll" : XText("@"),
        "slash" : XText("/"),
        "lash" : XKey("backslash"),
        "quest" : XText("?"),
        "grave" : XText("`"),
        "percent" : XKey('percent'),
        "lesser" : XText('<'),
        "greater" : XText('>'),
        "candy" : XKey('comma'),
        "brace left" : XText('{'),
        "brace right" : XText('}'),
        "pen left" : XText('('),
        "pen right" : XText(')'),
        "rack left" : XText('['),
        "rack right" : XText(']'),
        "home" : XKey("home"),
        "end" : XKey("end"),
        "tab" : XKey("tab"),
        "enter" : XKey("enter"),
        "space" : XKey("space"),
        "quote" : XKey("dquote"),
        "tick" : XKey("squote"),
        "dirk <text>" : XText("%(text)s", space = False),
        "camel <text>" : XText("%(text)s", space = False, title = True),
        "caps <text>" :  XText("%(text)s", space = False, upper = True),
        "shank <text>": XText("%(text)s"),
        }
    extras = [
        Dictation("text"),
        ]
        
########################################
# emacs
########################################

class EmacsEditRule(MappingRule):
    mapping = {
        "up [<n>]" : XKey("up:%(n)d"),
        "down [<n>]" : XKey("down:%(n)d"),
        "left [<n>]" : XKey("left:%(n)d"),
        "right [<n>]" : XKey("right:%(n)d"),
        "page [<n>]": XKey("pgdown:%(n)d"),
        "leaf [<n>]": XKey("pgup:%(n)d"),
        "tab [<n>]" : XKey("tab:%(n)d"),
        "page right": XKey("ca-v"),
        "leaf right": XKey("cas-v"),
        "top" : XKey("c-home"),
        "bottom" : XKey("m-rangle"),
        "top right" : XKey("m-home"),
        "bottom right" : XKey("m-end"),
        "word [<n>]" :  XKey("c-u,%(n)d,a-f"),
        "vow [<n>]" :  XKey("c-u,%(n)d,a-b"),
        "skip [<n>]" :  XKey("c-u,%(n)d,ca-f"),
        "creep [<n>]" :  XKey("c-u,%(n)d,ca-b"),
        "hence [<n>]" :  XKey("c-u,%(n)d,a-e"),
        "whence [<n>]" :  XKey("c-u,%(n)d,a-a"),
        "del [<n>]" : XKey("del:%(n)d"),
        "rub [<n>]": XKey("backspace:%(n)d"),
        "kill [<n>]": XKey("c-u,%(n)d,c-k"),
        "slay [<n>]": XKey("c-u,%(n)d,a-d"),
        "snuff [<n>]": XKey("c-u,%(n)d,a-backspace"),
        "yank": XKey("c-y"),
        "pull [<n>]": XKey("c-u,%(n)d,m-y"),
        "cram": XKey("home,down,enter,up,c-y"),
        "wedge": XKey("home,enter,up,c-y"),
        "save": XKey("c-x,c-s"),
        "open": XKey("c-x,c-f"),
        "open <text>": XKey("c-x,c-f,tab:2,w-c,c-s")+XText("%(text)s"),
        "swap": XKey("c-x,o"),
        "mark": XKey("c-space"),
        "mark from <text> to <other>": XKey("c-s") + XText("%(text)s") + XKey("enter,c-r,enter:2,c-space,c-s") + XText("%(other)s") + XKey("enter"),
        "mark up from <text> to <other>": XKey("c-r") + XText("%(text)s") + XKey("enter,c-s,enter:2,c-space,c-r") + XText("%(other)s") + XKey("enter"),
        "mark in from <text> to <other>": XKey("c-r") + XText("%(text)s") + XKey("enter,c-s,enter:2,c-space,c-s") + XText("%(other)s") + XKey("enter"),
        "pinch": XKey("m-w"),
        "pinch from <text> to <other>": XKey("c-s") + XText("%(text)s") + XKey("enter,c-r,enter:2,c-space,c-s") + XText("%(other)s") + XKey("enter,m-w"),
        "pinch up from <text> to <other>": XKey("c-r") + XText("%(text)s") + XKey("enter,c-s,enter:2,c-space,c-r") + XText("%(other)s") + XKey("enter,m-w"),
        "pinch in from <text> to <other>": XKey("c-r") + XText("%(text)s") + XKey("enter,c-s,enter:2,c-space,c-s") + XText("%(other)s") + XKey("enter,m-w"),
        "swipe": XKey("c-space,c-e,m-w"),
        "lift": XKey("c-w"),
        "quit": XKey("c-g"), #+ XText("keyboard-quit")  + XKey("enter"),
        "solo": XKey("c-x,1"),
        "limbo" : XKey("c-x,2"),
        "split" : XKey("c-x,3"),
        "goto" : XKey("m-g,g"),
        "undo [<n>]" :  XKey("c-u,%(n)d,c-slash"),
        "exit stage": XKey("c-x,c-c"),
        "find" : XKey("c-s"),
        "find <text>" : XKey("c-s") + XText("%(text)s"),
        "scout" : XKey("c-r"),
        "scout <text>" : XKey("c-r") + XText("%(text)s"),
        "hunt" : XKey("ca-s"),
        "track": XKey("cm-r"),
        "grill": XKey("m-percent"),
        "grill <text>": XKey("m-percent") + XText("%(text)s"),
        "grill <text> with <other>" : XKey("m-percent") + XText("%(text)s") + XKey("enter") + XText("%(other)s")+ XKey("enter"),
        "query": XKey("cm-percent"),
        "sub" : XKey("m-x") + XText("replace-string") + XKey("enter"),
        "sub <text> with <other>" : XKey("m-x") + XText("replace-string") + XKey("enter") + XText("%(text)s") + XKey("enter") + XText("%(other)s")+ XKey("enter"),
        "manual" : XKey("m-x") + XText("man") + XKey("enter"),
        "manual <text>" : XKey("m-x") + XText("man") + XKey("enter") + XText("%(text)s"),
        "macro start" : XKey("c-x,lparen"),
        "macro end" : XKey("c-x,rparen"),
        "macro do" : XKey("c-x,e"),
        "macro name" : XKey("c-x,c-k,n"),
        "macro name <text>" : XKey("c-x,c-k,n") + XText("%(text)s") + XKey("enter"),
        "tap": XText("e"),
        "cast" : XKey("m-x"),
        "cast <text>" : XKey("m-x") + XText("%(text)s") + XKey("enter"),
        "point" : XKey("c-x,r,space"),
        "point [<n>]" : XKey("c-x,r,space") + XText("%(n)d"),
        "jump" : XKey("c-x,r,j"),
        "jump [<n>]" : XKey("c-x,r,j") + XText("%(n)d"),
        "buff" : XKey("c-x,b"),
        "buff <text>" : XKey("c-x,b,c-s") + XText("%(text)s") + XKey("enter:2"),
        "buffer" : XKey("c-x,b,enter"),
        "murder" : XKey("c-x,k"),
        "murder <text>" : XKey("c-x,k,c-s") + XText("%(text)s") + XKey("enter:2"),
        "execute" : XKey("c-x,k,enter"),
        "fill" : XKey("m-x") + XText("fill-region") + XKey("enter"),
        "indent": XKey("ca-backslash"),
        "get": XKey("a-slash"),
        "yes": XText("yes") + XKey("enter"),
        "no": XText("no") + XKey("enter"),
        "yep": XKey("c-x,z"),        
        "help" : XKey("c-h,question"),
        "clamp": XKey("lbracket,rbracket,left"),
        "clamp <text>": XText("[%(text)s]"),
        "fix": XKey("lparen,rparen,left"),
        "fix <text>": XText("(%(text)s)"),
        "brace": XKey("lbrace,rbrace,left"),
        "brace <text>": XText("{%(text)s}"),
        "angle": XKey("langle,rangle,left"),
        "angle <text>": XText("<%(text)s>"),
        "imply": XKey("dquote:2,left"),
        "imply <text>": XText('"%(text)s"'),
        "allude": XKey("squote:2,left"),
        "allude <text>": XText("'%(text)s'"),
        "apropos" : XKey("m-x") + XText("apropos") + XKey("enter"),
        "apropos <text>" : XKey("m-x") + XText("apropos") + XKey("enter") + XText("%(text)s") + XKey("enter"),
        "describe function" : XKey("m-x") + XText("describe-function") + XKey("enter"),
        "describe variable" : XKey("m-x") + XText("describe-variable") + XKey("enter"),
        "clear": XKey("c-l"),
        "text mode" : XKey("m-x") + XText("text-mode") + XKey("enter"),
        "mini" : XKey("w-o"),
        "completions" : XKey("w-c"),
        "mini quit" : XKey("w-o,c-g"),
        "eval" : XKey("c-x,c-e"),
        }
    extras = [
        IntegerRef("n", 1, 20),
        Dictation("text"),
        Dictation("other"),
        ]
    defaults = {
        "n": 1,
        }

class BringEmacsRule(CompoundRule):
    spec = "bring emacs"

    def _process_recognition(self, node, extras):
        res = BringXApp('emacs').execute()
        if res == False:
            resumeServer()

class EmacsDictRule(MappingRule):
    mapping = {
        "command save": XKey("c-x,c-s"),
        "command open": XKey("c-x,c-f"),
        "command open <text>": XKey("c-x,c-f,tab:2,w-c,c-s")+XText("%(text)s"),
        "command swap": XKey("c-x,o"),
        "command buff" : XKey("c-x,b"),
        "command buff <text>" : XKey("c-x,b,c-s") + XText("%(text)s") + XKey("enter:2"),
        "command buffer" : XKey("c-x,b,enter"),
        "command fundamental mode" : XKey("m-x") + XText("fundamental-mode") + XKey("enter"),
        "command up [<n>]" : XKey("up:%(n)d"),
        "command down [<n>]" : XKey("down:%(n)d"),
        "command left [<n>]" : XKey("left:%(n)d"),
        "command right [<n>]" : XKey("right:%(n)d"),
        "command page [<n>]": XKey("pgdown:%(n)d"),
        "command leaf [<n>]": XKey("pgup:%(n)d"),
        "command page right": XKey("ca-v"),
        "command leaf right": XKey("cas-v"),
        "command top" : XKey("c-home"),
        "command bottom" : XKey("m-rangle"),
        "command top right" : XKey("m-home"),
        "command bottom right" : XKey("m-end"),
        "command word [<n>]" :  XKey("c-u,%(n)d,a-f"),
        "command vow [<n>]" :  XKey("c-u,%(n)d,a-b"),
        "command del [<n>]" : XKey("del:%(n)d"),
        "command rub [<n>]": XKey("backspace:%(n)d"),
        "command kill [<n>]": XKey("c-u,%(n)d,c-k"),
        "command slay [<n>]": XKey("c-u,%(n)d,a-d"),
        "command snuff [<n>]": XKey("c-u,%(n)d,a-backspace"),
        "command yank": XKey("c-y"),
        "command undo [<n>]" :  XKey("c-u,%(n)d,c-slash"),
        "command cast" : XKey("m-x"),
        "shank <text>": XText("%(text)s"),
        "<text>" : XText("%(text)s"),
        }
    extras = [
        IntegerRef("n", 1, 20),                
        Dictation("text"),
        ]
    defaults = {
        "n": 1,
        }

class EmacsMinibufRule(MappingRule):
    mapping = {
        "complete" : XKey("w-m"),
        }
    
#####################################
# readline
#####################################

## readline grammar
class ReadLineRule(MappingRule):
    mapping = {
        "up [<n>]" : XKey("up:%(n)d"),
        "down [<n>]" : XKey("down:%(n)d"),
        "left [<n>]" : XKey("left:%(n)d"),
        "right [<n>]" : XKey("right:%(n)d"),
        "page [<n>]": XKey("pgdown:%(n)d"),
        "leaf [<n>]": XKey("pgup:%(n)d"),
        "tab [<n>]" : XKey("tab:%(n)d"),
        "top" : XKey("m-langle"),
        "bottom" : XKey("m-rangle"),
        "word [<n>]" :  XKey("a-f:%(n)d"),
        "vow [<n>]" :  XKey("a-b:%(n)d"),
        "del [<n>]" : XKey("del:%(n)d"),
        "rub [<n>]": XKey("backspace:%(n)d"),
        "kill": XKey("c-k"),
        "whack": XKey("c-u"),
        "slay [<n>]": XKey("a-d:%(n)d"),
        "snuff [<n>]": XKey("a-backspace:%(n)d"),
        "yank": XKey("c-y"),
        "pull [<n>]": XKey("m-y:%(n)d"),
        "mark": XKey("c-space"),
        "pinch": XKey("m-w"),
        "swipe": XKey("c-space,c-e,m-w"),
        "lift": XKey("c-w"),
        "quit": XKey("c-g"), 
        "undo [<n>]" :  XKey("c-slash:%(n)d"),
        "find" : XKey("c-s"),
        "find <text>" : XKey("c-s") + XText("%(text)s"),
        "scout" : XKey("c-r"),
        "scout <text>" : XKey("c-r") + XText("%(text)s"),
        "macro start" : XKey("c-x,lparen"),
        "macro end" : XKey("c-x,rparen"),
        "macro do" : XKey("c-x,e"),
        "get": XKey("a-slash"),
        "yes": XText("yes") + XKey("enter"),
        "no": XText("no") + XKey("enter"),
        "clamp": XKey("lbracket,rbracket,left"),
        "clamp <text>": XText("[%(text)s]"),
        "fix": XKey("lparen,rparen,left"),
        "fix <text>": XText("(%(text)s)"),
        "brace": XKey("lbrace,rbrace,left"),
        "brace <text>": XText("{%(text)s}"),
        "angle": XKey("langle,rangle,left"),
        "angle <text>": XText("<%(text)s>"),
        "imply": XKey("dquote:2,left"),
        "imply <text>": XText('"%(text)s"'),
        "allude": XKey("squote:2,left"),
        "allude <text>": XText("'%(text)s'"),
        "clear": XKey("c-l"),
        "log out": XKey("c-d"),
        "break": XKey("c-c"),
        }
    extras = [
        IntegerRef("n", 1, 20),
        Dictation("text"),
        ]
    defaults = {
        "n": 1,
        }


#####################################
# bash
#####################################

class BashRule(MappingRule):
    mapping = {
        'seedy' : XText('cd'),
        'seedy <dest> done' : XText('cd %(text)s') + XKey('enter'),
        'pause' : XKey('c-z'),
        'resume' : XText('fg'),
        'resume done' : XText('fg') + XKey('enter'), 
        'ground' : XText('bg'),
        'ground done' : XText('bg') + XKey('enter'),
        'help' : XText('help'),
        'help done' : XText('help') + XKey('enter'),     
        'list'  : XText('ls'),
        'offer' : XKey('m-question'),
        'give' : XKey('c-m-a'),
        'dump' : XKey('m-star'),
        'basket' : XKey('m-{'),
        'variable' : XKey('m-$'),
        'move' : XText('mv'),
        'parent' : XText('../'),
        'erase' : XText('rm'),
        }
    
## construct one grammar to rule them all
xcon = XAppContext()
grammar = Grammar("Damselfly")
grammar.add_rule(ConnectRule())                     
grammar.add_rule(DisconnectRule())
grammar.add_rule(ResumeRule())
grammar.add_rule(DNSOverride())
grammar.add_rule(WMRule(context = xcon))

## charkey grammar
charContext = XAppContext("(emacs(?![^:].*:Text)|xterm)", usereg = True)
grammar.add_rule(CharkeyRule(context = charContext))

## emacs grammar
emacsContext = XAppContext('emacs(?![^:].*:Text)', usereg = True)
grammar.add_rule(EmacsEditRule(context=emacsContext))
grammar.add_rule(BringEmacsRule(context = xcon))

emacsDictContext = XAppContext('emacs:[^:].*:Text', usereg = True)
grammar.add_rule(EmacsDictRule(context = emacsDictContext))

emacsMinibufContext = XAppContext('emacs: \*Minibuf-[0-9]+\*:', usereg = True)
grammar.add_rule(EmacsMinibufRule(context = emacsMinibufContext))

## readline grammar
rlContext = XAppContext("xterm")
grammar.add_rule(ReadLineRule(context = rlContext))

## bash grammar
##rlContext = XAppContext("xterm")
##grammar.add_rule(BashRule(context = rlContext))

def unload():
    global xcon, charContext, emacsContext, emacsDictContext
    global emacsMinibufContext, rlContext, windowCache

    disconnect()

    ## does this suffice?
    xcon = None
    charContext = None

    emacsContext = None
    emacsDictContext = None
    emacsMinibufContext = None

    rlContext = None

    windowCache = None
    
    if grammar.loaded:
        grammar.unload()


grammar.load()                                   
