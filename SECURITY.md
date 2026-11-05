# Security and privacy

Rega – AI Album Maker handles family photos, so privacy problems are treated as security problems.

## Reporting

Please **don't open a public issue** for a security or privacy problem (for example a script that writes outside the
work folder, sends data somewhere it shouldn't, or exposes photos). Report it privately through GitHub's
**Security > Report a vulnerability** on https://github.com/tamirgur/rega-album-maker, or open an issue that only
says you have something to report privately, with no details.

Never include real photos of people in a report.

## What the skill promises

- The original photos are only read, never written, moved or uploaded.
- Everything it makes stays in the work folder on the user's computer.
- The only network request the scripts make is the optional place-name lookup at OpenStreetMap, with coordinates
  rounded to about 1 km.
- It never asks for an address, a payment card, a password or an API key.

What the AI model sees goes to the company running it: see `skills/rega-album-maker/references/privacy.md`.

## Supported versions

The latest release receives fixes.
