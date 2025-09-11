"""Plugin system for extending Klaw functionality.

This module provides the plugin architecture that allows extending Klaw's
functionality through a well-defined interface. Plugins can add new features,
modify existing behavior, or integrate with external systems.
"""

from __future__ import annotations

import importlib
import inspect
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, TypeVar

T: TypeVar('T')

if TYPE_CHECKING:
    from typing import Generic  # noqa


class Plugin(Protocol):
    """Protocol that all plugins must implement.

    This protocol defines the basic interface that all Klaw plugins must
    implement. It ensures that plugins can be discovered, loaded, and
    managed consistently.

    Attributes:
        name: A unique identifier for the plugin.
        version: The plugin's version string.
        description: A human-readable description of what the plugin does.

    Example:
        ```python
        from klaw_plugins import Plugin

        class MyPlugin:
            name = "my_plugin"
            version = "1.0.0"
            description = "A plugin that adds custom functionality"

            def initialize(self) -> None:
                print("MyPlugin initialized!")

            def cleanup(self) -> None:
                print("MyPlugin cleaned up!")

        # Register the plugin
        plugin_manager.register(MyPlugin())
        ```
    """

    name: str
    version: str
    description: str

    def initialize(self) -> None:
        """Initialize the plugin. Called when the plugin is loaded."""
        ...

    def cleanup(self) -> None:
        """Clean up the plugin. Called when the plugin is unloaded."""
        ...


class PluginManager:
    """Manager for loading, managing, and coordinating plugins.

    This class provides the central registry and lifecycle management for
    all plugins in the Klaw ecosystem. It handles plugin discovery, loading,
    initialization, and cleanup.

    Attributes:
        plugins: Dictionary mapping plugin names to plugin instances.
        loaded_plugins: List of successfully loaded plugin names.

    Example:
        ```python
        from klaw_plugins import PluginManager

        manager = PluginManager()

        # Load plugins from a directory
        manager.load_from_directory("plugins/")

        # Initialize all loaded plugins
        manager.initialize_all()

        # List all loaded plugins
        for name in manager.list_plugins():
            print(f"Loaded plugin: {name}")

        # Cleanup when done
        manager.cleanup_all()
        ```
    """

    def __init__(self) -> None:
        """Initialize the plugin manager."""
        self.plugins: dict[str, Plugin] = {}
        self.loaded_plugins: list[str] = []

    def register(self, plugin: Plugin) -> None:
        """Register a plugin instance.

        Args:
            plugin: The plugin instance to register.

        Raises:
            ValueError: If a plugin with the same name is already registered.
        """
        if plugin.name in self.plugins:
            raise ValueError(f"Plugin '{plugin.name}' is already registered")

        self.plugins[plugin.name] = plugin
        self.loaded_plugins.append(plugin.name)

    def unregister(self, name: str) -> None:
        """Unregister a plugin.

        Args:
            name: The name of the plugin to unregister.

        Raises:
            ValueError: If the plugin is not registered.
        """
        if name not in self.plugins:
            raise ValueError(f"Plugin '{name}' is not registered")

        plugin = self.plugins[name]
        plugin.cleanup()

        del self.plugins[name]
        self.loaded_plugins.remove(name)

    def get_plugin(self, name: str) -> Plugin:
        """Get a registered plugin by name.

        Args:
            name: The name of the plugin to retrieve.

        Returns:
            The plugin instance.

        Raises:
            KeyError: If the plugin is not registered.
        """
        if name not in self.plugins:
            raise KeyError(f"Plugin '{name}' is not registered")
        return self.plugins[name]

    def list_plugins(self) -> list[str]:
        """List all registered plugin names.

        Returns:
            A list of all registered plugin names.
        """
        return list(self.plugins.keys())

    def initialize_all(self) -> None:
        """Initialize all registered plugins."""
        for plugin in self.plugins.values():
            plugin.initialize()

    def cleanup_all(self) -> None:
        """Clean up all registered plugins."""
        for plugin in list(self.plugins.values()):
            plugin.cleanup()

    def load_from_directory(self, directory: str) -> list[str]:  # noqa
        """Load plugins from Python files in a directory.

        This method scans a directory for Python files, imports them as modules,
        and looks for plugin classes to instantiate and register.

        Args:
            directory: Path to the directory containing plugin files.

        Returns:
            List of plugin names that were successfully loaded.
        """
        loaded = []
        plugin_dir = Path(directory)

        if not plugin_dir.exists():
            return loaded

        for file_path in plugin_dir.glob('*.py'):  # noqa
            if file_path.name.startswith('_'):
                continue

            try:
                # Import the module
                module_name = file_path.stem
                spec = importlib.util.spec_from_file_location(module_name, file_path)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    # Look for plugin classes
                    for name, obj in inspect.getmembers(module):
                        if (  # noqa
                            inspect.isclass(obj)
                            and hasattr(obj, 'name')
                            and hasattr(obj, 'version')
                            and hasattr(obj, 'description')
                        ):
                            # Check if it implements the Plugin protocol
                            if hasattr(obj, 'initialize') and hasattr(obj, 'cleanup'):
                                try:
                                    plugin_instance = obj()
                                    self.register(plugin_instance)
                                    loaded.append(plugin_instance.name)
                                except Exception as e:
                                    print(f'Failed to instantiate plugin {name}: {e}')

            except Exception as e:
                print(f'Failed to load plugin from {file_path}: {e}')

        return loaded


