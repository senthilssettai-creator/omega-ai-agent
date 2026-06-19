"""Filesystem Tool - File and directory operations"""

import os
import shutil
import glob
import mimetypes
from pathlib import Path
from typing import Any, Dict, List, Optional

from omega.tools.registry import BaseTool, ToolResult


class FilesystemTool(BaseTool):
    name = "filesystem"
    description = "Read, write, delete, move, search files and directories"

    async def execute(self, action: str, **kwargs) -> ToolResult:
        handler = getattr(self, f"action_{action}", None)
        if not handler:
            return ToolResult(success=False, error=f"Unknown action: {action}")
        try:
            result = await handler(**kwargs)
            return ToolResult(success=True, output=result)
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def action_read(self, path: str, encoding: str = "utf-8") -> str:
        """Read file contents"""
        return Path(path).read_text(encoding=encoding)

    async def action_write(self, path: str, content: str,
                            encoding: str = "utf-8", mkdir: bool = True) -> str:
        """Write content to file"""
        p = Path(path)
        if mkdir:
            p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding=encoding)
        return f"Written {len(content)} bytes to {path}"

    async def action_append(self, path: str, content: str) -> str:
        """Append content to file"""
        with open(path, "a") as f:
            f.write(content)
        return f"Appended to {path}"

    async def action_delete(self, path: str, recursive: bool = False) -> str:
        """Delete file or directory"""
        p = Path(path)
        if p.is_dir():
            if recursive:
                shutil.rmtree(p)
            else:
                p.rmdir()
        else:
            p.unlink()
        return f"Deleted {path}"

    async def action_move(self, source: str, destination: str) -> str:
        """Move file or directory"""
        shutil.move(source, destination)
        return f"Moved {source} → {destination}"

    async def action_copy(self, source: str, destination: str) -> str:
        """Copy file or directory"""
        src = Path(source)
        if src.is_dir():
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination)
        return f"Copied {source} → {destination}"

    async def action_list(self, path: str = ".", recursive: bool = False,
                          pattern: str = "*") -> List[Dict]:
        """List directory contents"""
        p = Path(path)
        results = []
        if recursive:
            items = p.rglob(pattern)
        else:
            items = p.glob(pattern)

        for item in sorted(items):
            stat = item.stat()
            results.append({
                "name": item.name,
                "path": str(item),
                "type": "dir" if item.is_dir() else "file",
                "size": stat.st_size,
                "modified": stat.st_mtime,
            })
        return results

    async def action_search(self, path: str, pattern: str,
                             content: Optional[str] = None) -> List[str]:
        """Search for files by name or content"""
        matches = []
        for match in Path(path).rglob(pattern):
            if content:
                try:
                    text = match.read_text(errors="ignore")
                    if content.lower() in text.lower():
                        matches.append(str(match))
                except Exception:
                    pass
            else:
                matches.append(str(match))
        return matches

    async def action_mkdir(self, path: str) -> str:
        """Create directory"""
        Path(path).mkdir(parents=True, exist_ok=True)
        return f"Created directory: {path}"

    async def action_exists(self, path: str) -> bool:
        """Check if path exists"""
        return Path(path).exists()

    async def action_info(self, path: str) -> dict:
        """Get file/directory metadata"""
        p = Path(path)
        stat = p.stat()
        return {
            "path": str(p.absolute()),
            "name": p.name,
            "type": "directory" if p.is_dir() else "file",
            "size": stat.st_size,
            "mime_type": mimetypes.guess_type(str(p))[0] if p.is_file() else None,
            "modified": stat.st_mtime,
            "created": stat.st_ctime,
        }
