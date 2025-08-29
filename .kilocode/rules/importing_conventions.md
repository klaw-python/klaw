# importing_conventions.md

Always favor partial imports over full imports. A few examples of this is:

## Guidelines

- When creating a new python sub-module we'll import `annotations` from `__future__`. An example of this is:

    ```python
    from __future__ import annotations
    ```

- Always favor partial imports over full imports. A few examples of this is:
  - importing from the standard library:

    ```python
    from typing import Any, Optional
    ```

  - Importing from an internal library and/or module:

    ```python
    from claw_umbra import umbra
    ```

  - Importing from a third-party library:

    ```python
    from pydantic import BaseModel
    ```

  - Importing `StringZilla` and using it:
    - `StringZilla` is a library written in `C` so we does not provide `annotations` without  `from __future__ import annotations` statement and importing the whole library before doing partial imports.
    - Example:

      ```python
      from __future__ import annotations
      import stringzilla
      from stringzilla import Str, File

      text_from_str = Str('some-string') # no copies, just a view
      text_from_bytes = Str(b'some-array') # no copies, just a view
      text_from_file = Str(File('some-file.txt')) # memory-mapped file
      ```

- Always export only what we want exposed. A few examples of this is:
  - Exporting a few funcions:

    ```python
    __all__ = [ 'func1', 'func2']
    ```

  - Exporting a class:

    ```python
    __all__ = [ 'MyClass']
    ```

  - Exporting a function and a class:

    ```python
    __all__ = [ 'func', 'MyClass']
    ```

- We'll **NOT** export full modules. For example:
  - We'll **NOT** do:

    ```python
    __all__ = [ 'module1', 'module2']
    ```

  - Instead, we'll do:

     ```python
      from module1 import _func1 as func1
      from module2 import _func2 as func2

      __all__ = [ 'func1', 'func2']
      ```

  - This is because we'll use `mypy` to check the types of the functions we're exporting. This will also help us to avoid circular imports.
