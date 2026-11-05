# The question rounds

## Contents
- Round 1: the story (stage 3)
- The walk through the days (stage 3)
- Round 2: print and size (stage 4), with where to keep the albums (stage 1)
- Round 3: design (stage 5)
- The confirmation, the review, the order

Each round is one short message in the user's language (or one AskUserQuestion call where it exists), opening with
the status line, the recommended option first. The wording is given in English and Hebrew; for another language,
say the same thing in it. Skip every question you already have an answer to. If the user says "you decide", take the
defaults below and say in one line what you chose. Free text is needed only for the story.

## Round 1: the story (stage 3, after the overview)

Show the overview first: the days with dates and places, the counts, the sources, what was set aside.

| Question | English | Hebrew | Default |
|---|---|---|---|
| The kind of book | "What kind of book is it: a trip, an event (a wedding, a birthday, a bar or bat mitzvah), a baby's first year, a family year, or something else?" | "איזה ספר זה: טיול, אירוע (חתונה, יום הולדת, בר או בת מצווה), השנה הראשונה של תינוק, שנה משפחתית, או משהו אחר?" | a trip if there are several places, else an event |
| What goes in | "What goes in: everything above, or only part of it, by days, by place ("only Rome") or by subject ("only the kids")?" | "מה נכנס: כל מה שלמעלה, או רק חלק, לפי ימים, מקום ("רק רומא") או נושא ("רק הילדים")?" | everything in the overview |
| People | "Who is in the photos, and how will I recognize each of them? Must someone always look their best?" | "מי מופיע בתמונות ואיך אזהה כל אחד? מישהו חייב להיראות הכי טוב בכל תמונה?" | everyone looks good, no one first |

## The walk through the days (stage 3, after round 1)

One short message per day (quiet days may share one). Open with what you see, so the user only has to add what the
photos can't say, then one or two light questions. Any answer is fine, a word or a page; "skip" is fine too.

| | English | Hebrew |
|---|---|---|
| Opening | "Saturday 3.1, Florence: a museum in the morning, a long lunch, and the lights at night." | "שבת 3.1, פירנצה: מוזיאון בבוקר, ארוחת צהריים ארוכה, ואורות בלילה." |
| Question | "What happened that day? Anything from it that must be in the book?" | "מה היה ביום הזה? יש משהו ממנו שחייב להיכנס לספר?" |
| A detail | "I saw your name on a mailbox there: is that where you stayed?" | "ראיתי את השם שלכם על תיבת דואר: שם גרתם?" |

Don't press: no follow-up on a day the user skipped, and no question the photos answer.

Write:

```json
"book": {"kind": "trip"},
"scope": {"from": "2025-08-03", "to": "2025-08-09", "days": null, "places": ["Naxos"], "topic": null},
"story": {"moments": ["the boat to the caves", "Dana's birthday dinner"],
          "people": [{"name": "Dana", "looks": "short dark hair, red hat"}], "best": "Dana",
          "days": {"2025-08-04": "the boat to the caves; Dana jumped in first"}}
```

Map each moment the user named to a moment in `groups.json` by day, time and place: its best frame becomes a
highlight.

## Round 2: print and size (stage 4)

Ask the printer first; the rest follows from it.

