# Where the information goes

Tell the user once, in the first message, in one line, and answer from this file if they ask more.

| What | Where it goes |
|---|---|
| The original photos and videos | Nowhere. They are only read, on the user's computer (or in Cowork's sandbox), and never changed, moved or uploaded. |
| Everything the scripts make: scan data, thumbnails, contact sheets, previews, the book | The work folder, on the user's computer. Nothing is uploaded. The user may delete the folder when the book is done; the skill never deletes it. |
| What the AI model looks at: small thumbnails on contact sheets, sample sheets, page previews, a photo it opens to check a detail | The company running the AI model the skill is used with, as part of the conversation: **Anthropic** when it runs in Claude (Claude Code, Cowork, claude.ai), or **OpenAI**, Google or another company when the skill runs in their agent (skills follow an open standard). Their privacy terms and the user's account settings apply. |
| What the user types: the story, names, how to recognize people | The same AI company, as part of the conversation. Names go into the book only if the user wants them there. |
| Place names | Only when the user allows looking them up (`group.py --geocode`): the coordinates of each place, rounded to about 1 km, go to OpenStreetMap's Nominatim service. Without it, nothing leaves the computer for places. |
| Faces | Found on the computer by a small bundled model (OpenCV YuNet). No face data leaves the computer, and nobody is identified: the model only finds where faces are. |
| Printing | Nothing. The skill never uploads a file, never sees an address, a phone number, a card or a printer account. The user uploads the PDF and orders on the printer's own site. The order screenshot the user sends goes to the AI company like any image in the conversation. |
| Videos and QR codes | Only if the user uploads a video to a service of their choice; the QR code holds the link they give. |
| Version check | When the skill starts, `doctor.py` reads Rega's public version number from GitHub, to say if a newer version is out. Nothing about the user, the photos or the computer is sent; GitHub sees an ordinary web request. Nothing is installed without the user's yes. Off with `REGA_NO_UPDATE_CHECK=1` (or Claude Code's `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`). |
| Analytics, tracking | None. The scripts send nothing else anywhere. |

In one line, for the first message:
- English: "Your photos stay on your computer. I look at small thumbnails of them, which go to the AI company running me (Anthropic, for Claude), and nothing else is uploaded."
- Hebrew: "התמונות נשארות במחשב שלך. אני רואה תמונות ממוזערות קטנות שלהן, שעוברות לחברה שמפעילה אותי (Anthropic, במקרה של Claude), ושום דבר אחר לא עולה לרשת."
