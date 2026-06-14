"""
reaper_parser.py - Parser for Reaper project files (.rpp)

Reaper project files use a hierarchical block format:
  <BLOCKNAME arg1 arg2 ...
    KEY value1 value2 ...
    <CHILD_BLOCK ...
    >
  >

Blocks begin with a line starting with '<' and end with '>'.
Attribute lines are key-value pairs within a block.
Some blocks contain raw base64-encoded data lines (prefixed with a space).
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from typing import Iterator, List, Optional


@dataclass
class RppNode:
    """Represents a single node (block) in a Reaper project file."""

    tag: str
    attribs: List[str] = field(default_factory=list)
    children: List["RppNode"] = field(default_factory=list)
    # Key-value attribute lines within this block (non-child-block lines)
    params: List[List[str]] = field(default_factory=list)
    # Raw data lines (lines that start with a space and contain base64 data)
    raw_data: List[str] = field(default_factory=list)

    def find_all(self, tag: str) -> List["RppNode"]:
        """Return all direct children with the given tag."""
        return [c for c in self.children if c.tag == tag]

    def find(self, tag: str) -> Optional["RppNode"]:
        """Return the first direct child with the given tag, or None."""
        for child in self.children:
            if child.tag == tag:
                return child
        return None

    def find_recursive(self, tag: str) -> List["RppNode"]:
        """Return all descendants (at any depth) with the given tag."""
        results: List[RppNode] = []
        for child in self.children:
            if child.tag == tag:
                results.append(child)
            results.extend(child.find_recursive(tag))
        return results

    def get_param(self, key: str) -> Optional[List[str]]:
        """Return the first param line whose key matches (case-insensitive), or None."""
        key_upper = key.upper()
        for tokens in self.params:
            if tokens and tokens[0].upper() == key_upper:
                return tokens[1:]
        return None

    def __repr__(self) -> str:
        return f"RppNode(tag={self.tag!r}, attribs={self.attribs!r}, children={len(self.children)}, params={len(self.params)})"


def _tokenize_line(line: str) -> List[str]:
    """Split a line into tokens, respecting quoted strings."""
    try:
        return shlex.split(line)
    except ValueError:
        # Fall back to simple split if shlex fails (e.g. unmatched quotes)
        return line.split()


def _parse_block_lines(lines: List[str], pos: int) -> tuple[RppNode, int]:
    """
    Parse a block starting at lines[pos] (which should be a '<TAG ...' line).
    Returns (node, new_pos) where new_pos is the index after the closing '>'.
    """
    header = lines[pos].strip()
    if not header.startswith("<"):
        raise ValueError(f"Expected block start at line {pos}: {header!r}")

    # Parse the block header: <TAG attrib1 attrib2 ...
    header_content = header[1:]  # remove leading '<'
    tokens = _tokenize_line(header_content)
    tag = tokens[0] if tokens else ""
    attribs = tokens[1:]

    node = RppNode(tag=tag, attribs=attribs)
    pos += 1

    while pos < len(lines):
        line = lines[pos]
        stripped = line.strip()

        if stripped == ">":
            # End of this block
            pos += 1
            break
        elif stripped.startswith("<"):
            # Start of a child block
            child, pos = _parse_block_lines(lines, pos)
            node.children.append(child)
        elif line.startswith("  ") and stripped and not stripped.startswith("<"):
            # Could be a raw data line (base64) or a key-value param
            # Raw data lines typically start with exactly two spaces and contain
            # base64-like content without a recognisable keyword
            tokens = _tokenize_line(stripped)
            node.params.append(tokens)
            pos += 1
        else:
            # Blank lines or other content
            tokens = _tokenize_line(stripped)
            if tokens:
                node.params.append(tokens)
            pos += 1

    return node, pos


def parse_rpp(text: str) -> RppNode:
    """
    Parse the full text of a Reaper project file and return the root RppNode.

    Args:
        text: The full contents of a .rpp file.

    Returns:
        The root RppNode (typically with tag 'REAPER_PROJECT').

    Raises:
        ValueError: If the file does not start with a recognised block.
    """
    lines = text.splitlines()
    # Skip any leading blank lines
    start = 0
    while start < len(lines) and not lines[start].strip():
        start += 1

    if start >= len(lines) or not lines[start].strip().startswith("<"):
        raise ValueError("Reaper project file must start with a '<' block")

    root, _ = _parse_block_lines(lines, start)
    return root


def parse_rpp_file(path: str) -> RppNode:
    """
    Read a .rpp file from disk and return the parsed root RppNode.

    Args:
        path: Filesystem path to the .rpp file.

    Returns:
        The root RppNode.
    """
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    return parse_rpp(text)


def iter_nodes(root: RppNode, tag: str) -> Iterator[RppNode]:
    """
    Depth-first iterator over all nodes with the given tag in the tree.

    Args:
        root: The root node to search from.
        tag:  The tag name to match (case-sensitive).

    Yields:
        RppNode instances whose tag matches.
    """
    if root.tag == tag:
        yield root
    for child in root.children:
        yield from iter_nodes(child, tag)
