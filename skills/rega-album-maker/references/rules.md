# The craft: choosing, cropping, words and style

These rules come from real family albums: a two-week road trip of 1,350 photos, a beach-hotel weekend, a baby's
first year. They describe what made people say "this is our book".

## Choosing photos

- **One frame per moment.** A burst of ten nearly identical shots becomes the single best one. Look for eyes
  open, natural smiles, nobody mid-blink or mid-bite, a straight horizon and sharp faces.
- **The person who must look their best** (ask in the brief) gets their best frame in every moment. If they look
  bad in all the frames of a moment, prefer a frame without them over an unflattering one.
- **Couples and groups:** everyone must look good, faces open. Hoods, ponchos and sunglasses pulled over faces
  don't count as a good portrait, even in a dramatic place.
- **Tell the day,** in time order: arriving, the main place, the details (a meal, a sign, a ticket, the car),
  the evening. Mix wide shots with close ones.
- **Weigh the moments.** The sheets show each day moment by moment, and `group.py` marks the key ones: far more
  photos than usual, or a video. Give a key moment, or one the user named, 2–4 frames and make its best frame a
  highlight. A quiet moment gets one frame or none. A day told by its moments reads better than a day told by the
  clock.
- **Choose the frame by the faces.** In a key moment the sheet also shows other frames of the same burst (`B#id`).
  The sharpest frame is not always the one where everyone smiles.
- **Variety beats volume.** Fewer, stronger photos on more white space look better than a crowded page. The
  quota printed by `group.py` follows the page count in the brief. Without one it is about
  `1.6 × √candidates + 1` a day, from 1 to 12.
- **Leave out:** screenshots, documents, receipts with personal data, nudity, injuries, hospitals and medical
  close-ups, and anything embarrassing. If such a moment matters ("we ended up in the ER"), tell it with one
  sentence and a pleasant photo from the same day.
- **Check orientation.** WhatsApp photos taken from above (a plate, a baby on a blanket) are sometimes stored
  sideways. If a thumbnail looks rotated, say so and leave it out, or ask.
- **Suggest what may be missing:** a day with videos but few photos (take a still frame), a WhatsApp folder with
  photos from friends, a second phone.

## Cropping and frames

- Every frame keeps the photo's own shape (4:3, 3:4, 16:9, 9:16). People are never cut at the head, feet or
  hands. That is why `layout.py` places photos with people as "contain".
- Only photos in `no_people` may fill a frame or a whole page ("cover"/"bleed"): landscapes, food, signs, the
  plane wing.
- A cover may zoom into a photo with people only if every head stays whole. When in doubt, don't.

## Words

- **Titles:** 1–3 words, clear and specific. A place ("Gullfoss"), an event ("The wedding"), a thing that
  happened ("First steps"). No vague words such as "slowly" or "magic", and no puns, rhymes, clichés or cute
  phrases: printed, they sound silly.
- **Tags:** `weekday · date · place`, small, generated automatically.
- **Story sentences** appear only where there is a real story, in the family's voice and with real names: "We
  lost the green hat on the second day." Don't describe what the photo already shows, and don't add feelings
  the user didn't express.
- **Hebrew:** address the family in the first person plural ("we went"), keep words plain, and keep Latin names
  (places, flight codes) as they are. The renderer handles the direction.
- **Unknown facts:** whose photo it is, which day an undated photo belongs to, the name of a place. Ask or leave
  out. Never guess on paper.

## Style

The look comes from the structure, style and palette chosen in the brief (`references/design.md`). In all of them:
- **Few type sizes, far apart:** a title, a small label and little else. Thin weights only at large sizes, because
  they vanish in print.
- **One accent colour,** used small: labels, page numbers, a line.
- **No pages of words alone.** A title sits with a photo, on it or beside it.
- **Small graphic elements only when they relate to what happened:**
  - an illustration (rain on a rainy day, a mug at the café stop);
  - the route map of a trip;
  - a boarding pass for a flight;
  - a QR code to a clip.
