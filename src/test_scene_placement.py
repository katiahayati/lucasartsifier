"""Scene refusals sit at the CLICK that starts the hand-over, never inside the scene.

Play-found on GK1 v4 (2026-11-16, test-plan row G2): the refusal at the top of `sHRoom8`'s
state 0 ran after the hounfour's dispatcher had faded to black and disposed the hallway. The
"Not yet!" box was invisible, and dismissing it crashed the game
(`800 disposeCode::doit @ 2873: send to non-object 0000:0000`), because the dispatcher's
post-scene teardown disposed obstacles the refused scene had never added.

Source only: no model, no game install. A synthetic hallway pins the shape and the two ways it
must stay UNPLACED. The real GK1 hounfour is checked too when its decompiled source is in
`build/sweep/gk1/src`, so this test runs on a fresh checkout as well as on the box.
"""
import os
import shutil
import sys
import tempfile
import types

import patcher as P

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" -- {detail}" if detail and not cond else ""))


P._IR = types.SimpleNamespace(flag_test_proc="proc13_0",
                              flag_procs={"proc13_0": "test", "proc13_1": "set",
                                          "proc13_2": "clear"})
P.REFUSE = P._RETRACTION_FORM = "(proc64921_0 {Not yet!})"
P._EGO = 0
TITLES = {800: "Hall", 808: "sScene", 64921: "Print"}
SPEC = {"site": "scene", "room": 800, "script": 808, "machine": "sScene", "refused": [],
        "condition": "(and (gEgo has: 78) (proc13_0 351))"}

HALL = """;;; Sierra Script 1.0 - (do not remove this comment)
(script# 800)
(include sci.sh)
(use Main)

(public
	Hall 0
)

(local
	local0 = 1
	local1 = %(start)s
)

(instance Hall of Room
	(properties)

	(method (init)
		(super init:)
		(self setScript: sDispatch)%(auto)s
	)
)

(instance sDispatch of Script
	(properties)

	(method (changeState param1)
		(switch (= state param1)
			(0
				(= cycles 1)
			)
			(1
				(global1 handsOff:)
				(self setScript: (ScriptID local1 0) self local0)
			)
			(2
				(switch (global2 curLoc:)
					(7
						(= local1 808)
					)
				)
			)
		)
	)
)

(instance sOpenDoor of Script
	(properties)

	(method (changeState param1)
		(switch (= state param1)
			(0
				(global1 handsOff:)
				(= cycles 1)
			)
			(1
				(sDispatch cue:)
				(self dispose:)
			)
		)
	)
)

(instance sAuto of Script
	(properties)

	(method (changeState param1)
		(switch (= state param1)
			(0
				(sDispatch cue:)
				(self dispose:)
			)
		)
	)
)

(instance keypad of Feature
	(properties)

	(method (doVerb param1)
		(switch param1
			(8
				(theDoor setScript: sOpenDoor)
				(return 1)
			)
			(else
				(super doVerb: param1)
			)
		)
	)
)
"""


def place(text, titles=TITLES, spec=SPEC):
    d = tempfile.mkdtemp(prefix="scene_place_")
    try:
        os.makedirs(os.path.join(d, "src"))
        host = titles[spec["room"]]
        open(os.path.join(d, "src", host + ".sc"), "w").write(text)
        r = P._guard_scene(d, dict(spec), titles)
        return r, open(os.path.join(d, "src", host + ".sc")).read()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_synthetic():
    r, out = place(HALL % {"start": 806, "auto": ""})
    pl = r.get("placement") or {}
    check("synthetic: placed at the keypad, the click that starts the hand-over",
          r.get("applied") and [x["route"] for x in pl.get("routes", [])]
          == ["keypad::doVerb -> sOpenDoor"], str(r))
    check("synthetic: narrowed to THIS scene by the door's discriminator",
          pl.get("guard") == "(or (not (== local1 808)) (and (global0 has: 78) (proc13_0 351)))",
          str(pl.get("guard")))
    check("synthetic: the room's own start is refuted (it begins at scene 806), and so is a "
          "cue-er nothing arms",
          pl.get("refuted") == ["sAuto cues sDispatch but nothing arms it",
                                "Hall::init starts sDispatch with local1 = 806, not 808"],
          str(pl.get("refuted")))
    check("synthetic: the refusal is in keypad::doVerb and the Print use is added",
          out.count("(proc64921_0 {Not yet!})") == 1 and "(use Print)" in out
          and out.index("Not yet!") > out.index("(instance keypad"), out[-600:])

    r, out = place(HALL % {"start": 806, "auto": "\n\t\t(self setScript: sAuto)"})
    check("synthetic: a cue-er armed with no click (room init) leaves the row UNPLACED",
          not r.get("applied") and "sAuto is also armed from Hall::init" in (r.get("why") or "")
          and "Not yet!" not in out, str(r.get("why")))

    r, out = place(HALL % {"start": 808, "auto": ""})
    check("synthetic: a room that STARTS on the scene (no click to refuse) stays UNPLACED",
          not r.get("applied") and "Hall::init arms sDispatch" in (r.get("why") or "")
          and "Not yet!" not in out, str(r.get("why")))


def test_gk1_hounfour():
    here = os.path.dirname(os.path.abspath(__file__))
    src = os.path.join(here, "..", "build", "sweep", "gk1", "src")
    hp, sp = os.path.join(src, "Hounfour.sc"), os.path.join(src, "sHRoom8.sc")
    if not (os.path.exists(hp) and os.path.exists(sp)):
        print("  [SKIP] GK1 hounfour: no decompiled GK1 source in build/sweep/gk1/src")
        return
    titles = {800: "Hounfour", 808: "sHRoom8", 64921: "Print"}
    spec = {**SPEC, "machine": "sHRoom8",
            "condition": "(and (gEgo has: 78) (gEgo has: 79) (proc13_0 351))"}
    d = tempfile.mkdtemp(prefix="scene_place_gk1_")
    try:
        os.makedirs(os.path.join(d, "src"))
        shutil.copy(hp, os.path.join(d, "src"))
        shutil.copy(sp, os.path.join(d, "src"))
        r = P._guard_scene(d, dict(spec), titles)
        pl = r.get("placement") or {}
        check("GK1: Grace's room is refused at the hallway keypad, both its verbs",
              r.get("applied") and r.get("title") == "Hounfour"
              and sorted(x["route"] for x in pl.get("routes", []))
              == ["keypad::doVerb -> sOpenDoor", "keypad::doVerb -> sUnlockDoor"], str(r))
        check("GK1: the hounfour's own start is refuted (it begins at the elevator lobby, 806)",
              pl.get("refuted") == ["Hounfour::init starts sMainHallways with local1 = 806, "
                                    "not 808"], str(pl.get("refuted")))
        check("GK1: sHRoom8 itself is left untouched",
              open(os.path.join(d, "src", "sHRoom8.sc"), "rb").read() == open(sp, "rb").read())
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    test_synthetic()
    test_gk1_hounfour()
    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)
