# SkellForge Windows QA handoff

November 16, 2026. [Draft PR #27](https://github.com/skellyruno/skellforge/pull/27) follows the experimental generated Gain branch. Tested code is `22c8018b592c19a09f1bc6f0bcfa0c6957576972`. The pinned local Steinberg SDK now configures correctly, and the native pilot CLI rejects build paths inside or above its source checkout.

The Windows Python suite discovered 95 tests, with 4 skips. QZ92 built locally and passed the official validator. A second generated project, QZ93, had distinct factory IDs. The exact PR #25 CLI rebuilt and ran the registered Mini and Spacer checks. PR #7 Studio generation, compiled JUCE editor preview, DSP smoke, and packaging passed locally with JUCE 8.0.12 and pinned SkellCore. [Generated Gain CI](https://github.com/skellyruno/skellforge/actions/runs/43809729094), [legacy VST3 CI](https://github.com/skellyruno/skellforge/actions/runs/43809729085)

See the [SkellNative handoff and draft PR](https://github.com/skellyruno/skellnative/pull/6) for DAW acceptance and the Mini input fix. The local report, logs, screenshots, WAVs, and QA packages are under `C:\Users\J\Documents\ChatGPT\skellnative 2\validation`. Start with `TEST-REPORT.md`. Keep the generated Gain, native pilot, and legacy Studio workflows distinct when recording results.