class Hook:
    """A hook point where plugins can register callbacks.

    Hooks provide a way for plugins to extend or modify the behavior of
    the core system at specific points. Multiple plugins can register
    callbacks for the same hook, and they will be executed in registration order.

    Attributes:
        name: The name of the hook.
        callbacks: List of registered callback functions.

    Example:
        ```python
        from klaw_plugins import Hook

        # Create a hook
        pre_process_hook = Hook("pre_process")

        # Register callbacks
        @pre_process_hook.register
        def validate_data(data):
            if not data:
                raise ValueError("Data cannot be empty")
            return data

        @pre_process_hook.register
        def log_data(data):
            print(f"Processing data: {len(data)} items")
            return data

        # Execute the hook
        data = ["item1", "item2"]
        for callback in pre_process_hook.callbacks:
            data = callback(data)
        ```
    """

    def __init__(self, name: str) -> None:
        """Initialize a hook.

        Args:
            name: The name of the hook.
        """
        self.name = name
        self.callbacks: list[Callable[..., Any]] = []

    def register(self, callback: Callable[..., Any]) -> Callable[..., Any]:
        """Register a callback function for this hook.

        Args:
            callback: The callback function to register.

        Returns:
            The callback function (for decorator usage).
        """
        self.callbacks.append(callback)
        return callback

    def unregister(self, callback: Callable[..., Any]) -> None:
        """Unregister a callback function.

        Args:
            callback: The callback function to unregister.

        Raises:
            ValueError: If the callback is not registered.
        """
        if callback not in self.callbacks:
            raise ValueError(f"Callback {callback} is not registered for hook '{self.name}'")
        self.callbacks.remove(callback)

    def execute(self, *args: Any, **kwargs: Any) -> list[Any]:
        """Execute all registered callbacks.

        Args:
            *args: Positional arguments to pass to callbacks.
            **kwargs: Keyword arguments to pass to callbacks.

        Returns:
            List of results from all callback executions.
        """
        results = []

        for callback in self.callbacks:
            try:
                result = callback(*args, **kwargs)
                results.append(result)
            except Exception as e:
                print(f"Error executing callback for hook '{self.name}': {e}")
        return results

    def __call__(self, *args: Any, **kwargs: Any) -> list[Any]:
        """Execute the hook (same as execute method)."""
        return self.execute(*args, **kwargs)


# Global plugin manager instance
plugin_manager = PluginManager()
