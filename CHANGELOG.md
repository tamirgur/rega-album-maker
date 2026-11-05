# Changelog

All notable changes to Rega – AI Album Maker. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versions follow [Semantic Versioning](https://semver.org/).

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
