import os
import logging
from typing import List, Tuple
from medcat.cdb import CDB
from medcat.utils.decorators import check_positive


class Checkpoint(object):

    log = logging.getLogger(__package__)

    @check_positive
    def __init__(self, dir_path: str, *, steps: int = 1000, max_to_keep: int = 1) -> None:
        """ Initialise the checkpoint object
        Args:
            dir_path (str):
                The path to the checkpoint directory.
            steps (int):
                The number of processed sentences/documents before a checkpoint is saved.
                N.B.: A small number could result in error "no space left on device".
            max_to_keep (int):
                The maximum number of checkpoints to keep.
                N.B.: A large number could result in error "no space left on device".
        """
        self._dir_path = os.path.abspath(dir_path)
        self._steps = steps
        self._max_to_keep = max_to_keep
        self._file_paths: List[str] = []
        self._count = 0
        os.makedirs(self._dir_path, exist_ok=True)

    @property
    def steps(self) -> int:
        return self._steps

    @steps.setter  # type: ignore
    # [https://github.com/python/mypy/issues/1362]
    @check_positive
    def steps(self, value: int) -> None:
        self._steps = value

    @property
    def max_to_keep(self) -> int:
        return self._max_to_keep

    @max_to_keep.setter  # type: ignore
    # [https://github.com/python/mypy/issues/1362]
    @check_positive
    def max_to_keep(self, value: int) -> None:
        self._max_to_keep = value

    @property
    def count(self) -> int:
        return self._count

    @property
    def dir_path(self) -> str:
        return self._dir_path

    @classmethod
    def from_last_training(cls, parent_dir_path: str) -> "Checkpoint":
        if not os.path.isdir(parent_dir_path):
            raise ValueError(f"Checkpoint folder passed in does not exist: {parent_dir_path}")
        ckpt_parent_folders = os.listdir(parent_dir_path)
        if not ckpt_parent_folders:
            raise ValueError("No existing training found")
        ckpt_parent_folders.sort()
        ckpt_file_path = os.path.abspath(os.path.join(parent_dir_path, ckpt_parent_folders[-1]))
        checkpoint = cls.load(ckpt_file_path)
        return checkpoint

    @classmethod
    def load(cls, dir_path: str) -> "Checkpoint":
        r'''
        Load the latest checkpoint from a directory.

        Args:
            dir_path (string):
                The path to the directory containing checkpoint files
        Returns:
            A new checkpoint object
        '''
        if not os.path.isdir(dir_path):
            raise Exception("Checkpoints not found. You need to train from scratch.")
        ckpt_file_paths = cls._get_ckpt_file_paths(dir_path)
        if not ckpt_file_paths:
            raise Exception("Checkpoints not found. You need to train from scratch.")
        latest_ckpt = ckpt_file_paths[-1]
        steps, count = cls._get_steps_and_count(latest_ckpt)
        checkpoint = cls(dir_path, steps=steps)
        checkpoint._file_paths = ckpt_file_paths
        checkpoint._count = count
        cls.log.info(f"Checkpoint loaded from {latest_ckpt}")
        return checkpoint

    def restore(self) -> None:
        r'''
        Restore the latest checkpoint.
        '''
        if not os.path.isdir(self._dir_path):
            raise Exception("Checkpoints not found. You need to train from scratch.")
        ckpt_file_paths = self._get_ckpt_file_paths(self._dir_path)
        if not ckpt_file_paths:
            raise Exception("Checkpoints not found. You need to train from scratch.")
        latest_ckpt = ckpt_file_paths[-1]
        _, count = self._get_steps_and_count(latest_ckpt)
        self._file_paths = ckpt_file_paths
        self._count = count

    def purge(self) -> List[str]:
        r'''
        Remove all checkpoint files from the checkpoint directory.

        Returns:
            A list of paths to the removed files
        '''
        ckpt_file_paths = self._get_ckpt_file_paths(self._dir_path)
        removed = []
        for path in ckpt_file_paths:
            if os.path.isfile(path):
                os.remove(path)
                removed.append(path)
        self._file_paths = []
        self._count = 0
        return removed

    def save(self, cdb: CDB, count: int) -> None:
        r'''
        Save the CDB as the latest checkpoint.

        Args:
            cdb (medcat.CDB):
                The input MedCAT CDB object
            count (count):
                The number of the finished steps
        '''
        ckpt_file_path = os.path.join(os.path.abspath(self._dir_path), "checkpoint-%s-%s" % (self.steps, count))
        while len(self._file_paths) >= self._max_to_keep:
            to_remove = self._file_paths.pop(0)
            os.remove(to_remove)
        cdb.save(ckpt_file_path)
        self.log.debug("Checkpoint saved: %s", ckpt_file_path)
        self._file_paths.append(ckpt_file_path)
        self._count = count

    def populate(self, cdb: CDB) -> None:
        r'''
        Populate the latest checkpoint to a CDB.

        Args:
            cdb (medcat.CDB):
                The input MedCAT CDB object
        '''
        if not self._file_paths:
            raise Exception("Cannot populate the model. Make sure the checkpoint is restored beforehand.")
        cdb.load(self._file_paths[-1])

    def restore_and_populate(self, cdb: CDB) -> None:
        r'''
        Restore the latest checkpoint and populate it to a CDB

        Args:
            cdb (medcat.CDB):
                The input MedCAT CDB object
        '''
        self.restore()
        self.populate(cdb)

    @staticmethod
    def _get_ckpt_file_paths(dir_path: str) -> List[str]:
        ckpt_file_paths = [os.path.abspath(os.path.join(dir_path, f)) for f in os.listdir(dir_path)]
        ckpt_file_paths = [f for f in ckpt_file_paths if os.path.isfile(f) and "checkpoint-" in f]
        if ckpt_file_paths:
            ckpt_file_paths.sort(key=lambda f: Checkpoint._get_steps_and_count(f)[1])
        return ckpt_file_paths

    @staticmethod
    def _get_steps_and_count(file_path) -> Tuple[int, int]:
        file_name_parts = os.path.basename(file_path).split('-')
        return int(file_name_parts[1]), int(file_name_parts[2])
