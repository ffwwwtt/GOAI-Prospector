# SPDX-FileCopyrightText: 2024-present Adam Fourney <adamfo@microsoft.com>
# SPDX-License-Identifier: MIT
# Adapted from markitdown package for GOAI competition use.
# Stripped down to: PDF, DOCX, HTML, PlainText converters.

import mimetypes
import os
import re
import sys
import io
import traceback
from dataclasses import dataclass
from typing import Any, List, Dict, Optional, Union, BinaryIO
from pathlib import Path
from urllib.parse import urlparse
from warnings import warn

import requests
import charset_normalizer
import codecs

from ._stream_info import StreamInfo
from ._uri_utils import parse_data_uri, file_uri_to_path

from .converters import (
    PlainTextConverter,
    HtmlConverter,
    PdfConverter,
    DocxConverter,
)

from ._base_converter import DocumentConverter, DocumentConverterResult
from ._exceptions import (
    FileConversionException,
    UnsupportedFormatException,
    FailedConversionAttempt,
)

# Try to import magika for better file type detection
try:
    import magika as _magika_module
    _HAS_MAGIKA = True
except ImportError:
    _HAS_MAGIKA = False

# Lower priority values are tried first.
PRIORITY_SPECIFIC_FILE_FORMAT = 0.0
PRIORITY_GENERIC_FILE_FORMAT = 10.0


@dataclass(kw_only=True, frozen=True)
class ConverterRegistration:
    converter: DocumentConverter
    priority: float


