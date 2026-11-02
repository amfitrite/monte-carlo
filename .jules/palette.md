## 2024-05-30 - Tkinter interactive widgets missing focus ring
**Learning:** By default, some Tkinter widgets configured with `relief=tk.FLAT` lack a visible keyboard focus ring.
**Action:** When creating Tkinter apps or acting as Palette, ensure `highlightthickness=1`, `highlightbackground`, and `highlightcolor` are set on interactive elements with `relief=tk.FLAT`.
## 2026-11-02 - Tkinter FLAT Buttons Accessibility
**Learning:** Found an accessibility pattern specific to Tkinter: custom buttons using `relief=tk.FLAT` in bottom docks or menus do not show keyboard focus by default, which makes it impossible to navigate via Tab key effectively without them.
**Action:** Always add explicit focus properties (`highlightthickness=1`, `highlightbackground`, and `highlightcolor`) to any clickable element using `tk.FLAT` to maintain visual aesthetics while supporting standard keyboard navigation.
