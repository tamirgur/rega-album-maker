# Getting the photos into a folder

The scripts read any folder on the computer. Where the photos come from doesn't matter, but it helps to know each
source's habits.

| Source | How to get a folder | Notes |
|---|---|---|
| iPhone | On a Mac: Photos → select → File → Export Unmodified Original. On Windows: the Photos app's Import, or iCloud for Windows. | HEIC files need `pip install pillow-heif`. Videos are MOV, often HDR (see video.md). |
| Android / Google Photos | For one event: open it in Google Photos (photos.google.com), select the photos or the album, and Download (a zip). For more: Google Takeout (takeout.google.com) → Google Photos → choose albums or years. Or copy DCIM over USB. | Takeout writes a `.json` next to each photo with the time and GPS; `scan.py` reads it when the photo itself has no EXIF. |
| Google Drive, OneDrive, Dropbox | The desktop app shows the cloud as a folder. | With "files on demand", reading a photo downloads it. After the book is done, free the space (right-click → "Free up space" / "Online-only"). |
| WhatsApp | The phone's WhatsApp Images folder, or "Export chat" with media. | The date in the file name is the day **received**, not taken, and EXIF is stripped. The folder also holds many unrelated images. Treat each one as a question. |
| Camera, GoPro, drone | Copy the card's DCIM folder. | Camera clocks are often wrong (another time zone, never set). Compare with phone photos of the same moment and fix with `--shift "GoPro=+3"`. |

The photo folders are only read. Never ask the user to move or rename their originals for the book.

## What the scan handles by itself

Collections differ in their files, how they're built and how they're organized. `scan.py` deals with the common
cases, so you don't have to:

| In the folders | What the scan does |
|---|---|
| Hidden files: macOS `._` copies on a USB drive, Android `.trashed-` photos, `@eaDir`, `$RECYCLE.BIN` | Skips them. The Android ones are photos the user deleted. |
| iPhone Live Photos: `IMG_1234.HEIC` beside a 3-second `IMG_1234.MOV` | Marks the MOV `live`: part of the photo, not a video of its own. |
| The same photo twice: sent on WhatsApp, in two Takeout albums, `IMG_1234 (1).jpg` | Marks the extra ones `copy` of the one with the best date, then the biggest. |
| A night out, a concert, a snowy or sunny beach day | Judges dark and bright against the photos taken within 45 minutes, so only a single bad frame is flagged. |
| RAW files (CR2, NEF, ARW, DNG…) | Counts them and leaves them unread. Use the JPEGs the camera saved beside them, or export JPEGs. |
| WhatsApp stickers, thumbnails, tiny downloads | Marks them `small` (under 600 px): too small to print. |
| Folders by event or by person ("Naxos", "Dad's phone") | Keeps each file's folder. The overview lists the folders, and a folder name often names the place or the event. |
| Several phones and cameras | Lists the cameras. If one camera's clock is off, compare it with a phone photo of the same moment, then use `--shift`. |

## Dates and times

`scan.py` takes the best date it can find, in this order:
1. EXIF "date taken" (cameras and phones; this is local time)
2. the iPhone video creation date (local time)
3. a Google Takeout sidecar, or a video's UTC creation time, converted with `--tz`
4. the file name:
   - `20240711_123456`, `IMG_20240711_123456`, `2024-07-11 12.34.56`: local time;
   - `PXL_20240711_093015123` (Pixel): **UTC**, converted with `--tz`;
   - `IMG-20240711-WA0003`, `WhatsApp Image 2024-07-11 at 12.34.56`: the day received;
5. the file's modified time: flagged `undated`, often wrong after copying

When EXIF holds a time-zone offset, the most common one becomes the default `--tz`. For a trip to another time
zone with a Pixel phone, pass `--tz` explicitly (for example `--tz 0` in London in winter, `--tz 2` in Rome in summer).

A day runs from 04:00 to 04:00, so a photo at 01:30 belongs to the evening before.

## Big folders

20,000 files take a few minutes, using every core but one (`--workers` to change). Thumbnails are cached in the
work folder, so a second run is quick. Use `--from` and `--to` whenever the folder holds more than the book's
period: everything outside the dates is ignored.