class MarkItDown:
    """Document to Markdown converter — adapted for scientific literature parsing.

    Converts PDF, DOCX, HTML, and plain text files to Markdown.
    Supports local files, URLs, and binary streams.

    Usage:
        md = MarkItDown()
        result = md.convert("paper.pdf")
        print(result.markdown)
    """

    def __init__(self, **kwargs):
        requests_session = kwargs.get("requests_session")
        if requests_session is None:
            self._requests_session = requests.Session()
            self._requests_session.headers.update({
                "Accept": "text/markdown, text/html;q=0.9, text/plain;q=0.8, */*;q=0.1"
            })
        else:
            self._requests_session = requests_session

        if _HAS_MAGIKA:
            self._magika = _magika_module.Magika()
        else:
            self._magika = None

        self._llm_client: Any = None
        self._llm_model: Union[str, None] = None
        self._llm_prompt: Union[str, None] = None
        self._exiftool_path: Union[str, None] = None
        self._style_map: Union[str, None] = None

        self._converters: List[ConverterRegistration] = []
        self._register_builtins(**kwargs)

    def _register_builtins(self, **kwargs) -> None:
        self._llm_client = kwargs.get("llm_client")
        self._llm_model = kwargs.get("llm_model")
        self._llm_prompt = kwargs.get("llm_prompt")
        self._style_map = kwargs.get("style_map")

        # Register in priority order (later = higher priority)
        self.register_converter(PlainTextConverter(), priority=PRIORITY_GENERIC_FILE_FORMAT)
        self.register_converter(HtmlConverter(), priority=PRIORITY_GENERIC_FILE_FORMAT)
        self.register_converter(DocxConverter())
        self.register_converter(PdfConverter())

    def register_converter(self, converter: DocumentConverter,
                           priority: float = PRIORITY_SPECIFIC_FILE_FORMAT) -> None:
        self._converters.insert(
            0, ConverterRegistration(converter=converter, priority=priority)
        )

    # ── Public API ──

    def convert(self, source: Union[str, requests.Response, Path, BinaryIO],
                **kwargs) -> DocumentConverterResult:
        if isinstance(source, str):
            if source.startswith(("http:", "https:", "file:", "data:")):
                return self.convert_uri(source, **kwargs)
            else:
                return self.convert_local(source, **kwargs)
        elif isinstance(source, Path):
            return self.convert_local(source, **kwargs)
        elif isinstance(source, requests.Response):
            return self.convert_response(source, **kwargs)
        elif hasattr(source, "read") and callable(source.read) and not isinstance(source, io.TextIOBase):
            return self.convert_stream(source, **kwargs)
        else:
            raise TypeError(f"Invalid source type: {type(source)}")

    def convert_local(self, path: Union[str, Path], **kwargs) -> DocumentConverterResult:
        if isinstance(path, Path):
            path = str(path)

        base_guess = StreamInfo(
            local_path=path,
            extension=os.path.splitext(path)[1],
            filename=os.path.basename(path),
        )

        with open(path, "rb") as fh:
            guesses = self._get_stream_info_guesses(file_stream=fh, base_guess=base_guess)
            return self._convert(file_stream=fh, stream_info_guesses=guesses, **kwargs)

    def convert_stream(self, stream: BinaryIO,
                       stream_info: Optional[StreamInfo] = None, **kwargs) -> DocumentConverterResult:
        if not stream.seekable():
            buffer = io.BytesIO()
            while True:
                chunk = stream.read(4096)
                if not chunk:
                    break
                buffer.write(chunk)
            buffer.seek(0)
            stream = buffer

        base_guess = stream_info or StreamInfo()
        guesses = self._get_stream_info_guesses(file_stream=stream, base_guess=base_guess)
        return self._convert(file_stream=stream, stream_info_guesses=guesses, **kwargs)

    def convert_uri(self, uri: str, **kwargs) -> DocumentConverterResult:
        uri = uri.strip()

        if uri.startswith("file:"):
            netloc, path = file_uri_to_path(uri)
            if netloc and netloc != "localhost":
                raise ValueError(f"Unsupported file URI: {uri}")
            return self.convert_local(path, **kwargs)
        elif uri.startswith("data:"):
            mimetype, attributes, data = parse_data_uri(uri)
            base_guess = StreamInfo(mimetype=mimetype, charset=attributes.get("charset"))
            return self.convert_stream(io.BytesIO(data), stream_info=base_guess, **kwargs)
        elif uri.startswith(("http:", "https:")):
            response = self._requests_session.get(uri, stream=True)
            response.raise_for_status()
            return self.convert_response(response, **kwargs)
        else:
            raise ValueError(f"Unsupported URI scheme: {uri.split(':')[0]}")

    def convert_response(self, response: requests.Response, **kwargs) -> DocumentConverterResult:
        mimetype: Optional[str] = None
        charset: Optional[str] = None
        if "content-type" in response.headers:
            parts = response.headers["content-type"].split(";")
            mimetype = parts.pop(0).strip()
            for part in parts:
                if part.strip().startswith("charset="):
                    _charset = part.split("=")[1].strip()
                    if len(_charset) > 0:
                        charset = _charset

        filename: Optional[str] = None
        extension: Optional[str] = None
        if "content-disposition" in response.headers:
            m = re.search(r"filename=([^;]+)", response.headers["content-disposition"])
            if m:
                filename = m.group(1).strip("\"'")
                _, _extension = os.path.splitext(filename)
                if len(_extension) > 0:
                    extension = _extension

        if filename is None:
            parsed_url = urlparse(response.url)
            _, _extension = os.path.splitext(parsed_url.path)
            if len(_extension) > 0:
                filename = os.path.basename(parsed_url.path)
                extension = _extension

        base_guess = StreamInfo(
            mimetype=mimetype, charset=charset,
            filename=filename, extension=extension, url=response.url,
        )

        buffer = io.BytesIO()
        for chunk in response.iter_content(chunk_size=512):
            buffer.write(chunk)
        buffer.seek(0)

        guesses = self._get_stream_info_guesses(file_stream=buffer, base_guess=base_guess)
        return self._convert(file_stream=buffer, stream_info_guesses=guesses, **kwargs)

    # ── Internal ──

    def _convert(self, *, file_stream: BinaryIO,
                 stream_info_guesses: List[StreamInfo], **kwargs) -> DocumentConverterResult:
        res: Union[None, DocumentConverterResult] = None
        failed_attempts: List[FailedConversionAttempt] = []
        sorted_registrations = sorted(self._converters, key=lambda x: x.priority)
        cur_pos = file_stream.tell()

        for stream_info in stream_info_guesses + [StreamInfo()]:
            for converter_registration in sorted_registrations:
                converter = converter_registration.converter
                assert cur_pos == file_stream.tell(), \
                    "File stream position should NOT change between guess iterations"

                _kwargs = {k: v for k, v in kwargs.items()}
                if "llm_client" not in _kwargs and self._llm_client is not None:
                    _kwargs["llm_client"] = self._llm_client
                if "llm_model" not in _kwargs and self._llm_model is not None:
                    _kwargs["llm_model"] = self._llm_model
                if "llm_prompt" not in _kwargs and self._llm_prompt is not None:
                    _kwargs["llm_prompt"] = self._llm_prompt
                if "style_map" not in _kwargs and self._style_map is not None:
                    _kwargs["style_map"] = self._style_map
                if "exiftool_path" not in _kwargs and self._exiftool_path is not None:
                    _kwargs["exiftool_path"] = self._exiftool_path
                _kwargs["_parent_converters"] = self._converters

                if stream_info is not None:
                    if stream_info.extension is not None:
                        _kwargs["file_extension"] = stream_info.extension
                    if stream_info.url is not None:
                        _kwargs["url"] = stream_info.url

                _accepts = False
                try:
                    _accepts = converter.accepts(file_stream, stream_info, **_kwargs)
                except NotImplementedError:
                    pass

                assert cur_pos == file_stream.tell(), \
                    f"{type(converter).__name__}.accept() should NOT change file_stream position"

                if _accepts:
                    try:
                        res = converter.convert(file_stream, stream_info, **_kwargs)
                    except Exception:
                        failed_attempts.append(
                            FailedConversionAttempt(converter=converter, exc_info=sys.exc_info())
                        )
                    finally:
                        file_stream.seek(cur_pos)

                if res is not None:
                    res.text_content = "\n".join(
                        [line.rstrip() for line in re.split(r"\r?\n", res.text_content)]
                    )
                    res.text_content = re.sub(r"\n{3,}", "\n\n", res.text_content)
                    return res

        if len(failed_attempts) > 0:
            raise FileConversionException(attempts=failed_attempts)

        raise UnsupportedFormatException(
            "Could not convert stream to Markdown. No converter attempted a conversion."
        )

    def _get_stream_info_guesses(self, file_stream: BinaryIO,
                                  base_guess: StreamInfo) -> List[StreamInfo]:
        guesses: List[StreamInfo] = []
        enhanced_guess = base_guess.copy_and_update()

        if base_guess.mimetype is None and base_guess.extension is not None:
            _m, _ = mimetypes.guess_type("placeholder" + base_guess.extension, strict=False)
            if _m is not None:
                enhanced_guess = enhanced_guess.copy_and_update(mimetype=_m)

        if base_guess.mimetype is not None and base_guess.extension is None:
            _e = mimetypes.guess_all_extensions(base_guess.mimetype, strict=False)
            if len(_e) > 0:
                enhanced_guess = enhanced_guess.copy_and_update(extension=_e[0])

        if self._magika is not None:
            cur_pos = file_stream.tell()
            try:
                result = self._magika.identify_stream(file_stream)
                if result.status == "ok" and result.prediction.output.label != "unknown":
                    charset = None
                    if result.prediction.output.is_text:
                        file_stream.seek(cur_pos)
                        stream_page = file_stream.read(4096)
                        charset_result = charset_normalizer.from_bytes(stream_page).best()
                        if charset_result is not None:
                            charset = self._normalize_charset(charset_result.encoding)

                    guessed_extension = None
                    if len(result.prediction.output.extensions) > 0:
                        guessed_extension = "." + result.prediction.output.extensions[0]

                    compatible = True
                    if base_guess.mimetype is not None and \
                       base_guess.mimetype != result.prediction.output.mime_type:
                        compatible = False
                    if base_guess.extension is not None and \
                       base_guess.extension.lstrip(".") not in result.prediction.output.extensions:
                        compatible = False
                    if base_guess.charset is not None and \
                       self._normalize_charset(base_guess.charset) != charset:
                        compatible = False

                    if compatible:
                        guesses.append(StreamInfo(
                            mimetype=base_guess.mimetype or result.prediction.output.mime_type,
                            extension=base_guess.extension or guessed_extension,
                            charset=base_guess.charset or charset,
                            filename=base_guess.filename,
                            local_path=base_guess.local_path,
                            url=base_guess.url,
                        ))
                    else:
                        guesses.append(enhanced_guess)
                        guesses.append(StreamInfo(
                            mimetype=result.prediction.output.mime_type,
                            extension=guessed_extension,
                            charset=charset,
                            filename=base_guess.filename,
                            local_path=base_guess.local_path,
                            url=base_guess.url,
                        ))
                else:
                    guesses.append(enhanced_guess)
            finally:
                file_stream.seek(cur_pos)
        else:
            guesses.append(enhanced_guess)

        return guesses

    def _normalize_charset(self, charset) -> Optional[str]:
        if charset is None:
            return None
        try:
            return codecs.lookup(charset).name
        except LookupError:
            return charset


# ── Convenience function ──

def parse_document(source: Union[str, Path, BinaryIO]) -> str:
    """Parse a document (PDF, DOCX, HTML, etc.) and return Markdown text.

    Args:
        source: File path (str or Path), URL, or binary stream.

    Returns:
        Markdown string of the document content.
    """
    md = MarkItDown()
    result = md.convert(source)
    return result.markdown


def parse_pdf(filepath: str) -> str:
    """Parse a PDF file and return Markdown text."""
    return parse_document(filepath)
