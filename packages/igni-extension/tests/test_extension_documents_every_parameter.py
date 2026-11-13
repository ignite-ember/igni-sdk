"""Parse documented parameters from docstrings."""

from __future__ import annotations


def _documented(docstring: str) -> list[str]:
    """Extract parameter names from the Args: section of a docstring.

    Each parameter is on its own line, formatted as:
        name: description

    Returns the parameter names in order, or an empty list if no Args: section exists.
    """
    lines = docstring.split("\n")
    in_args = False
    parameters: list[str] = []

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("Args:"):
            in_args = True
            continue

        if in_args:
            # Stop when we hit another section (starts with capital letter followed by colon)
            if stripped and stripped[0].isupper() and ":" in stripped and not stripped.startswith((" ", "\t")):
                break

            # Skip empty lines and section headers
            if not stripped or stripped.startswith(("Returns:", "Raises:", "Note:", "Example:")):
                if stripped and ":" in stripped:
                    in_args = False
                continue

            # Parse parameter lines: they start with whitespace and have "name: description"
            if stripped and ":" in stripped:
                # Get the parameter name (before the colon)
                param_name = stripped.split(":", 1)[0].strip()
                if param_name and not param_name.startswith(("**", "*")):
                    parameters.append(param_name)
                # For **kwargs style, include the full name
                elif stripped.startswith(("**", "*")):
                    param_name = stripped.split(":", 1)[0].strip()
                    parameters.append(param_name)

    return parameters
