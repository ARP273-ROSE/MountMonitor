# Tests

```
pip install pytest
python -m pytest tests/ -q
```

`test_tracking_analysis.py` replays a synthetic session whose **ground truth is
known** — two targets 14.7° apart, a jitter of 0.26″ RMS, a drift of −5.65″/h, a
periodic error of 1.5″ at 8 minutes — and checks that the report recovers them.

A last test replays the **real session** that triggered all this. The file
`Logs/MountMonitor_20260921-220015.dat` is not versioned (`Logs/` is in
`.gitignore`, and it weighs 9.5 MB): the test is *skipped* when it is absent. To
run it, put the file at that location.

These tests exist because a real 8 h 30 session was rated **BAD** with a
combined RMS of 86″, while the jitter was **0.179″**. Five causes:

1. segmentation looked for a **jump** between consecutive samples; a slew being a
   continuous movement, no jump was ever large enough, and two targets fell into
   a single segment whose median sat between them;
2. samples taken **during** a slew entered the statistics;
3. the RMS mixed the **slow drift** with the **jitter**, whereas a 5″/h drift
   moves a star by only 0.28″ during a 180 s exposure and every dither cancels it;
4. the **FFT** worked on the raw deviations: the drift produced a false
   "dominant peak" there that hid the real periodic error;
5. 🔴 **the jitter was measured by removing a straight line, whereas the signal
   is a staircase.** Between two exposures the sequencer dithers and the mount
   *stays* on its new step. Removing a line does not remove a staircase: 9.1″ of
   "jitter" remained on the real session, while the mount held each step to
   **0.12″**. Jitter is now measured **between repositionings**.
