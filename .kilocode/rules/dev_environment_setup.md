# dev_environment_setup.md

Dev environment setup

## Guidelines

- We're using `uv` as our package manager.

  - You we have the docs in markdown format in [`uv`](../../.reference/docs/uv/docs/index.md).

  - We're creating a project with multiple packages in the same repo. We'll use `uv` to create the packages and `uv` to manage the dependencies. You can read more about projects in [`projects`](../../.reference/docs/uv/docs/concepts/projects/index.md).

- We're using `ruff` as our linter and formatter. You can read more about it in [`ruff`](../../.reference/docs/ruff/docs/index.md). We're using `ruff` to lint our code, but we're also using the `VSCode` extension facilitate the use of `ruff`. our settings. An example of this is:
  - Example config for the `VSCode` extension:

    ```json

    "ruff.path": [ "/Users/wrath/projects/klaw/.venv/bin/ruff" ],
    "ruff.interpreter": [
        "/Users/wrath/projects/klaw/.venv/bin/python"
    ],
    "ruff.configuration": "home/wrath/klaw/ruff.toml",
    "ruff.nativeServer": "on",
    "ruff.organizeImports": true,
    "ruff.configurationPreference": "filesystemFirst",
    "ruff.importStrategy": "fromEnvironment",
    "ruff.enable": true,
    "ruff.trace.server": "messages",
    "ruff.showSyntaxErrors": true,
    "[python]": {
        "editor.formatOnSave": true,
        "editor.codeActionsOnSave": {
            "source.fixAll.ruff": "explicit",
            "source.organizeImports.ruff": "explicit"
        },
        "editor.defaultFormatter": "charliermarsh.ruff"
    },

    ```

  - Example ruff.toml:

    ```toml
    # Copied from https://github.com/dry-python/returns/blob/master/pyproject.toml 

    # Exclude a variety of commonly ignored directories.
    exclude = [
        ".bzr",
        ".direnv",
        ".eggs",
        ".git",
        ".git-rewrite",
        ".hg",
        ".ipynb_checkpoints",
        ".mypy_cache",
        ".nox",
        ".pants.d",
        ".pyenv",
        ".pytest_cache",
        ".pytype",
        ".ruff_cache",
        ".svn",
        ".tox",
        ".venv",
        ".vscode",
        "__pypackages__",
        "_build",
        "buck-out",
        "build",
        "dist",
        "node_modules",
        "site-packages",
        "venv",
    ]

    target-version = "py313"
    line-length = 120

    preview = true
    fix = true
    format.quote-style = "single"
    format.docstring-code-format = false
    lint.select = [
      "A",    # flake8-builtins
      "B",    # flake8-bugbear
      "C4",   # flake8-comprehensions
      "C90",  # maccabe
      "COM",  # flake8-commas
      "D",    # pydocstyle
      "DTZ",  # flake8-datetimez
      "E",    # pycodestyle
      "ERA",  # flake8-eradicate
      "EXE",  # flake8-executable
      "F",    # pyflakes
      "FBT",  # flake8-boolean-trap
      "FLY",  # pyflint
      "FURB", # refurb
      "G",    # flake8-logging-format
      "I",    # isort
      "ICN",  # flake8-import-conventions
      "ISC",  # flake8-implicit-str-concat
      "LOG",  # flake8-logging
      "N",    # pep8-naming
      "PERF", # perflint
      "PIE",  # flake8-pie
      "PL",   # pylint
      "PT",   # flake8-pytest-style
      "PTH",  # flake8-use-pathlib
      "PYI",  # flake8-pyi
      "Q",    # flake8-quotes
      "RET",  # flake8-return
      "RSE",  # flake8-raise
      "RUF",  # ruff
      "S",    # flake8-bandit
      "SIM",  # flake8-simpify
      "SLF",  # flake8-self
      "SLOT", # flake8-slots
      "T100", # flake8-debugger
      "TRY",  # tryceratops
      "UP",   # pyupgrade
      "W",    # pycodestyle
      "YTT",  # flake8-2020
    ]
    lint.ignore = [
      "A005",   # allow to shadow stdlib and builtin module names
      "COM812", # trailing comma, conflicts with `ruff format`
      # Different doc rules that we don't really care about:
      "D100",
      "D104",
      "D106",
      "D203",
      "D212",
      "D401",
      "D404",
      "D405",
      "ISC001",  # implicit string concat conflicts with `ruff format`
      "ISC003",  # prefer explicit string concat over implicit concat
      "PLR09",   # we have our own complexity rules
      "PLR2004", # do not report magic numbers
      "PLR6301", # do not require classmethod / staticmethod when self not used
      "TRY003",  # long exception messages from `tryceratops`
    ]
    lint.per-file-ignores."*.pyi" = [ "D103" ]
    lint.per-file-ignores."returns/context/__init__.py" = [ "F401", "PLC0414" ]
    lint.per-file-ignores."returns/contrib/mypy/*.py" = [ "S101" ]
    lint.per-file-ignores."returns/contrib/mypy/_typeops/visitor.py" = [ "S101" ]
    lint.per-file-ignores."returns/contrib/pytest/__init__.py" = [ "F401", "PLC0414" ]
    lint.per-file-ignores."returns/interfaces/*.py" = [ "S101" ]
    lint.per-file-ignores."returns/methods/__init__.py" = [ "F401", "PLC0414" ]
    lint.per-file-ignores."returns/pipeline.py" = [ "F401", "PLC0414" ]
    lint.per-file-ignores."returns/pointfree/__init__.py" = [ "F401", "PLC0414" ]
    lint.per-file-ignores."returns/primitives/asserts.py" = [ "S101" ]
    lint.per-file-ignores."tests/*.py" = [
      "RUF029", # allow async functions to not use `await`
      "S101",   # asserts
      "S105",   # hardcoded passwords
      "S404",   # subprocess calls are for tests
      "S603",   # do not require `shell=True`
      "S607",   # partial executable paths
    ]
    lint.per-file-ignores."tests/test_examples/*" = [ "D102" ]
    lint.per-file-ignores."tests/test_examples/test_maybe/test_maybe_pattern_matching.py" = [
      "D101",
      "D103",
      "F811",
    ]
    lint.per-file-ignores."tests/test_examples/test_result/test_result_pattern_matching.py" = [
      "D103",
    ]
    lint.per-file-ignores."tests/test_pattern_matching.py" = [ "S101" ]
    lint.external = [ "WPS" ]
    lint.flake8-quotes.inline-quotes = "single"
    lint.mccabe.max-complexity = 6
    lint.pep8-naming.staticmethod-decorators = [ "law_definition", "staticmethod" ]
    lint.pydocstyle.convention = "google"
    ```
  
