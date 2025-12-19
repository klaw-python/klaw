#!/usr/bin/env python3
"""Generate API reference documentation for all Klaw workspaces."""

import ast
from pathlib import Path

import mkdocs_gen_files

nav = mkdocs_gen_files.Nav()
root = Path(__file__).parent.parent.parent
docs_dir = root / 'docs'

# Define the Python workspaces to document
python_workspaces = [
    'workspaces/python/klaw-core/src/klaw_core',
    'workspaces/rust/klaw-dbase/klaw_dbase',
]


def get_title(source_path: Path) -> str:
    """Extract title from Python source file."""
    try:
        with Path(source_path).open(encoding='utf-8') as f:
            tree = ast.parse(f.read())
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                return node.name
    except:
        pass
    return source_path.stem


def get_module_info(module_path: Path) -> dict:
    """Extract module information from Python file (module docstring)."""
    if not module_path.exists():
        return {}
    try:
        with Path(module_path).open(encoding='utf-8') as f:
            tree = ast.parse(f.read())
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                description = node.value.value.replace('\n', ' ').strip()
                return {'description': description}
    except:
        pass
    return {}


def clean_description(desc: str) -> str:
    """Clean up description text."""
    return ' '.join(desc.replace('\n', ' ').split())


# Process each workspace
modules_structure = {}
submodules_per_package = {}

for workspace_path in python_workspaces:
    src = root / workspace_path
    if not src.exists():
        continue

    module_name = workspace_path.split('/')[-1]  # e.g., "klaw_result"
    modules_structure[module_name] = set()
    submodules_per_package[module_name] = []

    # Collect top-level submodules (both .py files and packages with __init__.py)
    # For Python packages, skip _ prefixed modules (private by convention)
    # For Rust extension packages (klaw_dbase), include _ prefixed modules (implementation detail naming)
    is_rust_ext = 'rust' in workspace_path

    for item in sorted(src.iterdir()):
        # Skip __init__.py, __pycache__, py.typed
        if item.name.startswith('__') or item.name == 'py.typed':
            continue

        # Skip private modules in Python packages only (not Rust extensions)
        if not is_rust_ext and item.name.startswith('_'):
            continue

        if item.is_file() and item.suffix == '.py':
            # Top-level .py file
            submodule_name = item.stem
            submodule_info = get_module_info(item)
            description = clean_description(submodule_info.get('description', f'Module {submodule_name}'))
            submodules_per_package[module_name].append((submodule_name, description))

        elif item.is_dir() and (item / '__init__.py').exists():
            # Package directory
            submodule_name = item.name
            submodule_info = get_module_info(item / '__init__.py')
            description = clean_description(submodule_info.get('description', f'Package {submodule_name}'))
            submodules_per_package[module_name].append((submodule_name, description))

# Generate the main reference index
with mkdocs_gen_files.open('reference/index.md', 'w') as index:
    index.write('# API Reference\n\n')
    index.write('Welcome to the Klaw API reference documentation.\n\n')

    # Create a single table for all packages
    index.write('| Package   | Description |\n')
    index.write('|-----------|-------------|\n')

    for module_name, submodules in submodules_per_package.items():
        if submodules:  # Only show packages that have submodules
            display_name = module_name

            # Get package description from __init__.py
            workspace_src = None
            for ws_path in python_workspaces:
                if ws_path.endswith(module_name):
                    workspace_src = root / ws_path
                    break

            package_description = f'Package containing {len(submodules)} modules'
            if workspace_src:
                package_init_path = workspace_src / '__init__.py'
                package_info = get_module_info(package_init_path)
                if package_info:
                    package_description = clean_description(package_info.get('description', package_description))

            index.write(f'| [{display_name}]({module_name}/index.md) | {package_description} |\n')

    index.write('\n')

nav['reference'] = 'index.md'

