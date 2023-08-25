import asyncio
import os
from typing import List

from ...core.context import ContextProvider
from ...core.main import ContextItem, ContextItemDescription, ContextItemId
from ...libs.util.filter_files import DEFAULT_IGNORE_PATTERNS, should_filter_path
from .util import remove_meilisearch_disallowed_chars

MAX_SIZE_IN_BYTES = 1024 * 1024 * 1


def get_file_contents(filepath: str) -> str:
    try:
        filesize = os.path.getsize(filepath)
        if filesize > MAX_SIZE_IN_BYTES:
            return None

        with open(filepath, "r") as f:
            return f.read()
    except Exception:
        # Some files cannot be read, e.g. binary files
        return None


class FileContextProvider(ContextProvider):
    """
    The FileContextProvider is a ContextProvider that allows you to search files in the open workspace.
    """

    title = "file"
    ignore_patterns: List[str] = DEFAULT_IGNORE_PATTERNS

    async def start(self, *args):
        await super().start(*args)

        async def on_file_saved(filepath: str, contents: str):
            item = await self.get_context_item_for_filepath(filepath)
            if item is None:
                return
            await self.update_documents([item], self.sdk.ide.workspace_directory)

        async def on_files_created(filepaths: List[str]):
            items = await asyncio.gather(
                *[
                    self.get_context_item_for_filepath(filepath)
                    for filepath in filepaths
                ]
            )
            items = [item for item in items if item is not None]
            await self.update_documents(items, self.sdk.ide.workspace_directory)

        async def on_files_deleted(filepaths: List[str]):
            ids = [self.get_id_for_filepath(filepath) for filepath in filepaths]

            await self.delete_documents(ids)

        async def on_files_renamed(old_filepaths: List[str], new_filepaths: List[str]):
            if self.sdk.ide.workspace_directory is None:
                return

            old_ids = [self.get_id_for_filepath(filepath) for filepath in old_filepaths]
            new_docs = await asyncio.gather(
                *[
                    self.get_context_item_for_filepath(filepath)
                    for filepath in new_filepaths
                ]
            )
            new_docs = [doc for doc in new_docs if doc is not None]

            await self.delete_documents(old_ids)
            await self.update_documents(new_docs, self.sdk.ide.workspace_directory)

        self.sdk.ide.subscribeToFileSaved(on_file_saved)
        self.sdk.ide.subscribeToFilesCreated(on_files_created)
        self.sdk.ide.subscribeToFilesDeleted(on_files_deleted)
        self.sdk.ide.subscribeToFilesRenamed(on_files_renamed)

    def get_id_for_filepath(self, absolute_filepath: str) -> str:
        return remove_meilisearch_disallowed_chars(absolute_filepath)

    async def get_context_item_for_filepath(
        self, absolute_filepath: str
    ) -> ContextItem:
        content = get_file_contents(absolute_filepath)
        if content is None:
            return None

        relative_to_workspace = os.path.relpath(
            absolute_filepath, self.sdk.ide.workspace_directory
        )

        return ContextItem(
            content=content[: min(2000, len(content))],
            description=ContextItemDescription(
                name=os.path.basename(absolute_filepath),
                # We should add the full path to the ContextItem
                # It warrants a data modeling discussion and has no immediate use case
                description=relative_to_workspace,
                id=ContextItemId(
                    provider_title=self.title,
                    item_id=self.get_id_for_filepath(absolute_filepath),
                ),
            ),
        )

    async def provide_context_items(self, workspace_dir: str) -> List[ContextItem]:
        absolute_filepaths: List[str] = []
        for root, dir_names, file_names in os.walk(workspace_dir):
            dir_names[:] = [
                d for d in dir_names if not should_filter_path(d, self.ignore_patterns)
            ]
            for file_name in file_names:
                absolute_filepaths.append(os.path.join(root, file_name))

                if len(absolute_filepaths) > 1000:
                    break

            if len(absolute_filepaths) > 1000:
                break

        items = []
        for absolute_filepath in absolute_filepaths:
            item = await self.get_context_item_for_filepath(absolute_filepath)
            if item is not None:
                items.append(item)

        return items