- We're using `mypy` as our type checker. You can read more about it in [`mypy`](../../.reference/docs/mypy/README.md). We're using `mypy` to type check our code, but we're also using the `VSCode` extension facilitate the use of `mypy`. An example of our mypy settings is:
  - Example config for the `mypy.ini` file:

    ```ini
    # In setup.cfg or mypy.ini:
    [mypy]

    python_version = 3.13
    exclude = .venv
    strict_equality=True
    disallow_untyped_defs = True
    plugins =
      mypy.plugins.proper_plugin,
      returns.contrib.mypy.returns_plugin,

    enable_error_code =
      truthy-bool,
      truthy-iterable,
      redundant-expr,
      # We don't want "Are you missing an await?" errors,
      # because we can't disable them for tests only.
      # It is passed as a CLI arg in CI.
      # unused-awaitable,
      # ignore-without-code,
      possibly-undefined,
      redundant-self,

    disable_error_code = empty-body, no-untyped-def

    # We cannot work without explicit `Any` types and plain generics:
    disallow_any_explicit = false
    disallow_any_generics = false

    follow_imports = silent
    ignore_missing_imports = true
    strict = true
    strict_bytes = true
    warn_unreachable = true

    # TODO: Enable this later, it's disabled temporarily while we don't discover why
    # the explicit restriction on `typeshed.stdlib.unittest.mock`,
    # which is the next section, is not working properly when running
    # with `pytest`.
    disallow_subclassing_any = False
    
    exclude = ['.*test_.*pattern_matching']

    [mypy-typeshed.stdlib.unittest.mock]
    disallow_subclassing_any = False
    ```

