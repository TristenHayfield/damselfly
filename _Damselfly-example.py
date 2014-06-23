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
                       Dictation, IntegerRef, Context, ActionBase, Function)

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
capslock=False
verbose=False

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
            if verbose:
                print 'Requesting X context... ',
            fpO.write('getXCtx\n')
            fpO.flush()
            if verbose:
                print 'request sent'

            xctx = []
            if verbose:
                print 'waiting for response... ',
            xctx.append(fpI.readline().strip())
            if xctx[0].startswith('Failure'):
                raise CommandFailure(xctx[0])
            xctx.append(fpI.readline().strip())
            xctx.append(int(fpI.readline().strip()))
            if verbose:
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
        self._str = u"name: " + unicode(wmname) + u", " + u"class: " + unicode(wmclass) + u", " + u"id: " + unicode(wid)


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
                    iMatch &= self.myCmp(self.wmname, ctx[0].decode("utf-8")) | self.myCmp(self.wmclass, ctx[1].decode("utf-8"))
                else:
                    if self.wmname:                   
                        iMatch &= self.myCmp(self.wmname, ctx[0].decode("utf-8"))

                    if self.wmclass:
                        iMatch &= self.myCmp(self.wmclass, ctx[1].decode("utf-8"))
                
                    
                if self.wid:
                    iMatch &= (ctx[2].decode("utf-8") == self.wid)

                return iMatch
        else :
            return False

# custom actions: prepare for the babbyscape
def dispatchAndHandle(mess):
    if connected:
        try:
            if verbose:
                print 'sending request'
            fpO.write(mess)
            fpO.flush()
            if verbose:
                print 'request sent'
                print 'waiting for response... ',
            res = fpI.readline().strip()
            if verbose:
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

class InputAlias(ActionBase):
    def __init__(self):
        ActionBase.__init__(self)

    def _execute(self, data=None):
        mymess = 'inputAlias\n'
        return(dispatchAndHandle(mymess))

## neither autoformat nor pause are considered atm
class XText(DynStrActionBase):
    def __init__(self, spec, static = False, space = True, title = False, upper = False, lower = False, camel = False, capitalize = False, replace = '', check_capslock=False):
        DynStrActionBase.__init__(self, spec = str(spec), static = static)
        self.space = space
        self.title = title
        self.upper = upper
        self.lower = lower
        self.camel = camel
        self.capitalize = capitalize
        self.replace = replace
        self.check_capslock = check_capslock

    def _parse_spec(self, spec):
        self._pspec = spec
        return self

    def _execute_events(self, events):
        global capslock
        tspec = self._pspec
        if self.check_capslock and capslock:
            tspec = tspec.upper()
        elif self.title:
            tspec = tspec.title()
        elif self.upper:
            tspec = tspec.upper()
        elif self.lower:
            tspec = tspec.lower()
        elif self.camel:
            tp = tspec.partition(' ')
            tspec = tp[0].lower() + tp[2].title()
        elif self.capitalize:
            tp = tspec.partition(' ')
            tspec = tp[0].capitalize() + tp[1] + tp[2]
            
        if not self.space:
            tspec = tspec.replace(' ',self.replace)
            
        mymess = 'sendXText\n' + tspec + '\n'
        return(dispatchAndHandle(mymess))

class DoNothing(ActionBase):
    def __init__(self, message = 'Recognition event consumed.'):
        ActionBase.__init__(self)
        self.message = message
        
    def _execute(self, data=None):
        print self.message
        return True
        
# custom grammars
class Lexicon:
    def __init__(self, words = {}, characters = {}, keywords = {}, active = False):
        self.words = words
        self.characters = characters
        self.keywords = keywords
        self.active = active

class TranslationGrammar(Grammar):
    def __init__(self, name, description=None, context=None, lexicon=None):        
        Grammar.__init__(self, name=name, description=description, context=context)
        self.lexicon=lexicon

    def enter_context(self):
        Grammar.enter_context(self)
        self.lexicon.active=True

    def exit_context(self):
        Grammar.exit_context(self)
        self.lexicon.active=False


class XTranslation(XText):
    def __init__(self, spec, static = False, space = True, title = False, upper = False, lower = False, replace = '', check_capslock=False, lexica=[]):
        XText.__init__(self, spec=spec, static=static, space=space, title=title, upper=upper, lower=lower, replace=replace, check_capslock=check_capslock)
        
        self.lexica=lexica

    def get_active(self):
        iactive=[]
        for i, v in enumerate(self.lexica):
            if v.active:
                iactive.append(i)
        return iactive

    def translate(self,text):
        lexica=self.get_active()

        if len(lexica) == 0:
            return [XText(text, check_capslock=self.check_capslock)]
        
        allsymbols=text.split()
        
        actions = []
        mode=''
        for symbol in allsymbols:
            for l in lexica:
                if symbol in self.lexica[l].words:
                    if (mode == 'word') or (mode == 'keyword'):
                        actions.append(XKey('space'))
                    actions.append(self.lexica[l].words[symbol])
                    mode = 'word'
                    break
            else:
                for l in lexica:
                    if symbol in self.lexica[l].characters:
                        if mode == 'keyword':
                            actions.append(XKey('space'))
                            
                        actions.append(self.lexica[l].characters[symbol])
                        mode = 'character'
                        break
                else:
                    for l in lexica:
                        if symbol in self.lexica[l].keywords:
                            actions.append(XKey('space'))
                            actions.append(self.lexica[l].keywords[symbol])
                            mode = 'keyword'
                            break
                    else:
                        if (mode == 'word') or (mode == 'keyword'):
                            actions.append(XKey('space'))
                        actions.append(XText(symbol, check_capslock = self.check_capslock))
                        mode = 'word'

        if (mode == 'keyword'):
            actions.append(XKey('space'))
        return actions

    def _parse_spec(self, spec):
        self._pspec = self.translate(spec)
        return self

    def _execute_events(self, events):
        for action in self._pspec:
            action.execute()
        return True

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

