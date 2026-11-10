# OSCAL schema

`oscal_complete_schema.json` is NIST's OSCAL 1.2.3 complete JSON schema, from the v1.2.3 release of
github.com/usnistgov/OSCAL (a work of the US Government, not subject to copyright in the United States).
`grc oscal validate` and every export are checked against it. To move to a newer OSCAL release, replace the file,
set `OSCAL_VERSION` in `grc/oscal.py`, and run the tests.
