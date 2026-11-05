# How the book is designed

## Contents
- Structures: album, journal, magazine
- Styles: the 15, and what a style file holds
- Palettes: the roles, the 10 palettes, the colour rules
- Elements: the anatomy, the depths, the built-in elements, the bank by kind of book
- The templates
- Decided automatically
- The rules
- Your judgment

A book's look has three levels, chosen by the user in stage 5, in this order. Under all of them sits one common
ground: the rules at the end of this file.

| Level | Decides | Where |
|---|---|---|
| **Structure** | How the story is told: the pace, photos a page, how much is written, how deep the elements go | `assets/structures.json` |
| **Style** | How it looks: type, frames, paper, ornaments, the cover | `assets/styles/*.json` (15) |
| **Palette** | Its colours, by role | `assets/palettes.json` (10) |

`layout.py` merges them (`scripts/looks.py`), plans the pages and checks the rules. You decide the choices in
`selection.json` and the exceptions. You never invent a style per book: the 15 are designed once and tested, so
every book looks studio-made. Your creativity goes into what each page tells and which element tells it.

## Structures

| Structure | Hebrew | The pace | Photos a page | Words | Elements |
|---|---|---|---|---|---|
| `album` | אלבום | Calm: one moment a page, big photos | about 2 | A title and a small tag | Mentions: a small illustration by the title |
| `journal` | יומן | In order, day after day | about 3 | The day, the hours of each page, one real sentence | Cards: a day badge, a stamp, a ticket, an arrow to a detail |
| `magazine` | מגזין | Changes of pace: spreads, grids, quiet pages | about 2 | A big title, a deck | Pages: an opener across a spread, a full-page map |

Defaults by book: `journal` for a trip, `album` for an event, a baby's year or a family year, `magazine` for a big
trip or a year in review. A style that keeps every photo inside the margins (Classic, Kids, Scrapbook...) never
opens across a spread, whatever the structure.

## Styles

| # | Style | Hebrew | The look | Default palette |
|---|---|---|---|---|
| 1 | `minimal` | מינימלי | White, big photos in wide margins, a thin title | neutral |
| 2 | `nordic` | נורדי | A soft tint, photos in tight clusters, a thin title, a small flat illustration | sand |
| 3 | `classic` | קלאסי | Ivory, white mats with a fine gold line, a serif title over a double rule | sand |
| 4 | `vintage` | וינטג' | Grained paper, prints taped in a brown tone, a handwritten title, a date stamp | earth |
| 5 | `kids` | ילדים | Sky blue, thick white rounded frames, confetti, a yellow date tag | vivid |
| 6 | `colourful` | צבעוני | Blocks of a colour from the photos, the title white on the block | photos |
| 7 | `bold` | נועז | Black and white to the edge, one big word | neutral |
| 8 | `natural` | טבעי | Kraft paper, a thin olive line around the photos, a botanical drawing | sage |
| 9 | `newspaper` | עיתון | Photos to the edge, a heavy serif headline, a kicker over a thin rule | neutral |
| 10 | `night` | לילה | Deep slate pages, a thin white line around the photos, the moon | night |
| 11 | `scrapbook` | סקרפבוק | Polaroids, washi tape, handwriting, an arrow to a real detail | sand |
| 12 | `swiss` | שוויצרי | A strict grid, a bar in a colour from the photos, a small bold title | photos |
| 13 | `pastel` | פסטל | Dusty pink and sage, soft arches, rounded corners | pastel |
| 14 | `retro` | רטרו | Cream, seventies stripes, prints in a warm tone | earth |
| 15 | `mosaic` | פסיפס | A tight grid with 2 mm gaps, the title on a tile of colour | photos |

Each style file holds its fonts (all bundled, all OFL), type sizes, margins, frame (`mat`, `polaroid`, `rounded`,
`print`, `retro`, `keyline`, `soft`, `shadow` or none), tilt, tape, paper texture, photo tone (`warm`, `bw`, `retro`,
`soft`), the mark around a chapter title, the page ornaments and the cover. A book may have its own style file in the
work folder: `{"base": "nordic", ...}` with only what changes, for example a brand's font.

**Old or flash photos** look better toned than shown as they are: Vintage (brown), Bold (black and white), Retro
(warm) and Pastel (soft) do it for the whole book.

## Palettes

Every palette fills the same roles, so any palette works with any style:

| Role | Used for |
|---|---|
| `paper`, `tints` | The pages; the tints alternate by chapter in Nordic and Pastel |
| `ink`, `label` | The words; the small words |
| `accent` | The one thing that stands out: a bar, a stamp, a tile, a block |
| `dark` | A night page, a document page |
| `endpaper` | The back cover |
| `ill` | Three colours for decorations: confetti, stripes, tape |

