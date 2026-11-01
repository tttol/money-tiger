"""Restrict application file access to the configured household CSV directory."""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from money.csv_source import CsvError, MAX_BYTES, parse_csv
from money.domain import Month


@dataclass(frozen=True)
class Source:
    """A CSV identifier and its parsed monthly report."""

    name: str
    month: Month


@dataclass(frozen=True)
class Catalog:
    """Valid sources plus actionable notices for unreadable files."""

    sources: tuple[Source, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class CsvRepository:
    """A local filesystem adapter; original CSV files are never overwritten."""

    directory: Path

    def catalog(self) -> Catalog:
        """Read CSV files in the configured folder and report invalid exports."""
        sources = []
        warnings = []
        for path in sorted(self.directory.glob("*.csv")):
            try:
                sources.append(self.get(path.name))
            except (CsvError, OSError) as exc:
                message = str(exc) if isinstance(exc, CsvError) else "ファイルを読み取れません。"
                warnings.append(f"{path.name}: {message}")
        return Catalog(tuple(sorted(sources, key=lambda source: (source.month.period, source.name))), tuple(warnings))

    def get(self, name: str) -> Source:
        """Read an immediate child CSV; reject traversal, symlinks and oversize input."""
        if not name or Path(name).name != name or "/" in name or "\\" in name:
            raise CsvError("CSVの選択が正しくありません。")
        path = self.directory / name
        if path.suffix.lower() != ".csv" or path.is_symlink() or not path.is_file():
            raise CsvError("選択したCSVが見つかりません。")
        with path.open("rb") as stream:
            content = stream.read(MAX_BYTES + 1)
        return Source(name, parse_csv(content))

    def add(self, content: bytes) -> Source:
        """Validate an upload before storing it under a deterministic safe filename."""
        month = parse_csv(content)
        digest = sha256(content).hexdigest()
        for existing in self.directory.glob("*.csv"):
            if existing.is_file() and not existing.is_symlink() and existing.stat().st_size <= MAX_BYTES:
                with existing.open("rb") as stream:
                    same_content = sha256(stream.read(MAX_BYTES + 1)).hexdigest() == digest
                if same_content:
                    return Source(existing.name, month)
        name = f"{month.period}_{digest}.csv"
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / name
        if path.is_symlink():
            raise CsvError("保存先のファイルが正しくありません。")
        try:
            with path.open("xb") as stream:
                stream.write(content)
        except FileExistsError:
            return self.get(name)
        return Source(name, month)


def default_pair(catalog: Catalog) -> tuple[str, str]:
    """Select the two latest distinct months without merging duplicate exports."""
    by_month = {source.month.period: source.name for source in catalog.sources}
    months = sorted(by_month)
    if len(months) < 2:
        return "", by_month[months[0]] if months else ""
    return by_month[months[-2]], by_month[months[-1]]
