"""Tool manager module for GNOME Nano Image Edit.

This module manages the state of editing tools and validates tool selection.
"""

import logging

logger = logging.getLogger(__name__)


class ToolManager:
    """Manages the state of the editing tools.
    
    This class tracks the currently active tool and provides validation
    for tool selection.
    """

    VALID_TOOLS = frozenset(['select', 'crop', 'text', 'brush', 'move'])

    def __init__(self) -> None:
        """Initializes the tool manager with the default tool."""
        self._current_tool = 'select'  # Default tool

    @property
    def current_tool(self) -> str:
        """Gets the current tool.
        
        Returns:
            The name of the currently active tool.
        """
        return self._current_tool

    @current_tool.setter
    def current_tool(self, tool_name: str) -> None:
        """Sets the current tool.
        
        Args:
            tool_name: The name of the tool to activate.
        """
        if tool_name in self.VALID_TOOLS:
            self._current_tool = tool_name
        else:
            logger.warning("Unknown tool '%s'", tool_name)
