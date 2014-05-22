#!/usr/bin/python

from Tkinter import *

class AliasEntry:
    def __init__(self,master):
        self.name=StringVar()
        self.text=StringVar()
#
        self.namestring=None
        self.textstring=None
        self.okayclicked=False
        self.master=master
#        
        caption = "Alias name:"
        Label(master, text=caption).pack(side=LEFT)
        e = Entry(master,textvariable=self.name)
        e.pack(side=LEFT)
#
        e.focus_set()
#
        caption = "Alias text:"
        Label(master, text=caption).pack(side=LEFT)
        e = Entry(master,textvariable=self.text)
        e.pack(side=LEFT)
#
        b=Button(master, text="Okay", command=self.okay)
        b.pack(side=LEFT)
#
        b=Button(master, text="Cancel", command=master.destroy)
        b.pack(side=LEFT)
#
    def okay(self):
        self.namestring=self.name.get()
        self.textstring=self.text.get()
        self.okayclicked=True
        self.master.destroy()
                
root = Tk()
ae = AliasEntry(root)

root.wm_title("damselfly:input alias")
root.update_idletasks()

sw = root.winfo_screenwidth()
sh = root.winfo_screenheight()

w = root.winfo_reqwidth()
h = root.winfo_reqheight()

x = sw/2 - w/2
y = sh/2 - h/2
root.geometry("%dx%d+%d+%d" % (w,h,x,y))

root.mainloop()

print sendAlias
print ae.namestring
print ae.textstring
