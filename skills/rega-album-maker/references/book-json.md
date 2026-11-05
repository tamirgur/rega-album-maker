# brief.json, selection.json and book.json

## Contents
- brief.json: the user's answers, one section per stage
- selection.json: the photos you chose, by chapter
- book.json: the pages, made by layout.py
- Chapters: how to divide the book

## brief.json (the user's answers, one section per stage)

`brief.py --init` starts it. You fill the sections as the rounds are answered (`references/questions.md`), and
`brief.py` checks them.

```json
{
  "folders": ["D:/Photos/Greece 2025", "D:/Photos/WhatsApp Images"],
  "scope": {"from": "2025-08-03", "to": "2025-08-09", "days": null, "places": null, "topic": null},
  "story": {"moments": ["the boat to the caves", "Dana's birthday dinner"],
            "people": [{"name": "Dana", "looks": "short dark hair, red hat"}], "best": "Dana"},
  "book": {"title": "נקסוס", "lang": "he", "kind": "trip", "chapters": "day"},
  "print": {"printer": "prodigi", "sku": "BOOK-FE-8_3-SQ-HARD-G", "gutter_mm": 6, "copies": 1, "country": "IL"},
  "format": {"size": "prodigi-BOOK-FE-8_3-SQ-HARD-G", "w": 210, "h": 210, "pages": 36, "min_pages": 24, "max_pages": 300},
  "design": {"structure": "journal", "style": "nordic", "palette": "style",
             "elements": {"route_map": true, "illustrations": true, "badges": true, "callouts": true, "qr": false}},
  "confirmed": true,
  "approved": false
}
```

| Field | Meaning |
|---|---|
| `folders` | The photo folders, read only. |
| `scope` | What goes in. `null` in a field means everything. `from`/`to` must match the scan's `--from`/`--to`. |
| `story` | The moments the user named, the people and how to recognize them, and who must look their best. |
| `book.kind` | `trip`, `event`, `baby`, `year` or `other`. Day badges appear only in a trip's journal. |
| `print` | Written by `printer.py --choose` (the product, its pages, the part of the fold it hides), or `{"printer": "other", "name": "..."}`, or `{"printer": "none"}`. |
| `book.chapters` | `day`, `part` (parts of one day) or `month`. See "Chapters" below. |
| `format.pages` | Inside pages, even. `group.py` scales the quotas to it, and `layout.py` builds exactly that many pages. `w`, `h`, `min_pages` and `max_pages` come from the printer's product. |
| `design.structure` | `album`, `journal` or `magazine` (`references/design.md`). |
| `design.style` | One of the 15 styles in `assets/styles`, or a style file in the work folder (`{"base": "nordic", ...}`). |
| `design.palette` | `style` (the style's own), a palette from `assets/palettes.json`, or a brand `{"accent": "#..."}`. |
| `design.elements` | Switch elements off with `false`: `route_map`, `illustrations`, `badges`, `callouts`, `qr`. |
| `confirmed` | `true` once the user said yes to the brief. Build nothing before. |
| `approved` | `true` once the user approved the preview. |


## selection.json (you write it, after choosing)

```json
{
  "title": "Graduation",
  "subtitle": null,
  "cover": 31,
  "closing": 48,
  "no_people": [35],
  "pass": null,
  "chapters": [
    {"title": "Before", "photos": [2, 4, 5, 7, 9, 12], "highlights": [9], "quiet": [], "details": [],
     "story": null, "illustration": "mug", "qr": null, "deck": null},
    {"title": "The ceremony", "photos": [31, 33, 35, 38, 40, 41], "highlights": [38, 31], "details": [],
     "story": "My grandparents came with me to the ceremony.",
     "callout": {"photo": 35, "at": [0.62, 0.4], "text": "The certificate", "ill": null}},
    {"title": "The evening", "photos": [44, 46, 47], "details": [46]}
  ]
}
```

| Field | Meaning |
|---|---|
| `title`, `subtitle` | The book's title, 1–3 words. The subtitle defaults to the date range. They go on the cover, the first page and the back. |
| `cover` | The cover photo. It fills the top of the cover when a crop is safe; otherwise it is shown whole. |
| `closing` | The photo on the last page. Without one, the last photo of the last chapter closes the book. |
| `no_people` | Photos with nobody in them: they may be cropped to fill a frame. Never a document. |
| `pass` | Optional: a boarding pass on the route page (`from`, `via`, `to`, `date`). |
| `chapters[].title` | 1–3 words. It opens the chapter: on the photo, in a band or a column beside it, or above the first photos. |
| `chapters[].photos` | The ids in story order. |
| `chapters[].highlights` | The best frame of each key moment, or of a moment the user named: a page of its own, to the edge when it can be. The first one may open the chapter across a spread. |
| `chapters[].quiet` | Tender moments: alone, with air around them. |
| `chapters[].details` | Documents, certificates, tickets: whole, on a dark page. |
| `chapters[].story` | Optional: one real sentence, in the family's voice. |
| `chapters[].deck` | Optional: the small line under the title. Generated as `weekday · date · place` when left out. |
| `chapters[].illustration` | Optional, from `assets/illustrations.json`: balloon, bandaid, cake, camera, car, fish, heart, lifering, moon, mountain, mug, palm, pin, plane, popsicle, rain, sheep, sprig, sprout, star, sun, sunflower, tent, waterfall, watermelon. Only for something that really happened in the chapter. |
| `chapters[].callout` | Optional: a note with a hand-drawn arrow to a real detail in a photo of this chapter. `at` is the detail's place in the photo (0–1 across, 0–1 down). Placed only where the page has room. |
| `chapters[].tint` | Optional: a page colour for this chapter, such as `slate` for an evening. |
| `chapters[].qr` | Optional: `{"url": "...", "label": null}`, a link the user gave you. |

Older selections with `days` instead of `chapters` still work: each day becomes a chapter.

## book.json (made by layout.py)

Every page has a template (`tpl`), its side (`r` or `l`), a background, and lists of `frames`, `texts`, `shades`
and `items` in mm in the page's own coordinates. A frame gives the visible box (`clip`) and where the photo sits
behind it (`img`). `rules` holds the result of every design rule. Don't edit it by hand: change `selection.json` or
the brief and run `layout.py` again.

## Chapters

A chapter is any part of the story with a title. Divide the book the way the user thinks of it:

| The book is | Chapters | Example |
|---|---|---|
| a trip | one a day, or one a place | "Rome", "Florence" |
| one event (a wedding, a ceremony) | the parts of the day | "Before", "The ceremony", "The evening" |
| a year (a baby's first) | one a month or a season | "January", "Spring" |

The small line under a title (`deck`) is generated from the photos' first day: `weekday · date · place`, or the
date range for a chapter that spans days. To set it yourself, give `deck`.
