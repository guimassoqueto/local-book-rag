"""PDF extraction with Docling: layout models for hard documents, and OCR for scanned ones."""

from pathlib import Path

from app.errors import EmptyDocumentError, InvalidDocumentError
from app.ingestion.base import Block, BlockKind, DocumentFormat, ExtractedDocument


class DoclingLoader:
    def __init__(self, ocr: bool) -> None:
        self._ocr = ocr

    def load(self, path: Path) -> ExtractedDocument:
        # Imported here: Docling pulls in torch, and most books never need it.
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import HeadingHierarchyOptions, PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.exceptions import ConversionError
        from docling_core.types.doc import CodeItem, ListItem, SectionHeaderItem, TableItem, TextItem, TitleItem

        # Without the hierarchy options, Docling leaves every heading at level 1.
        options = PdfPipelineOptions(
            do_ocr=self._ocr,
            do_table_structure=True,
            heading_hierarchy_options=HeadingHierarchyOptions(enabled=True),
        )
        converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})
        try:
            document = converter.convert(path).document
        except ConversionError as exc:
            raise InvalidDocumentError(f"Docling could not read {path.name}: {exc}") from exc

        blocks: list[Block] = []
        for item, _ in document.iterate_items():
            pages = [provenance.page_no for provenance in getattr(item, "prov", [])]
            first, last = (min(pages), max(pages)) if pages else (None, None)
            match item:
                case TitleItem():
                    blocks.append(Block(BlockKind.HEADING, item.text, 1, first, last))
                case SectionHeaderItem():
                    blocks.append(Block(BlockKind.HEADING, item.text, item.level + 1, first, last))
                case TableItem():
                    blocks.append(Block(BlockKind.TABLE, item.export_to_markdown(document), None, first, last))
                case ListItem():
                    blocks.append(Block(BlockKind.LIST, f"- {item.text}", None, first, last))
                case CodeItem():
                    blocks.append(Block(BlockKind.CODE, item.text, None, first, last))
                case TextItem():
                    blocks.append(Block(BlockKind.PARAGRAPH, item.text, None, first, last))

        if not blocks:
            raise EmptyDocumentError(f"Docling found no text in {path.name}.")
        return ExtractedDocument(format=DocumentFormat.PDF, blocks=tuple(blocks))
