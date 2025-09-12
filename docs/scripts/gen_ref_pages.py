#!/usr/bin/env python3
"""
Generate API reference documentation for all Klaw workspaces.
"""

import ast
from pathlib import Path

import mkdocs_gen_files

nav = mkdocs_gen_files.Nav()
root = Path(__file__).parent.parent.parent
docs_dir = root / 'docs'

# Define the Python workspaces to document
python_workspaces = [
    'workspaces/python/klaw-core/src/klaw_core',
    'workspaces/python/klaw-plugins/src/klaw_plugins',
    'workspaces/python/klaw-polars/src/klaw_polars',
    'workspaces/python/klaw-returns/src/klaw_returns',
    'workspaces/python/klaw-testing/src/klaw_testing',
    'workspaces/python/klaw-types/src/klaw_types',
]


def get_title(source_path: Path) -> str:
    """Extract title from Python source file."""
    try:
        with open(source_path, encoding='utf-8') as f:
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
        with open(module_path, encoding='utf-8') as f:
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

    module_name = workspace_path.split('/')[-1]  # e.g., "klaw_core"
    modules_structure[module_name] = set()
    submodules_per_package[module_name] = []

    # Find all Python files in the workspace
    for path in sorted(src.rglob('*.py')):
        if path.name in ('__main__.py', '__version__.py') or path.name.endswith('_test.py'):
            continue

        module_path = path.relative_to(src).with_suffix('')
        parts = tuple(module_path.parts)

        if parts[-1] == '__init__':
            parts = parts[:-1]
            if parts:
                init_path = src / '/'.join(parts) / '__init__.py'
                module_info = get_module_info(init_path)
                if module_info and len(parts) == 1:
                    modules_structure[module_name].add((
                        parts[0],
                        clean_description(module_info.get('description', 'No description')),
                    ))

        # Collect submodules for package index
        if len(parts) == 1 and parts[0] != '__init__':
            submodule_name = parts[0]
            # Try to get description from module's own docstring
            submodule_info = get_module_info(path)
            if not submodule_info:
                # Fallback to package __init__.py or default
                submodule_info = (
                    get_module_info(path.parent / '__init__.py') if (path.parent / '__init__.py').exists() else {}
                )
            description = clean_description(submodule_info.get('description', f'Module {submodule_name}'))
            submodules_per_package[module_name].append((submodule_name, description))

# Generate the main reference index
with mkdocs_gen_files.open('reference/index.md', 'w') as index:
    index.write('# API Reference\n\n')
    index.write('Welcome to the Klaw API reference documentation.\n\n')
    index.write('## Available Modules\n\n')

    # Create a single table for all packages
    index.write('| Package   | Description |\n')
    index.write('|-----------|-------------|\n')

    for module_name, submodules in submodules_per_package.items():
        if submodules:  # Only show packages that have submodules
            display_name = module_name.replace('_', ' ').title()

            # Get package description from __init__.py
            # Find the correct workspace path for this module
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
            display_name = module_name.replace('_', ' ').title()
            fd.write(f'# {display_name}\n\n')
            fd.write(f'Package `{module_name}` provides the following modules:\n\n')

            fd.write('| Module | Description |\n')
            fd.write('|--------|-------------|\n')
            for submodule, description in sorted(submodules):
                fd.write(f'| [{submodule}]({submodule}.md) | {description} |\n')
            fd.write('\n')

        nav[*('reference', module_name)] = 'index.md'

# Generate documentation for each Python file
for workspace_path in python_workspaces:
    src = root / workspace_path
    if not src.exists():
        continue

    module_name = workspace_path.split('/')[-1]

    for path in sorted(src.rglob('*.py')):
        if path.name in ('__main__.py', '__version__.py') or path.name.endswith('_test.py'):
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
            fd.write(f'::: {ident}\n\n')

        mkdocs_gen_files.set_edit_path(full_doc_path, path)

# Generate navigation file with correct structure
with mkdocs_gen_files.open('reference/SUMMARY.md', 'w') as nav_file:
    nav_file.write('* [API Reference](index.md)\n')
    for module_name, submodules in sorted(submodules_per_package.items()):
        if submodules:
            display_name = module_name.replace('_', ' ').title()
            nav_file.write(f'  * {display_name}\n')
            nav_file.write(f'    * [{display_name}]({module_name}/index.md)\n')
            for submodule, _ in sorted(submodules):
                nav_file.write(f'    * [{submodule}]({module_name}/{submodule}.md)\n')