class IgnoreRule(MappingRule):
    mapping = {
        "<text>" : DoNothing(),
        }
    extras = [
        Dictation("text")
        ]

myIgnore = IgnoreRule()

def unignore():
    myIgnore.disable()

def ignore():
    myIgnore.enable()


class AliasRule(CompoundRule):
    spec = "damselfly alias"

    def _process_recognition(self, node, extras):
        result=InputAlias().execute()
        print 'result: ',result

def togglecapslock():
    global capslock
    capslock=not capslock

#####################################
# regular expressions
#####################################
class RegularExpressionRule(MappingRule):
    mapping = {
        "group":XKey("backslash") + XText('(') + XKey("backslash") + XText(')') + XKey("left:2"),
        "numeric":XKey("0,minus,1"),
        "return":XKey("c-q,c-j"),
        "alphanumeric":XKey("a,minus,z,A,minus,Z,0,minus,9"),
        "alphabetical":XKey("a,minus,z"),
        "alpha nautical":XKey("A,minus,Z"),
        "repeat":XKey("backslash") + XText('{') + XKey("backslash") + XText('}') + XKey("left:2"),
        "limit":XKey("backslash") + XText('<') + XKey("backslash") + XText('>') + XKey("left:2"),
        "another":XKey("backslash") + XText('|'),
        }

myRegularExpression = RegularExpressionRule()

def stopRegularExpression():
    myRegularExpression.disable()

def startRegularExpression():
    myRegularExpression.enable()
        
        
#####################################
# file
#####################################
FileDictionary = {
    "user":XText("usr/") ,
    "(bin|been)" : XText("bin/") ,
    "Lib" : XText("lib/") ,
    "et cetera" : XText("etc/") ,
    "temp" : XText("tmp/") ,
    "variable" : XText("var/") ,
    "optional" : XText("opt/") ,
    "mount" : XText("mnt/") ,
    "source" : XText("src/") ,
    "hemo" : XText("home/") ,
    "previous" : XText("../") ,
    "flat" : XText("~/") ,
    }

FileLexicon=Lexicon(characters=FileDictionary)
        
def stopfile():
    FileLexicon.active = False

def startfile():
    FileLexicon.active = True

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
CharDictionary={
        "alpha" : XText("a", check_capslock = True),
        "bravo" : XText("b", check_capslock = True),
        "Charlie" : XText("c", check_capslock = True),
        "delta" : XText("d", check_capslock = True),
        "echo" : XText("e", check_capslock = True),
        "Echo" : XText("e", check_capslock = True),
        "foxtrot" : XText("f", check_capslock = True),
        "golf" : XText("g", check_capslock = True),
        "hotel" : XText("h", check_capslock = True),
        "Hotel" : XText("h", check_capslock = True),
        "India" : XText("i", check_capslock = True),
        "Jill" : XText("j", check_capslock = True),
        "kilo" : XText("k", check_capslock = True),
        "Lima" : XText("l", check_capslock = True),
        "Mike" : XText("m", check_capslock = True),
        "nova" : XText("n", check_capslock = True),
        "Oscar" : XText("o", check_capslock = True),
        "papa" : XText("p", check_capslock = True),
        "quebec" : XText("q", check_capslock = True),
        "Romeo" : XText("r", check_capslock = True),
        "sick" : XText("s", check_capslock = True),
        "tango" : XText("t", check_capslock = True),
        "unit" : XText("u", check_capslock = True),
        "Victor" : XText("v", check_capslock = True),
        "whiskey" : XText("w", check_capslock = True),
        "xray" : XText("x", check_capslock = True),
        "x-ray" : XText("x", check_capslock = True),
        "yankee" : XText("y", check_capslock = True),
        "Yankee" : XText("y", check_capslock = True),
        "Zulu" : XText("z", check_capslock = True),
        "dot" : XText("."),
        "." : XText("."),
        "hyphen" : XText("-"),
        "dash" : XText("-"),
        "-" : XText("-"),
        "stress" : XText("_"),
        "star" : XText("*"),
        "bar" : XText("|"),
        "dollar" : XText("$"),
        "caret" : XText("^"),
        "candy" : XKey('comma'),
        "bang" : XText("!"),
        "colon" : XText(":"),
        "pound" : XText("#"),
        "tilde" : XText("~"),
        "Andy" : XText("&"),
        "Atoll" : XText("@"),
        "slash" : XText("/"),
        "/" : XText("/"),
        "lash" : XKey("backslash"),
        "quest" : XText("?"),
        "grave" : XText("`"),
        "percent" : XKey('percent'),
        "tab" : XKey("tab"),
        "space" : XKey("space"),
        "quote" : XKey("dquote"),
        "tick" : XKey("squote"),
##        "one" : XKey("1"),
        }

