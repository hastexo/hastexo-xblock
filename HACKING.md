Developer notes
===============

This document is for maintainers of this package.

How to cut a release
--------------------

This repository uses
[bumpversion](https://pypi.org/project/bumpversion/) for managing new
releases.

Before cutting a new release, open `Changelog.md` and add a new
section like this:

```markdown
Unreleased
----------

* [Bug fix] Description of bug fix
* [Enhancement] Description of enhancement
```

Commit these changes on `master` as you normally would.

Then, use `bumpversion` to increase the version number:

-   `bumpversion patch`: creates a new point release (such as 3.6.1)
-   `bumpversion minor`: creates a new minor release, with the patch level set to 0 (such as 3.7.0)
-   `bumpversion major`: creates a new major release, with the minor and patch levels set to 0 (such as 4.0.0)

This creates a new commit, and also a new tag, named `v<num>`, where
`<num>` is the new version number.

Push these two commits (the one for the changelog, and the version
bump) to `origin`. Make sure you push the `v<num>` tag to `origin` as
well.

Then, build a new `sdist` package, and [upload it to
PyPI](https://packaging.python.org/tutorials/packaging-projects/#uploading-the-distribution-archives)
(with [twine](https://packaging.python.org/key_projects/#twine)):

```bash
rm dist/* -f
./setup.py sdist
twine upload dist/*
```
