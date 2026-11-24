# Desktop check

Before trusting 3Dmodeling on a new computer (or after updating Windows, macOS, the
graphics driver or the app), run the desktop check. It takes about five minutes: half a
minute for the automatic part, the rest for the checks only a person can do.

## 1. The automatic part

Open a terminal (on Windows: PowerShell) and run:

```text
python -m modeler desktop-check
```

With the installed app instead of Python, use the app's command-line program in the
install folder: `3Dmodeling-cli.exe desktop-check` on Windows, or
`/Applications/3Dmodeling.app/Contents/MacOS/3Dmodeling-cli desktop-check` on macOS.

A window opens and works by itself for about half a minute. It checks that:

| Step | What goes wrong on some computers |
|------|-----------------------------------|
| the window opens and the 3D view starts | no OpenGL driver, or a remote desktop without one |
| a model is built and drawn | a black or empty 3D view |
| a mouse click picks the face under it | clicks land in the wrong place when the screen is scaled (125 %, 150 %, Retina) |
| dragging turns the view, the wheel zooms | mouse or touchpad events not reaching the view |
| save and open in a folder with spaces and non-English letters | file names like `Prüfung ü 文件` breaking saving |
| a drawing (PDF) and a STEP file are written there | the same, for other files |
| text is made with a font | no fonts found |
| the themes switch | the dark theme unreadable |
| the assistant panel opens | |
| a picture of the whole window | for you to look at |
| the window closes | a crash on closing |

At the end it prints where the report is: a folder with `report.md`, `report.json`,
`view.png` and `window.png`. If a step failed, open a problem report (in the app:
**Help > Report a problem**) and attach `report.md` and `window.png`.

## 2. The checks by hand

Open the app normally and go down this list. Each takes a few seconds.

**The 3D view**

- [ ] Type `BLOCK, 0,0,0, 40,30,10` and press Enter: a grey block appears.
- [ ] Drag with the left mouse button: the block turns smoothly, without jumps.
- [ ] Drag with the middle or right button (or Shift + left): the view pans.
- [ ] Turn the mouse wheel (or pinch on a touchpad): the view zooms where the mouse is.
- [ ] Click a face: it turns orange and `PICK, FACE, n` appears in History.
- [ ] Move the window to a second screen with a different scaling, if you have one, and
      click a face again: the face under the mouse is picked, not one beside it.
- [ ] Make the window full screen and back: the view redraws at the new size.

**Files**

- [ ] **File > Save** shows your system's save dialog; save into Documents.
- [ ] Close the app, then double-click the saved `.m3d` file (with the installed app):
      it opens with the model.
- [ ] **File > Import** a STEP file you have: it appears.
- [ ] **File > Export** STL and open the file in another program (a slicer or viewer).

**The rest of the window**

- [ ] **View > Preferences**: switch to the dark theme. Every panel is readable.
- [ ] Open the **Assistant** tab and sign in (if you use it): a question gets an answer.
- [ ] **Help > Command reference** (Ctrl+F1): the help opens, and searching for `FILLET`
      finds it.
- [ ] Put the computer to sleep with the app open, wake it: the 3D view still draws.

**Quitting**

- [ ] Close the app with unsaved changes: it asks whether to save.
- [ ] Start it again: no message about a crash.

If anything on this list does not work, report it with **Help > Report a problem**, say
which line, and attach the report from step 1.