CharKeywords={
    "minus" : XText("-"),
    "plus" : XText("+"),
    "equals" : XText("="),
    "lesser" : XText('<'),
    "greater" : XText('>'),
    }    

CharLexicon=Lexicon(characters=CharDictionary,keywords=CharKeywords)

class CharkeyRule(MappingRule):
    mapping = {
        "home" : XKey("home"),
        "enter" : XKey("enter"),
        "semi" : XText(";"),
        "end" : XKey("end"),
        "<n>" : XText("%(n)d"),
        "brace left" : XText('{'),
        "brace right" : XText('}'),
        "pen left" : XText('('),
        "pen right" : XText(')'),
        "rack left" : XText('['),
        "rack right" : XText(']'),
        "dirk <text>" : XText("%(text)s", space = False, lower = True),
        "Cape <text>" : XText("%(text)s", space = False, upper = True),
        "bridge <text>" : XText("%(text)s", space = False, replace = '_', lower = True),
        "camel <text>" : XText("%(text)s", space = False, camel = True),
        "title <text>" : XText("%(text)s", space = False, title = True),
        "launch <text>" :  XText("%(text)s", space = True, capitalize = True),
        "defcon <text>" :  XText("%(text)s", space = False, upper = True, replace = '_'),
        "shank <text>": XText("%(text)s"),
        }
    extras = [
        Dictation("text"),
        IntegerRef("n", 0, 999999),
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
        "page other": XKey("ca-v"),
        "leaf other": XKey("cas-v"),
        "top" : XKey("c-home"),
        "bottom" : XKey("m-rangle"),
        "top other" : XKey("m-home"),
        "bottom other" : XKey("m-end"),
        "word [<n>]" :  XKey("c-u,%(n)d,a-f"),
        "vow [<n>]" :  XKey("c-u,%(n)d,a-b"),
        "skip [<n>]" :  XKey("c-u,%(n)d,ca-f"),
        "creep [<n>]" :  XKey("c-u,%(n)d,ca-b"),
        "hence [<n>]" :  XKey("c-u,%(n)d,a-e"),
        "whence [<n>]" :  XKey("c-u,%(n)d,a-a"),
        "skulk" :  XKey("c-r,comma,enter"),
        "skulk <n>" :  XKey("c-r,comma,c-r:%(n)d,enter"),
        "slink" :  XKey("c-s,comma,enter"),
        "slink <n>" :  XKey("c-s,comma,c-s:%(n)d,enter"),
        "del [<n>]" : XKey("del:%(n)d"),
        "rub [<n>]": XKey("backspace:%(n)d"),
        "kill": XKey("c-k"),
        "kill <n>": XKey("c-u,%(n)d,c-k"),
        "kill line": XKey("home,c-k"),
        "slay [<n>]": XKey("c-u,%(n)d,a-d"),
        "snuff [<n>]": XKey("c-u,%(n)d,a-backspace"),
        "yank": XKey("c-y"),
        "pull [<n>]": XKey("c-u,%(n)d,m-y"),
        "cram": XKey("end,enter,c-y"),
        "wedge": XKey("up,end,enter,c-y"),
        "save": XKey("c-x,c-s"),
        "open": XKey("c-x,c-f"),
        "open <text>": XKey("c-x,c-f,tab:2,w-c,c-s")+XText("%(text)s") ,
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
        "grab": XKey("c-space,a-f,m-w"),
        "lift": XKey("c-w"),
        "quit": XKey("c-g"), #+ XText("keyboard-quit")  + XKey("enter"),
        "solo": XKey("c-x,1"),
        "limbo" : XKey("c-x,2"),
        "split" : XKey("c-x,3"),
        "goto" : XKey("m-g,g"),
        "goto <l>" : XKey("m-g,g") + XText("%(l)d") + XKey("enter"),
        "undo [<n>]" :  XKey("c-u,%(n)d,c-slash"),
        "exit stage": XKey("c-x,c-c"),
        "find" : XKey("c-s"),
        "find flip" : XKey("pgdown,c-s:2"),
        "find yank" : XKey("c-s,c-y"),
        "find again" : XKey("c-s,c-s"),
        "find <text>" : XKey("c-s") + XText("%(text)s", lower=True),
        "scout" : XKey("c-r"),
        "scout flip" : XKey("pgup,c-r:2"),
        "scout yank" : XKey("c-r,c-y"),
        "scout again" : XKey("c-r,c-r"),
        "scout <text>" : XKey("c-r") + XText("%(text)s", lower=True),
        "hunt" : XKey("ca-s"),
        "hunt flip" : XKey("pgdown,ca-s:2"),
        "hunt again" : XKey("ca-s:2"),
        "track": XKey("cm-r"),
        "track flip" : XKey("pgup,cm-r:2"),
        "track again": XKey("cm-r:2"),
        "grill": XKey("m-percent"),
        "grill <text>": XKey("m-percent") + XText("%(text)s"),
        "grill <text> with <other>" : XKey("m-percent") + XText("%(text)s") + XKey("enter") + XText("%(other)s")+ XKey("enter"),
        "query": XKey("cm-percent"),
        "transmute" : XKey("m-x") + XText("replace-regexp") + XKey("enter"),
        "sub" : XKey("m-x") + XText("replace-string") + XKey("enter"),
        "sub <text> with <other>" : XKey("m-x") + XText("replace-string") + XKey("enter") + XText("%(text)s") + XKey("enter") + XText("%(other)s")+ XKey("enter"),
        "sub <text> with yank" : XKey("m-x") + XText("replace-string") + XKey("enter") + XText("%(text)s") + XKey("enter,c-y,enter"),
        "manual" : XKey("m-x") + XText("man") + XKey("enter"),
        "manual <text>" : XKey("m-x") + XText("man") + XKey("enter") + XText("%(text)s"),
        "macro start" : XKey("c-x,lparen"),
        "macro end" : XKey("c-x,rparen"),
        "macro do" : XKey("c-x,e"),
        "macro <n>" : XKey("c-u") + XText("%(n)d") + XKey("c-x,e"),
        "macro insert" : XKey("m-x") + XText("insert-kbd-macro") + XKey("enter"),
        "macro insert <text>" : XKey("m-x") + XText("insert-kbd-macro") + XKey("enter") + XText("%(text)s") + XKey("enter"),
        "macro name" : XKey("c-x,c-k,n"),
        "macro name <text>" : XKey("c-x,c-k,n") + XText("%(text)s") + XKey("enter"),
        "tap": XText("e"),
        "scavenge" : XKey("m-x,g,r,e,p,enter"),
        "man" : XKey("m-x,m,a,n,enter"),
        "man" : XKey("m-x,m,a,n,enter") + XText("%(text)s") + XKey("enter"),
        "cast" : XKey("m-x"),
        "cast <n>" : XKey("c-u") + XText("%(n)d") + XKey("m-x"),
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
        "big yes": XText("yes") + XKey("enter"),
        "big no": XText("no") + XKey("enter"),
        "yep": XKey("c-x,z"),
        "tweak": XKey("c-t"),
        "twiddle": XKey("a-t"),        
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
        "apropos <text>" : XKey("m-x") + XText("apropos") + XKey("enter") + XText("%(text)s", space=False, replace="-") + XKey("enter"),
        "describe function" : XKey("m-x") + XText("describe-function") + XKey("enter"),
        "describe variable" : XKey("m-x") + XText("describe-variable") + XKey("enter"),
        "clear": XKey("c-l"),
        "text mode" : XKey("m-x") + XText("text-mode") + XKey("enter"),
        "mini" : XKey("w-o"),
        "completions" : XKey("w-c"),
        "mini quit" : XKey("w-o,c-g"),
        "up case" : XKey("c-x,c-u"),
        "lower case" : XKey("c-x,c-l"),
        "evaluate" : XKey("c-x,c-e"),
        "determine" : XKey("c-u,c-x,c-e"),
        "edit" : XKey("a-e"),
        "alter" : XKey("a-p:2"),
        "reap" : XKey("a-p"),
        "sickle" : XKey("a-n"),
        "sensitive" : XKey("a-c"),
        "confirm" : XKey("y"),
        "deny" : XKey("n"),
        "begin":XKey("m-x")  + XText("goto-first-nonblank") + XKey("enter"),
        }
    extras = [
        IntegerRef("n", 1, 99),
        IntegerRef("l", 0, 99999),
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

class StartConsoleRule(CompoundRule):            
    spec = "start console"

    def _process_recognition(self, node, extras):
        res = StartXApp('konsole').execute()
        if res == False:
            resumeServer()

class EmacsDictRule(MappingRule):
    mapping = {
        "command save": XKey("c-x,c-s"),
        "command open": XKey("c-x,c-f"),
        "command open <text>": XKey("c-x,c-f,tab:2,w-c,c-s")+XText("%(text)s"),
        "command swap": XKey("c-x,o"),
        "command split" : XKey("c-x,3"),
        "command buff" : XKey("c-x,b"),
        "command buff <text>" : XKey("c-x,b,c-s") + XText("%(text)s") + XKey("enter:2"),
        "command buffer" : XKey("c-x,b,enter"),
        "command fundamental mode" : XKey("m-x") + XText("fundamental-mode") + XKey("enter"),
        "command home" : XKey("home"),
        "command end" : XKey("end"),
        "command enter" : XKey("enter"),
        "command up [<n>]" : XKey("up:%(n)d"),
        "command down [<n>]" : XKey("down:%(n)d"),
        "command left [<n>]" : XKey("left:%(n)d"),
        "command right [<n>]" : XKey("right:%(n)d"),
        "command page [<n>]": XKey("pgdown:%(n)d"),
        "command leaf [<n>]": XKey("pgup:%(n)d"),
        "command page other": XKey("ca-v"),
        "command leaf other": XKey("cas-v"),
        "command top" : XKey("c-home"),
        "command bottom" : XKey("m-rangle"),
        "command top other" : XKey("m-home"),
        "command bottom other" : XKey("m-end"),
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
        "up case" : XKey("a-c"),
        "shank <text>": XText("%(text)s")+XKey("space"),
        "<text>" : XText("%(text)s")+XKey("space"),
        }
    extras = [
        IntegerRef("n", 1, 99),                
        Dictation("text"),
        ]
    defaults = {
        "n": 1,
        }

class EmacsMinibufRule(MappingRule):
    mapping = {
        "complete" : XKey("w-m"),
        }

#######################################
## R : R rules
#######################################

rLanguageWords = {
    "null" : XText("NULL"),
    "true" : XText("TRUE"),
    "false" : XText("FALSE"),
    "N/A" : XText("NA"),
    }

rLanguageKeywords = {
    "assign" : XText("<-"),
    "equality" : XText("=="),
    "biggish" : XText(">="),
    "smallish" : XText("<="),
    "inequality" : XText("!="),
    "simultaneous" : XText("&&"),
    "alternative" : XText("||"),
    "in" : XText("in"),
    }

rLanguageLexicon = Lexicon(words = rLanguageWords, keywords = rLanguageKeywords)

class RLanguageRule(MappingRule):
    mapping = {
        "comment":XText("##") + XKey("space"),
        "block" : XKey("lbrace,home,down,enter,up,rbrace,home,enter,up,tab"),
        "bind" : XText("c()") + XKey("left"),
        "stop" : XText('stop("")') + XKey("left:2"),
        "stop if not" : XText("stopifnot()") + XKey("left"),
        "browser" : XText("browser()") + XKey("left"),
        "missing" : XText("missing()") + XKey("left"),
        "debug" : XText("debug()") + XKey("left"),
        "data frame" : XText("data.frame()") + XKey("left"),
        "library" : XText("library()") + XKey("left"),
        "exit" : XText("quit()"),
        "exit stage" : XText("quit()") + XKey("enter,n,enter"),
        "if" : XText("if()") + XKey("left"),
        "if block" : XText("if()") + XKey("lbrace,home,down,enter,up,rbrace,home,enter,up,tab,up,right"),
        "fear" : XText("for()") + XKey("left"),
        "fear block" : XText("for() ") + XKey("lbrace,home,down,enter,up,rbrace,home,enter,up,tab,up,right:2"),
        "while" : XText("while()") + XKey("left"),
        "while block" : XText("while() ") + XKey("lbrace,home,down,enter,up,rbrace,home,enter,up,tab"),
        "columns" : XText("ncol()") + XKey("left"),
        "rose" : XText("nrows()") + XKey("left"),
        "return" : XText("return"),
        }
        
#######################################
## Python : Python rules
#######################################

pythonWords = {
    "else" : XText("else:"),
    "fear" : XText("for"),
    "print" : XText("print"),
    "global" : XText("global"),
    "try" : XText("try:"),
    "none" : XText("None"),
    "true" : XText("True"),
    "false" : XText("False"),
    }

pythonCharacters = {
    "invoke" : XText("()"),
    }
    
pythonKeywords = {
    "grow" : XText("+="),
    "shrink" : XText("-="),
    "equality" : XText("=="),
    }

pythonLexicon = Lexicon(words = pythonWords, keywords = pythonKeywords, characters = pythonCharacters)        
         
class PythonLanguageRule(MappingRule):
    mapping = {
        "class" : XText("class "),
        "class <text>" : XText("class") + XKey('space') + XText("%(text)s:",space = False, title = True),
        "class <text> inherits <name>" : XText("class") + XKey('space') + XText("%(text)s(%(name)s):",space = False, title = True),
        "constructor" : XText("__init__(self)"),
        "define constructor" : XText("def __init__(self,):")  + XKey("left:2"),
        "define" : XText("def"),
        "define <text>" : XText("def")+ XKey('space') + XText("%(text)s():",space=False) + XKey("left:2"),
        "define method <text>" : XText("def %(text)s(self,):",camel = True) + XKey("left:2"),
        "else if" : XText("elif:"),
        "else if <text>" : XText("elif %(text)s:"),
        "if" : XText("if") + XKey('space'),
        "if <text>" : XText("if %(text)s:"),
        "import" : XText("import") + XKey('space'),
        "import <text>" : XText("import %(text)s"),
        "import all": XText("from  import *") + XKey("left:9"),
        "from <text> import <name>" : XText("from %(text)s import ") + XText("(%(name)s)",space = False, title = True),
        "comment" : XText("##") + XKey('space'),
        "comment <text>" : XText("## %(text)s"),
        "promote":XKey("c-c,c-r"),
        "demote":XKey("c-c,c-l"),
        "burgle":XKey("ca-h,a-w"),
        }
    extras = [
        Dictation("text"),
        Dictation("name"),
        ]


                        
#######################################
## LaTeX : LaTeX rules
#######################################
class LatexRule(MappingRule):
    mapping = {
        "habitat <text>" : XKey("backslash") + XText("begin{%(text)s}") + XKey("enter,home,backslash") + XText("end{%(text)s}"),
        "itemize":XKey("home,backslash") + XText("item") + XKey("space"),
        "caption":XKey("backslash") + XText("caption{}") + XKey("left"),
        "centering":XKey("backslash") + XText("centering"),
        "subsection" : XKey("backslash") + XText("subsection{}") + XKey("left"),
        "subsection <text>" : XKey("backslash") + XText("subsection{%(text)s}"),
        "sub subsection" : XKey("backslash") + XText("subsubsection{}") + XKey("left"),
        "sub subsection <text>" : XKey("backslash") + XText("subsubsection{%(text)s}"),
        "section" : XKey("backslash") + XText("section{}") + XKey("left"),
        "section <text>" : XKey("backslash") + XText("section{%(text)s}"),
        "use package" : XKey("backslash") + XText("usepackage{}") + XKey("left"),
        "use package <text>" : XKey("backslash") + XText("usepackage{%(text)s}") + XKey("left"),
        "author" : XKey("backslash") + XText("author{}") + XKey("left"),
        "document class": XKey("backslash") + XText("documentclass[]{}") + XKey("left"),
        "new command" : XKey("backslash") + XText("newcommand{}{}") + XKey("left:3"),
        "new chunk" : XText("<<>>=") + XKey("left:3"),
        "code chunk" : XText("<<>>") + XKey("left:2"),
        "comment" : XKey("percent:2,space"),
        "bold font" : XKey("backslash,b,f,space"),
        "italic font" : XKey("backslash,i,t,space"),
        "emphasize font" : XKey("backslash,e,m,space"),
        "new label" : XKey("backslash,l,a,b,e,l,lbrace,rbrace,left"),
        "sex" : XKey("backslash,S,e,x,p,r,lbrace,rbrace,left"),
        "reference" : XKey("backslash,r,e,f,lbrace,rbrace,left"),
        "M dash" : XKey("hyphen:3"),
        "N dash" : XKey("hyphen:2"),
        "Quad" : XKey("backslash,q,u,a,d"),
        "new line" : XKey("backslash:2"),
        "Q quad" : XKey("backslash,q,q,u,a,d"),
        "new label <text>" : XKey("backslash") + XText("label{%(text)s}"),
        "math mode": XKey("dollar:2,left"),
        "math bold": XKey("backslash,m,a,t,h,b,f,lbrace,rbrace,left"),
        "math italic": XKey("backslash,m,a,t,h,i,t,lbrace,rbrace,left"),
        "math Roman": XKey("backslash,m,a,t,h,r,m,lbrace,rbrace,left"),
        "bounce" :  XKey("c-s,dollar,enter"),
        "bounce <n>" :  XKey("c-s,dollar,c-s:%(n)d,enter"),
        "rebound" :  XKey("c-r,dollar,enter"),
        "rebound <n>" :  XKey("c-r,dollar,c-r:%(n)d,enter"),
        }
    extras = [
        IntegerRef("n", 1, 99),                
        Dictation("text"),
        ]
    defaults = {
        "n": 1,
        }


#######################################
## LaTeX equations : LaTeX equations rules
#######################################
class LatexEquationRule(MappingRule):
    mapping = {
        "fraction": XKey("backslash,f,r,a,c,lbrace,rbrace,lbrace,rbrace,left:3"),
        "summation": XKey("backslash,s,u,m"),
        "product": XKey("backslash,p,r,o,d"),
        "logarithm": XKey("backslash,l,o,g"),
        "integral": XKey("backslash,i,n,t"),
        "square root": XKey("backslash,s,q,r,t,lbrace,rbrace,left"),
        "squared": XKey("caret,2"),
        "cubed": XKey("caret,3"),
        "arrange": XKey("ampersand,equal"),
        "group": XKey("backslash,l,e,f,t,lparen,backslash,r,i,g,h,t,rparen,left:7"),
        "group left": XKey("backslash,l,e,f,t,lparen"),
        "group right": XKey("backslash,r,i,g,h,t,rparen"),
        "natural logarithm": XKey("backslash,l,n"),
        "Sigma": XKey("backslash,s,i,g,m,a"),
        "dolt": XKey("backslash,d,e,l,t,a"),
        "equivalent": XKey("backslash,e,q,u,i,v"),
        "similar": XKey("backslash,s,i,m"),
        "approximately": XKey("backslash,s,i,m,e,q"),
        }


myLatexEquation = LatexEquationRule()

def stopLatexEquation():
    myLatexEquation.disable()

def startLatexEquation():
    myLatexEquation.enable()
        
#######################################
## C : C language emacs rules
#######################################
cLanguageKeywords = {
    "grow" : XText("+="),
    "shrink" : XText("-="),
    "scale" : XText("*="),
    "dilate" : XText("/="),
    "equality" : XText("=="),
    "biggish" : XText(">="),
    "smallish" : XText("<="),
    "inequality" : XText("!="),
    "simultaneous" : XText("&&"),
    "alternative" : XText("||"),
    }

cLanguageWords = {
    "null" : XText("NULL"),
    "void" : XText("void"),
    "double" : XText("double"),
    "float" : XText("float"),
    "constant" : XText("const"),
    "integer" : XText("int"),
    }    

cLanguageCharacters = {
    "increment" : XText("++"),
    "decrement" : XText("--"),
    }

cLanguageLexicon = Lexicon(words = cLanguageWords, keywords = cLanguageKeywords, characters = cLanguageCharacters)           
class CLanguageRule(MappingRule):
    mapping = {
        "block" : XKey("lbrace,home,down,enter,up,rbrace,home,enter,up,tab"),
        "else" : XText("else"),
        "else block" : XText("else ") + XKey("lbrace,home,down,enter,up,rbrace,home,enter,up,tab"),
        "else if" : XText("else if()") + XKey("left"),
        "else if block" : XText("else if()") + XKey("lbrace,home,down,enter,up,rbrace,home,enter,up,tab,a-f:2,right"),
        "if" : XText("if()") + XKey("left"),
        "if block" : XText("if()") + XKey("lbrace,home,down,enter,up,rbrace,home,enter,up,tab,up,right"),
        "fear" : XText("for(;;)") + XKey("left:3"),
        "fear block" : XText("for(;;) ") + XKey("lbrace,home,down,enter,up,rbrace,home,enter,up,tab,up,right:2"),
        "while" : XText("while()") + XKey("left"),
        "while block" : XText("while() ") + XKey("lbrace,home,down,enter,up,rbrace,home,enter,up,tab"),
        "return" : XText("return"),
        "size of" : XText("sizeof()") + XKey("left"),
        "define" : XText("#define"),
        "include" : XText("#include <>") + XKey("left"),
        "comment" : XText("//"),
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
        "macro <n>" : XKey("c-u") + XText("%(n)d") + XKey("c-x,e"),
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
        "interrupt" : XKey("c-z"),
        }
    extras = [
        IntegerRef("n", 1, 99),
        Dictation("text"),
        ]
    defaults = {
        "n": 1,
        }

#####################################
# bash
#####################################
bashKeywords = {
    'CD' : XText('cd'),
    'move' : XText('mv'),
    }

bashLexicon = Lexicon(keywords = bashKeywords)

class BashRule(MappingRule):
    mapping = {
        'yo-yo' : XText('cd') + XKey('space,minus'),
        'copy' : XText('cp') + XKey('space'),
        'completions' :XKey('tab:2'),
        'pause' : XKey('c-z'),
        'resume' : XText('fg'),
        'resume done' : XText('fg') + XKey('enter'), 
        'ground' : XText('bg'),
        'ground done' : XText('bg') + XKey('enter'),
        'help' : XText('help'),
        'help done' : XText('help') + XKey('enter'),     
        'list'  : XText('ls'),
        'do list'  : XText('ls') + XKey('enter'),
        'list all'  : XText('ls -la'),
        'do list all'  : XText('ls -la') + XKey('enter'),
        'offer' : XKey('m-question'),
        'give' : XKey('c-m-a'),
        'dump' : XKey('m-star'),
        'basket' : XKey('m-{'),
        'variable' : XKey('m-$'),
        'erase' : XText('rm') + XKey('space'),
        'touch' : XText('touch') + XKey('space'),
        'touch <text>' : XText('touch %(text)s'),
        'make directory' : XText('mkdir') + XKey('space'),
        'make directory <text>' : XText('mkdir %(text)s'),
        'remove directory' : XText('rmdir') + XKey('space'),
        'remove directory <text>' : XText('rmdir %(text)s'),
        'git' : XText('git') + XKey('space'),
        'git add' : XText('git add'),
        'git add <text>' : XText('git add %(text)s'),
        'git status' : XText('git status'),
        'git check out' : XText('git checkout'),
        'git check out <text>' : XText('git checkout %(text)s'),
        'git commit' : XText('git commit'),
        'git commit all' : XText('git commit -a'),
        'git branch' : XText('git branch'),
        'git merge' : XText('git merge'),
        'git merge <text>' : XText('git merge %(text)s'),
        'git diff' : XText('git diff'),
        'git log' : XText('git log'),
        'git pull' : XText('git pull'),
        'git push' : XText('git push'),
        'untar' : XText('tar -xvf') + XKey('space'),
        'untar zip' : XText('tar -xvzf') + XKey('space'),
        'untar be zip' : XText('tar -xvjf') + XKey('space'),
        'untar L zip' : XText('tar -xvJf') + XKey('space'),
        "are" : XText("R"),
        "are command" : XText("R CMD"),
        "are command install" : XText("R CMD INSTALL"),
        "are command install <text>" : XText("R CMD INSTALL %(text)s"),
        "are command <text>" : XText("R CMD %(text)s"),
        "debug are" : XText("R -d gdb"),
        'valgrind are' : XText('R -d "valgrind --tool=memcheck --leak-check=full --vgdb=yes --vgdb-error=0"'),
        "are command batch" : XText("R CMD BATCH"),
        "are no save" : XText("R --no-save"),
        "permissions" : XText("chmod") + XKey('space'),
        "permissions set executable" : XText("chmod u+x"),
        "permissions set all executable" : XText("chmod +x"),
        "dirk <text>" : XText("%(text)s", space = False, lower = True),
        }
    extras = [
        Dictation("text"),
        ]

class GdbRule(MappingRule):
    mapping = {
        "breakpoint" : XText("b") + XKey('space'),
        "continue" : XKey("c,enter"),
        "backtrace" : XKey("b,t,enter"),
        "frame <n>" : XKey("f,space")+XText("%(n)d")+XKey("enter"),
        "print" : XText("p") + XKey('space'),
        "set" : XText("set") + XKey('space'),
        "display" : XText("display") + XKey('space'),
        "delete" : XText("delete") + XKey('space'),
        "next" : XKey("n,enter"),
        "step" : XKey("s,enter"),
        "list" : XKey("l,enter"),
        "until" : XKey("u,enter"),
        "relist" : XKey("l,space,minus,enter"),
        "terminate" : XKey("k,enter"),
        "run" : XKey("r,enter"),
        "exit" : XKey("q,enter"),
        "help" : XText("help") + XKey('space'),
        "confirm" : XKey("y,enter"),
        "deny" : XKey("n,enter"),
        "stop" : XKey("q,enter"),
        }
    extras = [
        IntegerRef("n", 0, 99),
        ]

class AcroreadRule(MappingRule):
    mapping = {
        "reload":XKey('a-f,d'),
        "open":XKey('a-f,o'),
        "fit width":XKey('a-v,z,w'),
        "fit page":XKey('a-v,z,p'),
        "find":XKey('a-e,f'),
        }
        
class DictateRule(MappingRule):
    mapping = {
        "<text>" : XTranslation("%(text)s", check_capslock = True, lexica=[CharLexicon,FileLexicon,pythonLexicon,cLanguageLexicon,bashLexicon,rLanguageLexicon]),
        }
    extras = [
        Dictation("text")
        ]

myDictate = DictateRule()

def undictate():
    myDictate.disable()

def dictate():
    myDictate.enable()
                
class ControllerRule(MappingRule):
    mapping = {
        "start ignore" : Function(ignore),
        "stop ignore" : Function(unignore),
        "dictate" : Function(unignore) + Function(dictate),
        "stop dictate" : Function(ignore) + Function(undictate),
        "start file" : Function(startfile),
        "stop file" : Function(stopfile),
        "start expression" : Function(startRegularExpression),
        "stop expression" : Function(stopRegularExpression),
        "capslock" : Function(togglecapslock),
        "start math" : Function(startLatexEquation),
        "stop math" : Function(stopLatexEquation),
        }

    
## construct one grammar to rule them all
xcon = XAppContext()
grammar = Grammar("Damselfly")
grammar.add_rule(ConnectRule())
grammar.add_rule(AliasRule())                     
grammar.add_rule(DisconnectRule())
grammar.add_rule(ResumeRule())
grammar.add_rule(ControllerRule())
grammar.add_rule(WMRule(context = xcon))

## charkey grammar
charContext = XAppContext(u"(emacs:(?![^:].*:Text)|xterm|.*: (python2.7|lisp\.run|R|gdb|bash) \u2013 Konsole$)", usereg = True)
CharGrammar=TranslationGrammar("Character", context=charContext, lexicon=CharLexicon)
CharGrammar.add_rule(CharkeyRule())
CharGrammar.load()

#grammar.add_rule(CharkeyRule(context = charContext))

## emacs grammar
emacsContext = XAppContext('emacs:(?![^:].*:Text)', usereg = True)
grammar.add_rule(EmacsEditRule(context=emacsContext))
grammar.add_rule(BringEmacsRule(context = xcon))
grammar.add_rule(StartConsoleRule(context = xcon))

emacsLatexContext = XAppContext('emacs:[^:].*:LaTeX$', usereg = True)
grammar.add_rule(LatexRule(context = emacsLatexContext))

emacsCContext = XAppContext('emacs:[^:].*:C/l$', usereg = True)
cLanguageGrammar = TranslationGrammar("CLanguage", context=emacsCContext, lexicon=cLanguageLexicon)
cLanguageGrammar.add_rule(CLanguageRule())
cLanguageGrammar.load()

emacsRContext = XAppContext(u'(emacs:[^:].*:ESS\[S\]$|.*: R \u2013 Konsole$)', usereg = True)
rLanguageGrammar = TranslationGrammar("RLanguage", context=emacsRContext, lexicon=rLanguageLexicon)
rLanguageGrammar.add_rule(RLanguageRule())
rLanguageGrammar.load()

emacsDictContext = XAppContext('emacs:[^:].*:Text', usereg = True)
grammar.add_rule(EmacsDictRule(context = emacsDictContext))

emacsMinibufContext = XAppContext('emacs: \*Minibuf-[0-9]+\*:', usereg = True)
grammar.add_rule(EmacsMinibufRule(context = emacsMinibufContext))

## readline grammar
rlContext = XAppContext(u"(xterm|.*: (python2.7|lisp\.run|R|gdb|bash) \u2013 Konsole$)", usereg = True)
grammar.add_rule(ReadLineRule(context = rlContext))

## bash grammar
bashContext = XAppContext(u'(emacs:[^:].*:Shell|xterm|.*: bash \u2013 Konsole$)', usereg = True)
bashGrammar = TranslationGrammar("Bash", context=bashContext, lexicon=bashLexicon)
bashGrammar.add_rule(BashRule())
bashGrammar.load()

## gdb grammar
GdbContext = XAppContext(u'gdb \u2013 Konsole$', usereg = True)
grammar.add_rule(GdbRule(context =GdbContext))

## acroread grammar
acroreadContext = XAppContext(wmclass = 'acroread')
grammar.add_rule(AcroreadRule(context = acroreadContext))

pythonEmacsContext = XAppContext('emacs:[^:].*:Py', usereg = True)
pythonGrammar = TranslationGrammar("Python", context=pythonEmacsContext, lexicon=pythonLexicon)
pythonGrammar.add_rule(PythonLanguageRule())
pythonGrammar.load()

grammar.add_rule(DNSOverride())

#myDictate.disable()

def unload():
    global xcon, charContext, emacsContext, emacsDictContext, emacsCContext
    global emacsMinibufContext, rlContext, windowCache

    disconnect()

    ## does this suffice?
    xcon = None
    charContext = None

    emacsContext = None
    emacsCContext = None
    emacsDictContext = None
    emacsMinibufContext = None

    rlContext = None

    windowCache = None
    
    if grammar.loaded:
        grammar.unload()

myRegularExpression.disable()
grammar.add_rule(myRegularExpression)

myLatexEquation.disable()
grammar.add_rule(myLatexEquation)

myDictate.disable()
grammar.add_rule(myDictate)

grammar.add_rule(myIgnore)
grammar.load()                                   


