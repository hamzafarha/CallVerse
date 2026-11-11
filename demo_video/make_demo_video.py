"""Make the CallVerse demo video: narration, screen recording of the real app, editing. About 3.5 minutes.

Three stages, run in order from the project root (the app must run on http://127.0.0.1:8010 for "record"):

    python demo_video/make_demo_video.py voice    # narration, one WAV per sentence (Piper, offline)
    python demo_video/make_demo_video.py record   # each scene filmed in headless Chrome (CDP screencast)
    python demo_video/make_demo_video.py edit     # titles, captions, subtitles, transitions, sound -> MP4

Tools (not project dependencies): pip install imageio-ffmpeg==0.6.0 piper-tts==1.8.0, plus the Piper voice
en_US-hfc_female-medium (rhasspy/piper-voices on Hugging Face). VIDEO_TOOLS = a folder added to sys.path,
PIPER_VOICE = the .onnx voice, VIDEO_WORK = the working folder (default: your temporary folder).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import wave
from pathlib import Path

if os.environ.get("VIDEO_TOOLS"):
    sys.path.insert(0, os.environ["VIDEO_TOOLS"])

ROOT = Path(__file__).resolve().parent.parent
WORK = Path(os.environ.get("VIDEO_WORK") or Path(tempfile.gettempdir()) / "callverse-video")
OUTPUT = Path(__file__).resolve().parent / "CallVerse_demo.mp4"
APP = "http://127.0.0.1:8010"
W, H = 1920, 1080  # the video
VW, VH = 1600, 900  # the browser, framed inside the video
LEAD, TAIL, GAP = 0.7, 0.9, 0.32  # seconds of silence before, after and between sentences
TRANSITION = 0.6

# ------------------------------------------------------------------------------------------- storyboard
# "say" is what the voice reads (spelled for speech); "show" is the subtitle on screen.
SCENES = [
    {
        "id": "intro",
        "kind": "card",
        "lines": [
            (
                "This is CallVerse, a digital twin of an online shop's customer service centre.",
                "This is Call Verse, a digital twin of an online shop's customer service centre.",
            ),
            (
                "Four AI agents work inside it, and every claim is tested against a simple baseline.",
                "Four A I agents work inside it, and every claim is tested against a simple baseline.",
            ),
        ],
    },
    {
        "id": "centre",
        "kind": "app",
        "title": "The live contact centre",
        "subtitle": "Every move is a real event of the four agents",
        "lines": [
            (
                "Welcome to the live contact centre: every move on this floor is a real event of our agents.",
                "Welcome to the live contact centre. Every move on this floor is a real event of our agents.",
            ),
            (
                "A Client agent walks in with a real order and a real problem.",
                "A client agent walks in, with a real order and a real problem.",
            ),
            (
                "The receptionist, our Workforce agent, recognises the problem and picks an advisor with "
                "the right skill.",
                "The receptionist, our workforce agent, recognises the problem, and picks an advisor with "
                "the right skill.",
            ),
            (
                "The Advisor agent answers from the company's policies; the badges show the tools it used.",
                "The advisor agent answers from the company's policies, and the badges show the tools it "
                "used.",
            ),
            (
                "When the chat ends, the Quality agent scores it.",
                "When the chat ends, the quality agent scores it.",
            ),
        ],
    },
    {
        "id": "chat",
        "kind": "app",
        "title": "A customer chats with the AI advisor",
        "subtitle": "Hosted LLM (Nemotron via OpenRouter) + RAG + tools + rules engine",
        "lines": [
            (
                "Now the customer's side: a customer whose parcel is late chats with the AI advisor.",
                "Now the customer's side. A customer whose parcel is late chats with the A I advisor.",
            ),
            (
                "Here the advisor is a Nemotron model, hosted on OpenRouter's free tier.",
                "Here, the advisor is a Nemotron model, hosted on Open Router's free tier.",
            ),
            (
                "Behind the scenes, the Workforce agent predicts the problem and routes the chat.",
                "Behind the scenes, the workforce agent predicts the problem, and routes the chat.",
            ),
            (
                "The advisor searches the policies, looks up the order and asks the rules engine for the "
                "decision.",
                "The advisor searches the policies, looks up the order, and asks the rules engine for the "
                "decision.",
            ),
            (
                "The language model only writes the reply: the rules decide.",
                "The language model only writes the reply. The rules decide.",
            ),
            (
                "At the end, the customer rates the chat and the Quality agent reviews it against the "
                "policy.",
                "At the end, the customer rates the chat, and the quality agent reviews it against the "
                "policy.",
            ),
        ],
    },
    {
        "id": "twin",
        "kind": "app",
        "title": "Test a decision before customers feel it",
        "subtitle": "Same customers, two staffing plans, one clock",
        "lines": [
            (
                "Managers use the twin to test a decision before customers feel it.",
                "Managers use the twin to test a decision, before customers feel it.",
            ),
            (
                "Here is the real week after Black Friday 2017, with the same customers on both floors.",
                "Here is the real week after Black Friday, twenty seventeen, with the same customers on "
                "both floors.",
            ),
            (
                "On the left, the plan built from a normal forecast: the queue grows and customers hang up.",
                "On the left, the plan built from a normal forecast. The queue grows, and customers hang up.",
            ),
            (
                "On the right, the plan that was tested in the twin first.",
                "On the right, the plan that was tested in the twin first.",
            ),
            (
                "Across four peak weeks, testing first cuts understaffed hours by 60 to 84%.",
                "Across four peak weeks, testing first cuts understaffed hours by sixty to eighty four "
                "percent.",
            ),
        ],
    },
    {
        "id": "plan",
        "kind": "app",
        "title": "Forecast, then plan the shifts",
        "subtitle": "LightGBM forecast · CP-SAT shift planning",
        "lines": [
            ("This works because of two models underneath.", "This works because of two models underneath."),
            (
                "A LightGBM model forecasts the contacts per type of problem: 25% error, against 32% for "
                "the naive baseline.",
                "A Light G B M model forecasts the contacts for each type of problem, with twenty five "
                "percent error, "
                "against thirty two percent for the naive baseline.",
            ),
            (
                "Then a constraint solver builds legal shifts, 40% cheaper than a schedule sized for the "
                "peak,",
                "Then a constraint solver builds legal shifts, forty percent cheaper than a schedule sized "
                "for the peak,",
            ),
            (
                "while still answering 92% of chats within 20 seconds.",
                "while still answering ninety two percent of chats within twenty seconds.",
            ),
        ],
    },
    {
        "id": "monitoring",
        "kind": "app",
        "title": "Monitoring every AI component",
        "subtitle": "Latency · fallbacks · tool calls · routing · cost",
        "lines": [
            (
                "Finally, we monitor every AI component: latency, fallbacks, tool calls, routing and cost.",
                "Finally, we monitor every A I component: latency, fallbacks, tool calls, routing, and cost.",
            ),
            (
                "The hosted models answer in about two seconds, and the routing finds the right problem "
                "95% of the time.",
                "The hosted models answer in about two seconds, and the routing finds the right problem "
                "ninety five percent of the time.",
            ),
            (
                "When a model fails, an approved template answers instead, and the real cost is zero.",
                "When a model fails, an approved template answers instead. And the real cost is zero.",
            ),
        ],
    },
    {
        "id": "outro",
        "kind": "logo",  # the animated logo and the slogan (no subtitles: the slogan is on screen)
        "lines": [
            (
                "CallVerse: test every decision before your customers feel it.",
                "Call Verse. Test every decision, before your customers feel it.",
            ),
            ("Thank you for watching.", "Thank you for watching."),
        ],
    },
]


# ------------------------------------------------------------------------------------------------ voice
def voice(only: list[str]) -> None:
    """One WAV per sentence with Piper (offline), then the timing of every scene in timeline.json. With scene
    ids, only those scenes are voiced again (the others keep their recordings and timing)."""
    from piper import PiperVoice, SynthesisConfig

    model = os.environ.get("PIPER_VOICE")
    if not model:
        sys.exit("Set PIPER_VOICE to the .onnx voice file.")
    speaker = PiperVoice.load(model)
    config = SynthesisConfig(length_scale=1.06, noise_scale=0.5, noise_w_scale=0.333)
    (WORK / "voice").mkdir(parents=True, exist_ok=True)
    saved = WORK / "timeline.json"
    old = (
        {s["id"]: s for s in json.loads(saved.read_text(encoding="utf-8"))} if only and saved.exists() else {}
    )
    timeline = []
    for scene in SCENES:
        if only and scene["id"] not in only and scene["id"] in old:
            timeline.append(old[scene["id"]])
            continue
        t, lines = LEAD, []
        for index, (show, say) in enumerate(scene["lines"]):
            path = WORK / "voice" / f"{scene['id']}_{index}.wav"
            with wave.open(str(path), "wb") as wav:
                speaker.synthesize_wav(say, wav, syn_config=config)
            with wave.open(str(path), "rb") as wav:
                seconds = wav.getnframes() / wav.getframerate()
            lines.append({"wav": str(path), "show": show, "start": round(t, 3), "end": round(t + seconds, 3)})
            t += seconds + GAP
        duration = round(t - GAP + TAIL, 3)
        timeline.append({"id": scene["id"], "duration": duration, "lines": lines})
        print(f"  {scene['id']:<11} {duration:5.1f} s  ({len(lines)} sentences)")
    (WORK / "timeline.json").write_text(json.dumps(timeline, indent=2), encoding="utf-8")
    total = sum(s["duration"] for s in timeline) - TRANSITION * (len(timeline) - 1)
    print(f"Total: {total:.0f} s")


# ----------------------------------------------------------------------------------------------- record
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CHAT_CUSTOMER = "SC007450"  # Gabriela Z.: parcel shipped, one day past the estimate (a carrier investigation)
MIN_SECONDS = {"chat": 44.0, "twin": 30.0}  # longer than the narration: time to read the screen


# Music alone before the first words and after the last ones, and a little more room at both ends of every
# scene, so that the music swells between scenes (about 2 s without voice around each transition).
EXTRA_LEAD = {"intro": 1.8, "outro": 1.9}  # outro: the voice starts as the slogan settles
EXTRA_TAIL = {"outro": 3.2}
SCENE_BREATH = 0.5


def timeline() -> list[dict]:
    scenes = json.loads((WORK / "timeline.json").read_text(encoding="utf-8"))
    for scene in scenes:
        lead = EXTRA_LEAD.get(scene["id"], SCENE_BREATH)
        tail = EXTRA_TAIL.get(scene["id"], SCENE_BREATH)
        for line in scene["lines"]:
            line["start"], line["end"] = line["start"] + lead, line["end"] + lead
        scene["duration"] = max(scene["duration"] + lead + tail, MIN_SECONDS.get(scene["id"], 0.0) + lead)
    return scenes


class Browser:
    """Headless Chrome driven over the DevTools protocol, with a screencast recorder."""

    def __init__(self, port: int = 9343) -> None:
        import subprocess

        self.port, self.counter, self.pending, self.frames, self.filming = port, 0, {}, [], False
        profile = WORK / "chrome-profile"
        self.process = subprocess.Popen(
            [
                CHROME,
                "--headless=new",
                f"--remote-debugging-port={port}",
                f"--user-data-dir={profile}",
                f"--window-size={VW},{VH}",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-extensions",
                "--hide-scrollbars",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    async def start(self) -> None:
        import asyncio
        import time
        import urllib.request

        import websockets

        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(200):
            try:
                targets = json.load(opener.open(f"http://127.0.0.1:{self.port}/json/list"))
                url = next(t for t in targets if t["type"] == "page")["webSocketDebuggerUrl"]
                break
            except Exception:  # noqa: BLE001 - Chrome is still starting
                time.sleep(0.2)
        self.ws = await websockets.connect(url, max_size=200_000_000, proxy=None)
        self.reader = asyncio.create_task(self._read())
        await self.call("Page.enable")
        await self.call("Runtime.enable")
        await self.call(
            "Emulation.setDeviceMetricsOverride", width=VW, height=VH, deviceScaleFactor=1, mobile=False
        )

    async def _read(self) -> None:
        import asyncio
        import time

        import websockets

        try:
            while True:
                message = json.loads(await self.ws.recv())
                if "id" in message and message["id"] in self.pending:
                    self.pending.pop(message["id"]).set_result(message.get("result", {}))
                elif message.get("method") == "Page.screencastFrame":
                    params = message["params"]
                    if self.filming:
                        self.frames.append((time.time(), params["data"]))
                    self.counter += 1  # acknowledge the frame; its answer is not awaited
                    ack = {
                        "id": self.counter,
                        "method": "Page.screencastFrameAck",
                        "params": {"sessionId": params["sessionId"]},
                    }
                    asyncio.create_task(self.ws.send(json.dumps(ack)))
        except websockets.ConnectionClosed:
            return

    async def call(self, method: str, **params):
        import asyncio

        self.counter += 1
        future = asyncio.get_running_loop().create_future()
        self.pending[self.counter] = future
        await self.ws.send(json.dumps({"id": self.counter, "method": method, "params": params}))
        return await future

    async def js(self, expression: str):
        result = await self.call(
            "Runtime.evaluate", expression=expression, awaitPromise=True, returnByValue=True
        )
        return result.get("result", {}).get("value")

    async def wait(self, expression: str, seconds: float = 60) -> bool:
        import asyncio

        for _ in range(int(seconds / 0.25)):
            if await self.js(expression):
                return True
            await asyncio.sleep(0.25)
        return False

    async def wait_text(self, text: str, seconds: float = 60) -> bool:
        return await self.wait(
            f"!!document.body && document.body.innerText.includes({json.dumps(text)})", seconds
        )

    async def goto(self, url: str, theme_key: str) -> None:
        import asyncio

        await self.call("Page.navigate", url=url)
        await asyncio.sleep(1.5)
        await self.js(f"localStorage.setItem({json.dumps(theme_key)}, 'light'); location.reload()")
        await asyncio.sleep(2.0)

    async def click_text(self, text: str) -> bool:
        return await self.js(
            "(() => { const want = " + json.dumps(text) + "; const all = [...document.querySelectorAll("
            "'button, a, [role=tab], [role=radio]')]; const el = all.find(e => e.offsetParent !== null && "
            "(e.innerText || '').trim().includes(want)); if (!el) return false; el.click(); return true; })()"
        )

    async def scroll(self, target: float, seconds: float) -> None:
        """Smooth, eased scroll of the window (requestAnimationFrame, so the film stays fluid)."""
        await self.js(
            "new Promise(done => { const y0 = window.scrollY; const y1 = Math.min(" + str(target) + ", "
            "document.documentElement.scrollHeight - innerHeight); const t0 = performance.now(); const "
            "span = "
            + str(seconds * 1000)
            + "; function step(now) { const p = Math.min(1, (now - t0) / span); "
            "const e = p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2; window.scrollTo(0, y0 + (y1 "
            "- y0) * e);"
            " if (p < 1) requestAnimationFrame(step); else done(true); } requestAnimationFrame(step); })"
        )

    async def film(self) -> None:
        import time

        self.frames, self.filming, self.film_start = [], True, time.time()
        await self.call(
            "Page.startScreencast", format="jpeg", quality=90, maxWidth=VW, maxHeight=VH, everyNthFrame=1
        )

    async def cut(self, name: str) -> float:
        """Stop filming and save the frames with their times; returns the length of the take."""
        import base64
        import time

        stop = time.time()
        self.filming = False
        await self.call("Page.stopScreencast")
        folder = WORK / "frames" / name
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.glob("*.jpg"):
            old.unlink()
        index = []
        for number, (at, data) in enumerate(self.frames):
            path = folder / f"f{number:06d}.jpg"
            path.write_bytes(base64.b64decode(data))
            index.append([path.name, round(max(0.0, at - self.film_start), 4)])
        length = round(stop - self.film_start, 3)
        (folder / "frames.json").write_text(json.dumps({"length": length, "frames": index}), encoding="utf-8")
        print(f"  {name}: {len(index)} frames over {length:.1f} s", flush=True)
        return length

    async def close(self) -> None:
        import asyncio

        await asyncio.sleep(0.3)  # let the last frame acknowledgements leave
        self.reader.cancel()
        await self.ws.close()
        self.process.terminate()


def arrival(seed: int) -> str:
    return (
        "fetch('/api/centre/arrivals', {method: 'POST', headers: {'Content-Type': 'application/json'}, "
        f"body: JSON.stringify({{mode: 'template', seed: {seed}}})}}).then(r => r.json())"
    )


async def film_centre(b: Browser, scene: dict) -> None:
    import asyncio

    await b.goto(f"{APP}/back-office/centre", "callverse-theme-back")
    await b.wait_text("The centre is open", 40)
    await b.click_text("Offline backups")  # the walk-ins below use the templates: show it
    await asyncio.sleep(1.0)
    await b.film()
    await asyncio.sleep(0.4)
    print("   ", await b.js(arrival(11)), flush=True)
    await asyncio.sleep(5.0)
    print("   ", await b.js(arrival(23)), flush=True)
    await asyncio.sleep(scene["duration"] - 3.9)
    await b.cut("centre")


async def film_chat(b: Browser, scene: dict) -> None:
    import asyncio

    idle = (
        "(() => { const box = document.querySelector('textarea, input[type=text]');"
        " return !!box && !box.placeholder.includes('answering'); })()"
    )
    busy = idle.replace("return !!box && !box", "return !!box && box")

    async def reply(chip_js: str) -> None:
        await b.js(chip_js)
        await b.wait(busy, 6)  # the advisor starts working...
        await b.wait(idle, 150)  # ...and finishes
        await asyncio.sleep(1.6)

    await b.goto(f"{APP}/chat/{CHAT_CUSTOMER}", "callverse-theme-front")
    await b.wait("document.querySelectorAll('button.chip').length >= 3", 60)
    await b.wait_text("online", 30)
    print(
        "    engine:",
        await b.js("(document.querySelector('[data-sonner-toast]') || {}).innerText"),
        flush=True,
    )
    await asyncio.sleep(1.0)
    await b.film()
    await asyncio.sleep(1.2)

    def chip(text: str) -> str:
        return (
            "(() => { const c = [...document.querySelectorAll('button.chip')]; const el = c.find(e => "
            "e.innerText.includes(" + json.dumps(text) + ")); if (el) el.click(); return !!el; })()"
        )

    await reply("document.querySelectorAll('button.chip')[0].click()")
    await reply(chip("My order number is"))
    await reply(chip("Thanks, that"))
    await b.click_text("End chat")
    await asyncio.sleep(1.2)
    await b.js("document.querySelector('[aria-label=\"5 stars\"]').click()")
    await asyncio.sleep(1.0)
    await b.click_text("Send rating")
    print("    review:", await b.wait_text("quality review", 120), flush=True)
    await asyncio.sleep(5.0)
    await b.cut("chat")


async def film_twin(b: Browser, scene: dict) -> None:
    import asyncio

    await b.goto(f"{APP}/back-office/twin", "callverse-theme-back")
    await b.wait_text("Live floor", 40)
    await b.click_text("Side by side")
    await b.wait_text("Jump to the peak", 90)
    await asyncio.sleep(2.0)
    await b.click_text("Jump to the peak")
    await b.scroll(430, 0.4)  # the clock and the two animated floors in view
    await asyncio.sleep(0.8)
    await b.film()
    await asyncio.sleep(scene["duration"] + 1.0)
    await b.cut("twin")


async def film_plan(b: Browser, scene: dict) -> None:
    import asyncio

    await b.goto(f"{APP}/back-office/forecast", "callverse-theme-back")
    await b.wait("document.querySelectorAll('svg.recharts-surface').length > 0", 40)
    await asyncio.sleep(2.5)
    await b.film()
    switch = scene["lines"][2]["start"] - 0.5  # "Then a constraint solver..."
    await asyncio.sleep(switch)
    await b.click_text("Workforce agent")
    await asyncio.sleep(3.0)
    await b.scroll(520, 3.5)
    await asyncio.sleep(max(1.0, scene["duration"] + 1.0 - switch - 6.5))
    await b.cut("plan")


async def film_monitoring(b: Browser, scene: dict) -> None:
    import asyncio

    await b.goto(f"{APP}/back-office/monitoring", "callverse-theme-back")
    await b.wait_text("Per resolved chat", 60)
    await asyncio.sleep(3.0)
    await b.film()
    await asyncio.sleep(3.0)
    await b.scroll(4200, scene["duration"] - 5.0)
    await asyncio.sleep(3.0)
    await b.cut("monitoring")


FILMS = {
    "centre": film_centre,
    "chat": film_chat,
    "twin": film_twin,
    "plan": film_plan,
    "monitoring": film_monitoring,
}


def record(only: list[str]) -> None:
    import asyncio

    scenes = {s["id"]: s for s in timeline()}

    async def main() -> None:
        browser = Browser()
        await browser.start()
        try:
            for name, film in FILMS.items():
                if not only or name in only:
                    print(f"Filming {name} ({scenes[name]['duration']:.0f} s)...", flush=True)
                    await film(browser, scenes[name])
        finally:
            await browser.close()

    asyncio.run(main())


# ------------------------------------------------------------------------------------------------- edit
FONTS = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
NAVY, INDIGO, INK_SOFT = (11, 17, 32), (30, 27, 75), (203, 213, 225)
BRAND = (42, 120, 214)
BOX_X, BOX_Y, BOX_W, BOX_H = 192, 100, 1536, 864  # where the browser sits in the frame (96% of 1600x900)
TEAM = "Hamza Farhani · Jihed Hmila · Abdellaoui Woujoud · Mohamed Aziz Kadri · Mohamed Yessine El Ichi"
TRANSITIONS = {"centre": "fade", "outro": "fade"}  # into these scenes; the others slide in
RESULTS = [
    ("25.3%", "forecast error (wMAPE)", "vs 31.6% naive baseline"),
    ("−40%", "labour cost (CP-SAT)", "92.4% answered < 20 s"),
    ("−60 to −84%", "understaffed hours", "when the plan is tested first"),
    ("96.9%", "retrieval recall@4", "vs 80.4% keyword search"),
    ("12 / 12", "verified policy actions", "rules decide, LLM writes"),
]


def font(name: str, size: int):
    from PIL import ImageFont

    return ImageFont.truetype(str(FONTS / name), size)


def gradient():
    """The dark brand background of every frame."""
    import numpy as np
    from PIL import Image

    y, x = np.mgrid[0:H, 0:W]
    t = (x / W * 0.6 + y / H * 0.4)[..., None]
    rgb = np.array(NAVY) * (1 - t) + np.array(INDIGO) * t
    return Image.fromarray(rgb.astype("uint8"), "RGB")


def top_layer(number: int, total: int, scene: dict, path: Path) -> None:
    """Background + titles, with a rounded transparent window where the browser shows through."""
    from PIL import Image, ImageDraw, ImageFilter

    base = gradient().convert("RGBA")
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        (BOX_X - 4, BOX_Y + 8, BOX_X + BOX_W + 4, BOX_Y + BOX_H + 18), 22, fill=(0, 0, 0, 150)
    )
    base = Image.alpha_composite(base, shadow.filter(ImageFilter.GaussianBlur(18)))
    draw = ImageDraw.Draw(base)
    draw.rounded_rectangle((BOX_X, 30, BOX_X + 74, 66), 18, fill=BRAND)
    draw.text((BOX_X + 37, 48), f"{number}/{total}", font=font("seguisb.ttf", 22), fill="white", anchor="mm")
    draw.text((BOX_X + 92, 48), scene["title"], font=font("seguisb.ttf", 34), fill="white", anchor="lm")
    title_end = BOX_X + 92 + draw.textlength(scene["title"], font=font("seguisb.ttf", 34))
    draw.text(
        (title_end + 22, 50), scene["subtitle"], font=font("segoeui.ttf", 22), fill=INK_SOFT, anchor="lm"
    )
    draw.text((BOX_X + BOX_W, 48), "CallVerse", font=font("seguisb.ttf", 26), fill="white", anchor="rm")
    hole = Image.new("L", (W, H), 0)
    ImageDraw.Draw(hole).rounded_rectangle((BOX_X, BOX_Y, BOX_X + BOX_W - 1, BOX_Y + BOX_H - 1), 18, fill=255)
    alpha = base.getchannel("A").point(lambda v: v)
    alpha.paste(0, mask=hole)
    base.putalpha(alpha)
    base.save(path)


def card(scene_id: str, path: Path) -> None:
    """The title card (intro) and the results card (outro)."""
    from PIL import ImageDraw

    image = gradient()
    draw = ImageDraw.Draw(image)
    if scene_id == "intro":
        mark = logo_mark(132)
        image.paste(mark, (W // 2 - 66, 184), mark)
        draw.text((W // 2, 420), "CallVerse", font=font("seguibl.ttf", 120), fill="white", anchor="mm")
        draw.text(
            (W // 2, 530),
            "A multi-agent digital twin of an e-commerce customer service centre",
            font=font("segoeui.ttf", 40),
            fill=INK_SOFT,
            anchor="mm",
        )
        draw.text((W // 2, 650), TEAM, font=font("seguisb.ttf", 28), fill="white", anchor="mm")
        draw.text(
            (W // 2, 700),
            "Advanced Data Science Project · ESPRIT · Class 5DS3 · 2026",
            font=font("segoeui.ttf", 26),
            fill=INK_SOFT,
            anchor="mm",
        )
    else:
        draw.text(
            (W // 2, 150), "What the evidence shows", font=font("seguibl.ttf", 60), fill="white", anchor="mm"
        )
        width, gap, top = 300, 24, 270
        left = (W - (len(RESULTS) * width + (len(RESULTS) - 1) * gap)) // 2
        for i, (big, label, note) in enumerate(RESULTS):
            x = left + i * (width + gap)
            draw.rounded_rectangle(
                (x, top, x + width, top + 250), 22, fill=(36, 40, 92), outline=(84, 104, 168), width=2
            )
            size = 52  # shrink a long value until it fits its box
            while draw.textlength(big, font=font("seguibl.ttf", size)) > width - 36 and size > 30:
                size -= 2
            draw.text(
                (x + width // 2, top + 80), big, font=font("seguibl.ttf", size), fill="white", anchor="mm"
            )
            draw.text(
                (x + width // 2, top + 150), label, font=font("seguisb.ttf", 24), fill="white", anchor="mm"
            )
            draw.text(
                (x + width // 2, top + 190), note, font=font("segoeui.ttf", 21), fill=INK_SOFT, anchor="mm"
            )
        draw.text(
            (W // 2, 640),
            "One Docker container · 200 automated tests · one command to reproduce",
            font=font("seguisb.ttf", 32),
            fill="white",
            anchor="mm",
        )
        draw.text((W // 2, 700), "Thank you", font=font("seguibl.ttf", 54), fill="white", anchor="mm")
        credits = (
            "Data: Olist (CC BY-NC-SA 4.0), Bitext (CDLA-Sharing 1.0) · Voice: Piper 'hfc_female' (Hi-Fi "
            "Captain, "
            "NICT; CC BY-NC-SA 4.0) · Recorded and edited automatically with Claude Code (Anthropic)"
        )
        draw.text((W // 2, 790), credits, font=font("segoeui.ttf", 19), fill=INK_SOFT, anchor="mm")
        draw.text(
            (W // 2, 830), TEAM + " · ESPRIT 5DS3", font=font("segoeui.ttf", 19), fill=INK_SOFT, anchor="mm"
        )
    image.save(path)


LOGO_FROM, LOGO_TO = (139, 125, 255), (56, 189, 248)  # the app's dark-theme brand gradient (indigo -> sky)
SLOGAN = "Test every decision before your customers feel it."


def logo_mark(size: int, dots: tuple[float, float, float] = (0.0, 0.0, 0.0)):
    """The app's logo (LogoMark in frontend/shared/src/components/brand.tsx): a rounded square with the
    brand gradient, a white chat bubble and three dots. dots = how far each dot is lifted (in SVG units),
    for the 'typing' bounce. Drawn 4x larger, then reduced, for smooth edges."""
    import numpy as np
    from PIL import Image, ImageDraw

    big = size * 4
    y, x = np.mgrid[0:big, 0:big]
    t = ((x + y) / (2 * big))[..., None]  # 135 degrees: from the top left to the bottom right
    rgb = np.array(LOGO_FROM) * (1 - t) + np.array(LOGO_TO) * t
    square = Image.fromarray(rgb.astype("uint8"), "RGB").convert("RGBA")
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, big - 1, big - 1), int(big * 0.3), fill=255)
    square.putalpha(mask)
    draw = ImageDraw.Draw(square)
    unit = big * 0.66 / 32  # the SVG's 32x32 box, at 66% of the square, centred
    left = (big - big * 0.66) / 2

    def p(px: float, py: float) -> tuple[float, float]:
        return left + px * unit, left + py * unit

    draw.rounded_rectangle((*p(7, 7), *p(25, 20)), int(2.5 * unit), fill=(255, 255, 255, 242))
    draw.polygon([p(15, 19.9), p(10, 24), p(10, 19.9)], fill=(255, 255, 255, 242))
    for cx, lift in zip((12, 16, 20), dots):
        cx_, cy_ = p(cx, 13.5 - lift)
        r = 1.5 * unit
        draw.ellipse((cx_ - r, cy_ - r, cx_ + r, cy_ + r), fill=LOGO_FROM + (255,))
    return square.resize((size, size), Image.LANCZOS)


def logo_clip(duration: float, out: Path) -> None:
    """The closing animation: the logo pops in with a glow ring, its dots 'type', a white dot orbits it, the
    wordmark rises with a shine, then the slogan and the class line fade in; everything floats gently."""
    import subprocess

    import imageio_ffmpeg
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter

    fps, size, centre = 30, 230, (W // 2, 470)

    def ease_out(x: float) -> float:
        x = min(max(x, 0.0), 1.0)
        return 1 - (1 - x) ** 3

    def ease_back(x: float) -> float:  # overshoots a little, then settles
        x = min(max(x, 0.0), 1.0)
        return 1 + 2.7 * (x - 1) ** 3 + 1.7 * (x - 1) ** 2

    def phase(t: float, start: float, length: float) -> float:
        return min(max((t - start) / length, 0.0), 1.0)

    background = np.asarray(gradient(), dtype=np.float32)
    yy, xx = np.mgrid[0:H, 0:W]
    glow = np.exp(-(((xx - centre[0]) ** 2 + (yy - centre[1]) ** 2) / (2 * 260.0**2)))[..., None]
    glow_colour = np.array(LOGO_FROM, dtype=np.float32)

    def text_layer(text: str, face, fill, gradient_text: bool = False):
        box = Image.new("RGBA", (W, 200), (0, 0, 0, 0))
        ImageDraw.Draw(box).text((W // 2, 100), text, font=face, fill=fill, anchor="mm")
        return box

    word_face = font("seguibl.ttf", 132)
    word = Image.new("RGBA", (W, 200), (0, 0, 0, 0))
    wd = ImageDraw.Draw(word)
    call_w, verse_w = wd.textlength("Call", font=word_face), wd.textlength("Verse", font=word_face)
    x0 = W // 2 - (call_w + verse_w) / 2
    wd.text((x0, 100), "Call", font=word_face, fill="white", anchor="lm")
    verse_mask = Image.new("L", (W, 200), 0)
    ImageDraw.Draw(verse_mask).text((x0 + call_w, 100), "Verse", font=word_face, fill=255, anchor="lm")
    ramp = np.linspace(0, 1, W)[None, :, None]
    verse_rgb = (np.array(LOGO_FROM) * (1 - ramp) + np.array(LOGO_TO) * ramp) * np.ones((200, 1, 1))
    verse = Image.fromarray(verse_rgb.astype("uint8"), "RGB").convert("RGBA")
    verse.putalpha(verse_mask)
    word = Image.alpha_composite(word, verse)
    word_alpha = np.asarray(word.getchannel("A"), dtype=np.float32) / 255
    slogan = text_layer(SLOGAN, font("seguisb.ttf", 44), INK_SOFT)
    footer = text_layer("CallVerse · Advanced Data Science Project · ESPRIT · Class 5DS3 · 2026",
                        font("segoeui.ttf", 24), (148, 163, 184))  # fmt: skip
    orbit_dot = Image.new("RGBA", (60, 60), (0, 0, 0, 0))
    ImageDraw.Draw(orbit_dot).ellipse((18, 18, 42, 42), fill=LOGO_TO + (180,))
    orbit_dot = orbit_dot.filter(ImageFilter.GaussianBlur(7))
    ImageDraw.Draw(orbit_dot).ellipse((25, 25, 35, 35), fill=(255, 255, 255, 255))

    def faded(layer, alpha: float):
        if alpha >= 1:
            return layer
        copy = layer.copy()
        copy.putalpha(copy.getchannel("A").point(lambda v: int(v * alpha)))
        return copy

    command = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo",
               "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-", "-vf",
               "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p", "-c:v", "libx264", "-preset",
               "medium", "-crf", "17", *HD_TAGS, str(out)]  # fmt: skip
    encoder = subprocess.Popen(command, stdin=subprocess.PIPE)
    frames = int(round(duration * fps))
    for k in range(frames):
        t = k / fps
        breathe = 0.16 + 0.05 * np.sin(2 * np.pi * t / 4.0)
        canvas = background + glow * glow_colour * breathe * ease_out(phase(t, 0.1, 1.0))
        frame = Image.fromarray(np.clip(canvas, 0, 255).astype("uint8"), "RGB").convert("RGBA")
        draw = ImageDraw.Draw(frame)
        float_y = 5 * np.sin(2 * np.pi * (t - 1.2) / 3.5) if t > 1.2 else 0.0
        cx, cy = centre[0], centre[1] + float_y
        for start in (0.25, 0.65):  # two glow rings spreading out from the logo
            ring = phase(t, start, 1.2)
            if 0 < ring < 1:
                radius = size * 0.55 + ring * 230
                colour = LOGO_TO + (int(150 * (1 - ring)),)
                draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=colour, width=4)
        pop = phase(t, 0.0, 0.9)
        if pop > 0:
            scale = 0.2 + 0.8 * ease_back(pop)
            lifts = tuple(
                max(0.0, np.sin(2 * np.pi * (t - 1.0 - i * 0.16) / 1.1)) * 1.4 if t > 1.0 else 0.0
                for i in range(3)
            )
            mark = logo_mark(max(8, int(size * scale)), lifts)
            mark = mark.rotate(-12 * (1 - ease_out(pop)), resample=Image.BICUBIC, expand=True)
            mark = faded(mark, ease_out(pop / 0.55))
            frame.alpha_composite(mark, (int(cx - mark.width / 2), int(cy - mark.height / 2)))
        dot_in = phase(t, 1.0, 0.6)
        if dot_in > 0:  # the white dot orbiting the logo, one turn every 4 s
            angle = 2 * np.pi * (t - 1.0) / 4.0
            ox, oy = cx + (size * 0.62) * np.cos(angle), cy + (size * 0.62) * np.sin(angle)
            frame.alpha_composite(faded(orbit_dot, dot_in), (int(ox - 30), int(oy - 30)))
        rise = phase(t, 1.0, 0.8)
        if rise > 0:
            layer = faded(word, ease_out(rise))
            shine = phase(t, 2.1, 0.9)
            if 0 < shine < 1:  # a light sweeping across the wordmark
                band = np.exp(-(((np.arange(W) - (x0 - 200 + shine * (call_w + verse_w + 400))) / 70) ** 2))
                light = (word_alpha * band[None, :] * 0.55 * 255).astype("uint8")
                white = Image.new("RGBA", (W, 200), (255, 255, 255, 0))
                white.putalpha(Image.fromarray(light, "L"))
                layer = Image.alpha_composite(layer, white)
            frame.alpha_composite(layer, (0, int(560 + 30 * (1 - ease_out(rise)) + float_y * 0.5)))
        tag = phase(t, 1.8, 0.8)
        if tag > 0:
            frame.alpha_composite(faded(slogan, ease_out(tag)), (0, int(668 + 20 * (1 - ease_out(tag)))))
        foot = phase(t, 2.8, 0.8)
        if foot > 0:
            frame.alpha_composite(faded(footer, ease_out(foot) * 0.9), (0, 880))
        encoder.stdin.write(frame.convert("RGB").tobytes())
    encoder.stdin.close()
    if encoder.wait():
        sys.exit("ffmpeg failed on the logo animation")
    print(f"  outro: logo animation, {frames} frames", flush=True)


def subtitle(text: str, path: Path) -> None:
    """One sentence, centred in the band under the browser (two lines at most)."""
    from PIL import Image, ImageDraw

    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    face = font("seguisb.ttf", 31)
    words, lines = text.split(), [""]
    for word in words:
        trial = (lines[-1] + " " + word).strip()
        if draw.textlength(trial, font=face) > 1500 and lines[-1]:
            lines.append(word)
        else:
            lines[-1] = trial
    centre = (BOX_Y + BOX_H + H) // 2 + 2
    for i, line in enumerate(lines):
        y = centre + (i - (len(lines) - 1) / 2) * 40
        draw.text((W // 2 + 2, y + 2), line, font=face, fill=(0, 0, 0, 160), anchor="mm")
        draw.text((W // 2, y), line, font=face, fill="white", anchor="mm")
    layer.save(path)


HD_TAGS = [
    "-pix_fmt",
    "yuv420p",
    "-colorspace",
    "bt709",
    "-color_primaries",
    "bt709",
    "-color_trc",
    "bt709",
    "-color_range",
    "tv",
]


def run_ffmpeg(args: list[str]) -> None:
    import subprocess

    import imageio_ffmpeg

    done = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error", *args]
    )
    if done.returncode:
        sys.exit("ffmpeg failed")


def scene_clip(index: int, scene: dict, story: dict, out: Path) -> None:
    """One scene as a 1920x1080, 30 fps clip of exactly scene['duration'] seconds (no sound)."""
    edit = WORK / "edit"
    duration = scene["duration"]
    subs = []
    if story["kind"] == "logo":  # an animation drawn frame by frame, piped into ffmpeg
        logo_clip(duration, out)
        return
    for n, line in enumerate(scene["lines"]):
        path = edit / f"{scene['id']}_sub{n}.png"
        subtitle(line["show"], path)
        subs.append((path, line["start"], line["end"] + 0.25))
    inputs, chain = [], []
    if story["kind"] == "card":
        path = edit / f"{scene['id']}_card.png"
        card(scene["id"], path)
        inputs += ["-loop", "1", "-framerate", "30", "-t", f"{duration}", "-i", str(path)]
        chain.append("[0:v]format=rgb24[v0]")
    else:
        meta = json.loads((WORK / "frames" / scene["id"] / "frames.json").read_text(encoding="utf-8"))
        frames, length = meta["frames"], meta["length"]
        listing = ["ffconcat version 1.0"]
        for k, (name, at) in enumerate(frames):
            nxt = frames[k + 1][1] if k + 1 < len(frames) else length
            start = 0.0 if k == 0 else at
            listing += [
                f"file '{(WORK / 'frames' / scene['id'] / name).as_posix()}'",
                f"duration {max(nxt - start, 0.001):.4f}",
            ]
        listing.append(f"file '{(WORK / 'frames' / scene['id'] / frames[-1][0]).as_posix()}'")
        concat = edit / f"{scene['id']}_frames.txt"
        concat.write_text("\n".join(listing), encoding="utf-8")
        speed = min(length / duration, 3.0) if length > duration * 1.15 else 1.0
        top = edit / f"{scene['id']}_top.png"
        top_layer(index, 5, story, top)
        inputs += [
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat),
            "-loop",
            "1",
            "-framerate",
            "30",
            "-i",
            str(top),
        ]
        # Everything is composed in RGB, then converted once to HD video colours (BT.709, TV range).
        chain.append(
            f"[0:v]setpts=PTS/{speed:.4f},fps=30,scale={BOX_W}:{BOX_H}:flags=lanczos,format=rgb24,"
            f"pad={W}:{H}:{BOX_X}:{BOX_Y}:color=0x0b1120,tpad=stop_mode=clone:stop_duration=30[b0]"
        )
        chain.append("[b0][1:v]overlay=0:0:shortest=0:format=rgb[v0]")
        print(f"  {scene['id']}: take {length:.1f} s -> {duration:.1f} s (speed x{speed:.2f})", flush=True)
    first = 1 if story["kind"] == "card" else 2  # input index of the first subtitle
    for n, (path, start, end) in enumerate(subs):
        inputs += ["-loop", "1", "-framerate", "30", "-i", str(path)]
        chain.append(
            f"[v{n}][{first + n}:v]overlay=0:0:format=rgb:enable='between(t,{start:.2f},{end:.2f})'[v{n + 1}]"
        )
    chain.append(f"[v{len(subs)}]scale=out_color_matrix=bt709:out_range=tv,format=yuv420p[out]")
    graph = ";".join(chain)
    run_ffmpeg(
        [
            *inputs,
            "-filter_complex",
            graph,
            "-map",
            "[out]",
            "-t",
            f"{duration}",
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "17",
            *HD_TAGS,
            str(out),
        ]
    )


RATE = 48000  # the sound of the video
BPM = 100
# An original loop (vi-IV-I-V in C major, with sevenths): Am7, Fmaj7, Cmaj7, G(add9), one chord per bar.
CHORDS = [(57, 60, 64, 67), (53, 57, 60, 64), (48, 55, 59, 64), (55, 59, 62, 69)]
ROOTS = (45, 41, 36, 43)
ARPEGGIO = (0, 1, 2, 3, 2, 3, 1, 2)  # chord tones played as eighth notes, an octave up
MUSIC_UNDER_VOICE_DB, MUSIC_BETWEEN_DB = -18.0, -4.0  # music level relative to the speech


def voice_track(scenes: list[dict], starts: list[float], total: float):
    """The narration at 48 kHz (mono), and the (start, end) time of every sentence in the video."""
    import numpy as np
    from scipy.io import wavfile
    from scipy.signal import resample_poly

    track, spans = np.zeros(int(total * RATE) + RATE, dtype=np.float64), []
    for scene, begin in zip(scenes, starts):
        for line in scene["lines"]:
            rate, data = wavfile.read(line["wav"])
            samples = resample_poly(data.astype(np.float64) / 32768.0, RATE, rate)
            at = int((begin + line["start"]) * RATE)
            track[at : at + len(samples)] += samples[: len(track) - at]
            spans.append((begin + line["start"], begin + line["end"]))
    return track / max(1e-9, float(np.abs(track).max())) * 0.9, spans


def music_track(seconds: float):
    """An original, calm background track made from scratch: a warm chord pad, a plucked arpeggio with echoes,
    a bass and soft drums, with a little reverb. Two quiet bars to start; the drums leave for the last two."""
    import numpy as np
    from scipy.signal import butter, fftconvolve, sosfilt

    rng = np.random.default_rng(2026)
    beat = 60.0 / BPM
    bar = 4 * beat
    n = int((seconds + 2) * RATE)
    bars = int(seconds / bar) + 1
    layers = {name: np.zeros((2, n)) for name in ("pad", "arp", "bass", "drums")}

    def hz(midi: int) -> float:
        return 440.0 * 2 ** ((midi - 69) / 12)

    def add(layer: str, sound, at: float, pan: float = 0.0, gain: float = 1.0) -> None:
        start = int(at * RATE)
        if start >= n:
            return
        part = sound[: n - start] * gain
        angle = (pan + 1) * np.pi / 4  # equal-power panning, -1 = left, +1 = right
        layers[layer][0, start : start + len(part)] += part * np.cos(angle)
        layers[layer][1, start : start + len(part)] += part * np.sin(angle)

    def noise(seconds_: float, low: float | None = None, high: float | None = None):
        white = rng.normal(0, 1, int(seconds_ * RATE))
        if low and high:
            return sosfilt(butter(2, [low, high], "bandpass", fs=RATE, output="sos"), white)
        return sosfilt(butter(2, low, "highpass", fs=RATE, output="sos"), white)

    t_pad = np.arange(int((bar + 1.5) * RATE)) / RATE
    pad_env = np.minimum(1, t_pad / 0.8) * np.clip((bar + 1.5 - t_pad) / 1.5, 0, 1)
    t_note = np.arange(int(1.2 * RATE)) / RATE
    t_bass = np.arange(int(1.4 * beat * RATE)) / RATE
    t_kick = np.arange(int(0.45 * RATE)) / RATE
    kick = np.sin(2 * np.pi * np.cumsum(45 + 75 * np.exp(-t_kick / 0.04)) / RATE) * np.exp(-t_kick / 0.2)
    for b in range(bars):
        chord, at = CHORDS[b % 4], b * bar
        for note in chord:  # the pad: two slightly detuned voices per note, one on each side
            for cents, pan in ((-7, -0.55), (7, 0.55)):
                f, phase = hz(note) * 2 ** (cents / 1200), rng.uniform(0, 2 * np.pi)
                tone = np.sin(2 * np.pi * f * t_pad + phase) + 0.3 * np.sin(4 * np.pi * f * t_pad + phase)
                add("pad", (tone + 0.1 * np.sin(6 * np.pi * f * t_pad)) * pad_env, at, pan, 0.045)
        for k, index in enumerate(ARPEGGIO):  # the plucked arpeggio
            f = hz(chord[index] + 12)
            pluck = np.sin(2 * np.pi * f * t_note) + 0.2 * np.sin(4 * np.pi * f * t_note)
            pluck *= np.exp(-t_note / 0.28) * (1 - np.exp(-t_note / 0.003))
            add("arp", pluck, at + k * beat / 2, -0.3 if k % 2 == 0 else 0.3, 0.035 if k % 2 == 0 else 0.026)
        if b >= 2:  # the bass and the drums join after the two quiet bars
            f = hz(ROOTS[b % 4])
            low = (np.sin(2 * np.pi * f * t_bass) + 0.25 * np.sin(4 * np.pi * f * t_bass)) * np.exp(
                -t_bass / 0.9
            )
            low *= 1 - np.exp(-t_bass / 0.006)
            for k in (0, 2):
                add("bass", np.tanh(1.5 * low) / np.tanh(1.5), at + k * beat, 0.0, 0.16)
        if 2 <= b < bars - 2:
            for k in (0, 2):
                add("drums", kick, at + k * beat, 0.0, 0.26)
            for k in (1, 3):
                snare = noise(0.3, 1200, 6000) * np.exp(-np.arange(int(0.3 * RATE)) / RATE / 0.1)
                add("drums", snare, at + k * beat, 0.15, 0.05)
            for k in range(8):
                hat = noise(0.08, 7500) * np.exp(-np.arange(int(0.08 * RATE)) / RATE / 0.022)
                add("drums", hat, at + k * beat / 2, -0.25, 0.024 if k % 2 else 0.017)
    # Echoes on the arpeggio (a dotted eighth, ping-pong), then reverb on the pad and the arpeggio.
    echo, delay = layers["arp"].copy(), int(0.75 * beat * RATE)
    for repeat in range(1, 4):
        shifted = np.zeros_like(echo)
        shifted[:, delay * repeat :] = layers["arp"][:, : n - delay * repeat] * 0.35**repeat
        echo += shifted[::-1] if repeat % 2 else shifted
    tonal = layers["pad"] + echo
    t_ir = np.arange(int(2.4 * RATE)) / RATE
    smooth = butter(2, 4000, "lowpass", fs=RATE, output="sos")
    wet = np.zeros_like(tonal)
    for ch in range(2):
        ir = sosfilt(smooth, rng.normal(0, 1, len(t_ir)) * np.exp(-t_ir / 0.75))
        wet[ch] = fftconvolve(tonal[ch], ir / np.sqrt(np.sum(ir**2)), mode="full")[:n]
    mix = tonal + 0.3 * wet + layers["bass"] + layers["drums"]
    mix = sosfilt(butter(2, 40, "highpass", fs=RATE, output="sos"), mix)
    fade = np.ones(n)
    fade[: int(0.5 * RATE)] = np.linspace(0, 1, int(0.5 * RATE))
    end = int(seconds * RATE)
    fade[end - 3 * RATE : end] = np.linspace(1, 0, 3 * RATE)
    fade[end:] = 0
    return mix * fade / max(1e-9, float(np.abs(mix).max()))


def ducked_mix(voice, spans: list[tuple[float, float]], music, path: Path) -> None:
    """Voice + music, the music low while someone speaks and up in between (from the sentence times)."""
    import numpy as np
    from scipy.io import wavfile
    from scipy.signal import fftconvolve

    n = len(voice)
    music = music[:, :n] if music.shape[1] >= n else np.pad(music, ((0, 0), (0, n - music.shape[1])))
    speaking = np.zeros(n)
    merged: list[list[float]] = []
    for start, end in sorted((s - 0.35, e + 0.25) for s, e in spans):  # duck a little before, after
        if merged and start - merged[-1][1] < 1.3:  # short pauses inside a scene stay low (no pumping)
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    for start, end in merged:
        speaking[max(0, int(start * RATE)) : int(end * RATE)] = 1
    ramp = np.hanning(int(0.5 * RATE))
    duck = np.clip(fftconvolve(speaking, ramp / ramp.sum(), mode="same"), 0, 1)

    def rms_db(x) -> float:
        return 10 * np.log10(np.mean(x**2) + 1e-12)

    speech_db = rms_db(voice[np.abs(voice) > 1e-3])
    music_db = rms_db(music.mean(axis=0)[int(2 * RATE) : int(n - 4 * RATE)])
    high = 10 ** ((speech_db + MUSIC_BETWEEN_DB - music_db) / 20)
    low = 10 ** ((speech_db + MUSIC_UNDER_VOICE_DB - music_db) / 20)
    gain = high + (low - high) * duck
    mix = music * gain + voice
    mix *= min(1.0, 0.95 / float(np.abs(mix).max()))
    wavfile.write(path, RATE, (mix.T * 32767).astype(np.int16))
    print(
        f"  music: {MUSIC_BETWEEN_DB:+.0f} dB vs speech between scenes, "
        f"{MUSIC_UNDER_VOICE_DB:+.0f} dB under it"
    )
    if os.environ.get("DUCKING_PLOT"):  # a picture of the ducking, to check it by eye
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        step = RATE // 50
        t = np.arange(0, n, step) / RATE
        fig, ax = plt.subplots(figsize=(16, 3))
        ax.fill_between(t, 0, np.abs(voice[::step]), color="#2a78d6", alpha=0.5, label="voice")
        ax.plot(t, gain[::step] / high, color="#eb6834", lw=1.5, label="music gain (1 = between scenes)")
        ax.legend(loc="upper right")
        ax.set_xlabel("seconds")
        fig.savefig(os.environ["DUCKING_PLOT"], bbox_inches="tight", dpi=90)


def edit(redo: list[str]) -> None:
    """Build the scene clips (all, or only those named in redo when the others exist), then the video."""
    scenes, stories = timeline(), {s["id"]: s for s in SCENES}
    folder = WORK / "edit"
    folder.mkdir(parents=True, exist_ok=True)
    clips, number = [], 0
    for scene in scenes:
        story = stories[scene["id"]]
        number += story["kind"] == "app"
        clip = folder / f"clip_{scene['id']}.mp4"
        if not redo or scene["id"] in redo or not clip.exists():
            scene_clip(number, scene, story, clip)
        clips.append(clip)
    # Scene k starts when the transition into it starts: the sum of the earlier scenes minus the overlaps.
    starts, at = [], 0.0
    for k, scene in enumerate(scenes):
        starts.append(at)
        at += scene["duration"] - TRANSITION
    total = at + TRANSITION
    sound = folder / "soundtrack.wav"
    voice, spans = voice_track(scenes, starts, total)
    ducked_mix(voice, spans, music_track(total), sound)
    inputs, chain, last = [], [], "0:v"
    for clip in clips:
        inputs += ["-i", str(clip)]
    for k in range(1, len(clips)):
        kind = TRANSITIONS.get(scenes[k]["id"], "smoothleft")
        chain.append(
            f"[{last}][{k}:v]xfade=transition={kind}:duration={TRANSITION}:offset={starts[k]:.3f}[x{k}]"
        )
        last = f"x{k}"
    chain.append(f"[{last}]fade=t=in:st=0:d=0.8,fade=t=out:st={total - 2.0:.3f}:d=2.0[video]")
    chain.append(f"[{len(clips)}:a]afade=t=in:d=0.2,afade=t=out:st={total - 2.0:.3f}:d=2.0[audio]")
    run_ffmpeg(
        [
            *inputs,
            "-i",
            str(sound),
            "-filter_complex",
            ";".join(chain),
            "-map",
            "[video]",
            "-map",
            "[audio]",
            "-t",
            f"{total:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "20",
            *HD_TAGS,
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(OUTPUT),
        ]
    )
    print(f"Video: {OUTPUT} ({total:.0f} s, {OUTPUT.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else ""
    if stage == "voice":
        voice(sys.argv[2:])
    elif stage == "record":
        record(sys.argv[2:])
    elif stage == "edit":
        edit(sys.argv[2:])
    else:
        sys.exit(__doc__)
