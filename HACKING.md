Developer notes
===============

This document is for people who maintain and contribute to this
repository.


How to run tests
----------------

This repo uses [tox](https://tox.readthedocs.io/) for unit and
integration tests. It does not install `tox` for you, you should
follow [the installation
instructions](https://tox.readthedocs.io/en/latest/install.html) if
your local setup does not yet include `tox`.

You are encouraged to set up your checkout such
that the tests run on every commit, and on every push. To do so, run
the following command after checking out this repository:

```bash
git config core.hooksPath .githooks
```

Once your checkout is configured in this manner, every commit will run
a code style check (with [Flake8](https://flake8.pycqa.org/)), and
every push to a remote topic branch will result in a full `tox` run.

In addition, we use [GitHub
Actions](https://docs.github.com/en/actions) to run the same checks
on every push to GitHub.

*If you absolutely must,* you can use the `--no-verify` flag to `git
commit` and `git push` to bypass local checks, and rely on GitHub
Actions alone. But doing so is strongly discouraged.


How to cut a release
--------------------

This repository uses
[bump2version](https://pypi.org/project/bump2version/) (the maintained
fork of [bumpversion](https://github.com/peritus/bumpversion)) for
managing new releases.

Before cutting a new release, open `Changelog.md` and add a new
section like this:

```markdown
Unreleased
----------

* [Bug fix] Description of bug fix
* [Enhancement] Description of enhancement
```

Commit these changes on `master` as you normally would.

Then, use `tox -e bumpversion` to increase the version number:

-   `tox -e bumpversion patch`: creates a new point release (such as 3.6.1)
-   `tox -e bumpversion minor`: creates a new minor release, with the patch level set to 0 (such as 3.7.0)
-   `tox -e bumpversion major`: creates a new major release, with the minor and patch levels set to 0 (such as 4.0.0)

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

How to add support for new Apache Guacamole versions
----------------------------------------------------

Download the minified `guacamole-common-js` file from [maven](https://repo1.maven.org/maven2/org/apache/guacamole/guacamole-common-js/)
and add it to the `/hastexo/public/js/guacamole-common-js/` directory, prepending the version number
to the `all.min.js` file name, separated by a hyphen ("-").

The desired guacamole version can then be selected via the `guacamole_js_version` setting.

How to add translations
-----------------------

Install the [openedx i18n tools](https://github.com/openedx/i18n-tools) to your venv:
`pip install edx-i18n-tools`

Add translations for a new language:
 * Create the directories for the new language to the `/locale/` directory following the pattern: `<lang>/LC_MESSAGES`, where `<lang>` is one of the locales listed in `hastexo/locale/config.yaml`.
 * Copy the generated `django-partial.po` file to from `hastexo/locale/en/LC_MESSAGES/` to your language's `LC_MESSAGES` folder and name it `text.po`.
 * Edit the `text.po` file to add the translations.
 * Generate the machine readable `text.mo` file by running `i18n_tool generate` command in the `hastexo` directory.
 * The js translations `text.js` file can be generated in a local devstack
    - Make sure have the translation files in the `/locale/` folder and you've built the openedx image
    - inside your LMS container then run: `./manage.py lms compilejsi18n -p hastexo -d text -l <lang> -o <output_path>`
    - copy the content of the generated file from within the LMS container to `hastexo/public/js/translations/<lang>/text.js`, where `<lang>` is one of the supported languages listed in `hastexo/common.py`. (Note the difference of `-` vs `_` compared to the list in `hastexo/locale/config.yaml`)
 * Move your language directory with all it's contents from `hastexo/locale/` to the `hastexo/translations/` directory to make it discoverable for the LMS.

Update existing translations:
 * Run `i18n_tool extract` command in the `hastexo` directory.
 * Move all strings to one file and drop the js file:
    `tail -n +20 locale/en/LC_MESSAGES/djangojs-partial.po >> locale/en/LC_MESSAGES/django-partial.po`
    `rm locale/en/LC_MESSAGES/djangojs-partial.po`
 * Temporarily move your language directory (`<lang>/LC_MESSAGES`) with the translation files to `hastexo/locale`.
 * Compare the changes in the updated `django-partial.po` file to the `text.po` file for your selected language and make changes as needed.
 * Regenerate the `text.mo` file for the the updated `text.po` file by running `i18n_tool generate`
 * Repeat the steps from "Add translations for a new language" section above to regenerate the `text.js` file (if necessary).
 * Move your language directory with all it's contents from `hastexo/locale/` back to the `hastexo/translations/` directory to make it discoverable for the LMS.