The palettes: `photos` (מהתמונות: the accent and the decoration colours from the book's own photos), `neutral`,
`sand`, `mist`, `sage`, `pastel`, `vivid`, `earth`, `night`, and a brand: `{"accent": "#1f4aa8"}` in the brief, often
with a `logo` file. `"palette": "style"` keeps the style's own. Each style lists the palettes that suit it
(`palettes` in its file); offer those, but the user's choice wins.

Colour rules, kept by every palette:
- one accent on a spread;
- a large block of colour (Colourful, Mosaic, Retro) takes its colour from the photos on that spread;
- words are always readable: light words on a dark page;
- an evening chapter may get the night tint (`"tint": "slate"` in the chapter).

## Elements

Every element has the same anatomy: **a shape, one to three facts, and an optional icon.** The structure decides
its depth, the style its look, the palette its colours. So any new element you think of looks like it belongs.

| Depth | What it is | Examples |
|---|---|---|
| Mention | An icon and a word beside the title or the tag | a flat illustration of something that happened (a cake, a sunflower) |
| Card | A small object on a page, attached to a photo or a title | a day badge, a date stamp, a boarding pass, an arrow from a note to a detail |
| Page | A page made of facts | the route map, a boarding pass with the map |

**Real facts only.** Every fact on an element comes from the metadata (dates, hours, places, the route), from what
the user told you (names, a flight number, the venue), or from what the photos show (the cake on the table). No
fact, no element. Never a made-up flight number, never a placeholder.

The elements built in (`selection.json`, see `book-json.md`):
- **Route map** (page 1 of a trip). With a `journey` (the stops and how each leg was travelled, from the user's
  facts), it shows the whole trip from home, the destination marked, a flight as an arc, a train as a line, a drive
  as dots, and a legend: write one whenever the user told how they got there. Without it, the map follows the
  photos' GPS, and a **boarding pass** (`pass`) can sit under it.
- **Illustration** (`illustration`): from `assets/illustrations.json`, for something that really happened in the
  chapter.
- **Day badge**: automatic in a journal of a trip (`badges`).
- **Date stamp**: automatic in Vintage.
- **Callout** (`callout`): a short note in the page's free space, with a hand-drawn arrow to a real detail in a
  photo: `{"photo": 12, "at": [0.4, 0.6], "text": "the birthday cake", "ill": "cake"}`. `at` is the
  detail's place in the photo, from 0 to 1 across and down: look at the photo to find it. Users love it; one or two
  in a book.
- **QR code** to a video (`qr`): only if the user asks about videos. See `video.md`.

The bank, by kind of book (offer the ones the facts allow):

| Book | Elements |
|---|---|
| Trip | route map, boarding pass, day badges, illustrations of what happened, a callout |
| Event (a bar mitzvah, a wedding, a birthday) | an illustration of a real detail (the cake, the flowers), a callout, the evening's tint |
| A baby's year, a family year | illustrations by season or milestone, a callout to a first (the first shoes) |
| A certificate, a graduation | the document whole on a dark page (`details`), a date stamp |

At most one element on a page, two in a journal. An element is never the biggest thing on a page, except a page
that is the element (the map).

## The templates

| Template | What it does | Needs |
|---|---|---|
| `opener-spread` | A chapter opens across both pages, the title on a calm corner of the photo | A landscape, faces known, a crop that cuts no face and keeps faces out of the fold |
| `band` | A landscape across the full width, off the top edge, the words in a band below | A landscape |
| `side` | A portrait to the full height against the outer edge, a column for the words | A portrait |
| `fill` | 1–4 photos in their own shapes, arranged to fill the page; in Nordic a tight cluster with the title under it | Anything |
| `hero` | One photo fills the page, cropped where it is safe | Faces known, or a photo in `no_people` |
| `quiet` | One photo alone with air: a pause | Anything |
| `jewel` | A document or a detail, whole, on a dark page | A photo in `details` |

Page 1 is the route map or a title page. The last inside page holds the closing photo. Every chapter starts on a
spread. The cover is drawn the style's own way (`cover` in the style file).

## Decided automatically

- **The exact page count.** Pages of one moment are joined or split to reach it.
- **How photos fill a page.** Every arrangement is tried; photos keep their own shape. Framed styles keep room for
  the frame, so frames never overlap.
- **The opener's crop and the title's corner**, calm and covering no one.
- **The fold.** With a printer chosen, the part the binding hides (about 6 mm in a glued book) is kept free of
  faces and words, and the inner margins grow to the printer's safe area.
- **Pacing.** The same single-page layout never twice in a row, also across chapters.

## The rules (`layout.py` prints them; `check.py` lists any that fail)

- the page count the user chose;
- no layout twice in a row;
- edge-to-edge pages within the style's share;
- no crop cuts a face or, with a whole body in the photo, the feet;
- a photo of people is cropped only when its faces are known;
- no face in the fold;
- no title covers a person;
- each photo once inside the book;
- every chapter opens with its title.

**When a rule fails, change the choices, not the rule:** leave a near-duplicate out, mark a document in `details`,
move a highlight, choose more photos or fewer. Then run `layout.py` again.

## Your judgment

| When | Mark |
|---|---|
| The moment the user named, or a key moment from `group.py` | its best frame in `highlights` |
| A tender, quiet moment | `quiet` |
| A document, a certificate, a ticket | `details`, never `no_people` |
| A landscape, food or a sign with nobody in it | `no_people`: it may fill a frame |
| A real detail worth pointing at | a `callout` |
| The same scene three times | keep one |

About one highlight in every four or five pages: when everything is special, nothing is.

**Faces need OpenCV** (`doctor.py` shows it). Without it, photos with people are never cropped and chapters open on
a single page. The detector misses faces turned away and can't see feet: look at the previews.
