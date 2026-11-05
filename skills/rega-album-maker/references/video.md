# Videos: three ways, by what the computer has

Videos often hold moments that have no photo. A printed QR code next to the day lets the family watch that moment
again. `doctor.py` tells you which way is possible.

## 1. No video tools: a QR code to the video as it is

1. The user uploads the original video:
   - **YouTube, "Unlisted"** works best. Anyone with the link can watch, nobody else finds it, and it plays
     everywhere. To start at the right moment, add the time to the link: `https://youtu.be/VIDEO_ID?t=95` starts
     at 1:35.
   - **Google Drive or OneDrive:** share with "anyone with the link", "can view". Playback depends on the format;
     iPhone HEVC files may not play in every browser.
2. The user pastes the link. Put it on the day in `selection.json`:
   `"qr": {"url": "https://youtu.be/VIDEO_ID?t=95"}`. The label "Watch the clip" (or Hebrew) is added
   automatically.
3. After rendering, `render.py` reports whether each code scans.

Never invent, shorten through a third party, or "fill in later" a link. A code to nowhere can't be fixed on paper.

## 2. With ffmpeg: short clips

A 10–30 second clip of the best moment is nicer to watch than a 4-minute raw video.

```
python <skill>/scripts/clips.py sheet 22 --work "<work>"          # 16 frames with times (22 = the video's id)
python <skill>/scripts/clips.py cut 22 --start 12 --end 27 --work "<work>" [--mute]
```

- **Pick the segment** from the sheet: steady, well lit, the moment itself, not the walk to it.
- **The output:** an MP4, H.264 + AAC, at most 1920 px, 30 fps, sound evened out to -16 LUFS, ready to stream.
  iPhone HDR is tone-mapped to normal colors; without it the clip would look grey and washed out.
- **Mute** when the sound is wind, traffic or strangers' voices.
- The user uploads the clip (as in way 1) and gives you the link.

## 3. A still frame from a video, as a photo

For a moment that only exists on video:

```
python <skill>/scripts/clips.py frame 22 --at 14.5 --work "<work>"
```

The frame joins `scan.json` with a new id, the video's date and place, and the flag `from_video`. Video frames
have fewer pixels than photos (1920 × 1080 at best), so give them a small frame. `layout.py` reports the DPI.

## Privacy

An unlisted or "anyone with the link" video can be watched by anyone who gets the link, including anyone who
holds the book. Don't link videos the family wouldn't show a guest.
