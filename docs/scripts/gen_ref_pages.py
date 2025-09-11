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


def get_module_info(init_path: Path) -> dict:
    """Extract module information from __init__.py."""
    if not init_path.exists():
        return {}
    try:
        with open(init_path, encoding='utf-8') as f:
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

for workspace_path in python_workspaces:
    src = root / workspace_path
    if not src.exists():
        continue

    module_name = workspace_path.split('/')[-1]  # e.g., "klaw_core"
    modules_structure[module_name] = set()

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

# Generate the main reference index
with mkdocs_gen_files.open('reference/index.md', 'w') as index:
    index.write('# API Reference\n\n')
    index.write('Welcome to the Klaw API reference documentation.\n\n')
    index.write('## Available Modules\n\n')

    for module_name, submodules in modules_structure.items():
        if submodules:  # Only show modules that have content
            display_name = module_name.replace('_', ' ').title()
            index.write(f'### {display_name}\n\n')

            index.write('| Module | Description |\n')
            index.write('|--------|------------|\n')
            for submodule, description in sorted(submodules):
                index.write(f'| [{submodule}]({module_name}/{submodule}/index.md) | {description} |\n')
            index.write('\n')

nav['reference'] = 'index.md'

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
    nav_file.write('  * [Core](klaw_core/core.md)\n')
    nav_file.write('  * [Plugins](klaw_plugins/plugin.md)\n')
    nav_file.write('  * [Types](klaw_types/types.md)\n')
