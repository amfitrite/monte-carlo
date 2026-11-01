## 2024-05-30 - Tkinter interactive widgets missing focus ring
**Learning:** By default, some Tkinter widgets configured with `relief=tk.FLAT` lack a visible keyboard focus ring.
**Action:** When creating Tkinter apps or acting as Palette, ensure `highlightthickness=1`, `highlightbackground`, and `highlightcolor` are set on interactive elements with `relief=tk.FLAT`.
