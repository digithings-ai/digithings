#!/usr/bin/env python3
"""Record a hero banner running in a real pty, for TUI review before web integration.

    python3 scripts/hero-banner-capture.py digillm --size 120x30 --seconds 9 --out /tmp/digillm-120x30

Writes <out>.cast (asciicast v2: the exact bytes the OpenTUI app wrote) and,
with --render (needs `pyte`, Pillow and ffmpeg), <out>.mp4 plus PNG stills at
--stills ms, drawn by replaying the cast through a terminal emulator.
Extra environment (NO_MOTION=1, COLORTERM=, HERO_BANNER_LIVE=0) goes in --env.
"""
import argparse
import codecs
import fcntl
import json
import os
import pty
import select
import shutil
import struct
import subprocess
import sys
import termios
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TUI = os.path.join(ROOT, "clients", "digichat-tui")


def record(banner, cols, rows, seconds, env_extra):
    bun = shutil.which("bun") or os.path.expanduser("~/.bun/bin/bun")
    env = {**os.environ, "TERM": "xterm-256color", "COLORTERM": "truecolor", "COLUMNS": str(cols), "LINES": str(rows)}
    env.update(env_extra)
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(TUI)
        os.execve(bun, [bun, "src/hero-preview.tsx", banner], env)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    events, start, quit_sent = [], time.monotonic(), False
    # A block character is three bytes; a read can end mid-character.
    decode = codecs.getincrementaldecoder("utf-8")("replace").decode
    while True:
        now = time.monotonic() - start
        if now > seconds and not quit_sent:
            os.write(fd, b"q")
            quit_sent = True
        if now > seconds + 2:
            break
        ready, _, _ = select.select([fd], [], [], 0.02)
        if not ready:
            continue
        try:
            data = os.read(fd, 65536)
        except OSError:
            break
        if not data:
            break
        if not quit_sent:
            text = decode(data)
            if text:
                events.append([round(now, 4), "o", text])
    try:
        os.kill(pid, 9)
    except ProcessLookupError:
        # The recorded process already exited on its own; nothing left to kill.
        pass
    os.waitpid(pid, 0)
    header = {"version": 2, "width": cols, "height": rows, "env": {"TERM": env["TERM"], "COLORTERM": env.get("COLORTERM", "")}}
    return header, events


def render(header, events, out, stills, fps=25, ground=(10, 14, 12), default_fg=(215, 215, 215)):
    import pyte
    from PIL import Image, ImageDraw, ImageFont

    cols, rows = header["width"], header["height"]
    cw, ch = 10, 20
    font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 16)
    screen = pyte.Screen(cols, rows)
    stream = pyte.ByteStream(screen)
    names = {"black": (0, 0, 0), "white": (229, 229, 229), "brightblack": (95, 95, 95)}

    def rgb(value, fallback):
        if value == "default":
            return fallback
        if len(value) == 6:
            try:
                return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))
            except ValueError:
                pass
        return names.get(value, fallback)

    def frame():
        img = Image.new("RGB", (cols * cw, rows * ch), ground)
        d = ImageDraw.Draw(img)
        for y in range(rows):
            line = screen.buffer[y]
            for x in range(cols):
                c = line[x]
                fg, bg = rgb(c.fg, default_fg), rgb(c.bg, ground)
                if c.reverse:
                    fg, bg = bg, fg
                box = (x * cw, y * ch, x * cw + cw, y * ch + ch)
                if bg != ground:
                    d.rectangle(box, fill=bg)
                if c.data == "█":
                    d.rectangle(box, fill=fg)
                elif c.data == "▀":
                    d.rectangle((box[0], box[1], box[2], box[1] + ch // 2), fill=fg)
                elif c.data == "▄":
                    d.rectangle((box[0], box[1] + ch // 2, box[2], box[3]), fill=fg)
                elif c.data.strip():
                    d.text((box[0], box[1] + 1), c.data, font=font, fill=fg)
        return img

    frames_dir = out + ".frames"
    os.makedirs(frames_dir, exist_ok=True)
    end = events[-1][0] if events else 0
    i, n, pending = 0, 0, sorted(stills)
    t = 0.0
    last = max([end + 0.5] + [s / 1000 for s in stills])
    while t <= last:
        while i < len(events) and events[i][0] <= t:
            stream.feed(events[i][2].encode("utf-8"))
            i += 1
        img = frame()
        img.save(os.path.join(frames_dir, f"{n:05d}.png"))
        while pending and pending[0] / 1000 <= t:
            img.save(f"{out}-{pending.pop(0)}ms.png")
        n += 1
        t = n / fps
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i", os.path.join(frames_dir, "%05d.png"),
         "-pix_fmt", "yuv420p", "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", out + ".mp4"],
        check=True,
    )
    shutil.rmtree(frames_dir)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("banner")
    p.add_argument("--size", default="120x30")
    p.add_argument("--seconds", type=float, default=9)
    p.add_argument("--out", required=True)
    p.add_argument("--env", action="append", default=[])
    p.add_argument("--render", action="store_true")
    p.add_argument("--stills", default="")
    a = p.parse_args()
    cols, rows = (int(v) for v in a.size.split("x"))
    env = dict(kv.split("=", 1) for kv in a.env)
    header, events = record(a.banner, cols, rows, a.seconds, env)
    with open(a.out + ".cast", "w") as f:
        f.write(json.dumps(header) + "\n")
        for e in events:
            f.write(json.dumps(e) + "\n")
    print(f"{a.out}.cast: {len(events)} events", file=sys.stderr)
    if a.render:
        render(header, events, a.out, [int(s) for s in a.stills.split(",") if s])


if __name__ == "__main__":
    main()