# Generate package index pages
for module_name, submodules in submodules_per_package.items():
    if submodules:
        package_index_path = Path('reference', module_name, 'index.md')
        with mkdocs_gen_files.open(package_index_path, 'w') as fd:
            display_name = module_name
            fd.write(f'# {display_name}\n\n')

            # Check if package has public submodules (non _ prefixed)
            public_submodules = [s for s, _ in submodules if not s.startswith('_')]

            # Add the mkdocstrings directive for the main package
            fd.write(f'::: {module_name}\n')
            fd.write('    options:\n')
            fd.write('      show_submodules: false\n')
            # If no public submodules, show members (e.g., klaw_dbase exports via __init__)
            # If has public submodules, hide members to avoid repetition (e.g., klaw_core)
            if not public_submodules:
                fd.write('      members: true\n')
            fd.write('\n')

            # Only show submodules table if there are public ones
            if public_submodules:
                fd.write('| Module | Description |\n')
                fd.write('|--------|-------------|\n')

                # Find the workspace src to check if submodule is a package or file
                workspace_src = None
                for ws_path in python_workspaces:
                    if ws_path.endswith(module_name):
                        workspace_src = root / ws_path
                        break

                for submodule, description in sorted(submodules):
                    # Skip _ prefixed modules from the index table
                    if submodule.startswith('_'):
                        continue
                    # Check if it's a package (directory) or a module (file)
                    if workspace_src and (workspace_src / submodule).is_dir():
                        fd.write(f'| [{submodule}]({submodule}/index.md) | {description} |\n')
                    else:
                        fd.write(f'| [{submodule}]({submodule}.md) | {description} |\n')
                fd.write('\n')

        nav[*('reference', module_name)] = 'index.md'

# Generate documentation for each Python file and package
for workspace_path in python_workspaces:
    src = root / workspace_path
    if not src.exists():
        continue

    module_name = workspace_path.split('/')[-1]

    # For Python packages, skip _ prefixed modules; for Rust extensions, include them
    is_rust_ext = 'rust' in workspace_path

    for path in sorted(src.rglob('*.py')):
        if path.name in {'__main__.py', '__version__.py'} or path.name.endswith('_test.py'):
            continue

        # Skip private modules in Python packages only (any path component starting with _)
        # But don't skip __init__.py files (they're not private)
        rel_parts = path.relative_to(src).parts
        if not is_rust_ext and any(part.startswith('_') and not part.startswith('__') for part in rel_parts):
            continue

        module_path = path.relative_to(src).with_suffix('')
        doc_path = path.relative_to(src).with_suffix('.md')
        full_doc_path = Path('reference/', module_name, doc_path)

        parts = tuple(module_path.parts)
        if parts[-1] == '__init__':
            parts = parts[:-1]
            doc_path = doc_path.with_name('index.md')
            full_doc_path = full_doc_path.with_name('index.md')

        if not parts:
            continue

        nav[*('reference', module_name), *parts] = doc_path.as_posix()

        try:
            with path.open(encoding='utf-8') as source_file:
                source = source_file.read()
                title = get_title(path) or parts[-1]
        except:
            title = parts[-1]

        with mkdocs_gen_files.open(full_doc_path, 'w') as fd:
            ident = '.'.join((module_name, *parts))
            fd.write(f'# `{ident}`\n\n')
            fd.write(f'::: {ident}\n')
            fd.write('    options:\n')
            fd.write('      members: true\n')
            fd.write('      show_source: true\n\n')

        mkdocs_gen_files.set_edit_path(full_doc_path, path)

# Generate navigation file with correct structure
with mkdocs_gen_files.open('reference/SUMMARY.md', 'w') as nav_file:
    nav_file.write('* [API Reference](index.md)\n')
    for module_name, submodules in sorted(submodules_per_package.items()):
        if submodules:
            display_name = module_name
            nav_file.write(f'  * {display_name}\n')
            nav_file.write(f'    * [{display_name}]({module_name}/index.md)\n')

            # Find the workspace src to check if submodule is a package or file
            workspace_src = None
            for ws_path in python_workspaces:
                if ws_path.endswith(module_name):
                    workspace_src = root / ws_path
                    break

            for submodule, _ in sorted(submodules):
                # Skip _ prefixed modules in navigation (docs still generated, just hidden from nav)
                if submodule.startswith('_'):
                    continue

                # Check if it's a package (directory) or a module (file)
                if workspace_src and (workspace_src / submodule).is_dir():
                    nav_file.write(f'    * [{submodule}]({module_name}/{submodule}/index.md)\n')
                else:
                    nav_file.write(f'    * [{submodule}]({module_name}/{submodule}.md)\n')