| Question | English | Hebrew | Default |
|---|---|---|---|
| Where to keep the albums (stage 1) | "Where should I keep the albums? I'll make an 'Albums' folder there, with a folder for this book." | "איפה לשמור את האלבומים? אפתח שם תיקייה בשם 'אלבומים', ובה תיקייה לספר הזה." | the Pictures folder |
| Where to print | "Where would you like to print? Prodigi is one option: it ships worldwide and takes a ready file (it's not a recommendation, just convenient). Or another printer, or only a PDF for now." | "איפה תרצה להדפיס? Prodigi היא אפשרות אחת: שולחים לכל העולם, כולל ישראל, ומקבלים קובץ מוכן (לא המלצה, רק נוח). או בית דפוס אחר, או רק PDF בינתיים." | only a PDF for now |
| The product (Prodigi) | "Hardcover, softcover, layflat (opens flat, costs more) or magazine? And which size: 21×21 cm, 30×30, A4 or A5 (portrait)?" Show the options from `printer.py --list`. | "כריכה קשה, רכה, לייפלט (נפתח שטוח, יקר יותר) או מגזין? ואיזה גודל: 21×21, A4, A5?" | hardcover 21×21, gloss |
| Copies and country | "How many copies, and to which country?" (for the price; never the address) | "כמה עותקים, ולאיזו מדינה המשלוח?" | 1, the user's country |
| Pages | "How many pages? 24 (about 40 photos), 36 (about 60, recommended), 48 (about 85). Each extra page costs more." Use the numbers from `brief.py --options`. | "כמה עמודים? 24 (כ־40 תמונות), 36 (כ־60, מומלץ), 48 (כ־85). כל עמוד נוסף מייקר." | the standard option |
| How it is divided | "Divide it by days, by the parts of the event, or by months?" | "לחלק לפי ימים, לפי חלקי האירוע, או לפי חודשים?" | days for a trip, parts for an event, months for a year |
| Language and title | "Which language, and what is the book called (1–3 words)?" | "באיזו שפה, ומה שם הספר (1–3 מילים)?" | the user's language; the place or the event |

Write (`printer.py --choose` writes `print` and the size in `format` itself):

```json
"print": {"printer": "prodigi", "sku": "BOOK-FE-8_3-SQ-HARD-G", "copies": 1, "country": "GB", "...": "..."},
"format": {"size": "prodigi-BOOK-FE-8_3-SQ-HARD-G", "w": 210, "h": 210, "pages": 36, "min_pages": 24, "max_pages": 300},
"book": {"title": "Naxos", "lang": "en", "kind": "trip", "chapters": "day"}
```

Then run `group.py` again, so each day's quota follows the page count and the structure.

## Round 3: design (stage 5)

Show, don't describe: every choice is a picture made by `sample.py` on the user's photos.

| Question | English | Hebrew | Default |
|---|---|---|---|
| Structure | "How should the story be told? An album (the photos tell it, calm), a journal (day after day, with the hours and small cards) or a magazine (big openers, changing pace)?" | "איך לספר את הסיפור? אלבום (התמונות מספרות, רגוע), יומן (יום אחרי יום, עם שעות וכרטיסים) או מגזין (פתיחות גדולות, קצב משתנה)?" | journal for a trip, album for the rest |
| Style | "Here are the 15 styles on your photos. Which 2–3 do you like?" then "And which one?" | "אלה 15 הסגנונות על התמונות שלך. אילו 2–3 מושכים אותך?" ואז "ואיזה מהם?" | Nordic for a trip, Classic for an event, Kids for a child's year, Minimal for the rest |
| Palette | "The style's own colours, or one of these?" (the palettes listed in the style) | "הצבעים של הסגנון, או אחת מאלה?" | the style's own |
| Elements | "I suggest: <list per chapter, each with the fact it uses>. Add or remove anything?" | "אני מציע: <רשימה לפי פרק, ולכל אחד העובדה שהוא משתמש בה>. להוסיף או להוריד?" | the elements the facts allow |

Write:

```json
"design": {"structure": "journal", "style": "scrapbook", "palette": "style", "logo": null,
           "elements": {"route_map": true, "illustrations": true, "badges": true, "callouts": true, "qr": false}}
```

A brand: `"palette": {"accent": "#1f4aa8"}`, and `"logo": "C:/path/logo.png"`.

## The confirmation (stage 6)

A few lines: the folders, what goes in, the moments, the printer and product, size and pages, the structure, style
and palette, the elements. "Shall I go ahead?" / "מאשר?" Then `"confirmed": true`.

## The review (stage 8)

"Here is the preview, with page numbers. What should change? By page number: replace a photo, leave one out, make
one bigger, change a title." / "זו התצוגה המקדימה, עם מספרי עמודים. מה לשנות? לפי מספר עמוד: להחליף תמונה, להוריד,
להגדיל, לשנות כותרת." When they approve: `"approved": true`.

## The order (stage 9, Prodigi)

"The file and the order guide are ready. Before you pay, send me a screenshot of the order summary and I'll check
that everything matches." / "הקובץ והוראות ההזמנה מוכנים. לפני התשלום, צלם מסך של סיכום ההזמנה ושלח לי, ואבדוק
שהכול תואם."
