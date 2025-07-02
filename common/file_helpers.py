import io
import os
import tempfile
import contextlib
import zstandard as zstd
from typing import Any, Callable, Generator, IO, Optional, Tuple

LOG_COMPRESSION_LEVEL: int = 10 # little benefit up to level 15. level ~17 is a small step change


class CallbackReader:
  """Wraps a file, but overrides the read method to also
  call a callback function with the number of bytes read so far."""
  def __init__(self, f: IO[bytes], callback: Callable[..., None], *args: Any) -> None:
    self.f: IO[bytes] = f
    self.callback: Callable[..., None] = callback
    self.cb_args: Tuple[Any, ...] = args
    self.total_read: int = 0

  def __getattr__(self, attr: str) -> Any:
    return getattr(self.f, attr)

  def read(self, *args: Any, **kwargs: Any) -> bytes:
    chunk: bytes = self.f.read(*args, **kwargs)
    self.total_read += len(chunk)
    self.callback(*self.cb_args, self.total_read)
    return chunk


@contextlib.contextmanager
def atomic_write_in_dir(path: str, mode: str = 'w', buffering: int = -1, encoding: Optional[str] = None, newline: Optional[str] = None,
                        overwrite: bool = False) -> Generator[IO[Any], None, None]:
  """Write to a file atomically using a temporary file in the same directory as the destination file."""
  dir_name: str = os.path.dirname(path)

  if not overwrite and os.path.exists(path):
    raise FileExistsError(f"File '{path}' already exists. To overwrite it, set 'overwrite' to True.")

  tmp_file: Optional[IO[Any]] = None
  tmp_file_name: Optional[str] = None
  try:
    with tempfile.NamedTemporaryFile(mode=mode, buffering=buffering, encoding=encoding, newline=newline, dir=dir_name, delete=False) as tmp_f:
      tmp_file = tmp_f
      tmp_file_name = tmp_f.name
      yield tmp_file
  finally:
    if tmp_file is not None and tmp_file_name is not None:
      os.replace(tmp_file_name, path)


def get_upload_stream(filepath: str, should_compress: bool) -> tuple[io.BufferedIOBase, int]:
  if not should_compress:
    file_size: int = os.path.getsize(filepath)
    file_stream: io.BufferedIOBase = open(filepath, "rb")
    return file_stream, file_size

  # Compress the file on the fly
  compressed_stream: io.BytesIO = io.BytesIO()
  compressor: zstd.ZstdCompressor = zstd.ZstdCompressor(level=LOG_COMPRESSION_LEVEL)

  with open(filepath, "rb") as f:
    compressor.copy_stream(f, compressed_stream)
    compressed_size: int = compressed_stream.tell()
    compressed_stream.seek(0)
    return compressed_stream, compressed_size
