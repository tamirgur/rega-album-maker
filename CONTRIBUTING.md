# Contributing

Thank you for helping. Issues and pull requests are welcome at https://github.com/tamirgur/rega-album-maker.

## Privacy first

**Never attach real photos of people** to an issue or a pull request, yours or anyone's. Describe the problem, share
a screenshot of a page only if it shows no one, or reproduce it with the synthetic photos in `evals/`
(`python dev/make_fixtures.py` makes them).

## Before a pull request

Run the checks on your computer:

```
python dev/check_skill.py        # the skill against the Agent Skills spec and the repo's rules
ruff check --select F,E9 --target-version py39 skills/rega-album-maker/scripts dev
python dev/smoke_test.py         # books from the synthetic photos, end to end (needs Chrome or Edge)
python dev/smoke_test.py --all   # every style, before a release
```

For a change in what the AI does (SKILL.md or the references), also run the evals with the AI, as described in
the README, and compare against the last results.

## The rules the code keeps

- **The originals are never written to.** Every script writes only into the work folder.
- **Nothing is invented.** A script never makes up a fact (a place, a date, a name); it leaves it out or asks.
- **Nobody is cropped.** Photos with people keep their own shape unless the face detector knows where the faces are.
- **No network** except the optional OpenStreetMap lookup in `group.py`, with rounded coordinates. No analytics.
- **Python 3.9+.** No syntax newer than 3.9.
- **Styles are designed once and tested.** A new style is a file in `assets/styles/` plus a row in
  `references/design.md`; check it in `python dev/smoke_test.py --all` and look at its pages.

## Releases

Semantic versioning. A release updates, together: `.claude-plugin/plugin.json` (`version`), the `metadata.version` in
`skills/rega-album-maker/SKILL.md`, and a new section at the top of `CHANGELOG.md`; `dev/check_skill.py` fails if
they disagree. Then tag `vX.Y.Z`.
