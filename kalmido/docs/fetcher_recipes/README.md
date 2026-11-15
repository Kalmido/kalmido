# Recipes of the receipt fetcher

*Since 2.1188.0 (#6152).*

A receipt fetcher (docs/API.md "Receipt fetcher") asks `GET /api/v1/fetcher/recipes?api=N` at the start of a run for newer
recipes, so a repaired or new portal recipe reaches every helper without a new program version.

This folder holds the recipes Kalmido hands out, in pairs:

- `<id>.py` - the recipe source (UTF-8 text); `<id>` is `a-z 0-9 _`, up to 40 characters
- `<id>.sig.json` - its signature document `{"id", "version", "api", "sha256", "key", "sig"}` (Ed25519, made with the
  maintainers' signing tool; the private key never comes to a server or into this repo)

Kalmido does not check the signature itself (it has no key): it hands out only complete pairs whose `id` is the file name,
whose `api` is the one asked for and whose `sha256` is the hash of the `.py` file. The helper checks the signature with the
public keys built into it and runs nothing that does not check out. An empty folder is fine (`recipes: []`).

A server operator can point `KALMIDO_FETCHER_RECIPES` at another folder.
