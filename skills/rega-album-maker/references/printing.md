# Printing the book

Every print service has its own exact sizes, page counts and file rules. Check its "file specifications" page
before rendering, and order **one copy first, as a proof**. The skill prepares files and guides only: it takes no
responsibility for the print, the price, the delivery or an order, and it recommends no printer.

## Prodigi

Prodigi is built in because it ships worldwide, Israel included, and takes a ready PDF; that is all. `assets/printers/prodigi.json`
holds its photo books and magazines (40 products, captured on the date in the file): hardcover (24–300 pages),
softcover (20–300), layflat (18–122, nothing lost at the fold) and magazine (20–500), in A5, A4, Letter, 21×21 and
12×12 inch sizes.

- `printer.py --list` shows them; `printer.py --work W --choose SKU` sets the exact size, the page range and the
  fold (about 6 mm hidden in a glued book) before the layout.
- Their file: one PDF of single pages, page 1 the front cover, the last page the back cover, exactly the trim size,
  no bleed, no crop marks, 10 mm safe area, 300 DPI, RGB, an even page count. Prodigi adds the blank inside covers.
- Prodigi binds on the left: a Hebrew book is uploaded mirrored, and `printer.py --pack` does it.
- The spine is set in the order form, not in the file: text, font, size, background and text colour. **It does not
  take Hebrew:** use English or numbers, or colour only. Under 40 pages, colour only.
- The catalogue price includes a base page count; extra pages and shipping are added. The order summary on their
  site is the only exact price.
- **Before paying, the user sends a screenshot of the order summary**, and you check it against the guide: product
  and code, size, cover and paper, page count, copies, spine, country.
- Production takes about five working days, then shipping. The user places the order and pays in their own
  account: never ask for an address, a card or an API key.

## Sizes

| Preset | Trim size | Typical minimum inside pages |
|---|---|---|
| `square-21` | 210 × 210 mm | 24 |
| `square-30` | 300 × 300 mm | 24 |
| `a5-portrait` | 148 × 210 mm | 20 |
| `a5-landscape` | 210 × 148 mm | 20 |
| `a4-portrait` | 210 × 297 mm | 24 |
| `a4-landscape` | 297 × 210 mm | 24 |
| a Prodigi product | its exact size, from `printer.py --choose` | its own range |

Offered: the square sizes and the portrait ones. Landscape pages (`a4-landscape`, `a5-landscape`) remain only for
books made with an earlier version: in most styles they left too much empty space.
| custom | `layout.py --w 203 --h 203` | `--min-pages N` |

If the service's size is slightly different (8 × 8 in = 203 mm, or 8.3 in = 211 mm), use its exact numbers with
`--w` and `--h`.

## The file

- `book.pdf` = front cover, the inside pages, back cover. Many services (including Prodigi's photo books) want
  exactly this: page 1 is the front cover and the last page is the back.
- **Separate cover:** some services take the cover as its own file, often a wrap with the spine. Use
  `render.py --interior-only` for the pages, and build the cover in their online editor.
- **Even page count:** always required. `layout.py` takes care of it.
- **Bleed:** if the service asks for it (often 3 mm), run `render.py --bleed 3`. Photos that touch the page edge
  extend into the bleed. Without bleed the file is exactly the trim size, which is what Prodigi expects.
- **Safe area:** text and faces stay 10 mm from the edge, and 15 mm on the binding side (the layout does this).

## Hebrew books and the binding side

Most international printers bind on the **left** only. A Hebrew book opens from the right. The fix:
`render.py --left-binding` writes `book-print-left-binding.pdf`, with the back cover first, then the inside pages
from last to first, then the front cover. Upload that file. The printer binds "its" first page on the left, and
the book you hold opens from the right with every page in place. Israeli services that bind Hebrew books on the
right take the normal `book.pdf`.

## Resolution and color

- **Resolution:** 300 DPI at the printed size is ideal, 200 and above is fine, and 150–199 is visible on close
  inspection. Below 150, use a smaller frame or another photo. `layout.py` and `check.py` report each photo's
  DPI.
- **Color:** photos are converted to sRGB. Paper is darker and less saturated than a screen: a photo that is
  already dark on screen prints darker still, so avoid very dark frames.
- **Deep page colors** (the `slate` evening tint) can print greyer than on screen. Look at the proof copy.

## QR codes

- At least 18 mm wide, with a white margin (the quiet zone). Keep the square corner markers: rounded markers
  failed to scan in a printed book.
- `check.py` decodes every code from the PDF itself. Before ordering, also scan the screen preview with two
  phones.
- The link must open for anyone. On OneDrive and Google Drive, set "anyone with the link" and "can **view**":
  OneDrive's share dialog defaults to "can edit". Open the link in a private browser window to test it.
- Never print a code to a placeholder. If the video isn't uploaded yet, leave the QR out and add it in a second
  printing.

## Ordering

- Upload the PDF in the service's website. Most consumer services accept a ready PDF.
- A print API (Prodigi and others) needs the PDF at a public download URL. A personal OneDrive or Google Drive
  link usually isn't a direct download, so the website upload is simpler for one book.
- Before paying, confirm the product, the page count, the shipping method and the total with the user.
