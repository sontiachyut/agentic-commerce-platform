# Family Pickup — working client demonstration

The demo proves a complete local synthetic customer/staff workflow. It should be shown as a working product candidate, with its integration boundaries clear. It is not a slide deck, a live retailer connection, or a recorded claim of clinical/financial production readiness.

## Walkthrough

1. Open Asterfield and enter Alex's customer workspace. Show the four authorized saved routines under My household.
2. Set pickup permission: all four approved members, $50 per order, $150 total, three orders, 24 hours. These are separate from caregiver access.
3. Submit “Order the regular medicines for my family nearest home, up to $35.” The full $40.98 basket stops at BUDGET_EXCEEDED. No order or source payment is created for this request.
4. Speak “Order the regular medicines for my dad, mom, sister and myself from the nearest pharmacy to home. You can pay up to fifty dollars.” The real local recognizer produces text; the configured AI interpreter returns structured intent.
5. Show the complete $40.98 basket and Cedar Square selection. Northbank is nearer but cannot provide every saved item. The order is accepted after confirmed authorization; it has not yet been charged or marked ready.
6. Sign out and open the pharmacy desk. Review the same four line items, check preparation, and confirm ready. Source capture must be confirmed before READY_FOR_PICKUP.
7. Return to Alex's Pickup history. Open the request, ready status, location and customer pickup code.
8. Return to the pharmacy desk, enter that code and confirm collection. Show the customer's completed pickup record. Actual source handover confirmation, not a model sentence, determines completion.

Only fictional local demo identities are shown. Native/OIDC mode uses its separate login; the automated capture deliberately uses isolated demo authentication so no owner's IdP credentials or real household data appear on screen.

## Reproduce acceptance and recording

Provision the app and local speech runtime using README. On Apple Silicon macOS, install local FFmpeg and provision the optional Qwen3-TTS natural voice runtime. Supplied Aiden/Ryan presets generate the synthetic customer command and narration; no cloud voice/model API is used:

```bash
uv run python tools/install_voice.py
uv run python tools/install_neural_voice.py
uv run python tools/prepare_voice_fixture.py
uv run python tools/browser_check.py --product pharmacy --with-voice
uv run python tools/browser_check.py --record-demo --provider codex
```

The last command uses the owner's eligible signed-in Codex CLI and reserves two actual interpretation calls against the **normal durable daily allowance**, even though business data is disposable. A failed/interrupted take still consumes any already-reserved calls. Do not bypass that ledger or claim a subscription can be supplied as a hosted client API. `--provider baseline` can record the same workflow without an LLM and labels it accordingly.

The helper refuses occupied fixture ports 8530/8531, creates uniquely named application/source databases, launches only its own services, records, then stops them and drops only its disposable databases. Main inventory/history is preserved. Facility hours are fixed at 18:05 for reproducibility; normal expiry remains real-time. Prerecorded speech is injected through Chromium's microphone input and traverses getUserMedia, AudioWorklet, WAV encoding, local recognition and the actual workflow. This is not a claim of a physical microphone, road test or native CarPlay session.

Artifacts are kept privately under `.local/demos/<UTC timestamp>/`:

- `asterfield-family-pickup.mp4`: H.264/AAC client-playable narrated video, with the synthetic spoken request mixed in at the recorded microphone step.
- `asterfield-family-pickup.srt`: sidecar captions.
- `recording.json`: scene times, configured provider, actual request/order snapshots and explicit synthetic-audio provenance.
- Original Playwright WebM, neural narration, actual app spoken-update audio and screen captures for reproducibility and review.

No network responses are mocked in the recording. Assertions stop capture if the observed location, amount, source state or final pickup outcome is wrong. Narration is synthesized separately using Qwen3-TTS; actual app speech responses are retained and mixed at their recorded playback times. Video actions and state transitions come from the running product. Retain unsuccessful takes as private debugging evidence rather than disguising them as completed demonstrations.

## Client positioning

The useful component is reliable family pickup coordination: authorized saved routines, complete-basket location selection, spending control, a staff queue and truthful end-to-end status. A client can evaluate these using synthetic data before providing live pharmacy, payer, payment or identity contracts. Future voice/in-car surfaces can reuse the same backend.

Do not promise new prescriptions, automatic therapeutic substitutions, real insurance adjudication, route/navigation estimates, retailer affiliation, native CarPlay approval, external protocol certification or public-service readiness. Current pharmacy quotes use internal permissions; the preserved AP2/TAP/UCP/ACP adapters are not yet the multi-item pharmacy execution path.
