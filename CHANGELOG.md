# Changelog

All notable changes to Rega – AI Album Maker. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versions follow [Semantic Versioning](https://semver.org/).

## [1.0.2] - 2026-11-05

### Fixed
- **The style samples reach the user.** The 15 covers were made but only Claude looked at them, so the user chose a
  style by name. Every sample image now opens on the user's screen by itself (in Cowork, a link is given), and
  Claude asks for the choice only after, by the numbers in the image.

### Changed
- The samples are made from the scan's thumbnails, several at once: faster, and no original photo is downloaded
  from the cloud just for a sample.
- One line says why the samples are made, and "you decide" skips them.
- A general rule in the skill: the user sees only what is opened for them or linked, never what Claude reads.

## [1.0.1] - 2026-11-05

From a real trip book (a visit to Florence), where the second version came out much better than the first.

### Added
- **The journey map.** The route page can show the trip as the user told it (`journey` in `selection.json`): every
  stop named, the whole way from home with the destination marked, each leg drawn by how it was travelled (a flight
  as an arc, a train as a line, a drive as dots) and a small legend. It is drawn on the page in the book's colours,
  never tone-graded like a photo, and needs no GPS. The boarding pass is left out when the legend tells the same.
- A design rule: a story sentence never runs into a photo.

### Fixed
- On a page full of photos, the story sentence now gets its own room under the photos; before, a tall photo could
  run into it.
- A journal no longer prints an hour taken from a WhatsApp photo (the day it was received) or a file date: those
  photos simply get no hour, and can stay in the book.

## [1.0.0] - 2026-11-05

**Beta: the first public version.** Feedback is welcome:
[tell us how your book went](https://github.com/tamirgur/rega-album-maker/issues/new?template=feedback.yml).

- **Ten stages**, each telling the user where they are and what is needed from them, with iron rules: nothing of the
  user's is deleted, moved, renamed or changed without an explicit yes, and only the folders the user gave are read.
- **Photos from everywhere:** phones, WhatsApp, cameras, Google Takeout and cloud folders. Duplicates, blurry shots,
  screenshots and Live Photo videos are set aside without deleting anything; dates and places only when sure.
- **The story:** the days, places and moments are found first, then the days are walked through with the user in a few
  light questions.
- **The look in three levels:** a structure (album, journal, magazine), a style (15) and a palette (10, from the
  photos or a brand), each shown on the user's own photos first. Square (21, 30 cm) and portrait (A4, A5) books.
- **Elements made only from real facts:** a route map with place names, a boarding pass, day badges, a date stamp,
  illustrations, a callout arrow to a real detail.
- **Any language,** right to left included; English and Hebrew built in.
- **Printing:** Prodigi or any printer, with the file to upload, an order guide, a screenshot check before paying and
  a disclaimer. Each book has its own folder in an "Albums" folder, and a new version never replaces an earlier one.
- **Privacy:** photos stay on the computer; what goes where is listed in `references/privacy.md`.
- **Feedback from inside the skill:** when the book is done, Rega offers once to prepare a short feedback note; when
  something goes wrong, it offers an issue. Both are drafted without photos, names or paths, shown to the user first,
  and sent by the user, never by Rega.
- **Updates:** `doctor.py` says in one line when a newer version is out; the README explains how to turn on
  auto-update.
- Made for Windows, macOS and Linux with Python 3.9 or later, in Claude Code and Cowork.