- We're using `pytest` as our test runner. You can read more about it in [`pytest`](../../.reference/docs/pytest/doc/en/builtin.rst)
  - Example config for the `pytest.ini` file:

    ```ini
    [pytest]
    # ignores some directories:
    norecursedirs = *.egg .eggs dist build docs .git __pycache__ src .venv .tox .mypy_cache .ruff_cache .pytest_cache .vscode .github .DS_Store

    # Active the strict mode of xfail
    xfail_strict = true

    # Adds these options to each `pytest` run:
    addopts =
      --strict-markers
      --strict-config
      --doctest-modules
      --doctest-glob='*.rst'
      # pytest-mypy-plugin:
      --mypy-ini-file=mypy.ini

    # Ignores some warnings inside:
    filterwarnings =
      ignore:coroutine '\w+' was never awaited:RuntimeWarning    
    
    testpaths =
      */tests
      */tests_*
      */test_*
      */*/tests
      */*/tests_*
      */*/test_*
    ```

- We're using `pre-commit` as our pre-commit hook. Here a basic example of the `pre-commit` config file:
  - Example config for the `pre-commit` config file:

    ```yaml
    exclude: |
      (?x)^(
          .*\{\{.*\}\}.*|     # Exclude any files with cookiecutter variables
          docs/site/.*|       # Exclude mkdocs compiled files
          \.history/.*|       # Exclude history files
          .*cache.*/.*|       # Exclude cache directories
          .*venv.*/.*|        # Exclude virtual environment directories
      )$
    fail_fast: true
    default_language_version:
      python: python3.12
    default_install_hook_types:
    - pre-commit
    - commit-msg

    repos:
    # Linting & Formatting
    - repo: https://github.com/astral-sh/ruff-pre-commit
      # Ruff version.
      rev: v0.11.13
      hooks:
      # Run the linter.
      - id: ruff
        name: 🔧 ruff · lint
        types_or: [ python, pyi ]
        args: [ --fix ]
      # Run the formatter.
      - id: ruff-format
        name: 🔧 ruff · format
        types_or: [ python, pyi ]

    # Data & Config Validation 
    - repo: https://github.com/python-jsonschema/check-jsonschema
      rev: 0.33.0
      hooks:
      - id: check-github-workflows
        name: "🐙 github-actions · Validate gh workflow files"
        args: [ "--verbose" ]
      - id: check-taskfile
        name: "✅ taskfile · Validate Task configuration"

    #Markdown 
    - repo: https://github.com/hukkin/mdformat
      rev: 0.7.22
      hooks:
      - id: mdformat
        name: "📝 markdown · Format markdown"
        additional_dependencies:
        - mdformat-gfm
        - mdformat-ruff
        - mdformat-frontmatter
        - ruff
      # Test formatting
    - repo: local
      hooks:
      - id: pytest-collect
        name: 🧪 test · Validate test formatting
        entry: ./.venv/bin/pytest test
        language: system
        types: [ python ]
        args: [ "--collect-only" ]
        pass_filenames: false
        always_run: true

      # Tests Fast
      - id: pytest-fast
        name: 🧪 test · Run fast tests
        entry: ./.venv/bin/pytest test
        language: system
        types: [ python ]
        pass_filenames: false
        always_run: true

    # Verify web stuff
    - repo: https://github.com/biomejs/pre-commit
      rev: v2.0.0-beta.5 # Use the sha / tag you want to point at
      hooks:
      - id: biome-check
        name: "🕸️ javascript · Lint, format, and safe fixes with Biome"

    # Optimize images
    - repo: https://github.com/shssoichiro/oxipng
      rev: v9.1.4
      hooks:
      - id: oxipng
        name: 📸 images · optimize
        args: [ "-o", "4", "--strip", "safe", "--alpha" ]

    # Dependency management
    - repo: https://github.com/astral-sh/uv-pre-commit
      # uv version.
      rev: 0.7.13
      hooks:
      - id: uv-lock
        name: "🔒 uv-lock · Lock dependencies"
      - id: uv-export
        name: "🔗 uv-export · Export dependencies"
    ```
